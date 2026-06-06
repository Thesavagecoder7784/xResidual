#!/usr/bin/env python3
"""Diagnose + fix the model's favourite-overconfidence -> viz/model/_blend.js.

    python scripts/build_blend_check.py

Pure Elo over-rates the favourites because it only sees results. Blending in squad
value (Peeters 2018) closes the gap. We run the full sim under pure Elo and under
the value blend, and compare title odds to two independent sharp forecasters: the
market (Polymarket) and the Opta supercomputer. NOTE: we lack historical squad values,
so this is a consistency check (does the blend converge on the sharps?), not a backtest.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import baseline, data, elo, group_sim, knockout  # noqa: E402
from pull_forecast_data import ISO, KIT, INK, team_probs  # noqa: E402
from blend import blended_ratings, DEFAULT_W  # noqa: E402

OUT = os.path.join(ROOT, "viz", "model", "_blend.js")
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
# Opta supercomputer title odds (reference), June 2026.
OPTA = {"Spain": 16.1, "France": 13.0, "England": 11.2, "Argentina": 10.4,
        "Brazil": 6.6, "Portugal": 7.0, "Germany": 5.1}


def title_probs(ratings, params, fx, n=30000):
    out, det = group_sim.simulate(fx, ratings, params, n=n, return_detail=True)
    ko = knockout.simulate(det, out, ratings)
    return {t: ko["reach"][t]["win"] for t in ko["reach"]}


def main() -> int:
    res = elo.build_ratings(data.load_results())
    params = baseline.calibrate(res.calib)
    fx = pd.read_csv(FIXTURES)

    print(f"simulating pure Elo and value-blend (w={DEFAULT_W}) ...")
    elo_win = title_probs(res.ratings, params, fx)
    blend_win = title_probs(blended_ratings(res.ratings, DEFAULT_W), params, fx)

    mkt = team_probs("world-cup-winner")
    s = sum(mkt.values()) or 1
    mkt = {t: mkt[t] / s * 100 for t in mkt}

    teams = sorted(mkt, key=lambda t: -mkt[t])[:9]
    rows = [{"team": t, "iso": ISO.get(t, ""), "color": KIT.get(t, INK),
             "elo": round(elo_win.get(t, 0), 1), "blend": round(blend_win.get(t, 0), 1),
             "market": round(mkt[t], 1), "opta": OPTA.get(t)} for t in teams]

    def mae(key):
        return round(float(np.mean([abs(r[key] - r["opta"]) for r in rows if r["opta"] is not None])), 2)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.BLEND = " + json.dumps({"teams": rows, "w": DEFAULT_W,
                "mae_elo": mae("elo"), "mae_blend": mae("blend")}) + ";\n")
    print(f"wrote {OUT}: mean |model-Opta|  pure Elo {mae('elo')}pp -> blended {mae('blend')}pp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
