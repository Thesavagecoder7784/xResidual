#!/usr/bin/env python3
"""Fast WC-result overlay: pull final scores from ESPN's free scoreboard API and merge any games
the martj42/international_results feed doesn't carry yet into the local results cache.

    python scripts/fetch_scores.py            # fetch + merge (free, no key, every cycle)
    python scripts/fetch_scores.py --days 5   # widen the lookback window

ESPN's public scoreboard endpoint (https://site.api.espn.com/.../soccer/fifa.world/scoreboard)
posts a final scoreline within minutes of full time; the martj42 feed lags 1-2 days. This overlay
lets the model condition on a result the day it is played. martj42 stays canonical: once it carries
a game, the overlay defers to it (the merge skips any pair already in the cache), and overlay rows
are written in martj42's own naming so a later backfill is a no-op. It runs in the VM refresh right
after the martj42 refresh and before every build step, so all downstream consumers (matches, group
sim, bracket, board) read one merged cache.

Why ESPN (replaces The Odds API, Jun 2026): it needs NO API key and has no credit quota, so there
is nothing to expire or exhaust (the Odds-API key 401'd mid-tournament and silently froze results)
and no cost guard to throttle it — we just fetch fresh every cycle. martj42 remains the canonical
backstop, so if ESPN's unofficial endpoint ever changes, results still self-heal in 1-2 days.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import data, wc2026_teams  # noqa: E402

SCORES_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
CACHE_DIR = os.path.join(ROOT, "data", "cache")
OVERLAY = os.path.join(CACHE_DIR, "wc_scores_overlay.json")   # last fetched completed games
META = os.path.join(CACHE_DIR, "wc_scores_meta.json")          # last-fetch time (informational)
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
WC_START = pd.Timestamp("2026-06-11")
HOSTS = {"United States", "Canada", "Mexico"}


def _key(name: str) -> str:
    """ESPN / fixture / martj42 name -> common martj42-convention key."""
    return wc2026_teams.elo_name(wc2026_teams.canonical(str(name).strip()))


def _read_json(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _score(competitor) -> int | None:
    """ESPN competitor score: a bare string ('5') or {'value': 5, 'displayValue': '5'}."""
    s = competitor.get("score")
    if isinstance(s, dict):
        s = s.get("value", s.get("displayValue"))
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def fetch_completed(days: int):
    """Return (records, n). records: completed games in martj42 naming, from ESPN's scoreboard.

    ESPN takes a YYYYMMDD-YYYYMMDD date window; we look back `days` and one day forward so a game
    that finished just after UTC midnight is still in range. The fifa.world league is the World Cup
    finals, so every event in window is a WC2026 match."""
    today = datetime.now(timezone.utc).date()
    window = f"{(today - timedelta(days=days)):%Y%m%d}-{(today + timedelta(days=1)):%Y%m%d}"
    r = requests.get(SCORES_URL, params={"dates": window, "limit": 200}, timeout=30)
    r.raise_for_status()
    records = []
    for ev in r.json().get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        status = (comp.get("status") or ev.get("status") or {}).get("type", {})
        if not status.get("completed"):
            continue
        cs = comp.get("competitors") or []
        if len(cs) != 2:
            continue
        home = next((c for c in cs if c.get("homeAway") == "home"), cs[0])
        away = next((c for c in cs if c.get("homeAway") == "away"), cs[1])
        hs, as_ = _score(home), _score(away)
        if hs is None or as_ is None:
            continue
        records.append({
            "home_team": _key(home.get("team", {}).get("displayName", "")),
            "away_team": _key(away.get("team", {}).get("displayName", "")),
            "home_score": hs, "away_score": as_,
            "commence_time": ev.get("date", ""),
        })
    return records, len(records)


def merge_into_cache(records) -> int:
    """Append any overlay game the cache doesn't already carry. Returns rows added."""
    df = data.load_results()  # reads the (just-refreshed) martj42 cache
    wc = df[(df["tournament"] == "FIFA World Cup") & (pd.to_datetime(df["date"]) >= WC_START)]
    have = {frozenset((_key(r.home_team), _key(r.away_team))) for r in wc.itertuples(index=False)}

    fx = pd.read_csv(FIXTURES)
    fxmap = {}  # pair-key -> (date, ground); also bounds the overlay to real WC2026 fixtures
    for row in fx.itertuples(index=False):
        fxmap[frozenset((_key(row.team1), _key(row.team2)))] = (str(row.date), str(row.ground))

    rows = []
    for rec in records:
        pair = frozenset((rec["home_team"], rec["away_team"]))
        if pair in have:                  # martj42 already has it -> it is canonical
            continue
        if pair not in fxmap:             # not a known WC2026 fixture -> ignore (don't pollute)
            continue
        date, ground = fxmap[pair]
        rows.append({"date": date, "home_team": rec["home_team"], "away_team": rec["away_team"],
                     "home_score": rec["home_score"], "away_score": rec["away_score"],
                     "tournament": "FIFA World Cup", "city": ground, "country": "",
                     "neutral": rec["home_team"] not in HOSTS})
        have.add(pair)
    if not rows:
        return 0
    raw = pd.read_csv(data._CACHE_PATH)  # append to the on-disk cache (pre-dropna, full schema)
    merged = pd.concat([raw, pd.DataFrame(rows)[list(raw.columns)]], ignore_index=True)
    merged.to_csv(data._CACHE_PATH, index=False)
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="(deprecated no-op; ESPN is free so every run fetches)")
    ap.add_argument("--days", type=int, default=3, help="ESPN lookback window in days")
    args = ap.parse_args()

    os.makedirs(CACHE_DIR, exist_ok=True)
    overlay = _read_json(OVERLAY) or []
    try:
        overlay, n = fetch_completed(args.days)
        json.dump(overlay, open(OVERLAY, "w", encoding="utf-8"))
        json.dump({"last_fetch": datetime.now(timezone.utc).isoformat(), "n_completed": n},
                  open(META, "w", encoding="utf-8"))
        print(f"  fetch_scores: ESPN -> {n} completed games")
    except requests.RequestException as e:
        print(f"  fetch_scores: ESPN call failed ({e}); reusing cached overlay")

    added = merge_into_cache(overlay)
    print(f"  fetch_scores: merged {added} game(s) ahead of martj42" if added
          else "  fetch_scores: nothing to add (martj42 has all known results)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
