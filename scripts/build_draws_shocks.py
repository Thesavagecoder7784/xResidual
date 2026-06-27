#!/usr/bin/env python3
"""The group stage's biggest shocks were draws -> viz/model/_draws_shocks.js.

    python scripts/build_draws_shocks.py

Reads the model's own per-match forecast feed (docs/data/matches.js, written by
build_matches.py) and ranks every PLAYED group game by how much its result
surprised the pre-match model -- the probability the model put on the outcome
that actually happened (lower = bigger shock). The headline read is that, in one
of the highest-scoring group stages on record, the most surprising results were
heavy favourites being *held* to a draw, not giant-killings. Purely descriptive:
this is the texture of the tournament, not a market-mispricing claim.

Numbers regenerate from the same feed the thread and the live site read, so the
card cannot drift from the data behind it.
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from pull_forecast_data import ISO, ensure_flag  # noqa: E402

FEED = os.path.join(ROOT, "docs", "data", "matches.js")
OUT = os.path.join(ROOT, "viz", "model", "_draws_shocks.js")
TOP_N = 7  # rows shown on the card


def load_games() -> dict:
    txt = open(FEED, encoding="utf-8").read()
    blob = re.search(r"window\.GAMES\s*=\s*(\{.*\})\s*;?\s*$", txt.strip(), re.S).group(1)
    return json.loads(blob)


def main() -> int:
    g = load_games()
    played = [m for m in g["matches"] if m.get("played")]
    n = len(played)
    goals = sum(m["s1"] + m["s2"] for m in played)
    draws = sum(1 for m in played if m["result"] == "draw")
    fav_dropped = sum(1 for m in played if m["result"] != m["fav"])

    def prob_of_result(m):
        return {"t1": m["p1"], "draw": m["pd"], "t2": m["p2"]}[m["result"]]

    ranked = sorted(played, key=prob_of_result)
    rows = []
    for m in ranked[:TOP_N]:
        i1, i2 = ISO.get(m["t1"], ""), ISO.get(m["t2"], "")
        ensure_flag(i1); ensure_flag(i2)
        rows.append({
            "t1": m["t1"], "t2": m["t2"], "iso1": i1, "iso2": i2,
            "s1": m["s1"], "s2": m["s2"], "draw": m["result"] == "draw",
            "p": round(prob_of_result(m) * 100, 1),
        })

    # how many of the top six shocks were draws (the line the thread uses)
    top6_draws = sum(1 for m in ranked[:6] if m["result"] == "draw")

    payload = {
        "asof": g.get("asof"),
        "n_played": n,
        "goals_per_game": round(goals / n, 2),
        "draw_pct": round(100 * draws / n, 1),
        "draws": draws,
        "fav_dropped_pct": round(100 * fav_dropped / n),
        "top6_draws": top6_draws,
        "rows": rows,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.DRAWSHOCKS = " + json.dumps(payload) + ";\n")
    print(f"wrote {os.path.relpath(OUT, ROOT)}")
    print(f"  {n} played | {payload['goals_per_game']} goals/game | "
          f"{payload['draw_pct']}% draws | {top6_draws}/6 top shocks are draws")
    for r in rows:
        tag = "draw" if r["draw"] else "    "
        print(f"  [{tag}] {r['p']:>5}%  {r['t1']} {r['s1']}-{r['s2']} {r['t2']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
