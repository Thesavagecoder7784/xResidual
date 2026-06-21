#!/usr/bin/env python3
"""Event-conditional price discovery: is Polymarket's information-share lead CONCENTRATED at
goals, or is it just as strong in calm play?   -> viz/market/_eventis.js

    python scripts/build_event_is.py            # process NEW tapes, then re-pool
    python scripts/build_event_is.py --all
    python scripts/build_event_is.py --pool-only
    python scripts/build_event_is.py --limit 1

The flagship reports ONE information share over the whole match (~78% Polymarket). This conditions
it on the news: for each cointegrated contract we run the same VECM / Hasbrouck-IS + Gonzalo-Granger
estimator (xresidual.microstructure.information_share, via build_infoshare.pair_infoshare) in two
regimes —

  GOAL windows : +/-180s around each detected goal
  CALM windows : 360s chunks at least 90s clear of any goal

— and compare Polymarket's share between them. If the share is higher in goal windows, price
discovery concentrates at the news (the lead is an information-event phenomenon, not a steady
background hum). Everything is on MIDS, so it inherits the flagship's robustness to the ~59%
trade-direction problem (arXiv 2604.24366).

NOTE: this reports the conditional Hasbrouck IS and Gonzalo-Granger share directly (same quantities
the flagship reports unconditionally). The noise-robust PutniNs (2013) Information Leadership Share
is the natural refinement once its combination is validated against the paper; the per-regime IS/CS
here is the defensible first cut. Fork-forward: reuses build_infoshare.pair_infoshare + stream_micro
+ build_liquidity.detect_shocks; edits nothing under xresidual/.
"""
from __future__ import annotations

import glob
import json
import os
import statistics as st
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import ws_events as we                  # noqa: E402
import stream_micro as sm                              # noqa: E402
from build_leadlag import wc_captures, _match_label    # noqa: E402
from build_infoshare import pair_infoshare             # noqa: E402  tested VECM/IS/CS on a series pair
from build_liquidity import detect_shocks              # noqa: E402

DATA_DIR = os.path.join(ROOT, "logger", "data")
EI_DIR = os.path.join(ROOT, "viz", "market", "eventis")
OUT = os.path.join(ROOT, "viz", "market", "_eventis.js")
RESULTS = os.path.join(ROOT, "writeups", "_eventis_results.json")

GOAL_HALF = 180_000        # +/-180s goal window (>= MIN_OVERLAP_MS so the VECM is estimable)
CALM_LEN = 360_000         # 360s calm chunk
CALM_CLEAR = 90_000        # a calm chunk must be this far from any goal


def _slice(series, lo, hi):
    return [(t, v) for t, v in series if lo <= t <= hi]


def _regime_shares(km, pm, goals):
    """Return (goal_rows, calm_rows); each row = (hasbrouck_poly, gg_poly) for a cointegrated window."""
    goal_rows, calm_rows = [], []
    # GOAL windows
    for g in goals:
        r = pair_infoshare(_slice(km, g - GOAL_HALF, g + GOAL_HALF),
                           _slice(pm, g - GOAL_HALF, g + GOAL_HALF))
        if r and r.get("cointegrated") and r.get("hasbrouck_a_mid") is not None:
            goal_rows.append((r["hasbrouck_a_mid"], r.get("gg_a")))
    # CALM windows
    t0 = max(km[0][0], pm[0][0])
    t1 = min(km[-1][0], pm[-1][0])
    c = t0
    while c + CALM_LEN <= t1:
        lo, hi = c, c + CALM_LEN
        if all(abs(g - (lo + hi) / 2) > (GOAL_HALF + CALM_CLEAR) for g in goals):
            r = pair_infoshare(_slice(km, lo, hi), _slice(pm, lo, hi))
            if r and r.get("cointegrated") and r.get("hasbrouck_a_mid") is not None:
                calm_rows.append((r["hasbrouck_a_mid"], r.get("gg_a")))
        c += CALM_LEN
    return goal_rows, calm_rows


