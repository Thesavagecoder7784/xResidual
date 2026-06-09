"""The 2026 group-stage Monte Carlo (no network needed).

The format invariants are exact by construction of the selection rule: every draw
sends exactly 2 teams per group plus 8 best thirds through, so the field-wide sums
hold for any sample size and any ratings. These tests pin that down.

Run:  python -m pytest tests/test_group_sim.py
"""

import os
import sys

import numpy as np
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


def test_decisive_games_leverage_known_answer():
    # team1's result fully decides A & B's fate (leverage 100pp); C & D advance no matter
    # what (leverage 0). This pins the Schilling-leverage extraction.
    n = 200
    sign = np.array([1] * 100 + [-1] * 100)          # A wins first 100 sims, loses the rest
    A = np.zeros((n, 4), dtype=bool)
    A[:, 0] = sign > 0                               # A advances iff it wins
    A[:, 1] = sign < 0                               # B advances iff it wins
    A[:, 2] = True                                   # C always advances
    A[:, 3] = True                                   # D always advances
    detail = {"gidx": {"A": 0, "B": 1, "C": 2, "D": 3}, "adv_mat": A,
              "matches": [("X", "A", "B", sign), ("Y", "C", "D", sign)]}
    lev = group_sim.decisive_games(detail, top=12)
    by = {(d["t1"], d["t2"]): d["lev"] for d in lev}
    assert abs(by[("A", "B")] - 100.0) < 1e-6        # outcome fully determines both -> 100pp
    assert abs(by[("C", "D")] - 0.0) < 1e-6          # both through regardless -> 0pp
    assert lev[0]["lev"] >= lev[-1]["lev"]           # sorted descending


def test_third_place_cutline_known_answer():
    cl = np.array([3] * 90 + [4] * 8 + [2] * 2)      # cut-line is almost always 3 points
    freq, median = group_sim.third_place_cutline({"cutline": cl})
    assert median == 3
    d = {x["pts"]: x["freq"] for x in freq}
    assert abs(d[3] - 90.0) < 1e-6 and abs(d[4] - 8.0) < 1e-6
    assert abs(sum(x["freq"] for x in freq) - 100.0) < 0.2


if __name__ == "__main__":
    test_advancement_sums_are_exact()
    test_finish_places_are_a_distribution()
    test_equal_strength_group_is_symmetric()
    test_decisive_games_leverage_known_answer()
    test_third_place_cutline_known_answer()
    print("ok")
