"""2026 World Cup squad market values (Transfermarkt), by canonical team name.

A third, independent lens on team strength: results-blind (it values players, not
wins), and the one a bookmaker-style model leans on. Source: Transfermarkt combined
squad values, June 2026 (£m). Units are arbitrary for our use (we compare shares).
"""

# canonical WC2026_TEAMS name -> combined squad value (£m, Transfermarkt, Jun 2026)
SQUAD_VALUE = {
    "France": 1320, "England": 1130, "Spain": 1090, "Portugal": 880, "Germany": 862.97,
    "Brazil": 788.78, "Netherlands": 723.93, "Argentina": 707.76, "Norway": 519.68,
    "Belgium": 469.45, "Ivory Coast": 459.07, "Morocco": 422.15, "Senegal": 408.92,
    "Turkey": 408.74, "Sweden": 370.25, "Uruguay": 350.9, "Croatia": 333.51, "USA": 327.03,
    "Ecuador": 325.3, "Switzerland": 288.46, "Colombia": 263.95, "Japan": 241.16,
    "Austria": 234.94, "Algeria": 222.75, "Ghana": 199.64, "Canada": 175.58, "Mexico": 168.27,
    "Czech Republic": 164.45, "Scotland": 152.39, "Paraguay": 135.89,
    "Bosnia & Herzegovina": 129.04, "DR Congo": 128.91, "South Korea": 123.07, "Egypt": 116.48,
    "Australia": 63.7, "Uzbekistan": 60.74, "Tunisia": 60.06, "Cape Verde": 48.59,
    "Haiti": 48.09, "South Africa": 39.61, "Saudi Arabia": 32.09, "New Zealand": 30.57,
    "Panama": 30.12, "Iran": 28.24, "Curaçao": 22.51, "Iraq": 18.21, "Qatar": 17.24,
    "Jordan": 16.89,
}


# --- Availability adjustment (Tier-1 model upgrade) ------------------------------
# Static SQUAD_VALUE assumes the full-strength nation. A confirmed injury, suspension,
# or selection omission of a top-11-quality player lowers a team's *effective* strength
# in a way the static value misses — it is what faded Brazil on the Neymar fitness doubt,
# and what moves a price on squad-announcement day. ABSENCES is a curated, sourced table
# of such players who are NOT available for the World Cup, in the SAME units as
# SQUAD_VALUE (£m, Transfermarkt). It doubles as the "missing would-be top-11" covariate
# (count + value) that a 2026 forecasting model uses to stop overrating depleted squads.
#
# DELIBERATELY EMPTY by default: add a row only with a real source + Transfermarkt value,
# never a guessed one. `status` scales the deduction — "out" counts in full, "doubt"
# counts DOUBT_WEIGHT (a probable-but-unconfirmed absence). Example row (verify before use):
#   "Brazil": [{"player": "Neymar", "value": <TM £m>, "status": "doubt",
#               "source": "<url> YYYY-MM-DD"}],
DOUBT_WEIGHT = 0.5

ABSENCES: dict[str, list[dict]] = {}


def adjusted_squad_value(team: str) -> float:
    """SQUAD_VALUE minus the (status-weighted) value of absent top-11 players, floored so
    an over-entered table can never cut a team's value by more than half."""
    base = SQUAD_VALUE[team]
    miss = sum(a["value"] * (DOUBT_WEIGHT if a.get("status") == "doubt" else 1.0)
               for a in ABSENCES.get(team, []))
    return max(base - miss, base * 0.5)


def adjusted_squad_values() -> dict:
    """The full {team -> value} map with availability applied (identity where no absences
    are logged, so it is safe to use everywhere SQUAD_VALUE is used)."""
    return {t: adjusted_squad_value(t) for t in SQUAD_VALUE}


def missing_top11(team: str) -> dict:
    """The 'would-be top-11 missing' covariate: how many such players are out and their
    combined value. count=0 / value_out=0 when the team is at full strength."""
    a = ABSENCES.get(team, [])
    return {"count": len(a), "value_out": round(sum(x["value"] for x in a), 2)}
