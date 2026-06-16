#!/usr/bin/env python3
"""Scan upcoming group games for goal-market (BTTS / totals) leans -> stdout.

    python scripts/scan_goalmarkets.py

Match goal markets are UNCORRELATED with the advancement/FLB book, and play to the goal
model's strength (well-calibrated on draws + BTTS: ~+0.2pp bias over 8,110 games) with one
known haircut: it runs ~4pp HOT on Over 2.5, so we shade Over down / Under up before trading.
This prints the model's leans so we can check the live Polymarket "more-markets" price on the
strongest and deploy the freed $100 somewhere orthogonal to the FLB core.
"""
from __future__ import annotations

import math
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import baseline, data, elo, group_sim, skellam  # noqa: E402
from blend import blended_ratings  # noqa: E402

FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
OVER_HAIRCUT = 0.04          # model runs ~4pp hot on Over 2.5; shade Over down, Under up


def poisson_le(lam, k):      # P(N <= k), N ~ Poisson(lam)
    return sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k + 1))


def main() -> int:
    res = elo.build_ratings(data.load_results())
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)
    fx = pd.read_csv(FIXTURES)
    up = fx[fx["group"].astype(str).str.startswith("Group") & fx["score1"].isna()].copy()

    rows = []
    for r in up.itertuples(index=False):
        l1, l2 = group_sim._match_lambdas(r.team1, r.team2, r.ground, ratings, params)
        p1, pd_, p2 = skellam.wdl_probs(l1, l2)
        lam = l1 + l2
        p_btts = (1 - math.exp(-l1)) * (1 - math.exp(-l2))
        p_under = poisson_le(lam, 2)
        p_over = 1 - p_under
        # haircut-adjusted (the tradeable numbers)
        over_adj = max(0.0, p_over - OVER_HAIRCUT)
        under_adj = min(1.0, p_under + OVER_HAIRCUT)
        rows.append({"date": str(r.date), "g": str(r.group).replace("Group ", ""),
                     "m": f"{r.team1} v {r.team2}", "l1": l1, "l2": l2, "tot": lam,
                     "btts": p_btts, "under_adj": under_adj, "over_adj": over_adj,
                     "p1": p1, "pd": pd_, "p2": p2})

    print(f"{len(rows)} upcoming group games · Over-2.5 haircut {OVER_HAIRCUT*100:.0f}pp applied\n")

    print("== strongest UNDER 2.5 leans (model not hot here; public loves Overs) ==")
    for r in sorted(rows, key=lambda r: -r["under_adj"])[:8]:
        print(f"  {r['date']} {r['g']:2} {r['m']:30} xG {r['l1']:.2f}-{r['l2']:.2f} tot {r['tot']:.2f}  "
              f"UNDER2.5 {r['under_adj']*100:4.0f}%  (BTTS {r['btts']*100:.0f}%)")

    print("\n== strongest BTTS-NO leans (mismatch shutouts; recreational over-prices BTTS-yes) ==")
    for r in sorted(rows, key=lambda r: r["btts"])[:8]:
        fav = r["m"].split(" v ")[0] if r["l1"] > r["l2"] else r["m"].split(" v ")[1]
        print(f"  {r['date']} {r['g']:2} {r['m']:30} xG {r['l1']:.2f}-{r['l2']:.2f}  "
              f"BTTS-NO {(1-r['btts'])*100:4.0f}%  (fav {fav})")

    print("\n== strongest BTTS-YES leans (two scorers; balanced, model best-calibrated 40-60%) ==")
    for r in sorted(rows, key=lambda r: -r["btts"])[:6]:
        print(f"  {r['date']} {r['g']:2} {r['m']:30} xG {r['l1']:.2f}-{r['l2']:.2f}  "
              f"BTTS-YES {r['btts']*100:4.0f}%  (tot {r['tot']:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
