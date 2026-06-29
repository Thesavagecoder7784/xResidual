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
import inspect
import json
import os
import random
import ssl
import sys
import time
import unicodedata

import certifi
import requests
import websockets

import envtools
import venues

# Bridge venue spellings to one canonical key for cross-venue outcome pairing (see _norm).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xresidual import wc2026_teams as _wt  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
KALSHI_WS = "wss://api.elections.kalshi.com/trade-api/ws/v2"
POLY_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
# stdlib SSL has no CA bundle on some Python builds; use certifi's (as requests does).
SSL_CTX = ssl.create_default_context(cafile=certifi.where())


def _ws_connect(url, headers, **kw):
    """websockets.connect that works across the v14 header-kwarg rename.

    The per-request header kwarg was `extra_headers` through websockets 13 and was
    renamed `additional_headers` in 14+. On older versions (e.g. 10.x) connect() accepts
    arbitrary kwargs and only fails when create_connection is awaited, so a try/except at
    construction misses it. Detect the supported name by inspecting the signature instead."""
    names = set()
    for obj in (websockets.connect, getattr(websockets.connect, "__init__", None)):
        if obj is None:
            continue
        try:
            names |= set(inspect.signature(obj).parameters)
        except (ValueError, TypeError):
            pass
    key = "additional_headers" if "additional_headers" in names else "extra_headers"
    return websockets.connect(url, **{key: headers}, **kw)


def _ms() -> int:
    return int(time.time() * 1000)


def _now_day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _slug(s: str) -> str:
    """'Mexico vs South Africa' -> 'mexico-vs-south-africa' (filesystem-safe, short)."""
    out = "".join(c.lower() if c.isalnum() else "-" for c in s)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:48] or "capture"


def _capture_name(label: str | None) -> str:
    """A per-capture id: UTC start instant + a label slug. The start stamp makes it
    unique and sortable (lexically latest = latest-started capture), and binding the
    file to the START instant means a match that runs past UTC midnight stays in ONE
    file (no day-rollover split) and two simultaneous matches never share a file (no
    interleaved writes). Sorts after the legacy 'ws-events-YYYY-MM-DD' files."""
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{stamp}-{_slug(label)}" if label else stamp


class Writer:
    """Append-only JSONL with a local-ms timestamp on every event.

    One file PER CAPTURE (named by match + start instant), so concurrent captures of
    simultaneous matches never append to the same file (no torn interleaved lines) and
    a single capture never splits across a UTC-day boundary. Holds the file open
    (cheaper than reopening per event during a goal burst) and flushes every line;
    fsync on control events and at close. Connection control events are logged too, so
    the analyzer can see venue gaps instead of mistaking a disconnect for a quiet
    market."""

    def __init__(self, data_dir: str, name: str | None = None):
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, f"ws-events-{name or _now_day()}.jsonl")
        self._f = open(self.path, "a", encoding="utf-8")
        self.n = 0

    def write(self, venue: str, etype: str, market: str, data) -> None:
        rec = {"t": _ms(), "venue": venue, "type": etype, "market": market, "data": data}
        self._f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        self._f.flush()
        self.n += 1

    def meta(self, venue: str, event: str, info: str = "") -> None:
        """Log a capture-control event (connected | disconnected | stale) and fsync, so
        a venue gap is visible in the tape rather than looking like a silent market."""
        self.write(venue, f"_capture_{event}", "_meta", {"info": info})
        os.fsync(self._f.fileno())

    def close(self) -> None:
        try:
            self._f.flush()
            os.fsync(self._f.fileno())
            self._f.close()
        except Exception:
            pass


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


