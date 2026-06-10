#!/usr/bin/env python3
"""Live cross-venue arbitrage scan across the markets that exist on BOTH venues.

    python scripts/scan_arbitrage_live.py

scan_arbitrage.py only covers the tournament-winner market (the one Polymarket book the
30-min logger snapshots). But Kalshi lists ~80 World Cup series and Polymarket carries
several team-level twins. This pulls BOTH venues LIVE and scans every team-level pair we
can align, using executable bid/ask and netting Kalshi's fee (Polymarket charges none).

For the same contract on both venues, two directions can lock an outcome-independent profit:
    A) buy Polymarket @ poly_ask, sell Kalshi @ kalshi_bid   -> edge = kalshi_bid - poly_ask
    B) buy Kalshi @ kalshi_ask, sell Polymarket @ poly_bid   -> edge = poly_bid - kalshi_ask
Kalshi fee ~ 0.07*p*(1-p)/contract (symmetric in p). NOT modelled: top-of-book depth,
transfer/withdrawal cost, and capital locked until the market resolves.

PAPER ONLY (F-1 visa => no real-money trading). A market-efficiency measurement.
"""
from __future__ import annotations

import os
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "logger"))
from xresidual import wc2026_teams  # noqa: E402
import envtools  # noqa: E402
import venues  # noqa: E402

GAMMA = "https://gamma-api.polymarket.com/events"

# team-level twins. Each entry: (label, [polymarket slugs], kalshi series, kalshi ticker
# filter or None). Both sides resolve on the identical event, so a filled pair is hedged.
# - winner / advance: one Polymarket event vs a whole Kalshi series.
# - win group: Polymarket splits group winners into 12 per-group events; Kalshi is one
#   team-level series — merge the Polymarket side.
# - reach round: Polymarket has one event per round; Kalshi packs all rounds into KXWCROUND,
#   tagged by a ticker token (26RO16/26QUAR/26SEMI/26FINAL), so filter to the matching round.
GROUPS = list("abcdefghijkl")
PAIRS = [
    ("Tournament winner", ["world-cup-winner"], "KXMENWORLDCUP", None),
    ("Advance to knockout", ["world-cup-team-to-advance-to-knockout-stages"], "KXWCGROUPQUAL", None),
    ("Win group", [f"world-cup-group-{g}-winner" for g in GROUPS], "KXWCGROUPWIN", None),
    ("Reach round of 16", ["world-cup-nation-to-reach-round-of-16"], "KXWCROUND", "-26RO16-"),
    ("Reach quarterfinals", ["world-cup-nation-to-reach-quarterfinals"], "KXWCROUND", "-26QUAR-"),
    ("Reach semifinals", ["world-cup-nation-to-reach-semifinals"], "KXWCROUND", "-26SEMI-"),
    ("Reach final", ["world-cup-nation-to-reach-final"], "KXWCROUND", "-26FINAL-"),
]


def kalshi_fee(p: float) -> float:
    return 0.07 * p * (1.0 - p)


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
    containing `tick_filter` (used to pick one round out of the packed KXWCROUND series)."""
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


def scan_pair(label, pm, ka):
    common = sorted(set(pm) & set(ka))
    results = []
    for t in common:
        pb, pa = pm[t]
        kb, ka_ = ka[t]
        cands = []
        if pa is not None and kb is not None:
            cands.append(("buy PM / sell KA", kb - pa - kalshi_fee(kb)))
        if ka_ is not None and pb is not None:
            cands.append(("buy KA / sell PM", pb - ka_ - kalshi_fee(ka_)))
        if not cands:
            continue
        leg, net = max(cands, key=lambda c: c[1])
        results.append({"team": t, "leg": leg, "net": net,
                        "pm": f"{pb}/{pa}", "ka": f"{kb}/{ka_}"})
    results.sort(key=lambda r: -r["net"])
    return common, results


def main() -> int:
    env = envtools.load_env()
    print("CROSS-VENUE ARB SCAN (live) — Kalshi vs Polymarket, executable prices, net of Kalshi fee")
    print("PAPER ONLY (F-1). Net ignores depth, transfer cost, capital lockup until resolution.\n")
    grand = []
    for label, slugs, series, tick_filter in PAIRS:
        try:
            pm = poly_quotes(slugs)
            ka = kalshi_quotes(series, env, tick_filter)
        except Exception as e:
            print(f"## {label}: fetch error {e}\n")
            continue
        common, res = scan_pair(label, pm, ka)
        arbs = [r for r in res if r["net"] > 0]
        grand += [(label, r) for r in arbs]
        print(f"## {label}  (PM {slugs[0]}{'...' if len(slugs)>1 else ''} | KA {series}{tick_filter or ''})")
        print(f"   PM teams {len(pm)} · KA teams {len(ka)} · aligned {len(common)} · "
              f"net-positive {len(arbs)}")
        for r in (arbs or res[:3]):
            mark = "ARB" if r["net"] > 0 else "   "
            print(f"   {mark} {r['team']:<16} net {r['net']*100:+6.2f}c [{r['leg']}]  "
                  f"PM {r['pm']}  KA {r['ka']}")
        if res:
            best = res[0]["net"] * 100
            med = sorted(r["net"] for r in res)[len(res) // 2] * 100
            print(f"   best net {best:+.2f}c · median net {med:+.2f}c\n")
        else:
            print()
    print(f"=== TOTAL net-positive crossings across all pairs: {len(grand)} ===")
    for label, r in sorted(grand, key=lambda x: -x[1]["net"]):
        print(f"   {label:<22} {r['team']:<16} net {r['net']*100:+.2f}c [{r['leg']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
