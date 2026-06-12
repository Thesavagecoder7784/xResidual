#!/usr/bin/env python3
"""Fast WC-result overlay: pull final scores from The Odds API and merge any games the
martj42/international_results feed doesn't carry yet into the local results cache.

    python scripts/fetch_scores.py            # cadence-guarded (>= SCORES_EVERY_H since last call)
    python scripts/fetch_scores.py --force    # fetch now regardless of cadence

The Odds API posts a final scoreline within minutes of full time; the martj42 feed lags 1-2
days. This overlay lets the model condition on a result the day it is played. martj42 stays
canonical: once it carries a game, the overlay defers to it (the merge skips any pair already
in the cache), and the overlay rows are written in martj42's own naming so a later backfill is
a no-op. It runs in the VM refresh right after the martj42 refresh and before every build step,
so all downstream consumers (matches, group sim, bracket, board) read one merged cache.

Cost control: one scores call returns all 72 games and bills 2 credits. A cadence guard
(SCORES_EVERY_H, default 6h) caps that at ~8 credits/day even though the refresh runs every
30 min; off-cadence cycles re-apply the cached overlay for free.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import data, wc2026_teams  # noqa: E402

SCORES_URL = "https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/scores"
CACHE_DIR = os.path.join(ROOT, "data", "cache")
OVERLAY = os.path.join(CACHE_DIR, "wc_scores_overlay.json")   # last fetched completed games
META = os.path.join(CACHE_DIR, "wc_scores_meta.json")          # last-fetch time + credit log
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
WC_START = pd.Timestamp("2026-06-11")
HOSTS = {"United States", "Canada", "Mexico"}
SCORES_EVERY_H = float(os.environ.get("SCORES_EVERY_H", "6"))


def _key(name: str) -> str:
    """Odds API / fixture / martj42 name -> common martj42-convention key."""
    return wc2026_teams.elo_name(wc2026_teams.canonical(str(name).strip()))


def _load_env_key() -> str | None:
    if os.environ.get("ODDSAPI_KEY"):
        return os.environ["ODDSAPI_KEY"]
    envp = os.path.join(ROOT, ".env")
    if os.path.exists(envp):
        for line in open(envp, encoding="utf-8"):
            line = line.strip()
            if line.startswith("ODDSAPI_KEY=") and not line.startswith("#"):
                return line.split("=", 1)[1]
    return None


def _read_json(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _age_h(meta) -> float:
    if not meta or not meta.get("last_fetch"):
        return float("inf")
    try:
        last = datetime.fromisoformat(meta["last_fetch"])
        return (datetime.now(timezone.utc) - last).total_seconds() / 3600.0
    except ValueError:
        return float("inf")


def fetch_completed(api_key: str, days: int):
    """Return (records, credits_used). records: list of completed games in martj42 naming."""
    r = requests.get(SCORES_URL, params={"apiKey": api_key, "daysFrom": days}, timeout=30)
    r.raise_for_status()
    credits = r.headers.get("x-requests-last")
    records = []
    for g in r.json():
        if not g.get("completed") or not g.get("scores"):
            continue
        score = {s["name"]: s["score"] for s in g["scores"]}
        h, a = g["home_team"], g["away_team"]
        if h not in score or a not in score:
            continue
        try:
            hs, as_ = int(score[h]), int(score[a])
        except (TypeError, ValueError):
            continue
        records.append({"home_team": _key(h), "away_team": _key(a),
                        "home_score": hs, "away_score": as_,
                        "commence_time": g.get("commence_time", "")})
    return records, credits


def merge_into_cache(records) -> int:
    """Append any overlay game the cache doesn't already carry. Returns rows added."""
    df = data.load_results()  # reads the (just-refreshed) martj42 cache
    wc = df[(df["tournament"] == "FIFA World Cup") & (pd.to_datetime(df["date"]) >= WC_START)]
    have = {frozenset((_key(r.home_team), _key(r.away_team))) for r in wc.itertuples(index=False)}

    fx = pd.read_csv(FIXTURES)
    fxmap = {}  # pair-key -> (date, ground)
    for row in fx.itertuples(index=False):
        fxmap[frozenset((_key(row.team1), _key(row.team2)))] = (str(row.date), str(row.ground))

    rows = []
    for rec in records:
        pair = frozenset((rec["home_team"], rec["away_team"]))
        if pair in have:                  # martj42 already has it -> it is canonical
            continue
        date, ground = fxmap.get(pair, (rec["commence_time"][:10], ""))
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
    ap.add_argument("--force", action="store_true", help="fetch regardless of cadence")
    ap.add_argument("--days", type=int, default=3, help="Odds API daysFrom window")
    args = ap.parse_args()

    os.makedirs(CACHE_DIR, exist_ok=True)
    meta = _read_json(META) or {}
    overlay = _read_json(OVERLAY) or []

    should_fetch = args.force or _age_h(meta) >= SCORES_EVERY_H or not os.path.exists(OVERLAY)
    if should_fetch:
        key = _load_env_key()
        if not key:
            print("  fetch_scores: no ODDSAPI_KEY; reusing cached overlay")
        else:
            try:
                overlay, credits = fetch_completed(key, args.days)
                json.dump(overlay, open(OVERLAY, "w", encoding="utf-8"))
                meta = {"last_fetch": datetime.now(timezone.utc).isoformat(),
                        "last_credits": credits, "n_completed": len(overlay)}
                json.dump(meta, open(META, "w", encoding="utf-8"))
                print(f"  fetch_scores: Odds API -> {len(overlay)} completed (cost {credits} credits)")
            except requests.RequestException as e:
                print(f"  fetch_scores: API call failed ({e}); reusing cached overlay")
    else:
        print(f"  fetch_scores: cadence guard ({_age_h(meta):.1f}h < {SCORES_EVERY_H}h); reusing cached overlay")

    added = merge_into_cache(overlay)
    print(f"  fetch_scores: merged {added} game(s) ahead of martj42" if added
          else "  fetch_scores: nothing to add (martj42 has all known results)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
