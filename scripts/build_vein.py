#!/usr/bin/env python3
"""The format / advancement "vein" cards -> viz/model/_vein.js.

    python scripts/build_vein.py

One builder for the nine cards that all read off the SAME live-conditioned group +
knockout simulation (garbage_time, points_first, jeopardy_gd, dead_rubbers,
cross_group_butterfly, confederation_survival, softest_road, unequal_prize, clinch_first).
They used to inline
their headline numbers in the HTML, so build_all never touched them and they silently
went stale as games were played (a standalone drift-checker existed only to catch that).
Now they read window.VEIN and refresh with the rest of the pipeline.

Conditioning is build_bracket.live_results() — the live ledger (matches.js), NOT the
lagging Elo feed — so these stay in lock-step with the bracket / mispricing cards. One
40k sim feeds all eight; nothing here re-runs the model.
"""
from __future__ import annotations

import collections
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import baseline, data, elo, group_sim, knockout as K  # noqa: E402
from blend import blended_ratings                                   # noqa: E402
from build_bracket import live_results                              # noqa: E402
from build_drawluck import CONFED_OF                                # noqa: E402
from pull_forecast_data import ISO, ensure_flag                     # noqa: E402

OUT = os.path.join(ROOT, "viz", "model", "_vein.js")
N = 40_000
REGION = {"UEFA": "Europe", "CAF": "Africa", "CONMEBOL": "S. America",
          "AFC": "Asia", "CONCACAF": "N. America", "OFC": "Oceania"}


