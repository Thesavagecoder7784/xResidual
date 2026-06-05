"""The 48 qualified 2026 World Cup teams, and name reconciliation.

Source: openfootball/worldcup.json (2026), which matches the Odds API outright
naming. Use WC2026_TEAMS as the whitelist for trajectory.outright_probabilities to
drop the non-qualified longshots the futures market also lists.

Team names differ between feeds: the market/openfootball convention ("USA",
"Bosnia & Herzegovina") vs the martj42/Elo convention used by the baseline
("United States", "Bosnia and Herzegovina"). `elo_name()` bridges them so a market
outcome can be matched to its baseline expectation in the residual pipeline.
"""

from __future__ import annotations

# Market / openfootball convention (matches the Odds API outright outcomes).
WC2026_TEAMS = frozenset({
    "Algeria", "Argentina", "Australia", "Austria", "Belgium",
    "Bosnia & Herzegovina", "Brazil", "Canada", "Cape Verde", "Colombia",
    "Croatia", "Curaçao", "Czech Republic", "DR Congo", "Ecuador", "Egypt",
    "England", "France", "Germany", "Ghana", "Haiti", "Iran", "Iraq",
    "Ivory Coast", "Japan", "Jordan", "Mexico", "Morocco", "Netherlands",
    "New Zealand", "Norway", "Panama", "Paraguay", "Portugal", "Qatar",
    "Saudi Arabia", "Scotland", "Senegal", "South Africa", "South Korea",
    "Spain", "Sweden", "Switzerland", "Tunisia", "Turkey", "USA", "Uruguay",
    "Uzbekistan",
})

# Only the names that differ between the market feed and the Elo (martj42) data.
# Verified against the computed Elo rating keys; all other names match exactly.
_ODDS_TO_ELO = {
    "USA": "United States",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
}

# Venue-specific spellings -> canonical (WC2026_TEAMS) name. Kalshi and Polymarket
# each use their own conventions; verified against the live winner-market outcomes.
# Names not mapped and not already canonical are non-qualified/placeholder entries
# (e.g. "Italy", "Team AM") and resolve to a non-team that canonical() leaves as-is
# and is_qualified() rejects.
_VENUE_ALIASES = {
    "Bosnia and Herzegovina": "Bosnia & Herzegovina",  # Kalshi
    "Bosnia-Herzegovina": "Bosnia & Herzegovina",        # Polymarket
    "Congo DR": "DR Congo",                              # Kalshi, Polymarket
    "Curacao": "Curaçao",                                # Kalshi
    "Czechia": "Czech Republic",                          # Kalshi, Polymarket
    "Turkiye": "Turkey",                                  # Polymarket
}


def elo_name(market_team: str) -> str:
    """Translate a market/openfootball team name to the Elo-baseline convention."""
    return _ODDS_TO_ELO.get(market_team, market_team)


def canonical(venue_team: str) -> str:
    """Normalize a venue's team name to the canonical WC2026_TEAMS spelling."""
    return _VENUE_ALIASES.get(venue_team, venue_team)


def is_qualified(venue_team: str) -> bool:
    """True iff the (possibly venue-spelled) name is one of the 48 qualified teams."""
    return canonical(venue_team) in WC2026_TEAMS
