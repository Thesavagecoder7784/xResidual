"""The 2026 group-stage Monte Carlo (no network needed).

The format invariants are exact by construction of the selection rule: every draw
sends exactly 2 teams per group plus 8 best thirds through, so the field-wide sums
hold for any sample size and any ratings. These tests pin that down.

Run:  python -m pytest tests/test_group_sim.py
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xresidual import baseline, group_sim  # noqa: E402

PARAMS = baseline.BaselineParams(beta=0.55, total_goals=2.7, n_matches=1000)


def _synthetic_fixtures():
    """12 groups (A..L) of 4 teams, single round-robin, neutral sea-level venue."""
    rows = []
    for gi, L in enumerate("ABCDEFGHIJKL"):
        teams = [f"{L}{k}" for k in range(1, 5)]
        for a in range(4):
            for b in range(a + 1, 4):
                rows.append({"round": "Matchday 1", "group": f"Group {L}",
                             "date": "2026-06-11", "ground": "Miami",
                             "team1": teams[a], "team2": teams[b]})
    return pd.DataFrame(rows)


def test_advancement_sums_are_exact():
    sim = group_sim.simulate(_synthetic_fixtures(), ratings={}, params=PARAMS, n=2000, seed=3)
    assert len(sim) == 48
    assert abs(sum(r["padv"] for r in sim.values()) - 32.0) < 1e-9   # 32 of 48 advance
    assert abs(sum(r["p3adv"] for r in sim.values()) - 8.0) < 1e-9   # 8 third-place spots


def test_finish_places_are_a_distribution():
    sim = group_sim.simulate(_synthetic_fixtures(), ratings={}, params=PARAMS, n=2000, seed=5)
    for r in sim.values():
        assert abs(r["p1"] + r["p2"] + r["p3"] + r["p4"] - 1.0) < 1e-9
        assert abs(r["top2"] - (r["p1"] + r["p2"])) < 1e-9
        assert r["p3adv"] <= r["p3"] + 1e-9          # can't qualify as a third more often than you finish third
        assert r["padv"] <= r["top2"] + r["p3"] + 1e-9


def test_equal_strength_group_is_symmetric():
    # Four equal teams in a neutral venue -> ~1/4 each to win the group.
    sim = group_sim.simulate(_synthetic_fixtures(), ratings={}, params=PARAMS, n=8000, seed=7)
    a_teams = [r for t, r in sim.items() if t.startswith("A")]
    for r in a_teams:
        assert abs(r["p1"] - 0.25) < 0.04           # sampling tolerance


if __name__ == "__main__":
    test_advancement_sums_are_exact()
    test_finish_places_are_a_distribution()
    test_equal_strength_group_is_symmetric()
    print("ok")
