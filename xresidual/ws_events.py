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


def load_ws_events(data_dir: str) -> list[dict]:
    rows = []
    for path in sorted(glob.glob(os.path.join(data_dir, "ws-events-*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


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


def _grid(series: list[tuple[int, float]], t0: int, t1: int, bin_ms: int) -> np.ndarray:
    """Last value per bin, forward-filled across the [t0, t1] grid."""
    n = max(1, (t1 - t0) // bin_ms + 1)
    g = np.full(n, np.nan)
    for t, v in series:
        i = min(n - 1, (t - t0) // bin_ms)
        g[i] = v
    # forward fill
    last = np.nan
    for i in range(n):
        if np.isnan(g[i]):
            g[i] = last
        else:
            last = g[i]
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
                max_lag_ms: int = 10000) -> dict | None:
    """Cross-correlate binned mid-changes; report which venue leads, in ms.

    Positive lag => Polymarket leads Kalshi. Needs both series to actually move."""
    if len(series_kalshi) < 3 or len(series_poly) < 3:
        return None
    t0 = min(series_kalshi[0][0], series_poly[0][0])
    t1 = max(series_kalshi[-1][0], series_poly[-1][0])
    gk = np.diff(_grid(series_kalshi, t0, t1, bin_ms))
    gp = np.diff(_grid(series_poly, t0, t1, bin_ms))
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
                  lookback_ms: int = 4000, refractory_ms: int = 30000) -> list[dict]:
    """Times where the mid moved >= `min_jump` (probability units) within `lookback_ms`.

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


def _slice(series, lo, hi):
    return [x for x in series if lo <= x[0] <= hi]


def auto_lead_lag(events: list[dict], pairs: list[dict], min_jump: float = 0.04,
                  before_s: int = 10, after_s: int = 20, bin_ms: int = 200,
                  refractory_ms: int = 30000) -> list[dict]:
    """End-to-end: for each {label, kalshi, poly} pair, reconstruct both venues' mids,
    auto-detect shocks (on either venue), and measure the cross-venue lead at each.

    Returns one dict per pair: {label, kalshi, poly, n_events, events:[{t_ms, jump,
    lead, kalshi_reaction, poly_reaction}], tape}. `tape` is the leadlag_tape.html
    payload for the cleanest (largest-jump) event. No manual goal time anywhere."""
    out = []
    for pr in pairs:
        kt, pa = pr.get("kalshi"), pr.get("poly")
        k = kalshi_mid_series(events, kt) if kt else []
        p = polymarket_mid_series(events, pa) if pa else []
        # detect on both venues, then cluster nearby detections into single events
        cand = sorted(detect_shocks(k, min_jump, refractory_ms=refractory_ms) +
                      detect_shocks(p, min_jump, refractory_ms=refractory_ms),
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
