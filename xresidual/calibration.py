"""Market calibration toolkit, Layer 3 (METHODOLOGY.md §4).

Source-agnostic: everything here operates on pooled (predicted_probability,
outcome_indicator) pairs, so the same code grades 538's historical forecasts (the
pre-tournament dry-run) and the live 2026 market-implied probabilities.

A W/D/L forecast is flattened to binary events: each match contributes three
(p, y) points (its home/draw/away probability paired with whether that outcome
occurred). Reliability, the Murphy/Brier decomposition, and the calibration
regression are all computed on that pooled binary set, the standard treatment of a
multi-class probabilistic forecaster.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.isotonic import IsotonicRegression

EPS = 1e-12


def flatten_wdl(p_home, p_draw, p_away, outcome) -> tuple[np.ndarray, np.ndarray]:
    """Flatten W/D/L forecasts + realized outcomes to pooled binary (p, y).

    `outcome` is an iterable of "home"/"draw"/"away". Returns arrays of length
    3*N: each match yields (p_home, 1{home}), (p_draw, 1{draw}), (p_away, 1{away}).
    """
    p_home = np.asarray(p_home, float)
    p_draw = np.asarray(p_draw, float)
    p_away = np.asarray(p_away, float)
    outcome = np.asarray(outcome)
    p = np.concatenate([p_home, p_draw, p_away])
    y = np.concatenate([
        (outcome == "home").astype(float),
        (outcome == "draw").astype(float),
        (outcome == "away").astype(float),
    ])
    return p, y


# --------------------------------------------------------------------------- #
# Reliability
# --------------------------------------------------------------------------- #
def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for an observed proportion k/n."""
    if n == 0:
        return (float("nan"), float("nan"))
    phat = k / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = (z * np.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return center - half, center + half


def reliability_table(p, y, n_bins: int = 10) -> pd.DataFrame:
    """Binned reliability: mean prediction vs observed frequency, with counts and
    Wilson CIs. Bin counts are returned so sparse (extreme-probability) bins, where
    claims are weakest, stay visible rather than hidden."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, n_bins - 1)
    rows = []
    for b in range(n_bins):
        m = idx == b
        n = int(m.sum())
        k = int(y[m].sum())
        lo, hi = wilson_interval(k, n)
        rows.append({
            "bin": f"[{edges[b]:.1f},{edges[b + 1]:.1f})",
            "n": n,
            "mean_pred": float(p[m].mean()) if n else float("nan"),
            "obs_freq": (k / n) if n else float("nan"),
            "ci_lo": lo, "ci_hi": hi,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Brier score + Murphy decomposition
# --------------------------------------------------------------------------- #
def brier_score(p, y) -> float:
    """Mean squared error of the probabilistic forecast (binary events)."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    return float(np.mean((p - y) ** 2))


@dataclass
class MurphyDecomposition:
    reliability: float    # lower better; calibration penalty
    resolution: float     # higher better; discrimination
    uncertainty: float    # base-rate variance (irreducible)
    brier_binned: float   # reliability - resolution + uncertainty
    n_bins: int

    def as_dict(self) -> dict:
        return {"reliability": self.reliability, "resolution": self.resolution,
                "uncertainty": self.uncertainty, "brier_binned": self.brier_binned}


def murphy_decomposition(p, y, n_bins: int = 10) -> MurphyDecomposition:
    """Calibration-refinement (Murphy) decomposition of the Brier score:

        Brier_binned = Reliability - Resolution + Uncertainty

    computed by binning forecasts and replacing each with its bin mean. The raw
    Brier exceeds Brier_binned only by within-bin forecast variance.
    """
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    n = len(y)
    obar = float(y.mean())
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, n_bins - 1)

    rel = res = 0.0
    brier_binned = 0.0
    for b in range(n_bins):
        m = idx == b
        nk = int(m.sum())
        if nk == 0:
            continue
        pbar_k = float(p[m].mean())
        obar_k = float(y[m].mean())
        rel += nk * (pbar_k - obar_k) ** 2
        res += nk * (obar_k - obar) ** 2
        brier_binned += np.sum((pbar_k - y[m]) ** 2)
    rel /= n
    res /= n
    unc = obar * (1 - obar)
    return MurphyDecomposition(rel, res, unc, brier_binned / n, n_bins)


# --------------------------------------------------------------------------- #
# Calibration regression + ECE
# --------------------------------------------------------------------------- #
def calibration_regression(p, y) -> tuple[float, float]:
    """Logistic fit  logit(P(y=1)) = a + b * logit(p).

    Perfect calibration => (a, b) = (0, 1). b < 1 indicates overconfidence (the
    favorite-longshot bias signature); a != 0 indicates a directional tilt.
    Fit by maximum likelihood (no external ML dependency).
    """
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    y = np.asarray(y, float)
    z = np.log(p / (1 - p))
    X = np.column_stack([np.ones_like(z), z])

    def nll(beta):
        eta = X @ beta
        return float(np.sum(np.logaddexp(0.0, eta) - y * eta))

    res = minimize(nll, x0=np.array([0.0, 1.0]), method="BFGS")
    a, b = res.x
    return float(a), float(b)


