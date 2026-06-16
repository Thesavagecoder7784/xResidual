#!/usr/bin/env python3
"""Smart money or loud money? -> viz/market/_smartmoney.js  (CROSS: on-chain x model).

    python scripts/build_smartmoney.py

Card #2 of the "cross two ideas" set. The money map showed longshots out-trade the
favourites in $ volume on Polymarket. This asks whether that concentrated money is
INFORMED, by crossing two quantities per team:

  * MARKET (on-chain) -- Polymarket settles on Polygon, so every title-market trade
    carries a wallet. top10_flow = share of a team's title-market trading done by its 10
    busiest wallets (concentration); wallets = how many distinct accounts (breadth).

  * MODEL (edge) -- the model's edge to ADVANCE from the live dashboard (model - market
    price, pp). Positive = the model sees value; negative = the model fades it.

The cross: concentration (x) vs advance edge (y). If concentrated "conviction" money were
smart, it would sit where the model also sees value. Instead the whale-concentrated
longshots are the ones the model most fades -- loud money, not smart money. A 'whale' can
be a market-maker, not a punter, so read concentration descriptively.
"""
from __future__ import annotations

import json
import os
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from build_onchain import condition_ids, trades  # noqa: E402  (reuse the proven pull)
from pull_forecast_data import ISO, KIT, INK  # noqa: E402

OUT = os.path.join(ROOT, "viz", "market", "_smartmoney.js")
DASH = os.path.join(ROOT, "docs", "data", "dashboard.js")
CAP = 2000

# a spread across the title-odds spectrum: contenders, outsiders, and pure longshots
TEAMS = ["Spain", "France", "England", "Argentina", "Brazil", "Portugal", "Germany",
         "Netherlands", "USA", "Mexico", "Morocco", "Senegal", "Ecuador",
         "Saudi Arabia", "New Zealand", "Uzbekistan", "Curaçao", "Qatar", "Jordan", "Panama"]


def edges():
    """{team: (adv_edge, champ_price)} from the live dashboard."""
    raw = open(DASH, encoding="utf-8").read().split("=", 1)[1].rstrip().rstrip(";")
    d = json.loads(raw)
    adv = {f["team"]: f["edge"] for f in d["forecasts"] if f["market"] == "advance"}
    champ = {f["team"]: f["price"] for f in d["forecasts"] if f["market"] == "champion"}
    return adv, champ


def analyze(cid):
    tr = trades(cid, cap=CAP)
    if not tr:
        return None
    w = {}
    for r in tr:
        w[r["proxyWallet"]] = w.get(r["proxyWallet"], 0.0) + float(r["size"])
    vols = sorted(w.values(), reverse=True); tot = sum(vols) or 1
    return {"n_trades": len(tr), "wallets": len(w), "top10_flow": round(sum(vols[:10]) / tot * 100, 1)}


def tier(champ_price):
    if champ_price >= 3:
        return "contender"
    if champ_price >= 0.3:
        return "outsider"
    return "longshot"


def main() -> int:
    cids = condition_ids()
    adv, champ = edges()
    rows = []
    for t in TEAMS:
        if t not in cids or t not in adv:
            print(f"  {t}: no market/onchain match, skip"); continue
        a = analyze(cids[t])
        if not a:
            print(f"  {t}: no trades, skip"); continue
        cp = champ.get(t, 0.0)
        rows.append({"team": t, "iso": ISO.get(t, ""), "color": KIT.get(t, INK),
                     "tier": tier(cp), "adv_edge": round(adv[t], 1), "champ_price": cp,
                     **a})
        print(f"  {t:14} conc={a['top10_flow']:5.1f}%  wallets={a['wallets']:5d}  adv_edge={adv[t]:+6.1f}  ({tier(cp)})")
    rows.sort(key=lambda r: r["top10_flow"])
    payload = {"teams": rows, "cap": CAP}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.SMART = " + json.dumps(payload) + ";\n")
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(rows)} teams")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
