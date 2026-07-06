#!/usr/bin/env python3
"""Short-horizon return prediction from order-book state — the ML extension of the OFI work.

xResidual's OFI study regresses next-second mid returns on order-flow imbalance *linearly*. The
microstructure-ML literature (LOB transformers, deep LOB forecasting) shows a fuller feature set —
OFI, spread, depth, imbalance, microprice deviation, lagged returns — carries real, if small,
short-horizon predictability, and that nonlinearity/interactions matter. This asks the honest version
of that on our own tapes: **does gradient boosting on the full book state beat the linear OFI baseline
at predicting the next 1s mid move, out of sample?** Fork-forward; imports the frozen tape layer read-only.

Method: reuse the streaming top-of-book reconstruction (`stream_micro` / `ws_book`), build per-1s-bin
features per contract per venue, standardize per contract (so venues/contracts pool), target = the NEXT
bin's mid return. Split by MATCH (train on earlier matches, test on later) so there's no temporal leak.
Score test R^2 and directional accuracy vs (a) predict-zero, (b) linear OFI-only, (c) linear all-features.

    python scripts/ml_microstructure.py            # -> writeups/_ml_micro_results.json
"""
from __future__ import annotations
import glob
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import ws_events as we          # noqa: E402  frozen
import ws_book as wb                            # noqa: E402
import stream_micro as sm                       # noqa: E402

DATA_DIR = os.path.join(ROOT, "logger", "data")
BIN_MS = 1000
MAX_GAP_MS = 10000
FEATS = ["ofi", "ofi_l1", "spread", "depth", "imbalance", "micro_mid", "ret0", "ret1", "ret2", "is_poly"]


def _z(a: np.ndarray) -> np.ndarray:
    m = np.nanmean(a); s = np.nanstd(a)
    return (a - m) / s if s and s > 0 else a * 0.0


def _series(tob, key):
    return [(r["t"], r[key]) for r in tob]


