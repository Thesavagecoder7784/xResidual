#!/usr/bin/env python3
"""Identification robustness for the price-discovery decomposition (section 4).
    -> writeups/_identification_results.json

    python scripts/identification_check.py --check     # verify against the shipped artifact
    python scripts/identification_check.py --tracked   # restrict to git-tracked archives
    python scripts/identification_check.py             # regenerate from every archive present

WHY THIS EXISTS. Two objections to the VECM decomposition were answerable from artifacts we
already ship, and neither was answered in the manuscript:

  1. THE ADF GATE. Pairs enter the pool at p < 0.10. The paper argues permissiveness is the
     conservative direction (a stricter gate would retain only the cleanest pairs, which is
     the selection a reader should suspect), but never showed the estimate under a stricter
     gate. Now it does.

  2. THE INFORMATION LEADERSHIP SHARE. We cite Putnins (2013) for the diagnosis that the
     Hasbrouck information share and the Gonzalo-Granger component share diverge when
     innovation variances differ across venues, but not his proposed remedy, the ILS. A
     referee reading that citation will compute it. So we compute it first -- and the point
     of doing so is that it is NOT identified here: ILS is a function of a point-identified
     information share, ours is identified only up to a Cholesky interval, and the ILS
     verdict flips sign across that interval. Reporting the sweep is the honest form of the
     result; reporting the midpoint alone would be a number with no standing in either
     direction.

ESTIMATOR. Per contract from the archives, then the per-match median, then the median across
matches -- the same match-is-the-unit convention used everywhere else in the paper, so these
rows are comparable to the headline. The p < 0.10 row reproduces the shipped headline exactly
and is retained as a regression test on this script, not as a new result.

ILS DEFINITION (Putnins 2013). With IS_a the Hasbrouck share and CS_a the component share,
    IL_a = |(IS_a/IS_b)(CS_b/CS_a)|,   ILS_a = IL_a / (IL_a + IL_b).
Writing r = (IS_a/IS_b)/(CS_a/CS_b) this is r^2/(r^2+1), which is what we evaluate. It is
undefined when either share leaves (0,1) -- which happens here whenever a same-sign alpha pair
pushes the component share out of support -- and those contracts are counted, not silently
dropped.

Reads derived per-match archives only. Writes nothing under xresidual/ and touches no tape.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import statistics as st
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INFO = os.path.join(ROOT, "viz", "market", "infoshare")
OUT = os.path.join(ROOT, "writeups", "_identification_results.json")

# The gate as used in the paper, then two stricter ones. 0.10 must come first: it is the
# published specification and the row the regression test compares against.
ADF_LEVELS = [0.10, 0.05, 0.01]

# Which Hasbrouck bound to evaluate the ILS at. The midpoint is what the paper reports as
# \hasMid; lo/hi are the Cholesky bounds, and the span between them is the whole point.
HAS_KEYS = {"lower": "hasbrouck_a_lo", "mid": "hasbrouck_a_mid", "upper": "hasbrouck_a_hi"}


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files", "-z", "viz/market/infoshare"],
        capture_output=True, cwd=ROOT)
    return [os.path.join(ROOT, f) for f in out.stdout.decode().split("\0") if f]


def load(tracked_only: bool) -> tuple[list[tuple[str, list[dict]]], int]:
    """-> [(match name, [contract rows])], n_files. Cointegrated contracts only."""
    files = _tracked_files() if tracked_only else sorted(glob.glob(os.path.join(INFO, "*.json")))
    matches = []
    for f in files:
        try:
            d = json.load(open(f))
        except Exception:  # noqa: BLE001 -- a corrupt archive must not silently shrink coverage
            print(f"  ! unreadable, skipped: {os.path.basename(f)}")
            continue
        rows = [c for c in d.get("contracts", []) if c.get("cointegrated")]
        if rows:
            matches.append((d.get("match", os.path.basename(f)), rows))
    return matches, len(files)


def at_gate(matches, level: float) -> dict:
    """Per-match medians of the two shares, restricted to contracts passing ADF at `level`."""
    gg, has = [], []
    for _, rows in matches:
        r = [c for c in rows if c["adf_p"] < level]
        if not r:
            continue
        gg.append(st.median(c["gg_a"] for c in r))
        has.append(st.median(c["hasbrouck_a_mid"] for c in r))
    return {
        "adf_level": level,
        "n_matches": len(gg),
        "median_gg": round(st.median(gg), 4),
        "median_hasbrouck": round(st.median(has), 4),
        "matches_poly_gt_50": int(sum(1 for v in gg if v > 0.5)),
    }


def support(matches, level: float) -> dict:
    """Contracts whose component share leaves [0,1] -- a same-sign alpha pair, not an outlier
    to be averaged away. `n_in_permissive_band` answers whether the loose gate causes them."""
    oos = [c for _, rows in matches for c in rows
           if c["adf_p"] < level and not 0.0 <= c["gg_a"] <= 1.0]
    return {
        "n_contracts_out_of_support": len(oos),
        "max_gg_contract": round(max((c["gg_a"] for c in oos), default=float("nan")), 4),
        "n_in_permissive_band": int(sum(1 for c in oos if c["adf_p"] >= 0.05)),
        "permissive_band": [0.05, level],
    }


def ils(matches, level: float, has_key: str) -> dict:
    """Putnins (2013) information leadership share for Polymarket, evaluated at one Hasbrouck
    bound. Contracts with either share outside (0,1) are undefined and counted as such."""
    per_match, n_undef = [], 0
    for _, rows in matches:
        vals = []
        for c in rows:
            if c["adf_p"] >= level:
                continue
            IS, CS = c[has_key], c["gg_a"]
            if not 0.0 < IS < 1.0 or not 0.0 < CS < 1.0:
                n_undef += 1
                continue
            r = (IS / (1 - IS)) / (CS / (1 - CS))
            vals.append(r * r / (r * r + 1))
        if vals:
            per_match.append(st.median(vals))
    return {
        "median_ils_poly": round(st.median(per_match), 4),
        "n_matches": len(per_match),
        "matches_poly_leads": int(sum(1 for v in per_match if v > 0.5)),
        "n_contracts_undefined": n_undef,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="compare against the shipped artifact; write nothing")
    ap.add_argument("--tracked", action="store_true",
                    help="restrict to git-tracked archives (the acceptance-test subset)")
    args = ap.parse_args()

    matches, n_files = load(args.tracked)
    if not matches:
        print("  !! no per-game infoshare archives found — nothing to compute")
        return 1

    base = ADF_LEVELS[0]
    # The width of the Cholesky identification interval is why the ILS sweep is wide, so it is
    # part of the same result and must not be hand-typed into the prose beside it.
    widths = [c["hasbrouck_a_hi"] - c["hasbrouck_a_lo"]
              for _, rows in matches for c in rows if c["adf_p"] < base]
    payload = {
        "adf_sensitivity": [at_gate(matches, lv) for lv in ADF_LEVELS],
        "support": support(matches, base),
        "hasbrouck_band_width": {
            "median": round(st.median(widths), 4),
            "mean": round(st.fmean(widths), 4),
            "n_contracts": len(widths),
        },
        "ils": {name: ils(matches, base, key) for name, key in HAS_KEYS.items()},
    }
    lo = payload["ils"]["lower"]["median_ils_poly"]
    hi = payload["ils"]["upper"]["median_ils_poly"]
    payload["ils"]["spans_one_half"] = bool(min(lo, hi) < 0.5 < max(lo, hi))
    scope = "git-tracked subset" if args.tracked else "all archives present"
    payload["note"] = (
        f"ADF-gate sensitivity and Putnins (2013) ILS, computed per contract then per-match "
        f"median over {n_files} infoshare archives ({scope}). The adf_level=0.1 row is the "
        f"published specification and reproduces the shipped headline. ILS is evaluated at "
        f"each Hasbrouck Cholesky bound; spans_one_half=true means the leadership verdict is "
        f"not identified.")

    for row in payload["adf_sensitivity"]:
        print(f"  adf<{row['adf_level']:<5} n={row['n_matches']:3d}  GG={row['median_gg']:.3f}"
              f"  HAS={row['median_hasbrouck']:.3f}"
              f"  poly>0.5 in {row['matches_poly_gt_50']}/{row['n_matches']}")
    s = payload["support"]
    print(f"  out-of-support contracts: {s['n_contracts_out_of_support']}"
          f" (max {s['max_gg_contract']}), {s['n_in_permissive_band']} in the permissive band")
    for name in ("lower", "mid", "upper"):
        r = payload["ils"][name]
        print(f"  ILS @{name:<5} = {r['median_ils_poly']:.3f}"
              f"   poly leads {r['matches_poly_leads']}/{r['n_matches']}")
    print(f"  ILS spans 0.5 across the identification band: {payload['ils']['spans_one_half']}")

    if args.check:
        shipped = json.load(open(OUT))
        bad = [k for k, v in payload.items() if k != "note" and shipped.get(k) != v]
        for k in bad:
            print(f"  !! {k}: shipped={shipped.get(k)} fresh={payload[k]}")
        print("  " + ("CHECK CLEAN — regenerates the shipped artifact exactly"
                      if not bad else f"{len(bad)} FIELD(S) DIFFER"))
        return 1 if bad else 0

    with open(OUT, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"  wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
