#!/usr/bin/env python3
"""Macro-contract calibration on Kalshi — the durable, institution-facing extension of xResidual.

The World Cup was a clean testbed; the durable value of prediction markets is macro/economic event
contracts (CPI, Fed, GDP), which the Fed/NBER now study as forecasters and where the institutional
volume lives. Cross-venue price discovery isn't available there (Polymarket doesn't run these; Kalshi
is the macro venue), so the right question for a single venue is the *signal-source* one institutions
actually ask: **are these markets calibrated?** When Kalshi's CPI/Fed/GDP markets said 70% a day out,
did the event happen ~70% of the time?

Method: pull every SETTLED market in the macro series, take each market's last-traded probability at a
fixed lead before resolution (default 24h, from daily candlesticks), pair it with the binary outcome,
and score calibration (Brier vs base-rate, log-loss, a reliability table). Threshold-ladder markets
(the CPI -0.4/-0.3/-0.2/... strikes) cluster within a single release, so the honest unit is the
*release*, not the market — reported both ways.

    python scripts/macro_calibration.py            # public Kalshi API, no auth needed for market data
    python scripts/macro_calibration.py --lead 168 # calibration a week out instead of a day
"""
from __future__ import annotations
import argparse
import datetime as dt
import math

import requests

K = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = ["KXCPI", "KXCPIYOY", "KXFED", "KXFEDDECISION", "KXGDP"]


def _ts(s: str) -> int:
    return int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def settled_markets(series: str) -> list:
    out, cursor = [], None
    for _ in range(6):                                   # page through settled history
        p = {"series_ticker": series, "status": "settled", "limit": 200}
        if cursor:
            p["cursor"] = cursor
        j = requests.get(f"{K}/markets", params=p, timeout=20).json()
        out += j.get("markets", [])
        cursor = j.get("cursor")
        if not cursor:
            break
    return out


def price_at_lead(series: str, m: dict, lead_s: int):
    """Last-traded prob `lead_s` before close (the market's forecast without the outcome). None if illiquid."""
    try:
        st, en = _ts(m["open_time"]), _ts(m["close_time"])
    except Exception:
        return None
    target = en - lead_s
    if target <= st:
        return None
    r = requests.get(f"{K}/series/{series}/markets/{m['ticker']}/candlesticks",
                     params={"start_ts": st, "end_ts": en, "period_interval": 1440}, timeout=20)
    if r.status_code != 200:
        return None
    best, best_dt = None, None
    for c in r.json().get("candlesticks", []):
        t = c.get("end_period_ts")
        if t is None or t > target:                      # strictly before the lead cut -> no lookahead
            continue
        px = (c.get("price") or {}).get("close_dollars")
        vol = float(c.get("volume_fp") or 0)
        if px is None or vol <= 0:                        # need an actual trade
            continue
        d = abs(t - target)
        if best_dt is None or d < best_dt:
            best, best_dt = float(px), d
    return best


def brier(ps, ys):
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps)


def logloss(ps, ys):
    return -sum(y * math.log(max(p, 1e-6)) + (1 - y) * math.log(max(1 - p, 1e-6))
               for p, y in zip(ps, ys)) / len(ps)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lead", type=float, default=24.0, help="hours before resolution to price the forecast")
    args = ap.parse_args()
    lead_s = int(args.lead * 3600)

    rows = []            # (series, release_key, p, y)
    for s in SERIES:
        for m in settled_markets(s):
            res = m.get("result")
            if res not in ("yes", "no"):
                continue
            p = price_at_lead(s, m, lead_s)
            if p is None or not (0.0 <= p <= 1.0):
                continue
            release = m.get("event_ticker") or m.get("ticker", "").rsplit("-", 1)[0]
            rows.append((s, release, p, 1 if res == "yes" else 0))

    if not rows:
        print("no priced settled macro markets found")
        return 1
    ps = [r[2] for r in rows]; ys = [r[3] for r in rows]
    base = sum(ys) / len(ys)
    releases = len({r[1] for r in rows})

    print("=" * 66)
    print(f"KALSHI MACRO CALIBRATION  ·  forecast {args.lead:.0f}h before resolution")
    print(f"  {len(rows)} settled threshold-markets across ~{releases} releases "
          f"({', '.join(sorted({r[0] for r in rows}))})")
    print(f"  base rate (yes): {base:.1%}")
    print("-" * 66)
    print(f"  Brier   market {brier(ps, ys):.4f}   vs base-rate {brier([base]*len(ys), ys):.4f}   "
          f"vs coin-0.5 {brier([0.5]*len(ys), ys):.4f}")
    print(f"  LogLoss market {logloss(ps, ys):.4f}   vs base-rate {logloss([base]*len(ys), ys):.4f}")
    skill = 1 - brier(ps, ys) / brier([base]*len(ys), ys)
    print(f"  Brier skill score vs base rate: {skill:+.1%}")
    print("-" * 66)
    print("  reliability (predicted -> realized):")
    edges = [0, .1, .3, .5, .7, .9, 1.01]
    for lo, hi in zip(edges, edges[1:]):
        b = [(p, y) for p, y in zip(ps, ys) if lo <= p < hi]
        if not b:
            continue
        mp = sum(p for p, _ in b) / len(b); fr = sum(y for _, y in b) / len(b)
        bar = "#" * round(fr * 20)
        print(f"    p[{lo:.1f},{hi:.1f})  n={len(b):3d}  pred {mp:.0%}  realized {fr:.0%}  {bar}")
    print("=" * 66)
    print("  NOTE: threshold-ladder markets cluster within a release, so the honest unit is the")
    print(f"  release (~{releases}), not the {len(rows)} markets — read the reliability shape, not a tight CI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
