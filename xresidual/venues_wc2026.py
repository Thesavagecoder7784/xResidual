"""2026 World Cup venues and host context (METHODOLOGY.md §9).

Two 2026-specific facts the baseline must respect:
  - Hosts (Mexico, USA, Canada) play group matches at home -> not neutral. This is
    the real, significant lever (home advantage ~+0.47 goals in our history).
  - Mexico City and Guadalajara are high-altitude. The original prior assumed thin
    air lifts total goals, but an empirical check rejected it (see the note on
    ALT_GOAL_FACTOR_PER_1000M below), so the altitude total-goals factor is disabled.

Stadium elevations are approximate (metres). Team names match the
martj42/eloratings convention used by the Elo engine.
"""

from __future__ import annotations

HOST_NATIONS = {"Mexico", "United States", "Canada"}

# venue (host city) -> approximate stadium elevation in metres
VENUE_ALTITUDE_M = {
    "Mexico City": 2240, "Guadalajara": 1566, "Monterrey": 540,   # Mexico
    "Atlanta": 320, "Kansas City": 270, "Dallas": 150, "Toronto": 76,
    "Boston": 30, "Los Angeles": 30, "Houston": 15, "Philadelphia": 10,
    "Seattle": 5, "San Francisco Bay Area": 5, "Vancouver": 3,
    "New York New Jersey": 3, "Miami": 2,
}

HIGH_ALTITUDE_M = 1500  # flag venues at/above this as high-altitude

# Altitude -> total-goals factor. DISABLED (0.0) after an empirical check on our own
# ~50k-match history: regressing total goals on home-venue altitude (controlling for
# team strength) gives a *negative*, significant coefficient (~-0.15 goals/1000m),
# the opposite sign of the original +3%/1000m prior. Altitude also touches only 7 of
# 72 group matches in 2026 (all Mexico City / Guadalajara), so the honest, simpler
# choice is no adjustment. (A real altitude effect does exist on goal *difference*,
# home-team supremacy when adapted, but that only applies to Mexico at home and is
# deliberately left out; it would only widen the host edge.)
ALT_GOAL_FACTOR_PER_1000M = 0.0
_ALT_BASELINE_M = 500.0


def is_high_altitude(altitude_m: float | None) -> bool:
    return altitude_m is not None and altitude_m >= HIGH_ALTITUDE_M


def total_goals_factor(altitude_m: float | None) -> float:
    """Multiplier applied to expected total goals (Skellam `tot`) for a venue."""
    if altitude_m is None:
        return 1.0
    excess_km = max(0.0, altitude_m - _ALT_BASELINE_M) / 1000.0
    return 1.0 + ALT_GOAL_FACTOR_PER_1000M * excess_km


def altitude_of(venue: str | None) -> float | None:
    return VENUE_ALTITUDE_M.get(venue) if venue else None
