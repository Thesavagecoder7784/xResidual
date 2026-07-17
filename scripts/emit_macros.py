#!/usr/bin/env python3
"""Emit paper/arxiv/macros.tex from the canonical result JSONs — one source of truth.

    python scripts/emit_macros.py            # (re)write paper/arxiv/macros.tex
    python scripts/emit_macros.py --check    # verify it's in sync (CI); exit 1 if stale
    python scripts/emit_macros.py -v         # also print every macro and its source

Every result number in the arXiv manuscript is a LaTeX macro. This script reads the
committed writeups/*_results.json artifacts and regenerates that macro file, so the
July-19 data refresh re-numbers the ENTIRE paper by running one command instead of
hand-editing prose (the drift the reconciliation audit found). Numbers not yet emitted
by any builder are kept in a clearly-marked MANUAL block and reported as warnings, so
they are never silently forgotten.

Fork-forward safe: reads artifacts only, edits nothing under xresidual/.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WRITEUPS = os.path.join(ROOT, "writeups")
DEFAULT_OUT = os.path.join(ROOT, "paper", "arxiv", "macros.tex")

SOURCES = {
    "H": "_hardened_stats.json",   # cluster-robust flagship stats (canonical)
    "L": "_leadlag_results.json",  # pooled event-study lead-lag
    "I": "_infoshare_results.json",# Hasbrouck / Gonzalo-Granger
    "V": "_harvest_results.json",  # cost-of-immediacy ledger
    "O": "_ofi_results.json",      # order-flow imbalance
    "Q": "_liquidity_results.json",# spread/depth at the shock
    "C": "_calibration_results.json",
}


def load():
    D = {}
    for k, fn in SOURCES.items():
        p = os.path.join(WRITEUPS, fn)
        try:
            with open(p) as f:
                D[k] = json.load(f)
        except Exception as e:  # noqa: BLE001 — degrade to fallbacks, don't crash
            D[k] = {}
            print(f"  ! could not load {fn}: {e}", file=sys.stderr)
    return D


def dig(D, key, path):
    """Walk a dotted path through nested dicts/lists; raise KeyError if absent."""
    o = D.get(key, {})
    for part in path.split("."):
        if isinstance(o, list):
            o = o[int(part)]
        elif isinstance(o, dict) and part in o:
            o = o[part]
        else:
            raise KeyError(f"{key}.{path}")
    return o


# ---- formatters (all emit LaTeX-safe strings) ------------------------------
def pct(x, d=0):      return f"{x * 100:.{d}f}\\%"      # fraction -> percent
def rawpct(x, d=0):   return f"{x:.{d}f}\\%"            # already in percent units
def num(x, d=0):      return f"{x:.{d}f}"
def msn(x):           return f"+{int(round(x))}\\,ms"
def intu(x):          return str(int(round(x)))


def pval(p):
    if p <= 0:
        return "0"
    exp = math.floor(math.log10(p))
    mant = p / 10 ** exp
    if round(mant, 1) >= 10:      # 9.96e-9 -> 1.0e-8
        mant /= 10
        exp += 1
    return f"{mant:.1f}\\times10^{{{exp}}}"


def refill(D):
    # text-mode safe: en-dash + thin space both valid outside math mode
    a = dig(D, "Q", "poly.resilience_ms_med") / 1000
    b = dig(D, "Q", "kalshi.resilience_ms_med") / 1000
    lo, hi = sorted([int(round(a)), int(round(b))])
    return f"{lo}--{hi}\\,s" if lo != hi else f"{lo}\\,s"


# ---- the spec --------------------------------------------------------------
# Each AUTO entry: (name, producer(D)->str, fallback, note)
# Each MANUAL entry: (name, value, note)  — not yet emitted by any builder.
def auto(name, fn, fallback, note):  return ("auto", name, fn, fallback, note)
def manual(name, val, note):         return ("manual", name, val, note)

GROUPS = [
    ("Sample sizes (three distinct denominators — do not conflate)", [
        auto("nCaptured",    lambda D: intu(dig(D, "L", "n_matches")), "84", "marquee matches captured cross-venue"),
        auto("nLeadBearing", lambda D: intu(dig(D, "H", "leadlag.n_matches")), "77", "matches with >=1 decisive event"),
        auto("nPerMatch",    lambda D: intu(dig(D, "H", "leadlag.per_match_total")), "65", "matches in the per-match sign test"),
        auto("nEvents",      lambda D: intu(dig(D, "H", "leadlag.n_events")), "377", "decisive repricing events"),
        auto("nSync",        lambda D: intu(dig(D, "H", "leadlag.n_synchronous")), "35", "synchronous (same-second) events"),
    ]),
    ("Lead-lag (event study)", [
        auto("polyEvents",     lambda D: intu(dig(D, "L", "pooled.poly_leads")), "269", ""),
        auto("kalshiEvents",   lambda D: intu(dig(D, "L", "pooled.kalshi_leads")), "108", ""),
        auto("polyShare",      lambda D: pct(dig(D, "H", "leadlag.poly_share_decisive")), "71\\%", "decisive share"),
        auto("polyShareSync",  lambda D: pct(dig(D, "H", "leadlag.poly_share_incl_sync")), "65\\%", "if synchronous count against"),
        auto("medLead",        lambda D: msn(dig(D, "H", "leadlag.median_lead_ms")), "+600\\,ms", ""),
        auto("leadCIlo",       lambda D: pct(dig(D, "H", "leadlag.cluster_boot_ci.0")), "66\\%", ""),
        auto("leadCIhi",       lambda D: pct(dig(D, "H", "leadlag.cluster_boot_ci.1")), "76\\%", ""),
        auto("designEffect",   lambda D: num(dig(D, "H", "leadlag.design_effect"), 2), "1.13", ""),
        auto("iccVal",         lambda D: num(dig(D, "H", "leadlag.icc"), 3), "0.033", ""),
        auto("permatchLean",   lambda D: f"{intu(dig(D,'H','leadlag.per_match_poly_leaning'))} of {intu(dig(D,'H','leadlag.per_match_total'))}", "56 of 65", ""),
        auto("permatchSignP",  lambda D: pval(dig(D, "H", "leadlag.per_match_sign_p")), "2.0\\times10^{-9}", ""),
        auto("permatchWilcoxP",lambda D: pval(dig(D, "H", "leadlag.per_match_wilcoxon_p")), "1.0\\times10^{-7}", ""),
    ]),
    ("Information share (Hasbrouck / Gonzalo-Granger)", [
        auto("nCoint",          lambda D: intu(dig(D, "H", "infoshare.n_matches")), "61", "cointegrated matches"),
        auto("nCointContracts", lambda D: intu(dig(D, "I", "n_cointegrated_contracts")), "100", "cointegrated contracts"),
        auto("ggShare",         lambda D: pct(dig(D, "H", "infoshare.median_gg"), 1), "80.6\\%", ""),
        auto("ggCIlo",          lambda D: pct(dig(D, "H", "infoshare.median_ci.0")), "76\\%", ""),
        auto("ggCIhi",          lambda D: pct(dig(D, "H", "infoshare.median_ci.1")), "87\\%", ""),
        auto("hasMid",          lambda D: pct(dig(D, "I", "poly_infoshare_hasbrouck_mid")), "75\\%", ""),
        auto("hasBandLo",       lambda D: pct(dig(D, "I", "hasbrouck_mid_band.0")), "77\\%", ""),
        auto("hasBandHi",       lambda D: pct(dig(D, "I", "hasbrouck_mid_band.1")), "92\\%", ""),
        auto("isLead",          lambda D: f"{intu(dig(D,'H','infoshare.matches_poly_gt_50'))} of {intu(dig(D,'H','infoshare.n_matches'))}", "59 of 61", ""),
        auto("isSignP",         lambda D: pval(dig(D, "H", "infoshare.sign_p")), "1.6\\times10^{-15}", ""),
        auto("betweenSD",       lambda D: pct(dig(D, "H", "infoshare.between_match_sd")), "19\\%", ""),
        manual("isGoalWindow", "86\\%", "info share inside goal windows — VERIFY vs _eventis_results.json"),
        manual("isCalm",       "53\\%", "info share in calm play — VERIFY vs _eventis_results.json"),
    ]),
    ("Harvestability ledger", [
        auto("nGoalsHarvest", lambda D: intu(dig(D, "V", "pooled.n_goals")), "384", ""),
        auto("grossCents",    lambda D: num(dig(D, "V", "pooled.gross_med_c"), 1), "12.5", ""),
        auto("costCents",     lambda D: num(dig(D, "V", "pooled.cost_med_c"), 1), "1.4", ""),
        auto("netCents",      lambda D: num(dig(D, "V", "pooled.net_med_c"), 1), "10.9", ""),
        auto("depthFrac",     lambda D: pct(dig(D, "V", "pooled.depth_frac_med"), 1), "0.5\\%", "best-price depth at the goal, vs normal"),
        auto("pctHarvest",    lambda D: pct(dig(D, "V", "pooled.pct_harvestable")), "0\\%", ""),
        auto("refillSecs",    refill, "3--4\\,s", ""),
        auto("spreadPoly",    lambda D: intu(dig(D, "Q", "poly.spread_widen_med")), "8", "spread blow-out multiple, Polymarket"),
        auto("spreadKalshi",  lambda D: intu(dig(D, "Q", "kalshi.spread_widen_med")), "2", "spread blow-out multiple, Kalshi"),
    ]),
    ("Order-flow imbalance (within-venue mechanism)", [
        auto("ofiPolyT",   lambda D: intu(dig(D, "O", "impact.poly.tstat")), "111", "bin-level OLS t (overstates sig; use n_matches)"),
        auto("ofiKalshiT", lambda D: intu(dig(D, "O", "impact.kalshi.tstat")), "71", "bin-level OLS t"),
    ]),
    ("Calibration (market; graded verdict pending Jul-19)", [
        auto("calMarketBrier", lambda D: num(dig(D, "C", "versions.market.brier"), 3), "0.487", ""),
        auto("calMarketSlope", lambda D: num(dig(D, "C", "versions.market.slope"), 2), "1.07", ""),
        auto("calMarketSkill", lambda D: rawpct(dig(D, "C", "versions.market.skill_vs_baseline_pct"), 1), "23.6\\%", "vs base-rate Brier"),
    ]),
    ("MANUAL — not yet emitted by any builder (update by hand; warned on every run)", [
        manual("devigAgree",      "0.15\\,pp", "cross-venue title agreement, de-vigged"),
        manual("overroundK",      "5.4\\%", "Kalshi overround"),
        manual("overroundP",      "3.0\\%", "Polymarket overround"),
        manual("depthRatio",      "\\ensuremath{27\\times}", "Polymarket vs Kalshi title depth (group stage)"),
        manual("depthRatioLate",  "\\ensuremath{4\\times}", "compressing by the final four"),
        manual("obiFav",          "0.2", "order-book imbalance, title favorites"),
        manual("underReactMult",  "\\ensuremath{0.55\\times}", "post-goal update vs fair — VERIFY vs _livewp (curated 8-match subset)"),
        manual("underReactMatches","7 of 8", "clean-reconstruction subset"),
        manual("underReactGoals", "20 of 22", "clean-reconstruction subset"),
        manual("underReactSignP", "0.07", "per-match sign test"),
        manual("confedRPS",       "+4.6\\%", "confederation-shrinkage cross-confed RPS gain"),
        manual("confedDMp",       "0.009", "Diebold-Mariano p"),
        manual("rankCorr",        "0.95", "model vs de-vigged bookmaker consensus"),
    ]),
]


def build(D):
    """Return (text, warnings, n_auto, n_manual)."""
    try:
        seed = dig(D, "H", "seed")
        nboot = dig(D, "H", "n_bootstrap")
        prov = f"hardened seed {seed}, {nboot} bootstraps"
    except KeyError:
        prov = "hardened stats unavailable"
    lines = [
        "% ============================================================================",
        "%  CANONICAL NUMBERS — single source of truth for the manuscript.",
        "%  GENERATED by scripts/emit_macros.py — DO NOT EDIT BY HAND.",
        f"%  Source: writeups/_*_results.json ({prov}).",
        "%  Regenerate after every data refresh:  python scripts/emit_macros.py",
        "% ============================================================================",
        "",
    ]
    warnings, n_auto, n_manual = [], 0, 0
    for title, entries in GROUPS:
        lines.append(f"% ---- {title} " + "-" * max(3, 74 - len(title)))
        for entry in entries:
            kind, name = entry[0], entry[1]
            if kind == "auto":
                _, _, fn, fallback, note = entry
                try:
                    val = fn(D)
                    n_auto += 1
                except Exception as e:  # noqa: BLE001
                    val = fallback
                    warnings.append(f"{name}: source missing ({e}) — used fallback {fallback!r}")
                    note = (note + "; FALLBACK").strip("; ")
            else:
                _, _, val, note = entry
                n_manual += 1
                warnings.append(f"{name}: MANUAL ({note})")
            comment = f"  % {note}" if note else ""
            lines.append(f"\\newcommand{{\\{name}}}{{{val}}}{comment}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n", warnings, n_auto, n_manual


def parse_macros(text):
    return dict(re.findall(r"\\newcommand\{\\(\w+)\}\{(.*?)\}(?:\s*%|$)", text, re.M))


def main():
    ap = argparse.ArgumentParser(description="Emit paper/arxiv/macros.tex from canonical JSONs.")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="verify in-sync; exit 1 if stale")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    D = load()
    text, warnings, n_auto, n_manual = build(D)

    if args.verbose:
        for name, val in parse_macros(text).items():
            print(f"  \\{name} = {val}")

    if args.check:
        try:
            with open(args.out) as f:
                cur = f.read()
        except FileNotFoundError:
            print(f"FAIL: {args.out} does not exist — run emit_macros.py", file=sys.stderr)
            return 1
        old, new = parse_macros(cur), parse_macros(text)
        changed = {k: (old.get(k), new[k]) for k in new if old.get(k) != new[k]}
        removed = [k for k in old if k not in new]
        if changed or removed:
            print("OUT OF SYNC — macros.tex differs from the JSON artifacts:", file=sys.stderr)
            for k, (o, n) in changed.items():
                print(f"  \\{k}: {o!r} -> {n!r}", file=sys.stderr)
            for k in removed:
                print(f"  \\{k}: removed", file=sys.stderr)
            print("Run: python scripts/emit_macros.py", file=sys.stderr)
            return 1
        print(f"macros.tex in sync ({n_auto} auto + {n_manual} manual).")
        return 0

    with open(args.out, "w") as f:
        f.write(text)
    rel = os.path.relpath(args.out, ROOT)
    print(f"Wrote {rel}: {n_auto} auto-wired, {n_manual} manual.")
    if warnings:
        print(f"\n{len(warnings)} value(s) need attention (manual or fallback):")
        for w in warnings:
            print(f"  - {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
