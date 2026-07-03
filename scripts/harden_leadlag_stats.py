#!/usr/bin/env python3
"""Cluster-robust hardening of the flagship price-discovery statistics.

The lead-lag headline ('Polymarket leads 65% of events, median +400 ms') pools ~287 goal-events, but
those events are NESTED in ~60 matches — same tape, same book, same MM. A naive Wilson CI on 287 as if
independent OVERSTATES precision (the exact clustering that turned the goal-under-reaction p=0.0001 into
p~0.07). This recomputes the numbers three clustering-honest ways and reports whether the effect survives:

  1. CLUSTER BOOTSTRAP — resample MATCHES (not events) with replacement; the CI that respects clustering.
  2. PER-MATCH META-TEST — each match's poly-lead share is one observation; sign-test the 60 shares vs 0.5
     (equal-weight-per-match, so a few high-event matches can't carry the result).
  3. DESIGN EFFECT — ICC-based deff = how much clustering inflates the naive CI (effective N << 287).

Info-share is already per-match (the honest unit); bootstrap the 42 match GG shares + binomial sign-test.

    python scripts/harden_leadlag_stats.py            # -> prints naive vs clustered, writes _hardened_stats.json
"""
from __future__ import annotations
import json, os, math
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = os.path.join(ROOT, "writeups")
RNG = np.random.default_rng(20260702)
B = 10000


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def load_events():
    """-> decisive events [(match, poly_leads, lead_ms)] + count of synchronous (no-lead) events.

    'synchronous' = both venues repriced within the same 1s bin (leader=='synchronous'): no directional
    evidence, so excluded from the who-leads share but reported, since dropping them silently would flatter
    the result. Share among decisive events; the note's 65.5% keeps synchronous in the denominator."""
    d = json.load(open(os.path.join(W, "_leadlag_results.json")))
    ev = []; n_sync = 0
    for pr in d["pairs"]:
        m = pr.get("match", pr.get("label", "?"))
        for e in pr.get("events", []):
            ld = e.get("lead")
            if not ld:
                continue
            if ld.get("leader") == "synchronous":
                n_sync += 1
            elif ld.get("leader") in ("polymarket", "kalshi"):
                ev.append((m, ld["leader"] == "polymarket", ld.get("best_lag_ms")))
    return ev, n_sync, d["pooled"]


def cluster_bootstrap_share(ev):
    """Resample matches; pooled poly-lead share per replicate."""
    by = {}
    for m, poly, _ in ev:
        by.setdefault(m, []).append(1 if poly else 0)
    matches = list(by.keys())
    shares = []
    for _ in range(B):
        pick = RNG.choice(len(matches), len(matches), replace=True)
        flat = [x for i in pick for x in by[matches[i]]]
        shares.append(np.mean(flat))
    return np.percentile(shares, [2.5, 97.5]), matches, by


def cluster_bootstrap_median(ev):
    """Resample matches; median signed lead-ms (poly-led events, +ms = poly first)."""
    by = {}
    for m, poly, lag in ev:
        if poly and lag is not None:
            by.setdefault(m, []).append(abs(lag))
    matches = list(by.keys())
    meds = []
    for _ in range(B):
        pick = RNG.choice(len(matches), len(matches), replace=True)
        flat = [x for i in pick for x in by[matches[i]]]
        if flat:
            meds.append(np.median(flat))
    return np.median(meds), np.percentile(meds, [2.5, 97.5])


def design_effect(by):
    """One-way-ANOVA ICC for a binary outcome -> deff = 1+(m_bar-1)*ICC -> effective N."""
    groups = [np.array(v) for v in by.values() if len(v) > 0]
    N = sum(len(g) for g in groups); k = len(groups)
    grand = np.concatenate(groups).mean()
    m_bar = N / k
    msb = sum(len(g) * (g.mean() - grand) ** 2 for g in groups) / (k - 1)
    msw = sum(((g - g.mean()) ** 2).sum() for g in groups) / (N - k)
    icc = max(0.0, (msb - msw) / (msb + (m_bar - 1) * msw))
    deff = 1 + (m_bar - 1) * icc
    return icc, deff, N, N / deff


def per_match_sign_test(by):
    """Each match: poly share; count matches poly-leaning vs 0.5; two-sided binomial p."""
    from scipy.stats import binomtest, wilcoxon
    shares = np.array([np.mean(v) for v in by.values() if len(v) >= 1])
    hi = int((shares > 0.5).sum()); lo = int((shares < 0.5).sum())
    p_sign = binomtest(hi, hi + lo, 0.5).pvalue if hi + lo else float("nan")
    try:
        p_w = wilcoxon(shares - 0.5, zero_method="wilcox").pvalue
    except Exception:
        p_w = float("nan")
    return shares, hi, lo, p_sign, p_w


