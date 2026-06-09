#!/usr/bin/env python3
"""Run the cross-venue convergence forward-test and grow the paper track record.

    python scripts/forwardtest_run.py

Reads the logged snapshots, simulates the convergence rule (xresidual/forwardtest.py),
appends any newly-closed paper trades to logger/data/paper-trades.jsonl (append-only,
deduped by team+entry time), and writes viz/market/_forwardtest.js for the card.

Run it on a schedule (e.g. daily). Only *converged*/*expired* trades are persisted;
still-open positions at the data edge are transient and not logged, so the file is a
consistent, append-only forward record.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import forwardtest, trajectory  # noqa: E402

LOGGER_DATA = os.path.join(ROOT, "logger", "data")
TRADES_LOG = os.path.join(LOGGER_DATA, "paper-trades.jsonl")
OUT = os.path.join(ROOT, "viz", "market", "_forwardtest.js")


def _key(t: dict) -> str:
    return f"{t['team']}|{t['entry_ts']}"


def main() -> int:
    snaps = trajectory.load_snapshots(LOGGER_DATA)
    if snaps.empty:
        print("no snapshots logged yet; nothing to do")
        return 0
    div = forwardtest.divergence_series(snaps)
    res = forwardtest.run_convergence(div)

    # persist only genuinely-closed trades, deduped (append-only forward record)
    existing = set()
    if os.path.exists(TRADES_LOG):
        with open(TRADES_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    existing.add(_key(json.loads(line)))
    closed = [t for t in res["trades"] if t["reason"] != "eod"]
    new = [t for t in closed if _key(t) not in existing]
    if new:
        with open(TRADES_LOG, "a", encoding="utf-8") as f:
            for t in new:
                f.write(json.dumps(t) + "\n")
            f.flush()
            os.fsync(f.fileno())

    # recompute summary/equity from the *persisted* record (the disclosed track record)
    persisted = []
    if os.path.exists(TRADES_LOG):
        with open(TRADES_LOG, encoding="utf-8") as f:
            persisted = [json.loads(line) for line in f if line.strip()]
    payload = {
        "summary": forwardtest._summary(persisted),
        "equity": forwardtest._equity(persisted),
        "n_open": len([t for t in res["trades"] if t["reason"] == "eod"]),
        "params": {"entry_pp": forwardtest.ENTRY * 100, "exit_pp": forwardtest.EXIT * 100,
                   "cost_pp": forwardtest.COST * 100, "max_hold": forwardtest.MAX_HOLD},
        "note": "paper / out-of-sample; long cheap venue, short rich, modeled costs",
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.FORWARDTEST = " + json.dumps(payload) + ";\n")

    s = payload["summary"]
    print(f"persisted trades={s['n_trades']} total={s['total_pnl_pp']}pp "
          f"hit={s['hit_rate']} per-trade-sharpe={s['per_trade_sharpe']} "
          f"(+{len(new)} new this run, {payload['n_open']} open)")
    print(f"wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
