#!/usr/bin/env python3
"""How much does the de-vig METHOD choice move an implied probability? -> writeups/_devig_results.json

METHODOLOGY.md commits to reporting this sensitivity rather than silently picking a method, and
04_methods.tex asserted that "no finding hinges on the margin-removal choice" without ever showing
a number. This measures it, and the answer is not uniform across venues.

The estimator: for each logged snapshot of the title field, de-vig that cross-section with each of
multiplicative / power / Shin, and record the per-outcome spread across methods. The unit is one
outcome in one cross-section; we report the median and the worst case.

The important structural finding is that the two venues are not comparable objects here.
Polymarket's winner field is a normalized book (sums to ~1.01), so the methods nearly agree.
Kalshi's is a set of INDEPENDENT yes/no binaries that sums to ~7, so "de-vigging" it is really
normalizing a basket into a distribution, and the method choice matters an order of magnitude more.
Shin can fail outright on Polymarket, because its solver has no root when a book sums to <= 1.

Fork-forward: NEW scripts/ module; edits nothing under xresidual/ (it only imports the frozen
devig helpers).

    python scripts/build_devig_sensitivity.py
"""
from __future__ import annotations

import collections
import glob
import json
import os
import statistics as st
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual.devig import implied_probabilities  # noqa: E402  frozen helpers

OUT = os.path.join(ROOT, "writeups", "_devig_results.json")
LABEL = "WC2026 Winner"
MIN_FIELD = 20          # need a full field, not a partial scrape


def cross_sections(rows, venue):
    by = collections.defaultdict(list)
    for r in rows:
        if (r.get("market_label") == LABEL and r.get("venue") == venue
                and r.get("mid") and 0 < r["mid"] < 1):
            by[r["ts_utc"]].append(r["mid"])
    return [px for px in by.values() if len(px) >= MIN_FIELD]


def main() -> int:
    files = sorted(glob.glob(os.path.join(ROOT, "logger", "data", "snapshots-*.jsonl")))
    if not files:
        print("no snapshots on this machine (logger/data is gitignored) — cannot rebuild")
        return 1
    out = {"estimator": "per-outcome spread across de-vig methods, one title cross-section at a "
                        "time; unit = one outcome in one snapshot",
           "methods": ["multiplicative", "power"],
           "note": "Shin is excluded from the headline spread because its solver has no root when "
                   "a book sums to <= 1, which is the normal case on Polymarket.",
           "venues": {}}
    for f in files[-40:]:
        pass
    rows = []
    for f in files[-40:]:
        with open(f) as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue
    for venue in ("kalshi", "polymarket"):
        xs = cross_sections(rows, venue)
        if not xs:
            continue
        spreads, sums = [], []
        for px in xs:
            sums.append(sum(px))
            a = implied_probabilities([1 / p for p in px], "multiplicative")
            b = implied_probabilities([1 / p for p in px], "power")
            d = np.abs(a - b)
            spreads.append((float(np.median(d)) * 100, float(d.max()) * 100))
        out["venues"][venue] = {
            "n_cross_sections": len(xs),
            "book_sum_median": round(st.median(sums), 4),
            "median_spread_pp": round(st.median(s[0] for s in spreads), 3),
            "worst_outcome_pp": round(max(s[1] for s in spreads), 2),
        }
        v = out["venues"][venue]
        print(f"  {venue:11} n={v['n_cross_sections']:4d} book-sum {v['book_sum_median']:.3f} "
              f"median spread {v['median_spread_pp']:.3f}pp  worst {v['worst_outcome_pp']:.2f}pp")
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
