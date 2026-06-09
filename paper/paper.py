#!/usr/bin/env python3
"""Paper-trading tracker for xResidual (F-1-safe: no real orders, no capital).

Log hypothetical positions, mark them to LIVE Polymarket prices, and compute unrealized
and realized P&L. Trades are entered from chat (the assistant runs `open`); prices are
fetched live each `mark`/`report`.

    python paper/paper.py open --market <slug> --outcome "Champion" --side yes --price 0.11 --stake 100 --note "..."
    python paper/paper.py mark                 # live value + unrealized P&L of open positions
    python paper/paper.py close <id> [--price 0.18]   # close at live price (or a given price)
    python paper/paper.py report               # full book: money in, unrealized, realized

P&L mechanics (buying a YES/NO contract priced p in [0,1] that pays $1 if it resolves):
    shares = stake / p ;  value = shares * price_now ;  pnl = value - stake
A modeled round-trip cost (COST_BPS of stake) is applied to realized P&L for the 'net' line.
We can't predict the future price; `mark` shows the value at the CURRENT real price.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from datetime import datetime, timezone

import requests

DIR = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(DIR, "positions.json")     # raw machine ledger
BOOK = os.path.join(DIR, "book.md")              # human-readable tracker (open this one)
GAMMA = "https://gamma-api.polymarket.com/events"
COST_BPS = 100          # modeled round-trip cost (bps of stake) for the realized 'net' line


def _load() -> list:
    return json.load(open(LEDGER, encoding="utf-8")) if os.path.exists(LEDGER) else []


def _save(p: list) -> None:
    tmp = LEDGER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2)
    os.replace(tmp, LEDGER)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def live_price(venue: str, market: str, outcome: str, side: str) -> float | None:
    """Current price of `outcome` (side yes/no) on a Polymarket event slug. None if it
    can't be resolved (bad slug/outcome or network)."""
    if venue != "polymarket":
        return None                                   # Kalshi support can be added later
    try:
        ev = requests.get(GAMMA, params={"slug": market}, timeout=15).json()
        ev = ev[0] if isinstance(ev, list) and ev else ev
    except Exception:
        return None
    if not isinstance(ev, dict):
        return None
    o = outcome.lower()
    for m in ev.get("markets", []):
        title = (m.get("groupItemTitle") or m.get("question") or "").lower()
        if o in title or title in o:
            pr = m.get("outcomePrices")
            pr = ast.literal_eval(pr) if isinstance(pr, str) else pr
            if pr:
                return float(pr[0] if side == "yes" else pr[1])
    return None


def cmd_open(a) -> None:
    p = _load()
    pid = max([x["id"] for x in p], default=0) + 1
    shares = a.stake / a.price
    lp = live_price(a.venue, a.market, a.outcome, a.side)
    p.append({"id": pid, "ts_open": _now(), "venue": a.venue, "market": a.market,
              "outcome": a.outcome, "side": a.side, "entry_price": a.price,
              "stake_usd": a.stake, "shares": round(shares, 2), "status": "open",
              "note": a.note or "", "exit_price": None, "ts_close": None,
              "realized_pnl": None, "realized_pnl_net": None})
    _save(p)
    tag = f"live now {lp:.3f}" if lp is not None else "WARNING: live price not resolved — check --market/--outcome"
    print(f"opened #{pid}: {a.side.upper()} {a.outcome} @ {a.price} (${a.stake:.0f}) "
          f"= {shares:.1f} shares | {tag}")


def cmd_mark(a) -> None:
    opens = [x for x in _load() if x["status"] == "open"]
    if not opens:
        print("no open positions")
        return
    print(f"{'#':>2}  {'market / outcome':34} {'sd':3} {'in$':>6} {'entry':>6} "
          f"{'now':>6} {'value$':>8} {'uPnL$':>8} {'uPnL%':>7}")
    tin = tval = 0.0
    for x in opens:
        lp = live_price(x["venue"], x["market"], x["outcome"], x["side"])
        lbl = f"{x['market'].replace('world-cup-', '').replace('-stage-of-elimination', ' elim')}/{x['outcome']}"[:34]
        if lp is None:
            print(f"{x['id']:>2}  {lbl:34} {x['side'][:3]:3} {x['stake_usd']:6.0f}  (live price unavailable)")
            continue
        val = x["shares"] * lp
        up = val - x["stake_usd"]
        tin += x["stake_usd"]; tval += val
        print(f"{x['id']:>2}  {lbl:34} {x['side'][:3]:3} {x['stake_usd']:6.0f} {x['entry_price']:6.3f} "
              f"{lp:6.3f} {val:8.1f} {up:+8.1f} {up / x['stake_usd'] * 100:+6.1f}%")
    print("-" * 86)
    print(f"{'':>2}  {'TOTAL OPEN':34} {'':3} {tin:6.0f} {'':6} {'':6} {tval:8.1f} "
          f"{tval - tin:+8.1f} {((tval - tin) / tin * 100) if tin else 0:+6.1f}%")


