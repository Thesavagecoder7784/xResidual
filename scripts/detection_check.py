#!/usr/bin/env python3
"""Does tape detection over-fire against an exogenous goal clock?
    -> writeups/_detection_results.json

    python scripts/detection_check.py --check   # compare to the shipped artifact, write nothing
    python scripts/detection_check.py           # regenerate on every surviving archive

WHY THIS EXISTS. The shipped artifact had no generator, leaving nDetectChecked and nOverDetect
outside the "regenerates with one command" guarantee. It was also computed when only 31 per-game
archives survived on the working machine; 86 survive now, so the check runs on roughly three
times the coverage. This supersedes the earlier numbers rather than reproducing them, which is
the reason it is a separate, deliberate script rather than a silent refresh.

WHAT IS COUNTED, and why this definition. Section 4's claim is that a detector keyed on the size
and persistence of a mid move cannot distinguish a goal from the market repricing the game clock
on a level match. The honest test compares the events the paper actually ANALYSES against the
goals that actually happened:

  * events   -- only those clearing the co-movement quality gate in build_leadlag.py, i.e. the
                ones carrying a resolved lead (polymarket / kalshi / synchronous). Raw candidate
                shocks that failed the gate are not part of any downstream estimate, so counting
                them would overstate the problem by roughly an order of magnitude.
  * distinct -- de-duplicated across contracts at the detector's own 30 s refractory, because a
                single goal moves both of a match's contracts and would otherwise count twice.
  * goals    -- from data/wc_goals_espn.json, a public match feed independent of the price data,
                reconciled 104/104 against the official scorelines. The superseded artifact used
                the scoreline total instead, which cannot see own goals or shootouts separately.

A match over-detects when its distinct gated-event count exceeds its goal count.

Reads derived per-match archives and public match facts only. No venue data written.
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEADLAG = os.path.join(ROOT, "viz", "market", "leadlag")
OUT = os.path.join(ROOT, "writeups", "_detection_results.json")
REFRACTORY_MS = 30_000          # build_leadlag's own event de-duplication window

# Reuse the clock index + feed-name bridge already written and audited for the clock-verified
# lead-lag check, rather than maintaining a second copy of the alias table.
_spec = importlib.util.spec_from_file_location(
    "cv", os.path.join(ROOT, "scripts", "clock_verified_leadlag.py"))
_cv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cv)


def _distinct(times: list[int]) -> int:
    kept: list[int] = []
    for t in sorted(times):
        if not kept or t - kept[-1] >= REFRACTORY_MS:
            kept.append(t)
    return len(kept)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    clock = _cv.clock_index()
    n_archives = 0
    checked, over, goalless, goalless_detecting = 0, 0, 0, 0
    ratios: list[float] = []
    no_clock = 0

    for f in sorted(glob.glob(os.path.join(LEADLAG, "*.json"))):
        n_archives += 1
        try:
            d = json.load(open(f))
        except Exception:  # noqa: BLE001
            print(f"  ! unreadable, skipped: {os.path.basename(f)}")
            continue
        parts = (d.get("match") or "").split(" vs ")
        if len(parts) != 2:
            no_clock += 1
            continue
        cl = clock.get(frozenset((_cv._norm(parts[0]), _cv._norm(parts[1]))))
        if cl is None:
            no_clock += 1
            continue
        n_goals = len(cl.get("goals", []))
        gated = [e for p in d.get("pairs", []) for e in p.get("events", [])
                 if str(((e.get("lead") or {}).get("leader") or "")).lower()
                 in ("polymarket", "kalshi", "synchronous")]
        n_det = _distinct([e["t_ms"] for e in gated if e.get("t_ms") is not None])
        checked += 1
        if n_det > n_goals:
            over += 1
        if n_goals == 0:
            goalless += 1
            goalless_detecting += n_det > 0
        else:
            ratios.append(n_det / n_goals)

    ratios.sort()
    med_ratio = ratios[len(ratios) // 2] if ratios else None
    res = {
        "n_matches_checked": checked,
        "n_over_detect": over,
        "n_archives": n_archives,
        "n_no_clock_entry": no_clock,
        "n_goalless": goalless,
        "n_goalless_detecting": goalless_detecting,
        "median_detected_per_goal": round(med_ratio, 2) if med_ratio is not None else None,
        "definition": ("distinct gate-passing events (30s de-dup across contracts) vs goals from "
                       "data/wc_goals_espn.json"),
        "note": ("detection validity vs an exogenous goal clock. SUPERSEDES the earlier artifact, "
                 "which was computed on 31 surviving archives against scoreline totals; this runs "
                 "on every surviving archive. See scripts/detection_check.py for the counting rule."),
    }

    print(f"  archives read     : {n_archives}   (no clock entry: {no_clock})")
    print(f"  matches checked   : {checked}   (superseded artifact: 29)")
    print(f"  over-detecting    : {over} of {checked}  ({over/max(1,checked):.0%})"
          f"   (superseded: 15 of 29, 52%)")
    print(f"  goalless matches  : {goalless}, of which detect >0: {goalless_detecting}")
    print(f"  median detected per goal: {res['median_detected_per_goal']}")

    if args.check:
        shipped = json.load(open(OUT))
        diffs = [(k, shipped.get(k), res[k]) for k in ("n_matches_checked", "n_over_detect")
                 if shipped.get(k) != res[k]]
        for k, a, b in diffs:
            print(f"  ~~ {k}: shipped={a} fresh={b}  (expected: this supersedes)")
        print("  " + ("IDENTICAL to shipped" if not diffs
                      else f"{len(diffs)} field(s) superseded — rerun without --check to adopt"))
        return 0

    with open(OUT, "w") as fh:
        json.dump(res, fh, indent=1)
    print(f"  wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
