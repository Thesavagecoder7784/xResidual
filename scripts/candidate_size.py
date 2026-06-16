#!/usr/bin/env python3
"""Size candidate entries (France-fade, Argentina-value) against the current paper book.

    python scripts/candidate_size.py

Computes each candidate's model probability (from the joint sim), the live Polymarket
price, the edge, and correlation-aware joint Kelly sizing IN THE CONTEXT of the open book
(correct sizing depends on what you already hold). Half-Kelly is the practical number.

PAPER ONLY (F-1). Prices are live mids, not depth-aware. Edges on deep-run markets are
partly the systematic deep-run overpricing we already measured, not purely team-specific.
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
sys.path.insert(0, os.path.join(ROOT, "logger"))
from xresidual import baseline, data, elo, group_sim, knockout, wc2026_teams  # noqa: E402
from blend import blended_ratings  # noqa: E402
from prediction_board import wc_played_results  # noqa: E402
from venue_prices import poly_quotes  # noqa: E402


def mid(q):
    b, a = q
    return (b + a) / 2 if b is not None and a is not None else (a or b)


def win_vector(market_type, team, side, det, paths, gidx):
    """per-sim boolean: did THIS SIDE win? market_type in {champion, reach_final,
    reach_sf, reach_qf, advance, group_win}."""
    c = gidx.get(wc2026_teams.canonical(team))
    if c is None:
        return None
    champ = paths["champ"].reshape(paths["champ"].shape[0], -1)
    arr = {"champion": champ, "reach_final": paths["wsf"], "reach_sf": paths["wqf"],
           "reach_qf": paths["w16"], "reach_r16": paths["w32"]}
    if market_type in arr:
        won = (arr[market_type] == c).any(axis=1)
    elif market_type == "advance":
        won = det["adv_mat"][:, c]
    elif market_type == "group_win":
        won = det["pos"][:, c] == 0
    else:
        return None
    return ~won if side == "no" else won


def book_win_vector(p, det, paths, gidx):
    m, o, s = p["market"], p["outcome"], p["side"]
    if "stage-of-elimination" in m:
        team = m.split("world-cup-")[1].split("-stage")[0].replace("-", " ").title()
        return win_vector("champion", team, s, det, paths, gidx)
    if "team-to-advance" in m:
        return win_vector("advance", o, s, det, paths, gidx)
    if "group" in m and "winner" in m:
        return win_vector("group_win", o, s, det, paths, gidx)
    if "reach-quarterfinals" in m:
        return win_vector("reach_qf", o, s, det, paths, gidx)
    return None


def joint_kelly(R, cap=0.9):
    try:
        from scipy.optimize import minimize
    except Exception:
        return None
    k = R.shape[1]
    neg = lambda f: -np.mean(np.log1p(R @ f))
    cons = [{"type": "ineq", "fun": lambda f: cap - np.sum(f)}]
    res = minimize(neg, np.full(k, cap / (2 * k)), method="SLSQP",
                   bounds=[(0.0, cap)] * k, constraints=cons, options={"maxiter": 800, "ftol": 1e-10})
    return np.clip(res.x, 0.0, None)


def main() -> int:
    print("building joint sim ...")
    df = data.load_results()
    res = elo.build_ratings(df)
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)
    fx = pd.read_csv(os.path.join(ROOT, "data", "wc2026_fixtures.csv"))
    grp_results = wc_played_results(df, fx)   # condition on games played (was UNCONDITIONED)
    sim, det = group_sim.simulate(fx, ratings, params, return_detail=True,
                                  sigma=group_sim.MODEL_SIGMA, results=grp_results)
    paths = knockout.simulate(det, sim, ratings, return_paths=True)["paths"]
    gidx = det["gidx"]

    winm = {t: mid(q) for t, q in poly_quotes(["world-cup-winner"]).items()}
    fin = {t: mid(q) for t, q in poly_quotes(["world-cup-nation-to-reach-final"]).items()}

    Fr, Ar = wc2026_teams.canonical("France"), wc2026_teams.canonical("Argentina")
    # candidate: (label, market_type, team, side, market price of THAT side)
    cands = [
        ("France NOT reach final", "reach_final", "France", "no", 1 - fin.get(Fr, 0)),
        ("France NOT champion",    "champion",    "France", "no", 1 - winm.get(Fr, 0)),
        ("Argentina champion",     "champion",    "Argentina", "yes", winm.get(Ar, 0)),
    ]

    # existing open book
    book = [p for p in json.load(open(os.path.join(ROOT, "paper", "positions.json"))) if p["status"] == "open"]

    rows, R = [], []
    for p in book:
        wv = book_win_vector(p, det, paths, gidx)
        if wv is None:
            continue
        pr = float(p["entry_price"])
        rows.append({"tag": f"#{p['id']} {p['side']} {p['outcome'][:14]}", "p": pr,
                     "q": round(float(wv.mean()), 3), "kind": "book"})
        R.append(wv / pr - 1.0)
    n_book = len(rows)
    for label, mt, team, side, price in cands:
        wv = win_vector(mt, team, side, det, paths, gidx)
        rows.append({"tag": label, "p": round(price, 3), "q": round(float(wv.mean()), 3), "kind": "cand"})
        R.append(wv / price - 1.0)
    R = np.array(R).T

    f_joint = joint_kelly(R)
    print(f"\n{'position':<26}{'side$price':>11}{'model':>7}{'edge':>8}{'½Kelly':>8}{'jointK':>8}  maxcorr w/ book")
    for i, r in enumerate(rows):
        edge = r["q"] - r["p"]
        fk = max(0.0, edge / (1 - r["p"])) * 50
        jk = f"{f_joint[i]*100:5.1f}%" if f_joint is not None else "n/a"
        corr = ""
        if r["kind"] == "cand" and n_book:
            cc = [np.corrcoef(R[:, i], R[:, j])[0, 1] for j in range(n_book)]
            k = int(np.argmax(np.abs(cc)))
            corr = f"{cc[k]:+.2f} ({rows[k]['tag']})"
        mark = "  " if r["kind"] == "book" else "->"
        print(f"{mark}{r['tag']:<24}{r['p']:>11.3f}{r['q']*100:>6.1f}%{edge*100:>+7.1f}pp{fk:>7.1f}%{jk:>8}  {corr}")

    print("\nnotes:")
    print("  - France NOT reach final: bigger edge, but partly the SYSTEMATIC deep-run overpricing")
    print("    (model is below market on reach-final for most teams), not purely France's route.")
    print("  - France NOT champion: cleaner team-specific fade, smaller edge.")
    print("  - Argentina champion: the only contender our model rates ABOVE market on the title;")
    print("    clean (champion market isn't deep-run-biased) but small.")
    print("  - jointK = correlation-aware full Kelly for the WHOLE book+candidates together.")
    print("  PAPER ONLY. Half-Kelly is the practical stake; full Kelly is a ceiling.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
