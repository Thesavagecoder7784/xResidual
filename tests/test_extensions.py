"""Tests for the three extensions: host/altitude baseline, Asian-handicap mapping,
and the Layer 4 trajectory. No network.

Run:  python tests/test_extensions.py
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xresidual import asian_handicap as ah  # noqa: E402
from xresidual import baseline, trajectory, venues_wc2026, wc2026_teams  # noqa: E402


# --- host / altitude baseline ------------------------------------------------
def test_altitude_factor_disabled():
    # The altitude total-goals prior was disabled after an empirical check found the
    # effect was, if anything, negatively signed (see venues_wc2026). The factor is
    # now a no-op everywhere; the high-altitude *classifier* still works.
    assert venues_wc2026.total_goals_factor(None) == 1.0
    assert venues_wc2026.total_goals_factor(5) == 1.0
    assert venues_wc2026.total_goals_factor(2240) == 1.0        # no longer lifts goals
    assert venues_wc2026.is_high_altitude(2240) and not venues_wc2026.is_high_altitude(300)


def test_high_altitude_venue_does_not_change_totals():
    params = baseline.BaselineParams(beta=0.5, total_goals=2.7, n_matches=1)
    ratings = {"Mexico": 1850, "South Africa": 1600}
    flat = baseline.make_expectation("Mexico", "South Africa", ratings, params, venue="Miami")
    alt = baseline.make_expectation("Mexico", "South Africa", ratings, params, venue="Mexico City")
    assert (alt.lambda_home + alt.lambda_away) == (flat.lambda_home + flat.lambda_away)


def test_host_home_advantage_raises_win_prob():
    params = baseline.BaselineParams(beta=0.5, total_goals=2.7, n_matches=1)
    ratings = {"Mexico": 1800, "Germany": 1900}
    neutral = baseline.make_expectation("Mexico", "Germany", ratings, params, neutral=True)
    at_home = baseline.make_expectation("Mexico", "Germany", ratings, params, neutral=False)
    assert at_home.p_home > neutral.p_home


# --- Asian-handicap mapping --------------------------------------------------
def test_supremacy_sign_from_spread():
    # home favoured by 1 goal is quoted as -1.0
    assert ah.supremacy_from_home_spread(-1.0) == 1.0
    assert ah.supremacy_from_home_spread(0.5) == -0.5


def test_ah_wdl_normalizes_and_orders():
    ph, pd_, pa = ah.wdl_from_supremacy_total(supremacy=1.0, total=2.7)
    assert abs(ph + pd_ + pa - 1.0) < 1e-9
    assert ph > pa                      # favoured home more likely to win
    # bigger supremacy -> bigger home win prob
    ph2, _, _ = ah.wdl_from_supremacy_total(2.0, 2.7)
    assert ph2 > ph


def test_consensus_line_is_median():
    assert ah.consensus_line([-0.5, -1.0, -0.75, None]) == -0.75


# --- Layer 4 trajectory ------------------------------------------------------
def _synthetic_outrights():
    # two snapshots; Brazil drifts up fast, Spain flat
    rows = []
    for ts, (bra, esp, fra) in [
        ("2026-06-10T00:00:00+00:00", (0.10, 0.18, 0.12)),
        ("2026-06-13T00:00:00+00:00", (0.22, 0.18, 0.10)),
    ]:
        for team, prob in [("Brazil", bra), ("Spain", esp), ("France", fra)]:
            rows.append({"ts_utc": pd.Timestamp(ts), "venue": "oddsapi",
                         "outcome": team, "mid": prob, "market_type": "outrights"})
    return pd.DataFrame(rows)


def test_outright_probabilities_renormalize_per_ts():
    long = trajectory.outright_probabilities(_synthetic_outrights())
    sums = long.groupby("ts")["prob"].sum()
    assert ((sums - 1.0).abs() < 1e-9).all()


def test_outright_whitelist_drops_nonqualified_and_renormalizes():
    df = _synthetic_outrights()
    # add a stale non-qualified longshot; it must be excluded and not distort sums
    extra = pd.DataFrame([{"ts_utc": pd.Timestamp("2026-06-10T00:00:00+00:00"),
                           "venue": "oddsapi", "outcome": "Italy", "mid": 0.001,
                           "market_type": "outrights"}])
    df = pd.concat([df, extra], ignore_index=True)
    long = trajectory.outright_probabilities(df, teams={"Brazil", "Spain", "France"})
    assert "Italy" not in set(long["team"])
    sums = long.groupby("ts")["prob"].sum()
    assert ((sums - 1.0).abs() < 1e-9).all()


def test_belief_velocity_ranks_fast_mover_first():
    long = trajectory.outright_probabilities(_synthetic_outrights())
    vel = trajectory.belief_velocity(long)
    assert vel.iloc[0]["team"] == "Brazil"          # biggest mover ranked first
    assert vel.iloc[0]["net_drift"] > 0
    assert vel.set_index("team").loc["Spain", "velocity_per_day"] < \
        vel.set_index("team").loc["Brazil", "velocity_per_day"]


def test_wc2026_teams_list_and_name_mapping():
    assert len(wc2026_teams.WC2026_TEAMS) == 48
    assert wc2026_teams.elo_name("USA") == "United States"
    assert wc2026_teams.elo_name("Bosnia & Herzegovina") == "Bosnia and Herzegovina"
    assert wc2026_teams.elo_name("Brazil") == "Brazil"   # unchanged when names agree


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
