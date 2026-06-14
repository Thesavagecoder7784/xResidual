#!/usr/bin/env python3
"""Temperature-scale the model to fix the tail-overconfidence the 2018/2022 backtest exposed,
then re-derive the favourite-longshot advance edges at honest sizing.

The raw model-vs-market gap (e.g. Iraq advance 4% vs market 14%) OVERSTATED the edge, because
the out-of-sample backtest showed the model is overconfident at the extremes (confident calls
74%->60% in 2022; tail upsets priced ~0%). The standard fix is temperature scaling: fit one T
(>1 = cooler / less confident) on the out-of-sample 2018+2022 match outcomes by minimizing NLL,
apply it to the current advance probabilities, and the T-scaled gap is the genuine FLB signal
(literature: ~2-5%/contract at the price extremes). Fork-forward: reads the frozen model, never
edits xresidual/.

  python scripts/flb_recalibrate.py
"""
from __future__ import annotations
import os
import sys

import numpy as np
from scipy.optimize import minimize_scalar

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import data, elo, baseline, residual  # noqa: E402
import prediction_board as pb  # noqa: E402

WINDOWS = {"2018": ("2018-06-01", "2018-07-31"), "2022": ("2022-11-01", "2022-12-31")}
_IDX = {"home": 0, "draw": 1, "away": 2}


def _scale3(P, T):
    """Temperature-scale rows of 3-outcome probabilities (softmax of logits / T)."""
    L = np.log(np.clip(P, 1e-9, 1.0)) / T
    e = np.exp(L - L.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def fit_temperature():
    """Fit one T on the POINT-IN-TIME 2018+2022 World Cup match outcomes by minimizing NLL.
    Each tournament's goal-model params are calibrated strictly on matches before it (no leak)."""
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
            P.append([exp.p_home, exp.p_draw, exp.p_away])
            Y.append(_IDX[residual.outcome_from_goal_diff(int(r.goal_diff))])
    P, Y = np.array(P), np.array(Y)

    def nll(T):
        S = _scale3(P, T)
        return float(-np.mean(np.log(np.clip(S[np.arange(len(Y)), Y], 1e-9, 1.0))))

    r = minimize_scalar(nll, bounds=(0.5, 5.0), method="bounded")
    return float(r.x), len(Y), nll(1.0), nll(r.x)


def temp_binary(p, T):
    """Temperature-scale a single probability (binary): T>1 pulls it toward 0.5."""
    a, b = p ** (1.0 / T), (1.0 - p) ** (1.0 / T)
    return a / (a + b)


def main():
    T, n, nll1, nllT = fit_temperature()
    verdict = "model was OVERCONFIDENT" if T > 1.03 else ("well-calibrated" if T < 1.03 else "")
    print(f"fitted T = {T:.2f} on {n} out-of-sample 2018/2022 matches "
          f"(NLL {nll1:.3f} -> {nllT:.3f}); T>1 => {verdict}\n")

    sim, _ = pb.model_probs()
    adv = pb.market_prices().get("advance", {})
    teams = ["Ivory Coast", "Senegal", "Egypt", "Algeria",         # favourites we back
             "New Zealand", "Iraq", "Jordan", "Panama", "Saudi Arabia", "Tunisia"]  # longshots we fade
    print(f"  {'team':<15}{'mkt':>6}{'raw':>7}{'recal':>8}{'raw gap':>9}{'recal gap':>11}")
    for t in teams:
        s, m = sim.get(t), adv.get(t)
        if not s or m is None:
            continue
        raw = s["padv"]
        rc = temp_binary(raw, T)
        print(f"  {t:<15}{m * 100:6.0f}{raw * 100:7.0f}{rc * 100:8.0f}"
              f"{(raw - m) * 100:+9.1f}{(rc - m) * 100:+11.1f}")
    print("\n  recal gap = the honest FLB edge after fixing tail-overconfidence; "
          "size the basket on this, not the raw gap.")


if __name__ == "__main__":
    main()
