"""Map Asian-handicap + totals lines to W/D/L probabilities (METHODOLOGY.md §10).

The literature (Ramírez, Reade & Singleton 2025) finds the traditional 1X2 market
carries favorite-longshot bias while the Asian-handicap market is efficient. To
reproduce that contrast on World Cup data we need AH odds expressed as W/D/L
probabilities, comparable to the h2h feed.

We use the market's central lines directly, which is both standard and consistent
with our baseline:
  - the handicap line is the market's expected goal supremacy `sup`
    (home favoured by `sup` goals);
  - the totals line is the market's expected total goals `tot`;
  - lambda_home = (tot + sup)/2, lambda_away = (tot - sup)/2  ->  Skellam -> W/D/L.

Same generative object as baseline.py, so the AH-implied and model-implied
probabilities are directly comparable.
"""

from __future__ import annotations

import numpy as np

from .skellam import wdl_probs

LAMBDA_FLOOR = 0.05


def supremacy_from_home_spread(home_spread_point: float) -> float:
    """Convert an Odds API home spread `point` to expected supremacy.

    A favoured home team is quoted with a negative point (e.g. -0.5 means it must
    win by >0.5), so supremacy = -point.
    """
    return -float(home_spread_point)


def wdl_from_supremacy_total(supremacy: float, total: float) -> tuple[float, float, float]:
    """(P(home), P(draw), P(away)) implied by handicap supremacy + total goals."""
    lh = max((total + supremacy) / 2.0, LAMBDA_FLOOR)
    la = max((total - supremacy) / 2.0, LAMBDA_FLOOR)
    return wdl_probs(lh, la)


def consensus_line(points) -> float | None:
    """Median market line across bookmakers (robust to a single odd book)."""
    pts = [float(p) for p in points if p is not None and not _isnan(p)]
    return float(np.median(pts)) if pts else None


def _isnan(x) -> bool:
    try:
        return np.isnan(x)
    except TypeError:
        return False
