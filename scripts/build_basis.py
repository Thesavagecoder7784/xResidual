#!/usr/bin/env python3
"""Cross-venue basis: the same bet, two prices -> viz/market/_basis.js.

    python scripts/build_basis.py

Polymarket (a global, soccer-literate crypto crowd) and Kalshi (a mostly American
retail crowd) trade the same World Cup winner contracts, but they disagree. This
measures the disagreement honestly: for every team, take the latest winner price on
each venue, strip each venue's overround (multiplicative devig, so I'm comparing
beliefs and not fee levels), and report

    basis(team) = P_polymarket - P_kalshi      (percentage points)

Positive basis means the global book prices the team higher than the American book;
negative means the American book is richer. Both retail venues get anchored against
the Betfair Exchange (the sharpest global soccer market I log) to see which one tracks
the sharp price more closely. A pro-market read, not a "who's wrong".

Reads the logged JSONL snapshots (latest observation per venue/team). Confederation
tags let us aggregate the per-team basis into the continent market (Europe, etc.).
"""
from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import wc2026_teams  # noqa: E402
from pull_forecast_data import ISO, KIT, INK, ensure_flag  # noqa: E402

OUT = os.path.join(ROOT, "viz", "market", "_basis.js")
DATA_GLOB = os.path.join(ROOT, "logger", "data", "snapshots-*.jsonl")
SHARP_BOOK = "betfair_ex_uk"  # the sharpest global soccer market we log

CONFED = {
    "UEFA": ["Spain", "France", "England", "Portugal", "Germany", "Netherlands",
             "Belgium", "Croatia", "Switzerland", "Norway", "Austria", "Sweden",
             "Turkey", "Scotland", "Czech Republic", "Bosnia & Herzegovina"],
    "CONMEBOL": ["Argentina", "Brazil", "Uruguay", "Colombia", "Ecuador", "Paraguay"],
    "CAF": ["Morocco", "Senegal", "Ivory Coast", "Ghana", "Egypt", "Algeria",
            "Tunisia", "South Africa", "DR Congo", "Cape Verde"],
    "CONCACAF": ["USA", "Mexico", "Canada", "Panama", "Haiti", "Curaçao"],
    "AFC": ["Japan", "South Korea", "Iran", "Australia", "Saudi Arabia", "Qatar",
            "Iraq", "Uzbekistan", "Jordan"],
    "OFC": ["New Zealand"],
}
CONF_OF = {t: c for c, ts in CONFED.items() for t in ts}
CONF_LABEL = {"UEFA": "Europe", "CONMEBOL": "South America", "CAF": "Africa",
              "CONCACAF": "N. America", "AFC": "Asia", "OFC": "Oceania"}


def latest_winner(rows, venue):
    """canonical team -> latest mid (probability) for the winner field of `venue`."""
    best = {}  # team -> (ts, mid)
    for q in rows:
        if q.get("venue") != venue:
            continue
        if q.get("extra", {}).get("market_type") != "winner":
            continue
        if q.get("outcome") in (None, "__error__"):
            continue
        mid = q.get("mid")
        if mid is None or mid <= 0:
            continue
        t = wc2026_teams.canonical(q["outcome"])
        if t not in wc2026_teams.WC2026_TEAMS:
            continue
        ts = q.get("ts_utc", "")
        if t not in best or ts > best[t][0]:
            best[t] = (ts, float(mid))
    return {t: v[1] for t, v in best.items()}


def latest_sharp(rows):
    """canonical team -> latest Betfair-Exchange implied prob (overround-stripped)."""
    best = {}
    for q in rows:
        ex = q.get("extra", {})
        if q.get("venue") != "oddsapi" or ex.get("market_type") != "outrights":
            continue
        if ex.get("bookmaker") != SHARP_BOOK:
            continue
        mid = q.get("mid")
        if mid is None or mid <= 0:
            continue
        t = wc2026_teams.canonical(q["outcome"])
        if t not in wc2026_teams.WC2026_TEAMS:
            continue
        ts = q.get("ts_utc", "")
        if t not in best or ts > best[t][0]:
            best[t] = (ts, float(mid))
    return {t: v[1] for t, v in best.items()}


