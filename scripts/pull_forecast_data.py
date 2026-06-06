#!/usr/bin/env python3
"""Pull Polymarket's tournament-forecast markets (reach QF/SF/Final, winner, group
winners) and write viz/_forecast.js for the Path-to-Final + Group-Board cards.

    python scripts/pull_forecast_data.py   # -> viz/_forecast.js  (window.FORECAST)
"""
from __future__ import annotations

import json
import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xresidual import wc2026_teams  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "viz", "market", "_forecast.js")

# national-kit colours (canonical names), white/yellow kits shifted to a legible
# identity colour for the cream paper.
KIT = {
    "Spain": "#d4122a", "France": "#1e4fc4", "England": "#0a1f5c", "Portugal": "#7c1c2c",
    "Argentina": "#6cabdd", "Brazil": "#0a8f3c", "Germany": "#2b2b2b", "Netherlands": "#e8731c",
    "Belgium": "#c8102e", "Croatia": "#c8102e", "Uruguay": "#4f9fd6", "Mexico": "#1f7a4d",
    "USA": "#0a1f5c", "Colombia": "#c08a00", "Morocco": "#a31226", "Japan": "#1b2a78",
    "Senegal": "#0a7d3b", "Switzerland": "#c8102e", "Norway": "#c8102e", "Ecuador": "#c08a00",
    "Ivory Coast": "#e8731c", "Austria": "#c8102e", "Sweden": "#c89000", "Turkey": "#c8102e",
    "Scotland": "#0a2342", "Canada": "#d4122a", "Paraguay": "#b3122a", "Czech Republic": "#c8102e",
    "Bosnia & Herzegovina": "#1e4fc4", "Algeria": "#0a7d4f", "Ghana": "#0a7d3b", "Egypt": "#a31226",
    "South Korea": "#c8102e", "Australia": "#0a7d3b", "Iran": "#0a7d4f", "South Africa": "#0a7d3b",
    "Tunisia": "#a31226", "DR Congo": "#1e50c8", "Jamaica": "#0a7d3b", "Qatar": "#7a1f3a",
    "Saudi Arabia": "#0a7d3b", "Panama": "#b3122a", "New Zealand": "#3a3a3a", "Iraq": "#0a7d4f",
    "Cape Verde": "#16407a", "Uzbekistan": "#1e50c8", "Jordan": "#c8102e", "Haiti": "#1e50c8",
    "Curaçao": "#1e4fc4",
}
INK = "#4a443b"

# canonical team -> ISO code for circle-flags (home nations use gb-eng / gb-sct)
ISO = {
    "Spain": "es", "France": "fr", "England": "gb-eng", "Portugal": "pt", "Argentina": "ar",
    "Brazil": "br", "Germany": "de", "Netherlands": "nl", "Belgium": "be", "Croatia": "hr",
    "Uruguay": "uy", "Mexico": "mx", "USA": "us", "Colombia": "co", "Morocco": "ma",
    "Japan": "jp", "Senegal": "sn", "Switzerland": "ch", "Norway": "no", "Ecuador": "ec",
    "Ivory Coast": "ci", "Austria": "at", "Sweden": "se", "Turkey": "tr", "Scotland": "gb-sct",
    "Canada": "ca", "Paraguay": "py", "Czech Republic": "cz", "Bosnia & Herzegovina": "ba",
    "Algeria": "dz", "Ghana": "gh", "Egypt": "eg", "South Korea": "kr", "Australia": "au",
    "Iran": "ir", "South Africa": "za", "Tunisia": "tn", "DR Congo": "cd", "Qatar": "qa",
    "Saudi Arabia": "sa", "Panama": "pa", "New Zealand": "nz", "Iraq": "iq", "Cape Verde": "cv",
    "Uzbekistan": "uz", "Jordan": "jo", "Haiti": "ht", "Curaçao": "cw",
}
FLAG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "viz", "flags")


def ensure_flag(iso: str) -> None:
    """Download a circular flag SVG locally (once) so rendering never races a CDN."""
    if not iso:
        return
    path = os.path.join(FLAG_DIR, f"{iso}.svg")
    if os.path.exists(path):
        return
    os.makedirs(FLAG_DIR, exist_ok=True)
    try:
        r = requests.get(f"https://hatscripts.github.io/circle-flags/flags/{iso}.svg", timeout=15)
        if r.ok:
            open(path, "w", encoding="utf-8").write(r.text)
    except Exception:
        pass


TAG_2026 = "102350"  # Polymarket tag: 2026-fifa-world-cup


