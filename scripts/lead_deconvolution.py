#!/usr/bin/env python3
"""Recover the distribution of TRUE cross-venue leads from the published, bias-contaminated ones.

The lead-lag estimator is biased because Kalshi's mid is seen at most once a second while
Polymarket's is seen about every 10 ms (see sampling_bias_check.py). The bias is not a constant, so it
cannot simply be subtracted. But the estimator's RESPONSE to a known true lead is measurable: shift a
real Polymarket path by a known lag L, observe it at 1 Hz, and record what the estimator reports. Over a
grid of L that gives a response matrix R (columns: measured-lag histograms). The published histogram y
is then y ~= R w, and w -- the distribution of true leads -- follows by non-negative least squares.

Design choices, several of them corrections to a first version that an independent review flagged:
  * Bins are centred on the estimator's 200 ms grid and symmetric about zero, so no bin is empty and
    -200 and +200 are treated alike.
  * The lag grid runs to +/-7 s: measured lags reach +/-8 s, and a grid that stopped at 3 s could not
    explain the tails at all (chi-square 133 on 12 bins).
  * A NOISE column (flat across all lags) absorbs measured lags that no clean response produces --
    locks onto the wrong co-movement, second goals inside the window. Its mass is reported, not hidden.
  * The response is built from 33 windows, one per match: that match's largest gated event. The 427
    published events include smaller shocks and have heavier tails. The noise column partly absorbs
    that; the fit statistic says how well.
  * Uncertainty comes from a bootstrap that resamples MATCHES (events cluster within matches, and a
    goal appears once per contract) and resamples the WINDOWS behind R, so response uncertainty counts.
  * Self-tests are held out: R is built from half the windows and the known truths are drawn from the
    other half.

Inputs: the committed per-event leads in writeups/_leadlag_results.json, plus the per-tick windows in
viz/market/leadlag/*.js (withheld under the venues' data terms). The artifact holds aggregates only.

    python scripts/lead_deconvolution.py
"""
from __future__ import annotations

import bisect
import glob
import json
import os
import random
import sys

import numpy as np
from scipy.optimize import nnls

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import ws_events as we  # noqa: E402

OUT = os.path.join(ROOT, "writeups", "_lead_deconvolution_results.json")
LAGS = [-7000, -5000, -3000, -2000, -1500, -1000, -600, -300, 0, 300, 600, 1000, 1500, 2000, 3000, 5000, 7000]
EDGES = np.array([-8100, -5100, -3100, -2100, -1300, -700, -300, -100, 100, 300, 700, 1300, 2100, 3100, 5100, 8100])
PHASES = 40
N_BOOT = 300
SEED = 20260919


def hold(src, stamps):
    ts = [x[0] for x in src]
    out = []
    for t in stamps:
        i = bisect.bisect_right(ts, t) - 1
        if i >= 0:
            out.append((t, src[i][1]))
    return out


def gated(k, p):
    ll = we.lead_lag_ms(k, p, bin_ms=200, max_lag_ms=20000)
    if not ll or ll["best_corr"] < 0.5 or abs(ll["best_lag_ms"]) > 8000:
        return None
    return ll["best_lag_ms"]


def load_windows():
    wins = []
    for f in sorted(glob.glob(os.path.join(ROOT, "viz", "market", "leadlag", "*.js"))):
        s = open(f, encoding="utf-8").read()
        try:
            w = json.loads(s[s.index("{"):].rstrip().rstrip(";"))
        except ValueError:
            continue
        p = [(int(round(t * 1000)), v) for t, v in w["data"]["poly"]]
        if len(p) > 50 and len(w["data"]["kalshi"]) > 10:
            wins.append(p)
    return wins


def responses(wins, rng):
    """raw[j][i] = measured lags for true lag LAGS[j] on window i, over PHASES random 1 Hz phases."""
    raw = [[[] for _ in wins] for _ in LAGS]
    for j, L in enumerate(LAGS):
        for i, p in enumerate(wins):
            shifted = [(t + L, v) for t, v in p]
            lo, hi = p[0][0], p[-1][0]
            for _ in range(PHASES):
                ph = rng.randrange(1000)
                r = gated(hold(shifted, list(range(lo - (lo % 1000) + ph, hi, 1000))), p)
                if r is not None:
                    raw[j][i].append(r)
        print(f"  response built for true lag {L:+6d} ms", flush=True)
    return raw


def matrix(raw, idx):
    """Response matrix from windows `idx`, plus a flat noise column over the lag grid."""
    cols = []
    for j in range(len(LAGS)):
        vals = [x for i in idx for x in raw[j][i]]
        h, _ = np.histogram(vals, bins=EDGES)
        cols.append(h / max(1, len(vals)))
    grid = np.arange(-8000, 8001, 200)                      # every value the estimator can report
    noise, _ = np.histogram(grid, bins=EDGES)
    cols.append(noise / noise.sum())
    return np.column_stack(cols)


def fit(R, sample):
    y, _ = np.histogram(sample, bins=EDGES)
    n = len(sample)
    w, _ = nnls(R, y / max(1, n))
    w = w / w.sum() if w.sum() > 0 else w
    exp = n * (R @ w)
    ok = exp > 0
    chi2 = float(((y[ok] - exp[ok]) ** 2 / exp[ok]).sum())
    return w, chi2


