#!/usr/bin/env python3
"""Goal-gated overreaction fade, pooled across matches -> viz/model/_overreaction.js.

    python scripts/overreaction_build.py            # process NEW tapes, then re-pool
    python scripts/overreaction_build.py --all      # re-process every WC tape present
    python scripts/overreaction_build.py --pool-only # rebuild the pool from the per-game JSONs

This is the incremental, multi-match version of overreaction_run.py, built on the same
disposable-tape / per-game-JSON-is-truth architecture as build_leadlag.py:

  - process_capture() parses ONE 1 GB tape (heavy; laptop only, never the 900 MB VM), writes a
    per-game JSON, and is never run on that tape again;
  - pool_from_archive() rebuilds the pooled fade across EVERY per-game JSON, parsing no tapes.

The fix over overreaction_run.py: it fired on every 5pp jump, so a 1-1 game (two goals) became
~13 "shocks", most of them thin-market noise. Here each tape contributes ONE reference contract
(the most-liquid mid in the match, which reacts to BOTH teams' goals: own goal = up-shock,
opponent goal = down-shock), and we keep only the top-N persistent shocks by magnitude where
N = the match's actual goal count (from the fixtures score). So each match contributes ~its real
number of goals as clean trials, not a dozen noisy ones, and the pooled n is honest (one
observation per goal, not one per correlated contract).

v1 (xresidual/ws_events) is frozen: this REUSES its detect_shocks / overreaction_trade /
_ovr_summary primitives and adds the goal gate + pooling on top, editing nothing in xresidual/.
The documented edge (Choi & Hui; "Role of Surprise"): ~2-3%/trade fading a surprising goal ~2 min
in, reverting within ~6 min. Honest by construction: if it is gone, the pooled summary says so.
"""
from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import ws_events as we, wc2026_teams as W  # noqa: E402
from build_leadlag import wc_captures, _match_label       # noqa: E402  (same capture discovery)

DATA_DIR = os.path.join(ROOT, "logger", "data")
OVR_DIR = os.path.join(ROOT, "viz", "model", "overreaction")  # per-match JSONs (source of truth)
OUT = os.path.join(ROOT, "viz", "model", "_overreaction.js")  # pooled, for the site
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")

# Documented fade params (Choi & Hui): enter 2 min after a goal, exit at 6 min, fade the spike.
MIN_JUMP, ENTRY_S, EXIT_S, COST = 0.05, 120, 360, 0.005
LOOKBACK_MS, REFRACTORY_MS, CONFIRM_MS = 60000, 300000, 20000
DEFAULT_GOAL_CAP = 3            # fallback when the match score isn't found (typical goals/match)


def _bridge(t: str) -> str:
    return W.elo_name(W.canonical(t))


def match_goals(pairs: list[dict], cap: str) -> tuple[int | None, str]:
    """Total goals in the match, from the played-fixture score. Matches the two contract labels
    (the teams) against the fixtures row, name-bridged (USA/Bosnia variants differ across feeds).
    Returns (n_goals, source); n_goals=None only if both the fixtures score and results feed miss."""
    teams = {_bridge(p["label"]) for p in pairs if p.get("label")}
    if len(teams) != 2:
        return None, "no-2-teams"
    try:
        import pandas as pd
        fx = pd.read_csv(FIXTURES)
        for r in fx.itertuples(index=False):
            if {_bridge(r.team1), _bridge(r.team2)} == teams and pd.notna(r.score1) and pd.notna(r.score2):
                return int(r.score1) + int(r.score2), "fixtures"
    except Exception:
        pass
    try:                                                  # fall back to the canonical results feed
        from xresidual import data
        df = data.load_results()
        for r in df.itertuples(index=False):
            if {_bridge(r.home_team), _bridge(r.away_team)} == teams:
                return int(r.home_score) + int(r.away_score), "results"
    except Exception:
        pass
    return None, "not-found"


def _reference_series(events: list[dict], pairs: list[dict]):
    """The single most-liquid mid in the match (most ticks): it reacts to BOTH teams' goals, so
    one series carries every goal as a persistent shock. Returns (label, venue, series) or None."""
    best = None
    for pr in pairs:
        for venue, fn, key in (("kalshi", we.kalshi_mid_series, "kalshi"),
                               ("polymarket", we.polymarket_mid_series, "poly")):
            mid_id = pr.get(key)
            if not mid_id:
                continue
            series = fn(events, mid_id)
            if len(series) >= 10 and (best is None or len(series) > len(best[2])):
                best = (pr.get("label"), venue, series)
    return best


