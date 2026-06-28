#!/usr/bin/env python3
"""Simulate the full tournament (group stage -> Final) and write viz/_knockout.js for
the Model-vs-Market and R32-matchup cards.

    python scripts/build_knockout.py   # -> viz/_knockout.js  (window.KO)

Output:
  reach   = [{team,iso,color, model:{r16,qf,sf,final,win}, market:{...}}]  (top by model win)
  winner_opp = [{group, winner, winner_p, mean_opp_elo, via_third, opps:[{team,p}]}]
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
from pull_forecast_data import ISO, KIT, INK, team_probs  # noqa: E402
from blend import blended_ratings  # noqa: E402
from prediction_board import wc_played_results  # noqa: E402

OUT = os.path.join(ROOT, "viz", "model", "_knockout.js")
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")


def main() -> int:
    print("loading results + Elo + simulating group stage ...")
    df = data.load_results()
    res = elo.build_ratings(df)
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)   # Elo + squad value (Finding #10), not raw Elo
    fx = pd.read_csv(FIXTURES)
    grp_results = wc_played_results(df, fx)   # condition on games played (was UNCONDITIONED -> stale cards)
    out, det = group_sim.simulate(fx, ratings, params, return_detail=True,
                                  sigma=group_sim.MODEL_SIGMA, results=grp_results)

    print("simulating the knockouts ...")
    ko = knockout.simulate(det, out, ratings,
                           results=knockout.played_ko_results(det, fx))
    model = ko["reach"]

    print("pulling market reach-round + winner markets ...")
    try:
        mkt_raw = {
            "r16": team_probs("world-cup-nation-to-reach-round-of-16"),
            "qf": team_probs("world-cup-nation-to-reach-quarterfinals"),
            "sf": team_probs("world-cup-nation-to-reach-semifinals"),
            "final": team_probs("world-cup-nation-to-reach-final"),
            "win": team_probs("world-cup-winner"),
        }
    except Exception as e:
        print(f"  market unavailable ({e})")
        mkt_raw = {}

    def market_of(team):
        return {k: round(mkt_raw[k][team] * 100, 1) for k in mkt_raw if team in mkt_raw[k]} or None

    reach = []
    for t in model:
        reach.append({"team": t, "iso": ISO.get(t, ""), "color": KIT.get(t, INK),
                      "model": model[t], "market": market_of(t)})
    reach.sort(key=lambda r: -r["model"]["win"])

    winner_opp = [{**w, "iso": ISO.get(w["winner"], ""), "color": KIT.get(w["winner"], INK),
                   "opps": [{**o, "iso": ISO.get(o["team"], "")} for o in w["opps"]]}
                  for w in ko["winner_opp"]]

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.KO = " + json.dumps({"reach": reach, "winner_opp": winner_opp,
                "meta": {"n": 40000}}) + ";\n")
    print(f"wrote {OUT}: {len(reach)} teams, {len(winner_opp)} group-winner routes")
    print(f"  model champion top: " + ", ".join(f"{r['team']} {r['model']['win']:.0f}%" for r in reach[:4]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
