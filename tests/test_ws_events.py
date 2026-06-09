"""Tests for the websocket lead-lag analysis (no network).

Run:  python tests/test_ws_events.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xresidual import ws_events as we  # noqa: E402


def test_kalshi_mid_from_ticker():
    events = [
        {"venue": "kalshi", "type": "ticker", "market": "T", "t": 1000,
         "data": {"yes_bid_dollars": "0.16", "yes_ask_dollars": "0.18"}},
        {"venue": "kalshi", "type": "trade", "market": "T", "t": 1001, "data": {}},  # ignored
    ]
    s = we.kalshi_mid_series(events, "T")
    assert len(s) == 1 and s[0][0] == 1000 and abs(s[0][1] - 0.17) < 1e-9


def test_polymarket_mid_from_book_and_deltas():
    a = "TOK"
    events = [
        {"venue": "polymarket", "type": "book", "market": a, "t": 1000,
         "data": {"bids": [{"price": "0.15", "size": "100"}],
                  "asks": [{"price": "0.17", "size": "100"}]}},
        {"venue": "polymarket", "type": "price_change", "market": a, "t": 1100,
         "data": {"price_changes": [{"asset_id": a, "price": "0.16", "size": "50", "side": "BUY"}]}},
    ]
    s = we.polymarket_mid_series(events, a)
    assert abs(s[0][1] - 0.16) < 1e-9    # (0.15 + 0.17)/2
    assert abs(s[1][1] - 0.165) < 1e-9   # best bid moved to 0.16 -> (0.16 + 0.17)/2


def test_lead_lag_ms_recovers_known_shift():
    # Polymarket leads; Kalshi prints the same mids 2 bins (2000ms) later.
    mids = [0.10, 0.12, 0.11, 0.14, 0.12, 0.15, 0.13, 0.16, 0.14, 0.17,
            0.15, 0.18, 0.16, 0.19, 0.17, 0.20]
    poly = [(i * 1000, m) for i, m in enumerate(mids)]
    kal = [((i + 2) * 1000, m) for i, m in enumerate(mids)]
    res = we.lead_lag_ms(kal, poly, bin_ms=1000, max_lag_ms=6000)
    assert res is not None
    assert res["leader"] == "polymarket" and res["best_lag_ms"] == 2000
    assert res["best_corr"] > 0.9


def test_lead_lag_none_on_flat():
    flat = [(i * 1000, 0.5) for i in range(20)]
    assert we.lead_lag_ms(flat, flat) is None   # nothing moves -> no signal


def _goal_series(jump, give_back_frac, t0=0):
    """Synthetic mid path: flat at 0.20 pre-goal, jumps by `jump` at t0, then gives
    back `give_back_frac` of the jump by +180s."""
    pre = [(t0 + t * 1000, 0.20) for t in range(-20, -1)]
    settle = 0.20 + jump
    post_settle = [(t0 + t * 1000, settle) for t in range(4, 13)]
    later = settle - give_back_frac * jump
    drift = [(t0 + t * 1000, later) for t in (60, 120, 180, 240, 300)]
    return pre + post_settle + drift


def test_goal_reaction_measures_jump_and_reversal():
    s = _goal_series(jump=0.30, give_back_frac=0.5)   # overreaction: half given back
    r = we.goal_reaction(s, 0)
    assert abs(r["pre"] - 0.20) < 1e-6 and abs(r["jump"] - 0.30) < 1e-6
    assert abs(r["reversals"][180]["reversal_frac"] - 0.5) < 1e-6   # half reverted
    assert abs(r["surprise"] - 0.80) < 1e-6                          # 1 - pre


def test_efficient_goal_has_no_reversal():
    s = _goal_series(jump=0.30, give_back_frac=0.0)   # price sticks -> efficient
    r = we.goal_reaction(s, 0)
    assert abs(r["reversals"][180]["reversal_frac"]) < 1e-6


def test_overreaction_summary_splits_by_surprise():
    # surprising goals (low pre -> high surprise) revert; expected ones (high pre) don't
    surprising = we.goal_reaction(_goal_series(0.30, 0.6), 0)            # pre .20, surprise .80
    expected = [(t * 1000, 0.70) for t in range(-20, -1)] + \
               [(t * 1000, 0.80) for t in range(4, 13)] + \
               [(t * 1000, 0.80) for t in (60, 120, 180, 240, 300)]     # pre .70, no reversal
    exp = we.goal_reaction(expected, 0)
    summ = we.overreaction_summary([surprising, exp], horizon_s=180)
    assert summ["n"] == 2
    assert summ["surprising_goals_reversal"] > summ["expected_goals_reversal"]


def _ramp_series(jump_ms, base=0.60, post=0.78, lo=-9000, hi=20000, step=200):
    pts = []
    for ms in range(lo, hi + 1, step):
        if ms < jump_ms:
            p = base
        elif ms < jump_ms + 500:
            p = base + (post - base) * ((ms - jump_ms) / 500)
        else:
            p = post
        pts.append((ms, round(p, 4)))
    return pts


def test_detect_shocks_finds_the_jump():
    shocks = we.detect_shocks(_ramp_series(0), min_jump=0.04)
    assert len(shocks) == 1                         # one move, one shock (refractory holds)
    assert shocks[0]["dir"] == "up" and shocks[0]["jump"] > 0.04


def test_detect_shocks_ignores_flat():
    flat = [(ms, 0.5) for ms in range(-9000, 20001, 200)]
    assert we.detect_shocks(flat, min_jump=0.04) == []


def _venue_events(kal, poly, kt="KX", pa="PA"):
    ev = [{"t": ms, "venue": "kalshi", "type": "ticker", "market": kt,
           "data": {"yes_bid_dollars": round(p - 0.005, 4), "yes_ask_dollars": round(p + 0.005, 4)}}
          for ms, p in kal]
    for i, (ms, p) in enumerate(poly):
        b, a = round(p - 0.005, 3), round(p + 0.005, 3)
        if i == 0:
            ev.append({"t": ms, "venue": "polymarket", "type": "book", "market": pa,
                       "data": {"bids": [{"price": b, "size": 100}], "asks": [{"price": a, "size": 100}]}})
        else:
            ev.append({"t": ms, "venue": "polymarket", "type": "price_change", "market": pa,
                       "data": {"price_changes": [{"asset_id": pa, "price": b, "size": 100, "side": "BUY"},
                                                  {"asset_id": pa, "price": a, "size": 100, "side": "SELL"}]}})
    ev.sort(key=lambda e: e["t"])
    return ev


def test_auto_lead_lag_recovers_known_lead():
    # Polymarket jumps at t=0, Kalshi follows 1.4s later -> Polymarket should lead.
    # Sharp synthetic ramp, so use the 4s detection regime (the production default is 60s,
    # tuned for real goals that reprice gradually).
    ev = _venue_events(_ramp_series(1400), _ramp_series(0))
    res = we.auto_lead_lag(ev, [{"label": "A vs B", "kalshi": "KX", "poly": "PA"}],
                           lookback_ms=4000)
    assert res[0]["n_events"] == 1
    e = res[0]["events"][0]
    assert e["lead"]["leader"] == "polymarket" and e["lead"]["best_lag_ms"] > 0
    pooled = we.pool_leads(res)
    assert pooled["leader"] == "polymarket" and pooled["n"] == 1


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
