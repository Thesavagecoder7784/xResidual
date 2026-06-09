#!/usr/bin/env python3
"""Build the live in-play card data -> viz/market/_livematch.js.

Reconstructs each leg's mid from the running ws_capture and writes a payload the
self-refreshing card (viz/market/live_match.html) reads. Run once, or --watch to keep
it fresh while the match runs:

    python scripts/live_match_build.py
    python scripts/live_match_build.py --watch 12000   # refresh every 5s for N seconds
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import ws_events as we  # noqa: E402

DATA = os.path.join(ROOT, "logger", "data")
OUT = os.path.join(ROOT, "viz", "market", "_livematch.js")
COLORS = {"Spain": "#b3122a", "Draw": "#8a8175", "Peru": "#1e50c8"}
ORDER = ["Spain", "Draw", "Peru"]


def pairs_by_label(capture=None) -> dict:
    return {p["label"]: p["poly"] for p in we.load_pairs(DATA, capture=capture) if p.get("poly")}


def downsample(series, k=260):
    if len(series) <= k:
        return series
    step = len(series) / k
    return [series[min(len(series) - 1, int(i * step))] for i in range(k)] + [series[-1]]


def build_once(match="Peru vs Spain") -> dict:
    cap = we.latest_capture(DATA)            # events + pairs from the SAME capture
    events = we.load_ws_events(DATA, capture=cap)
    pmap = pairs_by_label(cap)
    legs, tmax = [], 0.0
    for lab in ORDER:
        tok = pmap.get(lab)
        if not tok:
            continue
        s = we.polymarket_mid_series(events, tok)
        if len(s) < 2:
            continue
        t0 = s[0][0]
        ser = [[round((t - t0) / 1000, 1), round(v * 100, 2)] for t, v in s]
        # 60s window: friendly markets reprice goals GRADUALLY, so a 4s window misses
        # them (learned live on Peru-Spain). Catch the cumulative move instead.
        shocks = we.detect_shocks(s, min_jump=0.05, lookback_ms=60000)
        sh = [{"t": round((x["t_ms"] - t0) / 1000, 1), "jump": round(x["jump"] * 100, 1)}
              for x in shocks]
        tmax = max(tmax, ser[-1][0])
        legs.append({"label": lab, "color": COLORS[lab], "now": round(s[-1][1] * 100, 1),
                     "chg": round((s[-1][1] - s[0][1]) * 100, 1), "n": len(s),
                     "series": downsample(ser), "shocks": sh})
    return {"ts": time.strftime("%H:%M:%S"), "n_events": len(events), "match": match,
            "legs": legs, "t_max": round(tmax, 1)}


def write(payload):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.LIVE = " + json.dumps(payload) + ";\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", type=int, default=0, help="refresh every 5s for N seconds")
    a = ap.parse_args()
    if a.watch:
        end = time.time() + a.watch
        while time.time() < end:
            write(build_once())
            time.sleep(5)
        return 0
    p = build_once()
    write(p)
    legs = " · ".join(f"{l['label']} {l['now']}% ({sum(len(x['shocks']) for x in p['legs'])} shocks total)"
                      for l in p["legs"][:1])
    print(f"wrote {os.path.relpath(OUT, ROOT)} · {p['n_events']:,} events · {legs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
