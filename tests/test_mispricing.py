"""Tests for the mispricing scanner + FLB term structure. No network.

Run:  python tests/test_mispricing.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xresidual import mispricing as M  # noqa: E402


def test_scan_gap_side_and_confound():
    out = M.scan([
        {"layer": "x", "team": "Morocco", "model": 26.0, "market": 22.0},   # underpriced -> back
        {"layer": "x", "team": "Brazil", "model": 21.0, "market": 31.5},    # overpriced -> fade
        {"layer": "x", "team": "Mexico", "model": 20.0, "market": 26.5},    # host -> confounded
        {"layer": "x", "team": "Z", "model": None, "market": 5.0},          # dropped
    ])
    assert len(out) == 3
    mor = next(c for c in out if c["team"] == "Morocco")
    assert mor["gap"] == 4.0 and mor["side"] == "back" and mor["confound"] is False
    bra = next(c for c in out if c["team"] == "Brazil")
    assert bra["gap"] == -10.5 and bra["side"] == "fade"
    assert next(c for c in out if c["team"] == "Mexico")["confound"] is True


def test_term_structure_detects_flb_shape_and_efficiency():
    # an EFFICIENT layer: model ~= market for everyone -> ~0 gaps
    eff = [{"layer": "winner", "team": t, "model": v, "market": v + d}
           for t, v, d in [("A", 30, 0.1), ("B", 20, -0.1), ("C", 10, 0.0), ("D", 5, 0.1)]]
    # an FLB layer: favourites (high market) overpriced, longshots (low) underpriced
    flb = [{"layer": "elim", "team": t, "model": m, "market": k}
           for t, m, k in [("W", 25, 32), ("X", 18, 24), ("Y", 12, 8), ("Z", 9, 5)]]
    ts = {r["layer"]: r for r in M.term_structure(M.scan(eff + flb))}
    assert ts["winner"]["mean_abs_gap"] < 0.5                  # efficient layer ~ flat
    assert abs(ts["winner"]["flb_spread"]) < 0.5
    assert ts["elim"]["fav_gap"] < 0                           # favourites overpriced
    assert ts["elim"]["longshot_gap"] > 0                      # longshots underpriced
    assert ts["elim"]["flb_spread"] > ts["winner"]["flb_spread"]   # bias grows in the thin layer


def test_top_edges_ranks_and_excludes_hosts():
    sc = M.scan([
        {"layer": "l", "team": "Morocco", "model": 26, "market": 22},   # +4 back
        {"layer": "l", "team": "Ecuador", "model": 12, "market": 7},     # +5 back (biggest)
        {"layer": "l", "team": "Brazil", "model": 21, "market": 32},     # -11 fade (biggest)
        {"layer": "l", "team": "Canada", "model": 20, "market": 10},     # +10 but host -> excluded
    ])
    e = M.top_edges(sc, n=8)
    assert [c["team"] for c in e["backs"]][:2] == ["Ecuador", "Morocco"]   # ranked, host dropped
    assert "Canada" not in [c["team"] for c in e["backs"]]
    assert e["fades"][0]["team"] == "Brazil"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
