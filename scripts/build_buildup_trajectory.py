#!/usr/bin/env python3
"""Buildup title-race trajectory -> viz/market/_buildup.js.

    python scripts/build_buildup_trajectory.py

The one market card whose data used to be pasted in by hand (and so went stale every
day). This regenerates it from the logged snapshots: for each calendar day it takes the
latest winner price per team on each venue, de-vigs each venue's field (multiplicative,
so we compare beliefs not margins), and reports the average across the two venues: the de-vigged
implied championship probability per day. Run daily (it's in build_all); the series
auto-extends through the tournament.
"""
from __future__ import annotations

import glob
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import wc2026_teams  # noqa: E402

OUT = os.path.join(ROOT, "viz", "market", "_buildup.js")
DATA_GLOB = os.path.join(ROOT, "logger", "data", "snapshots-*.jsonl")
VENUES = ("polymarket", "kalshi")
# the seven the card draws (must match its colour keys exactly)
TEAMS = ["Spain", "France", "England", "Portugal", "Argentina", "Brazil", "Germany"]


def main() -> int:
    # day -> venue -> team -> (ts, raw mid)  (keep the latest quote per day)
    latest: dict = {}
    for fn in sorted(glob.glob(DATA_GLOB)):
        with open(fn, encoding="utf-8") as f:
            for line in f:
                try:
                    q = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if q.get("extra", {}).get("market_type") != "winner":
                    continue
                v = q.get("venue")
                if v not in VENUES or q.get("outcome") in (None, "__error__"):
                    continue
                mid = q.get("mid")
                if mid is None or mid <= 0:
                    continue
                t = wc2026_teams.canonical(q["outcome"])
                if t not in wc2026_teams.WC2026_TEAMS:
                    continue
                day, ts = q["ts_utc"][:10], q["ts_utc"]
                cell = latest.setdefault(day, {}).setdefault(v, {})
                if t not in cell or ts > cell[t][0]:
                    cell[t] = (ts, float(mid))

    # per day, per venue: de-vig the whole field, then average across venues per team
    new_by_day: dict = {}  # day -> {team: pct or None}
    for day in sorted(latest):
        devigged = {}  # venue -> {team: fair prob}
        for v in VENUES:
            raw = {t: mp[1] for t, mp in latest[day].get(v, {}).items()}
            s = sum(raw.values())
            if s > 0:
                devigged[v] = {t: p / s for t, p in raw.items()}
        row = {}
        for t in TEAMS:
            vals = [devigged[v][t] for v in VENUES if t in devigged.get(v, {})]
            row[t] = round(statistics.mean(vals) * 100, 2) if vals else None
        new_by_day[day] = row

    # INCREMENTAL MERGE: the VM keeps only recent snapshots, so a full rebuild there would drop the
    # early buildup (May onward). Read the prior series and overlay only the days we just recomputed —
    # old days persist from the existing card, recent days refresh, new days extend. Retention-proof,
    # so this can run on the VM daily without losing history (it just needs the seeded card present).
    by_day: dict = {}
    try:
        prev = json.loads(open(OUT, encoding="utf-8").read().split("=", 1)[1].rstrip().rstrip(";\n"))
        for i, day in enumerate(prev.get("dates", [])):
            by_day[day] = {t: (prev["series"].get(t, []) + [None] * len(prev["dates"]))[i] for t in TEAMS}
    except Exception:
        pass
    by_day.update(new_by_day)                      # recomputed days overwrite; older days persist

    days = sorted(by_day)
    series = {t: [by_day[d].get(t) for d in days] for t in TEAMS}
    payload = {"dates": days, "series": series}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.BUILDUP = " + json.dumps(payload) + ";\n")
    span = f"{days[0]} → {days[-1]}" if days else "(no data)"
    last = {t: series[t][-1] for t in TEAMS if series[t] and series[t][-1] is not None}
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(days)} days ({span})")
    print("  latest: " + " · ".join(f"{t} {p:.1f}%" for t, p in
                                     sorted(last.items(), key=lambda kv: -kv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
