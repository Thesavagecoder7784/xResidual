#!/usr/bin/env python3
"""Single-pass streaming reader for ALL three tape microstructure pipelines (lead-lag, overreaction,
OFI). Builds each contract's mid series AND top-of-book series in ONE scan over the tape, holding
only those small series (a few hundred MB) instead of the ~2M parsed event dicts (~7 GB). Reuses the
frozen xresidual math and the editable ws_book helpers unchanged, so every result is byte-identical
to the load-everything path — it just fits the 900 MB collection VM.

Mid/top-of-book extraction mirrors, exactly:
  - ws_events.kalshi_mid_series / polymarket_mid_series   (lead-lag, overreaction)
  - ws_book.kalshi_top_of_book / polymarket_top_of_book   (OFI)
Both share the Polymarket book reconstruction, so the single pass emits both per touched event.

Fork-forward: NEW scripts/ module; edits nothing in xresidual/.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xresidual import ws_events as we   # frozen math
import ws_book as wb                     # editable: add_prices, ofi_increments

_f = we._f


def stream_all(path: str, pairs: list[dict]) -> dict:
    """ONE pass over the tape. Returns per-contract series:
        {'k_mid': {ticker: [(t,mid)..]}, 'p_mid': {asset: [(t,mid)..]},
         'k_tob': {ticker: [{t,bid,ask,bid_sz,ask_sz}..]}, 'p_tob': {asset: [..]}}
    mid mirrors *_mid_series (kalshi has the price_dollars fallback); tob mirrors *_top_of_book
    (kalshi requires bid&ask). Poly book reconstructed incrementally (bounded per-asset state)."""
    kt = {pr["kalshi"] for pr in pairs if pr.get("kalshi")}
    pa = {pr["poly"] for pr in pairs if pr.get("poly")}
    k_mid = {t: [] for t in kt}; p_mid = {a: [] for a in pa}
    k_tob = {t: [] for t in kt}; p_tob = {a: [] for a in pa}
    bids = {a: {} for a in pa}; asks = {a: {} for a in pa}   # running poly book per asset (bounded)

    def poly_best(a):
        bb = [(p, s) for p, s in bids[a].items() if s > 0]
        aa = [(p, s) for p, s in asks[a].items() if s > 0]
        if not bb or not aa:
            return None
        bp, bs = max(bb, key=lambda x: x[0])
        ap, as_ = min(aa, key=lambda x: x[0])
        return bp, bs, ap, as_

    if not os.path.exists(path):
        return {"k_mid": k_mid, "p_mid": p_mid, "k_tob": k_tob, "p_tob": p_tob}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            v = e.get("venue")
            if v == "kalshi":
                if e.get("type") != "ticker":
                    continue
                m = e.get("market")
                if m not in k_mid:
                    continue
                d = e["data"]; t = e["t"]
                bid, ask = _f(d.get("yes_bid_dollars")), _f(d.get("yes_ask_dollars"))
                if bid is not None and ask is not None:
                    k_mid[m].append((t, (bid + ask) / 2))
                    k_tob[m].append({"t": t, "bid": bid, "ask": ask,
                                     "bid_sz": _f(d.get("yes_bid_size_fp")) or 0.0,
                                     "ask_sz": _f(d.get("yes_ask_size_fp")) or 0.0})
                elif _f(d.get("price_dollars")) is not None:
                    k_mid[m].append((t, _f(d["price_dollars"])))     # mid fallback only; no tob
            elif v == "polymarket":
                typ = e.get("type"); d = e["data"]; t = e["t"]
                touched = set()
                if typ == "book":
                    a = e.get("market")
                    if a in p_mid:
                        bids[a] = {_f(x["price"]): _f(x["size"]) for x in d.get("bids", [])}
                        asks[a] = {_f(x["price"]): _f(x["size"]) for x in d.get("asks", [])}
                        touched.add(a)
                elif typ == "price_change":
                    for ch in d.get("price_changes", []):
                        a = ch.get("asset_id")
                        if a not in p_mid:
                            continue
                        price, size, side = _f(ch.get("price")), _f(ch.get("size")), ch.get("side")
                        if price is None:
                            continue
                        (bids if side == "BUY" else asks)[a][price] = size or 0.0
                        touched.add(a)
                for a in touched:
                    best = poly_best(a)
                    if best is None:
                        continue
                    bp, bs, ap, as_ = best
                    p_mid[a].append((t, (bp + ap) / 2))
                    p_tob[a].append({"t": t, "bid": bp, "ask": ap, "bid_sz": bs, "ask_sz": as_})
    return {"k_mid": k_mid, "p_mid": p_mid, "k_tob": k_tob, "p_tob": p_tob}


# ---- lead-lag (drop-in for ws_events.auto_lead_lag, using prebuilt mid series) ----
def _event_window(k, p, t_ev, before_s, after_s, bin_ms):
    lo, hi = t_ev - before_s * 1000, t_ev + after_s * 1000
    win = lambda s: [[round((t - t_ev) / 1000, 2), round(v, 4)] for t, v in s if lo <= t <= hi]
    return {"kalshi": win(k), "poly": win(p),
            "lead": we.lead_lag_ms(k, p, bin_ms=bin_ms, max_lag_ms=after_s * 1000)}


def auto_lead_lag(sm: dict, pairs: list[dict], min_jump: float = 0.04, before_s: int = 10,
                  after_s: int = 20, bin_ms: int = 200, refractory_ms: int = 30000,
                  lookback_ms: int = 60000) -> list[dict]:
    out = []
    for pr in pairs:
        kt, pa = pr.get("kalshi"), pr.get("poly")
        k = sm["k_mid"].get(kt, []) if kt else []
        p = sm["p_mid"].get(pa, []) if pa else []
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
            tape = _event_window(k, p, best["t_ms"], before_s, after_s, bin_ms)
        out.append({"label": pr.get("label", kt or pa), "kalshi": kt, "poly": pa,
                    "n_events": len(evs), "events": evs, "tape": tape})
    return out


# ---- overreaction reference series (drop-in for overreaction_build._reference_series) ----
def reference_series(sm: dict, pairs: list[dict]):
    best = None
    for pr in pairs:
        for key, store in (("kalshi", sm["k_mid"]), ("poly", sm["p_mid"])):
            mid_id = pr.get(key)
            if not mid_id:
                continue
            series = store.get(mid_id, [])
            venue = "kalshi" if key == "kalshi" else "polymarket"
            if len(series) >= 10 and (best is None or len(series) > len(best[2])):
                best = (pr.get("label"), venue, series)
    return best


# ---- OFI binned (drop-in for build_ofi_leadlag._binned, using prebuilt tob) ----
def binned(sm: dict, kind: str, cid: str):
    tob = sm["k_tob"].get(cid, []) if kind == "kalshi" else sm["p_tob"].get(cid, [])
    if len(tob) < 30:
        return None
    wb.add_prices(tob)
    mid = [(r["t"], r["mid"]) for r in tob]
    micro = [(r["t"], r["micro"]) for r in tob]
    ofi = wb.ofi_increments(tob)
    return {"tob": tob, "mid": mid, "micro": micro, "ofi": ofi,
            "t0": tob[0]["t"], "t1": tob[-1]["t"]}
