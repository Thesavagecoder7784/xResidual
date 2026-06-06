"""xResidual: calibration study of 2026 World Cup prediction markets.

Layer 1 (this package, so far): a reproducible match-expectation baseline.
World Football Elo computed from open results data, mapped to a Skellam goal
distribution. See METHODOLOGY.md.
"""

from .skellam import MatchExpectation, expectation, wdl_probs
from .residual import goal_diff_z, log_score, OUTCOME_HOME, OUTCOME_DRAW, OUTCOME_AWAY
from . import (calibration, devig, asian_handicap, trajectory, venues_wc2026,
               wc2026_teams, data_fixtures, pipeline, microstructure, ws_events)

__all__ = [
    "MatchExpectation",
    "expectation",
    "wdl_probs",
    "goal_diff_z",
    "log_score",
    "OUTCOME_HOME",
    "OUTCOME_DRAW",
    "OUTCOME_AWAY",
    "calibration",
    "devig",
    "asian_handicap",
    "trajectory",
    "venues_wc2026",
    "wc2026_teams",
    "data_fixtures",
    "pipeline",
    "microstructure",
    "ws_events",
]
