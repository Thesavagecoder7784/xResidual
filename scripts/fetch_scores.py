#!/usr/bin/env python3
"""Fast WC-result overlay: pull final scores from ESPN's free scoreboard API and merge any games
the martj42/international_results feed doesn't carry yet into the local results cache.

    python scripts/fetch_scores.py            # fetch only if a finished game is still missing
    python scripts/fetch_scores.py --force    # call ESPN regardless of the gate
    python scripts/fetch_scores.py --days 5   # widen the lookback window

ESPN's public scoreboard endpoint (https://site.api.espn.com/.../soccer/fifa.world/scoreboard)
posts a final scoreline within minutes of full time; the martj42 feed lags 1-2 days. This overlay
lets the model condition on a result the day it is played. martj42 stays canonical: once it carries
a game, the overlay defers to it (the merge skips any pair already in the cache), and overlay rows
are written in martj42's own naming so a later backfill is a no-op.

Call efficiency (the gate): ESPN is free and keyless, but there's no point calling it when nothing
has changed. Each run only hits ESPN when a fixture has *likely finished* (kickoff + FT_MARGIN) and
is *not yet in the merged cache* (martj42 + the overlay we've already pulled). So idle days make ZERO
calls, and a match day makes a handful — only in the window between a game's full time and the moment
we capture it. A finished-but-unmatchable game keeps the gate open for STALE_CUTOFF (then martj42
carries it and closes it), which bounds the worst case. The overlay is always re-merged locally (free)
regardless, so downstream builds still read a current merged cache every cycle.
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
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import data, wc2026_teams  # noqa: E402
from match_scheduler import kickoff_utc    # reuse the '13:00 UTC-6' -> UTC parser  # noqa: E402

SCORES_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
CACHE_DIR = os.path.join(ROOT, "data", "cache")
OVERLAY = os.path.join(CACHE_DIR, "wc_scores_overlay.json")   # last fetched completed games
META = os.path.join(CACHE_DIR, "wc_scores_meta.json")          # last-fetch time (informational)
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
WC_START = pd.Timestamp("2026-06-11")
HOSTS = {"United States", "Canada", "Mexico"}
FT_MARGIN = timedelta(minutes=105)   # a game is final ~105 min after kickoff; poll from here
STALE_CUTOFF = timedelta(hours=36)   # stop polling for a still-unmatched game (martj42 carries it by then)


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


def _fixtures() -> list:
    """[(pair_key, kickoff_utc, date_str, ground), ...] for every WC2026 fixture."""
    fx = pd.read_csv(FIXTURES)
    out = []
    for r in fx.itertuples(index=False):
        out.append((frozenset((_key(r.team1), _key(r.team2))),
                    kickoff_utc(str(r.date), str(r.time)), str(r.date), str(getattr(r, "ground", ""))))
    return out


def _martj42_keys() -> set:
    """Pair-keys of WC2026 games already in the canonical martj42 cache."""
    df = data.load_results()
    wc = df[(df["tournament"] == "FIFA World Cup") & (pd.to_datetime(df["date"]) >= WC_START)]
    return {frozenset((_key(r.home_team), _key(r.away_team))) for r in wc.itertuples(index=False)}


def _pending(now, captured: set, fixtures: list):
    """(should_fetch, reason): is there a fixture that has finished but isn't in `captured` yet?"""
    due = [(pair, ko) for pair, ko, *_ in fixtures
           if ko is not None and pair not in captured and ko + FT_MARGIN <= now <= ko + STALE_CUTOFF]
    if due:
        return True, f"{len(due)} finished game(s) not yet captured"
    nxt = min((ko for _, ko, *_ in fixtures if ko is not None and ko + FT_MARGIN > now), default=None)
    when = f"; next final ~{(nxt + FT_MARGIN - now).total_seconds() / 3600:.1f}h away" if nxt else ""
    return False, f"no finished game pending{when}"


def fetch_completed(days: int):
    """Return (records, n). Completed WC2026 games in martj42 naming, from ESPN's scoreboard."""
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


def merge_into_cache(records, have: set, fixtures: list) -> int:
    """Append any overlay game the cache doesn't already carry. Returns rows added."""
    fxmap = {pair: (date, ground) for pair, _ko, date, ground in fixtures}  # bounds overlay to real fixtures
    have = set(have)
    rows = []
    for rec in records:
        pair = frozenset((rec["home_team"], rec["away_team"]))
        if pair in have or pair not in fxmap:   # already canonical, or not a known WC2026 fixture
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
    ap.add_argument("--force", action="store_true", help="call ESPN regardless of the pending-game gate")
    ap.add_argument("--days", type=int, default=3, help="ESPN lookback window in days")
    args = ap.parse_args()

    os.makedirs(CACHE_DIR, exist_ok=True)
    overlay = _read_json(OVERLAY) or []
    now = datetime.now(timezone.utc)
    fixtures = _fixtures()
    have = _martj42_keys()                                      # canonical cache (loaded once, reused by merge)
    captured = have | {frozenset((o["home_team"], o["away_team"])) for o in overlay}

    fetch, reason = (True, "forced") if args.force else _pending(now, captured, fixtures)
    if fetch:
        try:
            overlay, n = fetch_completed(args.days)
            json.dump(overlay, open(OVERLAY, "w", encoding="utf-8"))
            json.dump({"last_fetch": now.isoformat(), "n_completed": n}, open(META, "w", encoding="utf-8"))
            print(f"  fetch_scores: ESPN call ({reason}) -> {n} completed games")
        except requests.RequestException as e:
            print(f"  fetch_scores: ESPN call failed ({e}); reusing cached overlay")
    else:
        print(f"  fetch_scores: skipped ESPN call ({reason})")

    added = merge_into_cache(overlay, have, fixtures)
    print(f"  fetch_scores: merged {added} game(s) ahead of martj42" if added
          else "  fetch_scores: nothing to add (martj42 has all known results)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
