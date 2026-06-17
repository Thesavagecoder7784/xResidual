#!/usr/bin/env python3
"""Tier-1 microstructure: turn the cross-venue lead-lag from a description ("Polymarket leads
Kalshi ~500ms") into a MECHANISM, using order-flow imbalance reconstructed from the book.

    python scripts/build_ofi_leadlag.py            # process NEW tapes, then re-pool
    python scripts/build_ofi_leadlag.py --all
    python scripts/build_ofi_leadlag.py --pool-only

Three measurements per matched contract (same disposable-tape / per-game-JSON architecture as
build_leadlag), pooled across matches via sufficient statistics (so it accumulates without
storing raw bins):

  1. OFI price impact (Cont-Kukanov-Stoikov 2014): regress each venue's 1s mid return on its own
     OFI. The literature's headline result is a positive linear relation; this checks it holds on
     these prediction markets (a data sanity check + the building block for #2).
  2. Cross-venue predictive lead-lag (the MECHANISM): does Polymarket's OFI predict Kalshi's NEXT
     mid move, more than Kalshi's OFI predicts Polymarket's? An asymmetry toward Poly->Kalshi at a
     positive lag is the order-flow reason Polymarket's PRICE leads (Hasbrouck-style price
     discovery: the venue where informed flow lands first leads the other's price).
  3. Microprice vs mid lead-lag: recompute the cross-venue lead on the imbalance-weighted
     microprice (Stoikov 2017) instead of the mid. A cleaner/earlier lead = a methodological win.

All variables are standardized per match before the regression, so the pooled coefficient is a
sample-size-weighted correlation (effect size) comparable across matches. Honest by construction:
if the asymmetry isn't there, the pooled summary says so. Fork-forward: reuses the frozen
xresidual/ws_events lead-lag + the new scripts/ws_book reconstruction; edits nothing in xresidual/.
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import ws_events as we  # noqa: E402
import ws_book as wb                    # noqa: E402
from build_leadlag import wc_captures, _match_label  # noqa: E402

DATA_DIR = os.path.join(ROOT, "logger", "data")
OFI_DIR = os.path.join(ROOT, "viz", "market", "ofi")     # per-match JSONs (source of truth)
OUT = os.path.join(ROOT, "viz", "market", "_ofi.js")     # pooled, for the site
RESULTS = os.path.join(ROOT, "writeups", "_ofi_results.json")  # pooled detail for the writeup

BIN_MS = 1000           # 1s bins
LAGS = list(range(-3, 4))   # lead/lag sweep in bins (= seconds); +L = predictor leads by L s
MAX_GAP_MS = 10000      # don't forward-fill a mid across a >10s gap (disconnect) -> NaN bin
MAX_LAG_MS = 8000       # cap for the micro-vs-mid cross-venue lead-lag


# ---- sufficient-statistics OLS (poolable across matches by summing) ------------------------
def suff(x, y) -> dict | None:
    x = np.asarray(x, float); y = np.asarray(y, float)
    m = ~(np.isnan(x) | np.isnan(y))
    x, y = x[m], y[m]
    if len(x) < 3:
        return None
    return {"n": int(len(x)), "Sx": float(x.sum()), "Sy": float(y.sum()),
            "Sxx": float((x * x).sum()), "Sxy": float((x * y).sum()), "Syy": float((y * y).sum())}


def comb(a: dict | None, b: dict | None) -> dict | None:
    if not a:
        return dict(b) if b else None
    if not b:
        return dict(a)
    return {k: a[k] + b[k] for k in ("n", "Sx", "Sy", "Sxx", "Sxy", "Syy")}


def finalize(s: dict | None) -> dict | None:
    """corr / R^2 / slope-t-stat from summed sufficient statistics."""
    if not s or s["n"] < 8:
        return None
    n, Sx, Sy, Sxx, Sxy, Syy = (s[k] for k in ("n", "Sx", "Sy", "Sxx", "Sxy", "Syy"))
    Sxx_c, Syy_c, Sxy_c = Sxx - Sx * Sx / n, Syy - Sy * Sy / n, Sxy - Sx * Sy / n
    if Sxx_c <= 0 or Syy_c <= 0:
        return None
    corr = Sxy_c / math.sqrt(Sxx_c * Syy_c)
    beta = Sxy_c / Sxx_c
    rss = Syy_c - beta * Sxy_c
    se = math.sqrt(rss / (n - 2) / Sxx_c) if n > 2 and rss > 0 and Sxx_c > 0 else None
    t = beta / se if se else None
    return {"corr": round(corr, 4), "r2": round(corr * corr, 4),
            "tstat": round(t, 2) if t is not None else None, "n": n}


def _z(a: np.ndarray) -> np.ndarray:
    mu, sd = np.nanmean(a), np.nanstd(a)
    return (a - mu) / sd if sd and sd > 0 else a * np.nan


def _shift_suff(x: np.ndarray, y: np.ndarray, lag: int) -> dict | None:
    """suff stats for predicting y[k] from x[k-lag]: +lag = x leads y by `lag` bins."""
    if lag > 0:
        xs, ys = x[:-lag], y[lag:]
    elif lag < 0:
        xs, ys = x[-lag:], y[:lag]
    else:
        xs, ys = x, y
    return suff(xs, ys)


def _binned(events, ticker_kind, cid):
    """For one contract on one venue: (ofi_bins, ret_bins, mid_series, micro_series) on the grid.
    ticker_kind in {'kalshi','poly'}. Returns None if too little data."""
    tob = (wb.kalshi_top_of_book(events, cid) if ticker_kind == "kalshi"
           else wb.polymarket_top_of_book(events, cid))
    if len(tob) < 30:
        return None
    wb.add_prices(tob)
    mid = [(r["t"], r["mid"]) for r in tob]
    micro = [(r["t"], r["micro"]) for r in tob]
    ofi = wb.ofi_increments(tob)
    return {"tob": tob, "mid": mid, "micro": micro, "ofi": ofi,
            "t0": tob[0]["t"], "t1": tob[-1]["t"]}


def _grids(b, t0, t1):
    """OFI-per-bin and mid-return-per-bin on a shared [t0,t1] grid for one venue's series dict.

    OFI is NaN in bins with NO book update (rather than a real 0): a quiet bin is "no observation",
    not "flow was zero". Encoding it as 0 would add a dense cloud of (0, ~0) points that inflate n
    and shrink the standardized OFI->return correlation (regression dilution toward 0), attenuating
    the very effect we measure. Restricting to active bins makes the regression conditional on there
    being book activity, the standard event-time treatment, and keeps the support honest."""
    n = max(1, (t1 - t0) // BIN_MS + 1)
    ofi = np.zeros(n)
    active = np.zeros(n, dtype=bool)
    for t, e in b["ofi"]:
        if t0 <= t <= t1:
            i = min(n - 1, (t - t0) // BIN_MS)
            ofi[i] += e
            active[i] = True
    ofi[~active] = np.nan                       # quiet bin -> no observation, not a zero
    mid_grid = we._grid(b["mid"], t0, t1, BIN_MS, max_gap_ms=MAX_GAP_MS)
    ret = np.full(n, np.nan)
    ret[1:] = np.diff(mid_grid)
    return _z(ofi), _z(ret)


def process_capture(cap: str, events=None, pairs=None, sm_bundle=None) -> str | None:
    if pairs is None:
        pairs = we.load_pairs(DATA_DIR, capture=cap)
    if sm_bundle is None and events is None:
        import stream_micro as _sm                # default to the streaming single pass (fits the VM)
        sm_bundle = _sm.stream_all(os.path.join(DATA_DIR, f"ws-events-{cap}.jsonl"), pairs)
    if not pairs or (sm_bundle is None and not events):
        return None
    if sm_bundle is not None:
        import stream_micro as _sm
    match = _match_label(cap)
    slug = cap.split("-", 1)[1] if "-" in cap else cap

    impact = {"kalshi": None, "poly": None}
    cross = {f"poly_to_kalshi@{L}": None for L in LAGS}
    cross.update({f"kalshi_to_poly@{L}": None for L in LAGS})
    ll_mid, ll_micro, n_pairs = [], [], 0

    for pr in pairs:
        kt, pa = pr.get("kalshi"), pr.get("poly")
        if not kt or not pa:
            continue
        if sm_bundle is not None:
            bk = _sm.binned(sm_bundle, "kalshi", kt)
            bp = _sm.binned(sm_bundle, "poly", pa)
        else:
            bk = _binned(events, "kalshi", kt)
            bp = _binned(events, "poly", pa)
        if not bk or not bp:
            continue
        t0, t1 = max(bk["t0"], bp["t0"]), min(bk["t1"], bp["t1"])
        if t1 - t0 < 60_000:                       # need at least a minute of overlap
            continue
        ofi_k, ret_k = _grids(bk, t0, t1)
        ofi_p, ret_p = _grids(bp, t0, t1)
        n_pairs += 1
        # 1. own-venue OFI price impact (contemporaneous)
        impact["kalshi"] = comb(impact["kalshi"], suff(ofi_k, ret_k))
        impact["poly"] = comb(impact["poly"], suff(ofi_p, ret_p))
        # 2. cross-venue predictive: does X's OFI lead the OTHER venue's return?
        for L in LAGS:
            cross[f"poly_to_kalshi@{L}"] = comb(cross[f"poly_to_kalshi@{L}"], _shift_suff(ofi_p, ret_k, L))
            cross[f"kalshi_to_poly@{L}"] = comb(cross[f"kalshi_to_poly@{L}"], _shift_suff(ofi_k, ret_p, L))
        # 3. micro vs mid cross-venue lead-lag (best lag by |corr|)
        m1 = we.lead_lag_ms(bk["mid"], bp["mid"], bin_ms=200, max_lag_ms=MAX_LAG_MS)
        m2 = we.lead_lag_ms(bk["micro"], bp["micro"], bin_ms=200, max_lag_ms=MAX_LAG_MS)
        if m1:
            ll_mid.append(m1)
        if m2:
            ll_micro.append(m2)

    def _med_ll(lls):
        if not lls:
            return None
        lags = sorted(l["best_lag_ms"] for l in lls)
        corrs = sorted(abs(l["best_corr"]) for l in lls)
        med = lambda a: a[len(a) // 2]
        return {"median_lag_ms": med(lags), "median_abs_corr": round(med(corrs), 3), "n": len(lls)}

    payload = {"match": match, "capture": cap, "n_pairs": n_pairs, "bin_ms": BIN_MS, "lags_s": LAGS,
               "impact": {k: finalize(v) for k, v in impact.items()},
               "impact_suff": impact,            # raw suff stats so the pool can recombine
               "cross_suff": cross,
               "microprice_leadlag": {"mid": _med_ll(ll_mid), "micro": _med_ll(ll_micro)}}
    os.makedirs(OFI_DIR, exist_ok=True)
    with open(os.path.join(OFI_DIR, slug + ".json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    bk_imp = payload["impact"]["kalshi"] or {}
    n_ev = len(events) if events is not None else sum(len(s) for s in sm_bundle["k_tob"].values()) + sum(len(s) for s in sm_bundle["p_tob"].values())
    print(f"  processed {match:<22} {n_ev:>10,} ev · {n_pairs} pair(s) · "
          f"OFI->price r2 kalshi={bk_imp.get('r2','?')} -> {slug}.json")
    return match


def _best_dir(cross_suff: dict, direction: str):
    """Across pooled suff stats, the lag (s) with the strongest predictive corr for a direction."""
    best = None
    by_lag = {}
    for L in LAGS:
        fin = finalize(cross_suff.get(f"{direction}@{L}"))
        if not fin:
            continue
        by_lag[L] = fin
        if best is None or abs(fin["corr"]) > abs(best[1]["corr"]):
            best = (L, fin)
    if not best:
        return None
    return {"best_lag_s": best[0], **best[1], "by_lag": by_lag}


def pool_from_archive() -> dict:
    impact = {"kalshi": None, "poly": None}
    cross = {}
    mids, micros, matches = [], [], []
    for path in sorted(glob.glob(os.path.join(OFI_DIR, "*.json"))):
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict) or "cross_suff" not in d:
            continue
        matches.append(d.get("match"))
        for v in ("kalshi", "poly"):
            impact[v] = comb(impact[v], d["impact_suff"].get(v))
        for k, s in d["cross_suff"].items():
            cross[k] = comb(cross.get(k), s)
        ml = d.get("microprice_leadlag", {})
        if ml.get("mid"):
            mids.append(ml["mid"])
        if ml.get("micro"):
            micros.append(ml["micro"])

    p2k = _best_dir(cross, "poly_to_kalshi")
    k2p = _best_dir(cross, "kalshi_to_poly")
    verdict = "pending (need more matches)"
    if p2k and k2p:
        if p2k["best_lag_s"] > 0 and abs(p2k["corr"]) > abs(k2p["corr"]) * 1.15:
            verdict = (f"Polymarket order flow leads Kalshi price: Poly OFI predicts Kalshi's move "
                       f"{p2k['best_lag_s']}s ahead (corr {p2k['corr']:+.2f}) more than the reverse "
                       f"(corr {k2p['corr']:+.2f}) — the order-flow mechanism behind the price lead.")
        elif k2p["best_lag_s"] > 0 and abs(k2p["corr"]) > abs(p2k["corr"]) * 1.15:
            verdict = (f"Kalshi order flow leads Polymarket price (corr {k2p['corr']:+.2f} at "
                       f"{k2p['best_lag_s']}s vs {p2k['corr']:+.2f}) — the opposite of the price lead.")
        else:
            verdict = (f"No clean cross-venue flow asymmetry yet (Poly->Kalshi {p2k['corr']:+.2f}, "
                       f"Kalshi->Poly {k2p['corr']:+.2f}); contemporaneous, not a lead.")

    def _pool_ll(lls):
        if not lls:
            return None
        lags = sorted(l["median_lag_ms"] for l in lls)
        return {"median_lag_ms": lags[len(lags) // 2],
                "median_abs_corr": round(sorted(l["median_abs_corr"] for l in lls)[len(lls) // 2], 3),
                "n_matches": len(lls)}

    pooled = {"n_matches": len(matches),
              "impact": {v: finalize(impact[v]) for v in ("kalshi", "poly")},
              "poly_to_kalshi": p2k, "kalshi_to_poly": k2p, "verdict": verdict,
              "microprice_leadlag": {"mid": _pool_ll(mids), "micro": _pool_ll(micros)}}
    payload = {**pooled,
               "note": "OFI price impact (Cont-Kukanov-Stoikov 2014), cross-venue predictive lead-lag "
                       "(the order-flow mechanism behind the price lead), and microprice (Stoikov 2017) "
                       "vs mid lead-lag. Standardized per match; pooled by sufficient statistics. Paper. "
                       "t-stats are BIN-LEVEL OLS, not corrected for 1s autocorrelation or match "
                       "clustering, so they overstate significance: treat corr/R^2 as the effect size and "
                       "judge significance across matches (n_matches), not bins.",
               "significance_basis": "per-bin OLS (uncorrected); n_matches is the real unit"}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.OFI = " + json.dumps(payload) + ";\n")
    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    with open(RESULTS, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    ik = pooled["impact"]["kalshi"]; ip = pooled["impact"]["poly"]
    print(f"POOLED · {len(matches)} match(es)")
    if ik:
        print(f"  OFI->price impact  kalshi r2={ik['r2']} (t={ik['tstat']})  "
              f"poly r2={ip['r2'] if ip else '?'} (t={ip['tstat'] if ip else '?'})")
    if p2k and k2p:
        print(f"  cross-venue lead   Poly->Kalshi corr {p2k['corr']:+.2f} @ {p2k['best_lag_s']}s · "
              f"Kalshi->Poly corr {k2p['corr']:+.2f} @ {k2p['best_lag_s']}s")
    mll = pooled["microprice_leadlag"]
    if mll["mid"] and mll["micro"]:
        print(f"  micro vs mid lead  mid {mll['mid']['median_lag_ms']:+.0f}ms (|r|={mll['mid']['median_abs_corr']}) · "
              f"micro {mll['micro']['median_lag_ms']:+.0f}ms (|r|={mll['micro']['median_abs_corr']})")
    print(f"  VERDICT: {verdict}")
    print(f"wrote {os.path.relpath(OUT, ROOT)} + {os.path.relpath(RESULTS, ROOT)}")
    return payload


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="incremental OFI cross-venue lead-lag mechanism")
    ap.add_argument("--all", action="store_true", help="re-process every WC tape present")
    ap.add_argument("--pool-only", action="store_true", help="rebuild the pool from JSONs; parse no tapes")
    args = ap.parse_args()
    os.makedirs(OFI_DIR, exist_ok=True)
    if args.pool_only:
        pool_from_archive()
        return 0
    caps = wc_captures(DATA_DIR)
    done = lambda c: os.path.exists(os.path.join(
        OFI_DIR, (c.split("-", 1)[1] if "-" in c else c) + ".json"))
    todo = caps if args.all else [c for c in caps if not done(c)]
    if todo:
        print(f"processing {len(todo)} new tape(s) of {len(caps)} present:")
        for cap in todo:
            process_capture(cap)
    else:
        print(f"no new tapes ({len(caps)} present, all archived); re-pooling.")
    pool_from_archive()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