def _feats_from_tob(tob, is_poly: int):
    """Per-1s-bin feature rows + next-bin-return target for one contract on one venue."""
    if len(tob) < 60:
        return None
    wb.add_prices(tob)                                   # adds mid, micro
    t0, t1 = tob[0]["t"], tob[-1]["t"]
    n = max(1, (t1 - t0) // BIN_MS + 1)
    if n < 40:
        return None
    grid = lambda s: we._grid(s, t0, t1, BIN_MS, max_gap_ms=MAX_GAP_MS)
    mid = grid(_series(tob, "mid"))
    spread = grid([(r["t"], r["ask"] - r["bid"]) for r in tob])
    depth = grid([(r["t"], r["bid_sz"] + r["ask_sz"]) for r in tob])
    imb = grid([(r["t"], ((r["bid_sz"] - r["ask_sz"]) / d if (d := r["bid_sz"] + r["ask_sz"]) > 0 else 0.0)) for r in tob])
    micro_mid = grid([(r["t"], r["micro"] - r["mid"]) for r in tob])
    ofi = np.full(n, np.nan)
    for t, e in wb.ofi_increments(tob):
        if t0 <= t <= t1:
            i = min(n - 1, (t - t0) // BIN_MS)
            ofi[i] = (0.0 if np.isnan(ofi[i]) else ofi[i]) + e
    ret = np.full(n, np.nan); ret[1:] = np.diff(mid)
    # standardize per contract (scale-normalize so contracts/venues pool; each contract uses its own
    # moments only, so no cross-contract leak across the train/test match split)
    ofiz, retz, sprz, depz, mmz = _z(ofi), _z(ret), _z(spread), _z(depth), _z(micro_mid)
    rows, ys, yraw = [], [], []
    for i in range(3, n - 1):
        y = retz[i + 1]                                   # NEXT bin's (standardized) return
        if np.isnan(y) or np.isnan(retz[i]) or np.isnan(sprz[i]):
            continue                                      # need a live book + defined target
        rows.append([ofiz[i], ofiz[i - 1], sprz[i], depz[i], imb[i], mmz[i],
                     retz[i], retz[i - 1], retz[i - 2], float(is_poly)])
        ys.append(y)
        yraw.append(ret[i + 1])                           # RAW next-bin return (for un-standardized direction)
    if len(rows) < 50:
        return None
    return np.array(rows, dtype=float), np.array(ys, dtype=float), np.array(yraw, dtype=float)


def _cap_keys():
    keys = []
    for p in sorted(glob.glob(os.path.join(DATA_DIR, "ws-events-*.jsonl"))):
        b = os.path.basename(p)
        keys.append(b[len("ws-events-"):-len(".jsonl")])
    return keys


def build():
    X_by_match, y_by_match, yr_by_match, order = {}, {}, {}, []
    for cap in _cap_keys():
        path = os.path.join(DATA_DIR, f"ws-events-{cap}.jsonl")
        pairs = we.load_pairs(DATA_DIR, capture=cap) if hasattr(we, "load_pairs") else _load_pairs(cap)
        if not pairs:
            continue
        try:
            b = sm.stream_all(path, pairs)
        except Exception as e:
            print(f"  {cap}: stream failed ({str(e)[:50]})"); continue
        Xs, ys, yrs = [], [], []
        for pr in pairs:
            for kind, tobmap, cid in (("k", b["k_tob"], pr.get("kalshi")), ("p", b["p_tob"], pr.get("poly"))):
                if not cid or cid not in tobmap:
                    continue
                out = _feats_from_tob(tobmap[cid], is_poly=int(kind == "p"))
                if out:
                    Xs.append(out[0]); ys.append(out[1]); yrs.append(out[2])
        if Xs:
            X_by_match[cap] = np.vstack(Xs); y_by_match[cap] = np.concatenate(ys)
            yr_by_match[cap] = np.concatenate(yrs); order.append(cap)
            print(f"  {cap}: {len(y_by_match[cap])} bin-rows")
    # cache so validation doesn't re-stream the tapes
    np.savez(os.path.join(ROOT, "writeups", "_ml_micro_cache.npz"),
             **{f"X__{c}": X_by_match[c] for c in order},
             **{f"y__{c}": y_by_match[c] for c in order},
             **{f"r__{c}": yr_by_match[c] for c in order})
    return X_by_match, y_by_match, yr_by_match, sorted(order)   # sorted() = chronological (keys start with ts)


def _load_pairs(cap):
    p = os.path.join(DATA_DIR, f"ws-pairs-{cap}.jsonl")
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p) if l.strip()]


def _gbm():
    from sklearn.ensemble import HistGradientBoostingRegressor
    return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.04, max_leaf_nodes=15,
                                         min_samples_leaf=200, l2_regularization=1.0, random_state=0)


def _dacc(pred, y):
    m = np.abs(y) > 1e-9
    return float(np.mean(np.sign(pred[m]) == np.sign(y[m]))) if m.any() else float("nan")


