"""On-chain Polymarket trade reader: true trade direction for order-flow work.

Why this exists. The public WebSocket feed lets you *infer* trade direction (tick rule),
but Hawkes et al. (2026) show that inference is only ~59% accurate on Polymarket, which
flips the sign of any signed microstructure measure (order-flow imbalance, Kyle's lambda)
on a majority of markets. The authoritative direction lives on-chain in the CTF Exchange
`OrderFilled` events. This module reads it, so signed metrics use ground truth instead of
a coin-flip-plus-9%.

Two sources, both used by the literature:
  - Polymarket data-API `/trades` (HTTP, public): returns each trade's taker `side`,
    `price`, `size`, `timestamp`. Simplest path to true direction; sourced from the chain.
  - Goldsky CTF subgraph (GraphQL): raw `OrderFilled` / `ordersMatched` events on Polygon,
    for when you want the on-chain record directly (maker/taker, tx hash).

This is a scaffold: the query code and the signed-OFI / direction-validation math are here
and unit-tested on synthetic input, but the live endpoint schemas should be validated
against a real market before the tournament (they drift). Network calls fail soft (return
[] / None) so nothing here can crash a capture run.
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np

DATA_API_TRADES = "https://data-api.polymarket.com/trades"
GOLDSKY_SUBGRAPH = (
    "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/"
    "subgraphs/orderbook-subgraph/prod/gn"
)
_TIMEOUT = 15


def fetch_trades(market: str, limit: int = 1000, before_ms: Optional[int] = None,
                 asset: Optional[str] = None) -> list[dict]:
    """Recent trades for a Polymarket condition id, newest first, as
    [{ts_ms, price, size, side, asset}] with side in {'BUY','SELL'} (taker side = true
    direction). Pass `asset` (an outcome token id) to keep only that contract's trades,
    so signed order flow is per-outcome rather than mixed across YES/NO. Returns [] on
    any failure. VALIDATED against the live data-API schema 2026-06-07 (fields: side,
    size, price, timestamp[unix s], asset, conditionId, transactionHash)."""
    try:
        import requests
    except Exception:
        return []
    params = {"market": market, "limit": limit}
    if before_ms is not None:
        params["before"] = before_ms // 1000
    try:
        r = requests.get(DATA_API_TRADES, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        rows = r.json()
    except Exception:
        return []
    out = []
    for t in rows if isinstance(rows, list) else []:
        ts = t.get("timestamp") or t.get("matchtime") or t.get("time")
        side = (t.get("side") or t.get("takerSide") or "").upper()
        price, size, tok = t.get("price"), t.get("size"), t.get("asset")
        if ts is None or price is None or size is None or side not in ("BUY", "SELL"):
            continue
        if asset is not None and tok != asset:
            continue
        ts = int(ts)
        out.append({"ts_ms": ts * 1000 if ts < 10_000_000_000 else ts,
                    "price": float(price), "size": float(size), "side": side, "asset": tok})
    return out


def subgraph_order_fills(condition_id: str, first: int = 1000) -> list[dict]:
    """Raw on-chain fills via the Goldsky CTF subgraph (maker/taker, amounts, timestamp).
    OPTIONAL / secondary: the data-API above already carries ground-truth taker side, so
    this is only for when you want the chain record itself. NOTE: the Goldsky endpoint
    below returned empty on 2026-06-07 (URL/schema drift); update GOLDSKY_SUBGRAPH to the
    current published endpoint before relying on it. Fails soft (returns [])."""
    try:
        import requests
    except Exception:
        return []
    q = """
    query($id: String!, $first: Int!) {
      orderFilledEvents(first: $first, orderBy: timestamp, orderDirection: desc,
                        where: {market: $id}) {
        timestamp makerAssetId takerAssetId makerAmountFilled takerAmountFilled
      }
    }"""
    try:
        r = requests.post(GOLDSKY_SUBGRAPH,
                          json={"query": q, "variables": {"id": condition_id, "first": first}},
                          timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json().get("data", {}).get("orderFilledEvents", []) or []
    except Exception:
        return []


def signed_order_flow(trades: list[dict]) -> float:
    """Signed order-flow imbalance from true sides: (buy_size - sell_size) / total_size,
    in [-1, 1]. Positive = net buying pressure. The whole point of using on-chain side
    instead of WS-inferred direction is that this number has the right sign."""
    if not trades:
        return float("nan")
    buy = sum(t["size"] for t in trades if t["side"] == "BUY")
    sell = sum(t["size"] for t in trades if t["side"] == "SELL")
    tot = buy + sell
    return float((buy - sell) / tot) if tot > 0 else float("nan")


def ofi_series(trades: list[dict], window_ms: int = 60_000) -> list[dict]:
    """Signed order-flow imbalance bucketed into `window_ms` windows, oldest first:
    [{ts_ms, ofi, n}]. Feeds the OFI-predicts-returns regression with correct signs."""
    if not trades:
        return []
    ts = np.array([t["ts_ms"] for t in trades])
    t0, t1 = ts.min(), ts.max()
    out = []
    for start in range(int(t0), int(t1) + 1, window_ms):
        bucket = [t for t in trades if start <= t["ts_ms"] < start + window_ms]
        if bucket:
            out.append({"ts_ms": start, "ofi": signed_order_flow(bucket), "n": len(bucket)})
    return out


def direction_accuracy(ws_inferred: list[str], onchain_true: list[str]) -> Optional[dict]:
    """Validate the WS tick-rule direction against on-chain truth, trade-for-trade.
    Reproduces the Hawkes et al. (2026) ~59% finding on our own data and justifies, in
    the writeup, why signed metrics use this module. Both lists are aligned 'BUY'/'SELL'.
    Returns {accuracy, n} or None."""
    n = min(len(ws_inferred), len(onchain_true))
    if n == 0:
        return None
    hits = sum(1 for a, b in zip(ws_inferred[:n], onchain_true[:n]) if a == b)
    return {"accuracy": round(hits / n, 4), "n": n}


def _now_ms() -> int:
    return int(time.time() * 1000)
