#!/usr/bin/env python3
"""Auto-fire the cross-venue lead-lag flagship on captured websocket data.

    python scripts/build_leadlag.py

No hand-typed goal time, no hand-typed tickers. Reads the ws-events captured by
logger/ws_capture.py, reads the cross-venue pairs that capture recorded
(ws-pairs-*.jsonl), auto-detects price shocks (a goal / red card shows up as a fast
large mid move), and for every shock measures which venue repriced first. Writes:

  - viz/market/_leadlag.js     the cleanest (largest) event, for leadlag_tape.html
  - writeups/_leadlag_results.json   every event + the pooled lead, for the writeup

Safe to run anytime: with no capture yet it prints what's missing and exits 0, so it
can sit at the end of a capture (ws_capture --analyze) or in build_all without failing.
"""
from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import ws_events as we  # noqa: E402

DATA_DIR = os.path.join(ROOT, "logger", "data")
TAPE_OUT = os.path.join(ROOT, "viz", "market", "_leadlag.js")
RESULTS_OUT = os.path.join(ROOT, "writeups", "_leadlag_results.json")
MIN_JUMP = 0.04  # probability-units move that counts as a shock (~a goal's worth)


def tape_config(pair_result: dict) -> dict | None:
    """Turn the largest event of one pair into the leadlag_tape.html CONFIG."""
    evs = pair_result["events"]
    if not evs or not pair_result.get("tape"):
        return None
    best = max(evs, key=lambda e: e["jump"])
    ll = best.get("lead") or {}
    rx = best.get("poly_reaction") or best.get("kalshi_reaction") or {}
    leader = (ll.get("leader") or "synchronous").capitalize()
    return {"match": pair_result["label"], "moment": f"shock · Δ{best['jump']*100:+.0f}¢",
            "market": pair_result["label"],
            "leadSec": round(abs(ll.get("best_lag_ms", 0)) / 1000, 2),
            "leader": leader,
            "base": rx.get("pre", 0.5), "post": rx.get("settle", 0.5),
            "corr": round(ll.get("best_corr", 0), 3)}


def main() -> int:
    cap = we.latest_capture(DATA_DIR)        # events + pairs from the SAME capture
    events = we.load_ws_events(DATA_DIR, capture=cap)
    pairs = we.load_pairs(DATA_DIR, capture=cap)
    if not events:
        print("no ws-events yet — capture a match first:\n"
              "  python logger/ws_capture.py --match 'Team A vs Team B' --seconds 9000 --analyze")
        return 0
    if not pairs:
        print(f"{len(events):,} ws-events but no cross-venue pairs recorded "
              "(ws-pairs-*.jsonl). Capture via --match/--outright-test to record pairs.")
        return 0

    print(f"{len(events):,} events · {len(pairs)} cross-venue pair(s) · detecting shocks ...")
    results = we.auto_lead_lag(events, pairs, min_jump=MIN_JUMP)
    pooled = we.pool_leads(results)

    for r in results:
        print(f"  {r['label']:<22} {r['n_events']} shock(s)")
        for e in r["events"]:
            ll = e.get("lead")
            if ll:
                print(f"     Δ{e['jump']*100:+.0f}¢  {ll['leader']:<11} "
                      f"lead {ll['best_lag_ms']:+5d}ms  r={ll['best_corr']:.2f}")
    if pooled:
        lo, hi = pooled["iqr_ms"]
        print(f"POOLED · n={pooled['n']} · {pooled['leader']} leads "
              f"(median {pooled['median_lead_ms']:+.0f}ms, IQR [{lo:+.0f},{hi:+.0f}]) · "
              f"leader share {pooled['leader_share']:.0%}")

    os.makedirs(os.path.dirname(RESULTS_OUT), exist_ok=True)
    with open(RESULTS_OUT, "w", encoding="utf-8") as f:
        json.dump({"pairs": results, "pooled": pooled, "min_jump": MIN_JUMP}, f, indent=2)
    print(f"wrote {os.path.relpath(RESULTS_OUT, ROOT)}")

    # the cleanest event -> the tape card
    best_pair = max((r for r in results if r["events"]),
                    key=lambda r: max(e["jump"] for e in r["events"]), default=None)
    if best_pair:
        cfg = tape_config(best_pair)
        with open(TAPE_OUT, "w", encoding="utf-8") as f:
            f.write("window.LEADLAG = " + json.dumps(
                {"config": cfg, "data": {"poly": best_pair["tape"]["poly"],
                                         "kalshi": best_pair["tape"]["kalshi"]}}) + ";\n")
        print(f"wrote {os.path.relpath(TAPE_OUT, ROOT)}: {cfg['match']} · "
              f"{cfg['leader']} led {cfg['leadSec']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
