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
from squad_values import SQUAD_VALUE

DEFAULT_W = 0.4


def blended_ratings(elo_ratings: dict, w: float = DEFAULT_W, teams=None) -> dict:
    teams = sorted(teams or wc2026_teams.WC2026_TEAMS)
    et = np.array([elo_ratings.get(wc2026_teams.elo_name(t), elo.INIT_RATING) for t in teams])
    vt = np.log10(np.array([SQUAD_VALUE[t] for t in teams], dtype=float))
    ez = (et - et.mean()) / et.std()
    vz = (vt - vt.mean()) / vt.std()
    br = et.mean() + (w * ez + (1 - w) * vz) * et.std()
    return {wc2026_teams.elo_name(teams[i]): float(br[i]) for i in range(len(teams))}