def main():
    from sklearn.linear_model import LinearRegression
    Xm, ym, yrm, order = build()
    if len(order) < 4:
        print("too few matches with usable tapes"); return 1
    k = max(1, int(round(len(order) * 0.7)))
    tr, te = order[:k], order[k:]
    Xtr = np.vstack([Xm[c] for c in tr]); ytr = np.concatenate([ym[c] for c in tr])
    Xte = np.vstack([Xm[c] for c in te]); yte = np.concatenate([ym[c] for c in te])
    yte_raw = np.concatenate([yrm[c] for c in te])
    def r2(pred): return 1 - np.sum((yte - pred) ** 2) / np.sum((yte - yte.mean()) ** 2)

    ofi_only = LinearRegression().fit(np.nan_to_num(Xtr[:, :1]), ytr).predict(np.nan_to_num(Xte[:, :1]))
    lin_all = LinearRegression().fit(np.nan_to_num(Xtr), ytr).predict(np.nan_to_num(Xte))
    gbm = _gbm().fit(Xtr, ytr); gp = gbm.predict(Xte)

    print("\n" + "=" * 64)
    print("ML MICROSTRUCTURE — result + VALIDATION (attacking it)")
    print(f"  {len(order)} matches ({len(tr)} train / {len(te)} test), {len(ytr):,}/{len(yte):,} rows")
    print("-" * 64)
    print("  base split OOS:")
    print(f"    linear OFI-only  R2 {r2(ofi_only):+.4f}  dir {_dacc(ofi_only, yte):.1%}")
    print(f"    linear all       R2 {r2(lin_all):+.4f}  dir {_dacc(lin_all, yte):.1%}")
    print(f"    GBM all          R2 {r2(gp):+.4f}  dir {_dacc(gp, yte):.1%} (std) / {_dacc(gp, yte_raw):.1%} (RAW up-down)")

    # (1) per-test-match — is it robust or one lucky match?
    print("\n  (1) per-test-match dir-acc:")
    for c in te:
        p = gbm.predict(Xm[c])
        print(f"      {c[-22:]:22} std {_dacc(p, ym[c]):.1%}  raw {_dacc(p, yrm[c]):.1%}  (n={len(ym[c]):,})")

    # (2) permutation-null: shuffle train labels -> must collapse to ~0 / ~50% (else leakage)
    rng = np.random.default_rng(1); yp = ytr.copy(); rng.shuffle(yp)
    pn = _gbm().fit(Xtr, yp).predict(Xte)
    print("\n  (2) permutation null (shuffled train y):")
    print(f"      R2 {r2(pn):+.4f}  dir {_dacc(pn, yte):.1%}   [clean if ~0.000 / ~50%]")

    # (3) leave-one-match-out: does the signal generalize across ALL matches?
    accs, raws = [], []
    for c in order:
        rest = [d for d in order if d != c]
        Xr = np.vstack([Xm[d] for d in rest]); yr = np.concatenate([ym[d] for d in rest])
        p = _gbm().fit(Xr, yr).predict(Xm[c])
        accs.append(_dacc(p, ym[c])); raws.append(_dacc(p, yrm[c]))
    accs, raws = np.array(accs), np.array(raws)
    print(f"\n  (3) leave-one-match-out ({len(order)} folds):")
    print(f"      std dir  mean {accs.mean():.1%}  range [{accs.min():.1%}, {accs.max():.1%}]  "
          f"{int((accs > 0.5).sum())}/{len(accs)} > 50%")
    print(f"      raw dir  mean {raws.mean():.1%}  {int((raws > 0.5).sum())}/{len(raws)} > 50%")

    # null is clean if permuting the target collapses R^2 to ~0 AND direction to ~50% (either side)
    clean = abs(r2(pn)) < 0.002 and abs(_dacc(pn, yte) - 0.5) < 0.035
    robust = accs.mean() > 0.53 and (accs > 0.5).mean() >= 0.8
    verdict = "LEAKAGE?" if not clean else ("HOLDS" if robust else "FRAGILE (real-but-weak, sample-thin)")
    print("\n  VERDICT:", verdict,
          f"— null {'clean' if clean else 'DIRTY'}, LOMO {'robust' if robust else 'not robust'}")
    print("=" * 64)

    json.dump({"n_matches": len(order), "base_gbm_r2": float(r2(gp)),
               "base_gbm_dir_std": _dacc(gp, yte), "base_gbm_dir_raw": _dacc(gp, yte_raw),
               "null_r2": float(r2(pn)), "null_dir": _dacc(pn, yte),
               "lomo_dir_mean": float(accs.mean()), "lomo_dir_min": float(accs.min()),
               "lomo_dir_max": float(accs.max()), "lomo_frac_gt50": float((accs > 0.5).mean()),
               "lomo_raw_mean": float(raws.mean()), "verdict": verdict},
              open(os.path.join(ROOT, "writeups", "_ml_micro_results.json"), "w"), indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