def process_capture(cap: str) -> str | None:
    """Parse ONE tape, goal-gate the shocks, fade each, write its per-game JSON. Heavy (a 1 GB tape
    parses to several GB) so it runs once per match on the laptop. Returns the match label or None."""
    events = we.load_ws_events(DATA_DIR, capture=cap)
    pairs = we.load_pairs(DATA_DIR, capture=cap)
    if not events or not pairs:
        return None
    match = _match_label(cap)
    slug = cap.split("-", 1)[1] if "-" in cap else cap
    n_goals, src = match_goals(pairs, cap)
    cap_n = n_goals if n_goals else DEFAULT_GOAL_CAP

    ref = _reference_series(events, pairs)
    trades, n_detected = [], 0
    if ref:
        label, venue, series = ref
        shocks = we.detect_shocks(series, min_jump=MIN_JUMP, lookback_ms=LOOKBACK_MS,
                                  refractory_ms=REFRACTORY_MS, confirm_ms=CONFIRM_MS)
        n_detected = len(shocks)
        # GATE: keep only the top-N persistent shocks by magnitude, N = the match's real goal count.
        # A goal moves win-probability more than thin-market noise, so the largest persistent moves
        # ARE the goals; capping at the score ties trials to real goals and drops the noise tail.
        kept = sorted(shocks, key=lambda s: -abs(s["jump"]))[:cap_n]
        for s in sorted(kept, key=lambda s: s["t_ms"]):
            tr = we.overreaction_trade(series, s, ENTRY_S, EXIT_S, COST)
            if tr:                                         # None if the 6-min exit runs past capture
                trades.append(tr)
    else:
        label, venue = None, None

    summary = we._ovr_summary(trades)
    os.makedirs(OVR_DIR, exist_ok=True)
    with open(os.path.join(OVR_DIR, slug + ".json"), "w", encoding="utf-8") as f:
        json.dump({"match": match, "capture": cap, "n_goals": n_goals, "goals_source": src,
                   "reference": {"label": label, "venue": venue}, "n_detected": n_detected,
                   "n_trades": len(trades), "trades": trades, "summary": summary,
                   "params": {"entry_s": ENTRY_S, "exit_s": EXIT_S, "min_jump": MIN_JUMP,
                              "cost_pp": COST * 100}}, f, indent=2)
    gtag = f"{n_goals}g/{src}" if n_goals is not None else f"cap{cap_n}/{src}"
    print(f"  processed {match:<22} {len(events):>10,} ev · {n_detected:>2} shocks -> "
          f"{len(trades)} goal-trades ({gtag}) · ref {label}/{venue} -> {slug}.json")
    del events
    return match


def pool_from_archive() -> dict:
    """Rebuild the pooled fade from EVERY per-game JSON. Parses no tapes -> instant and scaling."""
    all_trades, per_match = [], []
    for path in sorted(glob.glob(os.path.join(OVR_DIR, "*.json"))):
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict) or "trades" not in d:
            continue
        all_trades += d["trades"]
        per_match.append({"match": d.get("match"), "n_goals": d.get("n_goals"),
                          "n_trades": d.get("n_trades"), **d.get("summary", {})})
    summary = we._ovr_summary(all_trades)
    payload = {"summary": summary, "per_match": per_match, "n_matches": len(per_match),
               "params": {"entry_s": ENTRY_S, "exit_s": EXIT_S, "min_jump": MIN_JUMP,
                          "cost_pp": COST * 100, "refractory_min": REFRACTORY_MS // 60000,
                          "confirm_s": CONFIRM_MS // 1000, "gate": "top-N by |jump|, N = match goal count"},
       "note": "goal-gated overreaction fade, pooled across matches; paper, net of modeled cost; "
               "one trade per goal (top-N persistent shocks on the most-liquid mid). Live test of a "
               "documented ~2-3%/trade edge — if it is arbed away, the pooled summary says so."}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.OVERREACTION = " + json.dumps(payload) + ";\n")
    s = summary
    if s["n"]:
        print(f"POOLED · n={s['n']} trades across {len(per_match)} match(es) · total {s['total_pnl_pp']}pp "
              f"· hit {s['hit_rate']} · mean {s['mean_pnl_pp']}pp/trade · sharpe {s['per_trade_sharpe']}")
    else:
        print(f"POOLED · no goal-trades across {len(per_match)} match(es) yet")
    print(f"wrote {os.path.relpath(OUT, ROOT)} (pooled from {len(per_match)} per-game JSON(s))")
    return payload


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="incremental goal-gated overreaction fade: process NEW "
                                             "tapes, then pool from the per-game JSON archive")
    ap.add_argument("--all", action="store_true", help="re-process every WC tape present")
    ap.add_argument("--pool-only", action="store_true", help="rebuild the pool from JSONs; parse no tapes")
    args = ap.parse_args()
    os.makedirs(OVR_DIR, exist_ok=True)
    if args.pool_only:
        pool_from_archive()
        return 0
    caps = wc_captures(DATA_DIR)
    done = lambda c: os.path.exists(os.path.join(
        OVR_DIR, (c.split("-", 1)[1] if "-" in c else c) + ".json"))
    todo = caps if args.all else [c for c in caps if not done(c)]
    if todo:
        print(f"processing {len(todo)} new tape(s) of {len(caps)} present; the rest already archived:")
        for cap in todo:
            process_capture(cap)
    else:
        print(f"no new tapes to process ({len(caps)} present, all archived); re-pooling.")
    pool_from_archive()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
