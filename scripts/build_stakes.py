#!/usr/bin/env python3
"""Stakes vs attention -> viz/market/_stakes.js  (CROSS: model leverage x market prominence).

    python scripts/build_stakes.py

Card #1 of the "cross two ideas" set, and the sequel to the decisive-games card (the
best-performing post). For every group game still to be played it pairs:

  * MODEL (stakes) -- Schilling leverage: the average swing in the two teams' advancement
    probability between this match being won vs lost (group_sim.decisive_games),
    conditioned on games played. The midtable six-pointers, not the glamour ties.

  * MARKET (attention) -- combined title-market prominence of the two sides, i.e. the
    sum of their "to win the World Cup" prices. This is where mainstream betting interest
    and eyeballs concentrate -- the star power of the matchup.

The cross: leverage (x) vs star power (y). The games that decide qualification and the
games people actually watch turn out to be different games -- the deciders sit bottom-
right (high stakes, no stars), the glamour ties drift top-left (stars, little at stake).
"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import baseline, data, elo, group_sim  # noqa: E402
from blend import blended_ratings  # noqa: E402
from prediction_board import wc_played_results  # noqa: E402
from pull_forecast_data import ISO, KIT, INK  # noqa: E402

OUT = os.path.join(ROOT, "viz", "market", "_stakes.js")
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
DASH = os.path.join(ROOT, "docs", "data", "dashboard.js")
N = 40_000


def champ_prices():
    raw = open(DASH, encoding="utf-8").read().split("=", 1)[1].rstrip().rstrip(";")
    d = json.loads(raw)
    return {f["team"]: f["price"] for f in d["forecasts"] if f["market"] == "champion"}


def main() -> int:
    df = data.load_results()
    res = elo.build_ratings(df)
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)
    fx = pd.read_csv(FIXTURES)
    grp_results = wc_played_results(df, fx)
    print(f"conditioning on {len(grp_results)//2} played group games · N={N:,}")
    _sim, det = group_sim.simulate(fx, ratings, params, n=N, return_detail=True,
                                   sigma=group_sim.MODEL_SIGMA, results=grp_results)
    games = group_sim.decisive_games(det, top=200)        # all still-live group games
    cp = champ_prices()

    rows = []
    for g in games:
        s1, s2 = cp.get(g["t1"], 0.0), cp.get(g["t2"], 0.0)
        rows.append({"grp": g["grp"], "t1": g["t1"], "t2": g["t2"],
                     "iso1": ISO.get(g["t1"], ""), "iso2": ISO.get(g["t2"], ""),
                     "lev": g["lev"], "star": round(s1 + s2, 1),
                     "s1": round(s1, 1), "s2": round(s2, 1)})
    rows.sort(key=lambda r: -r["lev"])
    payload = {"games": rows, "n": N}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.STAKES = " + json.dumps(payload) + ";\n")
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(rows)} live games")
    print(f"  {'grp':4}{'match':30}{'lev':>7}{'star':>7}")
    for r in rows[:14]:
        print(f"  {r['grp']:4}{r['t1']+' v '+r['t2']:30}{r['lev']:7.1f}{r['star']:7.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
