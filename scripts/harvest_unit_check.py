#!/usr/bin/env python3
"""Match-unit vs goal-unit harvestability — the check that catches the wrong-denominator claim.

    python scripts/harvest_unit_check.py     # -> writeups/_harvest_unit_check.json

`_harvest_results.json`'s `pooled.pct_harvestable` is a MEDIAN ACROSS MATCHES. It prints 0.0 as
soon as half the matches contain no harvestable goal, which is emphatically NOT the claim
"0% of goals were harvestable" — yet every draft before 2026-07-25 published it as exactly that.

This recomputes both denominators side by side from the per-game harvest archive so the gap is a
committed number rather than an argument, and it records its own COVERAGE against two different
denominators, because they answer two different questions:

  * `n_matches_checked` vs `pooled_ledger_n_matches` — does this check cover the whole ledger?
    It did NOT until the per-game JSONs were recovered from a VM disk backup (2026-07-25); the
    note used to hard-code "this is a subset" and kept saying so after it stopped being true.
  * `n_matches_tracked` — how many of those archives are git-tracked, i.e. what a REVIEWER
    CLONING THE REPO can actually recompute. `viz/market/harvest` is gitignored and only the
    files committed before that rule existed still ship, so this can be far below the figure
    above. Whenever it is, the published number is not reproducible from a clone and the
    coverage note says so in as many words.

Quote this file only with its coverage attached.

Fork-forward safe: reads the archive, writes one artifact, edits nothing under xresidual/.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARV_DIR = os.path.join(ROOT, "viz", "market", "harvest")
POOLED = os.path.join(ROOT, "writeups", "_harvest_results.json")
OUT = os.path.join(ROOT, "writeups", "_harvest_unit_check.json")


def n_tracked() -> int | None:
    """How many per-game harvest archives are git-tracked = what a fresh clone can recompute.

    `core.quotepath=off` + NUL separation: several fixtures carry non-ASCII names (Curacao),
    which the default quoted output mangles into paths that do not exist on disk."""
    try:
        out = subprocess.run(
            ["git", "-c", "core.quotepath=off", "ls-files", "-z", "viz/market/harvest"],
            capture_output=True, cwd=ROOT, check=True)
        return len([p for p in out.stdout.decode().split("\0") if p.endswith(".json")])
    except Exception:  # noqa: BLE001 — not a git checkout; coverage-vs-clone is then unknowable
        return None


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

    tracked = n_tracked()

    # Two independent coverage statements. Neither is allowed to be assumed: the first was
    # hard-coded as "subset" and outlived its own truth by a re-pool, and the second is the
    # failure this file exists to make visible rather than repeat.
    if ledger_n and len(rows) >= ledger_n:
        cov = (f"Computed on the COMPLETE per-game harvest archive: {len(rows)} matches, matching "
               f"the {ledger_n} behind writeups/_harvest_results.json. (It was a "
               f"reduced subset until the missing per-game JSONs were recovered from a VM disk "
               f"backup on 2026-07-25; supersedes any earlier reduced-coverage reading.) The "
               f"match-unit figure reproduces the published estimator; the goal-weighted figure "
               f"is the number the published one is routinely mistaken for.")
    else:
        cov = (f"Computed on the per-game harvest archive PRESENT ON THIS MACHINE "
               f"({len(rows)} matches), a SUBSET of the "
               f"{ledger_n if ledger_n else 'pooled'} matches behind "
               f"writeups/_harvest_results.json. Re-run where the full archive lives to supersede.")

    if tracked is not None and tracked < len(rows):
        cov += (f" REPRODUCIBILITY: only {tracked} of these {len(rows)} archives are git-tracked "
                f"(viz/market/harvest is gitignored; the tracked ones predate that rule), so a "
                f"fresh CLONE recomputes this check on {tracked} matches and gets a different "
                f"goal-weighted rate. The figure published here is not clone-reproducible until "
                f"the remaining archives ship.")

    out = {
        "n_matches_checked": len(rows),
        "n_goals_checked": n_goals,
        "pct_harvestable_match_unit": round(match_unit, 2),
        "pct_harvestable_goal_weighted": round(goal_unit, 2),
        "harvestable_goals": int(round(harv_goals)),
        "matches_with_any_harvestable": sum(1 for r in rows if r[2] > 0),
        "pooled_ledger_n_matches": ledger_n,
        "n_matches_tracked": tracked,
        "coverage_note": cov,
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
    if tracked is not None and tracked < len(rows):
        print(f"  ! only {tracked} of {len(rows)} archives are git-tracked — a fresh clone "
              f"recomputes this on {tracked} matches")
    print(f"wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
