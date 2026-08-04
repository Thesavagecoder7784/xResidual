#!/usr/bin/env python3
"""Does the cross-venue lead survive when events are anchored to an EXOGENOUS goal clock?
    -> writeups/_clock_verified_results.json

    python scripts/clock_verified_leadlag.py

WHY. The headline lead-lag result is estimated on events DETECTED ON THE TAPE as decisive
mid-price shocks. Section 4 concedes what that costs: detection over-fires, because a market
repricing the game clock on a level match produces moves a size-and-persistence detector cannot
tell from a goal. The identification claim ("goals are exogenous") therefore applies to the
underlying event stream, not to the event set actually estimated on -- the events are defined by
price movement, which is endogenous to price by construction.

This script closes that gap for the subset where it can be closed. It keeps only those detected
events that line up with a goal in data/wc_goals_espn.json -- a public match feed independent of
the price data, reconciled 104/104 against the official scorelines -- and re-runs the
which-venue-first count on that subsample. If the ordering holds there, the lead is not an
artifact of what the detector chose to fire on.

CLOCK MODEL, fixed in advance and applied uniformly (no per-match fitting, which would let the
offset be tuned until events matched):
  * event wall-minute = (t_ms - kickoff_ms) / 60000, kickoff from data/wc2026_fixtures.csv
  * first half  (goal minute <= 45): expect the repricing in [m - 1, m + 6]
  * second half (goal minute >  45): expect it in [m + HT_LO, m + HT_HI], HT ~ 15 min break
  Calibrated on a held-out match (Algeria vs Austria: clock goals 28/45/55/60 land at event
  minutes 28.4/44.8/69.5/75.6 -- no offset in the first half, +15 in the second).

Reads derived per-match archives and public match facts only. Writes no venue data.
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import json
import os
import re
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEADLAG = os.path.join(ROOT, "viz", "market", "leadlag")
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
CLOCK = os.path.join(ROOT, "data", "wc_goals_espn.json")
OUT = os.path.join(ROOT, "writeups", "_clock_verified_results.json")

PRE_MIN, POST_MIN = 1.0, 6.0     # first-half window around the clock minute
HT_LO, HT_HI = 10.0, 22.0        # second-half window: halftime break plus first-half stoppage

# Feed-name bridge. THREE sources spell teams three ways and a silent miss here shows up as
# "no clock" rather than as an error, so the mismatches are enumerated explicitly:
#   leadlag tape : "Dr Congo" AND "Congo Dr", "Bosnia Herzegovina"
#   goal clock   : "Congo DR", "Bosnia-Herzegovina", "Czechia", "Turkiye", "United States"
#   fixtures     : "DR Congo", "Bosnia & Herzegovina", "Czech Republic", "Turkey", "USA"
# Punctuation normalisation handles Bosnia; the rest need real aliases.
ALIAS = {
    "congo dr": "dr congo",
    "democratic republic of congo": "dr congo",
    "czechia": "czech republic",
    "turkiye": "turkey",
    "united states": "usa",
    "united states of america": "usa",
}


def _norm(s: str) -> str:
    """Accent-fold, drop punctuation, collapse whitespace, then alias. Accents are folded rather
    than stripped to space: 'Turkiye' must not become 't rkiye', which silently misses."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    s = " ".join(t for t in s.split() if t != "and")
    return ALIAS.get(s, s)


def parse_kick(date: str, timestr: str) -> int | None:
    m = re.match(r"(\d{1,2}):(\d{2})\s*UTC([+-]\d{1,2})", (timestr or "").strip())
    if not m:
        return None
    h, mi, off = int(m.group(1)), int(m.group(2)), int(m.group(3))
    y, mo, d = map(int, date.split("-"))
    tz = dt.timezone(dt.timedelta(hours=off))
    return int(dt.datetime(y, mo, d, h, mi, tzinfo=tz).timestamp() * 1000)