def cmd_close(a) -> None:
    p = _load()
    pos = next((x for x in p if x["id"] == a.id and x["status"] == "open"), None)
    if not pos:
        print(f"no open position #{a.id}")
        return
    price = a.price if a.price is not None else live_price(pos["venue"], pos["market"],
                                                           pos["outcome"], pos["side"])
    if price is None:
        print("could not get an exit price; pass --price")
        return
    gross = pos["shares"] * price - pos["stake_usd"]
    cost = pos["stake_usd"] * COST_BPS / 10000
    pos.update({"exit_price": price, "ts_close": _now(), "status": "closed",
                "realized_pnl": round(gross, 2), "realized_pnl_net": round(gross - cost, 2)})
    _save(p)
    print(f"closed #{a.id} @ {price:.3f}: realized {gross:+.1f} gross / {gross - cost:+.1f} net")


def _mkt_label(x: dict) -> str:
    base = x["market"].replace("world-cup-", "").replace("-stage-of-elimination", " elim")
    return f"{base} / {x['outcome']}"


def cmd_report(a) -> None:
    """Build the readable book (positions, money in, unrealized + realized P&L), print it,
    and write paper/book.md (the file to open and watch)."""
    p = _load()
    opens = [x for x in p if x["status"] == "open"]
    closed = [x for x in p if x["status"] == "closed"]
    money_in = sum(x["stake_usd"] for x in p)
    L = [f"# Paper book — {_now()[:16].replace('T', ' ')}Z",
         "",
         f"**Money in:** ${money_in:.0f}  ·  **Open:** {len(opens)}  ·  **Closed:** {len(closed)}",
         "", "## Open positions", ""]
    uin = uval = 0.0
    if opens:
        L += ["| # | side | market / outcome | in $ | entry | now | value | unrealized |",
              "|--:|:--|:--|--:|--:|--:|--:|--:|"]
        for x in opens:
            lp = live_price(x["venue"], x["market"], x["outcome"], x["side"])
            now = lp if lp is not None else x["entry_price"]
            val = x["shares"] * now
            uin += x["stake_usd"]; uval += val
            mark = "" if lp is not None else " ⚠"
            L.append(f"| {x['id']} | {x['side'].upper()} | {_mkt_label(x)} | "
                     f"{x['stake_usd']:.0f} | {x['entry_price']:.3f} | {now:.3f}{mark} | "
                     f"{val:.1f} | {val - x['stake_usd']:+.1f} |")
    else:
        L.append("_none yet_")
    unreal = uval - uin
    L += ["", f"**Unrealized P&L:** {unreal:+.1f}  (on ${uin:.0f} open)", "",
          "## Closed positions", ""]
    realized = 0.0
    if closed:
        L += ["| # | side | market / outcome | entry → exit | realized (net) |",
              "|--:|:--|:--|:--|--:|"]
        for x in closed:
            r = x.get("realized_pnl_net", x.get("realized_pnl", 0)) or 0
            realized += r
            L.append(f"| {x['id']} | {x['side'].upper()} | {_mkt_label(x)} | "
                     f"{x['entry_price']:.3f} → {x['exit_price']:.3f} | {r:+.1f} |")
    else:
        L.append("_none yet_")
    L += ["", f"**Realized P&L (net of {COST_BPS}bps):** {realized:+.1f}", "",
          "## Total", "",
          f"money in **${money_in:.0f}**  ·  unrealized **{unreal:+.1f}**  ·  "
          f"realized **{realized:+.1f}**  ·  **combined {realized + unreal:+.1f}**", ""]
    txt = "\n".join(L)
    with open(BOOK, "w", encoding="utf-8") as f:
        f.write(txt)
    print(txt)
    print(f"\n(written to {os.path.relpath(BOOK, os.path.dirname(DIR))})")


def main() -> int:
    ap = argparse.ArgumentParser(description="xResidual paper-trading tracker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("open"); o.set_defaults(fn=cmd_open)
    o.add_argument("--venue", default="polymarket")
    o.add_argument("--market", required=True, help="event slug, e.g. world-cup-brazil-stage-of-elimination")
    o.add_argument("--outcome", required=True, help="leg, e.g. 'Champion' or a team name")
    o.add_argument("--side", default="yes", choices=["yes", "no"])
    o.add_argument("--price", type=float, required=True, help="your fill price (0-1)")
    o.add_argument("--stake", type=float, required=True, help="dollars in")
    o.add_argument("--note", default="")
    m = sub.add_parser("mark"); m.set_defaults(fn=cmd_mark)
    c = sub.add_parser("close"); c.set_defaults(fn=cmd_close)
    c.add_argument("id", type=int)
    c.add_argument("--price", type=float, default=None)
    r = sub.add_parser("report"); r.set_defaults(fn=cmd_report)
    a = ap.parse_args()
    a.fn(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
