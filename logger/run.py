#!/usr/bin/env python3
"""xResidual price logger entrypoint.

Modes:
  python run.py                              # one pass over all configured venues
  python run.py --loop 300                   # every 300s, drift-corrected, forever
  python run.py --venues polymarket,kalshi   # restrict to a subset of venues

Because The Odds API is quota-bound (see logger/README.md), the typical setup runs
TWO crons: the free feeds fast, the Odds API slow. For example:

  # free feeds every 5 min
  */5 * * * * cd /PATH/xResidual/logger && python3 run.py --venues polymarket,kalshi >> data/run.log 2>&1
  # odds api every 3 hours
  0 */3 * * * cd /PATH/xResidual/logger && python3 run.py --venues oddsapi >> data/run.log 2>&1
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import envtools
import snapshot
import storage

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _log(msg: str) -> None:
    print(f"[{storage.now_iso()}] {msg}", flush=True)


def one_pass(config: dict, env: dict, only) -> None:
    try:
        summary = snapshot.run_once(config, env, DATA_DIR, only=only)
        parts = [f"{v}: {s['ok']} ok / {s['errors']} err" for v, s in summary.items()]
        _log("snapshot — " + (", ".join(parts) if parts else "no matching markets configured"))
    except Exception as e:  # the loop must survive a bad pass
        _log(f"PASS FAILED (continuing): {type(e).__name__}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="xResidual price logger")
    ap.add_argument("--loop", type=int, metavar="SECONDS",
                    help="run forever, snapshotting every SECONDS (drift-corrected)")
    ap.add_argument("--venues", type=str, metavar="A,B",
                    help="comma-separated subset of venues (default: all configured)")
    ap.add_argument("--config", default=snapshot.CONFIG_DEFAULT,
                    help="path to config.json (default: ./config.json)")
    args = ap.parse_args()

    if not os.path.exists(args.config):
        _log(f"no config at {args.config} — copy config.example.json to config.json")
        return 1

    config = snapshot.load_config(args.config)
    env = envtools.load_env()
    only = [v.strip() for v in args.venues.split(",")] if args.venues else None

    if args.loop:
        _log(f"starting loop, interval={args.loop}s, venues={only or 'all'}, data_dir={DATA_DIR}")
        next_at = time.monotonic()
        while True:
            one_pass(config, env, only)
            next_at += args.loop
            sleep_for = max(0.0, next_at - time.monotonic())  # correct for pass duration
            if sleep_for == 0.0:
                next_at = time.monotonic()  # fell behind; reset schedule
            time.sleep(sleep_for)
    else:
        one_pass(config, env, only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
