"""FiveThirtyEight international SPI forecasts: historical calibration backtest set.

538 was wound down and its live API now returns an ABC News page, so we pull the
last Wayback Machine snapshot of the international matches file. It carries
pre-match home/draw/away probabilities (prob1/probtie/prob2) paired with actual
scores for ~3,850 completed internationals (2019-2024, incl. World Cup 2022): a
real (forecast, outcome) set to dry-run the Layer 3 calibration code before June 11.

These are 538's *model* probabilities, not market odds; the point of the dry-run is
to exercise and validate the calibration machinery on real forecasts, not to grade
538 specifically.
"""

from __future__ import annotations

import io
import os

import pandas as pd
import requests

# Pinned Wayback snapshot (id_ = raw capture, no toolbar wrapper).
SPI_INTL_URL = (
    "http://web.archive.org/web/20250306125415id_/"
    "https://projects.fivethirtyeight.com/soccer-api/international/spi_matches_intl.csv"
)
_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_CACHE_PATH = os.path.join(_CACHE_DIR, "spi_matches_intl.csv")


def _outcome(score1, score2) -> str:
    if score1 > score2:
        return "home"
    if score1 < score2:
        return "away"
    return "draw"


def load_spi_intl(refresh: bool = False, league_contains: str | None = None) -> pd.DataFrame:
    """Completed international matches with W/D/L forecasts and realized outcome.

    Returns columns: date, league, team1, team2, p_home, p_draw, p_away, outcome.
    `league_contains` optionally filters to a competition substring (e.g. "World
    Cup", "Nations League").
    """
    os.makedirs(_CACHE_DIR, exist_ok=True)
    if refresh or not os.path.exists(_CACHE_PATH):
        resp = requests.get(SPI_INTL_URL, timeout=60)
        resp.raise_for_status()
        raw = pd.read_csv(io.StringIO(resp.text))
        raw.to_csv(_CACHE_PATH, index=False)
    else:
        raw = pd.read_csv(_CACHE_PATH)

    df = raw.dropna(subset=["score1", "score2", "prob1", "prob2", "probtie"]).copy()
    if league_contains:
        df = df[df["league"].str.contains(league_contains, case=False, na=False)]
    df["outcome"] = [
        _outcome(s1, s2) for s1, s2 in zip(df["score1"], df["score2"])
    ]
    out = df.rename(columns={"prob1": "p_home", "probtie": "p_draw", "prob2": "p_away"})
    return out[["date", "league", "team1", "team2",
                "p_home", "p_draw", "p_away", "outcome"]].reset_index(drop=True)
