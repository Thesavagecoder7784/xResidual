#!/usr/bin/env python3
"""Conditional survival decoded from the market -> viz/market/_survival.js.

    python scripts/build_survival.py

The venues price 'reach R16', 'reach QF', etc. as separate contracts. The *ratio*
QF/R16 = P(win the Round-of-16 tie | you reached it) — a belief the market never
shows directly. High reach + low conditional = a 'paper tiger' (gets there, bows out);
high both = a deep runner. Ratios of independently-priced markets, so read directionally.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from pull_forecast_data import ISO, KIT, INK, team_probs  # noqa: E402

OUT = os.path.join(ROOT, "viz", "market", "_survival.js")


def main() -> int:
    r16 = team_probs("world-cup-nation-to-reach-round-of-16")
    qf = team_probs("world-cup-nation-to-reach-quarterfinals")
    win = team_probs("world-cup-winner")

    rows = []
    for t in sorted(win, key=lambda t: -win[t]):
        a, b = r16.get(t, 0), qf.get(t, 0)
        if a < 0.30:                       # need a meaningful reach prob for a stable ratio
            continue
        rows.append({"team": t, "iso": ISO.get(t, ""), "color": KIT.get(t, INK),
                     "reach": round(a * 100, 1), "cond": round(min(b / a, 1.0) * 100, 1)})
    rows = rows[:14]

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.SURVIVAL = " + json.dumps({"teams": rows}) + ";\n")
    print(f"wrote {OUT}: {len(rows)} teams")
    for r in sorted(rows, key=lambda r: r["cond"])[:3]:
        print(f"  paper tiger: {r['team']} reach {r['reach']}%  win-that-tie {r['cond']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
