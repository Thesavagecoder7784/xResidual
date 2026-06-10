#!/usr/bin/env python3
"""Cross-venue arbitrage scan: Kalshi vs Polymarket, executable prices only.

    python scripts/scan_arbitrage.py

Unlike build_basis.py (which devigs MIDS to compare *beliefs*), this uses the raw
BID/ASK you could actually trade against, and nets out Kalshi's trading fee, to test
for a locked, outcome-independent profit. For the SAME contract on both venues
(e.g. "Brazil wins the World Cup" = Polymarket token vs Kalshi KXMENWORLDCUP-26-BRA),
two directions can lock a profit:

    A) buy Polymarket @ poly_ask, sell Kalshi @ kalshi_bid   -> edge = kalshi_bid - poly_ask
    B) buy Kalshi @ kalshi_ask, sell Polymarket @ poly_bid   -> edge = poly_bid - kalshi_ask

Both legs settle on the identical event, so the position is fully hedged regardless of
result. Frictions modelled: Kalshi's fee  ~ 0.07 * p * (1-p) per contract (Polymarket
charges no trading fee). NOT modelled (so treat any hit as an upper bound): top-of-book
depth, withdrawal/KYC/transfer cost, and capital locked until the contract resolves
(the winner market doesn't settle until ~mid-July).

PAPER ONLY. F-1 visa => no real-money trading; this is a market-efficiency measurement.

Reads the latest bid/ask per team/venue from the logged snapshots. Match markets are
not scanned here: Polymarket per-match books only exist in the live capture files, not
the 30-min snapshots, so cross-venue match arb is a during-match job (see ws_capture).
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

DATA_GLOB = os.path.join(ROOT, "logger", "data", "snapshots-*.jsonl")


def kalshi_fee(p: float) -> float:
    """Kalshi trading fee per contract, ~$0.07 * p * (1-p) (symmetric in p/1-p, so it
    applies whether the Kalshi leg is a buy at the ask or a sell = buy-NO at 1-bid)."""
    return 0.07 * p * (1.0 - p)


def latest_winner_quotes(rows, venue):
    """canonical team -> {'bid','ask','ts'} latest winner quote for `venue`."""
    best = {}
    for q in rows:
        if q.get("venue") != venue:
            continue
        if q.get("extra", {}).get("market_type") != "winner":
            continue
        if q.get("outcome") in (None, "__error__"):
            continue
        t = wc2026_teams.canonical(q["outcome"])
        if t not in wc2026_teams.WC2026_TEAMS:
            continue
        ts = q.get("ts_utc", "")
        if t not in best or ts > best[t]["ts"]:
            best[t] = {"bid": q.get("bid"), "ask": q.get("ask"), "ts": ts}
    return best


def main() -> int:
    rows = []
    files = [f for f in sorted(glob.glob(DATA_GLOB)) if "backfill" not in f]
    for fn in files:  # latest-per-team below picks recency, so loading all dated files is safe
        with open(fn, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    asof = max((q.get("ts_utc", "") for q in rows), default="")
    pm = latest_winner_quotes(rows, "polymarket")
    ka = latest_winner_quotes(rows, "kalshi")
    common = sorted(set(pm) & set(ka))
    print(f"asof {asof} | polymarket {len(pm)} kalshi {len(ka)} | {len(common)} teams on both\n")

    def val(x):
        return x if isinstance(x, (int, float)) and x is not None and x > 0 else None

    results = []
    for t in common:
        pa, pb = val(pm[t]["ask"]), val(pm[t]["bid"])
        ka_, kb = val(ka[t]["ask"]), val(ka[t]["bid"])
        cands = []
        if pa is not None and kb is not None:                       # buy PM, sell Kalshi
            cands.append(("buy PM / sell KA", kb - pa, kb - pa - kalshi_fee(kb)))
        if ka_ is not None and pb is not None:                      # buy Kalshi, sell PM
            cands.append(("buy KA / sell PM", pb - ka_, pb - ka_ - kalshi_fee(ka_)))
        if not cands:
            continue
        leg, gross, net = max(cands, key=lambda c: c[2])
        results.append({"team": t, "leg": leg, "gross": gross, "net": net,
                        "pm_bid": pb, "pm_ask": pa, "ka_bid": kb, "ka_ask": ka_})

    results.sort(key=lambda r: -r["net"])
    arbs = [r for r in results if r["net"] > 0]

    def fmt(r):
        px = f"PM {r['pm_bid']}/{r['pm_ask']}  KA {r['ka_bid']}/{r['ka_ask']}"
        return (f"  {r['team']:<16} net {r['net']*100:+6.2f}c  gross {r['gross']*100:+6.2f}c  "
                f"[{r['leg']}]  {px}")

    if arbs:
        print(f"*** {len(arbs)} net-positive (after Kalshi fee) ***")
        for r in arbs:
            print(fmt(r))
    else:
        print("No net-positive arbitrage after fees.")
    print("\nTightest 12 (closest to crossing, incl. negatives):")
    for r in results[:12]:
        print(fmt(r))

    pos_gross = [r for r in results if r["gross"] > 0]
    print(f"\nsummary: {len(results)} comparable teams | {len(pos_gross)} cross gross>0 | "
          f"{len(arbs)} survive fees | best net {max((r['net'] for r in results), default=0)*100:+.2f}c "
          f"| median net {sorted(r['net'] for r in results)[len(results)//2]*100:+.2f}c"
          if results else "no comparable teams")
    print("PAPER ONLY (F-1). Gross ignores depth, transfer cost, and month-long capital lockup.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
