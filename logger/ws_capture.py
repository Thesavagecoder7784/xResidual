#!/usr/bin/env python3
"""Real-time websocket capture for cross-venue lead-lag.

Opens persistent websockets to Kalshi and Polymarket and stamps every event with a
local millisecond clock. The local clock matters: lead-lag is measured against one
reference, so server-clock skew between the venues can't fake a lead. Events append
to data/ws-events-YYYY-MM-DD.jsonl.

Run around a marquee match (markets exist at match time):

    python ws_capture.py --kalshi TICKER1,TICKER2 --polymarket TOKENID1,TOKENID2 --seconds 7200
    python ws_capture.py --outright-test --seconds 30   # validate plumbing on live winner markets

Resilient: auto-reconnect with backoff, heartbeat, append-only. Runs until --seconds
elapses (or Ctrl-C).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import ssl
import time

import certifi
import requests
import websockets

import envtools
import venues

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
KALSHI_WS = "wss://api.elections.kalshi.com/trade-api/ws/v2"
POLY_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
# stdlib SSL has no CA bundle on some Python builds; use certifi's (as requests does).
SSL_CTX = ssl.create_default_context(cafile=certifi.where())


def _ms() -> int:
    return int(time.time() * 1000)


def _now_day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


class Writer:
    """Append-only JSONL with a local-ms timestamp on every event."""

    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, f"ws-events-{_now_day()}.jsonl")
        self.n = 0

    def write(self, venue: str, etype: str, market: str, data) -> None:
        rec = {"t": _ms(), "venue": venue, "type": etype, "market": market, "data": data}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")
            f.flush()
        self.n += 1


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------- #
# Kalshi (authenticated): orderbook_delta + ticker + trade
# --------------------------------------------------------------------------- #
def _kalshi_ws_headers(env: dict) -> dict:
    pk = venues._load_kalshi_private_key(env)
    ts = str(_ms())
    sig = venues._kalshi_sign(pk, ts, "GET", "/trade-api/ws/v2")
    return {"KALSHI-ACCESS-KEY": env["KALSHI_ACCESS_KEY"],
            "KALSHI-ACCESS-SIGNATURE": sig, "KALSHI-ACCESS-TIMESTAMP": ts}


async def kalshi_stream(tickers: list[str], env: dict, w: Writer, deadline: float) -> None:
    sub = {"id": 1, "cmd": "subscribe",
           "params": {"channels": ["ticker", "trade", "orderbook_delta"],
                      "market_tickers": tickers}}
    async with websockets.connect(KALSHI_WS, extra_headers=_kalshi_ws_headers(env),
                                  ssl=SSL_CTX, ping_interval=10, ping_timeout=20, max_size=None) as ws:
        await ws.send(json.dumps(sub))
        _log(f"kalshi subscribed: {len(tickers)} tickers")
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                m = json.loads(raw)
            except ValueError:
                continue
            msg = m.get("msg", {})
            market = msg.get("market_ticker") or msg.get("ticker") or "?"
            w.write("kalshi", m.get("type", "?"), market, msg)


# --------------------------------------------------------------------------- #
# Polymarket (public): book + price_change + last_trade_price
# --------------------------------------------------------------------------- #
async def _poly_pinger(ws, deadline: float) -> None:
    while time.time() < deadline:
        try:
            await ws.send("PING")
        except Exception:
            return
        await asyncio.sleep(10)


async def polymarket_stream(token_ids: list[str], w: Writer, deadline: float) -> None:
    async with websockets.connect(POLY_WS, ssl=SSL_CTX, ping_interval=None, max_size=None) as ws:
        await ws.send(json.dumps({"assets_ids": token_ids, "type": "market"}))
        _log(f"polymarket subscribed: {len(token_ids)} tokens")
        pinger = asyncio.ensure_future(_poly_pinger(ws, deadline))
        try:
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                if raw == "PONG":
                    continue
                try:
                    events = json.loads(raw)
                except ValueError:
                    continue
                for ev in (events if isinstance(events, list) else [events]):
                    market = ev.get("asset_id") or ev.get("market") or "?"
                    w.write("polymarket", ev.get("event_type", "?"), market, ev)
        finally:
            pinger.cancel()


# --------------------------------------------------------------------------- #
# resilient supervisor
# --------------------------------------------------------------------------- #
async def supervise(name: str, factory, deadline: float) -> None:
    backoff = 1.0
    while time.time() < deadline:
        try:
            await factory()
            backoff = 1.0
        except Exception as e:
            _log(f"{name} dropped ({type(e).__name__}: {str(e)[:80]}) — reconnecting")
            await asyncio.sleep(min(backoff, 30.0))
            backoff *= 2


def _norm(name: str) -> str:
    """Loose team-name match across venue spellings (Turkiye/Turkey, Congo DR, etc.)."""
    return "".join(c for c in name.lower() if c.isalnum())


def discover_match_markets(env: dict, team_a: str, team_b: str):
    """Resolve the Kalshi tickers and Polymarket token ids for one match.

    Kalshi: the KXWCGAME series; a match's 3 outcome markets share a ticker prefix
    (e.g. KXWCGAME-26JUN24CZEMEX). Polymarket: per-match markets appear close to
    kickoff, so this returns [] (with a note) until then."""
    a, b = _norm(team_a), _norm(team_b)
    # --- Kalshi ---
    mk = venues._kalshi_get(env, "/trade-api/v2/markets",
                            params={"series_ticker": "KXWCGAME", "limit": 1000}).get("markets", [])
    by_prefix: dict[str, dict] = {}
    for m in mk:
        pre = m["ticker"].rsplit("-", 1)[0]
        by_prefix.setdefault(pre, {})[_norm(m.get("yes_sub_title", ""))] = m["ticker"]
    kalshi, k_by_name = [], {}
    for pre, names in by_prefix.items():
        if a in names and b in names:
            kalshi = sorted(names.values())  # the 3 outcome tickers (incl. Tie)
            k_by_name = names                 # normalized outcome name -> ticker
            break
    # --- Polymarket (best-effort; may not exist yet) ---
    poly, p_by_name = [], {}
    try:
        s = requests.get("https://gamma-api.polymarket.com/public-search",
                         params={"q": f"{team_a} {team_b} World Cup"}, timeout=15).json()
        for e in s.get("events", []):
            title = _norm(e.get("title", ""))
            if a in title and b in title:
                ev = requests.get("https://gamma-api.polymarket.com/events",
                                  params={"slug": e.get("slug")}, timeout=15).json()
                ev = ev[0] if isinstance(ev, list) and ev else ev
                for mm in (ev.get("markets", []) if isinstance(ev, dict) else []):
                    toks = venues._maybe_json_list(mm.get("clobTokenIds"))
                    if toks:
                        poly.append(toks[0])
                        p_by_name[_norm(mm.get("groupItemTitle") or mm.get("question", ""))] = toks[0]
                break
    except Exception:
        pass
    # pair the same outcome across venues by normalized name (team A, team B)
    pairs = _pairs_by_name(k_by_name, p_by_name, {a: team_a, b: team_b})
    return kalshi, poly, pairs


def _pairs_by_name(k_by_name: dict, p_by_name: dict, label_by_norm: dict) -> list[dict]:
    """Align the same outcome across venues by normalized name -> [{label, kalshi, poly}].
    Only outcomes present on BOTH venues become a cross-venue pair."""
    pairs = []
    for norm in set(k_by_name) & set(p_by_name):
        pairs.append({"label": label_by_norm.get(norm, norm),
                      "kalshi": k_by_name[norm], "poly": p_by_name[norm]})
    return pairs


def discover_outright_markets(env: dict, teams=("Spain", "France", "England")):
    """For --outright-test: resolve Kalshi tickers + Polymarket YES token ids for a
    few top teams from the live winner field, aligned into cross-venue pairs."""
    mk = venues._kalshi_get(env, "/trade-api/v2/markets",
                            params={"series_ticker": "KXMENWORLDCUP", "limit": 1000}).get("markets", [])
    k_by_name = {_norm(m.get("yes_sub_title", "")): m["ticker"]
                 for m in mk if m.get("yes_sub_title") in teams}
    ev = requests.get("https://gamma-api.polymarket.com/events",
                      params={"slug": "world-cup-winner"}, timeout=15).json()
    ev = ev[0] if isinstance(ev, list) else ev
    p_by_name = {}
    for m in ev.get("markets", []):
        if m.get("groupItemTitle") in teams:
            t = venues._maybe_json_list(m.get("clobTokenIds"))
            if t:
                p_by_name[_norm(m["groupItemTitle"])] = t[0]
    pairs = _pairs_by_name(k_by_name, p_by_name, {_norm(t): t for t in teams})
    return list(k_by_name.values()), list(p_by_name.values()), pairs


def _write_pairs(pairs: list[dict]) -> None:
    """Record the captured cross-venue pairs so the analyzer (scripts/build_leadlag.py)
    self-configures: no hand-typed tickers, no hand-typed goal time."""
    if not pairs:
        return
    path = os.path.join(DATA_DIR, f"ws-pairs-{_now_day()}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps({"t": _ms(), **p}, separators=(",", ":")) + "\n")
    _log(f"recorded {len(pairs)} cross-venue pair(s) -> {os.path.basename(path)}")


async def main_async(args) -> int:
    env = envtools.load_env()
    pairs = []
    if args.match:
        parts = [p.strip() for p in args.match.replace(" vs ", ",").split(",") if p.strip()]
        if len(parts) != 2:
            _log("--match expects 'Team A vs Team B'")
            return 1
        kalshi, poly, pairs = discover_match_markets(env, parts[0], parts[1])
        _log(f"match '{parts[0]} vs {parts[1]}' — kalshi tickers: {kalshi or 'NONE'}")
        _log(f"  polymarket tokens: {len(poly)}" + ("" if poly else " (per-match market not listed yet — Kalshi-only for now)"))
        _log(f"  cross-venue pairs: {len(pairs)}")
    elif args.outright_test:
        kalshi, poly, pairs = discover_outright_markets(env)
        _log(f"outright test — kalshi={kalshi} polymarket={len(poly)} tokens · {len(pairs)} pairs")
    else:
        kalshi = [t for t in (args.kalshi or "").split(",") if t]
        poly = [t for t in (args.polymarket or "").split(",") if t]
    _write_pairs(pairs)
    w = Writer(DATA_DIR)
    deadline = time.time() + args.seconds
    tasks = []
    if kalshi and "KALSHI_ACCESS_KEY" in env:
        tasks.append(supervise("kalshi", lambda: kalshi_stream(kalshi, env, w, deadline), deadline))
    if poly:
        tasks.append(supervise("polymarket", lambda: polymarket_stream(poly, w, deadline), deadline))
    if not tasks:
        _log("nothing to stream — pass --kalshi/--polymarket or --outright-test")
        return 1
    await asyncio.gather(*tasks)
    _log(f"done — {w.n} events written to {os.path.relpath(w.path)}")
    if args.analyze:
        _log("running lead-lag shock detection on the capture ...")
        import subprocess
        import sys as _sys
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        subprocess.run([_sys.executable, os.path.join("scripts", "build_leadlag.py")], cwd=root)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="xResidual websocket lead-lag capturer")
    ap.add_argument("--kalshi", help="comma-separated Kalshi market tickers")
    ap.add_argument("--polymarket", help="comma-separated Polymarket token ids")
    ap.add_argument("--match", help="auto-discover a match's markets, e.g. 'Mexico vs South Africa'")
    ap.add_argument("--outright-test", action="store_true",
                    help="stream a few live winner markets to validate plumbing")
    ap.add_argument("--seconds", type=int, default=7200, help="capture duration")
    ap.add_argument("--analyze", action="store_true",
                    help="after capture, auto-detect price shocks and run lead-lag")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
