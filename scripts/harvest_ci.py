#!/usr/bin/env python3
"""Bootstrap CI and depth-gate sensitivity for the harvestability result.
    -> writeups/_harvest_ci_results.json
    -> writeups/_harvest_gate_results.json

    python scripts/harvest_ci.py --check      # verify against the shipped artifacts, write nothing
    python scripts/harvest_ci.py --tracked    # acceptance test: restrict to the git-tracked subset
    python scripts/harvest_ci.py              # regenerate on every per-game archive present

WHY THIS EXISTS. Both artifacts above were originally produced ad-hoc, after the per-game
archives were lost from this machine, and no generator was ever committed. That left five
macros (harvestCIlo, harvestCIhi, harvestNzero, harvestNci, nGateOne) outside the
"regenerates with one command" guarantee the paper makes. This script closes that hole and
makes the coverage a parameter rather than an accident of which files happened to survive.

ESTIMATOR. The published point estimate is a median-of-medians: each per-game archive carries
that match's own median per-goal harvestable share in all.pct_harvestable, and the headline is
the median of those across matches. The match is the unit, never the goal -- quoting this as
"% of goals" is the specific misreading build_harvest.py warns about. The bootstrap therefore
resamples MATCHES with replacement, which is also the cluster-robust unit used everywhere else
in the paper.

Reads derived per-match archives only. Writes nothing under xresidual/ and touches no tape.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import statistics as st
import subprocess

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARV = os.path.join(ROOT, "viz", "market", "harvest")
CI_OUT = os.path.join(ROOT, "writeups", "_harvest_ci_results.json")
GATE_OUT = os.path.join(ROOT, "writeups", "_harvest_gate_results.json")

SEED = 20260702        # frozen with the rest of the hardened stats
N_BOOT = 10_000
RELAXED_GATE = 0.01    # the "even at 1%" sensitivity quoted in section 6.2
BUILD_GATE = 0.25      # build_harvest.py summ(): harvestable requires depth_frac >= 0.25


def _tracked_files() -> list[str]:
    """The archives under version control. Used as the acceptance-test subset: these are the
    files that were present when the shipped CI artifact was computed."""
    out = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files", "-z", "viz/market/harvest"],
        capture_output=True, cwd=ROOT)
    return [os.path.join(ROOT, f) for f in out.stdout.decode().split("\0") if f]


def load(tracked_only: bool) -> tuple[list[float], list[float], int]:
    files = _tracked_files() if tracked_only else sorted(glob.glob(os.path.join(HARV, "*.json")))
    shares, depths = [], []
    for f in files:
        try:
            a = (json.load(open(f)).get("all") or {})
        except Exception:  # noqa: BLE001  -- a corrupt archive must not silently shrink coverage
            print(f"  ! unreadable, skipped: {os.path.basename(f)}")
            continue
        if a.get("pct_harvestable") is None:
            continue
        shares.append(float(a["pct_harvestable"]))
        if a.get("depth_frac_med") is not None:
            depths.append(float(a["depth_frac_med"]))
    return shares, depths, len(files)


def bootstrap(shares: list[float]) -> dict:
    rng = np.random.default_rng(SEED)
    arr = np.asarray(shares, dtype=float)
    meds = np.median(rng.choice(arr, size=(N_BOOT, arr.size), replace=True), axis=1)
    lo, hi = np.percentile(meds, [2.5, 97.5])
    return {
        "n_matches": int(arr.size),
        "median_pct": float(st.median(shares)),
        "ci95": [round(float(lo), 4), round(float(hi), 4)],
        "n_zero_matches": int(sum(1 for v in shares if v == 0)),
        "frac_boot_median_zero": round(float((meds == 0).mean()), 4),
    }


def gate(depths: list[float], n_matches: int) -> dict:
    return {
        "depth_gate": BUILD_GATE,
        "gate_source": "build_harvest.py summ(): harvestable requires depth_frac >= 0.25",
        "n_matches_archived": n_matches,
        "n_clearing_gate_1pct": int(sum(1 for d in depths if d >= RELAXED_GATE)),
        "median_depth_frac": round(float(st.median(depths)), 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="compare against the shipped artifacts; write nothing")
    ap.add_argument("--tracked", action="store_true",
                    help="restrict to git-tracked archives (the acceptance-test subset)")
    args = ap.parse_args()

    shares, depths, n_files = load(args.tracked)
    if not shares:
        print("  !! no per-game harvest archives found — nothing to compute")
        return 1

    ci = bootstrap(shares)
    gt = gate(depths, len(shares))
    scope = "git-tracked subset" if args.tracked else "all archives present"
    ci["note"] = (f"bootstrap over the per-game harvest archives ({scope}: {ci['n_matches']} "
                  f"matches); resamples matches, {N_BOOT} replicates, seed {SEED}")
    gt["note"] = (f"sensitivity of the harvestability conclusion to the depth gate, computed on "
                  f"{gt['n_matches_archived']} per-game archives ({scope})")

    print(f"  archives read : {n_files} files -> {ci['n_matches']} matches with a share ({scope})")
    print(f"  median share  : {ci['median_pct']}%   CI95 {ci['ci95']}")
    print(f"  zero matches  : {ci['n_zero_matches']} of {ci['n_matches']}"
          f"   boot-median-zero {ci['frac_boot_median_zero']}")
    print(f"  median depth  : {gt['median_depth_frac']}   clearing 1% gate:"
          f" {gt['n_clearing_gate_1pct']} of {gt['n_matches_archived']}")

    if args.check:
        bad = 0
        for path, fresh in ((CI_OUT, ci), (GATE_OUT, gt)):
            shipped = json.load(open(path))
            for k, v in fresh.items():
                if k == "note":
                    continue
                if shipped.get(k) != v:
                    print(f"  !! {os.path.basename(path)}:{k} shipped={shipped.get(k)} fresh={v}")
                    bad += 1
        print("  " + ("CHECK CLEAN — regenerates the shipped artifacts exactly"
                      if not bad else f"{bad} FIELD(S) DIFFER"))
        return 1 if bad else 0

    for path, payload in ((CI_OUT, ci), (GATE_OUT, gt)):
        with open(path, "w") as f:
            json.dump(payload, f, indent=1)
        print(f"  wrote {os.path.relpath(path, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
