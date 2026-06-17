#!/usr/bin/env python3
"""Streaming lead-lag: build each venue's mid series in ONE pass over the tape, never holding
the ~2M parsed event dicts at once. Reuses the frozen xresidual math (detect_shocks, lead_lag_ms,
goal_reaction, _slice, pool_leads) — only the series construction is reimplemented as a stream, so
results are identical to ws_events.auto_lead_lag while peak memory drops from ~7 GB to a few hundred
MB (fits the 900 MB collection VM).

Fork-forward: NEW scripts/ module, edits nothing in xresidual/. Mirrors the exact mid logic of
ws_events.kalshi_mid_series / polymarket_mid_series (validated against real event shapes).
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xresidual import ws_events as we   # frozen math: detect_shocks, lead_lag_ms, goal_reaction, _slice, pool_leads, _f

_f = we._f


def stream_series(path: str, pairs: list[dict]) -> tuple[dict, dict]:
    """ONE pass over the tape -> ({kalshi_ticker: [(t,mid)...]}, {poly_asset: [(t,mid)...]}).

    Identical mid extraction to ws_events.kalshi_mid_series / polymarket_mid_series, but interleaved
    across all subscribed contracts in a single file scan, holding only the per-contract series and a
    bounded per-asset book (a few KB each) — not the events. Torn lines are skipped, as in _read_jsonl."""
    kt_set = {pr["kalshi"] for pr in pairs if pr.get("kalshi")}
    pa_set = {pr["poly"] for pr in pairs if pr.get("poly")}
    k_series: dict[str, list] = {kt: [] for kt in kt_set}
    p_series: dict[str, list] = {pa: [] for pa in pa_set}
    bids: dict[str, dict] = {pa: {} for pa in pa_set}   # running book per poly asset (bounded)
    asks: dict[str, dict] = {pa: {} for pa in pa_set}

    def poly_mid(pa):
        b = [pp for pp, s in bids[pa].items() if s > 0]
        a = [pp for pp, s in asks[pa].items() if s > 0]
        return (max(b) + min(a)) / 2 if b and a else None

    if not os.path.exists(path):
        return k_series, p_series
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            venue = e.get("venue")
            if venue == "kalshi":
                if e.get("type") != "ticker":
                    continue
                mkt = e.get("market")
                if mkt not in k_series:
                    continue
                d = e["data"]
                bid, ask = _f(d.get("yes_bid_dollars")), _f(d.get("yes_ask_dollars"))
                if bid is not None and ask is not None:
                    k_series[mkt].append((e["t"], (bid + ask) / 2))
                elif _f(d.get("price_dollars")) is not None:
                    k_series[mkt].append((e["t"], _f(d["price_dollars"])))
            elif venue == "polymarket":
                typ = e.get("type")
                d = e["data"]
                if typ == "book":
                    pa = e.get("market")
                    if pa not in p_series:
                        continue
                    bids[pa] = {_f(x["price"]): _f(x["size"]) for x in d.get("bids", [])}
                    asks[pa] = {_f(x["price"]): _f(x["size"]) for x in d.get("asks", [])}
                    m = poly_mid(pa)
                    if m is not None:
                        p_series[pa].append((e["t"], m))
                elif typ == "price_change":
                    # the asset is inside each change, not the event's top-level market key.
                    # Apply ALL deltas first, then record one mid per touched asset — matching
                    # polymarket_mid_series, which appends once per event after the whole loop.
                    touched = set()
                    for ch in d.get("price_changes", []):
                        pa = ch.get("asset_id")
                        if pa not in p_series:
                            continue
                        price, size, side = _f(ch.get("price")), _f(ch.get("size")), ch.get("side")
                        if price is None:
                            continue
                        (bids if side == "BUY" else asks)[pa][price] = size or 0.0
                        touched.add(pa)
                    for pa in touched:
                        m = poly_mid(pa)
                        if m is not None:
                            p_series[pa].append((e["t"], m))
    return k_series, p_series


def _event_window_from_series(k, p, t_event_ms, before_s, after_s, bin_ms):
    """Replicate ws_events.event_window using prebuilt series (no events)."""
    lo, hi = t_event_ms - before_s * 1000, t_event_ms + after_s * 1000
    win = lambda s: [[round((t - t_event_ms) / 1000, 2), round(v, 4)] for t, v in s if lo <= t <= hi]
    return {"kalshi": win(k), "poly": win(p),
            "lead": we.lead_lag_ms(k, p, bin_ms=bin_ms, max_lag_ms=after_s * 1000)}


def auto_lead_lag_streamed(path: str, pairs: list[dict], min_jump: float = 0.04,
                           before_s: int = 10, after_s: int = 20, bin_ms: int = 200,
                           refractory_ms: int = 30000, lookback_ms: int = 60000) -> list[dict]:
    """Streaming drop-in for ws_events.auto_lead_lag — identical output, ~7GB -> ~MB peak.
    Same orchestration; only the mid series come from stream_series instead of scanning events."""
    k_all, p_all = stream_series(path, pairs)
    out = []
    for pr in pairs:
        kt, pa = pr.get("kalshi"), pr.get("poly")
        k = k_all.get(kt, []) if kt else []
        p = p_all.get(pa, []) if pa else []
        cand = sorted(we.detect_shocks(k, min_jump, lookback_ms=lookback_ms, refractory_ms=refractory_ms) +
                      we.detect_shocks(p, min_jump, lookback_ms=lookback_ms, refractory_ms=refractory_ms),
                      key=lambda s: s["t_ms"])
        times = []
        for s in cand:
            if not times or s["t_ms"] - times[-1] >= refractory_ms:
                times.append(s["t_ms"])
        evs = []
        for te in times:
            lo, hi = te - before_s * 1000, te + after_s * 1000
            ll = we.lead_lag_ms(we._slice(k, lo, hi), we._slice(p, lo, hi),
                                bin_ms=bin_ms, max_lag_ms=after_s * 1000)
            jump = max((abs(c["jump"]) for c in cand if abs(c["t_ms"] - te) < refractory_ms), default=0.0)
            evs.append({"t_ms": te, "jump": round(jump, 4), "lead": ll,
                        "kalshi_reaction": we.goal_reaction(k, te),
                        "poly_reaction": we.goal_reaction(p, te)})
        tape = None
        if evs:
            best = max(evs, key=lambda e: e["jump"])
            tape = _event_window_from_series(k, p, best["t_ms"], before_s, after_s, bin_ms)
        out.append({"label": pr.get("label", kt or pa), "kalshi": kt, "poly": pa,
                    "n_events": len(evs), "events": evs, "tape": tape})
    return out


if __name__ == "__main__":
    # Equivalence + memory harness: prove streamed == frozen auto_lead_lag on a real tape.
    import argparse, resource, sys, time
    ap = argparse.ArgumentParser()
    ap.add_argument("tape", help="path to a ws-events-*.jsonl tape")
    ap.add_argument("--pairs", help="path to the matching ws-pairs file (default: infer)")
    args = ap.parse_args()
    data_dir = os.path.dirname(os.path.abspath(args.tape))
    cap = os.path.basename(args.tape)[len("ws-events-"):-len(".jsonl")]
    pairs = we.load_pairs(data_dir, capture=cap)
    print(f"pairs: {len(pairs)}")

    t0 = time.time()
    streamed = auto_lead_lag_streamed(args.tape, pairs)
    rss_stream = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    t_stream = time.time() - t0
    print(f"STREAMED: {t_stream:.1f}s  peak RSS {rss_stream/1e9:.2f} GB  pooled={we.pool_leads(streamed)}")

    t0 = time.time()
    events = we.load_ws_events(data_dir, capture=cap)
    frozen = we.auto_lead_lag(events, pairs)
    rss_frozen = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss   # cumulative max (includes the load)
    t_frozen = time.time() - t0
    print(f"FROZEN:   {t_frozen:.1f}s  cumulative peak RSS {rss_frozen/1e9:.2f} GB  pooled={we.pool_leads(frozen)}")

    # equivalence: compare the pooled result + per-pair leads
    same = (json.dumps(we.pool_leads(streamed), sort_keys=True) ==
            json.dumps(we.pool_leads(frozen), sort_keys=True))
    leads_s = [(r["label"], [e["lead"] for e in r["events"]]) for r in streamed]
    leads_f = [(r["label"], [e["lead"] for e in r["events"]]) for r in frozen]
    same = same and json.dumps(leads_s, sort_keys=True) == json.dumps(leads_f, sort_keys=True)
    print(f"\nEQUIVALENT: {'YES ✓' if same else 'NO ✗ — DIVERGENCE'}")
    sys.exit(0 if same else 1)
