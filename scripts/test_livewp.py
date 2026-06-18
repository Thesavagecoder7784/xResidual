#!/usr/bin/env python3
"""THROWAWAY proof-of-concept for the Tier-A in-play win-probability model.

Two checks:
  1. model sanity on synthetic (score, minute) inputs — no data, proves the math
  2. overlay on ONE captured match's market mids — model fair-WP vs market implied, at each goal

    python scripts/test_livewp.py                                  # part 1 only
    python scripts/test_livewp.py --capture <slug> --home England --away Croatia \
        --p1 0.571 --pd 0.230 --p2 0.199                            # + part 2 (needs the tape)

If this looks right we build scripts/build_livewp.py + the live_match card overlay properly.
Approximations flagged TEST-GRADE: match clock = minutes since first quote (ignores halftime),
goals inferred from up-shocks in each side's win-mid. The real build gets goal minutes from a feed.
"""
from __future__ import annotations

import argparse
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _pois(k: int, m: float) -> float:
    return math.exp(-m) * m ** k / math.factorial(k)


def remaining_wp(lh: float, la: float, h: int, a: int, minutes_left: float, max_goals: int = 12):
    """P(home win / draw / away win) from current score (h,a) and minutes_left, via independent
    Poisson on the REMAINING goals each side scores (rate scaled by time left)."""
    f = max(minutes_left, 0.0) / 90.0
    mh, ma = max(lh * f, 1e-9), max(la * f, 1e-9)
    pw = pd = pl = 0.0
    for i in range(max_goals + 1):
        pi = _pois(i, mh)
        for j in range(max_goals + 1):
            p = pi * _pois(j, ma)
            fh, fa = h + i, a + j
            if fh > fa:
                pw += p
            elif fh == fa:
                pd += p
            else:
                pl += p
    s = pw + pd + pl or 1.0
    return pw / s, pd / s, pl / s


def fit_lambdas(p1: float, pd: float, p2: float):
    """Grid-search (lh,la) so the pre-game remaining_wp(.,.,0,0,90) matches the model's (p1,pd,p2)."""
    best, lo = None, 0.3
    vals = [lo + 0.05 * k for k in range(int((3.2 - lo) / 0.05) + 1)]
    for lh in vals:
        for la in vals:
            w, d, l = remaining_wp(lh, la, 0, 0, 90)
            err = (w - p1) ** 2 + (d - pd) ** 2 + (l - p2) ** 2
            if best is None or err < best[0]:
                best = (err, lh, la)
    return best[1], best[2]


def sanity(p1=0.571, pd=0.230, p2=0.199):
    print(f"=== PART 1: model sanity (pre-game {p1}/{pd}/{p2}) ===")
    lh, la = fit_lambdas(p1, pd, p2)
    w, d, l = remaining_wp(lh, la, 0, 0, 90)
    print(f"fitted lambdas: home={lh:.2f} away={la:.2f}  -> refit pre-game {w:.3f}/{d:.3f}/{l:.3f} (should match)")
    for lab, h, a, ml in [("kickoff 0-0", 0, 0, 90), ("halftime 0-0", 0, 0, 45),
                          ("70' 1-0 home", 1, 0, 20), ("89' 1-0 home", 1, 0, 1),
                          ("89' 1-1 draw", 1, 1, 1), ("60' 0-1 away", 0, 1, 30),
                          ("80' 2-2", 2, 2, 10), ("30' 2-0 home", 2, 0, 60)]:
        w, d, l = remaining_wp(lh, la, h, a, ml)
        print(f"  {lab:16s} -> H {w:.2f}  D {d:.2f}  A {l:.2f}")
    return lh, la


def overlay(capture, home, away, p1, pd, p2, kickoff_iso):
    from datetime import datetime, timezone
    from xresidual import ws_events as we
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import stream_micro as sm                                  # streaming single pass — fits the 898 MB VM
    print(f"\n=== PART 2: overlay on {home} vs {away} ({capture}) · kickoff {kickoff_iso} ===")
    lh, la = fit_lambdas(p1, pd, p2)
    data_dir = os.path.join(ROOT, "logger", "data")
    pairs = we.load_pairs(data_dir, capture=capture)
    bundle = sm.stream_all(os.path.join(data_dir, f"ws-events-{capture}.jsonl"), pairs)

    def mid_for(team):
        for pr in pairs:
            if pr.get("poly") and team.lower() in pr["label"].lower():
                return bundle["p_mid"].get(pr["poly"], [])
        return []

    hs, as_ = mid_for(home), mid_for(away)
    if len(hs) < 5 or len(as_) < 5:
        print(f"  could not load both legs (home {len(hs)}, away {len(as_)} pts)"); return

    # PROPER clock: anchor to kickoff, then subtract the ~15-min halftime once we're past it.
    t_kick = int(datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00")).timestamp() * 1000)
    def match_min(t):
        raw = (t - t_kick) / 60000.0                            # wall-clock minutes since kickoff
        if raw <= 0:
            return raw                                          # pre-kickoff (negative)
        return raw if raw <= 50 else raw - 15                   # 1st half (+stoppage) ~<=50; else drop halftime
    mkt = lambda s, t: min(s, key=lambda x: abs(x[0] - t))[1]

    goals = []
    for team, s in ((home, hs), (away, as_)):
        for sh in we.detect_shocks(s, lookback_ms=60000):
            if sh["jump"] > 0:
                goals.append((sh["t_ms"], team, sh["jump"]))
    goals.sort()
    print(f"  inferred {sum(g[1]==home for g in goals)}-{sum(g[1]==away for g in goals)} from shocks")
    print(f"  REAL goals: Kane 12', Baturina 36', Kane 42', Musa 45+5', Bellingham 47', Rashford 85'")

    h = a = 0
    print(f"  {'min':>5} {'event':<16} {'score':>5} | {'MODEL H/D/A':<22} | {'MKT H':>6} {'gap':>6}")
    print(f"  {'0':>5} {'kickoff':<16} {'0-0':>5} | pre-game {p1:.2f}/-/{p2:.2f}        | {mkt(hs,t_kick):.2f}")
    for t, team, jump in goals:
        m = match_min(t)
        if team == home:
            h += 1
        else:
            a += 1
        ml = max(0.0, 92 - m)
        w, d, l = remaining_wp(lh, la, h, a, ml)
        mh = mkt(hs, t + 30000)
        print(f"  {m:5.0f} {('GOAL '+team)[:16]:<16} {f'{h}-{a}':>5} | "
              f"{w:.2f}/{d:.2f}/{l:.2f}            | {mh:6.2f} {mh-w:+6.2f}")
    print("  gap = market home-WP minus model home-WP, ~30s after the goal")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture")
    ap.add_argument("--home"); ap.add_argument("--away")
    ap.add_argument("--p1", type=float, default=0.571)
    ap.add_argument("--pd", type=float, default=0.230)
    ap.add_argument("--p2", type=float, default=0.199)
    ap.add_argument("--kickoff", default="2026-06-17T20:00:00Z", help="kickoff in UTC (ISO)")
    a = ap.parse_args()
    sanity(a.p1, a.pd, a.p2)
    if a.capture and a.home and a.away:
        overlay(a.capture, a.home, a.away, a.p1, a.pd, a.p2, a.kickoff)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
