"""Skellam match-outcome distribution (METHODOLOGY.md §2).

Goals are modelled as independent Poissons; the goal differential
d = goals_home - goals_away therefore follows a Skellam distribution. This single
generative object yields both the goal-difference distribution and, by summing its
PMF over the sign of d, the W/D/L probabilities — keeping the two views mutually
consistent.

Note the property the rest of the project leans on: Var[d] = lambda_home +
lambda_away = expected total goals. That is exactly the denominator used for the
per-match goal-difference z-score in METHODOLOGY.md §3.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import skellam


@dataclass(frozen=True)
class MatchExpectation:
    """The pre-match expectation for one fixture."""

    home: str
    away: str
    lambda_home: float          # expected goals, home
    lambda_away: float          # expected goals, away
    p_home: float               # P(home win)
    p_draw: float               # P(draw)
    p_away: float               # P(away win)
    exp_goal_diff: float        # E[d] = lambda_home - lambda_away
    sd_goal_diff: float         # sd[d] = sqrt(lambda_home + lambda_away)

    @property
    def wdl(self) -> tuple[float, float, float]:
        return (self.p_home, self.p_draw, self.p_away)


def wdl_probs(lambda_home: float, lambda_away: float) -> tuple[float, float, float]:
    """(P(home win), P(draw), P(away win)) from the Skellam over d = home - away."""
    p_draw = float(skellam.pmf(0, lambda_home, lambda_away))
    p_home = float(skellam.sf(0, lambda_home, lambda_away))    # P(d >= 1)
    p_away = float(skellam.cdf(-1, lambda_home, lambda_away))  # P(d <= -1)
    return p_home, p_draw, p_away


def goal_diff_pmf(lambda_home: float, lambda_away: float, d: int) -> float:
    """P(goal differential == d)."""
    return float(skellam.pmf(d, lambda_home, lambda_away))


def expectation(home: str, away: str,
                lambda_home: float, lambda_away: float) -> MatchExpectation:
    p_home, p_draw, p_away = wdl_probs(lambda_home, lambda_away)
    return MatchExpectation(
        home=home, away=away,
        lambda_home=lambda_home, lambda_away=lambda_away,
        p_home=p_home, p_draw=p_draw, p_away=p_away,
        exp_goal_diff=lambda_home - lambda_away,
        sd_goal_diff=float(np.sqrt(lambda_home + lambda_away)),
    )
