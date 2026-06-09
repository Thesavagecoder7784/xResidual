"""Tests for on-chain signed order-flow helpers (network-free)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xresidual import onchain  # noqa: E402


def _t(ts_ms, side, size=1.0, price=0.5):
    return {"ts_ms": ts_ms, "side": side, "size": size, "price": price}


def test_signed_order_flow_sign():
    trades = [_t(0, "BUY", 3), _t(1, "SELL", 1)]
    assert abs(onchain.signed_order_flow(trades) - 0.5) < 1e-9   # (3-1)/4
    assert onchain.signed_order_flow([]) != onchain.signed_order_flow([])  # nan


def test_ofi_series_buckets():
    trades = [_t(0, "BUY"), _t(10, "BUY"), _t(70_000, "SELL")]
    s = onchain.ofi_series(trades, window_ms=60_000)
    assert len(s) == 2
    assert s[0]["ofi"] == 1.0 and s[0]["n"] == 2
    assert s[1]["ofi"] == -1.0


def test_direction_accuracy():
    ws = ["BUY", "SELL", "BUY", "BUY"]
    truth = ["BUY", "BUY", "BUY", "SELL"]   # 2/4 right
    r = onchain.direction_accuracy(ws, truth)
    assert r["n"] == 4 and abs(r["accuracy"] - 0.5) < 1e-9
    assert onchain.direction_accuracy([], []) is None