def kickoffs() -> dict:
    out = {}
    for r in csv.DictReader(open(FIXTURES)):
        k = parse_kick(r.get("date", ""), r.get("time", ""))
        if k:
            out[frozenset((_norm(r["team1"]), _norm(r["team2"])))] = k
    return out


def clock_index() -> dict:
    raw = json.load(open(CLOCK))
    out = {}
    for name, v in raw.items():
        parts = [p for p in name.split(" vs ")]
        if len(parts) == 2:
            out[frozenset((_norm(parts[0]), _norm(parts[1])))] = v
    return out


def windows(minutes: list[int]) -> list[tuple[float, float]]:
    w = []
    for m in minutes:
        if m <= 45:
            w.append((m - PRE_MIN, m + POST_MIN))
        else:
            w.append((m + HT_LO, m + HT_HI))
    return w


def main() -> int:
    kick, clock = kickoffs(), clock_index()
    tot = dict(matches=0, ev_all=0, ev_ver=0, poly_all=0, poly_ver=0, kal_all=0, kal_ver=0)
    # events_but_no_leader: matches whose events are all synchronous or ungated. Counted, not
    # dropped -- an unreported skip is how coverage silently shrinks.
    per_match, skipped = [], dict(no_kickoff=0, no_clock=0, no_goals=0, no_events=0,
                                  events_but_no_leader=0, bad_name=0)

    for f in sorted(glob.glob(os.path.join(LEADLAG, "*.json"))):
        try:
            d = json.load(open(f))
        except Exception:  # noqa: BLE001
            continue
        name = d.get("match") or ""
        parts = name.split(" vs ")
        if len(parts) != 2:
            skipped["bad_name"] += 1; continue
        key = frozenset((_norm(parts[0]), _norm(parts[1])))
        k = kick.get(key)
        cl = clock.get(key)
        if k is None:
            skipped["no_kickoff"] += 1; continue
        if cl is None:
            skipped["no_clock"] += 1; continue
        goals = [g["minute"] for g in cl.get("goals", [])]
        if not goals:
            skipped["no_goals"] += 1; continue
        evs = [e for p in d.get("pairs", []) for e in p.get("events", [])]
        if not evs:
            skipped["no_events"] += 1; continue

        wins = windows(goals)
        m_all = m_ver = p_all = p_ver = ka = kv = 0
        for e in evs:
            # The archives spell it 'polymarket'/'kalshi'/'synchronous'. Synchronous events
            # carry no lead and are excluded from the decisive count, as in the pooled result.
            leader = ((e.get("lead") or {}).get("leader") or "").lower()
            if leader == "polymarket":
                leader = "poly"
            if leader not in ("poly", "kalshi"):
                continue
            wall = (e["t_ms"] - k) / 60000.0
            ver = any(lo <= wall <= hi for lo, hi in wins)
            m_all += 1
            p_all += leader == "poly"; ka += leader == "kalshi"
            if ver:
                m_ver += 1
                p_ver += leader == "poly"; kv += leader == "kalshi"
        if m_all == 0:
            skipped["events_but_no_leader"] += 1; continue
        tot["matches"] += 1
        tot["ev_all"] += m_all; tot["ev_ver"] += m_ver
        tot["poly_all"] += p_all; tot["poly_ver"] += p_ver
        tot["kal_all"] += ka; tot["kal_ver"] += kv
        per_match.append(dict(match=name, n_all=m_all, n_ver=m_ver,
                              poly_ver=p_ver, kalshi_ver=kv))

    lead_all = tot["poly_all"] / max(1, tot["poly_all"] + tot["kal_all"])
    lead_ver = tot["poly_ver"] / max(1, tot["poly_ver"] + tot["kal_ver"])

    # Per-match sign test on the CLOCK-VERIFIED events only: the cluster-immune unit.
    lean = [(m["poly_ver"] > m["kalshi_ver"]) - (m["poly_ver"] < m["kalshi_ver"])
            for m in per_match if m["n_ver"] > 0]
    npos, nneg = sum(1 for x in lean if x > 0), sum(1 for x in lean if x < 0)
    n_used = npos + nneg
    try:
        from scipy.stats import binomtest
        p_sign = binomtest(npos, n_used, 0.5).pvalue if n_used else None
    except Exception:  # noqa: BLE001
        from math import comb
        p_sign = (sum(comb(n_used, i) for i in range(npos, n_used + 1)) / 2 ** n_used * 2
                  if n_used else None)

    res = dict(
        n_matches=tot["matches"],
        n_events_all=tot["ev_all"], n_events_clock_verified=tot["ev_ver"],
        verified_share=round(tot["ev_ver"] / max(1, tot["ev_all"]), 4),
        poly_share_all=round(lead_all, 4), poly_share_clock_verified=round(lead_ver, 4),
        poly_ver=tot["poly_ver"], kalshi_ver=tot["kal_ver"],
        per_match_lean=f"{npos} of {n_used}",
        per_match_sign_p=p_sign,
        skipped=skipped,
        window=dict(first_half=[-PRE_MIN, POST_MIN], second_half=[HT_LO, HT_HI]),
        note=("Detected repricing events retained only when they fall in an exogenous window "
              "around a goal minute from data/wc_goals_espn.json (public match feed, reconciled "
              "104/104 to the scorelines). Clock model fixed in advance, applied uniformly, no "
              "per-match fitting. Tests whether the Polymarket-first ordering is an artifact of "
              "detector selection."),
    )
    # Window sensitivity, recorded rather than left as a researcher degree of freedom: the
    # windows above were chosen from one calibration match, so the reader gets the whole sweep.
    sweep = []
    for pre, post, lo, hi in [(1, 6, 10, 22), (0.5, 3, 12, 18), (1, 10, 8, 25),
                              (2, 4, 13, 17), (0, 5, 14, 20), (1, 6, 14, 16)]:
        pv = kv2 = ev = 0
        for f in sorted(glob.glob(os.path.join(LEADLAG, "*.json"))):
            try:
                d = json.load(open(f))
            except Exception:  # noqa: BLE001
                continue
            parts = (d.get("match") or "").split(" vs ")
            if len(parts) != 2:
                continue
            key = frozenset((_norm(parts[0]), _norm(parts[1])))
            k, cl = kick.get(key), clock.get(key)
            if k is None or cl is None or not cl.get("goals"):
                continue
            gm = [g["minute"] for g in cl["goals"]]
            wins = [((m - pre, m + post) if m <= 45 else (m + lo, m + hi)) for m in gm]
            for p in d.get("pairs", []):
                for e in p.get("events", []):
                    ld = ((e.get("lead") or {}).get("leader") or "").lower()
                    ld = "poly" if ld == "polymarket" else ld
                    if ld not in ("poly", "kalshi"):
                        continue
                    wall = (e["t_ms"] - k) / 60000.0
                    if any(a <= wall <= b for a, b in wins):
                        ev += 1
                        pv += ld == "poly"; kv2 += ld == "kalshi"
        sweep.append(dict(first_half=[-pre, post], second_half=[lo, hi], n_verified=ev,
                          poly_share=round(pv / max(1, pv + kv2), 4)))
    res["window_sensitivity"] = sweep
    shares = [s["poly_share"] for s in sweep]
    res["poly_share_clock_verified_range"] = [min(shares), max(shares)]

    print(f"  matches            : {res['n_matches']}   (skipped: {skipped})")
    print(f"  events all / verif : {res['n_events_all']} / {res['n_events_clock_verified']}"
          f"  ({res['verified_share']:.1%} retained)")
    print(f"  poly share  all    : {res['poly_share_all']:.1%}")
    print(f"  poly share  CLOCK  : {res['poly_share_clock_verified']:.1%}"
          f"   ({res['poly_ver']} vs {res['kalshi_ver']})")
    print(f"  per-match lean     : {res['per_match_lean']}   sign p = {p_sign}")
    with open(OUT, "w") as fh:
        json.dump(res, fh, indent=1)
    print(f"  wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
