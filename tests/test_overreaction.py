"""Tests for the goal-overreaction fade backtest on synthetic in-play series."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xresidual import ws_events as we  # noqa: E402


def _series(after_jump):
    """0.30 flat for 300s, a goal spike to 0.45 at 300s, then `after_jump(t)` to 660s."""
    s = [(t * 1000, 0.30) for t in range(0, 300)]
    s += [(t * 1000, after_jump(t)) for t in range(300, 661)]
    return s


def test_reversion_is_profitable():
    # spike to 0.45, then revert linearly to 0.36 by +6 min
    s = _series(lambda t: 0.45 - 0.09 * (t - 300) / 360)
    r = we.overreaction_backtest(s, min_jump=0.04, entry_s=120, exit_s=360, cost=0.005)
    assert r["summary"]["n"] == 1
    tr = r["trades"][0]
    assert tr["pnl_pp"] > 0          # fading the overreaction made money
    assert tr["reverted_pp"] > 4     # captured most of the reversion
    assert abs(tr["surprise"] - 0.5) < 0.01   # |0.15| / 0.30


def test_no_reversion_loses_the_cost():
    # spike to 0.45 and stay there: the fade just pays the round-trip cost
    s = _series(lambda t: 0.45)
    r = we.overreaction_backtest(s, min_jump=0.04, entry_s=120, exit_s=360, cost=0.005)
    assert r["summary"]["n"] == 1
    assert r["trades"][0]["pnl_pp"] < 0


def test_surprise_filter_excludes_small_shocks():
    s = _series(lambda t: 0.45 - 0.09 * (t - 300) / 360)
    # require surprise >= 1.0; this shock is 0.5, so it's filtered out
    r = we.overreaction_backtest(s, min_jump=0.04, min_surprise=1.0)
    assert r["summary"]["n"] == 0


def test_window_past_series_end_returns_no_trade():
    # shock near the very end: exit window runs past the data -> no trade
    s = [(t * 1000, 0.30) for t in range(0, 300)] + [(300 * 1000, 0.45), (305 * 1000, 0.45)]
    r = we.overreaction_backtest(s, min_jump=0.04, exit_s=360)
    assert r["summary"]["n"] == 0
