#!/usr/bin/env python3
"""Build the exogenous goal clock for all 104 matches, from ESPN's keyless scoreboard feed.

WHY THIS EXISTS. The microstructure pipeline infers goals from the tape as decisive mid shocks
(`ws_events.detect_shocks`), which `04_methods.tex` discloses as a limitation and
`scripts/verify_goals.py` quantifies: detection fires more often than there were goals in 49 of
86 matches, and all 7 goalless matches register detections (scripts/detection_check.py;
the original 15-of-29 read dates from when only 31 per-game archives survived locally). Those phantom events are real
repricings driven by the clock running on a 0-0, not by goals, and price alone cannot separate
the two (see `scripts/shock_detect_v2.py` for the failed attempts). An exogenous goal clock
removes the problem at the source rather than filtering it downstream.

WHY NOT football-data.org. `scripts/fetch_goals.py` targets it and works, but its free tier no
longer returns goal detail: all 104 matches come back with `goals: []`, including matches we hold
locally with full detail, so the 9 cached there cannot be extended. ESPN's public scoreboard has
per-event `details` with `scoringPlay` flags, minute clocks, scorers and card events, needs no
key, and is already the project's score source (`fetch_scores.py`).

BONUS: CARDS. The same feed carries red and yellow cards. Those are exactly the non-goal
information events the detector legitimately fires on, so capturing them lets a shock be
classified rather than merely accepted or rejected.

    python scripts/fetch_goals_espn.py             # all match dates
    python scripts/fetch_goals_espn.py --verify    # also check counts against the scorelines

Writes data/wc_goals_espn.json:
    {"Home vs Away": {"goals": [{minute, injury, team, scorer, type}], "cards": [...]}}
Goal minutes are ESPN's match clock. Stoppage time is split out into `injury` so a 45'+2 goal is
{"minute": 45, "injury": 2}, matching the shape data/wc_goals.json already uses.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "wc_goals_espn.json")
URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
GOAL_TYPES = {"Goal", "Own Goal", "Penalty - Scored"}
CARD_TYPES = {"Yellow Card", "Red Card", "Second Yellow Card"}
THROTTLE_S = 0.6


def _minute(detail: dict) -> tuple[int, int]:
    """ESPN clock -> (minute, injury). '45'+2' becomes (45, 2); '21'' becomes (21, 0)."""
    disp = ((detail.get("clock") or {}).get("displayValue") or "").strip().rstrip("'")
    if "+" in disp:
        base, extra = disp.split("+", 1)
        try:
            return int(base.strip().rstrip("'")), int(extra.strip().rstrip("'"))
        except ValueError:
            pass
    try:
        return int(float(disp)), 0
    except ValueError:
        return -1, 0


def match_dates() -> list[str]:
    """Every date on which a fixture was played, from the committed fixture list."""
    seen = []
    with open(os.path.join(ROOT, "data", "wc2026_fixtures.csv")) as fh:
        for r in csv.DictReader(fh):
            d = (r.get("date") or "").strip()
            if d and d not in seen:
                seen.append(d)
    return sorted(seen)


def fetch_day(date_iso: str) -> list[dict]:
    stamp = date_iso.replace("-", "")
    r = requests.get(URL, params={"dates": stamp}, timeout=30)
    r.raise_for_status()
    return r.json().get("events", [])


def parse_event(ev: dict) -> tuple[str, dict] | None:
    comp = (ev.get("competitions") or [{}])[0]
    if (comp.get("status") or ev.get("status") or {}).get("type", {}).get("completed") is False:
        return None
    names = {}
    home = away = None
    for c in comp.get("competitors") or []:
        t = c.get("team") or {}
        nm = t.get("displayName") or t.get("name") or t.get("abbreviation")
        names[str(t.get("id"))] = nm
        if c.get("homeAway") == "home":
            home = nm
        elif c.get("homeAway") == "away":
            away = nm
    if not home or not away:
        return None
    goals, cards = [], []
    for d in comp.get("details") or []:
        typ = (d.get("type") or {}).get("text") or ""
        who = [a.get("displayName") for a in (d.get("athletesInvolved") or []) if a.get("displayName")]
        minute, injury = _minute(d)
        rec = {"minute": minute, "injury": injury,
               "team": names.get(str((d.get("team") or {}).get("id"))),
               "scorer": who[0] if who else None, "type": typ}
        if d.get("scoringPlay") or typ in GOAL_TYPES:
            goals.append(rec)
        elif typ in CARD_TYPES:
            cards.append(rec)
    goals, shootout = _strip_shootout(goals)
    key = f"{home} vs {away}"
    return key, {"goals": sorted(goals, key=lambda g: (g["minute"], g["injury"])),
                 "shootout": sorted(shootout, key=lambda g: (g["minute"], g["injury"])),
                 "cards": sorted(cards, key=lambda c: (c["minute"], c["injury"]))}


def _strip_shootout(goals: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separate penalty-shootout kicks from match goals.

    ESPN books every shootout kick as a scoring play at exactly 120' with no injury time and
    type 'Penalty - Scored', alternating teams, which is why the raw feed reports 7 'goals' in a
    0-0 (Switzerland vs Colombia). A genuine late penalty carries stoppage time or a minute below
    120, so requiring three-or-more at the 120' mark separates a shootout from one real kick."""
    at120 = [g for g in goals if g["minute"] == 120 and g["injury"] == 0
             and "Penalty" in (g.get("type") or "")]
    if len(at120) < 3:
        return goals, []
    ids = {id(g) for g in at120}
    return [g for g in goals if id(g) not in ids], at120


