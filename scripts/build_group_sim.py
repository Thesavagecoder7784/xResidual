#!/usr/bin/env python3
"""Monte-Carlo the 2026 group stage and write viz/_groupsim.js for the reframed
Group-Openness card and the Third-Place-Lottery card.

    python scripts/build_group_sim.py   # -> viz/_groupsim.js  (window.GROUPSIM)

Output (probabilities, 0-1 scaled to % in the cards):
  groups[A..L] = [{team,iso,color, p1,p2,top2,p3,p3adv,padv,p4}]  (sorted by padv)
  thirds       = [{team,iso,color,grp, p3adv, cum}]  ranked by P(qualify as a third)
                 with `cum` = running sum of p3adv (crosses 8 where the spots fill, on avg)
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
from pull_forecast_data import ISO, KIT, INK, team_probs  # noqa: E402
from blend import blended_ratings  # noqa: E402
from prediction_board import wc_played_results  # noqa: E402

OUT = os.path.join(ROOT, "viz", "model", "_groupsim.js")
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")


def main() -> int:
    print("loading results + computing Elo ...")
    df = data.load_results()
    res = elo.build_ratings(df)
    params = baseline.calibrate(res.calib)
    print(f"  beta={params.beta:.3f} goals/100 Elo · total_goals={params.total_goals:.2f}")

    print("simulating the group stage ...")
    fixtures = pd.read_csv(FIXTURES)
    # blended (Elo + squad value) ratings: raw Elo is value-blind and mis-rates squad-strong
    # teams (Finding #10). On advancement it diverged from the market ~8.9pp; the blend halves
    # that to ~4.4pp and converges on the liquid advance market, so the sim runs on the blend.
    ratings = blended_ratings(res.ratings)
    # Condition on every group game played so far. Previously UNCONDITIONED, so the cards showed
    # PRE-TOURNAMENT numbers (e.g. Australia advancing ~38% after it had already beaten Turkey, vs
    # ~83% conditioned). Uses the same wc_played_results() the dashboard/bracket builds condition on,
    # so the whole site stays consistent and the third-place / openness / leverage cards update with
    # results. (Conditioning freshness tracks the results feed; if it lags, every conditioned build
    # lags together — not just this card.)
    grp_results = wc_played_results(df, fixtures)
    print(f"  conditioning on {len(grp_results) // 2} played group games")
    sim, det = group_sim.simulate(fixtures, ratings, params, return_detail=True,
                                  sigma=group_sim.MODEL_SIGMA, results=grp_results)

    # Market reference: Polymarket's P(advance) per team, for a model-vs-market overlay.
    try:
        mkt = team_probs("world-cup-team-to-advance-to-knockout-stages")
        print(f"  market advance reference: {len(mkt)} teams")
    except Exception as e:
        mkt = {}
        print(f"  market advance reference unavailable ({e}); overlay omitted")

    pc = lambda v: round(v * 100, 1)
    groups = {}
    for t, r in sim.items():
        row = {"team": t, "iso": ISO.get(t, ""), "color": KIT.get(t, INK),
               "p1": pc(r["p1"]), "p2": pc(r["p2"]), "top2": pc(r["top2"]),
               "p3": pc(r["p3"]), "p3adv": pc(r["p3adv"]), "padv": pc(r["padv"]),
               "p4": pc(r["p4"]),
               "mkt": pc(mkt[t]) if t in mkt else None}
        groups.setdefault(r["group"], []).append(row)
    for L in groups:
        groups[L].sort(key=lambda r: -r["padv"])

    # Third-place lottery: rank the field by P(qualify as a third), carry a running sum.
    thirds, cum = [], 0.0
    for t, r in sorted(sim.items(), key=lambda kv: -kv[1]["p3adv"]):
        if r["p3adv"] < 0.01:
            continue
        cum += r["p3adv"]
        thirds.append({"team": t, "iso": ISO.get(t, ""), "color": KIT.get(t, INK),
                       "grp": r["group"], "p3adv": pc(r["p3adv"]), "p3": pc(r["p3"]),
                       "cum": round(cum, 3)})

    # card metrics computed in the tested library; the build script only adds presentation
    cutline, cut_median = group_sim.third_place_cutline(det)   # #1 third-place cut line
    leverage = [{**g, "iso1": ISO.get(g["t1"], ""), "iso2": ISO.get(g["t2"], ""),  # #2 leverage
                 "c1": KIT.get(g["t1"], INK), "c2": KIT.get(g["t2"], INK)}
                for g in group_sim.decisive_games(det, top=12)]

    # coherence report (sums are exact by construction of the selection rule)
    print(f"  sum P(advance) = {sum(r['padv'] for r in sim.values()):.2f} (target 32)")
    print(f"  sum P(third-place qualifier) = {sum(r['p3adv'] for r in sim.values()):.2f} (target 8)")
    print(f"  cut line median = {cut_median} pts ; top decisive game = "
          f"{leverage[0]['t1']} v {leverage[0]['t2']} ({leverage[0]['lev']}pp)")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.GROUPSIM = " + json.dumps({"groups": groups, "thirds": thirds,
                "cutline": cutline, "cut_median": cut_median, "leverage": leverage,
                "meta": {"n": 40000}}) + ";\n")
    print(f"wrote {OUT}: {len(groups)} groups, {len(thirds)} third-place candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
