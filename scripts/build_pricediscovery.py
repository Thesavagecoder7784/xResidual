#!/usr/bin/env python3
"""P5 price discovery: does the closing line beat the opening line?
    -> writeups/_pricediscovery_results.json + viz/market/_pricediscovery.js

Pre-registration P5 (secondary, genuine unknown): `pipeline.closing_line_wdl` at the last pre-kickoff
snapshot (the CLOSING line) vs the FIRST logged snapshot (the OPENING line), both de-vigged; the
multiclass Brier of each over resolved matches, pooled. PASS if closing Brier < opening Brier.

The 1X2 line is the bookmaker h2h consensus (venue `oddsapi`) — the only per-match win/draw/loss
quote — aggregated across books exactly as `closing_line_wdl` does (median of the overround-stripped
mids, renormalized to sum to 1, i.e. de-vigged). Opening and closing get identical treatment, so the
comparison is clean. Each fixture's OPENING is `closing_line_wdl` capped at that fixture's earliest
snapshot; its CLOSING is the same call capped at kickoff (`commence_time`), which excludes in-play.

Fork-forward: reads the frozen loaders + pipeline.closing_line_wdl only; edits nothing under xresidual/.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import data_fixtures, pipeline, trajectory  # noqa: E402

LOGGER = os.path.join(ROOT, "logger", "data")
OUT_JS = os.path.join(ROOT, "viz", "market", "_pricediscovery.js")
RESULTS = os.path.join(ROOT, "writeups", "_pricediscovery_results.json")
VENUE = "oddsapi"


def _outcome_idx(s1, s2) -> int:
    return 0 if s1 > s2 else (1 if s1 == s2 else 2)        # home / draw / away


def _brier(wdl: dict, oc: int) -> float:
    p = np.array([wdl["p_home"], wdl["p_draw"], wdl["p_away"]], float)
    return float(np.sum((p - np.eye(3)[oc]) ** 2))


def main() -> int:
    fx = data_fixtures.load_fixtures()
    snaps = trajectory.load_snapshots(LOGGER)
    if snaps.empty:
        print("no snapshots; nothing to grade")
        return 0
    s = snaps[(snaps["venue"] == VENUE) & (snaps.get("market_type") == "h2h")
              & (snaps["outcome"] != "__error__")].copy()
    s["ts_utc"] = pd.to_datetime(s["ts_utc"], utc=True, errors="coerce")
    commence = pd.to_datetime(s.get("commence_time"), utc=True, errors="coerce")
    s["commence_time"] = commence
    teams_per_market = s.groupby("market_id")["outcome"].agg(set)

    rows = []
    for f in fx[fx["played"]].itertuples(index=False):
        t1, t2 = f.team1, f.team2
        ids = [mid for mid, outs in teams_per_market.items() if {t1, t2} <= outs]
        if not ids:
            continue
        sub = s[s["market_id"].isin(ids)]
        if sub.empty:
            continue
        open_cap = sub["ts_utc"].min()
        kick = sub["commence_time"].dropna().max()
        if pd.isna(kick):                                  # no commence_time -> cap at last quote
            kick = sub["ts_utc"].max()
        opening = pipeline.closing_line_wdl(sub, t1, t2, kickoff=open_cap, venue=VENUE)
        closing = pipeline.closing_line_wdl(sub, t1, t2, kickoff=kick, venue=VENUE)
        if opening is None or closing is None:
            continue
        oc = _outcome_idx(f.score1, f.score2)
        rows.append({"match": f"{t1} vs {t2}", "outcome": oc,
                     "brier_open": _brier(opening, oc), "brier_close": _brier(closing, oc),
                     "moved": opening != closing})

    n = len(rows)
    payload = {"n": n, "venue": VENUE}
    if n:
        bo = float(np.mean([r["brier_open"] for r in rows]))
        bc = float(np.mean([r["brier_close"] for r in rows]))
        payload.update({"brier_open": round(bo, 4), "brier_close": round(bc, 4),
                        "improvement": round(bo - bc, 4),
                        "pass": bool(bc < bo),
                        "n_moved": sum(1 for r in rows if r["moved"]),
                        "per_match": rows})
    os.makedirs(os.path.dirname(OUT_JS), exist_ok=True)
    with open(OUT_JS, "w") as fjs:
        fjs.write("window.PRICEDISCOVERY = " + json.dumps(payload) + ";\n")
    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    json.dump(payload, open(RESULTS, "w"), indent=2)

    if n:
        print(f"P5 price discovery ({n} resolved, {payload['n_moved']} moved): "
              f"opening Brier {payload['brier_open']} -> closing {payload['brier_close']} "
              f"({'PASS: closing sharper' if payload['pass'] else 'FAIL: no sharpening'})")
    else:
        print("P5: no resolved matches with both an opening and closing h2h line yet")
    print(f"wrote {os.path.relpath(RESULTS, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
