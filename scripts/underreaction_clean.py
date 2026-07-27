#!/usr/bin/env python3
"""§5.3 clean-subset goal under-reaction — the estimator, written down.

    python scripts/underreaction_clean.py     # -> writeups/_underreaction_clean_results.json

Why this file exists. The published §5.3 numbers ("a median 0.55x the model's fair update, in
log-odds; under-shoots in 7 of 8 matches / 20 of 22 goals; outcome test log-loss 0.235 vs 0.361")
were computed ad hoc and pasted into the writeups: the commit that introduced them
(5a0ff47) changed one markdown file and shipped no code, and no committed script computes a
log-odds ratio or the outcome test. A number in a reproducibility-first paper with no estimator
behind it is the exact failure this repo is supposed to prevent, so the analysis is reconstructed
here from the committed per-game live-WP archive and re-derived on every run.

What the reconstruction recovered, and where it disagrees with the published prose:

  * The outcome test reproduces EXACTLY (log-loss 0.235 vs 0.361, Brier 0.073 vs 0.113) when
    pooled over all goals in the subset. That statistic is confirmed as published.
  * The "22 goals" denominator is the goal set gated on the market having actually moved
    (29 goals in the 8 curated matches, 7 with a flat quote across the settle window).
  * The ratio statistic does NOT reproduce as published. "0.55x, 20 of 22 goals, 7 of 8 matches"
    matches neither space cleanly: in PROBABILITY space the gated sample gives 0.63 and 7 of 8
    matches, in LOG-ODDS it gives 0.35 and 8 of 8. Since the note explicitly claims log-odds --
    that framing is the defence against the "it's just logistic geometry" critique -- log-odds is
    the primary here, and it makes the result STRONGER than the published version, not weaker.

The gate is conservative, and deliberately so. Of the 7 excluded goals, 3 have no fair-value
change at all (90th-minute goals in decided matches: the market is right not to move), but 4 pair
a large model jump with a quote pinned to the tick across the whole window -- a market that does
not move one tick on a 37pp fair-value jump is a missing quote, not a considered zero reaction.
Those 4 are the most extreme apparent under-reactions in the sample, so dropping them can only
move the ratio toward the market. Both gated and ungated figures are emitted; quote the gated one.

Fork-forward safe: reads the archive, writes one artifact, edits nothing under xresidual/.
"""
from __future__ import annotations

import glob
import json
import math
import os
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LW_DIR = os.path.join(ROOT, "viz", "market", "livewp")
POOLED = os.path.join(ROOT, "writeups", "_livewp_results.json")
OUT = os.path.join(ROOT, "writeups", "_underreaction_clean_results.json")

EPS = 1e-9


def _logit(p: float) -> float:
    p = max(min(p, 1 - EPS), EPS)
    return math.log(p / (1 - p))


def _clean_matches() -> set[str]:
    """The clean-reconstruction subset: matches whose goal timeline came from curated minutes
    (not shock inference) AND whose reconstructed score validates against the final."""
    d = json.load(open(POOLED))
    return {m["match"] for m in d["matches"] if m.get("ok") and str(m.get("src", "")).startswith("curated")}


