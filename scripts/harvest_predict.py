#!/usr/bin/env python3
"""Can a follower know IN ADVANCE which matches hold a harvestable goal? (section 6.2)
    -> writeups/_harvest_predict_results.json

    python scripts/harvest_predict.py --check    # verify against the shipped artifact
    python scripts/harvest_predict.py --tracked  # restrict to git-tracked archives

WHY THIS EXISTS. Section 6.2 reports that harvestable goals cluster in a minority of matches
and then asserts that "a follower cannot know in advance which ones". That is the load-bearing
sentence turning a distributional result into a practical null, and it was an assertion. It is
testable on the archives we already ship, so it should be tested.

DESIGN. Label per match: does it contain at least one harvestable goal (pct_harvestable > 0)?
Predictors are restricted to what is knowable BEFORE kickoff, which is the whole point:

  fav_prob     the stronger side's pre-match win probability (docs/data/matches_v2.js)
  p_draw       pre-match draw probability
  closeness    -|p1 - p2|, higher for a more evenly matched fixture
  n_events     qualifying shocks in the match -- included as a DELIBERATE cheat (it is known
               only after the fact) to bound what any ex-ante feature could achieve

Scored by leave-one-out AUC, so no match contributes to the model that ranks it. A single split
would be noise at this n. The comparison that matters is ex-ante AUC against 0.5, and against
the cheating feature: if hindsight barely beats a coin flip, foresight cannot.

TWO HONEST LIMITS, BOTH STATED IN THE PAPER. First, the pre-match forecast ledger covers the
group stage, so the joined sample is the group-stage subset of the harvest ledger and the
knockout matches drop out. Second, and more important, the covariate a desk would actually
trade on -- pre-goal book depth on the follower venue -- does not survive anywhere in the
derived layer (the collection host was decommissioned). Match-strength probabilities are a weak
proxy for how deep a book will be. So this bounds predictability from public ex-ante
information, not from the full information set a live desk would hold, and a null here is
weaker evidence than a null with depth covariates would be. We do not claim otherwise.

Reads derived per-match archives only. Writes nothing under xresidual/.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import subprocess

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARV = os.path.join(ROOT, "viz", "market", "harvest")
FIXTURES = os.path.join(ROOT, "docs", "data", "matches_v2.js")
OUT = os.path.join(ROOT, "writeups", "_harvest_predict_results.json")

FEATURES = ["fav_prob", "p_draw", "closeness"]    # ex-ante only
CHEAT = "n_events"                                # known only after the fact; an upper bound


def _load_js(path):
    with open(path) as f:
        raw = f.read()
    m = re.search(r"=\s*(\{.*\})\s*;?\s*$", raw.strip(), re.S)
    return json.loads(m.group(1)) if m else {}


def _tracked_files():
    out = subprocess.run(["git", "-c", "core.quotepath=off", "ls-files", "-z",
                          "viz/market/harvest"], capture_output=True, cwd=ROOT)
    return [os.path.join(ROOT, f) for f in out.stdout.decode().split("\0") if f]


def _norm(s):
    return re.sub(r"[^a-z]", "", s.lower())


def load(tracked_only):
    """Join each harvest archive to its pre-match forecast. Unjoined matches are knockout
    fixtures, which the group-stage forecast ledger does not cover; they are counted and
    reported rather than quietly dropped."""
    fx = {}
    for r in (_load_js(FIXTURES).get("matches") or []):
        fx[frozenset((_norm(r["t1"]), _norm(r["t2"])))] = r
    files = _tracked_files() if tracked_only else sorted(glob.glob(os.path.join(HARV, "*.json")))
    rows, unmatched = [], 0
    for f in files:
        try:
            d = json.load(open(f))
        except Exception:  # noqa: BLE001
            continue
        a = d.get("all") or {}
        if a.get("pct_harvestable") is None or not a.get("n"):
            continue
        teams = [t.strip() for t in re.split(r"\s+vs\.?\s+", d.get("match", ""), maxsplit=1)]
        m = fx.get(frozenset(_norm(t) for t in teams)) if len(teams) == 2 else None
        if m is None:
            unmatched += 1
            continue
        p1, p2, pd = float(m["p1"]), float(m["p2"]), float(m["pd"])
        rows.append({
            "match": d["match"],
            "y": 1 if a["pct_harvestable"] > 0 else 0,
            "fav_prob": max(p1, p2),
            "p_draw": pd,
            "closeness": -abs(p1 - p2),
            "n_events": float(a["n"]),
        })
    return rows, unmatched


def _matrix(rows, feats):
    return (np.array([[r[k] for k in feats] for r in rows], dtype=float),
            np.array([r["y"] for r in rows], dtype=float))


def _fit_np(X, y, iters=25, ridge=1e-3):
    """Ridge-penalised logistic regression by IRLS (Newton) on standardized features.

    IRLS converges in a handful of Newton steps where gradient descent needs thousands, which
    matters because the permutation null refits this ~18,000 times. The small ridge term keeps
    the Hessian invertible when a leave-one-out fold separates -- at n=45 with three features
    that happens, and an unpenalised fit would diverge rather than fail loudly.
    """
    mu = X.mean(axis=0)
    sd = X.std(axis=0, ddof=1)
    sd[sd == 0] = 1.0
    Z = np.column_stack([np.ones(len(y)), (X - mu) / sd])   # intercept first
    beta = np.zeros(Z.shape[1])
    pen = ridge * np.eye(Z.shape[1])
    pen[0, 0] = 0.0                                          # never penalise the intercept
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(Z @ beta, -30, 30)))
        W = np.clip(p * (1 - p), 1e-6, None)
        grad = Z.T @ (y - p) - pen @ beta
        H = Z.T @ (Z * W[:, None]) + pen
        try:
            step = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        beta += step
        if np.max(np.abs(step)) < 1e-8:
            break
    return mu, sd, beta[1:], float(beta[0])


def _score_np(x, mu, sd, w, b):
    return float(((x - mu) / sd) @ w + b)


def _fit(rows, feats):
    """Convenience wrapper returning (scorer, weights-by-name) for the in-sample report."""
    X, y = _matrix(rows, feats)
    mu, sd, w, b = _fit_np(X, y)
    return (lambda r: _score_np(np.array([r[k] for k in feats], dtype=float), mu, sd, w, b),
            dict(zip(feats, w)))


def _auc(scored):
    """Mann-Whitney AUC with ties at 0.5. scored = [(score, y)]."""
    pos = [s for s, y in scored if y == 1]
    neg = [s for s, y in scored if y == 0]
    if not pos or not neg:
        return None
    wins = sum((1.0 if a > b else 0.5 if a == b else 0.0) for a in pos for b in neg)
    return wins / (len(pos) * len(neg))


def _loo_scores(X, y):
    """Leave-one-out: every row is ranked by a model that never saw it."""
    scored = []
    for i in range(len(y)):
        m = np.ones(len(y), dtype=bool)
        m[i] = False
        if len(set(y[m])) < 2:
            continue
        mu, sd, w, b = _fit_np(X[m], y[m])
        scored.append((_score_np(X[i], mu, sd, w, b), y[i]))
    return scored


def loo_auc(rows, feats):
    X, y = _matrix(rows, feats)
    scored = _loo_scores(X, y)
    return _auc(scored), len(scored), scored


def loo_perm_p(rows, feats, n_perm=400, seed=20260702):
    """Permutation null for the LOO AUC ITSELF.

    Leave-one-out AUC is downward-biased at small n -- removing a positive example makes the
    refit less likely to rank it highly -- so an observed AUC below 0.5 is not evidence of an
    inverted signal, and comparing it to 0.5 would be comparing an estimate to the wrong null.
    Shuffling the labels and re-running the identical LOO procedure gives the null distribution
    of this estimator on this sample, bias included. The two-sided p-value is computed against
    |AUC - median(null)| so it tests departure from the estimator's own centre, not from 0.5.
    """
    X, y = _matrix(rows, feats)
    obs = _auc(_loo_scores(X, y))
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(n_perm):
        a = _auc(_loo_scores(X, rng.permutation(y)))
        if a is not None:
            null.append(a)
    centre = float(np.median(null))
    extreme = sum(1 for a in null if abs(a - centre) >= abs(obs - centre))
    return {
        "observed_auc": round(obs, 4),
        "null_median_auc": round(centre, 4),
        "null_ci95": [round(float(np.percentile(null, 2.5)), 4),
                      round(float(np.percentile(null, 97.5)), 4)],
        "n_permutations": len(null),
        "p_two_sided": round((extreme + 1) / (len(null) + 1), 4),
    }


def auc_ci(scored, seed=20260702, n_boot=10_000):
    """Bootstrap interval on the out-of-sample AUC, resampling MATCHES. An AUC point estimate
    at this n says very little on its own; whether the interval covers 0.5 is the claim."""
    import random
    rng = random.Random(seed)
    n = len(scored)
    vals = []
    for _ in range(n_boot):
        samp = [scored[rng.randrange(n)] for _ in range(n)]
        a = _auc(samp)
        if a is not None:
            vals.append(a)
    vals.sort()
    lo = vals[int(0.025 * len(vals))]
    hi = vals[int(0.975 * len(vals)) - 1]
    return [round(lo, 4), round(hi, 4), bool(lo <= 0.5 <= hi)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--tracked", action="store_true")
    args = ap.parse_args()

    rows, unmatched = load(args.tracked)
    if len(rows) < 10:
        print(f"  !! only {len(rows)} usable matches — not enough to score")
        return 1
    n_pos = sum(r["y"] for r in rows)
    print(f"  matches: {len(rows)}  ({n_pos} with >=1 harvestable goal, "
          f"{len(rows) - n_pos} without; {unmatched} unjoined knockout fixtures)")

    ex_ante, n_ex, sc_ex = loo_auc(rows, FEATURES)
    cheat, n_ch, sc_ch = loo_auc(rows, FEATURES + [CHEAT])
    ci_ex, ci_ch = auc_ci(sc_ex), auc_ci(sc_ch)
    perm = loo_perm_p(rows, FEATURES)
    _, w = _fit(rows, FEATURES)

    payload = {
        "n_matches": len(rows),
        "n_with_harvestable": int(n_pos),
        "base_rate": round(n_pos / len(rows), 4),
        "features_ex_ante": FEATURES,
        "loo_auc_ex_ante": round(ex_ante, 4) if ex_ante is not None else None,
        "loo_auc_ex_ante_ci95": ci_ex[:2],
        # NOT a test: 0.5 is the wrong null for a LOO AUC at this n (see
        # permutation_null_ex_ante, whose own centre is well below 0.5). Kept only so a
        # reader can see the naive comparison and why it misleads.
        "loo_auc_ex_ante_ci95_covers_half_naive": ci_ex[2],
        "loo_auc_with_hindsight_feature": round(cheat, 4) if cheat is not None else None,
        "loo_auc_with_hindsight_ci95": ci_ch[:2],
        "loo_auc_with_hindsight_ci95_covers_half_naive": ci_ch[2],
        "permutation_null_ex_ante": perm,
        "n_scored": n_ex,
        "in_sample_weights": {k: round(v, 4) for k, v in w.items()},
        "note": ("leave-one-out AUC for predicting which matches contain a harvestable goal. "
                 "Ex-ante features are knowable before kickoff; the hindsight variant adds the "
                 "match's realised event count as an upper bound on what any feature set could "
                 "reach. Pre-goal book depth, the covariate a desk would actually use, does not "
                 "survive in the derived layer, so this bounds predictability from public "
                 "ex-ante information only."),
    }
    print(f"  LOO AUC, ex-ante features : {payload['loo_auc_ex_ante']}  (n scored {n_ex})")
    print(f"  LOO AUC, + hindsight feat : {payload['loo_auc_with_hindsight_feature']}")
    print(f"  in-sample weights         : {payload['in_sample_weights']}")
    pm = payload["permutation_null_ex_ante"]
    print(f"  permutation null (LOO)    : median {pm['null_median_auc']} "
          f"CI {pm['null_ci95']} -> p={pm['p_two_sided']}")

    if args.check:
        shipped = json.load(open(OUT))
        bad = [k for k, v in payload.items() if k != "note" and shipped.get(k) != v]
        for k in bad:
            print(f"  !! {k}: shipped={shipped.get(k)} fresh={payload[k]}")
        print("  " + ("CHECK CLEAN — regenerates the shipped artifact exactly"
                      if not bad else f"{len(bad)} FIELD(S) DIFFER"))
        return 1 if bad else 0

    with open(OUT, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"  wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
