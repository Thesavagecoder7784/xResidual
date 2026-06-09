#!/usr/bin/env python3
"""Backtest the goal-overreaction fade on captured in-play data -> _overreaction.js.

    python scripts/overreaction_run.py

Loads the ws-events captures + the ws-pairs sidecars, reconstructs each contract's mid
on each venue, auto-detects goal shocks, and fades them
(xresidual.ws_events.overreaction_backtest). No-op until a match has been captured.

The documented edge (Choi & Hui; "Role of Surprise") is ~2-3% per trade betting ~2 min
after a surprising goal, reverting within ~6 min. This tests whether it still survives on
2026 World Cup prediction markets, net of modeled costs. Honest by construction: if the
edge is gone (arbed away), the summary says so.
"""
from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import ws_events as we  # noqa: E402

DATA = os.path.join(ROOT, "logger", "data")
OUT = os.path.join(ROOT, "viz", "model", "_overreaction.js")


def main() -> int:
    cap = we.latest_capture(DATA)            # events + pairs from the SAME capture
    events = we.load_ws_events(DATA, capture=cap)
    all_trades, per_contract = [], []
    if events:
        for pr in we.load_pairs(DATA, capture=cap):
            for venue, fn, key in (("kalshi", we.kalshi_mid_series, "kalshi"),
                                   ("polymarket", we.polymarket_mid_series, "poly")):
                mid_id = pr.get(key)
                if not mid_id:
                    continue
                series = fn(events, mid_id)
                if len(series) < 10:
                    continue
                res = we.overreaction_backtest(series)
                if res["summary"]["n"]:
                    all_trades += res["trades"]
                    per_contract.append({"label": pr.get("label"), "venue": venue,
                                         **res["summary"]})

    payload = {
        "summary": we._ovr_summary(all_trades),
        "per_contract": per_contract,
        "params": {"entry_s": 120, "exit_s": 360, "min_jump": 0.04, "cost_pp": 0.5},
        "note": "fade goal overreaction; paper, net of modeled cost; live test of a "
                "documented ~2-3%/trade edge",
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.OVERREACTION = " + json.dumps(payload) + ";\n")

    s = payload["summary"]
    if not events:
        print("no ws-events captured yet; wrote empty _overreaction.js (ready for kickoff)")
    else:
        print(f"contracts={len(per_contract)} trades={s['n']} total={s['total_pnl_pp']}pp "
              f"hit={s['hit_rate']} mean_revert={s['mean_reverted_pp']}pp "
              f"per-trade-sharpe={s['per_trade_sharpe']}")
    print(f"wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
