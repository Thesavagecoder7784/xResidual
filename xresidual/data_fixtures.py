"""2026 World Cup fixtures + results, from openfootball (free, no key).

One file holds all 104 matches; the `score.ft` field is populated as matches are
played, so the same loader gives the schedule before the tournament and the results
during it. Team/venue names match the Odds API and our wc2026_teams convention.
"""

from __future__ import annotations

import os

import pandas as pd
import requests

FIXTURES_URL = (
    "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
)
_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_CACHE_PATH = os.path.join(_CACHE_DIR, "wc2026_fixtures.csv")


def load_fixtures(refresh: bool = True) -> pd.DataFrame:
    """All 104 fixtures. Columns: round, group, date, time, ground, team1, team2,
    score1, score2 (NaN until played), played (bool). `time` is local kickoff with a
    UTC offset, e.g. "13:00 UTC-6".

    Default refresh=True because results change during the tournament; caching is
    only a fallback when offline.
    """
    os.makedirs(_CACHE_DIR, exist_ok=True)
    try:
        data = requests.get(FIXTURES_URL, timeout=30).json()
        rows = []
        for m in data.get("matches", []):
            ft = (m.get("score") or {}).get("ft")
            s1, s2 = (ft[0], ft[1]) if ft and len(ft) == 2 else (None, None)
            rows.append({
                "round": m.get("round"), "group": m.get("group"),
                "date": m.get("date"), "time": m.get("time"), "ground": m.get("ground"),
                "team1": m.get("team1"), "team2": m.get("team2"),
                "score1": s1, "score2": s2,
            })
        df = pd.DataFrame(rows)
        df.to_csv(_CACHE_PATH, index=False)
    except Exception:
        if not os.path.exists(_CACHE_PATH):
            raise
        df = pd.read_csv(_CACHE_PATH)

    df["played"] = df["score1"].notna() & df["score2"].notna()
    return df


def outcome(score1, score2) -> str:
    """W/D/L from team1's perspective: home / draw / away."""
    if score1 > score2:
        return "home"
    if score1 < score2:
        return "away"
    return "draw"