async def kalshi_stream(tickers: list[str], env: dict, w: Writer, deadline: float,
                        stale_s: float = 120.0) -> None:
    # stale_s is a DATA-silence timeout (no market messages), not a liveness check — the WS
    # ping/pong (ping_interval=10, ping_timeout=20) already catches a truly dead connection in
    # ~30s. 45s was too twitchy: a legitimately quiet book (pre-KO, a lull, post-match) tripped
    # it and force-reconnected every minute (21 needless reconnects after the opener ended).
    sub = {"id": 1, "cmd": "subscribe",
           "params": {"channels": ["ticker", "trade", "orderbook_delta"],
                      "market_tickers": tickers}}
    async with _ws_connect(KALSHI_WS, _kalshi_ws_headers(env),
                           ssl=SSL_CTX, ping_interval=10, ping_timeout=20,
                           max_size=None, max_queue=None) as ws:
        await ws.send(json.dumps(sub))
        w.meta("kalshi", "connected", f"{len(tickers)} tickers")
        _log(f"kalshi subscribed: {len(tickers)} tickers")
        last = time.time()
        last_seq: int | None = None            # Kalshi `seq` is a PER-CONNECTION message
                                               # counter (drop detection across the whole
                                               # stream), NOT per market. Track it globally;
                                               # starts None on each (re)connect.
        try:
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    if time.time() - last > stale_s:
                        raise RuntimeError(f"no data for {stale_s:.0f}s (stale)")
                    continue
                last = time.time()
                try:
                    m = json.loads(raw)
                except ValueError:
                    continue
                msg = m.get("msg", {})
                typ = m.get("type", "?")
                market = msg.get("market_ticker") or msg.get("ticker") or "?"
                # Kalshi stamps every message on a connection with a monotonic `seq`; a hole
                # means the server dropped a message to us. It is PER CONNECTION, not per
                # market, so check it globally (a per-market check counts normal cross-market
                # interleaving as fake gaps — that was inflating the "gap rate" to ~2/3 with 3
                # markets). The raw seq is now preserved in the tape so true loss is measurable
                # offline regardless of this live flag.
                seq = m.get("seq")
                if seq is not None:
                    if last_seq is not None and seq != last_seq + 1:
                        w.meta("kalshi", "gap", f"conn seq {last_seq}->{seq}")
                    last_seq = seq
                    if isinstance(msg, dict):
                        msg = {**msg, "_seq": seq}
                w.write("kalshi", typ, market, msg)
        finally:
            w.meta("kalshi", "disconnected")


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


async def polymarket_stream(token_ids: list[str], w: Writer, deadline: float,
                            stale_s: float = 120.0) -> None:
    async with websockets.connect(POLY_WS, ssl=SSL_CTX, ping_interval=None,
                                   max_size=None, max_queue=None) as ws:
        await ws.send(json.dumps({"assets_ids": token_ids, "type": "market"}))
        w.meta("polymarket", "connected", f"{len(token_ids)} tokens")
        _log(f"polymarket subscribed: {len(token_ids)} tokens")
        pinger = asyncio.ensure_future(_poly_pinger(ws, deadline))
        last = time.time()
        try:
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    if time.time() - last > stale_s:
                        raise RuntimeError(f"no data for {stale_s:.0f}s (stale)")
                    continue
                last = time.time()
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
            w.meta("polymarket", "disconnected")


# --------------------------------------------------------------------------- #
# resilient supervisor
# --------------------------------------------------------------------------- #
async def supervise(name: str, factory, deadline: float) -> None:
    backoff = 1.0
    while time.time() < deadline:
        started = time.time()
        try:
            await factory()
            backoff = 1.0
        except Exception as e:
            ran = time.time() - started
            if ran > 60:                       # a stable run dropped; don't penalise it
                backoff = 1.0
            base = min(backoff, 30.0)
            wait = base / 2 + random.uniform(0, base / 2)   # equal jitter: no reconnect storms
            _log(f"{name} dropped after {ran:.0f}s ({type(e).__name__}: {str(e)[:80]}) "
                 f"— reconnecting in {wait:.1f}s")
            await asyncio.sleep(wait)
            backoff *= 2


# Venue / FIFA-name variants our canonical bridge (elo_name∘canonical) does NOT already collapse.
# Keyed by the canonical alnum norm; values are the extra alnum spellings the venues use. Without
# these, "Mexico vs. Korea Republic" never matches our "South Korea" and the match is lost entirely.
_TEAM_ALIASES = {
    "southkorea": ["korearepublic", "korea"],
    "iran": ["iriran"],
    "ivorycoast": ["cotedivoire"],
    "capeverde": ["caboverde"],
}
_ALIAS_TO_CANON = {alt: canon for canon, alts in _TEAM_ALIASES.items() for alt in alts}


