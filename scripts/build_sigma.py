#!/usr/bin/env python3
"""P8 sigma-sanity: are the biggest in-play repricings modest (no '12-sigma' events)?
    -> viz/market/_sigma.js + writeups/_sigma_results.json

    python scripts/build_sigma.py            # process NEW tapes, then re-pool
    python scripts/build_sigma.py --all
    python scripts/build_sigma.py --pool-only

Pre-registration P8 (secondary, genuine unknown), routine committed before capture (this file):
per contract, z = (largest one-second mid move in the match) / (std of one-second mid returns over
the prior 30 minutes). The match's z is the max over its contracts; the tournament's is the max over
matches. PASS if the biggest tournament z is <= 4 sigma, with typical largest shocks 2-3 sigma.

Sign-free (mids only), so robust to the ~59% trade-direction problem. The mid is a step function, so
1s returns are mostly zero between updates; the trailing-30min std is taken over the realized 1s
returns, and the zero-inflation caveat is reported alongside (a near-silent prior window inflates z).

Tape-bound: runs inside build_micro_all's single-parse driver (one parse feeds every pipeline) or
standalone. Fork-forward: reuses frozen ws_events + stream_micro; edits nothing under xresidual/.
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

DATA_DIR = os.path.join(ROOT, "logger", "data")
SIG_DIR = os.path.join(ROOT, "viz", "market", "sigma")
OUT = os.path.join(ROOT, "viz", "market", "_sigma.js")
RESULTS = os.path.join(ROOT, "writeups", "_sigma_results.json")

TRAIL_S = 1800          # 30-minute trailing window for the return std (in 1s steps)
MIN_WIN = 30            # need >=30 realized 1s returns in the prior window for a stable std
MIN_GRID = 120          # contract must span >=2 min of 1s grid to be considered


def _resample_1s(series):
    """series: sorted [(t_ms, mid), ...] -> [(sec, mid)] on a 1-second step grid (last value <= sec)."""
    if not series:
        return []
    t0, t1 = series[0][0] // 1000, series[-1][0] // 1000
    out, j, n, last = [], 0, len(series), series[0][1]
    for sec in range(t0, t1 + 1):
        while j < n and series[j][0] <= sec * 1000:
            last = series[j][1]
            j += 1
        out.append(last)
    return out


def _max_z(series):
    """Largest one-second move / trailing-30min std of 1s returns. Returns (z, move, sd, frac_nonzero)."""
    mids = _resample_1s(series)
    if len(mids) < MIN_GRID:
        return None
    rets = [mids[k] - mids[k - 1] for k in range(1, len(mids))]
    best = None
    for k in range(len(rets)):
        move = abs(rets[k])
        if move <= 0:
            continue
        window = rets[max(0, k - TRAIL_S):k]
        nz = [r for r in window if r != 0]
        if len(window) < MIN_WIN or len(nz) < 5:
            continue
        sd = st.pstdev(window)
        if sd <= 0:
            continue
        z = move / sd
        if best is None or z > best[0]:
            best = (z, move, sd, len(nz) / len(window))
    return best


def process_capture(cap, pairs=None, sm_bundle=None):
    if pairs is None:
        pairs = we.load_pairs(DATA_DIR, capture=cap)
    path = os.path.join(DATA_DIR, f"ws-events-{cap}.jsonl")
    if not pairs or (sm_bundle is None and not os.path.exists(path)):
        print(f"  skip {cap}: no pairs/tape")
        return None
    bundle = sm_bundle if sm_bundle is not None else sm.stream_all(path, pairs)
    match = _match_label(cap)
    rows = []                                            # (venue, z, move_c, sd_c, frac_nonzero)
    for pr in pairs:
        for venue, key, midmap in (("kalshi", pr.get("kalshi"), bundle["k_mid"]),
                                   ("poly", pr.get("poly"), bundle["p_mid"])):
            if not key:
                continue
            r = _max_z(midmap.get(key, []))
            if r:
                rows.append((venue, round(r[0], 2), round(r[1] * 100, 2), round(r[2] * 100, 3), round(r[3], 3)))
    top = max(rows, key=lambda x: x[1]) if rows else None
    payload = {"match": match, "capture": cap, "n_contracts": len(rows),
               "max_z": top[1] if top else None, "max_z_venue": top[0] if top else None,
               "max_move_c": top[2] if top else None, "trail_sd_c": top[3] if top else None,
               "max_z_nonzero_frac": top[4] if top else None,
               "per_contract": [{"venue": v, "z": z, "move_c": m, "sd_c": s, "nonzero_frac": f}
                                for v, z, m, s, f in sorted(rows, key=lambda x: -x[1])[:6]]}
    os.makedirs(SIG_DIR, exist_ok=True)
    name = (cap.split("-", 1)[1] if "-" in cap else cap) + ".json"
    with open(os.path.join(SIG_DIR, name), "w") as f:
        json.dump(payload, f, indent=2)
    print(f"  processed {match:<26} {len(rows)} contracts · max z {payload['max_z']} "
          f"(move {payload['max_move_c']}c / sd {payload['trail_sd_c']}c)")
    return match


def pool_from_archive():
    games, n = [], 0
    for p in sorted(glob.glob(os.path.join(SIG_DIR, "*.json"))):
        d = json.load(open(p))
        n += 1
        if d.get("max_z") is not None:
            games.append(d)
    pooled = None
    if games:
        zs = sorted(g["max_z"] for g in games)
        worst = max(games, key=lambda g: g["max_z"])
        med = zs[len(zs) // 2]
        pooled = {"n_matches": len(games), "tournament_max_z": worst["max_z"],
                  "tournament_max_match": worst["match"], "tournament_max_venue": worst["max_z_venue"],
                  "tournament_max_nonzero_frac": worst.get("max_z_nonzero_frac"),
                  "median_match_max_z": med, "max_z_le_4": bool(worst["max_z"] <= 4.0)}
    payload = {"pooled": pooled, "n_matches": n, "trail_s": TRAIL_S}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("window.SIGMA = " + json.dumps(payload) + ";\n")
    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    json.dump(payload, open(RESULTS, "w"), indent=2)
    if pooled:
        print(f"POOLED · {pooled['n_matches']} matches · tournament max z {pooled['tournament_max_z']} "
              f"({pooled['tournament_max_match']}, {pooled['tournament_max_venue']}, "
              f"nonzero-frac {pooled['tournament_max_nonzero_frac']}) · median match-max {pooled['median_match_max_z']} "
              f"· {'PASS <=4sigma' if pooled['max_z_le_4'] else 'FAIL >4sigma'}")
    else:
        print(f"POOLED · {n} match-files · no z yet")
    return payload


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--pool-only", action="store_true")
    args = ap.parse_args()
    os.makedirs(SIG_DIR, exist_ok=True)
    if args.pool_only:
        pool_from_archive()
        return 0
    caps = wc_captures(DATA_DIR)
    done = lambda c: os.path.exists(os.path.join(SIG_DIR, (c.split("-", 1)[1] if "-" in c else c) + ".json"))
    todo = caps if args.all else [c for c in caps if not done(c)]
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
