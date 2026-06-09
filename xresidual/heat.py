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


# --- Knockout-stage heat: the schedule doesn't ease off, it intensifies ----------- #
# The bracket is a fixed tree: R32 slots are coded 1A/2B/3X..., later rounds chain via
# W<match#>. Venues are slot-assigned, so a team's whole knockout VENUE path is
# deterministic the moment it finishes 1st/2nd in its group (opponents don't change it).

def knockout_matches(fixtures) -> list[dict]:
    """Parse knockout fixtures into bracket matches: a 1-based number (W<num> refers to
    it), the two slot codes (e.g. '1A', '2B', '3C/D/F', 'W74'), and the heat read."""
    df = fixtures.reset_index(drop=True)
    out = []
    for i, m in df.iterrows():
        if "Matchday" in str(m.get("round", "")):
            continue
        h = match_heat(m.get("ground"), m.get("time"))
        out.append({"num": i + 1, "round": str(m.get("round")),
                    "slot1": str(m.get("team1")), "slot2": str(m.get("team2")),
                    "ground": h["ground"], "hour": h["hour"],
                    "risk": h["risk"], "score": h["score"]})
    return out


def knockout_path(fixtures, start_slot: str) -> list[dict]:
    """The fixed venue path from `start_slot` (e.g. '1A' or '2A') through the bracket to
    the final. Deterministic in venue regardless of opponents. Returns matches on path."""
    kms = knockout_matches(fixtures)
    cur = next((m for m in kms if start_slot in (m["slot1"], m["slot2"])), None)
    path, seen = [], set()
    while cur and cur["num"] not in seen:
        seen.add(cur["num"]); path.append(cur)
        win = f"W{cur['num']}"
        cur = next((m for m in kms if win in (m["slot1"], m["slot2"])), None)
    return path


def path_load(fixtures, start_slot: str) -> dict:
    """Cumulative knockout heat along a team's win-out bracket path from `start_slot`."""
    path = knockout_path(fixtures, start_slot)
    return {"start": start_slot, "rounds": len(path),
            "ko_score": sum(m["score"] for m in path),
            "ko_extreme": sum(1 for m in path if m["risk"] == "extreme"),
            "path": [{"round": m["round"], "ground": m["ground"], "risk": m["risk"]} for m in path]}


def stage_intensity(fixtures) -> dict:
    """Afternoon / extreme-city / both shares, group stage vs knockouts. The structural
    finding: the dangerous afternoon-in-an-extreme-city share roughly doubles in the KOs."""
    def stats(sub):
        n = len(sub)
        if not n:
            return {"n": 0}
        aft = sum(is_afternoon(m.get("time")) for _, m in sub.iterrows())
        ext = sum(is_extreme_city(m.get("ground")) for _, m in sub.iterrows())
        both = sum(is_afternoon(m.get("time")) and is_extreme_city(m.get("ground"))
                   for _, m in sub.iterrows())
        return {"n": n, "afternoon_pct": round(100 * aft / n),
                "extreme_pct": round(100 * ext / n), "both_pct": round(100 * both / n)}
    is_g = fixtures["round"].astype(str).str.contains("Matchday", na=False)
    return {"group": stats(fixtures[is_g]), "knockout": stats(fixtures[~is_g])}
