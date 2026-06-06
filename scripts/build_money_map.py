#!/usr/bin/env python3
"""The money map -> viz/market/_money.js (window.MONEY).

    python scripts/build_money_map.py

Uses the volume + liquidity we already log. The finding: turnover runs opposite
to the odds. The title favourites are among the least-traded contracts, while
longshots and storylines churn (lottery-ticket buying + fading). Cumulative
Polymarket $ volume per winner contract, latest snapshot.
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

OUT = os.path.join(ROOT, "viz", "market", "_money.js")


def main() -> int:
    snaps = trajectory.load_snapshots(os.path.join(ROOT, "logger", "data"))
    w = snaps[(snaps.venue == "polymarket")
              & snaps["market_label"].str.contains("Winner", case=False, na=False)
              & snaps["volume"].notna() & snaps["mid"].notna()].copy()
    w = w[w.ts_utc == w.ts_utc.max()]
    w["team"] = w.outcome.map(wc2026_teams.canonical)
    w = w[w.team.isin(wc2026_teams.WC2026_TEAMS)]
    w["volrank"] = w.volume.rank(ascending=False).astype(int)
    total = w.volume.sum()
    corr = float(np.corrcoef(w.volume, w.mid)[0, 1])

    def row(r):
        return {"team": r.team, "iso": ISO.get(r.team, ""), "color": KIT.get(r.team, INK),
                "vol": round(r.volume / 1e6, 1), "volsh": round(r.volume / total * 100, 1),
                "prob": round(r.mid * 100, 1), "rank": int(r.volrank)}

    by_vol = [row(r) for r in w.sort_values("volume", ascending=False).itertuples()]
    # The favourites, for contrast: highest title odds, with their (low) turnover rank.
    favs = [row(r) for r in w.sort_values("mid", ascending=False).head(6).itertuples()]

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.MONEY = " + json.dumps({
            "teams": by_vol[:9], "favs": favs, "corr": round(corr, 2),
            "n": int(len(w)), "total_m": round(total / 1e6)}) + ";\n")
    print(f"wrote {OUT}: top {len(by_vol[:9])} traded + {len(favs)} favourites, "
          f"total ${total/1e6:.0f}M, corr(vol,prob)={corr:+.2f}")
    print("  favourites' turnover rank:", ", ".join(f"{f['team']} #{f['rank']}" for f in favs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
