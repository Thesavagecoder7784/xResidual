#!/usr/bin/env python3
"""Treat the paper book as a CORRELATED portfolio, not independent singles.

    python scripts/portfolio_risk.py

The model already produces a coherent JOINT distribution (group_sim + knockout share one
set of simulations). This reuses those simulations to do what flat-stake single-bet logging
can't:

  1. Map every open paper position to its per-simulation payoff, so the book's P&L is a
     real joint distribution, not a sum of marginals.
  2. Report portfolio risk that accounts for correlation: P&L mean/sd, P(book loses),
     5%-VaR, and the pairwise correlation matrix (World Cup bets are highly correlated —
     "France to win" and "Germany NOT to win" move together; sizing that ignores this is
     wrong).
  3. Size the book three ways for contrast: current flat stakes, independent per-bet
     Kelly (edge only), and correlation-aware joint Kelly (growth-optimal on the actual
     joint payoffs). The gap between the last two IS the correlation cost.

Edge q-p uses the model's simulated probability q vs the price paid p (entry_price). PAPER
ONLY (F-1). Half-Kelly is reported as the practical recommendation; full Kelly is a ceiling.
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
from xresidual import baseline, data, elo, group_sim, knockout, wc2026_teams  # noqa: E402
from blend import blended_ratings  # noqa: E402

FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
LEDGER = os.path.join(ROOT, "paper", "positions.json")
OUT = os.path.join(ROOT, "viz", "market", "_portfolio.js")


def win_vector(pos, det, paths, gidx):
    """Per-simulation boolean: did THIS SIDE of the position win? Returns None if the
    position references a team/market we can't map to the joint sim."""
    market, outcome, side = pos["market"], pos["outcome"], pos["side"]
    champ = paths["champ"].reshape(paths["champ"].shape[0], -1)
    w16, w32 = paths["w16"], paths["w32"]

    def col(team):
        return gidx.get(wc2026_teams.canonical(team))

    # team-resolved markets
    if "stage-of-elimination" in market and outcome.lower() == "champion":
        c = col(market.split("world-cup-")[1].split("-stage")[0].replace("-", " ").title())
        if c is None:
            return None
        won = (champ == c).any(axis=1)               # this team is champion
    elif "team-to-advance" in market:
        c = col(outcome)
        if c is None:
            return None
        won = det["adv_mat"][:, c]                    # reached the knockouts
    elif "group" in market and "winner" in market:
        c = col(outcome)
        if c is None:
            return None
        won = det["pos"][:, c] == 0                   # finished 1st in group
    elif "reach-quarterfinals" in market:
        c = col(outcome)
        if c is None:
            return None
        won = (w16 == c).any(axis=1)                  # in the 8 QF participants
    elif "reach-round-of-16" in market:
        c = col(outcome)
        if c is None:
            return None
        won = (w32 == c).any(axis=1)
    else:
        return None
    return ~won if side == "no" else won              # NO side wins on the complement


def joint_kelly(R, cap=0.95):
    """Growth-optimal long-only fractions maximizing E[log(1 + R @ f)] on the sim payoffs.
    R is (n_sims, n_pos) of per-$ returns. Falls back to clipped per-bet Kelly if SciPy
    is unavailable."""
    k = R.shape[1]
    try:
        from scipy.optimize import minimize
    except Exception:
        return None
    neg_growth = lambda f: -np.mean(np.log1p(R @ f))
    cons = [{"type": "ineq", "fun": lambda f: cap - np.sum(f)}]   # no leverage
    res = minimize(neg_growth, np.full(k, cap / (2 * k)), method="SLSQP",
                   bounds=[(0.0, cap)] * k, constraints=cons,
                   options={"maxiter": 500, "ftol": 1e-9})
    return np.clip(res.x, 0.0, None)


