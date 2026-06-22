"""Tests for knockout-stage heat: deterministic bracket path + stage intensity.

Uses a committed fixtures snapshot, NOT the live feed: openfootball rewrites the R32
slot labels into team names as groups resolve (e.g. "1A" -> "Mexico"), which is correct
for production but makes a slot-code path trace non-deterministic. The snapshot pins the
canonical slot codes so this exercises the bracket logic itself.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xresidual import heat  # noqa: E402

FX = pd.read_csv(os.path.join(os.path.dirname(__file__), "data", "wc2026_fixtures_frozen.csv"))


def test_winner_path_reaches_the_final():
    # a group winner who wins out plays R32 -> R16 -> QF -> SF -> Final = 5 venues
    p = heat.knockout_path(FX, "1A")
    assert len(p) == 5
    assert p[0]["round"].startswith("Round of 32")
    assert p[-1]["round"] == "Final"
    assert all(m["ground"] for m in p)


def test_runner_up_path_also_traces():
    p = heat.knockout_path(FX, "2A")
    assert len(p) == 5 and p[-1]["round"] == "Final"


def test_path_load_sums_along_path():
    pl = heat.path_load(FX, "1A")
    assert pl["rounds"] == 5
    assert pl["ko_score"] == sum(
        heat.RISK_SCORE[m["risk"]] for m in heat.knockout_path(FX, "1A"))


def test_heat_intensifies_into_knockouts():
    s = heat.stage_intensity(FX)
    assert s["group"]["n"] == 72 and s["knockout"]["n"] == 32
    # the dangerous afternoon-in-an-extreme-city share is higher in the knockouts
    assert s["knockout"]["both_pct"] > s["group"]["both_pct"]
