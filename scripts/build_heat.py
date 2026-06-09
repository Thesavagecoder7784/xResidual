#!/usr/bin/env python3
"""Heat-exposure map: who drew the worst afternoon-in-a-hot-city schedule.

    python scripts/build_heat.py

Descriptive only. This is the schedule draw, not a result: heat's effect on *who
wins* is small, confounded, and unproven before the tournament, so it never touches
the model (same call as altitude). I also checked whether the market prices heat into
goals and it doesn't survive the confound: the raw implied totals are higher at hot
matches only because the schedule put blowouts (Germany-Curacao etc.) in hot slots, and
n is ~9 extreme matches. So the honest output is exposure, grounded in FIFPRO's
heat-stress risk venues + the afternoon kickoff window.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import data_fixtures, heat  # noqa: E402
from pull_forecast_data import ISO, KIT, INK, ensure_flag  # noqa: E402

OUT = os.path.join(ROOT, "viz", "model", "_heat.js")

# UEFA teams in the field — for the Euro-TV mechanism (US afternoon = European evening,
# so European sides get scheduled into the afternoon heat window for home prime-time).
UEFA = {"Spain", "France", "England", "Portugal", "Germany", "Netherlands", "Belgium",
        "Croatia", "Switzerland", "Norway", "Austria", "Sweden", "Turkey", "Scotland",
        "Czech Republic", "Bosnia & Herzegovina"}


def tv_mechanism(fixtures) -> dict:
    """Do European-involved group games land in the afternoon (heat) window more?"""
    g = fixtures[fixtures["round"].astype(str).str.contains("Matchday", na=False)]
    eu = no = eu_pm = no_pm = eu_ex = no_ex = 0
    for _, m in g.iterrows():
        h = heat.match_heat(m.get("ground"), m.get("time"))
        euro = (m.get("team1") in UEFA) or (m.get("team2") in UEFA)
        if euro:
            eu += 1; eu_pm += h["afternoon"]; eu_ex += (h["risk"] == "extreme")
        else:
            no += 1; no_pm += h["afternoon"]; no_ex += (h["risk"] == "extreme")
    pct = lambda a, b: round(100 * a / b) if b else 0
    return {"euro_afternoon_pct": pct(eu_pm, eu), "non_afternoon_pct": pct(no_pm, no),
            "euro_extreme_pct": pct(eu_ex, eu), "non_extreme_pct": pct(no_ex, no)}


def team_group(fixtures) -> dict:
    """team -> group letter (A..L), from the group-stage rows."""
    g = fixtures[fixtures["round"].astype(str).str.contains("Matchday", na=False)]
    tg = {}
    for _, m in g.iterrows():
        letter = str(m.get("group", "")).replace("Group ", "").strip()
        for t in (m.get("team1"), m.get("team2")):
            if isinstance(t, str):
                tg[t] = letter
    return tg


def main() -> int:
    fx = data_fixtures.load_fixtures()
    exp = heat.team_exposure(fx)
    tg = team_group(fx)

    teams = []
    for r in exp:
        cum, letter = None, tg.get(r["team"])
        if letter:
            l1 = heat.path_load(fx, f"1{letter}")   # win the group -> this venue path
            l2 = heat.path_load(fx, f"2{letter}")   # runner-up path
            cum = {"group_score": r["score"],
                   "ko_1st_score": l1["ko_score"], "ko_1st_extreme": l1["ko_extreme"],
                   "ko_2nd_score": l2["ko_score"], "ko_2nd_extreme": l2["ko_extreme"],
                   "total_1st": r["score"] + l1["ko_score"],
                   "total_2nd": r["score"] + l2["ko_score"]}
        teams.append({
            "team": r["team"], "iso": ISO.get(r["team"], ""), "color": KIT.get(r["team"], INK),
            "score": r["score"], "extreme": r["extreme"], "afternoon": r["afternoon"],
            "group": letter, "cumulative": cum,
            "games": [{"vs": gm["vs"], "iso": ISO.get(gm["vs"], ""), "ground": gm["ground"],
                       "hour": gm["hour"], "risk": gm["risk"]} for gm in r["games"]],
        })

    g = fx[fx["round"].astype(str).str.contains("Matchday", na=False)]
    import collections
    tiers = collections.Counter(heat.match_heat(m.ground, m.time)["risk"] for _, m in g.iterrows())

    payload = {
        "teams": teams,
        "tiers": {k: tiers.get(k, 0) for k in ("extreme", "high", "moderate", "low")},
        "fifpro_cities": list(heat.FIFPRO_EXTREME_CITIES),
        "n_zero": sum(1 for t in teams if t["score"] == 0),
        "tv": tv_mechanism(fx),
        "ko_intensity": heat.stage_intensity(fx),
    }
    for t in teams:
        ensure_flag(t["iso"])
        for gm in t["games"]:
            ensure_flag(gm["iso"])

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.HEAT = " + json.dumps(payload) + ";\n")
    top = teams[0]
    tv = payload["tv"]
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(teams)} teams · worst {top['team']} "
          f"(score {top['score']}, {top['extreme']} extreme) · {payload['n_zero']} with no heat games · "
          f"tiers {payload['tiers']} · Euro-TV: afternoon {tv['euro_afternoon_pct']}% vs {tv['non_afternoon_pct']}%, "
          f"extreme {tv['euro_extreme_pct']}% vs {tv['non_extreme_pct']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
