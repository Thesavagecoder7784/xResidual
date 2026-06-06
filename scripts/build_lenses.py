#!/usr/bin/env python3
"""Three lenses on team strength -> viz/model/_lenses.js (window.LENSES).

    python scripts/build_lenses.py

Each lens is normalized to a share of the 48-team field:
  elo  = 10^(rating/400) strength share (recent results)
  val  = Transfermarkt squad-value share (talent on paper)
  mkt  = de-vigged Polymarket title-odds share (the market's verdict)
Where they diverge is the story.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import data, elo, trajectory, wc2026_teams  # noqa: E402
from pull_forecast_data import ISO, KIT, INK  # noqa: E402
from squad_values import SQUAD_VALUE  # noqa: E402

OUT = os.path.join(ROOT, "viz", "model", "_lenses.js")


def market_winner_probs():
    snaps = trajectory.load_snapshots(os.path.join(ROOT, "logger", "data"))
    w = snaps[(snaps.venue == "polymarket")
              & snaps["market_label"].str.contains("Winner", case=False, na=False)
              & snaps["mid"].notna() & snaps["volume"].notna()].copy()  # full winner passes
    w = w[w.ts_utc == w.ts_utc.max()]
    w["team"] = w.outcome.map(wc2026_teams.canonical)
    w = w[w.team.isin(wc2026_teams.WC2026_TEAMS)]
    return dict(zip(w.team, w.mid))


def main() -> int:
    res = elo.build_ratings(data.load_results())
    teams = list(wc2026_teams.WC2026_TEAMS)
    elo_str = {t: 10 ** (res.ratings.get(wc2026_teams.elo_name(t), elo.INIT_RATING) / 400) for t in teams}
    mkt = market_winner_probs()

    es, vs, ms = sum(elo_str.values()), sum(SQUAD_VALUE.values()), sum(mkt.values())
    rows = []
    for t in teams:
        if t not in mkt:
            continue
        rows.append({"team": t, "iso": ISO.get(t, ""), "color": KIT.get(t, INK),
                     "elo": round(elo_str[t] / es * 100, 1),
                     "val": round(SQUAD_VALUE.get(t, 0) / vs * 100, 1),
                     "mkt": round(mkt[t] / ms * 100, 1)})
    rows.sort(key=lambda r: -r["mkt"])
    top = rows[:15]

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.LENSES = " + json.dumps({"teams": top, "meta": {"n_field": len(rows)}}) + ";\n")
    print(f"wrote {OUT}: {len(top)} teams (of {len(rows)})")
    # a couple of headline divergences for the writeup
    for t in ("Argentina", "Germany", "Colombia"):
        r = next((x for x in rows if x["team"] == t), None)
        if r:
            print(f"  {t}: Elo {r['elo']}  Value {r['val']}  Market {r['mkt']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
