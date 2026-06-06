"""World Football Elo ratings, computed from open results data.

Rather than scrape eloratings.net (an undocumented, fragile feed), we reproduce
its published algorithm over the MIT-licensed martj42/international_results match
history. This keeps the ratings fully reproducible and auditable, which matters
for the project.

Algorithm (https://www.eloratings.net/about):
    R_new = R_old + K * G * (W - We)
  where
    We = 1 / (10^(-dr/400) + 1),   dr = R_home - R_away + home_advantage
    W  = 1 win / 0.5 draw / 0 loss
    G  = goal-difference index (1 if |gd|<=1, 1.5 if 2, (11+|gd|)/8 if >=3)
    K  = match-importance weight (World Cup 60 ... friendly 20)

Ratings are processed strictly chronologically. The absolute init value washes out
over ~150 years of history, so all teams start at 1500.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

INIT_RATING = 1500.0
# Added to the home side's rating in We; 0 at neutral venues. Calibrated to our own
# history: a home side gains ~0.47 goals of expectation, and beta*HA/100 matches that
# at HA~85 (was 100, which overstated it ~15% and inflated the 2026 hosts).
HOME_ADVANTAGE = 85.0


def importance_weight(tournament: str) -> float:
    """Map the martj42 `tournament` label to an eloratings.net K weight."""
    t = (tournament or "").lower()
    if "friendly" in t:
        return 20.0
    if "qualification" in t or "qualifier" in t:
        return 40.0
    if "world cup" in t or "olympic" in t:
        return 60.0
    # continental finals (Euro, Copa America, AFCON, Gold Cup, Asian Cup) + Confed/Nations
    if any(k in t for k in ("uefa euro", "copa", "african cup", "afc asian", "gold cup",
                            "confederations", "nations league", "finals")):
        return 50.0
    return 30.0  # other competitive tournaments


def goal_index(goal_diff: int) -> float:
    n = abs(goal_diff)
    if n <= 1:
        return 1.0
    if n == 2:
        return 1.5
    return (11.0 + n) / 8.0


def expected_score(r_home: float, r_away: float, neutral: bool) -> float:
    dr = r_home - r_away + (0.0 if neutral else HOME_ADVANTAGE)
    return 1.0 / (10.0 ** (-dr / 400.0) + 1.0)


@dataclass
class EloResult:
    ratings: dict[str, float]          # team -> current rating
    last_played: dict[str, pd.Timestamp]  # team -> date of most recent match
    calib: pd.DataFrame                # per-match pre-game features for calibration


def build_ratings(matches: pd.DataFrame) -> EloResult:
    """Run Elo over a chronologically-sorted results frame.

    Expects columns: date, home_team, away_team, home_score, away_score,
    tournament, neutral. Returns final ratings plus a calibration frame with the
    pre-match rating difference and realized goals for every match, the input to
    the Elo -> goals mapping in baseline.py.
    """
    df = matches.sort_values("date").reset_index(drop=True)
    ratings: dict[str, float] = defaultdict(lambda: INIT_RATING)
    last_played: dict[str, pd.Timestamp] = {}

    rows = []
    for r in df.itertuples(index=False):
        home, away = r.home_team, r.away_team
        rh, ra = ratings[home], ratings[away]
        neutral = bool(getattr(r, "neutral", False))

        gd = int(r.home_score) - int(r.away_score)
        we = expected_score(rh, ra, neutral)
        w = 1.0 if gd > 0 else (0.5 if gd == 0 else 0.0)
        k = importance_weight(getattr(r, "tournament", ""))
        delta = k * goal_index(gd) * (w - we)

        # effective pre-match rating gap (includes home advantage) drives the
        # supremacy mapping later; record it before updating.
        dr_eff = rh - ra + (0.0 if neutral else HOME_ADVANTAGE)
        rows.append((r.date, home, away, dr_eff, gd,
                     int(r.home_score) + int(r.away_score), neutral))

        ratings[home] = rh + delta
        ratings[away] = ra - delta
        last_played[home] = r.date
        last_played[away] = r.date

    calib = pd.DataFrame(
        rows,
        columns=["date", "home_team", "away_team", "dr_eff",
                 "goal_diff", "total_goals", "neutral"],
    )
    return EloResult(ratings=dict(ratings), last_played=last_played, calib=calib)
