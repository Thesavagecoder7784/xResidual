#!/usr/bin/env python3
"""One-time backfill of outright-winner price history.

Live logging only started 2026-06-05, so the buildup (e.g. Portugal's climb) is
missing from the trajectory. Both venues expose history (Kalshi candlesticks,
Polymarket prices-history), so this pulls daily points for all 48 teams and writes
them in the snapshot format the trajectory loader already reads.

Output: data/snapshots-backfill.jsonl (overwritten each run, so it's idempotent),
tagged extra.backfill=true to distinguish it from live capture.

    python backfill.py --days 21
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone

import requests

import envtools
import venues

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "snapshots-backfill.jsonl")


def _iso(unix_s: int) -> str:
    return datetime.fromtimestamp(int(unix_s), tz=timezone.utc).isoformat()


def _row(ts_unix, venue, market_id, team, mid):
    return {"ts_utc": _iso(ts_unix), "venue": venue, "market_id": str(market_id),
            "market_label": "WC2026 Winner (backfill)", "outcome": str(team),
            "bid": None, "ask": None, "mid": mid, "last": None,
            "extra": {"market_type": "winner", "backfill": True}}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def kalshi_rows(env, start, end):
    mk = venues._kalshi_get(env, "/trade-api/v2/markets",
                            params={"series_ticker": "KXMENWORLDCUP", "limit": 1000}).get("markets", [])
    rows = []
    for m in mk:
        ticker, team = m.get("ticker"), m.get("yes_sub_title") or m.get("title", "")
        try:
            cs = venues._kalshi_get(
                env, f"/trade-api/v2/series/KXMENWORLDCUP/markets/{ticker}/candlesticks",
                params={"start_ts": start, "end_ts": end, "period_interval": 1440},
            ).get("candlesticks", [])
        except Exception:
            continue
        for c in cs:
            p = c.get("price", {})
            mid = _f(p.get("mean_dollars")) or _f(p.get("close_dollars")) or _f(p.get("previous_dollars"))
            if mid:
                rows.append(_row(c.get("end_period_ts"), "kalshi", ticker, team, mid))
    return rows


def polymarket_rows(start, end):
    ev = requests.get("https://gamma-api.polymarket.com/events",
                      params={"slug": "world-cup-winner"}, timeout=20).json()
    ev = ev[0] if isinstance(ev, list) and ev else ev
    rows = []
    for m in (ev.get("markets", []) if isinstance(ev, dict) else []):
        team = m.get("groupItemTitle") or m.get("question", "")
        toks = venues._maybe_json_list(m.get("clobTokenIds"))
        if not toks:
            continue
        try:
            # the startTs/endTs+fidelity combo is rejected; use interval=max (daily)
            # and filter to the window client-side.
            hist = requests.get("https://clob.polymarket.com/prices-history",
                                params={"market": toks[0], "interval": "max",
                                        "fidelity": 1440}, timeout=20).json().get("history", [])
        except Exception:
            continue
        for pt in hist:
            t, mid = pt.get("t"), _f(pt.get("p"))
            if mid and t and t >= start:
                rows.append(_row(t, "polymarket", m.get("id"), team, mid))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=21)
    args = ap.parse_args()
    env = envtools.load_env()
    now = int(time.time())
    start = now - args.days * 86400
    print(f"backfilling {args.days}d of outright history ...")
    rows = polymarket_rows(start, now)
    print(f"  polymarket: {len(rows)} points")
    if "KALSHI_ACCESS_KEY" in env:
        kr = kalshi_rows(env, start, now)
        print(f"  kalshi: {len(kr)} points")
        rows += kr
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    print(f"wrote {len(rows)} rows -> {os.path.relpath(OUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
