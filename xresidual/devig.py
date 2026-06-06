"""Vig removal: converting bookmaker odds to implied probabilities.

Proportional (multiplicative) normalization is the naive default and is what the
logger stores as `mid`. But the literature shows the margin is loaded unevenly
(more on longshots), so the method choice can shift implied probabilities, most
for soft books and at the tails. METHODOLOGY.md §9 commits to *reporting that
sensitivity* rather than picking one method silently; this module is how.

Wraps penaltyblog's implementations. The logger also stores raw `decimal_odds`, so
any method here can be re-applied to the logged series after the fact.

Reference: Štrumbelj (2014); Shin (1992,1993); see penaltyblog.implied.
"""

from __future__ import annotations

import numpy as np
import penaltyblog as pb

# naive, longshot-aware, and insider-trading-aware: the three most-cited.
DEFAULT_METHODS = ("multiplicative", "power", "shin")


def implied_probabilities(decimal_odds, method: str = "multiplicative") -> np.ndarray:
    """Fair (overround-removed) probabilities for one market's decimal odds."""
    res = pb.implied.calculate_implied(list(map(float, decimal_odds)), method=method)
    return np.asarray(res.probabilities, dtype=float)


def devig_sensitivity(decimal_odds, methods=DEFAULT_METHODS) -> dict:
    """Compare implied probabilities across methods for one market.

    Returns {"probs": {method: array}, "max_spread": array}. `max_spread[i]` is the
    range of probabilities the method choice induces for outcome i, the quantity to
    report when claiming a market is mis/well-calibrated. If the spread is small
    relative to the calibration effect, the finding is robust to the devig choice.
    """
    probs = {m: implied_probabilities(decimal_odds, m) for m in methods}
    stack = np.vstack(list(probs.values()))
    return {"probs": probs, "max_spread": stack.max(axis=0) - stack.min(axis=0)}
