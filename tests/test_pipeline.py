"""End-to-end test of the live pipeline on synthetic snapshots + fixtures.

Run:  python tests/test_pipeline.py
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xresidual import baseline, pipeline  # noqa: E402


def _snapshots():
    """h2h snapshots for one market across 2 books and 2 timestamps."""
    rows = []
    quotes = {  # closing (t1) probabilities differ from earlier (t0)
        "t0": {"Mexico": 0.60, "Draw": 0.25, "South Africa": 0.15},
        "t1": {"Mexico": 0.70, "Draw": 0.20, "South Africa": 0.10},
    }
    for ts_key, ts in [("t0", "2026-06-11T15:00:00+00:00"), ("t1", "2026-06-11T18:00:00+00:00")]:
        for book in ("pinnacle", "betfair_ex_uk"):
            for outc, p in quotes[ts_key].items():
                rows.append({"ts_utc": pd.Timestamp(ts), "venue": "oddsapi",
                             "market_id": "ev1", "outcome": outc, "mid": p,
                             "market_type": "h2h"})
    return pd.DataFrame(rows)


def _fixtures():
    return pd.DataFrame([
        {"round": "Matchday 1", "group": "Group A", "date": "2026-06-11",
         "ground": "Mexico City", "team1": "Mexico", "team2": "South Africa",
         "score1": 2, "score2": 0, "played": True},
    ])


def _ratings_params():
    ratings = {"Mexico": 1800.0, "South Africa": 1600.0}
    params = baseline.BaselineParams(beta=0.5, total_goals=2.7, n_matches=1)
    return ratings, params


def test_closing_line_picks_latest_and_normalizes():
    cl = pipeline.closing_line_wdl(_snapshots(), "Mexico", "South Africa")
    assert abs(cl["p_home"] + cl["p_draw"] + cl["p_away"] - 1.0) < 1e-9
    assert abs(cl["p_home"] - 0.70) < 1e-6        # used the t1 (closing) snapshot
    assert cl["ts"] == pd.Timestamp("2026-06-11T18:00:00+00:00")


def test_closing_line_respects_kickoff_cutoff():
    cl = pipeline.closing_line_wdl(_snapshots(), "Mexico", "South Africa",
                                   kickoff=pd.Timestamp("2026-06-11T16:00:00+00:00"))
    assert abs(cl["p_home"] - 0.60) < 1e-6        # only the pre-kickoff t0 snapshot
    assert cl["n_books"] == 2


def test_closing_line_none_when_market_absent():
    assert pipeline.closing_line_wdl(_snapshots(), "Brazil", "France") is None


def test_build_match_table_and_residuals():
    ratings, params = _ratings_params()
    tbl = pipeline.build_match_table(_fixtures(), _snapshots(), ratings, params)
    assert len(tbl) == 1
    r = tbl.iloc[0]
    assert r["outcome"] == "home"                 # Mexico won 2-0
    assert abs(r["mkt_home"] + r["mkt_draw"] + r["mkt_away"] - 1.0) < 1e-9
    # market gave Mexico 0.70 -> log-score = -ln(0.70)
    import math
    assert abs(r["mkt_logscore"] - (-math.log(0.70))) < 1e-6
    assert abs(r["goal_diff_z"]) < 4               # sigma discipline: real results stay in-band
    # baseline should also favour Mexico (host + higher Elo)
    assert r["base_home"] > r["base_away"]


def test_calibration_and_skill_report_run():
    ratings, params = _ratings_params()
    tbl = pipeline.build_match_table(_fixtures(), _snapshots(), ratings, params)
    rep = pipeline.calibration_report(tbl, which="mkt")
    assert rep["n_matches"] == 1 and rep["n_events"] == 3
    assert "corp" in rep and "calib_b" in rep
    skill = pipeline.skill_comparison(tbl)
    assert "market_mean_logscore" in skill and "baseline_mean_logscore" in skill


def test_empty_when_no_played_matches():
    fx = _fixtures().assign(played=False)
    ratings, params = _ratings_params()
    tbl = pipeline.build_match_table(fx, _snapshots(), ratings, params)
    assert tbl.empty
    assert pipeline.calibration_report(tbl)["n_matches"] == 0


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
