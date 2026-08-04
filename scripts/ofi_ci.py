#!/usr/bin/env python3
"""Match-clustered interval for the cross-venue order-flow-imbalance null (section 5.5).
    -> writeups/_ofi_ci_results.json

    python scripts/ofi_ci.py --check      # verify against the shipped artifact
    python scripts/ofi_ci.py --tracked    # restrict to git-tracked archives
    python scripts/ofi_ci.py              # regenerate from every archive present

WHY THIS EXISTS. Section 5.5 reports a null -- cross-venue order flow does not predict the
other venue's price -- and reported it as a bare point estimate. The section argues, correctly,
that the bin-level OLS t-statistic is inflated by overlapping intervals and match clustering and
so should not be quoted. But the consequence was a null with no interval attached at all, which
is the weakest form the claim can take: a reader cannot tell a precise zero from an imprecise
one. The match-resampling bootstrap used everywhere else in the paper applies here unchanged,
so we use it.

ESTIMATOR. Each archive stores per-match sufficient statistics (n, Sx, Sy, Sxx, Sxy, Syy) for
the cross-venue regression at each lag, so the per-match Pearson correlation is recoverable
exactly without re-reading any tape:

    r = (n*Sxy - Sx*Sy) / sqrt((n*Sxx - Sx^2) * (n*Syy - Sy^2))

We then resample MATCHES with replacement and take the median, the same cluster-robust unit as
the lead-lag and harvestability statistics. Reporting the whole lag profile matters as much as
the point: a genuine predictive relation would peak away from zero, and this one does not.

Reads derived per-match archives only. Writes nothing under xresidual/ and touches no tape.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import statistics as st
import subprocess

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFI = os.path.join(ROOT, "viz", "market", "ofi")
OUT = os.path.join(ROOT, "writeups", "_ofi_ci_results.json")

SEED = 20260702        # frozen with the rest of the hardened stats
N_BOOT = 10_000
DIRECTION = "poly_to_kalshi"   # does Polymarket flow predict Kalshi's price? the paper's question


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files", "-z", "viz/market/ofi"],
        capture_output=True, cwd=ROOT)
    return [os.path.join(ROOT, f) for f in out.stdout.decode().split("\0") if f]


def corr_from_suff(s: dict) -> float | None:
    """Pearson r from sufficient statistics; None when a variance is degenerate."""
    if not isinstance(s, dict):   # a lag the builder could not fill for this match
        return None
    n, Sx, Sy, Sxx, Sxy, Syy = (s["n"], s["Sx"], s["Sy"], s["Sxx"], s["Sxy"], s["Syy"])
    if n < 2:
        return None
    vx, vy = n * Sxx - Sx * Sx, n * Syy - Sy * Sy
    if vx <= 0 or vy <= 0:
        return None
    return (n * Sxy - Sx * Sy) / math.sqrt(vx * vy)


def load(tracked_only: bool) -> tuple[dict[int, list[float]], int]:
    """-> {lag_seconds: [per-match r]}, n_files."""
    files = _tracked_files() if tracked_only else sorted(glob.glob(os.path.join(OFI, "*.json")))
    by_lag: dict[int, list[float]] = {}
    for f in files:
        try:
            d = json.load(open(f))
        except Exception:  # noqa: BLE001 -- a corrupt archive must not silently shrink coverage
            print(f"  ! unreadable, skipped: {os.path.basename(f)}")
            continue
        for key, suff in (d.get("cross_suff") or {}).items():
            name, _, lag = key.partition("@")
            if name != DIRECTION:
                continue
            r = corr_from_suff(suff)
            if r is not None:
                by_lag.setdefault(int(lag), []).append(r)
    return by_lag, len(files)


def boot(rs: list[float]) -> dict:
    rng = np.random.default_rng(SEED)
    arr = np.asarray(rs, dtype=float)
    meds = np.median(rng.choice(arr, size=(N_BOOT, arr.size), replace=True), axis=1)
    lo, hi = np.percentile(meds, [2.5, 97.5])
    return {
        "n_matches": int(arr.size),
        "median_r": round(float(st.median(rs)), 4),
        "ci95": [round(float(lo), 4), round(float(hi), 4)],
        "straddles_zero": bool(lo <= 0 <= hi),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="compare against the shipped artifact; write nothing")
    ap.add_argument("--tracked", action="store_true",
                    help="restrict to git-tracked archives (the acceptance-test subset)")
    args = ap.parse_args()

    by_lag, n_files = load(args.tracked)
    if not by_lag:
        print("  !! no per-game OFI archives found — nothing to compute")
        return 1

    lags = sorted(by_lag)
    profile = {str(lag): boot(by_lag[lag]) for lag in lags}
    # The lag whose |median r| is largest. If that is 0, the relation is contemporaneous:
    # flow moves with price rather than ahead of it, which is the section's claim.
    peak = max(lags, key=lambda lg: abs(profile[str(lg)]["median_r"]))
    scope = "git-tracked subset" if args.tracked else "all archives present"
    payload = {
        "direction": DIRECTION,
        "lags_s": lags,
        "profile": profile,
        "peak_lag_s": peak,
        "peak": profile[str(peak)],
        # The bound is the quotable summary: no lag's typical match shows an association
        # larger than this in absolute value, which caps the explained variance near zero.
        "max_abs_median_r": round(max(abs(profile[str(lg)]["median_r"]) for lg in lags), 4),
        "max_abs_ci_bound": round(max(max(abs(b) for b in profile[str(lg)]["ci95"])
                                      for lg in lags), 4),
        "note": (f"per-match cross-venue OFI correlation recovered from stored sufficient "
                 f"statistics over {n_files} archives ({scope}); match-resampling bootstrap, "
                 f"{N_BOOT} replicates, seed {SEED}. peak_lag_s=0 means the relation is "
                 f"contemporaneous rather than predictive."),
    }

    for lag in lags:
        p = profile[str(lag)]
        star = " <- peak" if lag == peak else ""
        print(f"  lag {lag:+d}s  n={p['n_matches']:3d}  median r={p['median_r']:+.4f}"
              f"  CI95 [{p['ci95'][0]:+.4f},{p['ci95'][1]:+.4f}]{star}")

    if args.check:
        shipped = json.load(open(OUT))
        bad = [k for k, v in payload.items() if k != "note" and shipped.get(k) != v]
        for k in bad:
            print(f"  !! {k} differs")
        print("  " + ("CHECK CLEAN — regenerates the shipped artifact exactly"
                      if not bad else f"{len(bad)} FIELD(S) DIFFER"))
        return 1 if bad else 0

    with open(OUT, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"  wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