def process_capture(cap):
    pairs = we.load_pairs(DATA_DIR, capture=cap)
    path = os.path.join(DATA_DIR, f"ws-events-{cap}.jsonl")
    if not pairs or not os.path.exists(path):
        print(f"  skip {cap}: no pairs/tape")
        return None
    bundle = sm.stream_all(path, pairs)
    match = _match_label(cap)
    goal_rows, calm_rows = [], []
    for pr in pairs:
        kt, pa = pr.get("kalshi"), pr.get("poly")
        if not kt or not pa:
            continue
        km, pm = bundle["k_mid"].get(kt, []), bundle["p_mid"].get(pa, [])
        if len(km) < 60 or len(pm) < 60:
            continue
        gr, cr = _regime_shares(km, pm, detect_shocks(pm))
        goal_rows += gr
        calm_rows += cr

    def summ(rows):
        if not rows:
            return None
        med = lambda a: sorted(a)[len(a) // 2]
        hb = [r[0] for r in rows if r[0] is not None]
        gg = [r[1] for r in rows if r[1] is not None]
        return {"n_windows": len(rows),
                "poly_hasbrouck_med": round(med(hb), 4) if hb else None,
                "poly_gg_med": round(med(gg), 4) if gg else None}

    payload = {"match": match, "capture": cap,
               "goal": summ(goal_rows), "calm": summ(calm_rows)}
    os.makedirs(EI_DIR, exist_ok=True)
    name = (cap.split("-", 1)[1] if "-" in cap else cap) + ".json"
    with open(os.path.join(EI_DIR, name), "w") as f:
        json.dump(payload, f, indent=2)
    gp = payload["goal"]["poly_gg_med"] if payload["goal"] else None
    cp = payload["calm"]["poly_gg_med"] if payload["calm"] else None
    print(f"  processed {match:<26} GG poly  goal={gp} calm={cp}")
    return match


def pool_from_archive():
    goal, calm = [], []
    n = 0
    for p in sorted(glob.glob(os.path.join(EI_DIR, "*.json"))):
        d = json.load(open(p))
        n += 1
        if d.get("goal"):
            goal.append(d["goal"])
        if d.get("calm"):
            calm.append(d["calm"])
    med = lambda a: sorted(a)[len(a) // 2] if a else None

    def poolv(rows):
        if not rows:
            return None
        hb = [r["poly_hasbrouck_med"] for r in rows if r.get("poly_hasbrouck_med") is not None]
        gg = [r["poly_gg_med"] for r in rows if r.get("poly_gg_med") is not None]
        return {"n_matches": len(rows), "n_windows": sum(r["n_windows"] for r in rows),
                "poly_hasbrouck_med": round(med(hb), 4) if hb else None,
                "poly_gg_med": round(med(gg), 4) if gg else None}

    payload = {"goal": poolv(goal), "calm": poolv(calm), "n_matches": n}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("window.EVENTIS = " + json.dumps(payload) + ";\n")
    with open(RESULTS, "w") as f:
        json.dump(payload, f, indent=2)
    g, c = payload["goal"], payload["calm"]
    if g and c:
        print(f"POOLED · GG poly: goals {g['poly_gg_med']} ({g['n_windows']}w) vs "
              f"calm {c['poly_gg_med']} ({c['n_windows']}w) · {payload['n_matches']} matches")
    else:
        print(f"POOLED · {n} match-files · need both regimes populated")
    return payload


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--pool-only", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    os.makedirs(EI_DIR, exist_ok=True)
    if args.pool_only:
        pool_from_archive()
        return 0
    caps = wc_captures(DATA_DIR)
    done = lambda c: os.path.exists(os.path.join(EI_DIR, (c.split("-", 1)[1] if "-" in c else c) + ".json"))
    todo = caps if args.all else [c for c in caps if not done(c)]
    if args.limit:
        todo = todo[:args.limit]
    print(f"processing {len(todo)} tape(s) of {len(caps)} present")
    for cap in todo:
        try:
            process_capture(cap)
        except Exception as e:
            print(f"  FAIL {cap}: {type(e).__name__}: {e}")
    pool_from_archive()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
