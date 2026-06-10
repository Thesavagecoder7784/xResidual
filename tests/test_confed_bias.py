"""Tests for the per-confederation Elo-bias correction (xresidual.confed_bias). No network.

Run:  python tests/test_confed_bias.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from xresidual import confed_bias, wc2026_teams as W  # noqa: E402
import blend                                          # noqa: E402


def test_uefa_is_reference():
    assert confed_bias.BASE_OFFSETS["UEFA"] == 0.0
    # every UEFA team carries a zero effective offset
    for t, conf in confed_bias.WC_TEAM_CONF.items():
        if conf == "UEFA":
            assert confed_bias.TEAM_OFFSET[t] == 0.0


def test_every_wc_team_mapped():
    missing = [t for t in W.WC2026_TEAMS if t not in confed_bias.WC_TEAM_CONF]
    assert not missing, f"unmapped WC teams: {missing}"
    assert set(confed_bias.WC_TEAM_CONF.values()) <= set(confed_bias.CONFEDERATIONS)
    assert set(confed_bias.TEAM_OFFSET) == set(confed_bias.WC_TEAM_CONF)


def test_offset_applied_per_team():
    en_mex = W.elo_name("Mexico")          # CONCACAF, negative offset
    en_spain = W.elo_name("Spain")         # UEFA reference, zero
    base = {en_mex: 1900.0, en_spain: 2150.0}
    out = confed_bias.apply_offsets(base)
    assert out[en_mex] == 1900.0 + confed_bias.TEAM_OFFSET["Mexico"]
    assert out[en_spain] == 2150.0
    assert base[en_mex] == 1900.0          # input not mutated


def test_isolated_team_gets_larger_offset():
    # within CONCACAF the empirical-Bayes weight makes the more isolated team shrink MORE:
    # Mexico (plays everyone) is lightly corrected, Canada more, Haiti/Curaçao most.
    o = confed_bias.TEAM_OFFSET
    assert abs(o["Mexico"]) < abs(o["Canada"]) < abs(o["Haiti"])
    assert abs(o["Curaçao"]) > abs(o["Mexico"])


def test_unknown_team_unchanged():
    out = confed_bias.apply_offsets({"Some Friendly XI": 1500.0})
    assert out["Some Friendly XI"] == 1500.0


def test_blend_correction_widens_confederation_gap():
    # the correction must re-level BETWEEN confederations: with Mexico (CONCACAF) and Spain
    # (UEFA) on equal raw Elo, the UEFA-minus-CONCACAF blended gap is wider WITH the
    # correction than without (CONCACAF carries a negative offset, UEFA the zero reference).
    elo_ratings = {W.elo_name(t): 1700.0 + 10.0 * i for i, t in enumerate(sorted(W.WC2026_TEAMS))}
    elo_ratings[W.elo_name("Mexico")] = elo_ratings[W.elo_name("Spain")] = 1900.0
    on = blend.blended_ratings(elo_ratings, confed_correct=True)
    off = blend.blended_ratings(elo_ratings, confed_correct=False)
    gap_on = on[W.elo_name("Spain")] - on[W.elo_name("Mexico")]
    gap_off = off[W.elo_name("Spain")] - off[W.elo_name("Mexico")]
    assert gap_on > gap_off + 1.0          # offset opened a clear UEFA-over-CONCACAF gap


def test_conf_of_tournament():
    assert confed_bias.conf_of_tournament("UEFA Euro qualification") == "UEFA"
    assert confed_bias.conf_of_tournament("Gold Cup") == "CONCACAF"
    assert confed_bias.conf_of_tournament("Friendly") is None        # bridge game, excluded
    assert confed_bias.conf_of_tournament("FIFA World Cup") is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
