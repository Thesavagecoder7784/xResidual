"""Venue adapters.

Each adapter reads its own section of the config plus the loaded env, and returns
Quote objects for the current instant. Adapters MUST NOT raise on network/parse/auth
errors: a single bad fetch must never kill the logging loop. Catch, record the
failure as an `__error__` quote, and move on. A gap in one venue's series is
recoverable; a crashed logger losing every venue is not.

Venues:
  - polymarket : public Gamma API, no auth.
  - kalshi     : RSA-PSS signed requests (KALSHI_ACCESS_KEY + private key PEM).
  - oddsapi    : The Odds API, multi-bookmaker h2h odds (ODDSAPI_KEY).

Prices are stored in PROBABILITY UNITS (0..1). Each adapter converts:
  - Polymarket Gamma price is already ~probability.
  - Kalshi cents (0..100) -> /100.
  - Odds API decimal odds -> 1/odds, renormalized per book to strip the overround.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Optional

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

import envtools
from storage import Quote, now_iso

HTTP_TIMEOUT = 10  # seconds; a slow venue must not stall the whole pass


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _as_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _maybe_json_list(v) -> list:
    """Gamma encodes arrays as JSON strings; tolerate both string and list."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    try:
        parsed = json.loads(v)
        return parsed if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


def _error_quote(venue: str, market_id: str, label: str, err: Exception) -> Quote:
    """A recorded miss. Keeping these in the series makes coverage gaps auditable."""
    return Quote(
        ts_utc=now_iso(),
        venue=venue,
        market_id=str(market_id),
        market_label=label,
        outcome="__error__",
        extra={"error": f"{type(err).__name__}: {err}"},
    )


# --------------------------------------------------------------------------- #
# Polymarket: public Gamma API, no auth.
# config["polymarket"] entries are either:
#   {"id": "<gamma market id>", "label": "..."}          a single market, or
#   {"event_slug": "world-cup-winner", "label": "..."}   a whole event (the winner
#       field): ONE call returns every child market, tagged market_type="winner".
# Verify the response shape before June 11; Gamma's schema has drifted.
# --------------------------------------------------------------------------- #
def fetch_polymarket(config: dict, env: dict) -> list[Quote]:
    specs = config.get("polymarket") or []
    out: list[Quote] = []
    for spec in specs:
        try:
            if "event_slug" in spec:
                out.extend(_poly_event(spec))
            else:
                out.extend(_poly_single(spec))
        except Exception as e:
            who = spec.get("event_slug") or spec.get("id", "?")
            out.append(_error_quote("polymarket", str(who), spec.get("label", str(who)), e))
    return out