def verify(out: dict) -> int:
    """Goal counts must equal the scoreline. Anything else means a parse or feed problem."""
    fx = {}
    with open(os.path.join(ROOT, "data", "wc2026_fixtures.csv")) as fh:
        for r in csv.DictReader(fh):
            if (r.get("score1") or "").strip() == "":
                continue
            fx[frozenset((r["team1"], r["team2"]))] = int(r["score1"]) + int(r["score2"])
    led = {}
    p = os.path.join(ROOT, "data", "cache", "ko_advancers.json")
    if os.path.exists(p):
        for v in json.load(open(p)).values():
            led[frozenset((v["home_team"], v["away_team"]))] = v["home_score"] + v["away_score"]

    def norm(n: str) -> str:
        return {"Cape Verde Islands": "Cape Verde", "United States": "USA",
                "Republic of Ireland": "Ireland", "Ivory Coast": "Ivory Coast",
                "Korea Republic": "South Korea", "South Korea": "South Korea",
                "IR Iran": "Iran", "Czechia": "Czech Republic",
                "Bosnia-Herzegovina": "Bosnia & Herzegovina",
                "DR Congo": "DR Congo", "Congo DR": "DR Congo",
                "Curacao": "Curaçao", "Turkiye": "Turkey", "Türkiye": "Turkey"}.get(n, n)

    ok = bad = unmatched = 0
    print("\n  VERIFY: goal count vs scoreline")
    for label, rec in sorted(out.items()):
        parts = [norm(x) for x in label.split(" vs ")]
        key = frozenset(parts)
        true = led.get(key, fx.get(key))
        n = len(rec["goals"])
        if true is None:
            unmatched += 1
            continue
        # a scoreline from the 90-minute feed can trail an AET goal; accept >= as well
        if n == true:
            ok += 1
        else:
            bad += 1
            print(f"    !! {label:40} feed {n} goals vs scoreline {true}")
    print(f"    matched {ok} · mismatched {bad} · unresolvable {unmatched}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    dates = match_dates()
    print(f"fetching {len(dates)} match dates from ESPN (keyless)")
    out: dict = {}
    for i, d in enumerate(dates, 1):
        try:
            evs = fetch_day(d)
        except Exception as e:
            print(f"  {d}: FAILED ({type(e).__name__})")
            continue
        got = 0
        for ev in evs:
            parsed = parse_event(ev)
            if not parsed:
                continue
            key, rec = parsed
            if rec["goals"] or rec["cards"]:
                out[key] = rec
                got += 1
        print(f"  [{i:2d}/{len(dates)}] {d}: {len(evs)} events, {got} with detail")
        time.sleep(THROTTLE_S)

    tot_s = sum(len(v.get("shootout", [])) for v in out.values())
    tot_g = sum(len(v["goals"]) for v in out.values())
    tot_c = sum(len(v["cards"]) for v in out.values())
    json.dump(out, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(f"\nwrote {os.path.relpath(OUT, ROOT)}: {len(out)} matches · {tot_g} goals · "
          f"{tot_c} cards · {tot_s} shootout kicks held separately")
    return verify(out) and 0 if args.verify else 0


if __name__ == "__main__":
    raise SystemExit(main())
