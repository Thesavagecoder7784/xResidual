#!/usr/bin/env python3
"""v2 dashboard: the advance / champion / group-win / reach forecasts with the v2 temperature
calibration applied, so the model-vs-market edges reflect the model AFTER fixing the 2018/2022
tail-overconfidence (T fit out-of-sample; see v2_calibrate). This is where the favourite-longshot
mirage was: the raw board overstated the edges because the model was overconfident at the extremes.

Parallel to build_matches_v2 for the group page; v1 (build_dashboard.py) stays untouched. Emits
docs/data/dashboard_v2.js (window.DASH_V2). A calibrated current snapshot (forecasts + edges +
title race); CLV/calibration grading stays on v1's pre-committed ledger.
  python scripts/build_dashboard_v2.py
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from prediction_board import model_probs, market_prices, build_forecasts  # noqa: E402
from v2_calibrate import scale_binary, temperature  # noqa: E402

OUT = os.path.join(ROOT, "docs", "data", "dashboard_v2.js")
MKT_LABEL = {"champion": "Champion", "advance": "Advance", "group_win": "Win group",
             "reach_qf": "Reach QF", "reach_sf": "Reach SF", "reach_final": "Reach Final"}


def main() -> int:
    T = temperature()
    print(f"building v2 (T={T:.3f}-calibrated) dashboard ...")
    sim, reach = model_probs()
    # Temperature-scale every market, then RENORMALIZE each to its coherent total. Independent
    # binary scaling alone breaks the market's sum constraint: T>1 pushes every sub-50% longshot
    # UP toward 50%, so on markets where most teams are longshots (champion, reach QF/SF/Final)
    # the scaled probabilities sum to far more than the market can (champion to ~280%, reach-final
    # to ~440%) and the "edges" become an artifact of that inflation. Renormalizing per market
    # restores a valid distribution while keeping the cooling — favourites flatten toward the field.
    #   pick-one markets (champion, group winner): softmax(log p / T), so each sums to exactly 1
    #     (1 champion overall; 1 winner PER GROUP);
    #   top-k binaries (advance, reach QF/SF/Final): scale_binary, renormalized to the sim's own
    #     pre-calibration count (the coherent number of slots the sim implies).
    from collections import defaultdict

    def _softmax_pow(items):                         # pick-one: p^(1/T) renormalized to sum 1
        q = {k: max(p, 1e-12) ** (1.0 / T) for k, p in items.items()}
        s = sum(q.values()) or 1.0
        return {k: v / s for k, v in q.items()}

    def _binary_renorm(items):                       # top-k: scale_binary, renorm to raw count
        q = {k: scale_binary(p, T) for k, p in items.items()}
        s = sum(q.values()) or 1.0
        return {k: v * (sum(items.values()) / s) for k, v in q.items()}

    # champion: one winner across the whole field -> sum to 1
    champ = _softmax_pow({t: reach[t]["win"] / 100.0 for t in reach})
    for t in reach:
        reach[t]["win"] = champ[t] * 100.0
    # group winner: one winner WITHIN each group -> each group sums to 1
    by_group = defaultdict(dict)
    for t, s in sim.items():
        by_group[s["group"]][t] = s["p1"]
    for members in by_group.values():
        for t, v in _softmax_pow(members).items():
            sim[t]["p1"] = v
    # advance + reach QF/SF/Final: top-k binaries, renormalized to the sim's implied count
    for t, v in _binary_renorm({t: sim[t]["padv"] for t in sim}).items():
        sim[t]["padv"] = v
    for k in ("qf", "sf", "final"):
        for t, v in _binary_renorm({t: reach[t][k] / 100.0 for t in reach}).items():
            reach[t][k] = v * 100.0

    pm = market_prices()
    rows = build_forecasts(sim, reach, pm)        # model-vs-market on the CALIBRATED probs
    forecasts = [{"market": r["market"], "market_label": MKT_LABEL.get(r["market"], r["market"]),
                  "team": r["team"], "model": round(r["model"] * 100, 1),
                  "price": round(r["mkt_at_forecast"] * 100, 1), "edge": r["edge_pp"]} for r in rows]
    title = sorted([f for f in forecasts if f["market"] == "champion"], key=lambda f: -f["model"])[:12]
    calls = sorted(forecasts, key=lambda f: -abs(f["edge"]))[:20]

    payload = {"asof": datetime.now(timezone.utc).isoformat(), "version": "v2",
               "temperature": round(T, 3), "n_forecasts": len(forecasts),
               "markets": list(MKT_LABEL.items()), "forecasts": forecasts,
               "title_race": title, "biggest_calls": calls,
               "note": "v2: temperature-calibrated (T fit on 2018/2022 out-of-sample) to fix the "
                       "tail-overconfidence that inflated the raw model-vs-market edges"}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.DASH_V2 = " + json.dumps(payload, separators=(",", ":")) + ";\n")
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(forecasts)} calibrated forecasts (T={T:.2f}); "
          f"max |edge| now {max(abs(f['edge']) for f in forecasts):.1f}pp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
