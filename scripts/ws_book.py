#!/usr/bin/env python3
"""Order-book + flow reconstruction from the captured ws-events tapes (fork-forward of the
frozen, mids-only xresidual/ws_events). Turns the raw stream into the objects microstructure
analysis needs but v1 never extracted:

  - top-of-book series   {t, bid, bid_sz, ask, ask_sz}  per contract, per venue
  - mid + microprice     the imbalance-weighted price (Stoikov 2017, weighted-mid form): the
                         size on the FAR side pulls the fair price toward it, so a heavy bid
                         predicts an up-move. A better short-horizon fair value than the mid.
  - OFI increments       Order-Flow Imbalance (Cont, Kukanov & Stoikov 2014): the signed change
                         in top-of-book liquidity. Bid lifts / ask pulls = +OFI (buy pressure);
                         the canonical short-horizon driver of price.
  - signed trade flow    aggressor-signed executed volume (+buy / -sell), per contract.

Conventions match xresidual/ws_events (so this composes with load_ws_events):
  Kalshi `ticker` carries yes_bid/ask_dollars AND yes_bid/ask_size_fp -> top-of-book directly.
  Polymarket: reconstruct the book from `book` snapshots + `price_change` (BUY->bid, SELL->ask,
  size REPLACES the level), then read the touch.

These functions take the already-loaded `events` list (one heavy load per tape, on the laptop)
and a contract id, exactly like the v1 mid-series functions. xresidual/ is not modified.
"""
from __future__ import annotations


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def kalshi_top_of_book(events: list[dict], ticker: str) -> list[dict]:
    """Top-of-book {t, bid, bid_sz, ask, ask_sz} from Kalshi `ticker` events (yes side)."""
    out = []
    for e in events:
        if e["venue"] != "kalshi" or e["type"] != "ticker" or e["market"] != ticker:
            continue
        d = e["data"]
        bid, ask = _f(d.get("yes_bid_dollars")), _f(d.get("yes_ask_dollars"))
        if bid is None or ask is None:
            continue
        out.append({"t": e["t"], "bid": bid, "ask": ask,
                    "bid_sz": _f(d.get("yes_bid_size_fp")) or 0.0,
                    "ask_sz": _f(d.get("yes_ask_size_fp")) or 0.0})
    return out


def polymarket_top_of_book(events: list[dict], asset_id: str) -> list[dict]:
    """Top-of-book for one Polymarket token, reconstructing the book from snapshot + price_change."""
    bids: dict[float, float] = {}
    asks: dict[float, float] = {}
    out = []
    for e in events:
        if e["venue"] != "polymarket":
            continue
        d = e["data"]
        touched = False
        if e["type"] == "book" and e["market"] == asset_id:
            bids = {_f(x["price"]): _f(x["size"]) for x in d.get("bids", [])}
            asks = {_f(x["price"]): _f(x["size"]) for x in d.get("asks", [])}
            touched = True
        elif e["type"] == "price_change":
            for ch in d.get("price_changes", []):
                if ch.get("asset_id") != asset_id:
                    continue
                price, size, side = _f(ch.get("price")), _f(ch.get("size")), ch.get("side")
                if price is None:
                    continue
                (bids if side == "BUY" else asks)[price] = size or 0.0
                touched = True
        if not touched:
            continue
        bb = [(p, s) for p, s in bids.items() if s > 0]
        aa = [(p, s) for p, s in asks.items() if s > 0]
        if not bb or not aa:
            continue
        bp, bs = max(bb, key=lambda x: x[0])
        ap, as_ = min(aa, key=lambda x: x[0])
        out.append({"t": e["t"], "bid": bp, "ask": ap, "bid_sz": bs, "ask_sz": as_})
    return out


def add_prices(tob: list[dict]) -> list[dict]:
    """Annotate each top-of-book record with mid and microprice (imbalance-weighted). In place."""
    for r in tob:
        b, a, bs, as_ = r["bid"], r["ask"], r["bid_sz"], r["ask_sz"]
        r["mid"] = (b + a) / 2.0
        tot = bs + as_
        # weighted-mid microprice: heavy bid (bs large) -> weight on ask -> price toward ask.
        r["micro"] = (b * as_ + a * bs) / tot if tot > 0 else r["mid"]
    return tob


def ofi_increments(tob: list[dict]) -> list[tuple[int, float]]:
    """(t, e_n) Order-Flow Imbalance increments from consecutive top-of-book states
    (Cont-Kukanov-Stoikov 2014). e_n = bid-contribution - ask-contribution:
      bid: +q^b if bid price rose, (q^b - q^b_prev) if unchanged, -q^b_prev if it fell;
      ask: -q^a_prev if ask price rose, (q^a - q^a_prev) if unchanged, +q^a if it fell.
    Bid building or ask pulling => +OFI => upward price pressure."""
    inc = []
    for n in range(1, len(tob)):
        p, c = tob[n - 1], tob[n]
        if c["bid"] > p["bid"]:
            db = c["bid_sz"]
        elif c["bid"] == p["bid"]:
            db = c["bid_sz"] - p["bid_sz"]
        else:
            db = -p["bid_sz"]
        if c["ask"] > p["ask"]:
            da = -p["ask_sz"]
        elif c["ask"] == p["ask"]:
            da = c["ask_sz"] - p["ask_sz"]
        else:
            da = c["ask_sz"]
        inc.append((c["t"], db - da))
    return inc


def kalshi_signed_trades(events: list[dict], ticker: str) -> list[tuple[int, float, float]]:
    """(t, signed_size, price) for Kalshi trades: +size if the taker bought yes, -size if no."""
    out = []
    for e in events:
        if e["venue"] != "kalshi" or e["type"] != "trade" or e["market"] != ticker:
            continue
        d = e["data"]
        sz = _f(d.get("count_fp")) or 0.0
        sgn = 1.0 if d.get("taker_side") == "yes" else -1.0
        out.append((e["t"], sgn * sz, _f(d.get("yes_price_dollars"))))
    return out


def polymarket_signed_trades(events: list[dict], asset_id: str) -> list[tuple[int, float, float]]:
    """(t, signed_size, price) for Polymarket trades on one token: +size BUY, -size SELL."""
    out = []
    for e in events:
        if e["venue"] != "polymarket" or e["type"] != "last_trade_price":
            continue
        d = e["data"]
        if d.get("asset_id") != asset_id and e.get("market") != asset_id:
            continue
        sz = _f(d.get("size")) or 0.0
        sgn = 1.0 if d.get("side") == "BUY" else -1.0
        out.append((e["t"], sgn * sz, _f(d.get("price"))))
    return out
