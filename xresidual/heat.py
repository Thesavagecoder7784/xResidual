"""Heat exposure for the 2026 World Cup (afternoon kickoffs in hot host cities).

This is deliberately a NAIVE, sourced exposure measure, not a win-probability
adjustment. Heat's effect on *who wins* is small, confounded, and can't be validated
before the tournament, so (like the altitude prior, which I tested on ~50k matches and
dropped) I don't touch the model with it. What is defensible:

  - which matches/teams face the worst heat, from two objective signals:
      * venue: FIFPRO named six cities "extremely high risk" of heat-stress injury
        (Atlanta, Dallas, Houston, Kansas City, Miami, Monterrey).
      * slot: the noon/3pm afternoon window FIFPRO flags as the danger.
  - whether the market already prices heat into goals (lower implied totals at hot,
    afternoon matches) — a descriptive, market-anchored read, reported with its n.

Sources: FIFPRO heat-stress risk assessment; TIME / Bloomberg / ESPN coverage, 2026.
"""

from __future__ import annotations

# FIFPRO "extremely high risk" venues (matched by substring against fixture grounds,
# which carry area suffixes, e.g. "Miami (Miami Gardens)").
FIFPRO_EXTREME_CITIES = ("Atlanta", "Dallas", "Houston", "Kansas City", "Miami", "Monterrey")

# Local-time afternoon window FIFPRO flags (noon to ~4pm kickoffs).
AFTERNOON_START, AFTERNOON_END = 12, 16

RISK_SCORE = {"extreme": 3, "high": 2, "moderate": 1, "low": 0}


def is_extreme_city(ground: str | None) -> bool:
    if not isinstance(ground, str):
        return False
    return any(c in ground for c in FIFPRO_EXTREME_CITIES)


def local_hour(time_str: str | None) -> int | None:
    """Local kickoff hour from an openfootball time like '13:00 UTC-6' -> 13."""
    if not isinstance(time_str, str) or ":" not in time_str:
        return None
    try:
        return int(time_str.split(":")[0])
    except ValueError:
        return None


def is_afternoon(time_str: str | None) -> bool:
    h = local_hour(time_str)
    return h is not None and AFTERNOON_START <= h <= AFTERNOON_END


def match_heat(ground: str | None, time_str: str | None) -> dict:
    """Per-match heat read. risk: extreme (FIFPRO venue + afternoon), high (FIFPRO
    venue, cooler slot), moderate (afternoon elsewhere), low (cool slot elsewhere)."""
    hot = is_extreme_city(ground)
    pm = is_afternoon(time_str)
    if hot and pm:
        risk = "extreme"
    elif hot:
        risk = "high"
    elif pm:
        risk = "moderate"
    else:
        risk = "low"
    return {"ground": ground, "hour": local_hour(time_str),
            "extreme_city": hot, "afternoon": pm,
            "risk": risk, "score": RISK_SCORE[risk]}


def team_exposure(fixtures) -> list[dict]:
    """Per team: heat exposure across its group matches. fixtures is a DataFrame with
    group rows (round contains 'Matchday'), columns team1/team2/ground/time."""
    g = fixtures[fixtures["round"].astype(str).str.contains("Matchday", na=False)]
    acc: dict[str, dict] = {}
    for _, m in g.iterrows():
        h = match_heat(m.get("ground"), m.get("time"))
        for t in (m.get("team1"), m.get("team2")):
            if not isinstance(t, str):
                continue
            a = acc.setdefault(t, {"team": t, "score": 0, "extreme": 0, "afternoon": 0,
                                   "n": 0, "games": []})
            a["score"] += h["score"]; a["n"] += 1
            a["extreme"] += int(h["risk"] == "extreme")
            a["afternoon"] += int(h["afternoon"])
            a["games"].append({"vs": m.get("team2") if t == m.get("team1") else m.get("team1"),
                               "ground": h["ground"], "hour": h["hour"], "risk": h["risk"]})
    return sorted(acc.values(), key=lambda r: (-r["score"], -r["extreme"]))
