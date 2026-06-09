"""Tests for the cross-venue convergence forward-test accounting.

Run:  python -m pytest tests/test_forwardtest.py
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xresidual import forwardtest as ft  # noqa: E402


def _div(rows):
    """rows = [(pass_index, team, gap)] -> divergence DataFrame."""
    base = pd.Timestamp("2026-06-08T00:00:00+00:00")
    recs = [{"ts": base + pd.Timedelta(minutes=30 * i), "team": t, "gap": g}
            for i, t, g in rows]
    return pd.DataFrame(recs)


def test_converged_trade_is_profitable():
    # gap opens at 1.5pp, drifts, converges to 0.2pp at the last pass
    div = _div([(0, "X", 0.015), (1, "X", 0.012), (2, "X", 0.002)])
    res = ft.run_convergence(div, entry=0.010, exit=0.003, cost=0.005, max_hold=8)
    assert len(res["trades"]) == 1
    tr = res["trades"][0]
    assert tr["reason"] == "converged"
    # (|0.015| - |0.002|) - 0.005 = 0.008 -> 0.8pp
    assert abs(tr["pnl_pp"] - 0.8) < 1e-6
    assert res["summary"]["hit_rate"] == 1.0
    assert abs(res["summary"]["total_pnl_pp"] - 0.8) < 1e-6


def test_expired_trade_can_lose():
    # gap opens then widens; forced out at max_hold
    div = _div([(0, "Y", 0.012), (1, "Y", 0.020), (2, "Y", 0.025), (3, "Y", 0.030)])
    res = ft.run_convergence(div, entry=0.010, exit=0.003, cost=0.005, max_hold=2)
    assert len(res["trades"]) == 1
    tr = res["trades"][0]
    assert tr["reason"] == "expired"
    # closes at pass 2 (held==2==max_hold), gap 0.025: (0.012-0.025)-0.005 = -0.018 -> -1.8pp
    assert abs(tr["pnl_pp"] - (-1.8)) < 1e-6
    assert res["summary"]["hit_rate"] == 0.0


def test_no_trade_below_entry():
    div = _div([(0, "Z", 0.004), (1, "Z", 0.003), (2, "Z", 0.001)])
    res = ft.run_convergence(div)
    assert res["trades"] == []
    assert res["summary"]["n_trades"] == 0


def test_one_position_per_team_at_a_time():
    # stays open across several wide passes, then converges -> exactly one trade
    div = _div([(0, "X", 0.02), (1, "X", 0.02), (2, "X", 0.015), (3, "X", 0.001)])
    res = ft.run_convergence(div, entry=0.010, exit=0.003, cost=0.005, max_hold=8)
    assert len(res["trades"]) == 1
    assert res["trades"][0]["reason"] == "converged"


def test_equity_is_cumulative():
    div = _div([(0, "A", 0.015), (1, "A", 0.001),      # +profit, converged
                (2, "B", 0.015), (3, "B", 0.001)])     # +profit, converged
    res = ft.run_convergence(div, entry=0.010, exit=0.003, cost=0.005, max_hold=8)
    eq = res["equity"]
    assert len(eq) == 2
    # monotone since both win, and ends at the summary total
    assert eq[-1]["cum_pnl_pp"] == res["summary"]["total_pnl_pp"]
