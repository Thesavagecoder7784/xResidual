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
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import ws_events as we  # noqa: E402

DATA = os.path.join(ROOT, "logger", "data")
OUT = os.path.join(ROOT, "viz", "market", "_livematch.js")
# role colours, matched to the original Peru-Spain card: favourite red, draw muted, underdog blue
FAV, DRAW, DOG = "#b3122a", "#8a8175", "#1e50c8"


def load_legs(capture=None) -> list:
    """[(display_label, poly_token)] from the capture's pairs: the two teams + the draw,
    draw label cleaned to 'Draw'. Match-agnostic so any captured fixture renders."""
    out = []
    for p in we.load_pairs(DATA, capture=capture):
        if not p.get("poly"):
            continue
        lab = p["label"]
        out.append(("Draw" if lab.lower().startswith("draw") else lab, p["poly"], lab))
    return out


def downsample(series, k=260):
    if len(series) <= k:
        return series
    step = len(series) / k
    return [series[min(len(series) - 1, int(i * step))] for i in range(k)] + [series[-1]]


def build_once(match: str | None = None) -> dict:
    cap = we.latest_capture(DATA)            # events + pairs from the SAME capture
    events = we.load_ws_events(DATA, capture=cap)
    raw, tmax, teams = [], 0.0, []
    for disp, tok, orig in load_legs(cap):
        s = we.polymarket_mid_series(events, tok)
        if len(s) < 2:
            continue
        t0 = s[0][0]
        ser = [[round((t - t0) / 1000, 1), round(v * 100, 2)] for t, v in s]
        # 60s window: markets reprice goals GRADUALLY, so a 4s window misses them (learned
        # live on Peru-Spain); the tightened detector also rejects thin-market noise blips.
        shocks = we.detect_shocks(s, lookback_ms=60000)
        sh = [{"t": round((x["t_ms"] - t0) / 1000, 1), "jump": round(x["jump"] * 100, 1)}
              for x in shocks]
        tmax = max(tmax, ser[-1][0])
        is_draw = disp == "Draw"
        raw.append({"label": disp, "is_draw": is_draw, "last": s[-1][1],
                    "now": round(s[-1][1] * 100, 1), "chg": round((s[-1][1] - s[0][1]) * 100, 1),
                    "n": len(s), "series": downsample(ser), "shocks": sh})
        if not is_draw:
            teams.append(disp)
    # order favourite (highest final win prob) -> draw -> underdog, and colour by role
    sides = sorted([r for r in raw if not r["is_draw"]], key=lambda r: -r["last"])
    draw = [r for r in raw if r["is_draw"]]
    ordered = ([sides[0]] if sides else []) + draw + sides[1:]
    fav_label = sides[0]["label"] if sides else None
    legs = []
    for r in ordered:
        color = DRAW if r["is_draw"] else (FAV if r["label"] == fav_label else DOG)
        legs.append({"label": r["label"], "color": color, "now": r["now"], "chg": r["chg"],
                     "n": r["n"], "series": r["series"], "shocks": r["shocks"]})
    if match is None:
        match = " vs ".join(teams) if teams else "Live match"
    return {"ts": time.strftime("%H:%M:%S"), "n_events": len(events), "match": match,
            "legs": legs, "t_max": round(tmax, 1)}


def write(payload):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.LIVE = " + json.dumps(payload) + ";\n")


def slug(match: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", match.lower()).strip("-") or "match"


def render_archive(match: str) -> str:
    """Render the live card to a PER-MATCH PNG so each fixture is archived separately and
    never overwrites another (the shared live_match.png is only the live working render).
    Renders the current _livematch.js, so call right after write()."""
    out = f"market/live_match-{slug(match)}.png"
    subprocess.run(["bash", os.path.join(ROOT, "viz", "render.sh"),
                    "market/live_match.html", out], check=True,
                   capture_output=True, text=True)
    return os.path.join(ROOT, "viz", out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", type=int, default=0, help="refresh every 5s for N seconds")
    ap.add_argument("--render", action="store_true",
                    help="also render a per-match PNG (live_match-<match>.png) — won't overwrite other fixtures")
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
    if a.render:
        png = render_archive(p["match"])
        print(f"archived {os.path.relpath(png, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
