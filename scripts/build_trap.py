#!/usr/bin/env python3
"""The bracket trap, priced -> viz/market/_trap.js  (CROSS: incentive geometry x market).

    python scripts/build_trap.py

Card #3 of the "cross two ideas" set. It pairs a MODEL quantity with a MARKET one,
keyed by group:

  * MODEL (path-delta) -- finishing 1st vs 2nd in a group sends you down different
    bracket paths. I measure each path's difficulty as the expected opponent Elo over
    the first two knockout rounds (R32 + projected R16), conditioned on every group game
    PLAYED SO FAR (so it is a live read, not the pre-tournament projection). delta < 0
    means the winner's path is harder -- winning the group is a trap (Csato et al.,
    incentive incompatibility).

  * MARKET (win premium) -- how much the prediction market pays for the group's
    favourite TO WIN the group, vs our model: premium = market price - model. From the
    live dashboard (docs/data/dashboard.js, "group_win" layer).

The cross: plot each group by (path-delta, win premium). The danger quadrant is the
teams the market most pays up to win -- in the groups where winning is the WORSE
outcome. Pro-market framing: the market prices likelihood and attention sharply; the
subtle thing it is not pricing is the fixed bracket's geometry.
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
from xresidual import baseline, data, elo, group_sim, knockout as K, wc2026_teams  # noqa: E402
from blend import blended_ratings  # noqa: E402
from prediction_board import wc_played_results  # noqa: E402
from pull_forecast_data import ISO  # noqa: E402

OUT = os.path.join(ROOT, "viz", "market", "_trap.js")
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
DASH = os.path.join(ROOT, "docs", "data", "dashboard.js")
N = 40_000


def load_group_win():
    """{team: (model%, price%)} for the live group-winner market."""
    raw = open(DASH, encoding="utf-8").read().split("=", 1)[1].rstrip().rstrip(";")
    dash = json.loads(raw)
    out = {}
    for f in dash["forecasts"]:
        if f["market"] == "group_win":
            out[f["team"]] = (f["model"], f["price"])
    return out


def path_deltas():
    """Per-group {group, delta, win_path, ru_path} from the conditioned joint sim."""
    df = data.load_results()
    res = elo.build_ratings(df)
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)
    fx = pd.read_csv(FIXTURES)
    grp_results = wc_played_results(df, fx)
    print(f"conditioning on {len(grp_results)//2} played group games · N={N:,}")
    out, det = group_sim.simulate(fx, ratings, params, n=N, return_detail=True,
                                  sigma=group_sim.MODEL_SIGMA, results=grp_results)
    ko = K.simulate(det, out, ratings, return_slots=True)
    r32 = ko["r32"]; rat = np.array(ko["rating_arr"]); teams = np.array(ko["teams_arr"])

    idx = {mid: i for i, (mid, a, b) in enumerate(K.R32)}
    sib = {}
    for _mid, f1, f2 in K.R16:
        sib[f1] = f2; sib[f2] = f1

    def locate(kind, L):
        for i, (mid, a, b) in enumerate(K.R32):
            for j, (k, v) in enumerate((a, b)):
                if k == kind and v == L:
                    return mid, i, j
        return None

    def mode(a):
        v, c = np.unique(a, return_counts=True)
        return teams[v[np.argmax(c)]]

    def path(mid, i, j):
        opp32 = rat[r32[:, i, 1 - j]]
        sidx = idx[sib[mid]]
        ra, rb = rat[r32[:, sidx, 0]], rat[r32[:, sidx, 1]]
        pa = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
        opp16 = pa * ra + (1 - pa) * rb
        return float(opp32.mean()), float(opp16.mean()), mode(r32[:, i, j])

    rows = {}
    for L in "ABCDEFGHIJKL":
        wm, wi, wj = locate("W", L); rm, ri, rj = locate("R", L)
        w32, w16, wname = path(wm, wi, wj)
        r_32, r_16, _ = path(rm, ri, rj)
        win_path = (w32 + w16) / 2
        ru_path = (r_32 + r_16) / 2
        rows[L] = {"delta": round(ru_path - win_path), "modal_winner": str(wname)}
    return fx, rows


def main() -> int:
    fx, deltas = path_deltas()
    gw = load_group_win()

    groups = []
    for L in "ABCDEFGHIJKL":
        teams = sorted(set(fx[fx.group == f"Group {L}"].team1) | set(fx[fx.group == f"Group {L}"].team2))
        # the team the MARKET most favours to win this group (the one "walking into" the path)
        cand = [(t, gw[t]) for t in teams if t in gw]
        if not cand:
            print(f"  Group {L}: no market group_win price, skipping"); continue
        team, (model_win, price_win) = max(cand, key=lambda c: c[1][1])
        d = deltas[L]["delta"]
        groups.append({
            "group": L, "team": team, "iso": ISO.get(team, ""),
            "delta": d,                                  # <0 => winning is a trap
            "model_win": round(model_win, 1),
            "market_win": round(price_win, 1),
            "premium": round(price_win - model_win, 1),  # >0 => market pays up to win
            "trap": d < -8,
        })

    groups.sort(key=lambda g: g["delta"])
    n_trap = sum(1 for g in groups if g["trap"])
    payload = {"groups": groups, "n_trap": n_trap, "n": N}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.TRAP = " + json.dumps(payload) + ";\n")
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {n_trap} trap groups")
    print(f"  {'grp':3} {'fav-to-win':14} {'delta':>6} {'mkt%':>6} {'mdl%':>6} {'prem':>6}")
    for g in groups:
        tag = "  <- TRAP" if g["trap"] else ""
        flag = "  *premium-to-win-a-trap*" if g["trap"] and g["premium"] > 3 else ""
        print(f"  {g['group']:3} {g['team']:14} {g['delta']:+6} {g['market_win']:6.1f} "
              f"{g['model_win']:6.1f} {g['premium']:+6.1f}{tag}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
