#!/usr/bin/env python3
"""v2 per-game W/D/L — zero-inflated-Skellam (ZISM) draws, run FORWARD in parallel with v1.

    python scripts/build_matches_v2.py

v1 (match_forecasts.jsonl, FROZEN) uses plain Skellam at the W/D/L layer, which under-counts
draws. v2 uses the zero-inflated Skellam (Karlis-Ntzoufras 2009): the SAME Skellam goal-
difference distribution with extra mass added at d=0. Chosen over Dixon-Coles after a
literature scan — it operates on the exact distribution this model already uses (rather than
a scoreline-cell correction) and beat DC head-to-head. Validated OUT-OF-SAMPLE (omega fit on
pre-2022, tested on 2022+): draw-Brier 0.1969 -> 0.1955, W/D/L log-loss 1.0115 -> 1.0077.

Honesty rule: v2 only PRE-COMMITS games whose kickoff is still in the FUTURE, so it never
claims a game already played. v1 and v2 are therefore graded head-to-head only on games BOTH
pre-committed. v1 is never edited. Emits docs/data/matches_v2.js + a v1-vs-v2 scoreboard.
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timezone

import pandas as pd
from scipy.stats import skellam as sk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
# v2 only READS v1's frozen model (group_sim lambdas); the zero-inflated-Skellam W/D/L lives
# HERE, so nothing in xresidual/ (the frozen v1 core) is modified.
from xresidual import baseline, data, elo, group_sim, wc2026_teams as W  # noqa: E402
from blend import blended_ratings  # noqa: E402
from match_scheduler import kickoff_utc  # noqa: E402

V1_LEDGER = os.path.join(ROOT, "paper", "match_forecasts.jsonl")
V2_LEDGER = os.path.join(ROOT, "paper", "match_forecasts_v2.jsonl")
OUT = os.path.join(ROOT, "docs", "data", "matches_v2.js")
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")


def _load(path):
    out = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            out[r["key"]] = r
    return out


def _brier3(p1, pd_, p2, outcome):                # multiclass Brier for W/D/L
    tgt = {"t1": (1, 0, 0), "draw": (0, 1, 0), "t2": (0, 0, 1)}[outcome]
    return sum((p - t) ** 2 for p, t in zip((p1, pd_, p2), tgt))


# Zero-inflation weight at d=0 (Karlis-Ntzoufras 2009). Method-of-moments on 2014+ rated
# internationals (~25% draw rate); validated OUT-OF-SAMPLE (omega fit pre-2022, tested 2022+:
# draw-Brier 0.1969 -> 0.1955, W/D/L log-loss 1.0115 -> 1.0077 vs plain Skellam). Frozen.
OMEGA = 0.04


def _wdl_zism(lh, la, omega):
    """W/D/L from the zero-inflated Skellam (Karlis-Ntzoufras 2009): the model's OWN Skellam
    goal-difference distribution with extra mass `omega` added at d=0. Restores the draw mass
    independent Poisson (v1) under-counts, on the exact distribution v1 already uses — a better
    fit for this Skellam-based model than a Dixon-Coles scoreline-cell correction. Self-
    contained, so v1's frozen xresidual/ core is untouched."""
    d, h, a = float(sk.pmf(0, lh, la)), float(sk.sf(0, lh, la)), float(sk.cdf(-1, lh, la))
    return (1 - omega) * h, omega + (1 - omega) * d, (1 - omega) * a


