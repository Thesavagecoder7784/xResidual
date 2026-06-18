#!/usr/bin/env python3
"""Tier-A live (in-play) win-probability model vs the live market.

    python scripts/build_livewp.py            # process NEW tapes, then re-pool
    python scripts/build_livewp.py --all
    python scripts/build_livewp.py --pool-only

For each captured match we already have the market's live repricing (tape mids). This adds the
MODEL side: a score+clock in-play win-probability (independent Poisson on remaining goals, rate
scaled by time left), calibrated so the pre-game WP matches our model's pre-game p1/pd/p2. Overlay
the two and, at each goal, compare the market's move to the model's well-defined fair-WP jump
(over/undershoot) and whether it reverts over the next minute — the goal-overreaction finding with
a fair-value anchor.

Clock (the thing the PoC got wrong): anchor to the real kickoff (data/wc2026_fixtures.csv) and
subtract the halftime break, detected as the longest quiet gap in quotes between 40-70 wall-minutes.

Goals: by default inferred from up-shocks in each side's win-mid (validated against the known final
score from docs/data/matches.js — the PoC reconstructed England 4-2 Croatia's full path exactly).
For exact goal MINUTES, set FOOTBALL_DATA_KEY (free at football-data.org) or drop a curated
data/wc_goals.json ({"England vs Croatia":[{"minute":12,"team":"England"},...]}); either overrides
the inference. A clock-only model is dumb about in-game dominance, so deviations away from goals are
NOT "market errors"; the trustworthy signal is the goal-anchored jump, where the fair move is defined.

Fork-forward: NEW scripts/ module; reuses frozen xresidual mids + the streaming reader; edits nothing
in xresidual/.
"""
from __future__ import annotations

import csv
import glob
import json
import math
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import ws_events as we           # noqa: E402  mids + shock detection
from build_leadlag import wc_captures, _match_label  # noqa: E402

DATA_DIR = os.path.join(ROOT, "logger", "data")
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
MATCHES = os.path.join(ROOT, "docs", "data", "matches.js")
GOALS_CURATED = os.path.join(ROOT, "data", "wc_goals.json")
LW_DIR = os.path.join(ROOT, "viz", "market", "livewp")          # per-match JSONs
OUT = os.path.join(ROOT, "viz", "market", "_livewp.js")          # pooled, for the site
RESULTS = os.path.join(ROOT, "writeups", "_livewp_results.json")
FULL_MIN = 92.0          # nominal full-time incl. typical stoppage, for "minutes left"
SETTLE_MS = 30000        # market WP measured ~30s after a goal (let the jump settle)
REVERT_MS = 90000        # and again ~90s after, to test reversion toward fair value


# ---- the in-play win-probability model (proven in test_livewp.py) --------------------------
def _pois(k: int, m: float) -> float:
    return math.exp(-m) * m ** k / math.factorial(k)


def remaining_wp(lh: float, la: float, h: int, a: int, minutes_left: float, max_goals: int = 12):
    """P(home win / draw / away win) from score (h,a) and minutes_left."""
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
    best, lo = None, 0.3
    vals = [lo + 0.05 * k for k in range(int((3.2 - lo) / 0.05) + 1)]
    for lh in vals:
        for la in vals:
            w, d, l = remaining_wp(lh, la, 0, 0, 90)
            err = (w - p1) ** 2 + (d - pd) ** 2 + (l - p2) ** 2
            if best is None or err < best[0]:
                best = (err, lh, la)
    return best[1], best[2]


# ---- reference data: kickoff, pre-game probs, (optional) curated goals ----------------------
def _parse_kickoff(date: str, time_str: str) -> int | None:
    """'2026-06-17','15:00 UTC-5' -> kickoff ms UTC."""
    m = re.match(r"(\d{1,2}):(\d{2})\s*UTC([+-]\d+)?", time_str.strip())
    if not m:
        return None
    hh, mm, off = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    try:
        dt = datetime.fromisoformat(date + "T00:00:00").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return int(dt.timestamp() * 1000) + (hh * 60 + mm) * 60000 - off * 3600000


