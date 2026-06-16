#!/usr/bin/env python3
"""v3 per-game W/D/L — format-conditional draw lift, run FORWARD in parallel with v1 + v2.

    python scripts/build_matches_v3.py

v3 = v2's zero-inflated Skellam (Karlis-Ntzoufras) PLUS a closeness-conditional draw lift for the
48-team best-thirds format, which structurally rewards drawing (a team can advance on three draws;
cf. Slovenia at Euro 2024, P3 W0 D3). The lift `omega_eff = 0.04 + 0.10*(1 - |p1 - p2|)` adds draw
mass in EVEN matches (where both teams are content with a point) and barely touches mismatches (so a
93%-favourite stays ~93%). Validated OUT-OF-SAMPLE: improves W/D/L log-loss on the expanded-format
Euros (Wf=0.10 optimal, 1.026 -> 1.017) and is net-harmful on the old 32-team WCs (Wf=0 optimal) —
i.e. genuinely format-specific, not a universal draw-bump. See NOTES.md / build_matches_v2.

Honesty rule (same as v2): v3 PRE-COMMITS only games whose kickoff is still in the FUTURE, in its OWN
forward-only ledger. So this is a clean live A/B: v2 (omega=0.04, the control) vs v3 (format lift, the
treatment), graded head-to-head ONLY on games BOTH pre-committed. Neither v1 nor v2 is touched. The
v2 ledger had already locked the group forecasts before the lift was found, which is exactly why v3
starts a fresh ledger rather than editing v2's record. Emits docs/data/matches_v3.js + a v2-vs-v3 board.
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
# v3 only READS v1's frozen model (group_sim lambdas); the W/D/L layer lives HERE, so nothing in
# xresidual/ (the frozen v1 core) is modified.
from xresidual import baseline, data, elo, group_sim, wc2026_teams as W  # noqa: E402
from blend import blended_ratings  # noqa: E402
from match_scheduler import kickoff_utc  # noqa: E402
from v2_calibrate import scale_wdl  # noqa: E402  (shared temperature calibration; fit on old-format backtest, unaffected by the lift)

V2_LEDGER = os.path.join(ROOT, "paper", "match_forecasts_v2.jsonl")   # control, for the head-to-head
V3_LEDGER = os.path.join(ROOT, "paper", "match_forecasts_v3.jsonl")   # v3's own forward-only ledger
OUT = os.path.join(ROOT, "docs", "data", "matches_v3.js")
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")

OMEGA = 0.04          # base zero-inflation (same as v2)
WF_FORMAT = 0.10      # expanded-format closeness-scaled draw lift; validated out-of-sample on the Euros


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


def _omega_eff(lh, la):
    """Closeness-scaled draw mass for the expanded-format group stage. Even matches (|p_home -
    p_away| small) get the full WF_FORMAT lift; mismatches get almost none, so favourites are kept."""
    h, a = float(sk.sf(0, lh, la)), float(sk.cdf(-1, lh, la))   # base Skellam win probs
    return min(0.5, OMEGA + WF_FORMAT * (1 - abs(h - a)))


def _wdl_zism(lh, la, omega):
    """W/D/L from the zero-inflated Skellam: the Skellam goal-difference distribution with extra
    mass `omega` at d=0."""
    d, h, a = float(sk.pmf(0, lh, la)), float(sk.sf(0, lh, la)), float(sk.cdf(-1, lh, la))
    return (1 - omega) * h, omega + (1 - omega) * d, (1 - omega) * a


def main() -> int:
    df = data.load_results()
    res = elo.build_ratings(df)
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)

    fx = pd.read_csv(FIXTURES)
    grp = fx[fx["group"].astype(str).str.startswith("Group")].copy()
    now = datetime.now(timezone.utc)

    # v3 forecasts: format-lifted ZISM W/D/L, committed ONLY for games not yet kicked off (forward-only)
    committed = _load(V3_LEDGER)
    new = 0
    for row in grp.itertuples(index=False):
        key = f"{row.date}|{W.canonical(row.team1)}|{W.canonical(row.team2)}"
        if key in committed:
            continue
        ko = kickoff_utc(row.date, row.time)
        if ko is None or ko <= now:               # never pre-commit a played/in-progress game
            continue
        l1, l2 = group_sim._match_lambdas(row.team1, row.team2, row.ground, ratings, params)
        p1, pdraw, p2 = _wdl_zism(l1, l2, _omega_eff(l1, l2))   # closeness-conditional draw lift
        p1, pdraw, p2 = scale_wdl(p1, pdraw, p2)
        rec = {"key": key, "version": "v3", "committed": now.isoformat(),
               "md": str(row.round), "group": str(row.group).replace("Group ", ""),
               "date": str(row.date), "t1": W.canonical(row.team1), "t2": W.canonical(row.team2),
               "p1": round(p1, 4), "pd": round(pdraw, 4), "p2": round(p2, 4)}
        committed[key] = rec
        with open(V3_LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        new += 1

    # results join
    d = df[df["tournament"] == "FIFA World Cup"].copy()
    d = d[pd.to_datetime(d["date"]) >= pd.Timestamp("2026-06-11")]
    bridge = lambda t: W.elo_name(W.canonical(t))
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
            probs = {"t1": rec["p1"], "draw": rec["pd"], "t2": rec["p2"]}
            played += 1
            hits += (max(probs, key=probs.get) == outcome)
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

    # head-to-head: v2 (control) vs v3 (treatment), only games BOTH pre-committed AND played
    v2 = _load(V2_LEDGER)
    common = {k for k in committed if k in v2}
    v2g = grade({k: v2[k] for k in common})
    v3g = grade({k: committed[k] for k in common})
    n = v3g[0]
    payload = {"asof": now.isoformat(), "n": len(matches), "omega": OMEGA, "wf_format": WF_FORMAT,
               "head_to_head": {"n_resolved": n,
                                "v2": {"logloss": round(v2g[2] / n, 4), "brier": round(v2g[3] / n, 4)} if n else None,
                                "v3": {"logloss": round(v3g[2] / n, 4), "brier": round(v3g[3] / n, 4)} if n else None},
               "matches": matches}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.GAMESV3 = " + json.dumps(payload, separators=(",", ":")) + ";\n")
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(matches)} games, {new} new v3 commits · "
          f"head-to-head resolved={n}" + (f" v2 LL {v2g[2]/n:.3f} vs v3 LL {v3g[2]/n:.3f}" if n else " (none resolved yet)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
