"""Per-match residuals (METHODOLOGY.md §3).

Two proper, per-match quantities — NOT Brier, which is an aggregate score
(see calibration, Layer 3) and is uninformative on a single match:

  - log score (surprisal): -log p(realized outcome). Higher = more surprising.
  - goal-difference z: standardized deviation against the Skellam expectation.

The sigma-discipline table in METHODOLOGY.md §3 applies: real soccer surprises
live in the 1-3 sigma band; |z| > 4 almost always means a misspecified variance
model, not a miracle.
"""

from __future__ import annotations

import math

from .skellam import MatchExpectation

OUTCOME_HOME = "home"
OUTCOME_DRAW = "draw"
OUTCOME_AWAY = "away"


def log_score(exp: MatchExpectation, outcome: str) -> float:
    """Surprisal of the realized W/D/L outcome, in nats."""
    p = {OUTCOME_HOME: exp.p_home, OUTCOME_DRAW: exp.p_draw, OUTCOME_AWAY: exp.p_away}.get(outcome)
    if p is None:
        raise ValueError(f"outcome must be one of home/draw/away, got {outcome!r}")
    return -math.log(max(p, 1e-12))  # guard against log(0) on near-impossible results


def goal_diff_z(exp: MatchExpectation, actual_goal_diff: int) -> float:
    """Standardized goal-difference residual: (actual - E[d]) / sd[d]."""
    return (actual_goal_diff - exp.exp_goal_diff) / exp.sd_goal_diff


def outcome_from_goal_diff(goal_diff: int) -> str:
    if goal_diff > 0:
        return OUTCOME_HOME
    if goal_diff < 0:
        return OUTCOME_AWAY
    return OUTCOME_DRAW
