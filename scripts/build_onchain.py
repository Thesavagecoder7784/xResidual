#!/usr/bin/env python3
"""On-chain forensics: who is actually behind the money? -> viz/market/_onchain.js

    python scripts/build_onchain.py

Polymarket settles on Polygon, so every trade carries a wallet (proxyWallet ≈ one
user account). The money map showed longshots out-trade the favourites in $ volume;
this checks *who* that volume is. For each team's winner market we pull a fixed sample of recent trades and measure:
  breadth   = unique wallets behind the flow
  top10_flow= share of traded volume from the 10 busiest wallets
Finding: longshot turnover is concentrated in a few large wallets (whales / makers),
not broad retail, the opposite of what raw volume implies. (The /holders endpoint
returns unreliable counts for some markets, so we stick to the robust trade metrics.)

Note: a recent-trades sample (equal per team), and one entity can run several proxy
wallets, so true concentration is if anything understated. 'Whale' = large wallet,
which may be a market-maker, not necessarily a punter, so read it descriptively.
"""
from __future__ import annotations

import json
import os
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from pull_forecast_data import ISO, KIT, INK  # noqa: E402

OUT = os.path.join(ROOT, "viz", "market", "_onchain.js")
G, D = "https://gamma-api.polymarket.com", "https://data-api.polymarket.com"
FAVES = ["Spain", "France", "England", "Argentina"]
LONGSHOTS = ["Uzbekistan", "Saudi Arabia", "New Zealand", "Curaçao", "DR Congo"]
CAP = 2500


def condition_ids():
    e = requests.get(f"{G}/events", params={"slug": "world-cup-winner"}, timeout=25).json()
    e = e[0] if isinstance(e, list) else e
    return {(m.get("groupItemTitle") or "").strip(): m.get("conditionId") for m in e["markets"]}


def trades(cid, cap=CAP):
    out, off = [], 0
    while len(out) < cap:
        t = requests.get(f"{D}/trades", params={"market": cid, "limit": 500, "offset": off}, timeout=25).json()
        if not isinstance(t, list) or not t:
            break
        out += t; off += len(t)
        if len(t) < 500:
            break
    return out[:cap]


def analyze(team, cid, group):
    tr = trades(cid)
    if not tr:
        return None
    w = {}
    for r in tr:
        w[r["proxyWallet"]] = w.get(r["proxyWallet"], 0.0) + float(r["size"])
    vols = sorted(w.values(), reverse=True); tot = sum(vols) or 1
    return {"team": team, "iso": ISO.get(team, ""), "color": KIT.get(team, INK), "group": group,
            "n_trades": len(tr), "wallets": len(w),
            "top10_flow": round(sum(vols[:10]) / tot * 100, 1)}


def main() -> int:
    cids = condition_ids()
    rows = []
    for team, grp in [(t, "fav") for t in FAVES] + [(t, "longshot") for t in LONGSHOTS]:
        if team in cids:
            r = analyze(team, cids[team], grp)
            if r:
                rows.append(r); print(f"  {team:13s} wallets={r['wallets']:5d} top10_flow={r['top10_flow']:5.1f}%")
    rows.sort(key=lambda r: -r["top10_flow"])
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.ONCHAIN = " + json.dumps({"teams": rows, "cap": CAP}) + ";\n")
    print(f"wrote {OUT}: {len(rows)} teams")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
