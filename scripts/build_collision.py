#!/usr/bin/env python3
"""Dream-matchup / collision probabilities -> viz/model/_collision.js.

    python scripts/build_collision.py

Records who-meets-whom at every knockout round across the full bracket sim, so I can
put a number on the question every preview asks but never answers: will Messi's
Argentina and Ronaldo's Portugal (who've never met in 48 World Cup games between them)
finally collide, and which heavyweight meetings is the bracket steering toward? Uses
the value-blended model and a high sim count for tight low-probability estimates.
"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import baseline, data, elo, group_sim, knockout  # noqa: E402
from pull_forecast_data import ISO, KIT, INK  # noqa: E402
from blend import blended_ratings  # noqa: E402
from prediction_board import wc_played_results  # noqa: E402

OUT = os.path.join(ROOT, "viz", "model", "_collision.js")
N = 200_000
ROUNDS = ["R32", "R16", "QF", "SF", "Final"]
CONTENDERS = ["Spain", "France", "England", "Argentina", "Brazil", "Portugal",
              "Germany", "Netherlands"]


def main() -> int:
    df = data.load_results()
    res = elo.build_ratings(df)
    params = baseline.calibrate(res.calib)
    fx = pd.read_csv(FIXTURES := os.path.join(ROOT, "data", "wc2026_fixtures.csv"))
    ratings = blended_ratings(res.ratings)
    grp_results = wc_played_results(df, fx)   # condition on games played (was UNCONDITIONED -> stale cards)

    print(f"simulating N={N:,} (value-blended) ...")
    out, det = group_sim.simulate(fx, ratings, params, n=N, return_detail=True,
                                  sigma=group_sim.MODEL_SIGMA, results=grp_results)
    ko = knockout.simulate(det, out, ratings, return_matchups=True)
    gidx, M = det["gidx"], ko["matchups"]

    def meet(a, b):
        ai, bi = gidx[a], gidx[b]
        by, tot = {}, 0
        for r in ROUNDS:
            arr = M[r]
            hit = int((((arr[:, :, 0] == ai) & (arr[:, :, 1] == bi)) |
                       ((arr[:, :, 0] == bi) & (arr[:, :, 1] == ai))).any(axis=1).sum())
            by[r] = round(hit / N * 100, 1); tot += hit
        return round(tot / N * 100, 1), by

    p, by = meet("Argentina", "Portugal")
    mr = {"a": "Argentina", "b": "Portugal", "a_label": "Messi", "b_label": "Ronaldo",
          "a_iso": ISO.get("Argentina"), "b_iso": ISO.get("Portugal"),
          "p": p, "by_round": by, "likely": max(by, key=by.get)}

    courses = []
    for i in range(len(CONTENDERS)):
        for j in range(i + 1, len(CONTENDERS)):
            a, b = CONTENDERS[i], CONTENDERS[j]
            pp, bb = meet(a, b)
            courses.append({"a": a, "b": b, "a_iso": ISO.get(a), "b_iso": ISO.get(b),
                            "ca": KIT.get(a, INK), "cb": KIT.get(b, INK),
                            "p": pp, "likely": max(bb, key=bb.get)})
    courses.sort(key=lambda r: -r["p"])

    # symmetric collision matrix for the top contenders (by model title odds)
    MT = sorted(ko["reach"], key=lambda t: -ko["reach"][t]["win"])[:12]
    P = [[0.0] * len(MT) for _ in MT]
    RND = [[""] * len(MT) for _ in MT]
    for i in range(len(MT)):
        for j in range(i + 1, len(MT)):
            p_ij, by = meet(MT[i], MT[j])
            P[i][j] = P[j][i] = p_ij
            r = max(by, key=by.get); RND[i][j] = RND[j][i] = r
    matrix = {"teams": [{"team": t, "iso": ISO.get(t, "")} for t in MT], "p": P, "round": RND}

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.COLLISION = " + json.dumps({"mr": mr, "courses": courses[:7],
                "matrix": matrix, "n": N}) + ";\n")
    print(f"wrote {OUT}: Messi-Ronaldo {p}% (likely {mr['likely']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
