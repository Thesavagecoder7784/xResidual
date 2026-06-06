"""The match-expectation baseline (METHODOLOGY.md §1-2, Layer 1).

Maps an Elo rating difference to a Skellam goal distribution in two calibrated
steps:

  1. Expected goal supremacy:  sup = beta * (dr_eff / 100)
     where dr_eff is the effective pre-match rating gap (home rating - away
     rating, plus home advantage at non-neutral venues). beta is fit by
     least-squares-through-origin on historical (dr_eff, goal_diff) pairs.

  2. Expected total goals:  tot = mean historical total goals.

Then the Poisson rates are recovered from their mean and difference:
     lambda_home = (tot + sup) / 2,   lambda_away = (tot - sup) / 2
(clipped to a small positive floor), and handed to the Skellam model.

Note the internal consistency: E[goal_diff] = sup and Var[goal_diff] = tot, so the
z-score denominator in residual.py is sqrt(tot) by construction.

Since national-team xG is no longer freely available (FBref dropped Opta xG in
Jan 2026), this baseline is Elo-driven. An xG adjustment can later be folded into
`sup`/`tot` via a paid feed without changing the interface.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import elo, venues_wc2026
from .skellam import MatchExpectation, expectation

LAMBDA_FLOOR = 0.05  # keep rates positive for weak-vs-strong blowout priors


@dataclass
class BaselineParams:
    beta: float          # goals of supremacy per 100 Elo points of effective gap
    total_goals: float   # expected total goals per match
    n_matches: int       # how many matches the fit used


def calibrate(calib: pd.DataFrame, min_date: str | None = "1990-01-01") -> BaselineParams:
    """Fit the Elo->goals mapping on historical matches.

    `calib` is the frame returned by elo.build_ratings (dr_eff, goal_diff,
    total_goals). We restrict to the modern era by default, since scoring rates and
    competitiveness shifted over a century-plus of history.
    """
    df = calib
    if min_date is not None:
        df = df[df["date"] >= pd.Timestamp(min_date)]
    x = (df["dr_eff"] / 100.0).to_numpy()
    y = df["goal_diff"].to_numpy()
    # least squares through the origin: dr_eff already encodes home advantage,
    # so a fair match (dr_eff = 0) should predict zero supremacy.
    beta = float(np.dot(x, y) / np.dot(x, x))
    return BaselineParams(
        beta=beta,
        total_goals=float(df["total_goals"].mean()),
        n_matches=int(len(df)),
    )


def lambdas(rating_home: float, rating_away: float, params: BaselineParams,
            neutral: bool = True, total_goals_factor: float = 1.0) -> tuple[float, float]:
    """Poisson rates (lambda_home, lambda_away) for a fixture.

    `neutral=False` applies the Elo home-advantage term (use for host fixtures).
    `total_goals_factor` scales expected total goals (e.g. an altitude prior, §9).
    """
    dr_eff = rating_home - rating_away + (0.0 if neutral else elo.HOME_ADVANTAGE)
    sup = params.beta * (dr_eff / 100.0)
    tot = params.total_goals * total_goals_factor
    lh = max((tot + sup) / 2.0, LAMBDA_FLOOR)
    la = max((tot - sup) / 2.0, LAMBDA_FLOOR)
    return lh, la


def make_expectation(home: str, away: str, ratings: dict[str, float],
                     params: BaselineParams, neutral: bool = True,
                     venue: str | None = None) -> MatchExpectation:
    """Full pre-match expectation for `home` vs `away` given current Elo ratings.

    For 2026 fixtures, pass `venue` (a host city) to apply the altitude total-goals
    factor automatically, and set `neutral=False` when `home` is a host playing at
    home. See METHODOLOGY.md §9.
    """
    rh = ratings.get(home, elo.INIT_RATING)
    ra = ratings.get(away, elo.INIT_RATING)
    tgf = venues_wc2026.total_goals_factor(venues_wc2026.altitude_of(venue))
    lh, la = lambdas(rh, ra, params, neutral=neutral, total_goals_factor=tgf)
    return expectation(home, away, lh, la)