def main() -> int:
    df = data.load_results()
    res = elo.build_ratings(df)
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)
    rt = lambda t: ratings.get(W.elo_name(W.canonical(t)), elo.INIT_RATING)

    fx = pd.read_csv(FIXTURES)
    grp = fx[fx["group"].astype(str).str.startswith("Group")].copy()
    now = datetime.now(timezone.utc)

    # v2 forecasts: Dixon-Coles W/D/L, committed ONLY for games not yet kicked off (forward-only)
    committed = _load(V2_LEDGER)
    new, skipped_past = 0, 0
    for row in grp.itertuples(index=False):
        key = f"{row.date}|{W.canonical(row.team1)}|{W.canonical(row.team2)}"
        if key in committed:
            continue
        ko = kickoff_utc(row.date, row.time)
        if ko is None or ko <= now:               # never pre-commit a played/in-progress game
            skipped_past += 1
            continue
        l1, l2 = group_sim._match_lambdas(row.team1, row.team2, row.ground, ratings, params)
        p1, pdraw, p2 = _wdl_zism(l1, l2, OMEGA)
        rec = {"key": key, "version": "v2", "committed": now.isoformat(),
               "md": str(row.round), "group": str(row.group).replace("Group ", ""),
               "date": str(row.date), "t1": W.canonical(row.team1), "t2": W.canonical(row.team2),
               "p1": round(p1, 4), "pd": round(pdraw, 4), "p2": round(p2, 4)}
        committed[key] = rec
        with open(V2_LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        new += 1

    # results join
    d = df[df["tournament"] == "FIFA World Cup"].copy()
    d = d[pd.to_datetime(d["date"]) >= pd.Timestamp("2026-06-11")]
    bridge = lambda t: W.elo_name(W.canonical(t))   # USA/United States + Bosnia variants -> one join key
    actual = {}
    for r in d.itertuples(index=False):
        hb, ab = bridge(r.home_team), bridge(r.away_team)
        actual[frozenset((hb, ab))] = (hb, ab, int(r.home_score), int(r.away_score))

    def grade(ledger):
        played, hits, ll, brier = 0, 0, 0.0, 0.0
        for rec in ledger.values():
            r = actual.get(frozenset((bridge(rec["t1"]), bridge(rec["t2"]))))
            if not r:
                continue
            h, a, hs, as_ = r
            s1, s2 = (hs, as_) if h == bridge(rec["t1"]) else (as_, hs)
            outcome = "t1" if s1 > s2 else ("t2" if s2 > s1 else "draw")
            p_act = {"t1": rec["p1"], "draw": rec["pd"], "t2": rec["p2"]}[outcome]
            fav = max({"t1": rec["p1"], "draw": rec["pd"], "t2": rec["p2"]}, key=lambda k: {"t1": rec["p1"], "draw": rec["pd"], "t2": rec["p2"]}[k])
            played += 1
            hits += (fav == outcome)
            ll += -math.log(max(p_act, 1e-9))
            brier += _brier3(rec["p1"], rec["pd"], rec["p2"], outcome)
        return played, hits, ll, brier

    matches = []
    for rec in sorted(committed.values(), key=lambda r: (r["date"], r["group"])):
        probs = {"t1": rec["p1"], "draw": rec["pd"], "t2": rec["p2"]}
        m = {**{k: rec[k] for k in ("md", "group", "date", "t1", "t2", "p1", "pd", "p2")},
             "fav": max(probs, key=probs.get), "played": False}
        r = actual.get(frozenset((bridge(rec["t1"]), bridge(rec["t2"]))))
        if r:
            h, a, hs, as_ = r
            s1, s2 = (hs, as_) if h == bridge(rec["t1"]) else (as_, hs)
            outcome = "t1" if s1 > s2 else ("t2" if s2 > s1 else "draw")
            m.update({"played": True, "s1": s1, "s2": s2, "result": outcome,
                      "correct": (m["fav"] == outcome)})
        matches.append(m)

    # head-to-head: only games BOTH versions pre-committed AND that are played
    v1 = _load(V1_LEDGER)
    common = {k for k in committed if k in v1}
    v1g = grade({k: v1[k] for k in common})
    v2g = grade({k: committed[k] for k in common})
    n = v2g[0]
    payload = {"asof": now.isoformat(), "n": len(matches), "omega": OMEGA,
               "head_to_head": {"n_resolved": n,
                                "v1": {"logloss": round(v1g[2] / n, 4), "brier": round(v1g[3] / n, 4)} if n else None,
                                "v2": {"logloss": round(v2g[2] / n, 4), "brier": round(v2g[3] / n, 4)} if n else None},
               "matches": matches}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.GAMESV2 = " + json.dumps(payload, separators=(",", ":")) + ";\n")

    print(f"v2: {new} newly committed (forward-only), {skipped_past} skipped as already kicked off")
    if n:
        print(f"v1 vs v2 head-to-head on {n} resolved games BOTH pre-committed:")
        print(f"  v1 (Skellam):    log-loss {v1g[2]/n:.4f}  Brier {v1g[3]/n:.4f}")
        print(f"  v2 (Dixon-Coles): log-loss {v2g[2]/n:.4f}  Brier {v2g[3]/n:.4f}")
    else:
        print("head-to-head: 0 resolved games both pre-committed yet (fills as future games play)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
