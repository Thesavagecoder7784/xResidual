"""Live pipeline: market closing-line + baseline + result -> residuals + calibration.

This is the connective tissue between the logger (market prices), the fixtures feed
(schedule + results), and the analysis layers. For each completed match it:
  1. extracts the market closing-line W/D/L from the logged h2h snapshots,
  2. computes the Elo/Skellam baseline expectation (host/altitude aware),
  3. reads the actual outcome,
  4. records per-match residuals (Layer 2) and the (market prob, outcome) pairs that
     feed the calibration study (Layer 3).

Pure functions over DataFrames so the join logic is testable without live data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import baseline as _baseline
from . import calibration as cal
from . import data_fixtures, residual, venues_wc2026, wc2026_teams

DRAW = "Draw"


def closing_line_wdl(snapshots: pd.DataFrame, team1: str, team2: str,
                     kickoff: pd.Timestamp | None = None,
                     venue: str = "oddsapi") -> dict | None:
    """Market W/D/L for team1 vs team2 from the last h2h snapshot before kickoff.

    Finds the h2h market whose outcomes include both teams, takes the latest
    timestamp at/under `kickoff` (the closing line), aggregates each outcome across
    bookmakers (median of the stored overround-stripped probabilities), and
    renormalizes to sum to 1. Returns {p_home, p_draw, p_away, ts, n_books} or None.
    """
    if snapshots.empty:
        return None
    s = snapshots[(snapshots["venue"] == venue)
                  & (snapshots.get("market_type") == "h2h")
                  & (snapshots["outcome"] != "__error__")]
    # markets carrying both teams (the h2h for this fixture)
    teams_per_market = s.groupby("market_id")["outcome"].agg(set)
    ids = [mid for mid, outs in teams_per_market.items() if {team1, team2} <= outs]
    if not ids:
        return None
    s = s[s["market_id"].isin(ids)]
    if kickoff is not None:
        s = s[s["ts_utc"] <= kickoff]
    if s.empty:
        return None
    last_ts = s["ts_utc"].max()
    snap = s[s["ts_utc"] == last_ts]
    med = snap.groupby("outcome")["mid"].median()
    p = {team1: med.get(team1), DRAW: med.get(DRAW), team2: med.get(team2)}
    if any(v is None or pd.isna(v) for v in p.values()):
        return None
    total = sum(p.values())
    return {
        "p_home": p[team1] / total, "p_draw": p[DRAW] / total, "p_away": p[team2] / total,
        "ts": last_ts, "n_books": int(snap.groupby("outcome").size().max()),
    }


def baseline_wdl(team1: str, team2: str, ratings: dict, params,
                 ground: str | None = None) -> dict:
    """Baseline expectation for the fixture (host advantage + altitude aware)."""
    host = team1 in venues_wc2026.HOST_NATIONS    # team1 is home; hosts play at home
    exp = _baseline.make_expectation(
        wc2026_teams.elo_name(team1), wc2026_teams.elo_name(team2),
        ratings, params, neutral=not host, venue=ground,
    )
    return {"p_home": exp.p_home, "p_draw": exp.p_draw, "p_away": exp.p_away, "exp": exp}


def build_match_table(fixtures: pd.DataFrame, snapshots: pd.DataFrame,
                      ratings: dict, params) -> pd.DataFrame:
    """One row per completed match with market + baseline forecasts, the actual
    outcome, and per-match residuals. Matches with no market data are skipped."""
    rows = []
    for f in fixtures[fixtures["played"]].itertuples(index=False):
        market = closing_line_wdl(snapshots, f.team1, f.team2)
        if market is None:
            continue
        base = baseline_wdl(f.team1, f.team2, ratings, params, ground=f.ground)
        oc = data_fixtures.outcome(f.score1, f.score2)
        gd = int(f.score1) - int(f.score2)
        market_exp = _exp_like(market, f.team1, f.team2)
        rows.append({
            "date": f.date, "group": f.group, "ground": f.ground,
            "team1": f.team1, "team2": f.team2, "score1": int(f.score1),
            "score2": int(f.score2), "outcome": oc,
            "mkt_home": market["p_home"], "mkt_draw": market["p_draw"], "mkt_away": market["p_away"],
            "base_home": base["p_home"], "base_draw": base["p_draw"], "base_away": base["p_away"],
            "mkt_logscore": residual.log_score(market_exp, oc),
            "base_logscore": residual.log_score(base["exp"], oc),
            "goal_diff_z": residual.goal_diff_z(base["exp"], gd),
        })
    return pd.DataFrame(rows)


def _exp_like(wdl: dict, home: str, away: str):
    """Wrap a W/D/L dict as a MatchExpectation so residual.log_score works on it."""
    from .skellam import MatchExpectation
    return MatchExpectation(home=home, away=away, lambda_home=float("nan"),
                            lambda_away=float("nan"), p_home=wdl["p_home"],
                            p_draw=wdl["p_draw"], p_away=wdl["p_away"],
                            exp_goal_diff=float("nan"), sd_goal_diff=float("nan"))


def calibration_report(match_table: pd.DataFrame, which: str = "mkt") -> dict:
    """Run the Layer 3 calibration on a match table's forecasts (`mkt` or `base`).

    Returns CORP decomposition, calibration regression (a, b), Brier and ECE, plus
    the reliability table, the same machinery validated on the 538 backtest.
    """
    if match_table.empty:
        return {"n_matches": 0}
    p, y = cal.flatten_wdl(match_table[f"{which}_home"], match_table[f"{which}_draw"],
                           match_table[f"{which}_away"], match_table["outcome"])
    a, b = cal.calibration_regression(p, y)
    corp = cal.corp(p, y, n_boot=500)
    return {
        "n_matches": len(match_table), "n_events": len(y),
        "brier": cal.brier_score(p, y), "ece": cal.expected_calibration_error(p, y),
        "calib_a": a, "calib_b": b,
        "corp": corp.as_dict(),
        "reliability": cal.reliability_table(p, y),
    }


def skill_comparison(match_table: pd.DataFrame) -> dict:
    """Mean log-score (lower better) for market vs baseline: who forecasts better.
    The market is expected to win; the baseline is an independent reference, not a
    competitor (METHODOLOGY.md §1, §10)."""
    if match_table.empty:
        return {"n_matches": 0}
    return {
        "n_matches": len(match_table),
        "market_mean_logscore": float(match_table["mkt_logscore"].mean()),
        "baseline_mean_logscore": float(match_table["base_logscore"].mean()),
    }
