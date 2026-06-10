#!/usr/bin/env python3
"""Group-stage travel burden -> viz/model/_travel.js (window.TRAVEL).

    python scripts/build_travel.py

Great-circle distance between each team's three group-match cities + minimum rest gap,
overlaid with the market's advance odds — plus the time-zone / jet-lag dimension for the
first multi-timezone World Cup. Headline: the travel burden is real and unequal, but the
residual circadian penalty after recovery is ~0 (4-6 day gaps clear the <=3-zone shifts),
so jet-lag is a media narrative, not an edge (see FINDINGS #25). Group stage only.
"""
from __future__ import annotations

import json
import math
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import wc2026_teams  # noqa: E402
from pull_forecast_data import ISO, KIT, INK, team_probs  # noqa: E402

OUT = os.path.join(ROOT, "viz", "model", "_travel.js")
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")

# 16 host-venue coordinates, keyed by the normalized city (matches group_sim._city).
COORDS = {
    "Mexico City": (19.43, -99.13), "Guadalajara": (20.68, -103.46), "Monterrey": (25.67, -100.24),
    "Atlanta": (33.75, -84.40), "Kansas City": (39.05, -94.48), "Dallas": (32.75, -97.09),
    "Toronto": (43.64, -79.39), "Boston": (42.09, -71.26), "Los Angeles": (33.95, -118.34),
    "Houston": (29.68, -95.41), "Philadelphia": (39.90, -75.17), "Seattle": (47.60, -122.33),
    "San Francisco Bay Area": (37.40, -121.97), "Vancouver": (49.19, -123.11),
    "New York New Jersey": (40.81, -74.07), "Miami": (25.96, -80.24),
}
_ALIAS = {"New York/New Jersey": "New York New Jersey"}

# UTC offsets during the tournament (Jun-Jul 2026): US DST on; Mexico has had no DST since
# 2023. Pacific -7 to Eastern -4 = a 3-hour span, the first multi-timezone World Cup.
TZ = {"Los Angeles": -7, "Seattle": -7, "San Francisco Bay Area": -7, "Vancouver": -7,
      "Mexico City": -6, "Guadalajara": -6, "Monterrey": -6,
      "Dallas": -5, "Houston": -5, "Kansas City": -5,
      "Atlanta": -4, "Toronto": -4, "Boston": -4, "Philadelphia": -4,
      "New York New Jersey": -4, "Miami": -4}


def _residual_zones(shift: int, rest_days: int) -> float:
    """Time zones still un-adjusted at kickoff after recovery. The circadian clock re-syncs
    ~1.0 zone/day westward (phase delay, easier) and ~0.67/day eastward (phase advance, the
    hard direction). `shift` is signed: + eastward. Literature-standard linear-residual form."""
    rate = 0.67 if shift > 0 else 1.0
    return max(0.0, abs(shift) - rate * rest_days)


def _city(ground: str) -> str:
    base = str(ground).split(" (")[0].strip()
    return _ALIAS.get(base, base)


def _haversine(a, b) -> float:
    R = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def main() -> int:
    fx = pd.read_csv(FIXTURES)
    fx["date"] = pd.to_datetime(fx["date"])
    g = fx[fx["group"].astype(str).str.startswith("Group")]
    adv = team_probs("world-cup-team-to-advance-to-knockout-stages")
    win = team_probs("world-cup-winner")

    recs = {}
    all_residuals = []
    for team in pd.unique(pd.concat([g.team1, g.team2])):
        m = g[(g.team1 == team) | (g.team2 == team)].sort_values("date")
        seq = [_city(x) for x in m.ground]
        km = sum(_haversine(COORDS[seq[i]], COORDS[seq[i + 1]]) for i in range(len(seq) - 1))
        rest = min((m.date.iloc[i + 1] - m.date.iloc[i]).days for i in range(len(m) - 1))
        # signed time-zone shifts between consecutive cities (+ eastward = the hard direction),
        # and the residual zones still un-adjusted at each kickoff after recovery.
        east = west = 0; resid = 0.0
        for i in range(len(seq) - 1):
            shift = TZ[seq[i + 1]] - TZ[seq[i]]
            gap = (m.date.iloc[i + 1] - m.date.iloc[i]).days
            east += max(shift, 0); west += max(-shift, 0)
            r = _residual_zones(shift, gap); resid = max(resid, r); all_residuals.append(r)
        t = wc2026_teams.canonical(team)
        recs[t] = {"team": t, "iso": ISO.get(t, ""), "color": KIT.get(t, INK),
                   "km": round(km), "rest": int(rest), "cities": seq,
                   "east_hrs": east, "west_hrs": west, "resid_zones": round(resid, 2),
                   "adv": round(adv.get(t, 0) * 100)}

    # one consistent ranking by km (1 = most travel), over all 48 teams
    ordered = sorted(recs.values(), key=lambda r: -r["km"])
    n = len(ordered)
    for i, r in enumerate(ordered):
        r["rank"] = i + 1
    fav_names = {wc2026_teams.canonical(t) for t in sorted(win, key=lambda t: -win[t])[:6]}
    for r in ordered:
        r["fav"] = r["team"] in fav_names

    # the worst 9 (a contiguous block) + the title favourites wherever they fall,
    # shown after an explicit elision so the jump reads as intentional.
    worst = [r for r in ordered[:9]]
    favs = [r for r in sorted((r for r in ordered if r["fav"]), key=lambda r: -r["km"])
            if r not in worst]

    # jet-lag summary: the myth-bust. residual circadian penalty after recovery, across every
    # group-stage travel leg. ~0 because the 4-6 day gaps clear the <=3-zone shifts.
    legs = len(all_residuals); zero = sum(1 for r in all_residuals if r < 1e-9)
    max_resid = round(max(all_residuals), 2) if all_residuals else 0.0
    jetlag = {"legs": legs, "zero_legs": zero, "zero_pct": round(100 * zero / max(legs, 1)),
              "max_resid_zones": max_resid, "span_hours": max(TZ.values()) - min(TZ.values()),
              "worst_case_winprob_pct": round(max_resid * 4 * 0.14, 1)}  # ~4 Elo/zone, ~0.14%/Elo

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.TRAVEL = " + json.dumps({"worst": worst, "favs": favs, "n": n,
                "max_km": ordered[0]["km"], "jetlag": jetlag}) + ";\n")
    print(f"wrote {OUT}: worst {ordered[0]['team']} {ordered[0]['km']}km (rank 1/{n})")
    print(f"  jet-lag: residual=0 for {zero}/{legs} legs ({jetlag['zero_pct']}%), max "
          f"{max_resid} zones (~{jetlag['worst_case_winprob_pct']}% win prob) over a "
          f"{jetlag['span_hours']}h span — the burden is real, the effect washes out")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
