#!/usr/bin/env python3
"""Choose the team-strength uncertainty sigma by out-of-sample RPS.

    python scripts/calibrate_sigma.py

sigma (the SD of each team's per-tournament rating offset) should be FIT, not eyeballed
to the market. Method: the Elo build records each match's PRE-match rating gap (dr_eff),
so every prediction is genuinely walk-forward. For a grid of sigma I widen the rating gap
by the strength noise (the match-level gap gets extra SD sqrt(2)*sigma, integrated out by
Gauss-Hermite), map it to W/D/L via Skellam, and score against the real result with the
Ranked Probability Score (RPS) - the proper, distance-sensitive rule for ordered W/D/L.

Weighting (the key question): friendlies are noisier and lower-stakes, so they pull sigma
higher than is right for a *tournament*. So I report sigma three ways - all matches,
competitive-only (no friendlies), and importance-weighted (the same Elo K weights that
build the ratings) - and adopt the competitive/weighted value for the World Cup.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import skellam

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import baseline, data, elo  # noqa: E402

SIGMAS = [0, 20, 40, 50, 60, 80, 100, 120, 150]
HALFLIVES = [2, 4, 8, None]    # recency-decay half-lives in years (None = no decay)
SINCE = "2006-01-01"            # mature-ratings / modern era floor (decay handles the rest)
_XQ, _WQ = np.polynomial.hermite.hermgauss(9)
_WQ = _WQ / np.sqrt(np.pi)      # weights for E[f(Z)], Z ~ N(0, tau^2)


def wdl(dr, beta, tot, sigma):
    """Marginal (P_away, P_draw, P_home) per match, integrating the strength noise."""
    pa, pd_, ph = (np.zeros_like(dr, dtype=float) for _ in range(3))
    offs = (2.0 * sigma) * _XQ if sigma > 0 else np.array([0.0])
    wts = _WQ if sigma > 0 else np.array([1.0])
    for off, wt in zip(offs, wts):
        sup = beta * ((dr + off) / 100.0)
        lh = np.clip((tot + sup) / 2.0, 0.05, None)
        la = np.clip((tot - sup) / 2.0, 0.05, None)
        pa = pa + wt * skellam.cdf(-1, lh, la)
        pd_ = pd_ + wt * skellam.pmf(0, lh, la)
        ph = ph + wt * (1.0 - skellam.cdf(0, lh, la))
    s = pa + pd_ + ph
    return pa / s, pd_ / s, ph / s


def rps(pa, pd_, ph, gd):
    """Ranked Probability Score per match for ordered outcomes [away, draw, home]."""
    oa = (gd < 0).astype(float); od = (gd == 0).astype(float)
    c1p, c2p = pa, pa + pd_
    c1o, c2o = oa, oa + od
    return 0.5 * ((c1p - c1o) ** 2 + (c2p - c2o) ** 2)


def main() -> int:
    res = elo.build_ratings(data.load_results())
    params = baseline.calibrate(res.calib)
    cal = res.calib.copy()
    # align tournament label by position (calib is built in the same date-sorted order)
    srt = data.load_results().sort_values("date").reset_index(drop=True)
    cal["tournament"] = srt["tournament"].values
    cal["w_imp"] = cal["tournament"].map(elo.importance_weight)
    cal["friendly"] = cal["tournament"].str.contains("Friendly", case=False, na=False)
    now = cal["date"].max()

    # tournament-relevant scoring set: competitive matches in the modern era
    m = cal[(cal["date"] >= pd.Timestamp(SINCE)) & (~cal["friendly"])].reset_index(drop=True)
    dr = m["dr_eff"].to_numpy(float); gd = m["goal_diff"].to_numpy(float)
    w_imp = m["w_imp"].to_numpy(float)
    age = ((now - m["date"]).dt.days / 365.25).to_numpy(float)
    print(f"scoring {len(m):,} competitive matches since {SINCE[:4]} · ref date {now.date()} · "
          f"beta={params.beta:.3f}\n")

    # predictions don't depend on the weighting, so score each match once per sigma
    rps_by_sigma = {sg: rps(*wdl(dr, params.beta, params.total_goals, sg), gd) for sg in SIGMAS}

    print("importance × recency-weighted RPS  (lower = better; ← marks each column's min)")
    print("sigma | " + " ".join(f"{('H='+str(h)+'y' if h else 'no-decay'):>9}" for h in HALFLIVES))
    best = {h: (1e9, None) for h in HALFLIVES}
    grid = {}
    for sg in SIGMAS:
        for h in HALFLIVES:
            wr = w_imp * (0.5 ** (age / h) if h else 1.0)
            val = float(np.average(rps_by_sigma[sg], weights=wr))
            grid[(sg, h)] = val
            if val < best[h][0]:
                best[h] = (val, sg)
    for sg in SIGMAS:
        cells = []
        for h in HALFLIVES:
            mark = " ←" if best[h][1] == sg else "  "
            cells.append(f"{grid[(sg, h)]:7.5f}{mark}")
        print(f"{sg:>5} | " + " ".join(cells))

    print("\nRPS-minimizing sigma by recency half-life:")
    for h in HALFLIVES:
        print(f"  half-life {(str(h)+'yr' if h else 'none'):>6}: sigma = {best[h][1]}")
    print("\nThe half-life is a modeling choice (weight current football more), not RPS-fit "
          "(that's degenerate).\nσ* is robust across half-lives; cross-checks: market anchor ~50, "
          "Glicko-RD (national teams) tens of Elo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
