#!/usr/bin/env python3
"""Favourite-longshot wedge: sportsbook vs prediction market -> viz/market/_flb.js.

    python scripts/build_flb_wedge.py

Both markets de-vigged (normalized over the shared team set), so any divergence is a
pricing bias, not margin. The classic favourite-longshot bias predicts traditional
books price longshots too high and favourites too low relative to a sharp market;
here that shows as points sitting above the agreement diagonal at the longshot end.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import trajectory, wc2026_teams  # noqa: E402
from pull_forecast_data import ISO, KIT, INK  # noqa: E402

OUT = os.path.join(ROOT, "viz", "market", "_flb.js")


def latest(mask):
    s = snaps[mask].copy()
    s = s[s.ts_utc == s.ts_utc.max()]
    s["team"] = s.outcome.map(wc2026_teams.canonical)
    s = s[s.team.isin(wc2026_teams.WC2026_TEAMS)]
    return dict(zip(s.team, s.mid))


snaps = trajectory.load_snapshots(os.path.join(ROOT, "logger", "data"))


def main() -> int:
    book = latest(snaps.get("market_type") == "outrights")
    poly = latest((snaps.venue == "polymarket")
                  & snaps.market_label.str.contains("Winner", na=False) & snaps.mid.notna())
    shared = sorted(set(book) & set(poly), key=lambda t: -poly[t])
    bs, ps = sum(book[t] for t in shared), sum(poly[t] for t in shared)
    pts = [{"team": t, "iso": ISO.get(t, ""), "color": KIT.get(t, INK),
            "book": round(book[t] / bs * 100, 3), "poly": round(poly[t] / ps * 100, 3)}
           for t in shared]

    x = np.log([p["poly"] for p in pts]); y = np.log([p["book"] for p in pts])
    slope, intercept = np.polyfit(x, y, 1)
    tiers = []
    for lab, lo, hi in [("favourites", 5, 100), ("mid", 1, 5), ("longshots", 0, 1)]:
        r = [p["book"] / p["poly"] for p in pts if lo <= p["poly"] < hi]
        if r:
            tiers.append({"label": lab, "ratio": round(float(np.mean(r)), 2), "n": len(r)})

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.FLB = " + json.dumps({"points": pts, "slope": round(float(slope), 3),
                "intercept": round(float(intercept), 4), "tiers": tiers}) + ";\n")
    print(f"wrote {OUT}: {len(pts)} teams, log-log slope={slope:.3f}")
    for t in tiers:
        print(f"  {t['label']:11s} book/poly = {t['ratio']}  (n={t['n']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
