"""Tests for availability-adjusted squad value (Tier-1 model upgrade). No network.

Run:  python tests/test_availability.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import squad_values as sv          # noqa: E402
import blend                       # noqa: E402


def _with_absences(absences, fn):
    """Run fn() with ABSENCES temporarily set, then restore (module-level state)."""
    saved = sv.ABSENCES
    sv.ABSENCES = absences
    try:
        return fn()
    finally:
        sv.ABSENCES = saved


def test_empty_table_is_identity():
    # default (empty) table: adjusted == static everywhere, so turning availability on
    # can never silently move the published model.
    assert sv.ABSENCES == {}
    adj = sv.adjusted_squad_values()
    assert adj == sv.SQUAD_VALUE
    assert sv.missing_top11("Brazil") == {"count": 0, "value_out": 0}


def test_out_and_doubt_weighting_and_floor():
    base = sv.SQUAD_VALUE["Brazil"]
    def check():
        # one confirmed-out (full) + one doubtful (half)
        v = sv.adjusted_squad_value("Brazil")
        assert abs(v - (base - 100.0 - 0.5 * 40.0)) < 1e-9      # 100 out + 0.5*40 doubt
        assert sv.missing_top11("Brazil") == {"count": 2, "value_out": 140.0}
    _with_absences({"Brazil": [{"player": "X", "value": 100.0, "status": "out"},
                               {"player": "Y", "value": 40.0, "status": "doubt"}]}, check)

    # floor: an over-entered absence can't cut more than half the base value
    def floored():
        assert abs(sv.adjusted_squad_value("Brazil") - base * 0.5) < 1e-9
    _with_absences({"Brazil": [{"player": "Z", "value": base * 5, "status": "out"}]}, floored)


def test_blend_availability_lowers_the_depleted_team():
    from xresidual import wc2026_teams as W
    teams = sorted(sv.SQUAD_VALUE)
    # synthetic Elo with spread (a flat dict -> std 0 -> NaN); the value channel still
    # carries the availability signal, so an absence must pull that team's rating down.
    elo_r = {W.elo_name(t): 1500.0 + 3.0 * i for i, t in enumerate(teams)}
    full = blend.blended_ratings(elo_r, teams=teams, availability=True)   # empty table == static
    static = blend.blended_ratings(elo_r, teams=teams, availability=False)
    assert full == static                                                 # identity when empty

    def check():
        dep = blend.blended_ratings(elo_r, teams=teams, availability=True)
        deltas = {t: dep[W.elo_name(t)] - static[W.elo_name(t)] for t in teams}
        assert deltas["Brazil"] < 0                                       # Brazil rating fell
        # the drop is concentrated on Brazil (others only drift via renormalization)
        assert min(deltas, key=deltas.get) == "Brazil"
    _with_absences({"Brazil": [{"player": "X", "value": 300.0, "status": "out"}]}, check)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