def infoshare_block():
    d = json.load(open(os.path.join(W, "_infoshare_results.json")))
    gg = np.array([m["poly_gg"] for m in d["per_match"]
                   if m.get("n_cointegrated", 0) >= 1 and m.get("poly_gg") is not None])
    from scipy.stats import binomtest, wilcoxon
    boot = [np.median(RNG.choice(gg, len(gg), replace=True)) for _ in range(B)]
    hi = int((gg > 0.5).sum()); lo = int((gg < 0.5).sum())
    return {
        "n_matches": len(gg), "median_gg": float(np.median(gg)),
        "median_ci": [float(x) for x in np.percentile(boot, [2.5, 97.5])],
        "mean_gg": float(gg.mean()), "between_match_sd": float(gg.std(ddof=1)),
        "matches_poly_gt_50": hi, "matches_kalshi": lo,
        "sign_p": float(binomtest(hi, hi + lo, 0.5).pvalue),
        "wilcoxon_p": float(wilcoxon(gg - 0.5).pvalue),
    }


def main():
    ev, n_sync, pooled = load_events()
    N = len(ev); P = sum(1 for _, poly, _ in ev if poly); share = P / N
    share_incl = P / (N + n_sync)
    naive = wilson(P, N)
    ci_share, matches, by = cluster_bootstrap_share(ev)
    med, ci_med = cluster_bootstrap_median(ev)
    icc, deff, _, neff = design_effect(by)
    shares, hi, lo, p_sign, p_w = per_match_sign_test(by)
    iso = infoshare_block()

    print("=" * 74)
    print("LEAD-LAG  (who reprices a goal first)")
    print(f"  {N} decisive events in {len(matches)} matches (+{n_sync} synchronous, no lead)")
    print(f"  poly leads {P}: {share:.1%} of decisive  ({share_incl:.1%} incl. synchronous, the note's convention)")
    print(f"  NAIVE   Wilson 95% CI (events indep):   [{naive[0]:.1%}, {naive[1]:.1%}]")
    print(f"  CLUSTER bootstrap 95% CI (resamp match):[{ci_share[0]:.1%}, {ci_share[1]:.1%}]  <- honest")
    print(f"  design effect: ICC={icc:.3f}  deff={deff:.2f}  effective N={neff:.0f} (of {N})")
    print(f"  per-match sign test: {hi} of {hi+lo} matches poly-leaning  (binom p={p_sign:.2g}, wilcoxon p={p_w:.2g})")
    print(f"  median lead: {med:.0f} ms   cluster-boot 95% CI [{ci_med[0]:.0f}, {ci_med[1]:.0f}] ms")
    verdict = "SURVIVES (CI excludes 50%)" if ci_share[0] > 0.5 else "DOES NOT survive clustering"
    print(f"  => {verdict}")
    print("=" * 74)
    print("INFORMATION SHARE  (Gonzalo-Granger, per-match unit)")
    print(f"  matches={iso['n_matches']} · median GG {iso['median_gg']:.1%}  "
          f"cluster-boot 95% CI [{iso['median_ci'][0]:.1%}, {iso['median_ci'][1]:.1%}]")
    print(f"  between-match SD {iso['between_match_sd']:.1%} (mean {iso['mean_gg']:.1%})")
    print(f"  per-match sign test: {iso['matches_poly_gt_50']} of "
          f"{iso['matches_poly_gt_50']+iso['matches_kalshi']} matches poly>50%  "
          f"(binom p={iso['sign_p']:.2g}, wilcoxon p={iso['wilcoxon_p']:.2g})")
    v2 = "SURVIVES" if iso["median_ci"][0] > 0.5 else "DOES NOT survive"
    print(f"  => {v2}")
    print("=" * 74)

    out = {
        "leadlag": {
            "n_events": N, "n_synchronous": n_sync, "n_matches": len(matches),
            "poly_share_decisive": share, "poly_share_incl_sync": share_incl,
            "naive_wilson_ci": list(naive), "cluster_boot_ci": list(ci_share),
            "icc": icc, "design_effect": deff, "effective_n": neff,
            "per_match_poly_leaning": hi, "per_match_total": hi + lo,
            "per_match_sign_p": p_sign, "per_match_wilcoxon_p": p_w,
            "median_lead_ms": med, "median_lead_ci_ms": list(ci_med),
            "survives_clustering": bool(ci_share[0] > 0.5),
        },
        "infoshare": iso,
        "n_bootstrap": B, "seed": 20260702,
    }
    json.dump(out, open(os.path.join(W, "_hardened_stats.json"), "w"), indent=1)
    print("wrote writeups/_hardened_stats.json")


if __name__ == "__main__":
    main()
