#!/usr/bin/env python3
"""v4 forward experiment: does weighting recent FORM more improve the rating?
    -> writeups/_v4_results.json   (a graded, validate-before-adopt experiment)

Motivation: the v3 match forecasts under-react to recent form (a team that just lost twice is rated
almost the same as before), because Elo's K is tournament-based, not recency-weighted, and 2-3 games
barely move a rating built on ~50k matches. This forks a recency-weighted Elo and asks, with proper
out-of-sample scoring, whether weighting current form more actually helps — the same bar the
confederation-bias fix had to clear (+4.6% OOS RPS, Diebold-Mariano p≈0.004) before it shipped.

Two knobs (the Elo recency levers; higher = shorter memory = more weight on recent form):
  kappa = global K multiplier         tau = extra multiplier on in-tournament (2026 WC) games

Method: replicate elo.build_ratings exactly (same expected score, goal index, home advantage) with
K scaled by (kappa, tau); refit the Elo->goals beta on the v4 ratings via baseline.calibrate; forecast
each played 2026 WC game AS-OF (only prior matches), W/D/L via the SAME v3 goal model (ZISM), so the
ONLY thing that changes vs the standard rolling baseline is the rating's recency. Score multiclass
Brier; compare to the standard rolling model (kappa=1) and report the committed-v3 / market references.

VERDICT (run 2026-06-25, n=54 played WC games): recency nudges individual forecasts toward intuition
(Turkey-USA: USA 43%->50%, vs the frozen v3 coin-flip 33%) but the aggregate accuracy gain is tiny
(~+0.005 Brier/game) and NOT significant (t≈0.4). It does not clear the adoption bar and does not close
the gap to the market (0.528). Conclusion: the model already weights form about right; the market's
edge is genuine sharpness, not the model ignoring form. NOT adopted into the live forecasts.

Fork-forward: new script; edits nothing in xresidual/ or the committed v1/v3 ledgers. Pure laptop job.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from math import sqrt

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import baseline, data, elo, group_sim, wc2026_teams as W  # noqa: E402
from build_matches_v3 import _omega_eff, _wdl_zism, scale_wdl            # noqa: E402

OUT = os.path.join(ROOT, "writeups", "_v4_results.json")
WC = pd.Timestamp("2026-06-11")
KAPPAS = (1.0, 1.5, 2.0, 2.5, 3.0)
TAUS = (1.0, 2.0, 3.0)
MARKET_BRIER, V3_BRIER = 0.5281, 0.5405          # references from build_calibration (same WC games)


def recency_elo(df: pd.DataFrame, kappa: float = 1.0, tau: float = 1.0):
    """Standard Elo (elo.build_ratings) with K scaled by (kappa, in-tournament tau). Returns final
    ratings, the calibration frame for baseline.calibrate, and per-2026-WC-game AS-OF pre-match state."""
    R: dict[str, float] = defaultdict(lambda: elo.INIT_RATING)
    rows, asof = [], []
    for r in df.itertuples(index=False):
        h, a = r.home_team, r.away_team
        rh, ra = R[h], R[a]
        neu = bool(getattr(r, "neutral", False))
        gd = int(r.home_score) - int(r.away_score)
        we = elo.expected_score(rh, ra, neu)
        w = 1.0 if gd > 0 else (0.5 if gd == 0 else 0.0)
        k = elo.importance_weight(getattr(r, "tournament", ""))
        wc26 = getattr(r, "tournament", "") == "FIFA World Cup" and pd.Timestamp(r.date) >= WC
        delta = (k * kappa * (tau if wc26 else 1.0)) * elo.goal_index(gd) * (w - we)
        rows.append((pd.Timestamp(r.date), rh - ra + (0.0 if neu else elo.HOME_ADVANTAGE), gd,
                     int(r.home_score) + int(r.away_score)))
        if wc26:
            asof.append({"rh": rh, "ra": ra, "neu": neu, "gd": gd})
        R[h], R[a] = rh + delta, ra - delta
    calib = pd.DataFrame(rows, columns=["date", "dr_eff", "goal_diff", "total_goals"])
    return dict(R), calib, asof


def _briers(asof, params) -> np.ndarray:
    out = []
    for g in asof:
        l1, l2 = baseline.lambdas(g["rh"], g["ra"], params, neutral=g["neu"])
        p = np.array(scale_wdl(*_wdl_zism(l1, l2, _omega_eff(l1, l2))))
        oc = 0 if g["gd"] > 0 else (1 if g["gd"] == 0 else 2)
        out.append(float(np.sum((p - np.eye(3)[oc]) ** 2)))
    return np.array(out)


def _evaluate(df, kappa, tau):
    _, calib, asof = recency_elo(df, kappa, tau)
    return _briers(asof, baseline.calibrate(calib))


def main() -> int:
    df = data.load_results(refresh=True).sort_values("date").reset_index(drop=True)
    base_b = _evaluate(df, 1.0, 1.0)
    grid, best = {}, (base_b.mean(), 1.0, 1.0, base_b)
    for kappa in KAPPAS:
        for tau in TAUS:
            b = _evaluate(df, kappa, tau)
            grid[f"k{kappa}_t{tau}"] = round(float(b.mean()), 4)
            if b.mean() < best[0]:
                best = (b.mean(), kappa, tau, b)
    bm, bk, bt, bb = best
    d = base_b - bb
    t = float(d.mean() / (d.std(ddof=1) / sqrt(len(d)))) if d.std() > 0 else 0.0

    payload = {"n_games": int(len(base_b)),
               "standard_brier": round(float(base_b.mean()), 4),
               "best": {"kappa": bk, "tau": bt, "brier": round(bm, 4)},
               "improvement_per_game": round(float(d.mean()), 4), "t_stat": round(t, 2),
               "market_brier": MARKET_BRIER, "v3_brier": V3_BRIER,
               "grid": grid, "adopted": bool(t > 2.0 and bm < V3_BRIER)}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(payload, open(OUT, "w"), indent=2)

    print(f"v4 recency experiment · {payload['n_games']} OOS WC games")
    print(f"  standard rolling (k1,t1):  Brier {payload['standard_brier']}")
    print(f"  best recency  (k{bk},t{bt}):  Brier {payload['best']['brier']}  "
          f"(improvement {payload['improvement_per_game']:+}/game, t={payload['t_stat']})")
    print(f"  references: committed v3 {V3_BRIER} · market {MARKET_BRIER}")
    print(f"  ADOPT? {payload['adopted']}  "
          f"(rule: t>2 AND beats v3 — recency must EARN it, like the confed fix did)")
    print(f"wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