def _poly_single(spec: dict) -> list[Quote]:
    mid_id, label = spec["id"], spec.get("label", spec["id"])
    r = requests.get(f"https://gamma-api.polymarket.com/markets/{mid_id}", timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    outcomes = _maybe_json_list(data.get("outcomes"))
    prices = _maybe_json_list(data.get("outcomePrices"))
    ts = now_iso()
    return [Quote(ts_utc=ts, venue="polymarket", market_id=str(mid_id), market_label=label,
                  outcome=str(name), last=_as_float(price), mid=_as_float(price),
                  volume=_as_float(data.get("volume")), liquidity=_as_float(data.get("liquidity")))
            for name, price in zip(outcomes, prices)]


def _poly_event(spec: dict) -> list[Quote]:
    """A whole event: one /events?slug= call -> one Quote per team (the 'Yes' price is
    that team's implied probability for the event). market_type defaults to 'winner' for
    back-compat; pass it in the spec to tag other markets (advance, reach_round, ...)."""
    slug, label = spec["event_slug"], spec.get("label", spec["event_slug"])
    mtype = spec.get("market_type", "winner")
    r = requests.get("https://gamma-api.polymarket.com/events",
                     params={"slug": slug}, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    ev = r.json()
    ev = ev[0] if isinstance(ev, list) and ev else ev
    ts = now_iso()
    out: list[Quote] = []
    for m in (ev.get("markets", []) if isinstance(ev, dict) else []):
        team = m.get("groupItemTitle") or m.get("question", "")
        outcomes = _maybe_json_list(m.get("outcomes"))
        prices = _maybe_json_list(m.get("outcomePrices"))
        yes = next((_as_float(p) for o, p in zip(outcomes, prices) if str(o).lower() == "yes"), None)
        out.append(Quote(
            ts_utc=ts, venue="polymarket", market_id=str(m.get("id")), market_label=label,
            outcome=str(team), mid=yes, last=_as_float(m.get("lastTradePrice")),
            bid=_as_float(m.get("bestBid")), ask=_as_float(m.get("bestAsk")),
            volume=_as_float(m.get("volume")), liquidity=_as_float(m.get("liquidity")),
            extra={"market_type": mtype, "slug": m.get("slug")},
        ))
    return out


# --------------------------------------------------------------------------- #
# Kalshi: RSA-PSS signed requests.
# Auth per https://trading-api.readme.io/reference/api-keys :
#   message = timestamp_ms + METHOD + path  (path has no query string)
#   signature = base64( RSA-PSS-SHA256(message), salt_length = digest length )
#   headers: KALSHI-ACCESS-KEY / KALSHI-ACCESS-SIGNATURE / KALSHI-ACCESS-TIMESTAMP
# config["kalshi"]: [{"ticker": "<market ticker>", "label": "..."}]
# Base host can drift; override with KALSHI_API_BASE if needed.
# --------------------------------------------------------------------------- #
_KALSHI_PATH_PREFIX = "/trade-api/v2"
_kalshi_key_cache: dict = {}


def _load_kalshi_private_key(env: dict):
    pem_path = envtools.resolve_path(env["KALSHI_PRIVATE_KEY_PEM_PATH"])
    if pem_path not in _kalshi_key_cache:
        with open(pem_path, "rb") as f:
            _kalshi_key_cache[pem_path] = serialization.load_pem_private_key(
                f.read(), password=None
            )
    return _kalshi_key_cache[pem_path]


def _kalshi_sign(private_key, ts_ms: str, method: str, path: str) -> str:
    message = f"{ts_ms}{method}{path}".encode("utf-8")
    sig = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(sig).decode("ascii")


def _kalshi_price(market: dict, base_field: str):
    """Read a Kalshi price in probability units (0..1). Prefer the new
    `<field>_dollars` string (e.g. "0.0100"), fall back to legacy integer cents."""
    v = _as_float(market.get(f"{base_field}_dollars"))
    if v is not None:
        return v
    cents = _as_float(market.get(base_field))
    return cents / 100 if cents is not None else None


def _kalshi_get(env: dict, path: str, params: dict | None = None) -> dict:
    """Signed GET. The signature covers `path` WITHOUT the query string; params are
    sent on the wire only."""
    base = env.get("KALSHI_API_BASE", "https://api.elections.kalshi.com").rstrip("/")
    private_key = _load_kalshi_private_key(env)
    ts_ms = str(int(time.time() * 1000))
    headers = {
        "KALSHI-ACCESS-KEY": env["KALSHI_ACCESS_KEY"],
        "KALSHI-ACCESS-SIGNATURE": _kalshi_sign(private_key, ts_ms, "GET", path),
        "KALSHI-ACCESS-TIMESTAMP": ts_ms,
        "Accept": "application/json",
    }
    r = requests.get(base + path, headers=headers, params=params or {}, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _kalshi_quote_from_market(m: dict, label: str, outcome: str,
                              market_type: str | None = None,
                              ts: str | None = None) -> Quote:
    bid = _kalshi_price(m, "yes_bid")
    ask = _kalshi_price(m, "yes_ask")
    return Quote(
        ts_utc=ts or now_iso(), venue="kalshi", market_id=str(m.get("ticker", "?")),
        market_label=label, outcome=outcome,
        bid=bid, ask=ask,
        mid=(bid + ask) / 2 if bid is not None and ask is not None else None,
        last=_kalshi_price(m, "last_price"),
        volume=_as_float(m.get("volume_fp")) or _as_float(m.get("volume")),
        liquidity=_as_float(m.get("liquidity_dollars")) or _as_float(m.get("liquidity")),
        extra={"market_type": market_type} if market_type else {},
    )


def fetch_kalshi(config: dict, env: dict) -> list[Quote]:
    """config["kalshi"] entries are either:
      {"ticker": "<market ticker>", "label": "..."}            a single market, or
      {"series_ticker": "KXMENWORLDCUP", "label": "..."}       a whole series: ONE
          list call returns every market (the winner field), tagged market_type="winner";
          outcome = each market's team subtitle.
    """
    specs = config.get("kalshi") or []
    out: list[Quote] = []
    if specs and ("KALSHI_ACCESS_KEY" not in env or "KALSHI_PRIVATE_KEY_PEM_PATH" not in env):
        return [_error_quote("kalshi", "*", "kalshi",
                             RuntimeError("KALSHI_ACCESS_KEY / KALSHI_PRIVATE_KEY_PEM_PATH not in env"))]
    for spec in specs:
        label = spec.get("label", spec.get("series_ticker") or spec.get("ticker", "?"))
        try:
            if "series_ticker" in spec:
                mtype = spec.get("market_type", "winner")  # "winner" field or "match" h2h
                data = _kalshi_get(env, f"{_KALSHI_PATH_PREFIX}/markets",
                                   params={"series_ticker": spec["series_ticker"], "limit": 1000})
                ts = now_iso()  # one timestamp for the whole series pass
                for m in data.get("markets", []):
                    team = m.get("yes_sub_title") or m.get("title", "")
                    out.append(_kalshi_quote_from_market(m, label, str(team),
                                                         market_type=mtype, ts=ts))
            else:
                data = _kalshi_get(env, f"{_KALSHI_PATH_PREFIX}/markets/{spec['ticker']}")
                m = data.get("market", data)
                out.append(_kalshi_quote_from_market(m, label, "yes"))
        except Exception as e:
            who = spec.get("series_ticker") or spec.get("ticker", "?")
            out.append(_error_quote("kalshi", str(who), label, e))
    return out


# --------------------------------------------------------------------------- #
# The Odds API: multi-bookmaker odds across regions.
# Docs: https://the-odds-api.com/liveapi/guides/v4/
# config["oddsapi"]: {"sport": "soccer_fifa_world_cup", "regions": "uk", "markets": "h2h"}
# One /odds call returns ALL events for the sport. Cost = (#markets x #regions)
# credits PER CALL, against a monthly quota (see logger/README.md). Poll this venue
# far less often than the free Polymarket/Kalshi feeds.
# --------------------------------------------------------------------------- #
def fetch_oddsapi(config: dict, env: dict) -> list[Quote]:
    cfg = config.get("oddsapi")
    if not cfg:
        return []
    key = env.get("ODDSAPI_KEY")
    if not key:
        return [_error_quote("oddsapi", "*", "oddsapi", RuntimeError("ODDSAPI_KEY not in env"))]

    feeds = cfg if isinstance(cfg, list) else [cfg]  # one or many sport feeds
    out: list[Quote] = []
    for feed in feeds:
        out.extend(_fetch_oddsapi_feed(feed, key))
    return out


def _fetch_oddsapi_feed(cfg: dict, key: str) -> list[Quote]:
    sport = cfg.get("sport", "soccer_fifa_world_cup")
    regions = cfg.get("regions", "uk")
    markets = cfg.get("markets", "h2h")
    out: list[Quote] = []
    try:
        r = requests.get(
            f"https://api.the-odds-api.com/v4/sports/{sport}/odds",
            params={"apiKey": key, "regions": regions,
                    "markets": markets, "oddsFormat": "decimal"},
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        remaining = r.headers.get("x-requests-remaining")
        used = r.headers.get("x-requests-used")
        ts = now_iso()
        for ev in r.json():
            ev_id = ev.get("id", "?")
            label = f"{ev.get('home_team', '?')} vs {ev.get('away_team', '?')}"
            for bk in ev.get("bookmakers", []):
                for mk in bk.get("markets", []):
                    outs = mk.get("outcomes", [])
                    implied = [(1.0 / p if p else None)
                               for p in (_as_float(o.get("price")) for o in outs)]
                    total = sum(p for p in implied if p)  # for overround removal
                    for o, imp in zip(outs, implied):
                        norm = (imp / total) if (imp and total) else None
                        out.append(Quote(
                            ts_utc=ts, venue="oddsapi", market_id=str(ev_id),
                            market_label=label, outcome=str(o.get("name")),
                            mid=norm,  # overround-stripped implied probability
                            extra={
                                "bookmaker": bk.get("key"),
                                "market_type": mk.get("key"),
                                "point": o.get("point"),  # handicap/total line (spreads, totals)
                                "decimal_odds": _as_float(o.get("price")),
                                "implied_raw": imp,
                                "commence_time": ev.get("commence_time"),
                                "book_last_update": bk.get("last_update"),
                                "quota_remaining": remaining,
                                "quota_used": used,
                            },
                        ))
    except Exception as e:
        out.append(_error_quote("oddsapi", "*", "oddsapi", e))
    return out


# --------------------------------------------------------------------------- #
# Order books: depth and spread snapshots for the microstructure layer.
# config["orderbooks"]: {"kalshi_series": "KXMENWORLDCUP",
#                        "polymarket_event": "world-cup-winner",
#                        "top_levels": 5}
# Stored as Quotes with market_type="orderbook": bid/ask/mid plus spread, depth, and
# the top price levels in `extra`. Kalshi shows only bids (YES and NO); the YES ask is
# the reciprocal of the best NO bid (1 - best_no_bid).
# --------------------------------------------------------------------------- #
def _levels_summary(levels, descending_best: bool, top_n: int):
    """(best_price, total_size, top_n levels) from [(price,size), ...]."""
    if not levels:
        return None, 0.0, []
    total = sum(s for _, s in levels)
    ranked = sorted(levels, key=lambda x: -x[0] if descending_best else x[0])
    return ranked[0][0], total, [[round(p, 4), s] for p, s in ranked[:top_n]]


def _book_quote(venue, market_id, team, label, best_bid, best_ask,
                bid_depth, ask_depth, bid_levels, ask_levels) -> Quote:
    mid = (best_bid + best_ask) / 2 if best_bid is not None and best_ask is not None else None
    spread = (best_ask - best_bid) if best_bid is not None and best_ask is not None else None
    return Quote(
        ts_utc=now_iso(), venue=venue, market_id=str(market_id), market_label=label,
        outcome=str(team), bid=best_bid, ask=best_ask, mid=mid,
        extra={"market_type": "orderbook", "spread": spread,
               "bid_depth": bid_depth, "ask_depth": ask_depth,
               "bid_levels": bid_levels, "ask_levels": ask_levels},
    )


def fetch_orderbooks(config: dict, env: dict) -> list[Quote]:
    cfg = config.get("orderbooks")
    if not cfg:
        return []
    top_n = int(cfg.get("top_levels", 5))
    out: list[Quote] = []

    # --- Kalshi: list the series, then pull each market's book ---
    ks = cfg.get("kalshi_series")
    if ks and "KALSHI_ACCESS_KEY" in env:
        try:
            mk = _kalshi_get(env, f"{_KALSHI_PATH_PREFIX}/markets",
                             params={"series_ticker": ks, "limit": 1000}).get("markets", [])
        except Exception as e:
            mk = []
            out.append(_error_quote("kalshi", ks, "orderbook-list", e))
        for m in mk:
            ticker = m.get("ticker", "?")
            team = m.get("yes_sub_title") or m.get("title", "")
            try:
                ob = _kalshi_get(env, f"{_KALSHI_PATH_PREFIX}/markets/{ticker}/orderbook"
                                 ).get("orderbook_fp", {})
                yes = [(float(p), float(c)) for p, c in (ob.get("yes_dollars") or [])]
                no = [(float(p), float(c)) for p, c in (ob.get("no_dollars") or [])]
                yb, ydepth, ylv = _levels_summary(yes, True, top_n)
                nb, ndepth, nlv = _levels_summary(no, True, top_n)
                best_ask = (1.0 - nb) if nb is not None else None  # YES ask = 1 - best NO bid
                out.append(_book_quote("kalshi", ticker, team, ks, yb, best_ask,
                                       ydepth, ndepth, ylv, nlv))
            except Exception as e:
                out.append(_error_quote("kalshi", ticker, str(team), e))

    # --- Polymarket: event children, pull each YES token's CLOB book ---
    pe = cfg.get("polymarket_event")
    if pe:
        try:
            ev = requests.get("https://gamma-api.polymarket.com/events",
                              params={"slug": pe}, timeout=HTTP_TIMEOUT)
            ev.raise_for_status()
            ev = ev.json()
            ev = ev[0] if isinstance(ev, list) and ev else ev
            markets = ev.get("markets", []) if isinstance(ev, dict) else []
        except Exception as e:
            markets = []
            out.append(_error_quote("polymarket", pe, "orderbook-event", e))
        for m in markets:
            team = m.get("groupItemTitle") or m.get("question", "")
            toks = _maybe_json_list(m.get("clobTokenIds"))
            if not toks:
                continue
            try:
                bk = requests.get("https://clob.polymarket.com/book",
                                  params={"token_id": toks[0]}, timeout=HTTP_TIMEOUT)
                bk.raise_for_status()
                bk = bk.json()
                bids = [(float(b["price"]), float(b["size"])) for b in bk.get("bids", [])]
                asks = [(float(a["price"]), float(a["size"])) for a in bk.get("asks", [])]
                bb, bdepth, blv = _levels_summary(bids, True, top_n)   # best bid = highest
                ba, adepth, alv = _levels_summary(asks, False, top_n)  # best ask = lowest
                out.append(_book_quote("polymarket", m.get("id"), team, pe, bb, ba,
                                       bdepth, adepth, blv, alv))
            except Exception as e:
                out.append(_error_quote("polymarket", str(m.get("id")), str(team), e))
    return out


FETCHERS = {
    "polymarket": fetch_polymarket,
    "kalshi": fetch_kalshi,
    "oddsapi": fetch_oddsapi,
    "orderbooks": fetch_orderbooks,
}