def main() -> int:
    print("building joint simulation (Elo + blend + group + knockout) ...")
    res = elo.build_ratings(data.load_results())
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)
    fixtures = pd.read_csv(FIXTURES)
    sim, det = group_sim.simulate(fixtures, ratings, params, return_detail=True,
                                  sigma=group_sim.MODEL_SIGMA)
    ko = knockout.simulate(det, sim, ratings, return_paths=True)
    paths, gidx = ko["paths"], det["gidx"]
    n = det["adv_mat"].shape[0]

    book = [p for p in json.load(open(LEDGER, encoding="utf-8")) if p.get("status") == "open"]
    rows, R = [], []
    for p in book:
        wv = win_vector(p, det, paths, gidx)
        if wv is None:
            print(f"  [skip] unmapped: {p['market']} / {p['outcome']}")
            continue
        q = float(wv.mean())                          # model probability of this side
        pr = float(p["entry_price"])                  # price paid
        r = wv / pr - 1.0                              # per-$ return vector across sims
        rows.append({"id": p["id"], "label": f"{p['side'].upper()} {p['outcome']} "
                     f"[{p['market'].replace('world-cup-', '').replace('-', ' ')[:22]}]",
                     "stake": p["stake_usd"], "p": pr, "q": round(q, 3),
                     "edge": round(q - pr, 3)})
        R.append(r)
    R = np.array(R).T                                  # (n_sims, n_pos)
    stakes = np.array([r["stake"] for r in rows])
    bankroll = float(stakes.sum())                     # current deployed = the reference bankroll

    # ---- portfolio risk on CURRENT (flat) sizing ----------------------------------------
    pnl = R @ stakes                                   # per-sim $ P&L of the whole book
    var5 = float(np.percentile(pnl, 5))
    corr = np.corrcoef(R.T) if R.shape[1] > 1 else np.array([[1.0]])
    iu = np.triu_indices_from(corr, k=1)
    worst_pair = int(np.argmax(np.abs(corr[iu]))) if iu[0].size else None

    # ---- sizing: independent per-bet Kelly vs joint correlation-aware Kelly --------------
    f_indep = np.array([max(0.0, (r["q"] - r["p"]) / (1 - r["p"])) for r in rows])
    f_joint = joint_kelly(R)

    print(f"\nOpen positions: {len(rows)} | deployed ${bankroll:.0f} (flat ${stakes[0]:.0f} each)\n")
    print(f"{'#':>2} {'position':38} {'price':>6} {'model':>6} {'edge':>7} {'½Kelly':>7} {'jointK':>7}")
    for i, r in enumerate(rows):
        jk = f"{f_joint[i]*100:5.1f}%" if f_joint is not None else "  n/a"
        flag = "" if r["edge"] >= 0 else "  <-- model DISAGREES"
        print(f"{r['id']:>2} {r['label'][:38]:38} {r['p']:6.2f} {r['q']:6.2f} "
              f"{r['edge']*100:+6.1f}pp {f_indep[i]*50:5.1f}% {jk}{flag}")

    print(f"\n--- portfolio P&L on current flat sizing (joint, {n:,} sims) ---")
    print(f"  expected P&L   {pnl.mean():+.2f}  (on ${bankroll:.0f} deployed = {pnl.mean()/bankroll*100:+.1f}%)")
    print(f"  std dev        {pnl.std():.2f}")
    print(f"  P(book loses)  {float((pnl < 0).mean())*100:.1f}%")
    print(f"  5%-VaR         {var5:+.2f}  (5% of sims lose at least this much)")
    print(f"  sharpe-ish     {pnl.mean()/pnl.std():+.2f}  (mean/sd of terminal P&L)")
    if worst_pair is not None:
        a, b = rows[iu[0][worst_pair]], rows[iu[1][worst_pair]]
        print(f"  largest |corr| {corr[iu][worst_pair]:+.2f} between #{a['id']} and #{b['id']} "
              f"(flat sizing treats these as independent — they aren't)")

    if f_joint is not None:
        # apples-to-apples: FULL independent Kelly (capped to no-leverage) vs FULL joint Kelly.
        f_indep_capped = f_indep * min(1.0, 0.95 / max(f_indep.sum(), 1e-9))
        print(f"\n--- sizing comparison (fraction of bankroll, full Kelly) ---")
        print(f"  current flat:    {len(rows)} x {stakes[0]/bankroll*100:.0f}% = {stakes.sum()/bankroll*100:.0f}% deployed, edge-blind")
        print(f"  indep Kelly:     sum {f_indep_capped.sum()*100:.0f}% (edge-aware, correlation-blind)")
        print(f"  joint Kelly:     sum {f_joint.sum()*100:.0f}% (edge- AND correlation-aware)")
        g_flat = np.mean(np.log1p(R @ (stakes / bankroll)))
        g_indep = np.mean(np.log1p(R @ f_indep_capped))
        g_joint = np.mean(np.log1p(R @ f_joint))
        print(f"  log-growth/per: flat {g_flat:+.4f}  ->  indep-Kelly {g_indep:+.4f}  ->  joint-Kelly {g_joint:+.4f}")
        print(f"                  (edge-aware sizing adds {g_indep-g_flat:+.4f}; correlation adjustment adds {g_joint-g_indep:+.4f} more)")
        print(f"  NOTE: P&L/growth are under the MODEL's measure (assume the sim probs are right);")
        print(f"        they quantify sizing discipline, not whether the model beats the market.")

    payload = {"asof_sims": n, "bankroll": bankroll,
               "positions": [{**r, "f_indep_half": round(f_indep[i] * 50, 1),
                              "f_joint": round(float(f_joint[i]) * 100, 1) if f_joint is not None else None}
                             for i, r in enumerate(rows)],
               "pnl": {"mean": round(float(pnl.mean()), 2), "sd": round(float(pnl.std()), 2),
                       "p_loss": round(float((pnl < 0).mean()), 3), "var5": round(var5, 2)},
               "corr": np.round(corr, 2).tolist()}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.PORTFOLIO = " + json.dumps(payload) + ";\n")
    print(f"\nwrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
