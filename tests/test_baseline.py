"""Unit tests for the Layer 1 math core (no network needed).

Run:  python -m pytest tests/  ||  python tests/test_baseline.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xresidual import baseline, elo, residual, skellam  # noqa: E402


def test_wdl_sums_to_one():
    for lh, la in [(1.5, 1.1), (2.0, 0.3), (0.4, 0.4), (3.0, 2.5)]:
        ph, pd_, pa = skellam.wdl_probs(lh, la)
        assert abs(ph + pd_ + pa - 1.0) < 1e-9


def test_symmetry_when_equal_rates():
    ph, pd_, pa = skellam.wdl_probs(1.3, 1.3)
    assert abs(ph - pa) < 1e-12     # equal rates -> equal win probs
    assert pd_ > 0                   # draws have positive mass


def test_stronger_side_more_likely_to_win():
    ph_strong, _, _ = skellam.wdl_probs(2.2, 0.8)
    ph_even, _, _ = skellam.wdl_probs(1.5, 1.5)
    assert ph_strong > ph_even


def test_expectation_variance_identity():
    # Var[goal diff] == lambda_home + lambda_away  (METHODOLOGY §2)
    exp = skellam.expectation("A", "B", 1.7, 1.1)
    assert abs(exp.sd_goal_diff - math.sqrt(1.7 + 1.1)) < 1e-12
    assert abs(exp.exp_goal_diff - 0.6) < 1e-12


def test_elo_expected_score_bounds_and_symmetry():
    assert abs(elo.expected_score(1500, 1500, neutral=True) - 0.5) < 1e-12
    assert elo.expected_score(1800, 1500, neutral=True) > 0.5
    # home advantage raises the home expectation vs a neutral venue
    assert elo.expected_score(1500, 1500, neutral=False) > 0.5


def test_goal_index_steps():
    assert elo.goal_index(0) == 1.0
    assert elo.goal_index(1) == 1.0
    assert elo.goal_index(2) == 1.5
    assert elo.goal_index(3) == (11 + 3) / 8


def test_log_score_matches_probability():
    exp = skellam.expectation("A", "B", 1.5, 1.2)
    assert abs(residual.log_score(exp, residual.OUTCOME_HOME) + math.log(exp.p_home)) < 1e-12


def test_lambda_floor_keeps_rates_positive():
    p = baseline.BaselineParams(beta=1.0, total_goals=2.6, n_matches=1)
    # an extreme mismatch must not drive a rate negative
    lh, la = baseline.lambdas(2400, 1000, p, neutral=True)
    assert la >= baseline.LAMBDA_FLOOR and lh > 0


def _run_all():
    fns = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
