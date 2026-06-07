#!/usr/bin/env python3
"""Does winning your group pay? -> viz/model/_incentive.js.

    python scripts/build_incentive.py

Tournament-design research calls a format "incentive incompatible" when a team can be
better off NOT winning (Csato et al., arXiv:1804.04422). I make it concrete for 2026:
the bracket is fixed, so finishing 1st vs 2nd in a group sends you down different paths.
For each group I measure the difficulty of each path as the expected opponent Elo over
the first two knockout rounds (R32 + the projected R16 opponent), averaged over the
group-stage Monte Carlo. If the runner-up's path is easier than the winner's, winning
the group is self-defeating. Position-pure: the metric depends on the bracket and the
field, not on who actually finishes there.
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
from xresidual import baseline, data, elo, group_sim, knockout as K  # noqa: E402
from blend import blended_ratings  # noqa: E402
from pull_forecast_data import ISO  # noqa: E402

OUT = os.path.join(ROOT, "viz", "model", "_incentive.js")
N = 60_000


def main() -> int:
    res = elo.build_ratings(data.load_results())
    params = baseline.calibrate(res.calib)
    fx = pd.read_csv(os.path.join(ROOT, "data", "wc2026_fixtures.csv"))
    ratings = blended_ratings(res.ratings)

    print(f"simulating N={N:,} ...")
    out, det = group_sim.simulate(fx, ratings, params, n=N, return_detail=True, sigma=group_sim.MODEL_SIGMA)
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
        """(mean R32 opp Elo, mean projected R16 opp Elo, modal team in the slot)."""
        opp32 = rat[r32[:, i, 1 - j]]
        sidx = idx[sib[mid]]
        ra, rb = rat[r32[:, sidx, 0]], rat[r32[:, sidx, 1]]
        pa = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
        opp16 = pa * ra + (1 - pa) * rb
        return float(opp32.mean()), float(opp16.mean()), mode(r32[:, i, j])

    groups = []
    for L in "ABCDEFGHIJKL":
        wm, wi, wj = locate("W", L); rm, ri, rj = locate("R", L)
        w32, w16, wname = path(wm, wi, wj)
        r_32, r_16, rname = path(rm, ri, rj)
        win_path = (w32 + w16) / 2          # mean opponent Elo over the two rounds
        ru_path = (r_32 + r_16) / 2
        groups.append({
            "group": L,
            "winner": wname, "winner_iso": ISO.get(wname, ""),
            "runner": rname, "runner_iso": ISO.get(rname, ""),
            "win_path": round(win_path, 0), "ru_path": round(ru_path, 0),
            "delta": round(ru_path - win_path, 0),     # <0 => finishing 2nd is easier
            "win_r32": round(w32, 0), "ru_r32": round(r_32, 0),
        })
    groups.sort(key=lambda g: g["delta"])              # 2nd-easier groups first

    n_2nd = sum(1 for g in groups if g["delta"] < -5)  # ignore ~noise within +-5 Elo
    payload = {"groups": groups, "n_2nd_easier": n_2nd, "n": N}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.INCENTIVE = " + json.dumps(payload) + ";\n")
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {n_2nd} groups where finishing 2nd is easier")
    for g in groups:
        tag = "  <- 2nd easier" if g["delta"] < 0 else ""
        print(f"  {g['group']} {g['winner']:14} win {g['win_path']:.0f} vs 2nd {g['ru_path']:.0f}  "
              f"delta {g['delta']:+.0f}{tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