def devig(raw):
    """Multiplicative overround removal: scale a field to sum to 1. Returns
    (fair_probs, overround) where overround = raw sum (e.g. 1.18 = 18% margin)."""
    s = sum(raw.values())
    if s <= 0:
        return {}, 0.0
    return {t: p / s for t, p in raw.items()}, s


def main() -> int:
    rows = []
    for fn in sorted(glob.glob(DATA_GLOB)):
        with open(fn, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    asof = max((q.get("ts_utc", "") for q in rows), default="")
    print(f"loaded {len(rows):,} quotes; asof {asof}")

    pm_raw = latest_winner(rows, "polymarket")
    ka_raw = latest_winner(rows, "kalshi")
    sharp_raw = latest_sharp(rows)
    print(f"  polymarket:{len(pm_raw)}  kalshi:{len(ka_raw)}  betfair:{len(sharp_raw)}")

    pm, or_pm = devig(pm_raw)
    ka, or_ka = devig(ka_raw)
    sharp, or_bf = devig(sharp_raw)

    common = sorted(set(pm) & set(ka), key=lambda t: -(pm[t] + ka[t]) / 2)
    teams = []
    for t in common:
        basis = (pm[t] - ka[t]) * 100  # percentage points, PM minus Kalshi (belief)
        raw_basis = (pm_raw[t] - ka_raw[t]) * 100  # raw, includes each venue's margin
        teams.append({
            "team": t, "iso": ISO.get(t, ""), "color": KIT.get(t, INK),
            "conf": CONF_OF.get(t, ""), "confl": CONF_LABEL.get(CONF_OF.get(t, ""), ""),
            "pm": round(pm[t] * 100, 2), "ka": round(ka[t] * 100, 2),
            "pm_raw": round(pm_raw[t] * 100, 2), "ka_raw": round(ka_raw[t] * 100, 2),
            "basis": round(basis, 2), "raw_basis": round(raw_basis, 2),
            "sharp": round(sharp[t] * 100, 2) if t in sharp else None,
        })

    # which retail venue tracks the sharp (Betfair) price more closely?
    anchored = [t for t in common if t in sharp]
    pm_mae = sum(abs(pm[t] - sharp[t]) for t in anchored) / len(anchored) * 100
    ka_mae = sum(abs(ka[t] - sharp[t]) for t in anchored) / len(anchored) * 100
    closer = "Polymarket" if pm_mae < ka_mae else "Kalshi"

    # continent market: aggregate devigged probability by confederation, each venue
    conts = []
    for c in ["UEFA", "CONMEBOL", "CAF", "CONCACAF", "AFC"]:
        members = [t for t in common if CONF_OF.get(t) == c]
        if not members:
            continue
        conts.append({
            "conf": c, "label": CONF_LABEL[c], "n": len(members),
            "pm": round(sum(pm[t] for t in members) * 100, 1),
            "ka": round(sum(ka[t] for t in members) * 100, 1),
        })
    conts.sort(key=lambda r: -max(r["pm"], r["ka"]))

    avg_abs_gap = sum(abs(d["basis"]) for d in teams) / len(teams)
    avg_abs_raw = sum(abs(d["raw_basis"]) for d in teams) / len(teams)
    payload = {
        "asof": asof, "teams": teams, "n_teams": len(teams),
        "avg_abs_raw": round(avg_abs_raw, 2),
        "overround": {"pm": round((or_pm - 1) * 100, 1), "kalshi": round((or_ka - 1) * 100, 1),
                      "betfair": round((or_bf - 1) * 100, 1)},
        "sharp": {"pm_mae": round(pm_mae, 2), "ka_mae": round(ka_mae, 2),
                  "closer": closer, "n": len(anchored)},
        "continents": conts, "avg_abs_gap": round(avg_abs_gap, 2),
    }

    for t in common:
        ensure_flag(ISO.get(t, ""))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.BASIS = " + json.dumps(payload) + ";\n")
    top = max(teams, key=lambda d: abs(d["basis"]))
    print(f"wrote {OUT}: {len(teams)} teams · avg |gap| {avg_abs_gap:.2f}pp · "
          f"widest {top['team']} {top['basis']:+.2f}pp · {closer} closer to sharp "
          f"(PM {pm_mae:.2f} vs KA {ka_mae:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
