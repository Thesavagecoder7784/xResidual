"""Tests for knockout-stage heat: deterministic bracket path + stage intensity."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xresidual import data_fixtures, heat  # noqa: E402

FX = data_fixtures.load_fixtures()


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
