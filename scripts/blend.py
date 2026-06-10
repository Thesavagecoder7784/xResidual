"""Blend Elo (results) with Transfermarkt squad value (quality) into one rating.

Elo is results-only and blind to squad quality, which made the sim overconfident on
favourites. Peeters (2018, Int. J. Forecasting) found squad value out-predicts Elo
and FIFA ranking for international football, so value gets the majority weight here.

blended = z(Elo)*w + z(log10 value)*(1-w), rescaled to Elo's mean/spread so it drops
straight into the existing goal model. w = Elo weight in [0,1]; w=1 recovers pure Elo.
Default w=0.4 (value-weighted). Covers the 48 WC teams (the only ones with values).
"""

from __future__ import annotations

import numpy as np

from xresidual import elo, wc2026_teams
from squad_values import SQUAD_VALUE, adjusted_squad_values

DEFAULT_W = 0.4


def blended_ratings(elo_ratings: dict, w: float = DEFAULT_W, teams=None,
                    availability: bool = False, confed_correct: bool = True) -> dict:
    """Blend Elo with squad value. `availability=True` uses availability-adjusted squad
    values (SQUAD_VALUE minus injured/absent top-11 players, see squad_values.ABSENCES)
    instead of the static full-strength value. Default False keeps the published model on
    the static value until the ABSENCES table carries real, sourced squad-announcement
    data — an empty table makes the two identical, so turning it on is harmless.

    `confed_correct=True` (default) first applies the empirical-Bayes confederation offset
    (xresidual.confed_bias) to de-bias the near-disconnected confederation clusters before
    blending — a validated +4.6% out-of-sample gain on cross-confederation matches. Pass
    False for rating-isolation diagnostics that deliberately study raw Elo / the draw alone."""
    from xresidual import confed_bias
    teams = sorted(teams or wc2026_teams.WC2026_TEAMS)
    values = adjusted_squad_values() if availability else SQUAD_VALUE
    if confed_correct:
        elo_ratings = confed_bias.apply_offsets(elo_ratings)
    et = np.array([elo_ratings.get(wc2026_teams.elo_name(t), elo.INIT_RATING) for t in teams])
    vt = np.log10(np.array([values[t] for t in teams], dtype=float))
    ez = (et - et.mean()) / et.std()
    vz = (vt - vt.mean()) / vt.std()
    br = et.mean() + (w * ez + (1 - w) * vz) * et.std()
    return {wc2026_teams.elo_name(teams[i]): float(br[i]) for i in range(len(teams))}
