#!/usr/bin/env python3
"""Drift-check the INLINE-data cards against the live-conditioned simulation.

    python scripts/validate_cards.py

The builder-backed cards (group_sim / knockout / market / ...) refresh on fresh results via
`python scripts/build_all.py --pull`. But several cards INLINE their headline numbers in the HTML
(the format / advancement "vein" cards, plus draws_paradox), so build_all does NOT touch them and
they silently go stale as games are played.

This recomputes each inline card's headline number from the CURRENT live results (the same
conditioning the builder cards use) and flags any that have drifted past tolerance vs the value
baked into the card, so you can refresh before posting. **When you rebuild a card, update its
AS_BUILT value here.** Run order before a post: build_all.py --pull, then this.
"""
from __future__ import annotations

import collections
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import baseline, data, elo, group_sim, knockout as K   # noqa: E402
from blend import blended_ratings                                     # noqa: E402
from build_bracket import live_results                                # noqa: E402
from build_drawluck import CONFED_OF                                  # noqa: E402

N = 40_000
# card -> (as-built value baked into the HTML, absolute tolerance). Update when you rebuild a card.
AS_BUILT = {
    "garbage_time   (+pp at the -1->0 GD hinge)": (30, 3),
    "jeopardy_gd    (% of cuts level on points)": (72, 4),
    "jeopardy_gd    (% of cuts landing on 3 pts)": (83, 5),
    "dead_rubbers   (teams clinched, padv>=97%)": (17, 2),
    "dead_rubbers   (giant lock-ins, padv>=99.9%)": (13, 2),
    "cross_group_butterfly (Grp-G third swing, pp)": (20, 4),
    "confederation_survival (CAF expected through)": (6.5, 0.7),
    "softest_road   (easy-vs-hard winner spread, Elo)": (125, 25),
    "clinch_first   (Grp-A winner modal opponent %)": (31, 6),
    "unequal_prize  (# group-winner traps)": (3, 1),
}


def main() -> int:
    df = data.load_results()
    res = elo.build_ratings(df)
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)
    fx = pd.read_csv(os.path.join(ROOT, "data", "wc2026_fixtures.csv"))
    live, _ = live_results()
    print(f"validating inline cards against {len(live)//2} live games · N={N:,}\n")
    sim, det = group_sim.simulate(fx, ratings, params, n=N, return_detail=True,
                                  sigma=group_sim.MODEL_SIGMA, results=live)
    pos, adv = det["pos"], det["adv_mat"]
    gd = det["gf"].astype(int) - det["ga"].astype(int)
    cut, miss = det["cutline"], det["missed"]
    padv = {t: sim[t]["padv"] for t in sim}
    tg = {t: sim[t]["group"] for t in sim}
    teams = det["teams"]

    third = pos == 2
    g, a = gd[third], adv[third]
    pr = lambda v: a[g == v].mean() * 100 if (g == v).sum() else float("nan")

    gi = {L: np.array([i for i, t in enumerate(teams) if tg[t] == L]) for L in "ABCDEFGHIJKL"}
    ta = {L: adv[:, gi[L]][(pos[:, gi[L]] == 2)].astype(float) for L in gi}

    ce = collections.defaultdict(float)
    for t in sim:
        ce[CONFED_OF.get(t, "?")] += padv[t]

    ko = K.simulate(det, sim, ratings, return_slots=True)
    r32, rat, tarr = ko["r32"], np.array(ko["rating_arr"]), np.array(ko["teams_arr"])
    idx = {mid: i for i, (mid, aa, bb) in enumerate(K.R32)}
    sib = {}
    for _m, f1, f2 in K.R16:
        sib[f1] = f2; sib[f2] = f1

    def loc(kind, L):
        for i, (mid, aa, bb) in enumerate(K.R32):
            for j, (k, v) in enumerate((aa, bb)):
                if k == kind and v == L:
                    return mid, i, j

    def pathv(mid, i, j):
        o32 = rat[r32[:, i, 1 - j]]
        s = idx[sib[mid]]; ra, rb = rat[r32[:, s, 0]], rat[r32[:, s, 1]]
        pa = 1 / (1 + 10 ** ((rb - ra) / 400))
        return (o32.mean() + (pa * ra + (1 - pa) * rb).mean()) / 2

    wp = {}
    for L in "ABCDEFGHIJKL":
        wm, wi, wj = loc("W", L); rm, ri, rj = loc("R", L)
        wp[L] = (pathv(wm, wi, wj), pathv(rm, ri, rj) - pathv(wm, wi, wj))
    spread = max(v[0] for v in wp.values()) - min(v[0] for v in wp.values())
    traps = sum(1 for L in wp if wp[L][1] < 0)

    # Group A winner's modal R32 opponent share
    wm, wi, wj = loc("W", "A")
    opp = tarr[r32[:, wi, 1 - wj]]
    _, c = np.unique(opp, return_counts=True)
    top_opp = c.max() / len(opp) * 100

    live_vals = {
        "garbage_time   (+pp at the -1->0 GD hinge)": pr(0) - pr(-1),
        "jeopardy_gd    (% of cuts level on points)": (cut == miss).mean() * 100,
        "jeopardy_gd    (% of cuts landing on 3 pts)": (cut == 3).mean() * 100,
        "dead_rubbers   (teams clinched, padv>=97%)": sum(1 for t in padv if padv[t] >= 0.97),
        "dead_rubbers   (giant lock-ins, padv>=99.9%)": sum(1 for t in padv if padv[t] >= 0.999),
        "cross_group_butterfly (Grp-G third swing, pp)": (ta["G"][ta["D"] == 0].mean() - ta["G"][ta["D"] == 1].mean()) * 100,
        "confederation_survival (CAF expected through)": ce["CAF"],
        "softest_road   (easy-vs-hard winner spread, Elo)": spread,
        "clinch_first   (Grp-A winner modal opponent %)": top_opp,
        "unequal_prize  (# group-winner traps)": traps,
    }

    print(f"  {'metric':<48} {'live':>7}  {'card':>6}  status")
    drift = 0
    for k, (built, tol) in AS_BUILT.items():
        lv = live_vals[k]
        ok = abs(lv - built) <= tol
        drift += 0 if ok else 1
        print(f"  {k:<48} {lv:>7.1f}  {built:>6}  {'ok' if ok else 'DRIFT -> refresh'}")
    print(f"\n{'all inline cards current' if not drift else str(drift)+' card(s) drifted — refresh + update AS_BUILT'}")
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
