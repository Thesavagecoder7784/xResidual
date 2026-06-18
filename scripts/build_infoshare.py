#!/usr/bin/env python3
"""Tier-1 microstructure: turn the cross-venue lead-lag from a COUNT ("Polymarket wins 54 of 78
shock events") into the rigorous, ordering-free price-discovery metric the literature uses —
Hasbrouck (1995) information share + Gonzalo-Granger (1995) permanent-component share — computed
on the high-frequency TAPE mids, per matched contract, pooled across matches.

    python scripts/build_infoshare.py            # process NEW tapes, then re-pool
    python scripts/build_infoshare.py --all       # re-process every WC tape present
    python scripts/build_infoshare.py --pool-only  # rebuild the pool from per-match JSONs

Why this exists: a 2026 Polymarket order-book paper (arXiv 2604.24366) computes the within-venue
microstructure but explicitly leaves the Kalshi-vs-Polymarket price-discovery question for future
work. Our tapes answer it. The event-win count is suggestive; the information share is the citable
number ("Polymarket contributes X% of price discovery"). The frozen xresidual.microstructure.
information_share already implements the VECM + Hasbrouck bounds + GG shares + an ADF cointegration
guard; this script just feeds it the aligned tape mids and pools the per-contract shares.

Method, per matched contract (same Kalshi ticker + Polymarket token = same outcome):
  - forward-fill each venue's mid onto a common BIN_MS grid over their overlap (last-price
    sampling, the standard Hasbrouck input),
  - run information_share(poly, kalshi) so the reported `a`-share IS Polymarket's share,
  - keep only contracts whose (1,-1) spread is stationary (ADF p<0.10) and long enough — on a
    non-cointegrated pair the shares are a spurious-regression artifact and are dropped.
Pooling: the honest unit is the MATCH, so we take each match's median share across its contracts,
then the median across matches for the headline (a single liquid contract can't dominate). Robust
to the ~59% WS trade-direction problem because it's computed on MID moves, not signed trades.

Fork-forward: NEW scripts/ module; reuses frozen xresidual/ unchanged; edits nothing in xresidual/.
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import ws_events as we           # noqa: E402  frozen mids + _grid
from xresidual import microstructure as ms        # noqa: E402  frozen information_share
from build_leadlag import wc_captures, _match_label  # noqa: E402

DATA_DIR = os.path.join(ROOT, "logger", "data")
IS_DIR = os.path.join(ROOT, "viz", "market", "infoshare")   # per-match JSONs (source of truth)
OUT = os.path.join(ROOT, "viz", "market", "_infoshare.js")  # pooled, for the site
RESULTS = os.path.join(ROOT, "writeups", "_infoshare_results.json")  # pooled detail for the writeup

BIN_MS = 1000            # 1s last-price grid (standard Hasbrouck frequency; sub-second is bid-ask noise)
N_LAGS = 2               # VECM short-run lags
MIN_OVERLAP_MS = 300_000  # need >=5 min of two-sided quoting to estimate a VECM
MIN_BINS = 200           # and a decently long aligned series per contract


def _ffill(a: np.ndarray) -> np.ndarray:
    """Forward-fill NaNs (rare interior disconnect gaps); leading NaNs stay NaN and get trimmed."""
    out = a.copy()
    last = np.nan
    for i in range(len(out)):
        if np.isnan(out[i]):
            out[i] = last
        else:
            last = out[i]
    return out


def pair_infoshare(k_series, p_series) -> dict | None:
    """information_share on one contract's two aligned mid grids. a=poly so a-share is Polymarket's."""
    if len(k_series) < 30 or len(p_series) < 30:
        return None
    t0 = max(k_series[0][0], p_series[0][0])
    t1 = min(k_series[-1][0], p_series[-1][0])
    if t1 - t0 < MIN_OVERLAP_MS:
        return None
    # forward-fill across all gaps (huge max_gap) -> last-price sampling; both valid from t0.
    kg = np.asarray(we._grid(k_series, t0, t1, BIN_MS, max_gap_ms=10**12), float)
    pg = np.asarray(we._grid(p_series, t0, t1, BIN_MS, max_gap_ms=10**12), float)
    mask = ~(np.isnan(kg) | np.isnan(pg))
    if mask.sum() < MIN_BINS:
        return None
    first = int(np.argmax(mask))                 # trim any leading NaN
    kg, pg = _ffill(kg[first:]), _ffill(pg[first:])
    if np.isnan(kg).any() or np.isnan(pg).any() or len(kg) < MIN_BINS:
        return None
    return ms.information_share(pg, kg, label_a="polymarket", label_b="kalshi", n_lags=N_LAGS)


def process_capture(cap: str, pairs=None, sm_bundle=None) -> str | None:
    if pairs is None:
        pairs = we.load_pairs(DATA_DIR, capture=cap)
    if not pairs:
        return None
    if sm_bundle is None:
        import stream_micro as _sm                # single low-mem pass over the tape (fits the VM)
        sm_bundle = _sm.stream_all(os.path.join(DATA_DIR, f"ws-events-{cap}.jsonl"), pairs)
    match = _match_label(cap)
    slug = cap.split("-", 1)[1] if "-" in cap else cap

    contracts = []
    for pr in pairs:
        kt, pa = pr.get("kalshi"), pr.get("poly")
        if not kt or not pa:
            continue
        k = sm_bundle["k_mid"].get(kt, [])
        p = sm_bundle["p_mid"].get(pa, [])
        res = pair_infoshare(k, p)
        if res is None:
            continue
        contracts.append({"label": pr.get("label", kt), "kalshi": kt, "poly": pa, **res})

    coint = [c for c in contracts if c.get("cointegrated") and c.get("hasbrouck_a_mid") is not None]
    match_poly_hb = _median([c["hasbrouck_a_mid"] for c in coint]) if coint else None
    match_poly_gg = _median([c["gg_a"] for c in coint]) if coint else None
    payload = {"match": match, "capture": cap, "bin_ms": BIN_MS, "n_lags": N_LAGS,
               "n_contracts": len(contracts), "n_cointegrated": len(coint),
               "match_poly_hasbrouck_mid": match_poly_hb, "match_poly_gg": match_poly_gg,
               "contracts": contracts}
    os.makedirs(IS_DIR, exist_ok=True)
    with open(os.path.join(IS_DIR, slug + ".json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    n_ev = sum(len(s) for s in sm_bundle["k_mid"].values()) + sum(len(s) for s in sm_bundle["p_mid"].values())
    hb = f"{match_poly_hb:.0%}" if match_poly_hb is not None else "n/a"
    print(f"  processed {match:<22} {n_ev:>9,} mids · {len(coint)}/{len(contracts)} cointegrated · "
          f"Poly info-share={hb} -> {slug}.json")
    return match


def _median(xs):
    xs = sorted(v for v in xs if v is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else round((xs[n // 2 - 1] + xs[n // 2]) / 2, 4)


def pool_from_archive() -> dict:
    matches, per_match, all_coint = [], [], []
    for path in sorted(glob.glob(os.path.join(IS_DIR, "*.json"))):
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict) or "contracts" not in d:
            continue
        coint = [c for c in d["contracts"] if c.get("cointegrated") and c.get("hasbrouck_a_mid") is not None]
        if not coint:
            continue
        matches.append(d["match"])
        all_coint.extend(coint)
        per_match.append({"match": d["match"], "n_contracts": d["n_contracts"], "n_cointegrated": len(coint),
                          "poly_hasbrouck_mid": d.get("match_poly_hasbrouck_mid"),
                          "poly_gg": d.get("match_poly_gg"),
                          "leader": "polymarket" if (d.get("match_poly_gg") or 0) > 0.5 else "kalshi"})

    # headline = median across MATCHES (each match contributes its own median; one liquid contract
    # can't dominate). Also report the pair-level distribution + identification width (Hasbrouck lo/hi).
    poly_hb = _median([m["poly_hasbrouck_mid"] for m in per_match])
    poly_gg = _median([m["poly_gg"] for m in per_match])
    leads = {"polymarket": sum(m["leader"] == "polymarket" for m in per_match),
             "kalshi": sum(m["leader"] == "kalshi" for m in per_match)}
    hb_lo = _median([c.get("hasbrouck_a_lo") for c in all_coint])
    hb_hi = _median([c.get("hasbrouck_a_hi") for c in all_coint])

    payload = {
        "n_matches": len(matches), "n_cointegrated_contracts": len(all_coint), "bin_ms": BIN_MS,
        "poly_infoshare_hasbrouck_mid": poly_hb,        # HEADLINE: Polymarket's % of price discovery
        "poly_infoshare_gg": poly_gg,                    # Gonzalo-Granger cross-check (ordering-free)
        "hasbrouck_mid_band": [hb_lo, hb_hi],            # median identification width across contracts
        "match_leader_counts": leads,
        "per_match": sorted(per_match, key=lambda m: -(m["poly_hasbrouck_mid"] or 0)),
        "note": "Hasbrouck (1995) information share + Gonzalo-Granger (1995) permanent-component share, "
                "on 1s last-price tape mids per matched contract, dropping non-cointegrated pairs (ADF "
                "p>=0.10 on the (1,-1) spread). >50% = that venue leads price discovery. The honest unit "
                "is the match: headline is the median across matches of each match's median contract "
                "share. Hasbrouck gives a lo/hi band per contract (Cholesky ordering); GG is unique. "
                "Computed on MID moves, so robust to the ~59% WS trade-direction problem (arXiv 2604.24366).",
        "significance_basis": "per-match shares; n_matches is the unit, not contracts or bins",
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.INFOSHARE = " + json.dumps(payload) + ";\n")
    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    with open(RESULTS, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"POOLED · {len(matches)} match(es) · {len(all_coint)} cointegrated contract(s)")
    if poly_hb is not None:
        print(f"  Polymarket info-share (Hasbrouck mid): {poly_hb:.1%}  "
              f"[band {hb_lo:.0%}-{hb_hi:.0%}]   GG: {poly_gg:.1%}")
        print(f"  match leader: Polymarket {leads['polymarket']} · Kalshi {leads['kalshi']}")
    else:
        print("  no cointegrated contracts yet — pool empty")
    print(f"wrote {os.path.relpath(OUT, ROOT)} + {os.path.relpath(RESULTS, ROOT)}")
    return payload


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="cross-venue information share (Hasbrouck/Gonzalo-Granger) on tape mids")
    ap.add_argument("--all", action="store_true", help="re-process every WC tape present")
    ap.add_argument("--pool-only", action="store_true", help="rebuild the pool from per-match JSONs; parse no tapes")
    args = ap.parse_args()
    os.makedirs(IS_DIR, exist_ok=True)
    if args.pool_only:
        pool_from_archive()
        return 0
    caps = wc_captures(DATA_DIR)
    done = lambda c: os.path.exists(os.path.join(IS_DIR, (c.split("-", 1)[1] if "-" in c else c) + ".json"))
    todo = caps if args.all else [c for c in caps if not done(c)]
    if todo:
        print(f"processing {len(todo)} tape(s) of {len(caps)} present:")
        for cap in todo:
            process_capture(cap)
    else:
        print(f"no new tapes ({len(caps)} present, all archived); re-pooling.")
    pool_from_archive()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