def load_fixtures() -> dict:
    out = {}
    if not os.path.exists(FIXTURES):
        return out
    with open(FIXTURES, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            k = _parse_kickoff(r.get("date", ""), r.get("time", ""))
            out[(r["team1"], r["team2"])] = {"kickoff": k,
                                             "s1": _num(r.get("score1")), "s2": _num(r.get("score2"))}
    return out


def _num(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def load_pregame() -> dict:
    try:
        d = json.loads(open(MATCHES).read().split("=", 1)[1].strip().rstrip(";"))
    except Exception:
        return {}
    return {(g["t1"], g["t2"]): (g["p1"], g["pd"], g["p2"]) for g in d.get("matches", [])}


def load_curated_goals(match: str) -> list | None:
    """data/wc_goals.json or FOOTBALL_DATA_KEY override -> [{'minute':int,'team':str}] or None."""
    if os.path.exists(GOALS_CURATED):
        try:
            j = json.load(open(GOALS_CURATED))
            if match in j and j[match]:
                return sorted(j[match], key=lambda g: g["minute"])
        except Exception:
            pass
    return None  # FOOTBALL_DATA_KEY hook: a fetch_goals(match) can populate GOALS_CURATED out-of-band


# ---- clock: kickoff anchor + detected halftime ---------------------------------------------
def halftime_gap_ms(series, t_kick) -> int:
    """Longest gap between consecutive quotes in the 40-70 wall-minute window = the halftime break."""
    lo, hi = t_kick + 40 * 60000, t_kick + 70 * 60000
    ts = [t for t, _ in series if lo <= t <= hi]
    best = 0
    for i in range(1, len(ts)):
        best = max(best, ts[i] - ts[i - 1])
    return best if best > 4 * 60000 else 15 * 60000   # fall back to 15 min if no clear gap


def make_clock(t_kick, ht_gap_ms):
    """wall-clock ms -> match minute, removing the halftime break once we're past first-half play."""
    first_half_end = t_kick + (45 + ht_gap_ms / 60000 + 7) * 60000   # ~45' + stoppage just before the gap

    def mm(t):
        raw = (t - t_kick) / 60000.0
        if t <= first_half_end:
            return raw
        return raw - ht_gap_ms / 60000.0
    return mm


# ---- goals from shocks (validated vs final score) ------------------------------------------
def infer_goals(hs, as_, home, away, final):
    g = []
    for team, s in ((home, hs), (away, as_)):
        for sh in we.detect_shocks(s, lookback_ms=60000):
            if sh["jump"] > 0:
                g.append({"t_ms": sh["t_ms"], "team": team, "jump": round(sh["jump"], 4)})
    g.sort(key=lambda x: x["t_ms"])
    nh, na = sum(x["team"] == home for x in g), sum(x["team"] == away for x in g)
    ok = (final is None) or (nh == final[0] and na == final[1])
    return g, ok, (nh, na)


def process_capture(cap, pairs=None, sm_bundle=None, fixtures=None, pregame=None):
    fixtures = fixtures if fixtures is not None else load_fixtures()
    pregame = pregame if pregame is not None else load_pregame()
    if pairs is None:
        pairs = we.load_pairs(DATA_DIR, capture=cap)
    if sm_bundle is None:
        import stream_micro as _sm
        sm_bundle = _sm.stream_all(os.path.join(DATA_DIR, f"ws-events-{cap}.jsonl"), pairs)
    match = _match_label(cap)
    slug = cap.split("-", 1)[1] if "-" in cap else cap
    if " vs " not in match:
        return None
    home, away = [s.strip() for s in match.split(" vs ", 1)]

    fx = fixtures.get((home, away))
    pg = pregame.get((home, away))
    if not fx or not fx.get("kickoff") or not pg:
        print(f"  skip {match}: missing kickoff/pre-game"); return None
    lh, la = fit_lambdas(*pg)

    def mid_for(team):
        for pr in pairs:
            if pr.get("poly") and team.lower() in pr["label"].lower():
                return sm_bundle["p_mid"].get(pr["poly"], [])
        return []
    hs, as_ = mid_for(home), mid_for(away)
    if len(hs) < 10 or len(as_) < 10:
        print(f"  skip {match}: thin mids ({len(hs)}/{len(as_)})"); return None

    t_kick = fx["kickoff"]
    clock = make_clock(t_kick, halftime_gap_ms(hs, t_kick))
    final = (fx["s1"], fx["s2"]) if fx["s1"] is not None else None
    mkt = lambda s, t: min(s, key=lambda x: abs(x[0] - t))[1]

    curated = load_curated_goals(match)
    if curated:
        # exact MINUTES from feed/curation (for the model's minutes-left), but the accurate WALL time
        # from the matching shock (for reading the market move). Pair chronologically when counts agree.
        ig, _, _ = infer_goals(hs, as_, home, away, final)
        goals = []
        if len(ig) == len(curated):
            for cg, sh in zip(curated, ig):
                goals.append({"t_ms": sh["t_ms"], "team": cg["team"], "minute": cg["minute"]})
            src = "curated-min + shock-time"
        else:
            ht = halftime_gap_ms(hs, t_kick)
            for cg in curated:
                wt = t_kick + cg["minute"] * 60000 + (ht if cg["minute"] > 45 else 0)
                goals.append({"t_ms": wt, "team": cg["team"], "minute": cg["minute"]})
            src = f"curated-min + kickoff-time ({len(ig)} shocks != {len(curated)} goals)"
        goals.sort(key=lambda x: x["t_ms"])
        score_ok = True
    else:
        ig, score_ok, counts = infer_goals(hs, as_, home, away, final)
        goals = [{"t_ms": x["t_ms"], "team": x["team"], "minute": round(clock(x["t_ms"]), 1)} for x in ig]
        src = "shock-inferred" + ("" if score_ok else f" (MISMATCH {counts} vs final {final})")

    # walk goals: score timeline + per-goal fair jump vs market move + reversion
    h = a = 0
    events = []
    for g in goals:
        before = remaining_wp(lh, la, h, a, max(0.0, FULL_MIN - g["minute"]))
        if g["team"] == home:
            h += 1
        else:
            a += 1
        after = remaining_wp(lh, la, h, a, max(0.0, FULL_MIN - g["minute"]))
        model_jump = after[0] - before[0]                   # fair change in P(home win)
        mkt_pre = mkt(hs, g["t_ms"] - 5000)
        mkt_settle = mkt(hs, g["t_ms"] + SETTLE_MS)
        mkt_revert = mkt(hs, g["t_ms"] + REVERT_MS)
        events.append({"minute": round(g["minute"], 1), "team": g["team"], "score": f"{h}-{a}",
                       "model_home_before": round(before[0], 4), "model_home_after": round(after[0], 4),
                       "model_jump": round(model_jump, 4),
                       "mkt_home_pre": round(mkt_pre, 4), "mkt_home_settle": round(mkt_settle, 4),
                       "mkt_jump": round(mkt_settle - mkt_pre, 4),
                       "overshoot": round((mkt_settle - mkt_pre) - model_jump, 4),
                       "revert_60s": round(mkt_revert - mkt_settle, 4)})

    # continuous model WP line in match-minute space (for a future card overlay)
    line = []
    h = a = 0
    gi = 0
    for mm in range(0, int(FULL_MIN) + 1):
        while gi < len(goals) and goals[gi]["minute"] <= mm:
            if goals[gi]["team"] == home:
                h += 1
            else:
                a += 1
            gi += 1
        w, d, l = remaining_wp(lh, la, h, a, max(0.0, FULL_MIN - mm))
        line.append([mm, round(w, 3)])

    payload = {"match": match, "capture": cap, "home": home, "away": away, "pregame": pg,
               "lambdas": [round(lh, 3), round(la, 3)], "final": final, "goal_source": src,
               "score_reconstruction_ok": score_ok, "n_goals": len(goals),
               "goals": events, "model_home_line": line}
    os.makedirs(LW_DIR, exist_ok=True)
    with open(os.path.join(LW_DIR, slug + ".json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    flag = "" if score_ok else "  ⚠ score mismatch"
    print(f"  {match:<24} {len(goals)} goals · src={src.split(' ')[0]} · "
          f"mean overshoot {_mean(e['overshoot'] for e in events):+.3f}{flag} -> {slug}.json")
    return match


def _mean(xs):
    xs = [x for x in xs]
    return sum(xs) / len(xs) if xs else 0.0


def pool_from_archive() -> dict:
    matches, all_goals = [], []
    for path in sorted(glob.glob(os.path.join(LW_DIR, "*.json"))):
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict) or "goals" not in d:
            continue
        matches.append({"match": d["match"], "n_goals": d["n_goals"], "ok": d.get("score_reconstruction_ok"),
                        "src": d.get("goal_source")})
        for g in d["goals"]:
            all_goals.append(g)
    # headline: on average does the market over- or under-shoot the fair jump, and does it revert?
    n = len(all_goals)
    over = _mean(g["overshoot"] for g in all_goals)
    # reversion sign relative to the move: did the market come back TOWARD the model after settling?
    rev = _mean(-g["revert_60s"] * (1 if g["mkt_jump"] >= 0 else -1) for g in all_goals)
    payload = {"n_matches": len(matches), "n_goals": n,
               "mean_overshoot_home_wp": round(over, 4),
               "mean_reversion_60s": round(rev, 4),
               "matches": matches,
               "note": "In-play win-prob (independent Poisson on remaining goals, calibrated to the model's "
                       "pre-game p1/pd/p2), vs the live market, anchored at goals where the fair WP jump is "
                       "defined. overshoot = market's immediate move minus the model's fair jump (in P(home "
                       "win)); reversion = how far the market came back toward the model over the next ~90s. "
                       "Clock anchored to real kickoff with detected halftime. Goals shock-inferred (validated "
                       "vs final score) unless a feed/curated minute overrides. A clock-only model is blind to "
                       "in-game dominance, so only the goal-anchored numbers are trustworthy.",
               "significance_basis": "n_goals across n_matches is the unit"}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.LIVEWP = " + json.dumps(payload) + ";\n")
    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    with open(RESULTS, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    bad = [m["match"] for m in matches if not m["ok"]]
    print(f"POOLED · {len(matches)} match(es) · {n} goals")
    print(f"  mean overshoot (market move - fair jump, P(home)): {over:+.3f}")
    print(f"  mean reversion toward model over ~90s: {rev:+.3f}")
    if bad:
        print(f"  ⚠ score-reconstruction mismatch (need feed/curated goals): {', '.join(bad)}")
    print(f"wrote {os.path.relpath(OUT, ROOT)} + {os.path.relpath(RESULTS, ROOT)}")
    return payload


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Tier-A in-play win-probability vs live market")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--pool-only", action="store_true")
    args = ap.parse_args()
    os.makedirs(LW_DIR, exist_ok=True)
    if args.pool_only:
        pool_from_archive(); return 0
    fixtures, pregame = load_fixtures(), load_pregame()
    caps = wc_captures(DATA_DIR)
    done = lambda c: os.path.exists(os.path.join(LW_DIR, (c.split("-", 1)[1] if "-" in c else c) + ".json"))
    todo = caps if args.all else [c for c in caps if not done(c)]
    if todo:
        print(f"processing {len(todo)} tape(s) of {len(caps)}:")
        for cap in todo:
            try:
                process_capture(cap, fixtures=fixtures, pregame=pregame)
            except Exception as e:
                print(f"  {cap} failed: {type(e).__name__}: {e}")
    else:
        print(f"no new tapes ({len(caps)} present); re-pooling.")
    pool_from_archive()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