def main() -> int:
    df = data.load_results()
    res = elo.build_ratings(df)
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)
    fx = pd.read_csv(os.path.join(ROOT, "data", "wc2026_fixtures.csv"))
    live, _ = live_results()
    ngames = len(live) // 2
    print(f"building vein cards on {ngames} live games · N={N:,} ...")

    sim, det = group_sim.simulate(fx, ratings, params, n=N, return_detail=True,
                                  sigma=group_sim.MODEL_SIGMA, results=live)
    ko = K.simulate(det, sim, ratings, return_slots=True)

    pos, adv = det["pos"], det["adv_mat"]
    gd = det["gf"].astype(int) - det["ga"].astype(int)
    cut, miss = det["cutline"], det["missed"]
    teams = det["teams"]
    padv = {t: sim[t]["padv"] for t in sim}
    tg = {t: sim[t]["group"] for t in sim}

    # ---- garbage_time: P(advance | finish 3rd, goal difference = g) ----------------
    third = pos == 2
    g3, a3 = gd[third], adv[third]
    nthird = int(third.sum())
    # Plot the well-populated core window [-4, +3]. Outside it a third-place GD is a handful
    # of sims, AND P(adv|GD) is non-monotonic there because POINTS (not GD) drive advancement
    # — GD only breaks ties among teams level on points (see jeopardy_gd: ~72% of cuts). The
    # core window is where the -1 -> 0 cut-line cliff is both clean and well-sampled.
    curve = []
    for v in range(max(-4, int(g3.min())), min(3, int(g3.max())) + 1):
        m = g3 == v
        if m.sum() >= 0.01 * nthird:
            curve.append([v, round(a3[m].mean() * 100, 1)])
    pr = {v: p for v, p in curve}
    p_m1, p_0 = pr.get(-1), pr.get(0)
    garbage_time = {"curve": curve, "p_at_minus1": p_m1, "p_at_0": p_0,
                    "hinge_delta": round(p_0 - p_m1) if (p_m1 and p_0) else None}

    # ---- points_first: the HONEST version of the garbage_time cliff. P(adv|3rd,GD) is
    # confounded — high-GD thirds also tend to have more points. Control for it: reconstruct
    # each third's group POINTS (from the per-match signs), bucket vs the cut line, and read
    # the GD cliff ONLY among teams level on the cut. There GD is the actual decider and the
    # effect is causal (points held fixed). Above the cut a goal is worthless (already in),
    # below it worthless (already out) — the leverage lives entirely in the level band. ------
    pts3 = np.zeros((len(adv), len(teams)), dtype=np.int16)
    for (_L, t1, t2, sgn) in det["matches"]:
        i, j = det["gidx"][t1], det["gidx"][t2]
        pts3[:, i] += (sgn > 0) * 3 + (sgn == 0)
        pts3[:, j] += (sgn < 0) * 3 + (sgn == 0)
    rel = pts3[third] - np.broadcast_to(cut[:, None], pts3.shape)[third]   # third's pts vs cut
    below, level, above = rel < 0, rel == 0, rel > 0
    buckets = [{"label": "Behind on points", "padv": round(a3[below].mean() * 100, 1),
                "share": round(below.mean() * 100)},
               {"label": "Level on the cut", "padv": round(a3[level].mean() * 100, 1),
                "share": round(level.mean() * 100)},
               {"label": "Ahead on points", "padv": round(a3[above].mean() * 100, 1),
                "share": round(above.mean() * 100)}]
    nlevel = int(level.sum())
    lev_curve = []
    for v in range(max(-4, int(g3.min())), min(3, int(g3.max())) + 1):
        m = level & (g3 == v)
        if m.sum() >= 0.01 * nlevel:
            lev_curve.append([v, round(a3[m].mean() * 100, 1)])
    lp = {v: p for v, p in lev_curve}
    points_first = {"buckets": buckets, "level_curve": lev_curve,
                    "level_share": round(level.mean() * 100),
                    "p_at_minus1": lp.get(-1), "p_at_0": lp.get(0),
                    "marginal_gap": round(lp[0] - lp[-1]) if (lp.get(-1) and lp.get(0)) else None,
                    "full_swing": round(max(lp.values()) - min(lp.values()))}

    # ---- jeopardy_gd: how the last R32 ticket is decided ---------------------------
    jeopardy = {"pct_level": round((cut == miss).mean() * 100),
                "pct_cut3": round((cut == 3).mean() * 100),
                "cut_pts": int(np.median(cut))}

    # ---- dead_rubbers: clinched giants + the live win-and-in deciders --------------
    clinched = sorted((t for t in padv if padv[t] >= 0.999), key=lambda t: -padv[t])
    short = {"Bosnia & Herzegovina": "Bosnia", "South Korea": "S. Korea",
             "South Africa": "S. Africa", "Saudi Arabia": "Saudi Arabia"}
    sn = lambda t: short.get(t, t)
    deciders = [{"label": f"{sn(d['t1'])} v {sn(d['t2'])}", "grp": f"Group {d['grp']}",
                 "lev": round(d["lev"])} for d in group_sim.decisive_games(det, top=6)]
    dead_rubbers = {"clinched": [[t, ISO.get(t, "")] for t in clinched],
                    "n_clinched": len(clinched), "deciders": deciders}

    # ---- cross_group_butterfly: a Grp-G third's fate vs a Grp-D third's result -----
    gi = {L: np.array([i for i, t in enumerate(teams) if tg[t] == L]) for L in "ABCDEFGHIJKL"}
    ta = {L: adv[:, gi[L]][(pos[:, gi[L]] == 2)].astype(float) for L in gi}
    # NaN-safe: once the group stage resolves, ta["D"] is deterministic so one branch is empty
    # (.mean() -> NaN). The butterfly card is degenerate at that point; guard so the builder still
    # runs (the live knockout-route vein cards depend on it) and the frozen live version is kept.
    _po = ta["G"][ta["D"] == 0].mean(); _pi = ta["G"][ta["D"] == 1].mean()
    p_out = round(_po * 100) if _po == _po else 0     # Grp-D third misses
    p_in = round(_pi * 100) if _pi == _pi else 0      # Grp-D third sneaks in
    butterfly = {"p_if_out": p_out, "p_if_in": p_in, "swing": p_out - p_in}

    # ---- confederation_survival: expected number through, per confederation --------
    exp = collections.defaultdict(float)
    field = collections.Counter()
    for t in sim:
        c = CONFED_OF.get(t, "?")
        exp[c] += padv[t]
        field[c] += 1
    order = ["UEFA", "CAF", "CONMEBOL", "AFC", "CONCACAF", "OFC"]
    confed_rows = [[c, REGION.get(c, c), round(exp[c], 1), field[c]]
                   for c in order if c in exp]
    confederation = {"rows": confed_rows, "caf_expected": round(exp["CAF"], 1)}

    # ---- per-group winner / runner-up knockout paths (softest_road + unequal_prize)-
    rat = np.array(ko["rating_arr"]); tarr = np.array(ko["teams_arr"]); r32 = ko["r32"]
    idx = {mid: i for i, (mid, a, b) in enumerate(K.R32)}
    sib = {}
    for _m, f1, f2 in K.R16:
        sib[f1] = f2; sib[f2] = f1

    def locate(kind, L):
        for i, (mid, a, b) in enumerate(K.R32):
            for j, (k, v) in enumerate((a, b)):
                if k == kind and v == L:
                    return mid, i, j

    def mode_team(col):
        v, c = np.unique(col, return_counts=True)
        return tarr[v[np.argmax(c)]]

    def path(mid, i, j):
        """(mean opponent Elo over R32 + projected R16, modal team in this slot)."""
        o32 = rat[r32[:, i, 1 - j]]
        s = idx[sib[mid]]; ra, rb = rat[r32[:, s, 0]], rat[r32[:, s, 1]]
        pa = 1 / (1 + 10 ** ((rb - ra) / 400))
        o16 = pa * ra + (1 - pa) * rb
        return (o32.mean() + o16.mean()) / 2, mode_team(r32[:, i, j])

    soft_rows, trap_rows = [], []
    for L in "ABCDEFGHIJKL":
        wm, wi, wj = locate("W", L); rm, ri, rj = locate("R", L)
        win_path, wname = path(wm, wi, wj)
        ru_path, _ = path(rm, ri, rj)
        soft_rows.append({"team": wname, "iso": ISO.get(wname, ""), "group": f"Grp {L}",
                          "elo": round(win_path)})
        trap_rows.append({"team": wname, "iso": ISO.get(wname, ""), "group": f"Group {L}",
                          "delta": round(ru_path - win_path)})
    soft_rows.sort(key=lambda r: r["elo"])
    elos = [r["elo"] for r in soft_rows]
    softest_road = {"rows": soft_rows, "spread": max(elos) - min(elos),
                    "easiest": soft_rows[0], "hardest": soft_rows[-1]}
    trap_rows.sort(key=lambda r: r["delta"])
    traps = [r for r in trap_rows if r["delta"] < 0]
    unequal_prize = {"rows": trap_rows, "n_traps": len(traps),
                     "trap_teams": [r["team"] for r in traps]}

    # ---- clinch_first: the Group A winner's mystery R32 opponent -------------------
    wm, wi, wj = locate("W", "A")
    a_winner = mode_team(r32[:, wi, wj])
    opp = tarr[r32[:, wi, 1 - wj]]
    vals, counts = np.unique(opp, return_counts=True)
    dist = sorted(([tarr_i, int(c)] for tarr_i, c in zip(vals, counts)),
                  key=lambda x: -x[1])
    tot = len(opp)
    top = dist[:6]
    opp_rows = [[t, ISO.get(t, ""), round(c / tot * 100)] for t, c in top]
    other = round(sum(c for _, c in dist[6:]) / tot * 100)
    if other > 0:
        opp_rows.append(["other", "", other])
    clinch_first = {"group": "A", "winner": a_winner, "winner_iso": ISO.get(a_winner, ""),
                    "opponents": opp_rows, "modal_pct": opp_rows[0][2],
                    "n_opponents": int((counts / tot >= 0.02).sum())}

    payload = {
        "asof_games": ngames, "n": N,
        "garbage_time": garbage_time, "points_first": points_first,
        "jeopardy_gd": jeopardy, "dead_rubbers": dead_rubbers,
        "cross_group_butterfly": butterfly, "confederation": confederation,
        "softest_road": softest_road, "unequal_prize": unequal_prize, "clinch_first": clinch_first,
    }

    # flags used by the cards
    for t, iso in dead_rubbers["clinched"]:
        ensure_flag(iso)
    for r in soft_rows + trap_rows:
        ensure_flag(r["iso"])
    for row in opp_rows:
        ensure_flag(row[1])

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.VEIN = " + json.dumps(payload) + ";\n")
    print(f"wrote {os.path.relpath(OUT, ROOT)}:")
    print(f"  garbage_time hinge -1->0: {garbage_time['p_at_minus1']}% -> {garbage_time['p_at_0']}% "
          f"(+{garbage_time['hinge_delta']}pp)")
    print(f"  points_first: behind/level/ahead P(adv) = "
          f"{'/'.join(str(b['padv']) for b in buckets)}%; level-band GD -1->0 = "
          f"{points_first['p_at_minus1']}->{points_first['p_at_0']}% (+{points_first['marginal_gap']}pp honest)")
    print(f"  jeopardy: {jeopardy['pct_level']}% level on points, {jeopardy['pct_cut3']}% cut on 3 pts")
    print(f"  dead_rubbers: {dead_rubbers['n_clinched']} clinched, {len(deciders)} live deciders")
    print(f"  butterfly: {p_out}% vs {p_in}% ({butterfly['swing']}pp swing)")
    print(f"  confederation CAF: {confederation['caf_expected']} expected through")
    print(f"  softest_road: {softest_road['spread']} Elo spread "
          f"({softest_road['easiest']['team']} -> {softest_road['hardest']['team']})")
    print(f"  unequal_prize: {unequal_prize['n_traps']} traps ({', '.join(unequal_prize['trap_teams'])})")
    print(f"  clinch_first: Grp A = {a_winner}, modal opp {clinch_first['modal_pct']}%, "
          f"{clinch_first['n_opponents']} live opponents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