def main() -> int:
    clean = _clean_matches()
    per_match, goals = {}, []
    for fp in sorted(glob.glob(os.path.join(LW_DIR, "*.json"))):
        d = json.load(open(fp))
        if d.get("match") not in clean:
            continue
        fin = d.get("final")
        home_won = None if not fin else (1.0 if fin[0] > fin[1] else 0.0)
        rows = []
        for g in d.get("goals", []):
            model_lo = _logit(g["model_home_after"]) - _logit(g["model_home_before"])
            mkt_lo = _logit(g["mkt_home_settle"]) - _logit(g["mkt_home_pre"])
            rows.append({
                "moved": abs(g["mkt_jump"]) > EPS,
                "model_jump": g["model_jump"],
                "ratio_logodds": (mkt_lo / model_lo) if abs(model_lo) > EPS else None,
                "ratio_prob": (g["mkt_jump"] / g["model_jump"]) if abs(g["model_jump"]) > EPS else None,
                "model_post": g["model_home_after"], "mkt_post": g["mkt_home_settle"],
                "home_won": home_won,
            })
        if rows:
            per_match[d["match"]] = rows
            goals += rows

    if not per_match:
        print("no clean-subset matches in the archive — nothing to compute")
        return 0

    gated = [g for g in goals if g["moved"] and g["ratio_logodds"] is not None]
    ungated = [g for g in goals if g["ratio_logodds"] is not None]
    excl = [g for g in goals if not g["moved"]]

    def match_medians(key, only_moved):
        out = {}
        for m, rows in per_match.items():
            vals = [r[key] for r in rows if r[key] is not None and (r["moved"] or not only_moved)]
            if vals:
                out[m] = st.median(vals)
        return out

    mm_lo = match_medians("ratio_logodds", True)
    under_matches = sum(1 for v in mm_lo.values() if v < 1)
    try:
        from scipy.stats import binomtest
        sign_p = float(binomtest(under_matches, len(mm_lo), 0.5).pvalue)
    except Exception:  # noqa: BLE001 — scipy optional; the point estimate still stands
        sign_p = None

    # Outcome test: pooled over EVERY goal in the subset (this is the variant that reproduces the
    # published 0.235/0.361 and 0.073/0.113 exactly). Scored on the binary home-win indicator.
    scored = [g for g in goals if g["home_won"] is not None]
    ll = lambda p, y: -(y * math.log(max(p, EPS)) + (1 - y) * math.log(max(1 - p, EPS)))
    outcome = None
    if scored:
        outcome = {
            "n_goals": len(scored),
            "model_logloss": round(st.mean(ll(g["model_post"], g["home_won"]) for g in scored), 3),
            "market_logloss": round(st.mean(ll(g["mkt_post"], g["home_won"]) for g in scored), 3),
            "model_brier": round(st.mean((g["model_post"] - g["home_won"]) ** 2 for g in scored), 3),
            "market_brier": round(st.mean((g["mkt_post"] - g["home_won"]) ** 2 for g in scored), 3),
            "basis": "pooled over every goal in the subset, binary home-win indicator",
        }
        outcome["model_better"] = bool(outcome["model_logloss"] < outcome["market_logloss"])

    out = {
        "n_matches": len(per_match), "n_goals": len(goals),
        "n_goals_gated": len(gated), "n_goals_excluded": len(excl),
        "excluded_no_fair_change": sum(1 for g in excl if abs(g["model_jump"]) < 0.01),
        "excluded_quote_pinned": sum(1 for g in excl if abs(g["model_jump"]) >= 0.01),
        "median_ratio_logodds": round(st.median([g["ratio_logodds"] for g in gated]), 3),
        "median_ratio_prob": round(st.median([g["ratio_prob"] for g in gated
                                              if g["ratio_prob"] is not None]), 3),
        "median_ratio_logodds_ungated": round(st.median([g["ratio_logodds"] for g in ungated]), 3),
        "undershoot_goals": sum(1 for g in gated if g["ratio_logodds"] < 1),
        "undershoot_matches": under_matches, "n_matches_ratio": len(mm_lo),
        "match_sign_p": sign_p,
        "outcome_test": outcome,
        "estimator": (
            "log-odds ratio of the market's post-goal move to the model's fair move, per goal, on "
            "the curated-minute matches whose score reconstruction validates; gated on the market "
            "quote actually moving. Primary = median across gated goals. The outcome test pools "
            "ALL goals in the subset (gated and not), which is how the published figure was built."),
        "supersedes": (
            "the ad-hoc '0.55x / 20 of 22 goals / 7 of 8 matches' figures published before "
            "2026-07-25, which shipped with no estimator; see this file's module docstring"),
    }
    json.dump(out, open(OUT, "w"), indent=1)

    print(f"clean subset: {out['n_matches']} matches · {out['n_goals']} goals "
          f"({out['n_goals_gated']} with a market move, {out['n_goals_excluded']} excluded: "
          f"{out['excluded_no_fair_change']} no fair-value change, "
          f"{out['excluded_quote_pinned']} quote pinned)")
    print(f"  median market/model ratio  log-odds {out['median_ratio_logodds']:.3f}  "
          f"(probability space {out['median_ratio_prob']:.3f}; ungated {out['median_ratio_logodds_ungated']:.3f})")
    print(f"  under-shoots in {out['undershoot_goals']}/{out['n_goals_gated']} gated goals, "
          f"{out['undershoot_matches']}/{out['n_matches_ratio']} matches"
          + (f" (sign p={sign_p:.4f})" if sign_p is not None else ""))
    if outcome:
        print(f"  outcome test ({outcome['n_goals']} goals): model log-loss "
              f"{outcome['model_logloss']} vs market {outcome['market_logloss']} · "
              f"Brier {outcome['model_brier']} vs {outcome['market_brier']}")
    print(f"wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
