#!/usr/bin/env python3
"""Compute data for the must-watch and longshot-spread cards from logged snapshots.

    python scripts/build_insight_data.py   # -> viz/_insights.js  (window.INSIGHTS)
"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # for pull_forecast_data.ISO
from xresidual import microstructure, trajectory, wc2026_teams  # noqa: E402
from pull_forecast_data import ISO  # noqa: E402

def iso_of(name):
    return ISO.get(wc2026_teams.canonical(name), "")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "viz", "market", "_insights.js")
LOG = os.path.join(ROOT, "logger", "data")


def match_table(snaps: pd.DataFrame) -> list[dict]:
    """Per group match: market W/D/L (Odds API consensus) + implied total goals →
    expected goals and 'closeness' (1 - favourite's win prob)."""
    h = snaps[(snaps["venue"] == "oddsapi") & (snaps.get("market_type") == "h2h")
              & (snaps["outcome"] != "__error__") & snaps["mid"].notna()].copy()
    if h.empty:
        return []
    h = h[h["ts_utc"] == h["ts_utc"].max()]
    cons = h.groupby(["market_label", "outcome"])["mid"].median()
    totals = microstructure.market_implied_totals(snaps).set_index("market_label")["implied_total_goals"]

    rows = []
    for label in cons.index.get_level_values(0).unique():
        if " vs " not in label or label not in totals.index:
            continue
        home, away = label.split(" vs ", 1)
        try:
            ph, pd_, pa = cons[(label, home)], cons[(label, "Draw")], cons[(label, away)]
        except KeyError:
            continue
        s = ph + pd_ + pa
        if not s:
            continue
        ph, pa = ph / s, pa / s
        fav, favp = (home, ph) if ph >= pa else (away, pa)
        rows.append({"home": home, "away": away, "home_iso": iso_of(home), "away_iso": iso_of(away),
                     "goals": round(float(totals[label]), 2),
                     "close": round(1 - max(ph, pa), 3), "fav": fav, "favp": round(max(ph, pa), 3)})
    return rows


def spread_table(snaps: pd.DataFrame) -> list[dict]:
    """Per (venue, team): mid and RELATIVE spread (spread/mid), the longshot premium."""
    ob = microstructure.orderbook_panel(snaps)
    if ob.empty:
        return []
    ob = ob[ob["ts"] == ob["ts"].max()]
    ob = ob[(ob["mid"] > 0) & ob["spread"].notna()]
    return [{"team": r.team, "venue": r.venue, "mid": round(r.mid, 4),
             "rel": round(r.spread / r.mid, 4)} for r in ob.itertuples() if r.mid > 0]


def main() -> int:
    snaps = trajectory.load_snapshots(LOG)
    mt, st = match_table(snaps), spread_table(snaps)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.INSIGHTS = " + json.dumps({"matches": mt, "spread": st}) + ";\n")
    print(f"wrote {OUT}: {len(mt)} matches, {len(st)} (venue,team) spread points")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