def expected_calibration_error(p, y, n_bins: int = 10) -> float:
    """ECE: count-weighted mean |mean_pred - obs_freq| across bins."""
    tab = reliability_table(p, y, n_bins)
    tab = tab[tab["n"] > 0]
    w = tab["n"] / tab["n"].sum()
    return float((w * (tab["mean_pred"] - tab["obs_freq"]).abs()).sum())


# --------------------------------------------------------------------------- #
# CORP reliability (isotonic / PAV): the primary, binning-free method.
# Dimitriadis, Gneiting & Jordan (2021), PNAS 118(8). Consistent, Optimally
# binned, Reproducible: recalibrate forecasts by isotonic regression (PAV), which
# removes the ad-hoc binning of the count-based diagram and yields an EXACT score
# decomposition plus consistency bands computed under the null of calibration.
# --------------------------------------------------------------------------- #
@dataclass
class CorpResult:
    grid: np.ndarray      # forecast-probability axis for plotting
    recal: np.ndarray     # PAV-recalibrated frequency at each grid point (the curve)
    band_lo: np.ndarray   # consistency-band lower (null-of-calibration; brackets 45-deg)
    band_hi: np.ndarray   # consistency-band upper
    mcb: float            # MisCaliBration (lower better); the calibration penalty
    dsc: float            # DiSCrimination (higher better)
    unc: float            # UNCertainty (base-rate difficulty)
    brier: float          # = MCB - DSC + UNC, EXACTLY (no binning approximation)

    def as_dict(self) -> dict:
        return {"MCB": self.mcb, "DSC": self.dsc, "UNC": self.unc, "brier": self.brier}


def _pav_fit(p, y) -> IsotonicRegression:
    return IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(p, y)


def corp(p, y, n_boot: int = 500, grid_size: int = 101, seed: int = 0,
         wdl_n: int | None = None) -> CorpResult:
    """CORP reliability diagram + exact Brier (MCB/DSC/UNC) decomposition, with
    consistency bands computed under the null hypothesis of calibration.

    Point estimates are exact: the identity Brier = MCB - DSC + UNC holds for the
    raw score because miscalibration is measured against the PAV-recalibrated
    forecast rather than coarse bins.

    Consistency bands (Dimitriadis, Gneiting & Jordan 2021, §"consistency bands"):
    the band is the sampling distribution of the PAV recalibration curve *when the
    forecasts are calibrated*. We hold the forecasts `p` fixed, resample outcomes
    FROM them under H0 (true event probability == forecast probability), refit PAV,
    and take pointwise 2.5/97.5 percentiles. Under H0 the recal curve estimates the
    identity line, so the band brackets the 45-degree line; the calibration claim is
    "significant" where the estimated (CORP) curve leaves the band. This is the DGJ
    consistency band, NOT a pair-bootstrap confidence band for the fitted curve (the
    latter is miscentered for this test and ignores outcome dependence).

    `wdl_n`: when (p, y) came from `flatten_wdl` (layout [home(N), draw(N), away(N)]),
    pass the number of matches N. The null then draws ONE coherent categorical
    outcome per match (exactly one of home/draw/away occurs) rather than three
    independent Bernoullis, so the resampling unit is the match. This respects the
    mutual exclusivity and dependence among a match's three events; without it the
    band would treat 3N dependent events as independent and come out too narrow
    (~sqrt(3)). Omit it for a single binary forecaster (independent Bernoulli null).
    """
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    n = len(y)

    iso = _pav_fit(p, y)
    recal_at_p = iso.predict(p)
    obar = float(y.mean())

    brier = float(np.mean((p - y) ** 2))
    recal_score = float(np.mean((recal_at_p - y) ** 2))
    unc = obar * (1 - obar)
    mcb = brier - recal_score      # original score minus recalibrated score
    dsc = unc - recal_score        # base-rate score minus recalibrated score

    grid = np.linspace(0.0, 1.0, grid_size)
    recal_grid = iso.predict(grid)

    # consistency bands under H0 of calibration: forecasts fixed, outcomes resampled
    # from them, PAV refit. The match is the resampling unit when wdl_n is given.
    rng = np.random.default_rng(seed)
    curves = np.empty((n_boot, grid_size))
    if wdl_n is not None:
        N = int(wdl_n)
        # per-match (home, draw, away) probabilities from the flatten_wdl layout
        P = np.column_stack([p[:N], p[N:2 * N], p[2 * N:3 * N]])
        P = P / P.sum(axis=1, keepdims=True)
        cum = np.cumsum(P, axis=1)
        for b in range(n_boot):
            cat = (rng.random((N, 1)) < cum).argmax(axis=1)   # 0=home,1=draw,2=away
            ystar = np.concatenate([cat == 0, cat == 1, cat == 2]).astype(float)
            curves[b] = _pav_fit(p, ystar).predict(grid)
    else:
        for b in range(n_boot):
            ystar = (rng.random(n) < p).astype(float)
            curves[b] = _pav_fit(p, ystar).predict(grid)
    band_lo = np.percentile(curves, 2.5, axis=0)
    band_hi = np.percentile(curves, 97.5, axis=0)

    return CorpResult(grid, recal_grid, band_lo, band_hi, mcb, dsc, unc, brier)
