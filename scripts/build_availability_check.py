#!/usr/bin/env python3
"""Validate availability-adjusted squad value against the market (Tier-1 check).

The thesis behind the availability adjustment (squad_values.ABSENCES) is that a key
player's injury/omission is *real* strength signal, not noise — so applying it should move
the model the same way the market moved on the squad news. This harness grades exactly
that. For each logged absence it compares:

  - model delta : the team's title probability with the absence applied minus without
                  (blended ratings, availability on vs off), in pp, and
  - market delta: how the team's de-vigged title price actually moved around the
                  announcement date in the logged snapshots, in pp,

and reports whether they agree in sign (the consistency check). With an empty ABSENCES
table it is a no-op that prints the schema; it starts grading as real squad news is logged.

    python scripts/build_availability_check.py
"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import baseline, data, elo, microstructure as ms, trajectory  # noqa: E402
from squad_values import ABSENCES, missing_top11  # noqa: E402
from blend import blended_ratings  # noqa: E402
from build_blend_check import title_probs  # noqa: E402

DATA = os.path.join(ROOT, "logger", "data")
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
OUT = os.path.join(ROOT, "viz", "model", "_availability.js")


def market_delta(panel: pd.DataFrame, team: str, date: str | None,
                 window_days: int = 4) -> float | None:
    """Change (pp) in the team's de-vigged title prob from just before to just after
    `date`, preferring Polymarket then Kalshi. None if the logs don't span the date."""
    if date is None or panel.empty:
        return None
    cut = pd.Timestamp(date, tz="UTC")
    g = panel[panel["team"] == team]
    for venue in ("polymarket", "kalshi"):
        v = g[g["venue"] == venue].sort_values("ts")
        if v.empty:
            continue
        before = v[v["ts"] <= cut]
        after = v[(v["ts"] > cut) & (v["ts"] <= cut + pd.Timedelta(days=window_days))]
        if not before.empty and not after.empty:
            return round((after["prob"].iloc[0] - before["prob"].iloc[-1]) * 100, 2)
    return None


def main() -> int:
    if not ABSENCES:
        print("squad_values.ABSENCES is empty — nothing to grade yet.")
        print("Add sourced rows from the official 26-man squads + Transfermarkt, e.g.:")
        print('  ABSENCES = {"Brazil": [{"player": "Neymar", "value": 18.0,')
        print('                          "status": "doubt", "date": "2026-06-07",')
        print('                          "source": "<url>"}]}')
        print("Then re-run: this compares the model\'s title move to the market\'s on that date.")
        return 0

    res = elo.build_ratings(data.load_results())
    params = baseline.calibrate(res.calib)
    fx = pd.read_csv(FIXTURES)
    print(f"simulating title odds with availability off vs on ({len(ABSENCES)} teams affected) ...")
    base = title_probs(blended_ratings(res.ratings, availability=False), params, fx)
    adj = title_probs(blended_ratings(res.ratings, availability=True), params, fx)

    panel = ms.venue_outright_panel(trajectory.load_snapshots(DATA))

    rows, agree, graded = [], 0, 0
    for team, absents in ABSENCES.items():
        m11 = missing_top11(team)
        # title_probs is already in percentage points, so the delta is pp directly
        model_d = round(adj.get(team, 0) - base.get(team, 0), 2)            # pp, <0 = absence hurt
        date = min((a["date"] for a in absents if a.get("date")), default=None)
        mkt_d = market_delta(panel, team, date)
        same = None if mkt_d is None else bool((model_d < 0) == (mkt_d < 0))
        if same is not None:
            graded += 1
            agree += int(same)
        rows.append({"team": team, "missing": m11["count"], "value_out": m11["value_out"],
                     "model_delta_pp": model_d, "market_delta_pp": mkt_d, "sign_agree": same,
                     "players": [a["player"] for a in absents]})

    rows.sort(key=lambda r: r["model_delta_pp"])
    print(f"\n{'team':<14}{'out':>4}{'£m_out':>8}{'model Δpp':>11}{'market Δpp':>12}  agree")
    for r in rows:
        md = "n/a" if r["market_delta_pp"] is None else f"{r['market_delta_pp']:+.2f}"
        ag = "-" if r["sign_agree"] is None else ("yes" if r["sign_agree"] else "NO")
        print(f"{r['team']:<14}{r['missing']:>4}{r['value_out']:>8.1f}"
              f"{r['model_delta_pp']:>+11.2f}{md:>12}  {ag}")
    if graded:
        print(f"\nsign-agreement with the market: {agree}/{graded} "
              f"(N={graded}; descriptive until more squad news is logged)")
    else:
        print("\nno market overlap yet (logs don't span the announcement dates) — model "
              "deltas recorded; consistency grades once the dates fall inside the captured series.")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.AVAILABILITY = " + json.dumps(
            {"rows": rows, "n_graded": graded, "n_agree": agree}) + ";\n")
    print(f"wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
