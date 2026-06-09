#!/usr/bin/env python3
"""Live terminal view of an in-play ws_capture.

Reconstructs each leg's mid from the ws-events file and refreshes every few seconds,
with sparklines and goal-shock alerts. Reads the poly token for each leg from today's
ws-pairs sidecar (by label).

    python logger/live_monitor.py                 # live loop (Ctrl-C to stop)
    python logger/live_monitor.py --legs Spain,Peru --every 3
    python logger/live_monitor.py --once          # one frame and exit

The capture keeps running in the background regardless of this monitor.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xresidual import ws_events as we  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SPARK = "▁▂▃▄▅▆▇█"


def pairs_by_label() -> dict:
    m = {}
    for p in sorted(glob.glob(os.path.join(DATA, "ws-pairs-*.jsonl")))[-1:]:  # latest only
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    d = json.loads(line)
                    if d.get("poly"):
                        m[d.get("label")] = d["poly"]
    return m


def spark(vals, n=46) -> str:
    v = vals[-n:]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    rng = (hi - lo) or 1e-9
    return "".join(SPARK[min(7, int((x - lo) / rng * 7.999))] for x in v)


def frame(labels, pmap) -> str:
    events = we.load_ws_events(DATA)
    out = ["\033[2J\033[H", f"  PERU vs SPAIN — live capture · {time.strftime('%H:%M:%S')} "
           f"· {len(events):,} events", "  " + "─" * 70]
    for lab in labels:
        tok = pmap.get(lab)
        if not tok:
            out.append(f"  {lab:8} (no token in pairs sidecar)")
            continue
        s = we.polymarket_mid_series(events, tok)
        if len(s) < 2:
            out.append(f"  {lab:8} (waiting for ticks…)")
            continue
        mids = [v for _, v in s]
        chg = mids[-1] - mids[0]
        shocks = we.detect_shocks(s, min_jump=0.03)
        out.append(f"  {lab:8} {mids[-1] * 100:5.1f}%  {spark(mids)}  "
                   f"({chg * 100:+.1f}pp · {len(s)} ticks · {len(shocks)} shock(s))")
        for sh in shocks[-2:]:
            out.append(f"           ↳ shock {sh['pre'] * 100:.0f}→{sh['post'] * 100:.0f}% "
                       f"({sh['jump'] * 100:+.0f}pp)")
    out += ["  " + "─" * 70, "  Ctrl-C to stop (capture keeps running in background)"]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--legs", default="Spain,Draw,Peru")
    ap.add_argument("--every", type=float, default=4.0)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    labels = [x.strip() for x in a.legs.split(",")]
    pmap = pairs_by_label()
    if a.once:
        print(frame(labels, pmap))
        return 0
    try:
        while True:
            print(frame(labels, pmap), flush=True)
            time.sleep(a.every)
    except KeyboardInterrupt:
        print("\nstopped (capture still running in background)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
