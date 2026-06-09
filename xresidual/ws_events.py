"""Lead-lag from websocket events. The cross-venue price-discovery piece.

Takes the raw ws-events capture (logger/ws_capture.py), rebuilds each venue's
mid-price series at millisecond resolution, and measures which venue moves first.

Mid extraction (validated against real event shapes):
  - Kalshi: the `ticker` channel carries yes_bid_dollars / yes_ask_dollars -> mid.
  - Polymarket: reconstruct the book from the `book` snapshot + `price_change`
    deltas (each sets the resting size at a price/side; size 0 removes), then mid =
    (best bid + best ask) / 2.

Lead-lag: bin both series to a common grid, cross-correlate the changes at ±max_lag.
A positive best lag means Polymarket leads Kalshi; negative means Kalshi leads.
"""

from __future__ import annotations

import glob
import json
import os

import numpy as np


def _capture_suffix(path: str, prefix: str) -> str:
    """'…/ws-events-20260611T1900Z-mex-rsa.jsonl' -> '20260611T1900Z-mex-rsa'."""
    base = os.path.basename(path)
    return base[len(prefix):-len(".jsonl")] if base.startswith(prefix) else base


def latest_capture(data_dir: str) -> str | None:
    """Suffix (capture id) of the most recent ws-events file, or None. Each capture
    writes its OWN file keyed by match+start instant, so the lexically-last file is the
    latest-started capture and its events never mix with another match's. Both the
    events file and its ws-pairs sidecar share this suffix, so callers load a matched
    pair with load_ws_events(..., capture=cap) + load_pairs(..., capture=cap)."""
    paths = sorted(glob.glob(os.path.join(data_dir, "ws-events-*.jsonl")))
    return _capture_suffix(paths[-1], "ws-events-") if paths else None


