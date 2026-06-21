#!/usr/bin/env python3
"""Liquidity around goals: does the order book thin out and widen the instant a goal lands,
and how fast does it refill?  ->  viz/market/_liquidity.js

    python scripts/build_liquidity.py            # process NEW tapes, then re-pool
    python scripts/build_liquidity.py --all      # reprocess every tape
    python scripts/build_liquidity.py --pool-only
    python scripts/build_liquidity.py --limit 1  # smoke test: just the first unprocessed tape

For each matched contract we detect goal shocks on the mid series (a fast >=4c move, the same
MIN_JUMP the lead-lag uses), then measure top-of-book SPREAD (ask-bid) and DEPTH (bid_sz+ask_sz)
in a pre-goal baseline window versus the moment of the goal, plus the time for the spread to
revert to near baseline (resilience). All comparisons are WITHIN a venue as ratios, because the
size units differ across Kalshi (contracts) and Polymarket (shares).

Memory-safe: one streaming pass per tape via stream_micro.stream_all (the same single-parse the
VM uses for OFI/lead-lag), so it never holds a whole 1.3GB tape in memory. Fork-forward: reuses
the frozen xresidual/ws_events + scripts/stream_micro + build_leadlag discovery; edits nothing
under xresidual/.
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
from xresidual import ws_events as we   # noqa: E402
import stream_micro as sm               # noqa: E402
from build_leadlag import wc_captures, _match_label   # noqa: E402

DATA_DIR = os.path.join(ROOT, "logger", "data")
LIQ_DIR = os.path.join(ROOT, "viz", "market", "liquidity")          # per-match JSONs (source of truth)
OUT = os.path.join(ROOT, "viz", "market", "_liquidity.js")          # pooled, for the site
RESULTS = os.path.join(ROOT, "writeups", "_liquidity_results.json")  # pooled detail for the writeup

MIN_JUMP = 0.04          # a goal's worth of mid move (prob units), matches build_leadlag
GRID_MS = 500            # downsample the mid series to this before shock detection (speed)
JUMP_WIN_MS = 4000       # the >=MIN_JUMP move must complete within this window
REFRACTORY_MS = 25000    # minimum gap between two distinct shocks
PRE = (-12000, -2000)    # baseline window before the shock (ms, relative)
AT = (-1000, 3000)       # the shock window (ms, relative)
POST_MAX = 30000         # look this far past the shock for spread reversion
RESILIENCE_MULT = 1.5    # spread "recovered" when back within 1.5x the pre-goal median


def _downsample(mids):
    """Keep one (t, mid) per GRID_MS bucket — enough to see a goal, fast to scan."""
    out = []
    last_t = -1e18
    for t, m in mids:
        if t - last_t >= GRID_MS:
            out.append((t, m))
            last_t = t
    return out


def detect_shocks(mids):
    """Shock times = a >=MIN_JUMP mid move completing within JUMP_WIN_MS, refractory-deduped."""
    g = _downsample(mids)
    out, n, last = [], len(g), -1e18
    for i in range(n):
        ti, mi = g[i]
        k = i + 1
        while k < n and g[k][0] - ti <= JUMP_WIN_MS:
            if abs(g[k][1] - mi) >= MIN_JUMP:
                tev = g[k][0]
                if tev - last >= REFRACTORY_MS:
                    out.append(tev)
                    last = tev
                break
            k += 1
    return out


def _win(tob, lo, hi):
    return [r for r in tob if lo <= r["t"] <= hi]


def measure(tob, shock_t):
    """(spread_widen, depth_withdraw, resilience_ms) for one shock, or None if too sparse."""
    pre = _win(tob, shock_t + PRE[0], shock_t + PRE[1])
    at = _win(tob, shock_t + AT[0], shock_t + AT[1])
    if len(pre) < 3 or len(at) < 1:
        return None
    spr = lambda r: r["ask"] - r["bid"]
    dep = lambda r: (r["bid_sz"] or 0.0) + (r["ask_sz"] or 0.0)
    spread_pre = st.median([spr(r) for r in pre])
    depth_pre = st.median([dep(r) for r in pre])
    if spread_pre <= 0 or depth_pre <= 0:
        return None
    spread_at = max(spr(r) for r in at)       # widest spread at the goal
    depth_at = min(dep(r) for r in at)        # thinnest book at the goal
    res = None
    for r in tob:
        if r["t"] <= shock_t + AT[1]:
            continue
        if r["t"] > shock_t + POST_MAX:
            break
        if spr(r) <= RESILIENCE_MULT * spread_pre:
            res = r["t"] - shock_t
            break
    return (spread_at / spread_pre, depth_at / depth_pre, res)


def _summ(rows):
    if not rows:
        return None
    med = lambda a: sorted(a)[len(a) // 2] if a else None
    res = [r[2] for r in rows if r[2] is not None]
    return {"n": len(rows),
            "spread_widen_med": round(med([r[0] for r in rows]), 2),
            "depth_withdraw_med": round(med([r[1] for r in rows]), 2),
            "resilience_ms_med": med(res), "n_recovered": len(res)}


def process_capture(cap):
    pairs = we.load_pairs(DATA_DIR, capture=cap)
    path = os.path.join(DATA_DIR, f"ws-events-{cap}.jsonl")
    if not pairs or not os.path.exists(path):
        print(f"  skip {cap}: no pairs/tape")
        return None
    bundle = sm.stream_all(path, pairs)
    match = _match_label(cap)
    rows = {"kalshi": [], "poly": []}
    for pr in pairs:
        for venue, midk, tobk, cid in (("kalshi", "k_mid", "k_tob", pr.get("kalshi")),
                                        ("poly", "p_mid", "p_tob", pr.get("poly"))):
            if not cid:
                continue
            mids = bundle[midk].get(cid, [])
            tob = bundle[tobk].get(cid, [])
            if len(mids) < 10 or len(tob) < 10:
                continue
            for stime in detect_shocks(mids):
                m = measure(tob, stime)
                if m:
                    rows[venue].append(m)
    payload = {"match": match, "capture": cap,
               "kalshi": _summ(rows["kalshi"]), "poly": _summ(rows["poly"])}
    os.makedirs(LIQ_DIR, exist_ok=True)
    name = (cap.split("-", 1)[1] if "-" in cap else cap) + ".json"
    with open(os.path.join(LIQ_DIR, name), "w") as f:
        json.dump(payload, f, indent=2)
    nk = payload["kalshi"]["n"] if payload["kalshi"] else 0
    npy = payload["poly"]["n"] if payload["poly"] else 0
    print(f"  processed {match:<26} kalshi {nk} shocks · poly {npy} shocks")
    return match


def pool_from_archive():
    rows = {"kalshi": [], "poly": []}
    n = 0
    for p in sorted(glob.glob(os.path.join(LIQ_DIR, "*.json"))):
        d = json.load(open(p))
        n += 1
        for v in ("kalshi", "poly"):
            s = d.get(v)
            if s and s.get("n"):
                rows[v].append((s["spread_widen_med"], s["depth_withdraw_med"],
                                s.get("resilience_ms_med"), s["n"]))

    def poolv(rs):
        if not rs:
            return None
        med = lambda a: sorted(a)[len(a) // 2] if a else None
        res = [r[2] for r in rs if r[2] is not None]
        return {"n_matches": len(rs), "n_shocks": sum(r[3] for r in rs),
                "spread_widen_med": round(med([r[0] for r in rs]), 2),
                "depth_withdraw_med": round(med([r[1] for r in rs]), 2),
                "resilience_ms_med": med(res)}

    payload = {"kalshi": poolv(rows["kalshi"]), "poly": poolv(rows["poly"]),
               "n_matches": n, "min_jump": MIN_JUMP}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("window.LIQUIDITY = " + json.dumps(payload) + ";\n")
    with open(RESULTS, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"POOLED · {n} match-files")
    for v in ("kalshi", "poly"):
        s = payload[v]
        if s:
            print(f"  {v:7s}: spread x{s['spread_widen_med']} · depth x{s['depth_withdraw_med']} "
                  f"at goals · refill {s['resilience_ms_med']}ms · {s['n_shocks']} shocks / {s['n_matches']} matches")
    return payload


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--pool-only", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    os.makedirs(LIQ_DIR, exist_ok=True)
    if args.pool_only:
        pool_from_archive()
        return 0
    caps = wc_captures(DATA_DIR)
    done = lambda c: os.path.exists(os.path.join(LIQ_DIR, (c.split("-", 1)[1] if "-" in c else c) + ".json"))
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
