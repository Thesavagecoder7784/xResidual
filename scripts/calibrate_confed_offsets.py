#!/usr/bin/env python3
"""Re-derive and validate the empirical-Bayes confederation offsets in xresidual.confed_bias.

    python scripts/calibrate_confed_offsets.py

Prints (1) the production base offsets + per-team effective offsets (recency-weighted over all
internationals, as of today), and (2) the out-of-sample evidence:

  - a time-split, cross- vs within-confederation stratified backtest. The shrinkage must
    improve the CROSS-confederation test slice (RPS, log-loss) while leaving the WITHIN slice
    essentially unchanged (the placebo).
  - the gain of the EB shrinkage over a FLAT per-confederation offset, with a dependence-
    respecting significance test (Diebold-Mariano with HAC SE) on the per-match RPS difference,
    because the cross-confederation slice is small and autocorrelated.

This is the calibration record for BASE_OFFSETS / TEAM_OFFSET; update those constants in
confed_bias.py if the numbers here drift materially.
"""
from __future__ import annotations

import os
import sys
from datetime import date

import numpy as np
from scipy.stats import norm, poisson

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import baseline, confed_bias as CB, data, elo  # noqa: E402

CONFS = CB.CONFEDERATIONS


def _prep():
    df = data.load_results()
    res = elo.build_ratings(df)
    cal = res.calib.copy()
    cal["tournament"] = df.sort_values("date").reset_index(drop=True)["tournament"].values
    cal["imp"] = cal["tournament"].map(elo.importance_weight)
    tc = CB.confederation_map(df)
    cal["ch"] = cal["home_team"].map(tc); cal["ca"] = cal["away_team"].map(tc)
    return cal.dropna(subset=["ch", "ca"]), tc


def _wdl(dr, params, gmax=10):
    lh = max((params.total_goals + params.beta * dr / 100.0) / 2.0, 0.02)
    la = max((params.total_goals - params.beta * dr / 100.0) / 2.0, 0.02)
    ph = poisson.pmf(np.arange(gmax + 1), lh); pa = poisson.pmf(np.arange(gmax + 1), la)
    J = np.outer(ph, pa)
    return np.tril(J, -1).sum(), np.trace(J), np.triu(J, 1).sum()


def _per_match_rps(frame, params, off_lookup):
    """off_lookup(home_team, away_team, ch, ca) -> rating delta to add to dr_eff."""
    dr = frame["dr_eff"].values; gd = frame["goal_diff"].values
    ht = frame["home_team"].values; at = frame["away_team"].values
    ch = frame["ch"].values; ca = frame["ca"].values
    oi = {"H": 0, "D": 1, "A": 2}; out = []
    for k in range(len(frame)):
        dd = off_lookup(ht[k], at[k], ch[k], ca[k])
        H, D, A = _wdl(dr[k] + dd, params); s = H + D + A; pv = np.array([H, D, A]) / s
        o = "H" if gd[k] > 0 else ("D" if gd[k] == 0 else "A")
        ov = np.zeros(3); ov[oi[o]] = 1
        out.append(0.5 * np.sum((np.cumsum(pv) - np.cumsum(ov)) ** 2))
    return np.array(out)


def main() -> int:
    cal, tc = _prep()
    today = str(date.today())
    counts = CB.cross_counts(cal, tc, today)
    base = CB.fit_base_offsets(cal, tc, counts, asof=today)
    toff = CB.team_offsets(base, counts)
    print("production base offsets (EB, recency-weighted, all data, UEFA=0):")
    for c in CONFS:
        print(f"  {c:9} {base[c]:+7.1f}   (constant: {CB.BASE_OFFSETS[c]:+.1f})")
    print(f"  K = {CB.SHRINK_K}")
    drift = max(abs(toff[t] - CB.TEAM_OFFSET.get(t, 0.0)) for t in toff)
    print(f"max per-team offset drift vs stored TEAM_OFFSET: {drift:.1f} Elo")

    # OOS backtest: fit strictly before the split, test forward
    SPLIT = "2021-01-01"
    tr = cal[cal["date"] < SPLIT]; te = cal[cal["date"] >= SPLIT]
    params = baseline.calibrate(tr)
    tr_counts = CB.cross_counts(tr, tc, SPLIT)
    tr_base = CB.fit_base_offsets(tr, tc, tr_counts, asof=SPLIT)
    flat = _fit_flat(tr, SPLIT)                                   # comparison baseline
    eb = {t: CB.SHRINK_K / (tr_counts.get(t, 0.0) + CB.SHRINK_K) for t in set(tr["home_team"]) | set(tr["away_team"])}

    def off_none(h, a, ch, ca):
        return 0.0

    def off_flat(h, a, ch, ca):
        return flat.get(ch, 0.0) - flat.get(ca, 0.0)

    def off_eb(h, a, ch, ca):
        return tr_base.get(ch, 0.0) * eb.get(h, 1.0) - tr_base.get(ca, 0.0) * eb.get(a, 1.0)

    cross = te[te["ch"] != te["ca"]].sort_values("date").reset_index(drop=True)
    within = te[te["ch"] == te["ca"]]
    print(f"\nOOS backtest (train < {SPLIT}, test >= {SPLIT}): cross {len(cross)}, within {len(within)}")
    r_none = _per_match_rps(cross, params, off_none)
    r_flat = _per_match_rps(cross, params, off_flat)
    r_eb = _per_match_rps(cross, params, off_eb)
    rw_none = _per_match_rps(within, params, off_none)
    rw_eb = _per_match_rps(within, params, off_eb)
    print(f"  CROSS  baseline RPS {r_none.mean():.5f}")
    print(f"         flat offset  {r_flat.mean():.5f} ({100*(r_none.mean()-r_flat.mean())/r_none.mean():+.2f}%)")
    print(f"         EB shrinkage {r_eb.mean():.5f} ({100*(r_none.mean()-r_eb.mean())/r_none.mean():+.2f}%)")
    print(f"  WITHIN baseline {rw_none.mean():.5f} -> EB {rw_eb.mean():.5f} "
          f"({100*(rw_none.mean()-rw_eb.mean())/rw_none.mean():+.2f}%, placebo ~0)")

    # significance of EB over flat (Diebold-Mariano, HAC SE) on the cross slice
    d = r_flat - r_eb
    n = len(d); L = max(int(n ** (1 / 3)), 1); dm = d - d.mean()
    g0 = np.mean(dm * dm)
    s = g0 + 2 * sum((1 - lag / (L + 1)) * np.mean(dm[lag:] * dm[:-lag]) for lag in range(1, L + 1))
    stat = d.mean() / np.sqrt(s / n); p = 2 * (1 - norm.cdf(abs(stat)))
    print(f"  EB over flat: mean RPS gain {d.mean():.5f}  Diebold-Mariano p = {p:.4f}  "
          f"(b strictly better in {100*(d>0).mean():.0f}% of matches)")
    return 0


def _fit_flat(cal, asof):
    """A flat per-confederation offset = the EB special case with no shrinkage (weight 1 for
    every team), got by fitting with empty cross-counts so K/(0+K)=1. Used for the comparison."""
    tc = {}
    for h, a, ch, ca in zip(cal["home_team"], cal["away_team"], cal["ch"], cal["ca"]):
        tc[h] = ch; tc[a] = ca
    return CB.fit_base_offsets(cal, tc, counts={}, asof=asof)


if __name__ == "__main__":
    raise SystemExit(main())
