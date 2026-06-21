#!/usr/bin/env python3
"""Is the price-discovery lead harvestable? The cost-of-immediacy ledger at goals.
    -> viz/market/_harvest.js

    python scripts/build_harvest.py            # process NEW tapes, then re-pool
    python scripts/build_harvest.py --all
    python scripts/build_harvest.py --pool-only
    python scripts/build_harvest.py --limit 1

The flagship shows Polymarket prices a goal first. The honest follow-up: could a reactor on the
LAGGING venue actually capture that lead, or does the spread that opens at the goal (the
liquidity-withdrawal finding) eat it? Per goal we measure, in the SAME units (cents):

  gross  = |post-goal consensus mid - pre-goal consensus mid|   (the goal's worth, the most a
           reactor on the stale follower could in principle capture)
  cost   = follower's HALF-SPREAD *during the goal window* (the widened, withdrawn book) + fee
  net    = gross - cost

If net <= 0, the news is in the price before you can trade it (Demsetz 1968; Croxson-Reade 2014;
Budish-Cramton-Shim 2015) — the lead is real but not harvestable after the cost of immediacy. The
follower is whichever venue reacts later per goal; the cost uses its goal-time spread, which is why
this builds directly on top of the liquidity-at-goals measurement. Sign-free (mids + book spread),
so robust to the ~59% trade-direction problem (arXiv 2604.24366). Fork-forward: reuses frozen
ws_events + stream_micro; edits nothing under xresidual/.
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
from build_liquidity import detect_shocks              # noqa: E402  reuse goal detection

DATA_DIR = os.path.join(ROOT, "logger", "data")
HARV_DIR = os.path.join(ROOT, "viz", "market", "harvest")
OUT = os.path.join(ROOT, "viz", "market", "_harvest.js")
RESULTS = os.path.join(ROOT, "writeups", "_harvest_results.json")

MIN_JUMP = 0.04             # a real goal: consensus mid moves >= 4c
PRE = (-15000, -5000)       # pre-goal baseline (ms)
POST = (5000, 15000)        # post-goal, both venues settled (ms)
REACT_WIN = (-5000, 8000)   # search window for each venue's reaction onset
REACT_DEV = 0.02            # a venue "reacted" once its mid moved >= 2c from pre
SPREAD_WIN = (-1000, 4000)  # follower spread measured across the goal (the widened book)


def fee(venue, p):
    """Approx taker fee per contract. Kalshi: 0.07*p*(1-p). Polymarket: ~0 (gas only)."""
    return 0.07 * p * (1 - p) if venue == "kalshi" else 0.0


def _win_med(series, lo, hi):
    xs = [v for t, v in series if lo <= t <= hi]
    return st.median(xs) if xs else None


def _react_time(series, pre, lo, hi):
    for t, v in series:
        if t < lo:
            continue
        if t > hi:
            break
        if abs(v - pre) >= REACT_DEV:
            return t
    return None


def _last_le(series, t):
    v = None
    for tt, val in series:
        if tt <= t:
            v = val
        else:
            break
    return v


def _spread_med(tob, lo, hi):
    xs = [r["ask"] - r["bid"] for r in tob if lo <= r["t"] <= hi]
    return st.median(xs) if xs else None


def process_capture(cap):
    pairs = we.load_pairs(DATA_DIR, capture=cap)
    path = os.path.join(DATA_DIR, f"ws-events-{cap}.jsonl")
    if not pairs or not os.path.exists(path):
        print(f"  skip {cap}: no pairs/tape")
        return None
    bundle = sm.stream_all(path, pairs)
    match = _match_label(cap)
    ledger = []                                          # (follower, gross, cost, net, lead_ms)
    for pr in pairs:
        kt, pa = pr.get("kalshi"), pr.get("poly")
        if not kt or not pa:
            continue
        km, pm = bundle["k_mid"].get(kt, []), bundle["p_mid"].get(pa, [])
        ktob, ptob = bundle["k_tob"].get(kt, []), bundle["p_tob"].get(pa, [])
        if len(km) < 20 or len(pm) < 20:
            continue
        for t in detect_shocks(pm):
            pre_k, pre_p = _win_med(km, t + PRE[0], t + PRE[1]), _win_med(pm, t + PRE[0], t + PRE[1])
            post_k, post_p = _win_med(km, t + POST[0], t + POST[1]), _win_med(pm, t + POST[0], t + POST[1])
            if None in (pre_k, pre_p, post_k, post_p):
                continue
            pre_c, post_c = (pre_k + pre_p) / 2, (post_k + post_p) / 2
            gross = abs(post_c - pre_c)
            if gross < MIN_JUMP:                          # not a real goal-sized move
                continue
            rk = _react_time(km, pre_k, t + REACT_WIN[0], t + REACT_WIN[1])
            rp = _react_time(pm, pre_p, t + REACT_WIN[0], t + REACT_WIN[1])
            if rk is None or rp is None:
                continue
            if rp <= rk:                                 # poly led -> kalshi is the follower
                foll, ftob = "kalshi", ktob
            else:
                foll, ftob = "poly", ptob
            lead_ms = abs(rk - rp)
            spr = _spread_med(ftob, t + SPREAD_WIN[0], t + SPREAD_WIN[1])
            if spr is None or spr <= 0:
                continue
            cost = spr / 2.0 + fee(foll, post_c)
            ledger.append((foll, gross, cost, gross - cost, lead_ms))

    def summ(rows):
        if not rows:
            return None
        med = lambda a: sorted(a)[len(a) // 2]
        net = [r[3] for r in rows]
        return {"n": len(rows),
                "gross_med_c": round(med([r[1] for r in rows]) * 100, 2),
                "cost_med_c": round(med([r[2] for r in rows]) * 100, 2),
                "net_med_c": round(med(net) * 100, 2),
                "pct_harvestable": round(sum(1 for x in net if x > 0) / len(net) * 100, 1),
                "lead_ms_med": med([r[4] for r in rows])}

    payload = {"match": match, "capture": cap,
               "follower_kalshi": summ([r for r in ledger if r[0] == "kalshi"]),
               "follower_poly": summ([r for r in ledger if r[0] == "poly"]),
               "all": summ(ledger)}
    os.makedirs(HARV_DIR, exist_ok=True)
    name = (cap.split("-", 1)[1] if "-" in cap else cap) + ".json"
    with open(os.path.join(HARV_DIR, name), "w") as f:
        json.dump(payload, f, indent=2)
    a = payload["all"]
    print(f"  processed {match:<26} {a['n'] if a else 0} goals · "
          f"net {a['net_med_c'] if a else '-'}c · {a['pct_harvestable'] if a else '-'}% harvestable")
    return match


def pool_from_archive():
    allr = []
    n = 0
    for p in sorted(glob.glob(os.path.join(HARV_DIR, "*.json"))):
        d = json.load(open(p))
        n += 1
        s = d.get("all")
        if s and s.get("n"):
            allr.append(s)
    med = lambda a: sorted(a)[len(a) // 2] if a else None
    pooled = None
    if allr:
        pooled = {"n_matches": len(allr), "n_goals": sum(s["n"] for s in allr),
                  "gross_med_c": med([s["gross_med_c"] for s in allr]),
                  "cost_med_c": med([s["cost_med_c"] for s in allr]),
                  "net_med_c": med([s["net_med_c"] for s in allr]),
                  "pct_harvestable": med([s["pct_harvestable"] for s in allr]),
                  "lead_ms_med": med([s["lead_ms_med"] for s in allr])}
    payload = {"pooled": pooled, "n_matches": n, "min_jump": MIN_JUMP}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("window.HARVEST = " + json.dumps(payload) + ";\n")
    with open(RESULTS, "w") as f:
        json.dump(payload, f, indent=2)
    if pooled:
        print(f"POOLED · {pooled['n_matches']} matches · {pooled['n_goals']} goals · "
              f"gross {pooled['gross_med_c']}c vs cost {pooled['cost_med_c']}c -> "
              f"net {pooled['net_med_c']}c · {pooled['pct_harvestable']}% harvestable · lead {pooled['lead_ms_med']}ms")
    else:
        print(f"POOLED · {n} match-files · no goals yet")
    return payload


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--pool-only", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    os.makedirs(HARV_DIR, exist_ok=True)
    if args.pool_only:
        pool_from_archive()
        return 0
    caps = wc_captures(DATA_DIR)
    done = lambda c: os.path.exists(os.path.join(HARV_DIR, (c.split("-", 1)[1] if "-" in c else c) + ".json"))
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