def discover_group_slugs(keyword: str) -> dict:
    """Map group letter -> event slug for per-group placement markets, whose slugs
    carry a creation-timestamp suffix (e.g. 'world-cup-group-a-second-place-2026...').
    keyword is 'second-place' or 'last-place'."""
    out = {}
    try:
        evs = requests.get("https://gamma-api.polymarket.com/events",
                           params={"tag_id": TAG_2026, "limit": 500, "closed": "false"},
                           timeout=30).json()
    except Exception:
        return out
    pat = re.compile(rf"^world-cup-group-([a-l])-{keyword}(?:-\d+)?$")
    for ev in (evs if isinstance(evs, list) else []):
        m = pat.match(ev.get("slug", "") or "")
        if m:
            out[m.group(1)] = ev["slug"]
    return out


def event_markets(slug: str) -> list[dict]:
    r = requests.get("https://gamma-api.polymarket.com/events", params={"slug": slug}, timeout=25).json()
    e = r[0] if isinstance(r, list) and r else r
    return e.get("markets", []) if isinstance(e, dict) else []


def yes(m: dict):
    op = m.get("outcomePrices")
    try:
        return float(json.loads(op)[0]) if isinstance(op, str) else None
    except (ValueError, TypeError):
        return None


def team_probs(slug: str) -> dict:
    """canonical team -> yes prob, for a 'one market per team' event."""
    out = {}
    for m in event_markets(slug):
        t = wc2026_teams.canonical(m.get("groupItemTitle") or "")
        p = yes(m)
        if p is not None and t:
            out[t] = p
    return out


def main() -> int:
    print("pulling reach-round + winner markets ...")
    r16 = team_probs("world-cup-nation-to-reach-round-of-16")
    qf = team_probs("world-cup-nation-to-reach-quarterfinals")
    sf = team_probs("world-cup-nation-to-reach-semifinals")
    fn = team_probs("world-cup-nation-to-reach-final")
    win = team_probs("world-cup-winner")

    pct = lambda d, t: round(d.get(t, 0) * 100, 1)
    # matrix: the realistic field (top 16 by reach-R16), every round (the bracket outlook)
    field = sorted(r16, key=lambda t: -r16[t])[:16]
    matrix = [{"team": t, "color": KIT.get(t, INK), "iso": ISO.get(t, ""),
               "r16": pct(r16, t), "qf": pct(qf, t), "sf": pct(sf, t),
               "final": pct(fn, t), "win": pct(win, t)} for t in field]
    path = matrix[:8]  # kept for back-compat

    # Advancement is what actually matters in the 48-team format: top 2 of each
    # group PLUS the 8 best third-placed teams reach the Round of 32 (32 of 48 advance).
    # So we price each team's path: P(top 2) from winner+second markets, P(advance)
    # from the knockout market, and the third-place-wildcard slice = adv - top2.
    print("pulling advance-to-knockout + per-group placement markets ...")
    adv = team_probs("world-cup-team-to-advance-to-knockout-stages")
    sec_slugs = discover_group_slugs("second-place")
    last_slugs = discover_group_slugs("last-place")
    print(f"  advance:{len(adv)} teams · second-place groups:{len(sec_slugs)} · last-place groups:{len(last_slugs)}")

    print("pulling 12 group-winner markets ...")
    groups = {}
    for g in "abcdefghijkl":
        gw = team_probs(f"world-cup-group-{g}-winner")
        p2 = team_probs(sec_slugs[g]) if g in sec_slugs else {}
        lp = team_probs(last_slugs[g]) if g in last_slugs else {}
        # Anchor the team set to the group-winner market (reliably the 4 group teams).
        team_set = [t for t in gw if t in wc2026_teams.WC2026_TEAMS] or \
                   [t for t in p2 if t in wc2026_teams.WC2026_TEAMS]
        rows = []
        for t in team_set:
            pw, ps, a = gw.get(t, 0.0), p2.get(t, 0.0), adv.get(t, 0.0)
            top2 = pw + ps
            rows.append({"team": t, "color": KIT.get(t, INK), "iso": ISO.get(t, ""),
                         "gw": round(pw * 100, 1), "p2": round(ps * 100, 1),
                         "top2": round(top2 * 100, 1), "adv": round(a * 100, 1),
                         "via3": round(max(0.0, a - top2) * 100, 1),
                         "last": round(lp.get(t, 0.0) * 100, 1)})
        rows.sort(key=lambda r: -r["gw"])  # gw order: keeps the Group Board card stable
        if rows:
            groups[g.upper()] = rows

    # fetch flag SVGs for everyone that appears
    used = {r["iso"] for r in matrix} | {r["iso"] for rows in groups.values() for r in rows}
    for iso in used:
        ensure_flag(iso)
    print(f"flags ready: {len([i for i in used if i])}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.FORECAST = " + json.dumps({"matrix": matrix, "path": path, "groups": groups}) + ";\n")
    print(f"wrote {OUT}: {len(matrix)} field teams, {len(groups)} groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
