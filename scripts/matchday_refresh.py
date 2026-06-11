#!/usr/bin/env python3
"""Matchday-aware refresh gate — runs the full refresh after each matchday's games finish.

    python scripts/matchday_refresh.py            # refresh if a matchday just settled (or heartbeat)
    python scripts/matchday_refresh.py --dry-run   # show the decision, run nothing
    python scripts/matchday_refresh.py --force      # refresh now regardless

Wired to launchd (com.xresidual.render) every ~30 min. It fires scripts/refresh_daily.sh only
when a matchday has just completed (the day's last kickoff + a buffer), or at least every
HEARTBEAT_H hours so results that land late on the feed still get picked up — so it's cheap
between matchdays and prompt right after one. State in logger/data/last-refresh.json.

(The results feed lags kickoff by ~1-2 days, so a matchday's *scores* may only condition the
model on a later run; this gate makes the site refresh promptly regardless, and re-runs catch
the scores when the feed has them.)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from match_scheduler import kickoff_utc  # noqa: E402

FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
REFRESH = os.path.join(ROOT, "scripts", "refresh_daily.sh")
STATE = os.path.join(ROOT, "logger", "data", "last-refresh.json")
BUFFER_H = 3.0        # a day's games are done ~3h after the last kickoff
HEARTBEAT_H = 12.0    # refresh at least this often regardless (catch late-landing results)


def settle_times():
    """One 'matchday settle' instant per fixture date: that day's last kickoff + buffer."""
    fx = pd.read_csv(FIXTURES)
    last = {}
    for r in fx.itertuples(index=False):
        ko = kickoff_utc(r.date, r.time)
        if ko is None:
            continue
        last[r.date] = max(ko, last.get(r.date, ko))
    return sorted(t + timedelta(hours=BUFFER_H) for t in last.values())


def _load():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    dry = "--dry-run" in sys.argv
    force = "--force" in sys.argv
    now = datetime.now(timezone.utc)
    st = _load()
    done = set(st.get("done", []))
    settles = settle_times()
    due = [s.isoformat() for s in settles if s <= now and s.isoformat() not in done]
    last = st.get("last_refresh")
    last_dt = datetime.fromisoformat(last) if last else None
    heartbeat = last_dt is None or (now - last_dt) >= timedelta(hours=HEARTBEAT_H)
    reason = "forced" if force else ("matchday settled" if due else ("heartbeat" if heartbeat else None))

    if reason is None:
        nxt = next((s for s in settles if s > now), None)
        mins = int((nxt - now).total_seconds() / 60) if nxt else None
        print(f"[{now:%Y-%m-%d %H:%M}Z] no refresh due"
              + (f"; next matchday settles in {mins // 60}h{mins % 60:02d}m" if nxt else "; no upcoming matchdays"))
        return 0

    print(f"[{now:%Y-%m-%d %H:%M}Z] refresh due ({reason})"
          + (f"; {len(due)} matchday(s) settled" if due else "") + (" [DRY-RUN]" if dry else ""))
    if dry:
        return 0
    subprocess.run(["bash", REFRESH], cwd=ROOT)
    st["last_refresh"] = now.isoformat()
    st["done"] = sorted(done | set(due))
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)
    print(f"[{now:%H:%M}Z] refresh complete; state saved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