def masses(w):
    lead = w[:-1]
    k = sum(x for L, x in zip(LAGS, lead) if L < 0)
    z = sum(x for L, x in zip(LAGS, lead) if L == 0)
    p = sum(x for L, x in zip(LAGS, lead) if L > 0)
    noise = float(w[-1])
    tot = k + z + p
    share = (lambda v: v / tot) if tot > 0 else (lambda v: 0.0)
    return {"kalshi": share(k), "none": share(z), "poly": share(p), "noise_mass": noise}


def published():
    d = json.load(open(os.path.join(ROOT, "writeups", "_leadlag_results.json")))
    by_match = {}
    for pr in d["pairs"]:
        for e in pr.get("events", []):
            ll = e.get("lead")
            if ll and isinstance(ll.get("best_lag_ms"), (int, float)):
                by_match.setdefault(pr.get("match", pr.get("label")), []).append(ll["best_lag_ms"])
    return by_match


def main() -> int:
    rng = random.Random(SEED)
    nrng = np.random.default_rng(SEED)
    wins = load_windows()
    if not wins:
        print("no per-tick lead-lag windows (withheld inputs) - nothing to compute")
        return 0
    print(f"{len(wins)} windows; building responses", flush=True)
    raw = responses(wins, rng)
    allidx = list(range(len(wins)))
    R = matrix(raw, allidx)

    # Held-out self-test: R from one half of the windows, known truths drawn from the other half.
    half = allidx[:]
    rng.shuffle(half)
    a, b = half[: len(half) // 2], half[len(half) // 2:]
    Ra = matrix(raw, a)
    selftest = []
    for name, truth in [("all 0 (no lead)", {0: 1.0}), ("all +600 (Poly first)", {600: 1.0}),
                        ("all -600 (Kalshi first)", {-600: 1.0}), ("all +300", {300: 1.0}),
                        ("all -300", {-300: 1.0}), ("all -1000", {-1000: 1.0}),
                        ("20% -600 / 60% 0 / 20% +600", {-600: .2, 0: .6, 600: .2})]:
        samp = []
        for L, frac in truth.items():
            pool = [x for i in b for x in raw[LAGS.index(L)][i]]
            samp += list(nrng.choice(pool, size=int(round(427 * frac)), replace=True))
        m = masses(fit(Ra, samp)[0])
        tk = sum(f for L, f in truth.items() if L < 0)
        tz = sum(f for L, f in truth.items() if L == 0)
        tp = sum(f for L, f in truth.items() if L > 0)
        selftest.append({"truth": name, "truth_kzp": [tk, tz, tp],
                         "recovered_kzp": [round(m["kalshi"], 3), round(m["none"], 3), round(m["poly"], 3)],
                         "recovered_noise": round(m["noise_mass"], 3)})
        print(f"  self-test {name:<30} truth K/0/P {tk:.0%}/{tz:.0%}/{tp:.0%}  recovered "
              f"{m['kalshi']:.0%}/{m['none']:.0%}/{m['poly']:.0%}  (noise {m['noise_mass']:.0%})", flush=True)

    bym = published()
    pub = [x for v in bym.values() for x in v]
    w, chi2 = fit(R, pub)
    m = masses(w)
    dof = len(EDGES) - 1 - int((w > 1e-9).sum())
    print(f"\n{len(pub)} published events, {len(bym)} matches: Kalshi-first {m['kalshi']:.1%} | none "
          f"{m['none']:.1%} | Polymarket-first {m['poly']:.1%}  (noise mass {m['noise_mass']:.1%}; "
          f"chi2 {chi2:.1f} on ~{dof} dof)", flush=True)

    keys = list(bym)
    boot = []
    for _ in range(N_BOOT):
        ms = [keys[i] for i in nrng.integers(0, len(keys), len(keys))]          # resample matches
        samp = [x for k in ms for x in bym[k]]
        wi = [allidx[i] for i in nrng.integers(0, len(allidx), len(allidx))]  # resample response windows
        mb = masses(fit(matrix(raw, wi), samp)[0])
        boot.append([mb["kalshi"], mb["none"], mb["poly"], mb["noise_mass"]])
    boot = np.array(boot)
    ci = {lab: [float(np.percentile(boot[:, i], 2.5)), float(np.percentile(boot[:, i], 97.5))]
          for i, lab in enumerate(["kalshi", "none", "poly", "noise_mass"])}
    for lab, (lo, hi) in ci.items():
        print(f"  {lab:<11} 95% [{lo:.1%}, {hi:.1%}]")

    json.dump({
        "n_published": len(pub), "n_matches": len(bym), "n_windows": len(wins),
        "lags_ms": LAGS, "bin_edges_ms": EDGES.tolist(), "phases_per_window": PHASES,
        "weights": [float(x) for x in w], "weight_names": [str(L) for L in LAGS] + ["noise"],
        "masses": {k: float(v) for k, v in m.items()},
        "bootstrap95": ci, "bootstrap": "resamples matches AND response windows, %d replicates" % N_BOOT,
        "fit_chi2": chi2, "fit_bins": len(EDGES) - 1,
        "self_test_held_out": selftest,
        "note": ("Masses kalshi/none/poly are shares of the NON-noise mass. The response windows are each "
                 "match's largest gated event, so the fit should be read with its chi-square: a poor fit "
                 "means the split is indicative only."),
        "seed": SEED,
    }, open(OUT, "w"), indent=1)
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
