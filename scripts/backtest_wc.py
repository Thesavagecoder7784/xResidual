#!/usr/bin/env python3
"""Backtest the per-match expectation baseline on the 2018 + 2022 World Cups (no lookahead).

    python scripts/backtest_wc.py

The integrated framework — expectation -> W/D/L -> residual -> calibration — is run end-to-end
on two completed tournaments, each match scored with the POINT-IN-TIME pre-match rating the
chronological Elo build recorded for it (`EloResult.calib.dr_eff`): a game is forecast using
only results before it, ratings updating through the tournament. This is the §2 baseline the
project grades (P1) — raw Elo + host advantage, not the squad blend (no historical squad
values), which is the right object to backtest.

Two tournaments, not one, because 2022 was upset-heavy: running 2018 too separates real model
properties (replicate) from 2022-specific noise (don't). Emits viz/model/_backtest_wc.js for the
card; the card HTML is private per the repo's template convention.
"""
from __future__ import annotations

import json
import os
import sys
import warnings

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import baseline, calibration, data, elo, residual  # noqa: E402

WINDOWS = {"2018": ("2018-06-01", "2018-07-31"), "2022": ("2022-11-01", "2022-12-31")}
CODE = {"United States": "USA", "South Korea": "KOR", "Saudi Arabia": "KSA"}
abbr = lambda nm: CODE.get(nm) or "".join(nm.split())[:3].upper()


def run_year(cal, params, start, end):
    wc = cal[(cal["tournament"] == "FIFA World Cup") &
             (cal["date"] >= start) & (cal["date"] <= end)].copy()
    rows = []
    for r in wc.itertuples(index=False):
        exp = baseline.make_expectation(r.home_team, r.away_team,
                                        {r.home_team: r.dr_eff, r.away_team: 0.0}, params, neutral=True)
        outcome = residual.outcome_from_goal_diff(int(r.goal_diff))
        p_out = {"home": exp.p_home, "draw": exp.p_draw, "away": exp.p_away}[outcome]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            z = residual.goal_diff_z(exp, int(r.goal_diff))
        zf = z * (1.0 if r.dr_eff >= 0 else -1.0)        # favourite-oriented: <0 stunned, >0 ran riot
        hs = int(round((r.total_goals + r.goal_diff) / 2)); as_ = int(round((r.total_goals - r.goal_diff) / 2))
        win = r.home_team if r.goal_diff > 0 else (r.away_team if r.goal_diff < 0 else None)
        loser = r.away_team if r.goal_diff > 0 else r.home_team
        hi, lo = max(hs, as_), min(hs, as_)
        rows.append({"home": r.home_team, "away": r.away_team, "outcome": outcome,
                     "pH": exp.p_home, "pD": exp.p_draw, "pA": exp.p_away, "p_out": p_out,
                     "logloss": -np.log(max(p_out, 1e-12)), "absz": abs(z), "zf": zf,
                     "tag": (f"{abbr(win)} {hi}-{lo} {abbr(loser)}" if win
                             else f"{abbr(r.home_team)} {hs}-{as_} {abbr(r.away_team)}"),
                     "label": (f"{win} {hi}-{lo} {loser}" if win
                               else f"{r.home_team} {hs}-{as_} {r.away_team}")})
    bt = pd.DataFrame(rows)
    base = {o: (bt["outcome"] == o).mean() for o in ("home", "draw", "away")}
    p, y = calibration.flatten_wdl(bt["pH"].values, bt["pD"].values, bt["pA"].values, bt["outcome"].values)
    bs = calibration.brier_score(p, y); bs0 = calibration.brier_score(np.full_like(p, p.mean()), y)
    conf = p >= 0.65
    notable_idx = set(bt["absz"].sort_values(ascending=False).head(7).index)
    matches = [{"zf": round(float(t.zf), 2), "p_out": round(float(t.p_out), 3),
                "notable": i in notable_idx, "tag": t.tag, "label": t.label}
               for i, t in bt.iterrows()]
    top = []
    for t in bt.sort_values("logloss", ascending=False).head(3).itertuples(index=False):
        lab = (f"{t.home} beat {t.away}" if t.outcome == "home"
               else f"{t.away} beat {t.home}" if t.outcome == "away" else f"{t.home} drew {t.away}")
        top.append({"label": lab, "p": round(float(t.p_out), 3)})
    return {
        "n": int(len(bt)), "median_absz": round(float(bt["absz"].median()), 2),
        "max_absz": round(float(bt["absz"].max()), 2),
        "brier_skill": round(1 - bs / bs0, 3),
        "ll_model": round(float(bt["logloss"].mean()), 3),
        "ll_base": round(float(bt["outcome"].map(lambda o: -np.log(base[o])).mean()), 3),
        "conf_pred": round(float(p[conf].mean()), 2), "conf_obs": round(float(y[conf].mean()), 2),
        "conf_n": int(conf.sum()), "matches": matches, "top": top,
    }


def main() -> int:
    df = data.load_results(); res = elo.build_ratings(df)
    cal = res.calib.copy()
    cal["tournament"] = df.sort_values("date").reset_index(drop=True)["tournament"].values
    # No leakage: each tournament's goal-model params are calibrated STRICTLY on matches before
    # it (faithful to how the model would have run in real time). Ratings are already point-in-
    # time (Elo is causal); fitting params on pre-window data closes the only other path.
    years = {y: run_year(cal, baseline.calibrate(cal[cal["date"] < w[0]]), *w)
             for y, w in WINDOWS.items()}

    print("Per-match backtest, point-in-time (no lookahead)   " + "".join(f"{y:>14}" for y in WINDOWS))
    def row(lbl, fn): print(f"  {lbl:<32}" + "".join(f"{fn(years[y]):>14}" for y in WINDOWS))
    row("matches", lambda d: d["n"])
    row("median |z| / max |z|", lambda d: f"{d['median_absz']}/{d['max_absz']}σ")
    row("Brier skill vs climatology", lambda d: f"{d['brier_skill']:+.1%}")
    row("log-loss model/base", lambda d: f"{d['ll_model']}/{d['ll_base']}")
    row("confident calls (P>=.65) pred->obs", lambda d: f"{d['conf_pred']:.0%}->{d['conf_obs']:.0%} (n={d['conf_n']})")
    for y in WINDOWS:
        print(f"  {y} biggest misses: " + " · ".join(f"{t['label']} @{t['p']:.0%}" for t in years[y]["top"]))

    out = os.path.join(ROOT, "viz", "model", "_backtest_wc.js")
    payload = {"years": years, "window_labels": {y: f"{w[0][:4]}" for y, w in WINDOWS.items()},
               "note": "2018 + 2022 World Cups, point-in-time per-match model (no lookahead); both "
                       "32-team, so this validates the residual/calibration framework, not the "
                       "48-team bracket sim"}
    with open(out, "w", encoding="utf-8") as f:
        f.write("window.BACKTESTWC = " + json.dumps(payload) + ";\n")
    print(f"\nwrote {os.path.relpath(out, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
