#!/usr/bin/env python3
"""Emit docs/data/dashboard.json — the data the live dashboard site loads.

    python scripts/build_dashboard.py

A browser can't hit Kalshi/Polymarket directly (auth + CORS + geofencing), so the site is a
static dashboard regenerated each refresh loop and deployed (GitHub Pages from docs/). This
assembles everything the page needs into one JSON: every current model-vs-market forecast,
the CLV per forecast (vs the first committed price in the ledger), the title race, the
biggest calls, and the calibration summary (fills in as markets resolve). Reuses the
prediction-board internals so there is one source of truth.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from prediction_board import (model_probs, market_prices, build_forecasts,  # noqa: E402
                              _resolve_outcomes, LEDGER)

OUT = os.path.join(ROOT, "docs", "data", "dashboard.js")  # JS global, not JSON: loads via
# <script src> so the page works opened locally (file://) AND on GitHub Pages — fetch() is
# blocked on file:// and was the "error fetching data".
MKT_LABEL = {"champion": "Champion", "advance": "Advance", "group_win": "Win group",
             "reach_qf": "Reach QF", "reach_sf": "Reach SF", "reach_final": "Reach Final"}


def main() -> int:
    print("building dashboard data (sim + live market) ...")
    sim, reach = model_probs()
    pm = market_prices()
    rows = build_forecasts(sim, reach, pm)            # current model vs current market

    led = [json.loads(l) for l in open(LEDGER, encoding="utf-8")] if os.path.exists(LEDGER) else []
    # earliest committed price per (market, team) -> the CLV reference
    commit = {}
    for e in led:
        k = (e["market"], e["team"])
        if k not in commit or e["batch"] < commit[k]["batch"]:
            commit[k] = {"price": e["mkt_at_forecast"], "model": e["model"], "batch": e["batch"]}
    outc = _resolve_outcomes(led) if led else {}
    resolved = {}
    for i, e in enumerate(led):
        if outc.get(i) is not None:
            resolved[(e["market"], e["team"])] = outc[i]

    forecasts = []
    for r in rows:
        k = (r["market"], r["team"])
        c = commit.get(k)
        clv = None
        if c is not None:
            clv = round((r["mkt_at_forecast"] - c["price"]) * (1 if c["model"] > c["price"] else -1) * 100, 2)
        forecasts.append({"market": r["market"], "market_label": MKT_LABEL.get(r["market"], r["market"]),
                          "team": r["team"], "model": round(r["model"] * 100, 1),
                          "price": round(r["mkt_at_forecast"] * 100, 1), "edge": r["edge_pp"],
                          "clv": clv, "outcome": resolved.get(k)})

    title = sorted([f for f in forecasts if f["market"] == "champion"], key=lambda f: -f["model"])[:12]
    # Biggest calls EXCLUDE the advance-to-R32 layer: there the model systematically disagrees with
    # BOTH bookmakers and Polymarket (the mispricing "our model, not the market" verdict — the
    # squad-value / minnow-advancement bias), so its largest "edges" are our model's bias, not real
    # calls. Lead the board with the markets where the model-vs-market gap is genuine (reach-QF/SF
    # favourite overpricing, group winner), not the layer we'd never actually trade.
    calls = sorted([f for f in forecasts if f["market"] != "advance"], key=lambda f: -abs(f["edge"]))[:20]

    clv_vals = [f["clv"] for f in forecasts if f["clv"] is not None]
    clv_summary = {"n": len(clv_vals),
                   "positive_pct": round(100 * sum(1 for v in clv_vals if v > 0) / len(clv_vals)) if clv_vals else None,
                   "mean": round(sum(clv_vals) / len(clv_vals), 2) if clv_vals else None}

    pairs = [(f["model"] / 100, f["outcome"]) for f in forecasts if f["outcome"] is not None]
    calib = {"status": "pending", "n": len(pairs)}
    if pairs:
        import numpy as np
        p = np.array([a for a, _ in pairs]); y = np.array([b for _, b in pairs], dtype=float)
        brier = float(np.mean((p - y) ** 2))
        eps = 1e-12
        ll = float(np.mean(-(y * np.log(np.clip(p, eps, 1)) + (1 - y) * np.log(np.clip(1 - p, eps, 1)))))
        base = float(y.mean())
        rel = []
        for lo in (0.0, 0.2, 0.4, 0.6, 0.8):
            m = (p >= lo) & (p < lo + 0.2)
            if m.sum():
                rel.append({"bucket": f"{int(lo*100)}-{int(lo*100)+20}", "pred": round(float(p[m].mean()) * 100, 1),
                            "actual": round(float(y[m].mean()) * 100, 1), "n": int(m.sum())})
        calib = {"status": "live", "n": len(pairs), "brier": round(brier, 4), "logloss": round(ll, 4),
                 "brier_skill": round(1 - brier / (base * (1 - base) + eps), 3), "reliability": rel}

    payload = {"asof": datetime.now(timezone.utc).isoformat(), "n_forecasts": len(forecasts),
               "markets": list(MKT_LABEL.items()), "forecasts": forecasts,
               "title_race": title, "biggest_calls": calls,
               "clv": clv_summary, "calibration": calib,
               "n_batches": len(set(e["batch"] for e in led))}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.DASH = " + json.dumps(payload, separators=(",", ":")) + ";\n")
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(forecasts)} forecasts · "
          f"CLV {clv_summary['positive_pct']}% pos · calibration {calib['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
