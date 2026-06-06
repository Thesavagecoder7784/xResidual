"""Unit tests for the Layer 3 calibration toolkit (no network).

Uses synthetic data with known calibration properties.
Run:  python tests/test_calibration.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xresidual import calibration as cal  # noqa: E402


def _perfectly_calibrated(n=200_000, seed=0):
    """Forecasts p drawn uniformly; outcomes drawn with true prob p. By
    construction these are perfectly calibrated."""
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.01, 0.99, n)
    y = (rng.uniform(size=n) < p).astype(float)
    return p, y


def test_flatten_wdl_shapes_and_indicators():
    p, y = cal.flatten_wdl([0.6], [0.3], [0.1], ["home"])
    assert len(p) == 3 and len(y) == 3
    assert list(y) == [1.0, 0.0, 0.0]          # home occurred
    assert abs(p[0] - 0.6) < 1e-12


def test_wilson_interval_brackets_phat():
    lo, hi = cal.wilson_interval(5, 20)
    assert lo < 0.25 < hi and 0.0 <= lo and hi <= 1.0


def test_murphy_identity_holds():
    # REL - RES + UNC must equal the binned Brier, exactly, on any data.
    p, y = _perfectly_calibrated(50_000, seed=1)
    md = cal.murphy_decomposition(p, y, n_bins=10)
    lhs = md.reliability - md.resolution + md.uncertainty
    assert abs(lhs - md.brier_binned) < 1e-9


def test_perfect_calibration_is_reliable():
    p, y = _perfectly_calibrated()
    md = cal.murphy_decomposition(p, y, n_bins=10)
    assert md.reliability < 1e-3                 # near-zero calibration penalty
    a, b = cal.calibration_regression(p, y)
    assert abs(a) < 0.05 and abs(b - 1.0) < 0.05  # (a,b) ~ (0,1)
    assert cal.expected_calibration_error(p, y) < 0.01


def test_overconfident_forecasts_have_slope_below_one():
    # push probabilities toward the extremes -> overconfident -> b < 1
    p, y = _perfectly_calibrated(200_000, seed=2)
    p_over = np.clip(p + 0.6 * (p - 0.5), 0.01, 0.99)  # stretch around 0.5
    _, b = cal.calibration_regression(p_over, y)
    assert b < 0.95


def test_brier_bounds():
    p, y = _perfectly_calibrated(10_000, seed=3)
    assert 0.0 <= cal.brier_score(p, y) <= 0.25 + 1e-6  # uniform-p base rate ~0.5


def test_corp_decomposition_identity_is_exact():
    # CORP's MCB - DSC + UNC == raw Brier EXACTLY (no binning approximation)
    p, y = _perfectly_calibrated(20_000, seed=4)
    r = cal.corp(p, y, n_boot=50)
    assert abs((r.mcb - r.dsc + r.unc) - r.brier) < 1e-9


def test_corp_perfect_calibration_low_mcb():
    p, y = _perfectly_calibrated(100_000, seed=5)
    r = cal.corp(p, y, n_boot=50)
    assert r.mcb < 1e-2          # well-calibrated -> tiny miscalibration
    assert r.dsc > 0.0           # forecasts still discriminate


def test_devig_methods_agree_roughly_and_normalize():
    from xresidual import devig
    out = devig.devig_sensitivity([1.5, 4.0, 7.0])
    for m, probs in out["probs"].items():
        assert abs(probs.sum() - 1.0) < 1e-6      # each method returns a distribution
    assert out["max_spread"].max() < 0.05          # methods agree to within a few pts here


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
