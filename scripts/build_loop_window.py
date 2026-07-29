#!/usr/bin/env python3
"""Cross-venue title gap, raw vs de-vigged, replayed day by day -> writeups/_loop_window_results.json

WHY THIS EXISTS. `viz/market/_basis.js` reports a single `avg_abs_gap` measured at one `asof`
timestamp, and the committed value was stamped 2026-07-20, the day AFTER the final. At that point
Kalshi's winner field is not a probability distribution at all: its overround reads 2300%, because
the resolved teams sit at 0 or 1 and the field no longer normalizes. A gap measured there is a
statement about resolution mechanics, not about whether two venues agree on an event.

It also matters which quantity that number is. `avg_abs_gap` is built from the DE-VIGGED prices
(build_basis.py line 132); the raw gap is the separate `avg_abs_raw`, which reads 49.95 at the same
timestamp. Quoting 3.98 as "the raw gap" therefore mislabels a de-vigged figure by an order of
magnitude in the wrong direction.

This replays the same comparison across every logged day so both quantities can be read against
each other on a common date, and so the buildup window is separable from the resolution window.
Nothing here is frozen: it recomputes from `logger/data/snapshots-*.jsonl` and can be rerun.

    python scripts/build_loop_window.py
"""
from __future__ import annotations

import collections
import glob
import json
import os
import statistics as st
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual.wc2026_teams import canonical as canon  # noqa: E402

OUT = os.path.join(ROOT, "writeups", "_loop_window_results.json")
LABELS = ("WC2026 Winner", "world-cup-winner")
MIN_FIELD = 20
# A venue's field is a usable probability distribution only while it roughly normalizes. Past this
# the book is resolving and a "gap" measures resolution, not disagreement.
MAX_BOOK_SUM = 1.25


def day_cross_section(path: str) -> dict:
    v = collections.defaultdict(dict)
    with open(path) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if r.get("market_label") not in LABELS:
                continue
            ven, o, m = r.get("venue"), r.get("outcome"), r.get("mid")
            if ven in ("kalshi", "polymarket") and o and m and 0 < m < 1:
                v[ven][canon(o)] = m
    return v


def main() -> int:
    files = sorted(glob.glob(os.path.join(ROOT, "logger", "data", "snapshots-*.jsonl")))
    if not files:
        print("no snapshots on this machine (logger/data is gitignored) — cannot rebuild")
        return 1
    series = []
    for path in files:
        day = os.path.basename(path)[len("snapshots-"):-len(".jsonl")]
        v = day_cross_section(path)
        if "kalshi" not in v or "polymarket" not in v:
            continue
        common = sorted(set(v["kalshi"]) & set(v["polymarket"]))
        if len(common) < MIN_FIELD:
            continue
        sk = sum(v["kalshi"][t] for t in common)
        sp = sum(v["polymarket"][t] for t in common)
        raw = [abs(v["kalshi"][t] - v["polymarket"][t]) * 100 for t in common]
        dev = [abs(v["kalshi"][t] / sk - v["polymarket"][t] / sp) * 100 for t in common]
        series.append({"date": day, "n_teams": len(common),
                       "book_sum_kalshi": round(sk, 4), "book_sum_poly": round(sp, 4),
                       "raw_gap_pp": round(st.mean(raw), 4),
                       "devig_gap_pp": round(st.mean(dev), 4),
                       "distributional": bool(sk <= MAX_BOOK_SUM and sp <= MAX_BOOK_SUM)})

    live = [s for s in series if s["distributional"]]
    out = {
        "estimator": "per-day mean absolute cross-venue gap on the title field, raw and after "
                     "multiplicative de-vig, replayed from the logged snapshots",
        "max_book_sum_for_distributional": MAX_BOOK_SUM,
        "n_days": len(series), "n_days_distributional": len(live),
        "window_distributional": [live[0]["date"], live[-1]["date"]] if live else None,
        "raw_gap_pp_median": round(st.median(s["raw_gap_pp"] for s in live), 3) if live else None,
        "devig_gap_pp_median": round(st.median(s["devig_gap_pp"] for s in live), 3) if live else None,
        "raw_gap_pp_max_distributional": round(max(s["raw_gap_pp"] for s in live), 3) if live else None,
        "note": "While both books normalize, the raw and de-vigged gaps are nearly identical, because "
                "both venues carry small overrounds on the title field. The large gaps in _basis.js "
                "come from days on which Kalshi's field stops normalizing as teams resolve.",
        "series": series,
    }
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"  {len(series)} days, {len(live)} with both books distributional "
          f"({out['window_distributional']})")
    print(f"  median raw gap   {out['raw_gap_pp_median']} pp")
    print(f"  median de-vigged {out['devig_gap_pp_median']} pp")
    print(f"  max raw gap while distributional: {out['raw_gap_pp_max_distributional']} pp")
    print(f"wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