def _alnum(s: str) -> str:
    """Accent-stripped, lowercased, alphanumerics only (so 'Côte d'Ivoire' -> 'cotedivoire')."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return "".join(c for c in s if c.isalnum())


def _norm(name: str) -> str:
    """Loose team-name match across venue spellings. Bridge through the WC name map
    (elo_name∘canonical) so USA/United States, Bosnia variants, Czechia/Czech Republic,
    Curacao/Curaçao, Turkiye/Turkey collapse to one key, then fold in the FIFA-name aliases above
    (Korea Republic, IR Iran, Côte d'Ivoire, Cabo Verde) that the bridge misses; non-team strings
    (Tie, full questions) pass through unchanged."""
    base = _alnum(_wt.elo_name(_wt.canonical(name)))
    return _ALIAS_TO_CANON.get(base, base)


def _spellings(name: str) -> set:
    """Every alnum spelling a venue might use for `name` (canonical + its FIFA aliases) — for
    substring-matching event titles, which carry the venue's spelling, not ours."""
    canon = _norm(name)
    return {canon, _alnum(name), *(a for a, c in _ALIAS_TO_CANON.items() if c == canon)}


def _title_has(title_alnum: str, name: str) -> bool:
    return any(sp and sp in title_alnum for sp in _spellings(name))


def _ko_outcome(norm_name: str) -> str:
    """Knockout match-winner outcomes are titled 'Reg Time <team>' / 'Reg Time Tie' (a knockout
    can go to ET/penalties, so the moneyline is on the REGULATION result), normalizing to
    'regtime<team>' — whereas group games use the bare team name. Strip the 'regtime' prefix so
    knockout outcomes key by the bare team name, exactly like group games and like Polymarket's
    groupItemTitle. Without this, KXWCGAME knockout games matched 0 outcomes and captured
    Polymarket-only (South Africa-Canada, the first R32 game, Jun 28 2026)."""
    return norm_name[len("regtime"):] if norm_name.startswith("regtime") else norm_name


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
        by_prefix.setdefault(pre, {})[_ko_outcome(_norm(m.get("yes_sub_title", "")))] = m["ticker"]
    kalshi, k_by_name = [], {}
    for pre, names in by_prefix.items():
        if a in names and b in names:
            kalshi = sorted(names.values())  # the 3 outcome tickers (incl. Tie)
            k_by_name = names                 # normalized outcome name -> ticker
            break
    # --- Polymarket (best-effort; the per-match moneyline lists close to kickoff) ---
    poly, p_by_name = [], {}
    try:
        # search by team names only (no "World Cup" suffix) so warm-up FRIENDLIES are
        # found too; the title filter below keeps the right event. The suffix used to make
        # discovery miss friendlies like Argentina v Iceland that aren't titled "World Cup".
        # Search the plain names PLUS each team's FIFA aliases, so events titled with the venue's
        # spelling (e.g. "Mexico vs. Korea Republic") still surface; dedupe by slug.
        queries = [f"{team_a} {team_b}"]
        queries += [f"{alt} {team_b}" for alt in _TEAM_ALIASES.get(a, [])]
        queries += [f"{team_a} {alt}" for alt in _TEAM_ALIASES.get(b, [])]
        events, seen = [], set()
        for q in queries:
            try:
                for e in requests.get("https://gamma-api.polymarket.com/public-search",
                                      params={"q": q}, timeout=15).json().get("events", []):
                    sl = e.get("slug")
                    if sl and sl not in seen:
                        seen.add(sl); events.append(e)
            except Exception:
                continue
        for e in events:
            title = _alnum(e.get("title", ""))
            if not (_title_has(title, team_a) and _title_has(title, team_b)):
                continue
            ev = requests.get("https://gamma-api.polymarket.com/events",
                              params={"slug": e.get("slug")}, timeout=15).json()
            ev = ev[0] if isinstance(ev, list) and ev else ev
            for mm in (ev.get("markets", []) if isinstance(ev, dict) else []):
                # Keep ONLY the match-winner outcomes — their groupItemTitle is the team name
                # ('Brazil'/'Haiti'), keyed like Kalshi's yes_sub_title, so they pair by team.
                # This skips the prop / '-more-markets' events (spreads, totals, BTTS) whose
                # markets never key by team and so produced 0 pairs — which silently zeroed
                # USA-Paraguay (it matched a 24-market prop event first, non-deterministically).
                if _norm(mm.get("groupItemTitle") or "") in (a, b):
                    toks = venues._maybe_json_list(mm.get("clobTokenIds"))
                    if toks:
                        p_by_name[_norm(mm["groupItemTitle"])] = toks[0]
            if p_by_name:            # found the moneyline event's team outcomes — stop scanning
                break
        poly = list(p_by_name.values())
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


def _write_pairs(pairs: list[dict], name: str) -> None:
    """Record the captured cross-venue pairs so the analyzer (scripts/build_leadlag.py)
    self-configures: no hand-typed tickers, no hand-typed goal time. The sidecar shares
    the capture id with its ws-events file, so loaders pair them unambiguously."""
    if not pairs:
        return
    path = os.path.join(DATA_DIR, f"ws-pairs-{name}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps({"t": _ms(), **p}, separators=(",", ":")) + "\n")
    _log(f"recorded {len(pairs)} cross-venue pair(s) -> {os.path.basename(path)}")


# Re-discover markets this often (seconds) until both venues are streaming — Polymarket lists
# per-match markets close to / after kickoff (and Kalshi occasionally lags), so a one-shot
# subscribe at start used to lose the whole game on the late venue. Env-overridable for tuning.
REPOLL_SECONDS = int(os.environ.get("WSCAP_REPOLL_S", "90"))

# Adaptive early-stop: end the capture once the match's market has gone silent, instead of
# blindly running the full --seconds window (which over-ran every group game by ~40 min of dead
# post-match recording — wasting tape and keeping the memory guard up so the micro pools couldn't
# refresh). Fires ONLY when BOTH conditions hold, so it can never trip mid-match or at half-time:
#   - at least IDLE_STOP_AFTER_S elapsed (past any plausible full-time), AND
#   - no new events for IDLE_STOP_SILENCE_S (a live match always emits events; only a settled,
#     post-match market goes fully silent).
# Adapts to length automatically: a group game stops near full-time, a knockout only after ET/pens.
# The --seconds value stays the hard backstop. Env-overridable; set IDLE_STOP_AFTER_S=0 to disable.
IDLE_STOP_AFTER_S = int(os.environ.get("WSCAP_IDLE_AFTER_S", "6000"))     # 100 min elapsed floor
IDLE_STOP_SILENCE_S = int(os.environ.get("WSCAP_IDLE_SILENCE_S", "900"))  # 15 min of no events
IDLE_STOP_POLL_S = int(os.environ.get("WSCAP_IDLE_POLL_S", "30"))         # how often to check


async def idle_watchdog(w, deadline: float, stop: "asyncio.Event") -> None:
    """Set `stop` when the market has been silent past full-time (see constants above)."""
    if IDLE_STOP_AFTER_S <= 0:
        return
    start = time.time()
    last_n, last_change = w.n, time.time()
    while time.time() < deadline and not stop.is_set():
        await asyncio.sleep(IDLE_STOP_POLL_S)
        if w.n != last_n:
            last_n, last_change = w.n, time.time()
            continue
        if (time.time() - start) > IDLE_STOP_AFTER_S and (time.time() - last_change) > IDLE_STOP_SILENCE_S:
            _log(f"idle-stop: no events for {IDLE_STOP_SILENCE_S/60:.0f} min past full-time "
                 f"({(time.time()-start)/60:.0f} min elapsed) — ending capture early")
            stop.set()
            return


async def main_async(args) -> int:
    env = envtools.load_env()
    pairs = []
    label = None
    match_teams = None                       # set for --match -> enables the re-poll loop
    if args.match:
        parts = [p.strip() for p in args.match.replace(" vs ", ",").split(",") if p.strip()]
        if len(parts) != 2:
            _log("--match expects 'Team A vs Team B'")
            return 1
        match_teams = (parts[0], parts[1])
        label = f"{parts[0]} vs {parts[1]}"
        kalshi, poly, pairs = discover_match_markets(env, parts[0], parts[1])
        _log(f"match '{parts[0]} vs {parts[1]}' — kalshi tickers: {kalshi or 'NONE'}")
        _log(f"  polymarket tokens: {len(poly)}" + ("" if poly else " (per-match market not listed yet — will re-poll)"))
        _log(f"  cross-venue pairs: {len(pairs)}")
    elif args.outright_test:
        kalshi, poly, pairs = discover_outright_markets(env)
        label = "outright"
        _log(f"outright test — kalshi={kalshi} polymarket={len(poly)} tokens · {len(pairs)} pairs")
    else:
        kalshi = [t for t in (args.kalshi or "").split(",") if t]
        poly = [t for t in (args.polymarket or "").split(",") if t]
        label = "manual"
    name = _capture_name(label)
    _write_pairs(pairs, name)
    w = Writer(DATA_DIR, name)
    deadline = time.time() + args.seconds

    # Launch each venue's stream the moment its market is available — not just once at start.
    # start_* are idempotent (a venue is started at most once); the re-poll task below brings up
    # a late-listing venue and records its cross-venue pairs mid-capture.
    active: dict[str, asyncio.Future] = {}

    def start_kalshi(tickers) -> bool:
        if "kalshi" in active or not tickers or "KALSHI_ACCESS_KEY" not in env:
            return False
        active["kalshi"] = asyncio.ensure_future(
            supervise("kalshi", lambda: kalshi_stream(tickers, env, w, deadline), deadline))
        return True

    def start_poly(tokens) -> bool:
        if "polymarket" in active or not tokens:
            return False
        active["polymarket"] = asyncio.ensure_future(
            supervise("polymarket", lambda: polymarket_stream(tokens, w, deadline), deadline))
        return True

    start_kalshi(kalshi)
    start_poly(poly)

    async def repoll() -> None:
        """Re-discover the match markets until both venues stream and a pair exists (or the
        capture ends), subscribing late-listed markets and appending new cross-venue pairs.
        Discovery runs in a thread so its blocking HTTP calls don't stall the live streams."""
        loop = asyncio.get_event_loop()
        seen = {(p["kalshi"], p["poly"]) for p in pairs}
        while time.time() < deadline:
            if "kalshi" in active and "polymarket" in active and seen:
                _log("re-poll: both venues streaming and paired — discovery done")
                return
            await asyncio.sleep(REPOLL_SECONDS)
            try:
                k2, p2, pr2 = await loop.run_in_executor(
                    None, discover_match_markets, env, match_teams[0], match_teams[1])
            except Exception as e:
                _log(f"re-poll discovery error ({type(e).__name__}); retrying")
                continue
            if start_kalshi(k2):
                _log(f"re-poll: late Kalshi listing ({len(k2)} tickers) — subscribed")
            if start_poly(p2):
                _log(f"re-poll: late Polymarket listing ({len(p2)} tokens) — subscribed")
            fresh = [p for p in pr2 if (p["kalshi"], p["poly"]) not in seen]
            if fresh:
                _write_pairs(fresh, name)
                seen |= {(p["kalshi"], p["poly"]) for p in fresh}
                _log(f"re-poll: {len(fresh)} new cross-venue pair(s) recorded")

    repoll_task = asyncio.ensure_future(repoll()) if match_teams else None

    if not active and repoll_task is None:
        _log("nothing to stream — pass --kalshi/--polymarket or --outright-test")
        w.close()
        return 1
    if not active:
        _log("no markets listed at start — re-polling until they appear")

    stop = asyncio.Event()
    watchdog = asyncio.ensure_future(idle_watchdog(w, deadline, stop))
    try:
        if repoll_task is not None:
            await repoll_task                # runs concurrently with the streams; returns at both-up or deadline
        if active:
            # wait for the streams to finish at the hard deadline, OR the idle-watchdog to fire
            # post-match — whichever comes first.
            stop_waiter = asyncio.ensure_future(stop.wait())
            await asyncio.wait([*active.values(), stop_waiter], return_when=asyncio.FIRST_COMPLETED)
            stop_waiter.cancel()
            if stop.is_set():                       # idle-stop fired: cancel the still-running streams
                for t in active.values():
                    if not t.done():
                        t.cancel()
            # drain ALL stream tasks (whether they finished at the deadline or were just cancelled)
            # before the writer is closed in `finally`, so nothing writes to a closed tape.
            await asyncio.gather(*active.values(), return_exceptions=True)
    finally:
        watchdog.cancel()
        w.close()
    _log(f"done — {w.n} events written to {os.path.relpath(w.path)}")
    if args.analyze:
        import subprocess
        import sys as _sys
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _log("running lead-lag shock detection on the capture ...")
        subprocess.run([_sys.executable, os.path.join("scripts", "build_leadlag.py")], cwd=root)
        _log("running goal-overreaction backtest on the capture ...")
        subprocess.run([_sys.executable, os.path.join("scripts", "overreaction_run.py")], cwd=root)
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
