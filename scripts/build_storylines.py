#!/usr/bin/env python3
"""The tournament's storylines, by the numbers -> viz/model/_storylines.js.

    python scripts/build_storylines.py

Every preview asks these questions; the bracket sim answers them. Champion-level
scenarios are sums of per-team win probs (mutually exclusive); "any team from a set
reaches round R" comes from the per-round matchup arrays. Value-blended model, high N.
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
from blend import blended_ratings  # noqa: E402

OUT = os.path.join(ROOT, "viz", "model", "_storylines.js")
N = 200_000
CAF = ["Algeria", "Cape Verde", "DR Congo", "Egypt", "Ghana", "Ivory Coast",
       "Morocco", "Senegal", "South Africa", "Tunisia"]
HOSTS = ["USA", "Mexico", "Canada"]
DEBUTANTS = ["Cape Verde", "Curaçao", "Jordan", "Uzbekistan"]
PAST_WINNERS = ["Brazil", "Germany", "Argentina", "France", "Uruguay", "England", "Spain"]


def main() -> int:
    res = elo.build_ratings(data.load_results())
    params = baseline.calibrate(res.calib)
    fx = pd.read_csv(os.path.join(ROOT, "data", "wc2026_fixtures.csv"))
    ratings = blended_ratings(res.ratings)

    print(f"simulating N={N:,} ...")
    out, det = group_sim.simulate(fx, ratings, params, n=N, return_detail=True, sigma=group_sim.MODEL_SIGMA)
    ko = knockout.simulate(det, out, ratings, return_matchups=True)
    gidx, M, reach = det["gidx"], ko["matchups"], ko["reach"]

    def any_reaches(teams, rnd):
        idxs = [gidx[t] for t in teams if t in gidx]
        arr = M[rnd].reshape(M[rnd].shape[0], -1)
        return round(float(np.isin(arr, idxs).any(axis=1).mean()) * 100, 1)

    def win_sum(teams):
        return round(sum(reach[t]["win"] for t in teams if t in reach), 1)

    arg_adv = round(out["Argentina"]["padv"] * 100, 1)
    rows = [
        {"q": "An African team in the final?", "p": any_reaches(CAF, "Final"),
         "sub": f"Morocco most likely ({reach['Morocco']['final']:.0f}% to reach it) — no African side ever has"},
        {"q": "A host nation in the semis?", "p": any_reaches(HOSTS, "SF"),
         "sub": "Mexico's ceiling is the QF — reached only when it hosted (1970, 1986)"},
        {"q": "Argentina goes back-to-back?", "p": reach["Argentina"]["win"],
         "sub": f"no team has repeated since 1962; here it's {100-arg_adv:.0f}% to even exit in the group"},
        {"q": "A first-time champion?", "p": round(100 - win_sum(PAST_WINNERS), 1),
         "sub": "a new name on the trophy — Netherlands, Portugal, Morocco & co."},
        {"q": "A debutant in the Round of 16?", "p": any_reaches(DEBUTANTS, "R16"),
         "sub": "Curaçao (pop. 156k) is the smallest nation ever to qualify"},
        {"q": "Messi or Ronaldo lifts the trophy?", "p": win_sum(["Argentina", "Portugal"]),
         "sub": "the farewell tournament for both — a record 6th World Cup"},
    ]

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.STORYLINES = " + json.dumps({"rows": rows, "n": N}) + ";\n")
    print(f"wrote {OUT}")
    for r in rows:
        print(f"  {r['p']:5.1f}%  {r['q']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
