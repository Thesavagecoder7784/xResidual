#!/usr/bin/env python3
"""xG-flow lead PoC — the necessary-condition gate for the in-play "deserved-WP vs market" idea.

    python scripts/xgflow_poc.py

THE QUESTION. The trade thesis is: a side piling up xG/territory without scoring should see its
win-probability drift up, and maybe the market lags that slow signal. Before touching odds we test
the NECESSARY condition with free data: does accumulated xG actually *lead future goals*, over and
above the current scoreline? If a team is out-xG'ing its opponent but level on the board, does it
go on to outscore them in the rest of the match? If not, the whole idea is dead regardless of how
the market prices it.

DESIGN. StatsBomb open data, FIFA World Cup 2018 + 2022 (128 matches), REGULATION only (periods 1-2,
extra-time and shootouts excluded so this is a clean in-regulation WP test). For each match, signed
home-minus-away. At each checkpoint minute t we have (goal_diff_t, xg_diff_t); the label is the
goal-diff scored over the REMAINDER [t, full-time]. Pooled OLS:

    remaining_goal_diff ~ 1 + goal_diff_t + xg_diff_t

The coefficient on xg_diff_t is the test: > 0 and significant means xG leads future goals *beyond*
the scoreline (deserved -> actual), the green light to get the Betfair in-play odds and test the
market lag. We also report the sharp subset: situations where a team leads xG but is NOT ahead on
goals -- do they outscore the opponent in the remainder?

STAGE 2 (not here; needs a manual data pull): join Betfair historical in-play odds (minute last-
traded price, free tier, since 2016) and run the same stats->price lead-lag as the cross-venue
flagship. Betfair historical can't be fetched here (account-gated portal). Fork-forward: new pillar,
touches nothing under xresidual/.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
CACHE = os.path.join(ROOT, "data", "sb_cache")
OUT = os.path.join(ROOT, "writeups", "_xgflow_poc.json")
COMPS = [(43, 3, "WC2018"), (43, 106, "WC2022")]      # competition_id, season_id, label
CHECKPOINTS = [30, 45, 60, 75]
PRIMARY = 60                                          # one independent obs/match for the headline


def _get(url: str, cachekey: str | None = None):
    if cachekey:
        os.makedirs(CACHE, exist_ok=True)
        p = os.path.join(CACHE, cachekey)
        if os.path.exists(p):
            return json.load(open(p))
        d = requests.get(url, timeout=40).json()
        json.dump(d, open(p, "w"))
        return d
    return requests.get(url, timeout=40).json()


def timeline(mid: int, home: str, away: str) -> list[tuple]:
    """Regulation shots/goals as (minute, sign[+1 home/-1 away], xg, is_goal)."""
    evs = _get(f"{BASE}/events/{mid}.json", f"ev_{mid}.json")
    out = []
    for e in evs:
        if e.get("period", 9) not in (1, 2):                  # regulation only
            continue
        typ = e.get("type", {}).get("name")
        tm = e.get("team", {}).get("name")
        mn = e.get("minute", 0)
        if typ == "Shot":
            sh = e.get("shot", {})
            xg = sh.get("statsbomb_xg") or 0.0
            sgn = 1 if tm == home else -1
            out.append((mn, sgn, float(xg), sh.get("outcome", {}).get("name") == "Goal"))
        elif typ == "Own Goal Against":                       # own goal -> goal for the OTHER side
            sgn = -1 if tm == home else 1
            out.append((mn, sgn, 0.0, True))
    return out


def diffs_at(tl, t):
    gd = sum(s[1] for s in tl if s[0] < t and s[3])
    xd = sum(s[1] * s[2] for s in tl if s[0] < t)
    return gd, xd


def final_gd(tl):
    return sum(s[1] for s in tl if s[3])


def ols(y, X):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    s2 = (resid @ resid) / (n - k)
    cov = s2 * np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    return beta, beta / se, n


def main() -> int:
    matches = []
    for cid, sid, label in COMPS:
        ms = _get(f"{BASE}/matches/{cid}/{sid}.json", f"m_{cid}_{sid}.json")
        for m in ms:
            matches.append((m["match_id"], m["home_team"]["home_team_name"],
                            m["away_team"]["away_team_name"], label))
    print(f"fetching {len(matches)} matches (cached after first run) ...")

    rows = []          # (checkpoint, gd_t, xd_t, remaining_gd)  panel
    prim = []          # primary: one row per match at PRIMARY minute
    for i, (mid, home, away, label) in enumerate(matches):
        try:
            tl = timeline(mid, home, away)
        except Exception as e:
            print(f"  skip {mid}: {e}")
            continue
        fgd = final_gd(tl)
        for t in CHECKPOINTS:
            gd, xd = diffs_at(tl, t)
            rows.append((t, gd, xd, fgd - gd))
            if t == PRIMARY:
                prim.append((gd, xd, fgd - gd))
        if (i + 1) % 32 == 0:
            print(f"  {i+1}/{len(matches)} processed")

    rows = np.array(rows, float)
    prim = np.array(prim, float)

    # primary: remaining_gd ~ 1 + gd60 + xg_diff60  (128 independent matches)
    X = np.column_stack([np.ones(len(prim)), prim[:, 0], prim[:, 1]])
    beta, t, n = ols(prim[:, 2], X)
    # baseline: scoreline only, to show the xG term adds signal
    Xb = np.column_stack([np.ones(len(prim)), prim[:, 0]])
    bb, tb, _ = ols(prim[:, 2], Xb)

    # sharp subset at PRIMARY: xG leader (|xg_diff|>=0.5) who is NOT ahead on goals
    lead_xg_not_goal = prim[(np.abs(prim[:, 1]) >= 0.5) &
                            (np.sign(prim[:, 1]) != np.sign(prim[:, 0]).clip(-1, 1) *
                             (np.abs(prim[:, 0]) > 0))]
    # align remainder to the xG-favoured direction
    fav = []
    for gd, xd, rem in prim:
        if abs(xd) >= 0.5 and (gd == 0 or np.sign(gd) != np.sign(xd)):
            fav.append(rem * np.sign(xd))      # + means the xG-favoured side outscored the rest
    fav = np.array(fav, float)

    res = {
        "source": "StatsBomb open data, FIFA World Cup 2018 + 2022, regulation only",
        "n_matches": int(n), "checkpoint_min": PRIMARY,
        "model": "remaining_goal_diff ~ 1 + goal_diff_t + xg_diff_t (home-minus-away)",
        "coef_intercept": round(float(beta[0]), 4),
        "coef_goal_diff": round(float(beta[1]), 4), "t_goal_diff": round(float(t[1]), 2),
        "coef_xg_diff": round(float(beta[2]), 4), "t_xg_diff": round(float(t[2]), 2),
        "baseline_scoreline_only_coef_goal_diff": round(float(bb[1]), 4),
        "disagree_subset": {
            "n": int(len(fav)),
            "mean_remaining_gd_favouring_xg_leader": round(float(fav.mean()), 3) if len(fav) else None,
            "share_xg_leader_outscores_rest": round(float((fav > 0).mean()), 3) if len(fav) else None,
        },
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=2)

    print("\n=== xG-flow lead PoC (necessary condition) ===")
    print(f"  n={res['n_matches']} matches · checkpoint min {PRIMARY} · regulation only")
    print(f"  remaining_goal_diff ~ 1 + goal_diff_{PRIMARY} + xg_diff_{PRIMARY}")
    print(f"    goal_diff coef  {res['coef_goal_diff']:+.3f} (t={res['t_goal_diff']})")
    print(f"    xg_diff   coef  {res['coef_xg_diff']:+.3f} (t={res['t_xg_diff']})  <- the test")
    d = res["disagree_subset"]
    print(f"  sharp subset (xG leader, not ahead on goals): n={d['n']}, "
          f"xG-leader's mean remaining GD = {d['mean_remaining_gd_favouring_xg_leader']}, "
          f"outscores rest {d['share_xg_leader_outscores_rest']} of the time")
    verdict = ("PASS — xG leads future goals beyond the scoreline; get the Betfair odds for stage 2"
               if res["t_xg_diff"] >= 2 and res["coef_xg_diff"] > 0 else
               "WEAK/FAIL — xG does not clearly lead future goals here; the trade idea is in doubt")
    print(f"  VERDICT: {verdict}")
    print(f"  wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
