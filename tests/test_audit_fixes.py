"""Regression tests for the repo-audit fixes (Tier 1/2). No network.

Run:  python tests/test_audit_fixes.py
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                   # noqa: E402
import pandas as pd                                  # noqa: E402

from xresidual import ws_events as we                # noqa: E402
from xresidual import microstructure as ms           # noqa: E402
from xresidual import group_sim as gs                # noqa: E402
from xresidual import forwardtest as ft              # noqa: E402


# --- file-per-capture loaders: scoping + torn-line guard ------------------------- #
def _write(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write((r if isinstance(r, str) else json.dumps(r)) + "\n")


def test_loaders_scope_to_one_capture_and_skip_torn_lines():
    with tempfile.TemporaryDirectory() as d:
        # two captures; "B" sorts after "A" so it's the latest
        capA = "20260101T000000Z-match-a"
        capB = "20260101T000001Z-match-b"
        _write(os.path.join(d, f"ws-events-{capA}.jsonl"), [
            {"t": 1, "venue": "polymarket", "type": "book", "market": "TOKA", "data": {}},
            '{"t": 2, "venue": "kalshi", BROKEN LINE',          # torn line must be skipped
            {"t": 3, "venue": "kalshi", "type": "ticker", "market": "KXA", "data": {}},
        ])
        _write(os.path.join(d, f"ws-events-{capB}.jsonl"), [
            {"t": 9, "venue": "polymarket", "type": "book", "market": "TOKB", "data": {}},
        ])
        _write(os.path.join(d, f"ws-pairs-{capA}.jsonl"),
               [{"t": 1, "label": "A win", "kalshi": "KXA", "poly": "TOKA"}])
        _write(os.path.join(d, f"ws-pairs-{capB}.jsonl"),
               [{"t": 9, "label": "B win", "kalshi": "KXB", "poly": "TOKB"}])

        assert we.latest_capture(d) == capB
        # capture A: torn line skipped (2 good rows of 3), and B's events don't leak in
        evA = we.load_ws_events(d, capture=capA)
        assert len(evA) == 2 and all(e["market"] in ("TOKA", "KXA") for e in evA)
        # pairs scoped to the same capture — A's legs never collide with B's tokens
        prA = we.load_pairs(d, capture=capA)
        assert len(prA) == 1 and prA[0]["poly"] == "TOKA"
        prB = we.load_pairs(d, capture=capB)
        assert prB[0]["poly"] == "TOKB"
        # default (no capture) picks the latest capture's events only
        assert {e["market"] for e in we.load_ws_events(d)} == {"TOKB"}


# --- _grid caps the forward-fill so a disconnect isn't fabricated as flat --------- #
def test_grid_does_not_fill_across_a_long_gap():
    series = [(0, 0.5), (10000, 0.6)]                # a 10s hole between two ticks
    g = we._grid(series, 0, 10000, bin_ms=1000, max_gap_ms=2000)
    assert g[0] == 0.5
    assert g[1] == 0.5 and g[2] == 0.5               # ffill up to the 2s cap
    assert np.isnan(g[3]) and np.isnan(g[9])         # beyond the cap: a hole, not a flat line
    assert g[10] == 0.6
    # unlimited (legacy) still fills everything
    g2 = we._grid(series, 0, 10000, bin_ms=1000, max_gap_ms=None)
    assert not np.isnan(g2).any()


# --- cross-venue divergence renormalizes over the COMMON team set ----------------- #
def test_divergence_uses_common_field_not_per_venue_coverage():
    # both venues agree on the A:B ratio; polymarket also quotes C, kalshi doesn't.
    # per-venue normalization would invent a gap; common-set renorm must cancel it.
    panel = pd.DataFrame([
        {"ts": "T", "venue": "polymarket", "team": "A", "prob": 0.50},
        {"ts": "T", "venue": "polymarket", "team": "B", "prob": 0.30},
        {"ts": "T", "venue": "polymarket", "team": "C", "prob": 0.20},
        {"ts": "T", "venue": "kalshi", "team": "A", "prob": 0.625},   # 0.50/0.80
        {"ts": "T", "venue": "kalshi", "team": "B", "prob": 0.375},   # 0.30/0.80
    ])
    div = ms.cross_venue_divergence(panel)
    assert not div.empty
    assert float(div["divergence"].max()) < 1e-9     # phantom coverage gap removed


# --- information_share refuses to name a leader on a non-cointegrated pair --------- #
def test_information_share_gated_on_cointegration():
    rng = np.random.default_rng(0)
    a = np.cumsum(rng.normal(0, 1, 300))             # two INDEPENDENT random walks:
    b = np.cumsum(rng.normal(0, 1, 300))             # a - b is non-stationary
    res = ms.information_share(a, b, "poly", "kalshi")
    assert res is not None
    assert res["cointegrated"] is False
    assert res["leader"] is None and res["gg_a"] is None and res["hasbrouck_a_mid"] is None
    assert res["adf_p"] is None or res["adf_p"] >= 0.10


# --- Dixon-Coles is applied in the per-sim (sigma>0) path -------------------------- #
def test_dc_sample_vec_lifts_draws_and_keeps_marginals():
    rng = np.random.default_rng(1)
    n = 60000
    lam = np.full(n, 1.3)
    g1, g2 = gs._dc_sample_vec(lam, lam, rho=-0.11, rng=rng)
    p00 = float(np.mean((g1 == 0) & (g2 == 0)))
    plain_p00 = np.exp(-1.3) * np.exp(-1.3)          # ~0.0743 under independent Poisson
    assert p00 > plain_p00 + 0.003                   # rho<0 lifts the 0-0 cell
    assert abs(g1.mean() - 1.3) < 0.05 and abs(g2.mean() - 1.3) < 0.05   # marginals ~intact
    # rho=0 must be a plain Poisson passthrough
    g1b, g2b = gs._dc_sample_vec(lam, lam, rho=0.0, rng=np.random.default_rng(2))
    assert abs(g1b.mean() - 1.3) < 0.05


# --- forward-test: a team already wide at the first pass must NOT open ------------- #
def test_forwardtest_no_first_pass_entry():
    # X starts wide and stays wide -> never reset below entry -> no trade.
    # Y starts tight (arms) then widens -> a legitimate detected crossing -> one trade.
    rows = []
    for i, ts in enumerate(["t0", "t1", "t2"]):
        rows.append({"ts": ts, "team": "X", "gap": 0.05})            # always above entry
        rows.append({"ts": ts, "team": "Y", "gap": 0.0 if i == 0 else 0.05})
    div = pd.DataFrame(rows)
    res = ft.run_convergence(div, entry=0.010, exit=0.003, cost=0.0, max_hold=8)
    traded = {t["team"] for t in res["trades"]}
    assert "X" not in traded                          # no entry on a start-time artifact
    assert "Y" in traded                              # armed by the t0 reset, opens at t1


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
