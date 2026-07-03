#!/usr/bin/env python3
"""Backtest the Elo/squad-value blend weight on the 2026 World Cup itself.

We have no HISTORICAL squad values (build_blend_check note), so the blend weight can't be tested on
past tournaments. But the WC2026 group stage (72 clean W/D/L games) IS a valid out-of-sample test for
the CURRENT squad values: predict every game from PRE-tournament ratings (no lookahead) under each
blend weight and score against the actual result. Answers: does Elo or squad value predict better,
and is the production default w=0.4 (40% Elo) right?

    python scripts/backtest_blend.py

Result (2026-07-02): log-loss is monotonically WORSE as Elo weight rises; optimal w* ~= 0.1 (weight
squad value MORE), vs the default 0.4 — the opposite of the old 'blend over-rates squad value' belief.
Gain is small (~0.007 log-loss, flat optimum over w in [0, 0.3]) and it's one draw-heavy tournament,
so read it as 'the default leans slightly too much on Elo', not a precise w*. v1 core untouched.
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
from scipy.stats import skellam

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import data, elo, baseline, group_sim, wc2026_teams  # noqa: E402
import blend as B  # noqa: E402

WC_START = pd.Timestamp("2026-06-11")


def _key(a, b):
    return frozenset((wc2026_teams.elo_name(wc2026_teams.canonical(a)),
                      wc2026_teams.elo_name(wc2026_teams.canonical(b))))


def load_games():
    df = data.load_results(); df["date"] = pd.to_datetime(df["date"])
    pre = elo.build_ratings(df[df["date"] < WC_START])        # no lookahead
    params = baseline.calibrate(pre.calib)
    fx = pd.read_csv(os.path.join(ROOT, "data", "wc2026_fixtures.csv"))
    grp = fx[fx["group"].astype(str).str.startswith("Group")]
    res = df[(df["tournament"] == "FIFA World Cup") & (df["date"] >= WC_START)]
    rmap = {_key(r.home_team, r.away_team): (r.home_score, r.away_score) for r in res.itertuples(index=False)}
    games = []
    for r in grp.itertuples(index=False):
        m = rmap.get(_key(r.team1, r.team2))
        if m and not np.isnan(m[0]):
            games.append((r.team1, r.team2, r.ground, int(m[0]), int(m[1])))
    return pre, params, games


def score(w, pre, params, games):
    br = B.blended_ratings(pre.ratings, w=w)
    ll = brier = 0.0
    for t1, t2, g, s1, s2 in games:
        l1, l2 = group_sim._match_lambdas(t1, t2, g, br, params)
        p = np.array([1 - skellam.cdf(0, l1, l2), skellam.pmf(0, l1, l2), skellam.cdf(-1, l1, l2)])
        p = p / p.sum()
        y = 0 if s1 > s2 else (1 if s1 == s2 else 2)
        ll += -np.log(max(p[y], 1e-9)); brier += ((p - np.eye(3)[y]) ** 2).sum()
    return ll / len(games), brier / len(games)


def main() -> int:
    pre, params, games = load_games()
    print(f"backtest: {len(games)} WC2026 group games, predicted from pre-tournament ratings\n")
    print(f"{'w (Elo wt)':>11}{'log-loss':>10}{'brier':>9}")
    best = None
    for w in np.round(np.arange(0.0, 1.01, 0.1), 2):
        ll, br = score(w, pre, params, games)
        print(f"{w:>11.1f}{ll:>10.4f}{br:>9.4f}" + ("   <- default 0.4" if abs(w - 0.4) < 1e-9 else ""))
        if best is None or ll < best[0]:
            best = (ll, w)
    print(f"\noptimal Elo weight w* = {best[1]:.1f} (log-loss {best[0]:.4f}); default is 0.4.")
    print("lower w = more squad value = better here — the blend leans slightly too much on Elo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
