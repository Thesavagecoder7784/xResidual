#!/usr/bin/env python3
"""Event-driven cross-venue lead-lag forward-test (the in-play sibling of the convergence
null in writeups/cross-venue-price-discovery.md §6).

Pre-registered strategy: Polymarket leads Kalshi on in-play shocks (build_leadlag.py).
So when Polymarket's mid jumps >= MIN_JUMP inside a short window (a goal/red-card reprice),
take the SAME direction on Kalshi at its still-stale price and hold for HOLD_S, betting Kalshi
converges toward Polymarket. The question is whether that convergence is economically
capturable NET OF KALSHI'S SPREAD — fills cross the real bid/ask both ways, so the cost is
data-driven, not assumed. Direction is fixed in advance (follow the leader); we grade honestly.

  python scripts/leadlag_forwardtest.py            # all WC tapes present in logger/data
Runs on the laptop (parses the big tapes one at a time, like build_leadlag.py).
"""
from __future__ import annotations

import os
import sys
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import ws_events as we  # noqa: E402
from build_leadlag import wc_captures, _match_label, DATA_DIR  # noqa: E402

# --- pre-registered parameters ---------------------------------------------------------
MIN_JUMP = 0.04          # Polymarket move (prob units) that counts as a shock — same as lead-lag
WINDOW_MS = 3000         # ...within this trailing window (catch the goal reprice fast, before Kalshi)
REFRACTORY_MS = 60000    # one trade per shock (goals are minutes apart)
HOLD_S = 30              # hold horizon (capture Kalshi's seconds-long convergence)
# Entry latency sweep: 0s = the frictionless HFT fantasy (fill the instant the signal fires);
# realistic non-co-located execution is hundreds of ms to seconds. If the edge dies as latency
# rises, it lived only in the zero-latency fill — i.e. it's a speed mirage, not a harvestable edge.
ENTRY_LATENCIES_S = (0.0, 0.25, 0.5, 1.0, 2.0, 5.0)


def kalshi_book(events, ticker):
    """(t_ms, bid, ask) for one Kalshi market — the real top-of-book for realistic fills."""
    out = []
    for e in events:
        if e.get("venue") != "kalshi" or e.get("type") != "ticker" or e.get("market") != ticker:
            continue
        d = e["data"]
        bid, ask = we._f(d.get("yes_bid_dollars")), we._f(d.get("yes_ask_dollars"))
        if bid is not None and ask is not None and ask >= bid:
            out.append((e["t"], bid, ask))
    return out


def _book_at(book, t):
    """Last (bid, ask, quote_t) at or before t; None if t precedes the book."""
    res = None
    for tt, b, a in book:
        if tt <= t:
            res = (b, a, tt)
        else:
            break
    return res


def poly_triggers(mid, min_jump, window_ms, refractory_ms):
    """Times Polymarket moved >= min_jump within a trailing window_ms -> [(t_ms, signed_jump)].
    Detects the shock ONSET (no persistence wait) — a trading signal can't wait to confirm."""
    trigs, last, j = [], -10 ** 18, 0
    for t, v in mid:
        while j + 1 < len(mid) and mid[j + 1][0] <= t - window_ms:
            j += 1
        base_t, base_v = mid[j]
        if base_t > t - window_ms + 1:          # not enough trailing history
            continue
        jump = v - base_v
        if abs(jump) >= min_jump and t - last >= refractory_ms:
            trigs.append((t, jump))
            last = t
    return trigs


def trade(book, t_sig, dirn, hold_s, lat_s=0.0):
    """One paper trade: enter at t_sig + lat_s (execution latency), exit hold_s later, crossing
    Kalshi's real bid/ask. Long (dirn>0): buy at ask, sell at bid. Short: sell at bid, buy at ask.
    Returns (net_pnl, gross_mid_pnl, entry_spread, quote_staleness_s) in prob units, or None."""
    t_entry = t_sig + int(lat_s * 1000)
    eb = _book_at(book, t_entry)
    xb = _book_at(book, t_entry + hold_s * 1000)
    if eb is None or xb is None or book[-1][0] < t_entry + hold_s * 1000:
        return None                              # need a real exit inside the capture
    (ebid, eask, et), (xbid, xask, _) = eb, xb
    emid, xmid = (ebid + eask) / 2, (xbid + xask) / 2
    if dirn > 0:
        net = xbid - eask                        # bought the ask, sold the bid
        gross = xmid - emid
    else:
        net = ebid - xask                        # sold the bid, bought the ask
        gross = emid - xmid
    stale_s = (t_entry - et) / 1000              # how old the Kalshi quote we "filled" at was
    return net, gross, eask - ebid, stale_s


def run():
    """One pass over each tape; every trigger evaluated at all ENTRY_LATENCIES_S. Returns {lat: {...}}."""
    caps = wc_captures(DATA_DIR)
    res = {L: {"nets": [], "grosses": [], "spreads": [], "stale": []} for L in ENTRY_LATENCIES_S}
    for cap in caps:
        events = we.load_ws_events(DATA_DIR, capture=cap)
        pairs = we.load_pairs(DATA_DIR, capture=cap)
        if not events or not pairs:
            continue
        for pr in pairs:
            poly = we.polymarket_mid_series(events, pr.get("poly")) if pr.get("poly") else []
            book = kalshi_book(events, pr.get("kalshi")) if pr.get("kalshi") else []
            if len(poly) < 10 or len(book) < 10:
                continue
            for t_sig, jump in poly_triggers(poly, MIN_JUMP, WINDOW_MS, REFRACTORY_MS):
                dirn = 1 if jump > 0 else -1
                for L in ENTRY_LATENCIES_S:
                    r = trade(book, t_sig, dirn, HOLD_S, L)
                    if r is None:
                        continue
                    net, gross, spr, stale_s = r
                    res[L]["nets"].append(net); res[L]["grosses"].append(gross)
                    res[L]["spreads"].append(spr); res[L]["stale"].append(stale_s)
        del events
    return res


def _summ(xs):
    if not xs:
        return "n=0"
    mean = sum(xs) / len(xs)
    hit = sum(1 for x in xs if x > 0) / len(xs)
    sharpe = mean / st.pstdev(xs) if len(xs) > 1 and st.pstdev(xs) > 0 else float("nan")
    return (f"n={len(xs)}  total {sum(xs) * 100:+.1f}pp  mean {mean * 100:+.2f}pp  "
            f"hit {hit:.0%}  Sharpe {sharpe:+.2f}")


def main():
    print("Cross-venue lead-lag forward-test (follow Polymarket on a shock, trade Kalshi):")
    print(f"  MIN_JUMP={MIN_JUMP}  detect-window={WINDOW_MS/1000:.0f}s  hold={HOLD_S}s  "
          f"refractory={REFRACTORY_MS/1000:.0f}s")
    print("  Entry-latency sweep — net P&L vs how fast you fill after the signal:\n")
    res = run()
    print(f"  {'latency':>8} | {'NET (cross spread)':<46} | {'GROSS (mid)':<22}")
    print("  " + "-" * 82)
    for L in ENTRY_LATENCIES_S:
        print(f"  {L:>6.2f}s | {_summ(res[L]['nets']):<46} | {_summ(res[L]['grosses'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
