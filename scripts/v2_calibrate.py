#!/usr/bin/env python3
"""v2 model calibration: temperature scaling to fix the overconfidence the 2018/2022 backtest
exposed (confident calls 74%->60% in 2022; tail upsets priced ~0%). Fits ONE temperature on the
out-of-sample 2018 + 2022 World Cups, scored with the v2 ZISM W/D/L on point-in-time ratings,
by minimizing NLL. T>1 (cooler) pulls extreme probabilities toward the centre.

This is part of the v2 fork: v1 (xresidual/) stays byte-frozen. v2 = ZISM draws + this temperature
calibration. The fit uses raw point-in-time Elo (no historical squad values to backtest the blend,
the same limitation backtest_wc.py has), which calibrates the model's sharpness, not its ratings.

  python scripts/v2_calibrate.py     # print the fitted T
"""
from __future__ import annotations
import functools
import os
import sys

import numpy as np
from scipy.optimize import minimize_scalar

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import data, elo, baseline, residual  # noqa: E402

WINDOWS = {"2018": ("2018-06-01", "2018-07-31"), "2022": ("2022-11-01", "2022-12-31")}
_IDX = {"home": 0, "draw": 1, "away": 2}


def _scale3(P, T):
    L = np.log(np.clip(P, 1e-9, 1.0)) / T
    e = np.exp(L - L.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


@functools.lru_cache(maxsize=1)
def temperature() -> float:
    """Fit T on the point-in-time 2018+2022 World Cup outcomes using the v2 ZISM W/D/L. Cached:
    the build of ratings + the fit run once per process."""
    from build_matches_v2 import _wdl_zism, OMEGA          # lazy: avoid the import cycle
    df = data.load_results()
    res = elo.build_ratings(df)
    cal = res.calib.copy()
    cal["tournament"] = df.sort_values("date").reset_index(drop=True)["tournament"].values
    P, Y = [], []
    for _, (s, e) in WINDOWS.items():
        params = baseline.calibrate(cal[cal["date"] < s])
        wc = cal[(cal["tournament"] == "FIFA World Cup") & (cal["date"] >= s) & (cal["date"] <= e)]
        for r in wc.itertuples(index=False):
            exp = baseline.make_expectation(r.home_team, r.away_team,
                                            {r.home_team: r.dr_eff, r.away_team: 0.0}, params, neutral=True)
            p1, pd_, p2 = _wdl_zism(exp.lambda_home, exp.lambda_away, OMEGA)
            P.append([p1, pd_, p2])
            Y.append(_IDX[residual.outcome_from_goal_diff(int(r.goal_diff))])
    P, Y = np.array(P), np.array(Y)
    nll = lambda T: float(-np.mean(np.log(np.clip(_scale3(P, T)[np.arange(len(Y)), Y], 1e-9, 1.0))))
    return float(minimize_scalar(nll, bounds=(0.5, 5.0), method="bounded").x)


def scale_wdl(p1, pd_, p2, T=None):
    """Temperature-scale a W/D/L triple (renormalized). Used by build_matches_v2."""
    T = temperature() if T is None else T
    s = _scale3(np.array([[p1, pd_, p2]], dtype=float), T)[0]
    return float(s[0]), float(s[1]), float(s[2])


def scale_binary(p, T=None):
    """Temperature-scale a single probability (advance, group-win, champion). T>1 -> toward 0.5."""
    T = temperature() if T is None else T
    a, b = p ** (1.0 / T), (1.0 - p) ** (1.0 / T)
    return a / (a + b)


if __name__ == "__main__":
    print(f"v2 fitted temperature T = {temperature():.3f}  (T>1 = the base model was overconfident)")