def _read_jsonl(path: str) -> list[dict]:
    """Parse a JSONL file, skipping any torn/partial line rather than letting one bad
    record abort the whole load. (Concurrent appends from simultaneous captures used to
    write to one shared file and could interleave mid-line; files are now per-capture,
    but the guard stays so a single corrupt byte never kills the analysis.)"""
    rows, bad = [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                bad += 1
    if bad:
        print(f"  warn: skipped {bad} malformed line(s) in {os.path.basename(path)}")
    return rows


def load_ws_events(data_dir: str, capture: str | None = None,
                   latest_only: bool = True) -> list[dict]:
    """Load captured ws-events. With `capture` set, reads exactly that capture's file
    (the safe path — pair it with load_pairs(capture=...)). Otherwise reads only the most
    recent capture (latest_only=True) so stale events from earlier matches can't mix in,
    or the full history with latest_only=False. Torn lines are skipped, not fatal."""
    if capture is not None:
        path = os.path.join(data_dir, f"ws-events-{capture}.jsonl")
        return _read_jsonl(path) if os.path.exists(path) else []
    paths = sorted(glob.glob(os.path.join(data_dir, "ws-events-*.jsonl")))
    if latest_only:
        paths = paths[-1:]
    rows = []
    for path in paths:
        rows.extend(_read_jsonl(path))
    return rows


def load_pairs(data_dir: str, capture: str | None = None) -> list[dict]:
    """Cross-venue pairs recorded by ws_capture, de-duplicated by (kalshi, poly).
    Scoped to one capture (the matching ws-pairs sidecar), so a match's legs can never
    collide with another capture's tokens. `capture` defaults to the latest capture."""
    if capture is None:
        capture = latest_capture(data_dir)
    if capture is None:
        return []
    path = os.path.join(data_dir, f"ws-pairs-{capture}.jsonl")
    if not os.path.exists(path):
        return []
    seen, pairs = set(), []
    for p in _read_jsonl(path):
        key = (p.get("kalshi"), p.get("poly"))
        if key != (None, None) and key not in seen:
            seen.add(key)
            pairs.append({"label": p.get("label", ""), "kalshi": p.get("kalshi"),
                          "poly": p.get("poly")})
    return pairs


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def kalshi_mid_series(events: list[dict], ticker: str) -> list[tuple[int, float]]:
    """(local_ms, mid) from Kalshi `ticker` events for one market."""
    out = []
    for e in events:
        if e["venue"] != "kalshi" or e["type"] != "ticker" or e["market"] != ticker:
            continue
        d = e["data"]
        bid, ask = _f(d.get("yes_bid_dollars")), _f(d.get("yes_ask_dollars"))
        if bid is not None and ask is not None:
            out.append((e["t"], (bid + ask) / 2))
        elif _f(d.get("price_dollars")) is not None:
            out.append((e["t"], _f(d["price_dollars"])))
    return out


def polymarket_mid_series(events: list[dict], asset_id: str) -> list[tuple[int, float]]:
    """(local_ms, mid) for one Polymarket token, reconstructing the book from the
    snapshot + price_change deltas."""
    bids: dict[float, float] = {}
    asks: dict[float, float] = {}

    def mid():
        b = [p for p, s in bids.items() if s > 0]
        a = [p for p, s in asks.items() if s > 0]
        if not b or not a:
            return None
        return (max(b) + min(a)) / 2

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
            # the asset is inside each change, not the event's top-level market key
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
        m = mid()
        if m is not None:
            out.append((e["t"], m))
    return out


def _grid(series: list[tuple[int, float]], t0: int, t1: int, bin_ms: int,
          max_gap_ms: int | None = None) -> np.ndarray:
    """Last value per bin, forward-filled across the [t0, t1] grid.

    `max_gap_ms` caps the forward-fill: bins more than that long after the last real
    observation stay NaN. This matters because a venue disconnect (logged as a
    _capture_disconnected meta event, with no price ticks until reconnect) would
    otherwise be filled with a flat pre-disconnect price — fabricating a steady mid that
    fakes lead-lag and a fake reconnect jump. Beyond the cap we'd rather have a hole the
    correlation/vol step masks out than invented data. None = unlimited (legacy)."""
    n = max(1, (t1 - t0) // bin_ms + 1)
    g = np.full(n, np.nan)
    for t, v in series:
        i = min(n - 1, (t - t0) // bin_ms)
        g[i] = v
    max_bins = None if max_gap_ms is None else max(1, max_gap_ms // bin_ms)
    last, gap = np.nan, 0
    for i in range(n):
        if np.isnan(g[i]):
            gap += 1
            if not np.isnan(last) and (max_bins is None or gap <= max_bins):
                g[i] = last
        else:
            last, gap = g[i], 0
    return g


def event_window(events: list[dict], kalshi_ticker: str, poly_asset: str,
                 t_event_ms: int, before_s: int = 10, after_s: int = 20,
                 bin_ms: int = 200) -> dict:
    """Extract both venues' mid series in a window around an event (e.g. a goal), plus
    the lead. Output maps straight onto viz/leadlag_tape.html:

        w = event_window(events, ticker, asset, goal_ms)
        # DATA.kalshi = w["kalshi"], DATA.poly = w["poly"]
        # CONFIG.leadSec = abs(w["lead"]["best_lag_ms"])/1000, CONFIG.leader = w["lead"]["leader"]

    Series are [[seconds_relative_to_event, mid], ...]."""
    k = kalshi_mid_series(events, kalshi_ticker)
    p = polymarket_mid_series(events, poly_asset)
    lo, hi = t_event_ms - before_s * 1000, t_event_ms + after_s * 1000
    win = lambda s: [[round((t - t_event_ms) / 1000, 2), round(v, 4)] for t, v in s if lo <= t <= hi]
    return {"kalshi": win(k), "poly": win(p),
            "lead": lead_lag_ms(k, p, bin_ms=bin_ms, max_lag_ms=after_s * 1000)}


def lead_lag_ms(series_kalshi, series_poly, bin_ms: int = 1000,
                max_lag_ms: int = 10000, max_gap_ms: int = 5000) -> dict | None:
    """Cross-correlate binned mid-changes; report which venue leads, in ms.

    Positive lag => Polymarket leads Kalshi. Needs both series to actually move.
    `max_gap_ms` caps the forward-fill so a venue disconnect is masked out (NaN), not
    forward-filled into a flat line that would fake a lead."""
    if len(series_kalshi) < 3 or len(series_poly) < 3:
        return None
    t0 = min(series_kalshi[0][0], series_poly[0][0])
    t1 = max(series_kalshi[-1][0], series_poly[-1][0])
    gk = np.diff(_grid(series_kalshi, t0, t1, bin_ms, max_gap_ms))
    gp = np.diff(_grid(series_poly, t0, t1, bin_ms, max_gap_ms))
    mask = ~(np.isnan(gk) | np.isnan(gp))
    gk, gp = gk[mask], gp[mask]
    max_lag = max_lag_ms // bin_ms
    if len(gk) < max_lag + 3 or np.nanstd(gk) == 0 or np.nanstd(gp) == 0:
        return None
    best_lag, best_corr = 0, 0.0
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            a, b = gk[lag:], gp[:len(gp) - lag] if lag else gp
        else:
            a, b = gk[:lag], gp[-lag:]
        if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
            continue
        c = float(np.corrcoef(a, b)[0, 1])
        if abs(c) > abs(best_corr):
            best_lag, best_corr = lag, c
    return {"best_lag_ms": best_lag * bin_ms, "best_corr": best_corr,
            "leader": "polymarket" if best_lag > 0 else "kalshi" if best_lag < 0 else "synchronous",
            "n_bins": int(len(gk))}


# --- Automatic shock detection (so lead-lag fires without a hand-typed goal time) --
# A goal / red card / major news event shows up as a fast, large mid move. Rather than
# eyeballing the minute a goal went in, scan the series for moves that clear a threshold
# inside a short trailing window, and treat each as a candidate price shock. So the
# analysis finds the shocks itself instead of relying on a hand-typed goal time.

def detect_shocks(series: list[tuple[int, float]], min_jump: float = 0.04,
                  lookback_ms: int = 60000, refractory_ms: int = 30000) -> list[dict]:
    """Times where the mid moved >= `min_jump` (probability units) within `lookback_ms`.

    `lookback_ms` defaults to 60s, matching the callers (overreaction_backtest,
    auto_lead_lag): prediction markets reprice a goal GRADUALLY over tens of seconds
    (learned live on Peru-Spain), so a 4s window misses the goal. Pass a small lookback
    only for tick-scale synthetic tests.
    `refractory_ms` suppresses re-triggering on the same move (one goal = one shock).
    Returns [{t_ms, pre, post, jump, dir}], earliest first."""
    if len(series) < 2:
        return []
    shocks, last_fire, j = [], -10 ** 18, 0
    for t, v in series:
        while j + 1 < len(series) and series[j + 1][0] <= t - lookback_ms:
            j += 1
        base_t, base_v = series[j]
        if base_t > t - lookback_ms + 1:  # not enough trailing history yet
            continue
        jump = v - base_v
        if abs(jump) >= min_jump and t - last_fire >= refractory_ms:
            shocks.append({"t_ms": t, "pre": round(base_v, 4), "post": round(v, 4),
                           "jump": round(jump, 4), "dir": "up" if jump > 0 else "down"})
            last_fire = t
    return shocks


def max_move_sigma(series: list[tuple[int, float]], bin_ms: int = 1000,
                   window_bins: int = 1800, min_prior: int = 30) -> dict | None:
    """The biggest single-bin mid move in z-units vs trailing realized vol (the P8 metric).

    Grids the series at `bin_ms`, takes one-bin returns, and for each bin computes
    z = |return| / (std of returns over the prior `window_bins`, excluding the move
    itself). Returns {max_sigma, bin, ret_at_max, n_bins} for the largest z, or None if
    there isn't enough history. This is the number that debunks "12-sigma" claims: the
    biggest real in-play shock is usually ~2-3 sigma."""
    if len(series) < 3:
        return None
    t0, t1 = series[0][0], series[-1][0]
    # cap the ffill so a disconnect gap is dropped, not turned into a fake 0-then-jump
    # return that would inflate the max-sigma figure this metric exists to debunk.
    g = _grid(series, t0, t1, bin_ms, max_gap_ms=5 * bin_ms)
    g = g[~np.isnan(g)]
    if len(g) < min_prior + 2:
        return None
    rets = np.diff(g)
    z = np.full(len(rets), np.nan)
    for i in range(len(rets)):
        prior = rets[max(0, i - window_bins):i]
        if len(prior) >= min_prior:
            s = float(prior.std())
            if s > 0:
                z[i] = abs(rets[i]) / s
    if np.all(np.isnan(z)):
        return None
    j = int(np.nanargmax(z))
    return {"max_sigma": round(float(z[j]), 2), "bin": j,
            "ret_at_max": round(float(rets[j]), 4), "n_bins": int(len(g))}


# --- Goal-overreaction mean reversion (the candidate trading edge) ---------------- #
# The literature (Choi & Hui; "Role of Surprise") finds in-play markets OVERREACT to
# surprising goals: the scoring side is overbet, the price overshoots, then reverts
# within ~6 min, with a documented ~2-3% edge to betting AGAINST the move ~2 min after.
# Not a speed game (minutes, not ms). This backtests that fade on our captured mids.

def _value_at(series: list[tuple[int, float]], t_ms: int) -> float | None:
    """Last mid at or before t_ms (forward-fill). None if t_ms precedes the series."""
    v = None
    for t, m in series:
        if t <= t_ms:
            v = m
        else:
            break
    return v


def overreaction_trade(series, shock: dict, entry_s: int = 120, exit_s: int = 360,
                       cost: float = 0.005) -> dict | None:
    """Fade one goal shock: enter `entry_s` after it (betting it reverts), exit `exit_s`
    after. Fade direction is opposite the shock (short an up-spike, long a down-spike).
    PnL is in probability units, net of a modeled round-trip `cost`. None if the window
    runs past the captured series."""
    t0, jump = shock["t_ms"], shock["jump"]
    if not series or jump == 0 or t0 + exit_s * 1000 > series[-1][0]:
        return None                                    # exit runs past the capture
    p_entry = _value_at(series, t0 + entry_s * 1000)
    p_exit = _value_at(series, t0 + exit_s * 1000)
    if p_entry is None or p_exit is None:
        return None
    side = -1 if jump > 0 else 1                       # fade the spike
    reverted = side * (p_exit - p_entry)               # gross reversion captured
    return {"t_ms": t0, "jump": round(jump, 4), "pre": shock.get("pre"),
            "p_entry": round(p_entry, 4), "p_exit": round(p_exit, 4),
            "reverted_pp": round(reverted * 100, 3),
            "pnl_pp": round((reverted - cost) * 100, 3),
            "surprise": round(abs(jump) / max(shock.get("pre") or 0.01, 0.01), 2)}


def overreaction_backtest(series, min_jump: float = 0.04, entry_s: int = 120,
                          exit_s: int = 360, cost: float = 0.005,
                          refractory_ms: int = 30000, min_surprise: float = 0.0,
                          lookback_ms: int = 60000) -> dict:
    """Detect goal shocks in one contract's mid series and fade each. `min_surprise`
    filters to the more-surprising goals (|jump|/pre), where the overreaction is strongest.
    `lookback_ms` defaults to 60s, not the 4s tick default: prediction markets reprice a
    goal GRADUALLY over tens of seconds (learned live on Peru-Spain), so a 4s window misses
    the goal entirely. Returns {trades, summary}."""
    shocks = detect_shocks(series, min_jump=min_jump, lookback_ms=lookback_ms,
                           refractory_ms=refractory_ms)
    trades = []
    for s in shocks:
        tr = overreaction_trade(series, s, entry_s, exit_s, cost)
        if tr and tr["surprise"] >= min_surprise:
            trades.append(tr)
    return {"trades": trades, "summary": _ovr_summary(trades)}


def _ovr_summary(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "total_pnl_pp": 0.0, "hit_rate": None,
                "mean_reverted_pp": None, "mean_pnl_pp": None, "per_trade_sharpe": None}
    pnl = np.array([t["pnl_pp"] for t in trades], dtype=float)
    rev = np.array([t["reverted_pp"] for t in trades], dtype=float)
    return {"n": len(trades), "total_pnl_pp": round(float(pnl.sum()), 3),
            "hit_rate": round(float((pnl > 0).mean()), 3),
            "mean_reverted_pp": round(float(rev.mean()), 3),
            "mean_pnl_pp": round(float(pnl.mean()), 3),
            "per_trade_sharpe": round(float(pnl.mean() / pnl.std()), 3) if pnl.std() > 0 else None}


def _slice(series, lo, hi):
    return [x for x in series if lo <= x[0] <= hi]


def auto_lead_lag(events: list[dict], pairs: list[dict], min_jump: float = 0.04,
                  before_s: int = 10, after_s: int = 20, bin_ms: int = 200,
                  refractory_ms: int = 30000, lookback_ms: int = 60000) -> list[dict]:
    """End-to-end: for each {label, kalshi, poly} pair, reconstruct both venues' mids,
    auto-detect shocks (on either venue), and measure the cross-venue lead at each.

    `lookback_ms` defaults to 60s (goals reprice gradually; a 4s window misses them,
    learned live on Peru-Spain). Returns one dict per pair: {label, kalshi, poly,
    n_events, events:[{t_ms, jump, lead, kalshi_reaction, poly_reaction}], tape}. `tape`
    is the leadlag_tape.html payload for the cleanest (largest-jump) event."""
    out = []
    for pr in pairs:
        kt, pa = pr.get("kalshi"), pr.get("poly")
        k = kalshi_mid_series(events, kt) if kt else []
        p = polymarket_mid_series(events, pa) if pa else []
        # detect on both venues, then cluster nearby detections into single events
        cand = sorted(detect_shocks(k, min_jump, lookback_ms=lookback_ms, refractory_ms=refractory_ms) +
                      detect_shocks(p, min_jump, lookback_ms=lookback_ms, refractory_ms=refractory_ms),
                      key=lambda s: s["t_ms"])
        times = []
        for s in cand:
            if not times or s["t_ms"] - times[-1] >= refractory_ms:
                times.append(s["t_ms"])
        evs = []
        for te in times:
            lo, hi = te - before_s * 1000, te + after_s * 1000
            ll = lead_lag_ms(_slice(k, lo, hi), _slice(p, lo, hi),
                             bin_ms=bin_ms, max_lag_ms=after_s * 1000)
            jump = max((abs(c["jump"]) for c in cand if abs(c["t_ms"] - te) < refractory_ms),
                       default=0.0)
            evs.append({"t_ms": te, "jump": round(jump, 4), "lead": ll,
                        "kalshi_reaction": goal_reaction(k, te),
                        "poly_reaction": goal_reaction(p, te)})
        tape = None
        if evs:
            best = max(evs, key=lambda e: e["jump"])
            tape = event_window(events, kt, pa, best["t_ms"], before_s, after_s, bin_ms)
        out.append({"label": pr.get("label", kt or pa), "kalshi": kt, "poly": pa,
                    "n_events": len(evs), "events": evs, "tape": tape})
    return out


def pool_leads(results: list[dict]) -> dict | None:
    """Pool every event's lead across pairs: median lead (ms), IQR, and how consistent
    the leader is (the honesty check: random sign flips = no real leadership)."""
    leads = [e["lead"]["best_lag_ms"] for r in results for e in r["events"]
             if e.get("lead")]
    if not leads:
        return None
    a = np.array(sorted(leads), dtype=float)
    poly = int((a > 0).sum()); kal = int((a < 0).sum())
    lead_side = "polymarket" if poly > kal else "kalshi" if kal > poly else "split"
    consistency = max(poly, kal) / len(a)
    return {"n": len(a), "median_lead_ms": float(np.median(a)),
            "iqr_ms": [float(np.percentile(a, 25)), float(np.percentile(a, 75))],
            "leader": lead_side, "leader_share": round(consistency, 3),
            "poly_leads": poly, "kalshi_leads": kal}


# --- Goal overreaction (METHODOLOGY §3/§6) ---------------------------------------
# Theory (Croxson & Reade 2014): in-play markets overreact to *surprising* goals and
# underreact to expected ones. Test: when a goal hits, measure the price jump, then how
# much of it the market gives back over the next minutes. A positive "reversal" =
# overreaction; ~0 = efficient. Conditioning on surprise (1 - the scoring team's
# pre-goal implied prob) is the experiment: surprising goals should revert more.

def _mean_in(series: list[tuple[int, float]], t0: int, t1: int):
    vals = [v for t, v in series if t0 <= t <= t1]
    return float(np.mean(vals)) if vals else None


def _at(series: list[tuple[int, float]], t: int):
    """Last mid at or before time t (the price the market was showing then)."""
    last = None
    for ts, v in series:
        if ts <= t:
            last = v
        else:
            break
    return last


def goal_reaction(series: list[tuple[int, float]], t_goal_ms: int,
                  pre_s: tuple = (-15, -2), settle_s: tuple = (4, 12),
                  horizons_s: tuple = (60, 180, 300)) -> dict | None:
    """How ONE contract's mid reacts to a goal at `t_goal_ms`. Pass the *scoring*
    team's contract (its price jumps up), so surprise = 1 - pre-goal prob.

      pre     : baseline mid just before the goal
      settle  : the immediate post-goal level (the reaction)
      jump    : settle - pre
      reversals[h].reversal_frac : fraction of the jump given back by t+h
                                   (>0 overreaction · ~0 efficient · <0 momentum)
    """
    pre = _mean_in(series, t_goal_ms + pre_s[0] * 1000, t_goal_ms + pre_s[1] * 1000)
    settle = _mean_in(series, t_goal_ms + settle_s[0] * 1000, t_goal_ms + settle_s[1] * 1000)
    if pre is None or settle is None:
        return None
    jump = settle - pre
    revs = {}
    for h in horizons_s:
        later = _at(series, t_goal_ms + h * 1000)
        if later is None:
            continue
        revs[h] = {"level": round(later, 4),
                   "reversal_frac": round((settle - later) / jump, 3) if abs(jump) > 1e-9 else None}
    return {"pre": round(pre, 4), "settle": round(settle, 4), "jump": round(jump, 4),
            "surprise": round(1.0 - pre, 3), "reversals": revs}


def overreaction_summary(reactions: list[dict], horizon_s: int = 180) -> dict | None:
    """Aggregate per-goal reactions into the Croxson-Reade test: do *surprising* goals
    revert more than *expected* ones? Splits at the median surprise and also fits the
    reversal-on-surprise slope (positive => overreaction scales with surprise)."""
    rs = [(r["surprise"], r["reversals"][horizon_s]["reversal_frac"])
          for r in reactions if r and horizon_s in r.get("reversals", {})
          and r["reversals"][horizon_s]["reversal_frac"] is not None]
    if not rs:
        return None
    surp = np.array([s for s, _ in rs]); rev = np.array([f for _, f in rs])
    med = float(np.median(surp))
    hi, lo = rev[surp >= med], rev[surp < med]
    out = {"n": len(rs), "horizon_s": horizon_s, "mean_reversal": round(float(rev.mean()), 3),
           "surprising_goals_reversal": round(float(hi.mean()), 3) if len(hi) else None,
           "expected_goals_reversal": round(float(lo.mean()), 3) if len(lo) else None}
    if surp.std() > 1e-9 and len(rs) >= 3:
        out["slope_reversal_on_surprise"] = round(float(np.polyfit(surp, rev, 1)[0]), 3)
    return out
