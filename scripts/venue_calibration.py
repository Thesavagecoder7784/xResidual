#!/usr/bin/env python3
"""Grade the VENUES, not just the model.

Per-venue calibration of every prediction venue we capture (Polymarket, Kalshi, and the
bookmaker close) against realised outcomes, scored on each venue's CLOSING price — the last
captured snapshot BEFORE the market resolved — with Brier, log-loss, and a reliability read.

This is the differentiated half of xResidual: simultaneous tick capture of two venues on the
same events lets us ask "which crowd was sharpest, and where do the regulated-USD and
crypto-global books disagree?" head-to-head. Almost no one else has the data to answer it.

PENDING until markets resolve (group-stage markets ~Jun 27, knockout rounds after). It prints
what it can as outcomes land, and reads the captured snapshot history
(logger/data/snapshots-*.jsonl) — richest on the always-on VM. PAPER / research only.
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import calibration, wc2026_teams as W  # noqa: E402
import prediction_board as PB  # noqa: E402

SNAP_GLOB = os.path.join(ROOT, "logger", "data", "snapshots-*.jsonl")
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
OUT = os.path.join(ROOT, "docs", "data", "venue_calibration.js")

# captured snapshot extra.market_type -> the resolver's market key
MARKET_MAP = {"winner": "champion", "champion": "champion", "advance": "advance",
              "group_winner": "group_win", "group_win": "group_win", "group": "group_win",
              "qf": "reach_qf", "reach_qf": "reach_qf", "quarterfinal": "reach_qf",
              "sf": "reach_sf", "reach_sf": "reach_sf", "semifinal": "reach_sf",
              "final": "reach_final", "reach_final": "reach_final"}


def _resolution_cutoffs() -> dict:
    """Latest timestamp at which a market's CLOSING price is still pre-resolution, per market.
    Group markets close when the group stage ends; reach-round markets when that round starts;
    champion at the final. Using a pre-resolution cutoff keeps the closing line from being the
    post-settlement price (which would be circular)."""
    fx = pd.read_csv(FIXTURES)
    fx["date"] = pd.to_datetime(fx["date"]).dt.tz_localize("UTC")   # snapshots are tz-aware UTC
    grp_end = fx[fx["group"].astype(str).str.startswith("Group")]["date"].max()
    ko = fx[~fx["group"].astype(str).str.startswith("Group")]
    rnd = lambda lbl: ko[ko["round"].astype(str) == lbl]["date"].min()
    return {"advance": grp_end, "group_win": grp_end, "reach_qf": rnd("Quarter-final"),
            "reach_sf": rnd("Semi-final"), "reach_final": rnd("Final"), "champion": rnd("Final")}


def closing_prices(cutoffs: dict) -> dict:
    """{venue: {(market, canon_team): closing_mid}} — the last snapshot strictly before the
    market's resolution cutoff, per venue."""
    latest: dict = {}                          # (venue, market, team) -> (ts, mid)
    for f in glob.glob(SNAP_GLOB):
        for line in open(f, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            mt = MARKET_MAP.get(str((r.get("extra") or {}).get("market_type", "")).lower())
            mid, ts = r.get("mid"), r.get("ts_utc", "")
            if mt is None or mid is None or not ts:
                continue
            cut = cutoffs.get(mt)
            if cut is not None and pd.to_datetime(ts, utc=True) >= cut:
                continue                        # past the closing line -> skip (avoid circularity)
            key = (r.get("venue"), mt, W.canonical(r.get("outcome", "")))
            if key not in latest or ts > latest[key][0]:
                latest[key] = (ts, float(mid))
    venues: dict = {}
    for (venue, mt, team), (_ts, mid) in latest.items():
        venues.setdefault(venue, {})[(mt, team)] = mid
    return venues


def main() -> int:
    venues = closing_prices(_resolution_cutoffs())
    if not venues:
        print("no captured snapshots yet — venue calibration is PENDING (snapshot history "
              "lives on the VM; run there or `make pull` first).")
        return 0

    pairs = sorted({k for v in venues.values() for k in v})
    pseudo = [{"market": m, "team": t, "model": 0.5, "mkt_at_forecast": 0.5} for (m, t) in pairs]
    out = PB._resolve_outcomes(pseudo)
    outcome = {pairs[i]: out.get(i) for i in range(len(pairs))}
    n_res = sum(1 for o in outcome.values() if o is not None)
    print(f"venues: {sorted(venues)} · {len(pairs)} market-team pairs captured · {n_res} resolved")
    if n_res == 0:
        print("nothing resolved yet — fires once results land (group markets ~Jun 27).")
        return 0

    rows = []
    for venue, prices in sorted(venues.items()):
        p, y = [], []
        for k, mid in prices.items():
            o = outcome.get(k)
            if o is not None:
                p.append(mid); y.append(float(o))
        if len(p) < 10:
            print(f"  {venue:12} only {len(p)} resolved — skip until more land")
            continue
        p, y = np.array(p), np.array(y)
        brier = calibration.brier_score(p, y)
        logloss = float(np.mean(-(y * np.log(np.clip(p, 1e-9, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-9, 1)))))
        rows.append({"venue": venue, "n": len(p), "brier": round(brier, 4), "logloss": round(logloss, 4)})
        print(f"  {venue:12} n={len(p):<4} Brier {brier:.4f}  log-loss {logloss:.4f}")

    if rows:
        rows.sort(key=lambda r: r["brier"])
        payload = {"asof": pd.Timestamp.utcnow().isoformat(), "venues": rows,
                   "sharpest": rows[0]["venue"]}
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as fh:
            fh.write("window.VENUECAL = " + json.dumps(payload, separators=(",", ":")) + ";\n")
        print(f"sharpest by Brier: {rows[0]['venue']} · wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
