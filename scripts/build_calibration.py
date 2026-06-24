#!/usr/bin/env python3
"""Are the pre-committed forecasts calibrated? CORP reliability + Brier decomposition.
    -> viz/model/_calibration.js + writeups/_calibration_results.json

The project's thesis is calibration, and the pre-registration is the credibility anchor; this grades
that anchor properly. The model's home/draw/away probabilities are committed before kickoff
(paper/match_forecasts*.jsonl, an append-only ledger that can't be edited), then scored against what
actually happened. We report, pooling the three outcome classes one-vs-rest:

  - the multiclass Brier score (mean squared error of the probability vector), with the no-skill
    'uncertainty' baseline (always forecast the base rates) for context;
  - the Murphy decomposition  Brier = reliability - resolution + uncertainty  (reliability is the
    calibration error, lower is better; resolution is the skill, higher is better);
  - a reliability curve: forecast probability vs observed frequency, in deciles with bin counts, plus
    the CORP/PAV isotonic fit (Dimitriadis, Gneiting & Jordan 2021) which is the modern, bin-free read.

v1 vs v2 vs v3 compares the draw-calibration fixes (v3 = v2 + the format-conditional draw lift). Honest
on sample size: this is one group stage, ~45 games x 3 classes. Fork-forward; touches nothing under
xresidual/.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import wc2026_teams as W  # noqa: E402
from xresidual.calibration import calibration_regression  # noqa: E402  P1 binds the slope to this

LEDGERS = {"v1": "paper/match_forecasts.jsonl", "v2": "paper/match_forecasts_v2.jsonl",
           "v3": "paper/match_forecasts_v3.jsonl"}
MATCHES = os.path.join(ROOT, "docs", "data", "matches.js")
SNAP = os.path.join(ROOT, "logger", "data")
MKT_CACHE = os.path.join(ROOT, "data", "cache", "market_closing_h2h.json")
OUT = os.path.join(ROOT, "viz", "model", "_calibration.js")
RESULTS = os.path.join(ROOT, "writeups", "_calibration_results.json")


def load_market_closing(force: bool = False) -> dict:
    """Per-game CLOSING market h2h consensus. Streams the (large) oddsapi snapshot logs once and
    caches: each bookmaker's latest devigged mid before kickoff, averaged across books, renormalized
    to sum 1. Keyed by (date, frozenset{canon(home),canon(away)}) -> {canon(team):p, 'draw':p}."""
    snaps = glob.glob(os.path.join(SNAP, "snapshots-*.jsonl"))
    cache_fresh = (os.path.exists(MKT_CACHE) and snaps
                   and os.path.getmtime(MKT_CACHE) >= max(os.path.getmtime(s) for s in snaps))
    if cache_fresh and not force:                        # re-extract only when newer snapshots arrive
        raw = json.load(open(MKT_CACHE))
        return {frozenset(r[0]): r[1] for r in raw}
    best = {}                                            # (match,outcome,book) -> (ts, mid, commence)
    for fp in sorted(glob.glob(os.path.join(SNAP, "snapshots-*.jsonl"))):
        for line in open(fp):
            try:
                r = json.loads(line)
            except Exception:
                continue
            e = r.get("extra") or {}
            if r.get("venue") != "oddsapi" or e.get("market_type") != "h2h":
                continue
            m, o, mid, ts, ct = (r.get("market_label"), r.get("outcome"), r.get("mid"),
                                 r.get("ts_utc"), e.get("commence_time"))
            if not (m and o and mid and ts and ct) or ts > ct:   # pre-kickoff only
                continue
            k = (m, o, e.get("bookmaker"))
            if k not in best or ts > best[k][0]:
                best[k] = (ts, mid, ct)
    agg = collections.defaultdict(lambda: collections.defaultdict(list)); comm = {}
    for (m, o, _bk), (ts, mid, ct) in best.items():
        agg[m][o].append(mid); comm[m] = ct
    out = {}
    for m, od in agg.items():
        if " vs " not in m:
            continue
        home, away = [s.strip() for s in m.split(" vs ", 1)]
        cons = {o: sum(v) / len(v) for o, v in od.items()}
        ph, pd_, pa = cons.get(home), cons.get("Draw"), cons.get(away)
        if None in (ph, pd_, pa):
            continue
        s = ph + pd_ + pa
        key = frozenset({W.canonical(home), W.canonical(away)})       # date-agnostic: each pair plays once
        out[key] = {W.canonical(home): ph / s, "draw": pd_ / s, W.canonical(away): pa / s}
    os.makedirs(os.path.dirname(MKT_CACHE), exist_ok=True)
    json.dump([[sorted(k), v] for k, v in out.items()], open(MKT_CACHE, "w"))
    return out


def load_outcomes() -> dict:
    """key (date|t1|t2) -> outcome index 0=home,1=draw,2=away, for PLAYED games only."""
    s = open(MATCHES).read()
    d = json.loads(s.split("=", 1)[1].rstrip().rstrip(";"))
    rows = d if isinstance(d, list) else next(v for v in d.values() if isinstance(v, list))
    out = {}
    for r in rows:
        if not r.get("played"):
            continue
        res = r.get("result")
        oi = {"t1": 0, "draw": 1, "d": 1, "t2": 2}.get(res)
        if oi is None:
            continue
        out[f"{r['date']}|{r['t1']}|{r['t2']}"] = oi
    return out


def _pav(x, y, w):
    """Pool-adjacent-violators isotonic fit of y on x (weighted) -> monotone fitted values (CORP)."""
    order = np.argsort(x, kind="mergesort")
    y, w = y[order].astype(float), w[order].astype(float)
    val, wt, idx = list(y), list(w), [[i] for i in range(len(y))]
    i = 0
    while i < len(val) - 1:
        if val[i] > val[i + 1] + 1e-12:                     # violation -> pool
            nw = wt[i] + wt[i + 1]
            nv = (val[i] * wt[i] + val[i + 1] * wt[i + 1]) / nw
            val[i:i + 2] = [nv]; wt[i:i + 2] = [nw]; idx[i:i + 2] = [idx[i] + idx[i + 1]]
            i = max(i - 1, 0)
        else:
            i += 1
    fit = np.empty(len(y))
    for v, ii in zip(val, idx):
        for j in ii:
            fit[j] = v
    inv = np.empty(len(y), int); inv[np.arange(len(y))] = order
    return fit[np.argsort(order)]                           # back to input order


def score(forecasts: dict, outcomes: dict) -> dict | None:
    """forecasts: key -> (p_home, p_draw, p_away). Returns calibration metrics over played games."""
    P, O = [], []
    for k, p in forecasts.items():
        if k in outcomes:
            P.append(p); O.append(outcomes[k])
    if len(P) < 5:
        return None
    P = np.array(P, float); O = np.array(O, int)
    n = len(P)
    onehot = np.eye(3)[O]
    brier = float(np.mean(np.sum((P - onehot) ** 2, axis=1)))          # multiclass Brier
    base = onehot.mean(0)                                              # climatology (base rates)
    brier_base = float(np.mean(np.sum((base[None, :] - onehot) ** 2, axis=1)))

    # pool the three classes one-vs-rest for a single reliability read
    f = P.reshape(-1)                                                  # forecast probs
    o = onehot.reshape(-1)                                             # binary outcomes
    obar = o.mean()
    # Murphy decomposition via deciles
    bins = np.linspace(0, 1, 11)
    bi = np.clip(np.digitize(f, bins) - 1, 0, 9)
    rel = res = 0.0; curve = []
    for b in range(10):
        m = bi == b
        if not m.any():
            continue
        fb, ob, nb = f[m].mean(), o[m].mean(), int(m.sum())
        rel += nb * (fb - ob) ** 2
        res += nb * (ob - obar) ** 2
        curve.append({"f": round(float(fb), 3), "o": round(float(ob), 3), "n": nb})
    N = len(f)
    reliability, resolution = rel / N, res / N
    uncertainty = float(obar * (1 - obar))
    # CORP/PAV calibration error (bin-free): mean |fit - forecast|
    fit = _pav(f, o, np.ones_like(f))
    corp_mce = float(np.mean(np.abs(fit - f)))
    # P1 calibration-regression slope b (logit fit, b=1 perfect): bound to calibration.calibration_regression,
    # on the same pooled one-vs-rest (forecast, outcome) pairs. P1 PASS needs b in [0.70, 1.30].
    a, b = calibration_regression(f, o)
    return {"n_games": n, "brier": round(brier, 4), "brier_baseline": round(brier_base, 4),
            "skill_vs_baseline_pct": round((1 - brier / brier_base) * 100, 1),
            "reliability": round(reliability, 4), "resolution": round(resolution, 4),
            "uncertainty": round(uncertainty, 4), "corp_mce": round(corp_mce, 4),
            "slope": round(float(b), 4), "intercept": round(float(a), 4),
            "base_rates": {"home": round(float(base[0]), 3), "draw": round(float(base[1]), 3),
                           "away": round(float(base[2]), 3)},
            "reliability_curve": curve}


def main() -> int:
    outcomes = load_outcomes()
    versions = {}
    for v, path in LEDGERS.items():
        p = os.path.join(ROOT, path)
        if not os.path.exists(p):
            continue
        fc = {}
        for line in open(p):
            r = json.loads(line)
            fc[f"{r['date']}|{r['t1']}|{r['t2']}"] = (r["p1"], r["pd"], r["p2"])
        s = score(fc, outcomes)
        if s:
            versions[v] = s

    # the MARKET closing line — the project's actual thesis: are the prediction markets calibrated?
    try:
        mkt = load_market_closing()
        mkt_fc = {}
        for key in outcomes:
            _date, t1, t2 = key.split("|")
            rec = mkt.get(frozenset({W.canonical(t1), W.canonical(t2)}))
            if rec:
                mkt_fc[key] = (rec[W.canonical(t1)], rec["draw"], rec[W.canonical(t2)])
        sm = score(mkt_fc, outcomes)
        if sm:
            versions["market"] = sm
    except Exception as e:
        print(f"  market calibration skipped ({type(e).__name__}: {e})")

    payload = {"n_played": len(outcomes), "versions": versions,
               "headline_version": "v3" if "v3" in versions else ("v1" if "v1" in versions else None),
               "has_market": "market" in versions}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("window.CALIBRATION = " + json.dumps(payload) + ";\n")
    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    json.dump(payload, open(RESULTS, "w"), indent=2)

    print(f"=== calibration of the pre-committed match forecasts ({len(outcomes)} played) ===")
    print(f"{'ver':>4} {'n':>4} {'Brier':>7} {'baseline':>9} {'skill%':>7} {'reliab':>8} {'resol':>7} {'CORP-MCE':>9} {'slopeB':>7}")
    for v, s in versions.items():
        print(f"{v:>4} {s['n_games']:>4} {s['brier']:>7} {s['brier_baseline']:>9} "
              f"{s['skill_vs_baseline_pct']:>6}% {s['reliability']:>8} {s['resolution']:>7} {s['corp_mce']:>9} {s.get('slope', '-'):>7}")
    print("  read: Brier < baseline = skill; reliability ~0 = well-calibrated; resolution high = discriminating.")
    print(f"wrote {os.path.relpath(OUT, ROOT)} + {os.path.relpath(RESULTS, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
