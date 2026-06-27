#!/usr/bin/env python3
"""Matchday-aware refresh gate — runs a full refresh right after each matchday's games finish.

    python scripts/matchday_refresh.py --target vm       # VM: publish results at matchday end
    python scripts/matchday_refresh.py --target laptop    # laptop: re-render cards at matchday end
    python scripts/matchday_refresh.py --target vm --dry-run   # show the decision, run nothing
    python scripts/matchday_refresh.py --target vm --list      # print each settle time (UTC)

On each tick it reads data/wc2026_fixtures.csv, finds each day's last kickoff, and fires the
target refresh once that day's games are done (last kickoff + BUFFER_H). State in
logger/data/last-refresh-<target>.json makes it fire once per matchday and restart-safe.

Targets:
  vm     -> deploy/refresh_site_vm.sh with FORCE_SCORES=1, so the Odds-API overlay bypasses its
            6h cost guard and pulls the finals immediately (worth the 2 credits once per matchday).
            No heartbeat: the 30-min xresidual-site timer is the backstop, so the gate only ever
            adds a prompt, force-fetched build at the moment the last whistle goes.
  laptop -> scripts/refresh_daily.sh (re-render cards, re-mark the paper book) once the matchday
            is done, plus a HEARTBEAT_H safety run so late-landing results still get rendered.

Wired on the VM to the xresidual-matchday systemd timer (every ~10 min).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from match_scheduler import kickoff_utc  # reuse the '13:00 UTC-6' -> UTC parser  # noqa: E402

FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
BUFFER_H = 3.0        # a day's games are done ~3h after the last kickoff
HEARTBEAT_H = 12.0    # laptop only: refresh at least this often (catch late-landing results)

TARGETS = {
    # name: (refresh script, extra env, heartbeat?)
    "vm": (os.path.join(ROOT, "deploy", "refresh_site_vm.sh"), {"FORCE_SCORES": "1"}, False),
    "laptop": (os.path.join(ROOT, "scripts", "refresh_daily.sh"), {}, True),
}


def settle_times() -> list[datetime]:
    """One 'matchday settle' instant per fixture date: that day's last kickoff + buffer."""
    fx = pd.read_csv(FIXTURES)
    last: dict[str, datetime] = {}
    for r in fx.itertuples(index=False):
        ko = kickoff_utc(r.date, r.time)
        if ko is None:
            continue
        last[r.date] = max(ko, last.get(r.date, ko))
    return sorted(t + timedelta(hours=BUFFER_H) for t in last.values())


def _load(state_path: str) -> dict:
    try:
        return json.load(open(state_path, encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description="refresh right after a matchday's games finish")
    ap.add_argument("--target", choices=sorted(TARGETS), default="laptop",
                    help="vm = publish results (force-fetch); laptop = re-render cards")
    ap.add_argument("--dry-run", action="store_true", help="show the decision, run nothing")
    ap.add_argument("--force", action="store_true", help="refresh now regardless")
    ap.add_argument("--list", action="store_true", help="print settle times and exit")
    args = ap.parse_args()

    script, extra_env, use_heartbeat = TARGETS[args.target]
    state_path = os.path.join(ROOT, "logger", "data", f"last-refresh-{args.target}.json")
    now = datetime.now(timezone.utc)
    settles = settle_times()

    if args.list:
        for s in settles:
            print(f"  {s:%Y-%m-%d %H:%M}Z  ({'done' if s <= now else 'upcoming'})")
        return 0

    st = _load(state_path)
    done = set(st.get("done", []))
    due = [s.isoformat() for s in settles if s <= now and s.isoformat() not in done]

    # First run (or wiped state): seed with everything already settled so we never back-fire the
    # whole past schedule; only act on the NEXT matchday to finish.
    if not st:
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        json.dump({"done": sorted(due), "seeded_utc": now.isoformat()},
                  open(state_path, "w", encoding="utf-8"), indent=2)
        print(f"[{now:%FT%TZ}] {args.target}: seeded {len(due)} settled matchdays; no refresh")
        return 0

    last = st.get("last_refresh")
    last_dt = datetime.fromisoformat(last) if last else None
    heartbeat = use_heartbeat and (last_dt is None or (now - last_dt) >= timedelta(hours=HEARTBEAT_H))
    reason = "forced" if args.force else ("matchday settled" if due else ("heartbeat" if heartbeat else None))

    if reason is None:
        nxt = next((s for s in settles if s > now), None)
        mins = int((nxt - now).total_seconds() / 60) if nxt else None
        print(f"[{now:%Y-%m-%d %H:%M}Z] {args.target}: no refresh due"
              + (f"; next matchday settles in {mins // 60}h{mins % 60:02d}m" if nxt else "; none upcoming"))
        return 0

    print(f"[{now:%Y-%m-%d %H:%M}Z] {args.target}: refresh due ({reason})"
          + (f"; {len(due)} matchday(s) settled" if due else "") + (" [DRY-RUN]" if args.dry_run else ""))
    if args.dry_run:
        return 0

    rc = subprocess.call(["bash", script], cwd=ROOT, env={**os.environ, **extra_env})
    if rc != 0:
        print(f"[{now:%H:%M}Z] {args.target}: refresh exited {rc}; state unchanged, retry next tick")
        return 1
    st["last_refresh"] = now.isoformat()
    st["done"] = sorted(done | set(due))
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)
    print(f"[{now:%H:%M}Z] {args.target}: refresh complete; state saved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
