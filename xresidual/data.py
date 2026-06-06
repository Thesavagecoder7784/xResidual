"""Data loading for the baseline.

Match results come from martj42/international_results (MIT-licensed, ~49k
internationals 1872->present, daily-updated). We cache the CSV locally so the
pipeline is reproducible offline and we don't hammer GitHub.
"""

from __future__ import annotations

import io
import os

import pandas as pd
import requests

RESULTS_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
)
_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_CACHE_PATH = os.path.join(_CACHE_DIR, "international_results.csv")


def load_results(refresh: bool = False) -> pd.DataFrame:
    """Return the international results frame, cached locally.

    Columns: date, home_team, away_team, home_score, away_score, tournament,
    city, country, neutral. Rows with missing scores (future/abandoned fixtures)
    are dropped; `date` is parsed and `neutral` coerced to bool.
    """
    os.makedirs(_CACHE_DIR, exist_ok=True)
    if refresh or not os.path.exists(_CACHE_PATH):
        # use requests (certifi CA bundle); pandas' urllib can't verify SSL on
        # some Python builds.
        resp = requests.get(RESULTS_URL, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        df.to_csv(_CACHE_PATH, index=False)
    else:
        df = pd.read_csv(_CACHE_PATH)

    df = df.dropna(subset=["home_score", "away_score"]).copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["neutral"] = df["neutral"].astype(bool)
    return df.sort_values("date").reset_index(drop=True)
