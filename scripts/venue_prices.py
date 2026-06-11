#!/usr/bin/env python3
"""Live venue price helpers — fetch top-of-book per team from Polymarket and Kalshi.

Generic infrastructure for model-vs-market work: comparing the model's probability to the
price the market is actually quoting needs the live quote. (Extracted from the cross-venue
arbitrage exploration, which was retired — the durable use is forecasting/calibration, not
arb; see writeups/cross-venue-efficiency.md for why.)
"""
from __future__ import annotations

import os
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "logger"))
from xresidual import wc2026_teams  # noqa: E402
import venues  # noqa: E402

GAMMA = "https://gamma-api.polymarket.com/events"


def num(x):
    try:
        x = float(x)
        return x if x > 0 else None
    except (TypeError, ValueError):
        return None


def poly_quotes(slugs: list) -> dict:
    """canonical team -> (bid, ask) for the YES outcome, merged across one or more events."""
    out = {}
    for slug in slugs:
        r = requests.get(GAMMA, params={"slug": slug}, timeout=25).json()
        if not r:
            continue
        for m in r[0].get("markets", []):
            t = wc2026_teams.canonical(m.get("groupItemTitle") or "")
            if t not in wc2026_teams.WC2026_TEAMS:
                continue
            out[t] = (num(m.get("bestBid")), num(m.get("bestAsk")))
    return out


def kalshi_quotes(series: str, env: dict, tick_filter: str | None = None) -> dict:
    """canonical team -> (bid, ask) per market YES side; optionally restrict to tickers
    containing `tick_filter` (e.g. one round out of the packed KXWCROUND series)."""
    d = venues._kalshi_get(env, "/trade-api/v2/markets", {"series_ticker": series, "limit": 1000})
    out = {}
    for m in d.get("markets", []) or []:
        if tick_filter and tick_filter not in str(m.get("ticker", "")):
            continue
        t = wc2026_teams.canonical(m.get("yes_sub_title") or "")
        if t not in wc2026_teams.WC2026_TEAMS:
            continue
        out[t] = (venues._kalshi_price(m, "yes_bid"), venues._kalshi_price(m, "yes_ask"))
    return out
