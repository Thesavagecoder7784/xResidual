#!/usr/bin/env python3
"""Match-unit vs goal-unit harvestability — the check that catches the wrong-denominator claim.

    python scripts/harvest_unit_check.py     # -> writeups/_harvest_unit_check.json

`_harvest_results.json`'s `pooled.pct_harvestable` is a MEDIAN ACROSS MATCHES. It prints 0.0 as
soon as half the matches contain no harvestable goal, which is emphatically NOT the claim
"0% of goals were harvestable" — yet every draft before 2026-07-25 published it as exactly that.

This recomputes both denominators side by side from the per-game harvest archive so the gap is a
committed number rather than an argument, and it records its own COVERAGE: the archive on this
machine is a subset of the matches behind the pooled artifact (the tapes are transient and the
per-game JSONs were pruned), so `n_matches` here is smaller than `pooled.n_matches` there. Quote
this file only with its coverage attached; re-run it wherever the full archive lives to supersede.

Fork-forward safe: reads the archive, writes one artifact, edits nothing under xresidual/.
"""
from __future__ import annotations

import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARV_DIR = os.path.join(ROOT, "viz", "market", "harvest")
POOLED = os.path.join(ROOT, "writeups", "_harvest_results.json")
OUT = os.path.join(ROOT, "writeups", "_harvest_unit_check.json")


def main() -> int:
    rows = []
    for p in sorted(glob.glob(os.path.join(HARV_DIR, "*.json"))):
        d = json.load(open(p))
        s = d.get("all")
        if s and s.get("n"):
            rows.append((d.get("match", os.path.basename(p)[:-5]), s["n"], s["pct_harvestable"]))
    if not rows:
        print("no per-game harvest JSONs in viz/market/harvest — nothing to check")
        return 0

    med = lambda a: sorted(a)[len(a) // 2]
    n_goals = sum(r[1] for r in rows)
    harv_goals = sum(r[2] / 100.0 * r[1] for r in rows)
    match_unit = med([r[2] for r in rows])
    goal_unit = harv_goals / n_goals * 100

    ledger_n = None
    try:
        ledger_n = json.load(open(POOLED))["pooled"]["n_matches"]
    except Exception:  # noqa: BLE001 — the pooled artifact is optional context, not a dependency
        pass

    out = {
        "n_matches_checked": len(rows),
        "n_goals_checked": n_goals,
        "pct_harvestable_match_unit": round(match_unit, 2),
        "pct_harvestable_goal_weighted": round(goal_unit, 2),
        "harvestable_goals": int(round(harv_goals)),
        "matches_with_any_harvestable": sum(1 for r in rows if r[2] > 0),
        "pooled_ledger_n_matches": ledger_n,
        "coverage_note": (
            "Computed on the per-game harvest archive PRESENT ON THIS MACHINE, which is a subset "
            "of the matches behind writeups/_harvest_results.json (pooled_ledger_n_matches). The "
            "match-unit figure reproduces the published estimator on this subset; the goal-weighted "
            "figure is the number the published one is routinely mistaken for. Re-run where the "
            "full archive lives to supersede."),
        "claim_note": (
            "Correct phrasing: 'the median match has no harvestable goal'. INCORRECT: '0% of goals "
            "are harvestable' / 'essentially 0% of goals clear a tradeable-depth bar'."),
    }
    json.dump(out, open(OUT, "w"), indent=1)

    print(f"harvest unit check · {len(rows)} matches / {n_goals} goals"
          + (f"  (pooled ledger: {ledger_n} matches)" if ledger_n else ""))
    print(f"  match unit (the PUBLISHED estimator): median match {match_unit:.1f}% harvestable")
    print(f"  goal unit  (what it is misread as):   {goal_unit:.2f}% of goals "
          f"({int(round(harv_goals))} of {n_goals})")
    print(f"  matches with >=1 harvestable goal:    {out['matches_with_any_harvestable']} of {len(rows)}")
    print(f"wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
