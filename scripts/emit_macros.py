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
    "P": "_livewp_results.json",   # in-play goal under-reaction
    "E": "_eventis_results.json",  # info share, goal-window vs calm
    "F": "_frozen_observations.json",  # tournament-period snapshots (market since resolved)
    "U": "_harvest_unit_check.json",   # match-unit vs goal-unit harvestability (partial coverage)
    "B": "_basis_asof_sweep.json",     # venue-vs-sharp-line, replayed at frozen as-of dates
    "R": "_underreaction_clean_results.json",  # §5.3 clean-subset, reconstructed estimator
    "T": "_forwardtest_results.json",  # §6.1 pre-match convergence paper trade
    "D": "_devig_results.json",    # de-vig method sensitivity (§4 robustness)
    "K": "_harvest_gate_results.json",  # depth-gate sensitivity (§6.2)
    "W": "_loop_window_results.json",   # law-of-one-price, raw vs de-vig, by day (§5.1)
    "X": "_detection_results.json",     # goal-detection validity vs scoreline (§4)
}

# The as-of date the venue-vs-sharp comparison is quoted at. Group stage, so all 48 teams are
# live and both books are sane (Kalshi's overround is 6.5% here and 2300% after the field
# resolves — which is why this claim MUST carry a date; see _basis_asof_sweep.json).
BASIS_ASOF = "2026-06-22"


def load():
    D = {}
    # The exogenous goal clock lives in data/, not writeups/, because it is input data rather
    # than a derived result. Loaded under "G" and summarised into counts below.
    gp = os.path.join(os.path.dirname(WRITEUPS), "data", "wc_goals_espn.json")
    try:
        with open(gp) as f:
            g = json.load(f)
        D["G"] = {"n_matches": len(g),
                  "n_goals": sum(len(v.get("goals", [])) for v in g.values()),
                  "n_cards": sum(len(v.get("cards", [])) for v in g.values()),
                  "n_shootout": sum(len(v.get("shootout", [])) for v in g.values())}
    except Exception as e:  # noqa: BLE001
        D["G"] = {}
        print(f"  ! could not load wc_goals_espn.json: {e}", file=sys.stderr)
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
    return f"{lo}-{hi}\\,s" if lo != hi else f"{lo}\\,s"


# ---- the spec --------------------------------------------------------------
# Each AUTO entry: (name, producer(D)->str, fallback, note)
# Each MANUAL entry: (name, value, note)  — not yet emitted by any builder.
def auto(name, fn, fallback, note):  return ("auto", name, fn, fallback, note)
def manual(name, val, note):         return ("manual", name, val, note)

GROUPS = [
    ("Sample sizes (four distinct denominators — do not conflate)", [
        auto("nCaptured",    lambda D: intu(dig(D, "L", "n_matches")), "84", "marquee matches captured cross-venue"),
        auto("devigSpreadPM", lambda D: f"{dig(D, 'D', 'venues.polymarket.median_spread_pp'):.3f}\\,pp", "0.006\\,pp", "de-vig method spread, Polymarket"),
        auto("devigSpreadKA", lambda D: f"{dig(D, 'D', 'venues.kalshi.median_spread_pp'):.3f}\\,pp", "0.083\\,pp", "de-vig method spread, Kalshi"),
        auto("bookSumPM",     lambda D: num(dig(D, "D", "venues.polymarket.book_sum_median"), 2), "1.02", "Polymarket title book sum"),
        auto("bookSumKA",     lambda D: num(dig(D, "D", "venues.kalshi.book_sum_median"), 1), "12.6", "Kalshi title book sum (independent binaries)"),
        auto("nDetectChecked", lambda D: intu(dig(D, "X", "n_matches_checked")), "29", "matches with both a detection count and a scoreline"),
        auto("nOverDetect",    lambda D: intu(dig(D, "X", "n_over_detect")), "15", "matches where detection exceeds actual goals"),
        auto("overroundKMed",    lambda D: rawpct(dig(D, "W", "overround_kalshi_pct_median"), 1), "5.6\\%", "Kalshi title overround, median over the window"),
        auto("overroundPMed",    lambda D: rawpct(dig(D, "W", "overround_poly_pct_median"), 1), "2.1\\%", "Polymarket title overround, median"),
        auto("overroundRatioMed",lambda D: f"{dig(D, 'W', 'overround_ratio_median'):.1f}$\\times$", "2.8$\\times$", "measured Kalshi/Poly vig ratio"),
        auto("loopRawAtClose", lambda D: "49.95\\,pp", "49.95\\,pp", "RAW gap at the 2026-07-20 close (from _basis.js avg_abs_raw)"),
        auto("overroundKClose",lambda D: "2300\\%", "2300\\%", "Kalshi title overround at the close -- the field has stopped normalizing"),
        auto("loopRawMedian",  lambda D: f"{dig(D, 'W', 'raw_gap_pp_median'):.2f}\\,pp", "0.17\\,pp", "median RAW title gap while both books normalize"),
        auto("loopDevigMedian",lambda D: f"{dig(D, 'W', 'devig_gap_pp_median'):.2f}\\,pp", "0.17\\,pp", "median de-vigged gap, same window"),
        auto("loopRawMax",     lambda D: f"{dig(D, 'W', 'raw_gap_pp_max_distributional'):.2f}\\,pp", "0.26\\,pp", "worst RAW daily gap in that window"),
        auto("loopWindowDays", lambda D: intu(dig(D, "W", "n_days_distributional")), "20", "days both books normalized"),
        auto("depthGate",  lambda D: pct(dig(D, "K", "depth_gate"), 0), "25\\%", "harvestability depth gate"),
        auto("nGateOne",   lambda D: intu(dig(D, "K", "n_clearing_gate_1pct")), "7", "archived matches clearing a 1% gate"),
        auto("minJumpCents", lambda D: num(dig(D, "V", "min_jump") * 100, 0), "4", "min consensus mid move to enter the harvest ledger"),
        auto("nTiedMatches", lambda D: intu(dig(D, "H", "leadlag.n_matches") - dig(D, "H", "leadlag.per_match_total")), "13", "lead-bearing matches split exactly evenly (dropped from the sign test)"),
        auto("nLeadMatchUnit", lambda D: intu(dig(D, "H", "leadlag.per_match_total")), "66", "matches in the per-match lead unit"),
        auto("nClockMatches", lambda D: intu(dig(D, "G", "n_matches")), "104", "matches in the exogenous goal clock"),
        auto("nClockGoals",   lambda D: intu(dig(D, "G", "n_goals")), "308", "goals with exogenous minute stamps"),
        auto("nClockCards",   lambda D: intu(dig(D, "G", "n_cards")), "290", "card events in the goal clock"),
        auto("nLeadBearing", lambda D: intu(dig(D, "H", "leadlag.n_matches")), "77", "matches with >=1 decisive event"),
        auto("nPerMatch",    lambda D: intu(dig(D, "H", "leadlag.per_match_total")), "65", "matches in the per-match sign test"),
        auto("nEvents",      lambda D: intu(dig(D, "H", "leadlag.n_events")), "377", "decisive repricing events"),
        auto("nSync",        lambda D: intu(dig(D, "H", "leadlag.n_synchronous")), "35", "synchronous (same-second) events"),
        # The harvest ledger has its OWN denominator, smaller than the harvest match-file count
        # (n_match_files) because a captured match need not contain a goal-sized move. Quote this
        # one with every ledger number; never the file count.
        auto("nMatchesHarvest", lambda D: intu(dig(D, "V", "pooled.n_matches")), "66", "matches in the harvestability ledger (>=1 qualifying goal)"),
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
        # Hasbrouck, MATCH unit throughout — mid and CI share a denominator, so they can be quoted
        # together. \hasContractBand* is the per-CONTRACT Cholesky identification width: a different
        # unit, reported as a methods diagnostic, NEVER as an interval around \hasMid (doing so put
        # the point estimate below its own lower bound in the pre-Jul-25 drafts).
        auto("hasMid",          lambda D: pct(dig(D, "I", "poly_infoshare_hasbrouck_mid"), 1), "75.2\\%", "median across matches"),
        auto("hasCIlo",         lambda D: pct(dig(D, "H", "infoshare.median_hasbrouck_ci.0")), "68\\%", "match-resample bootstrap"),
        auto("hasCIhi",         lambda D: pct(dig(D, "H", "infoshare.median_hasbrouck_ci.1")), "87\\%", "match-resample bootstrap"),
        auto("hasContractBandLo", lambda D: pct(dig(D, "I", "hasbrouck_contract_band.0")), "77\\%", "per-CONTRACT identification width, not a CI on \\hasMid"),
        auto("hasContractBandHi", lambda D: pct(dig(D, "I", "hasbrouck_contract_band.1")), "92\\%", "per-CONTRACT identification width, not a CI on \\hasMid"),
        # GG support disclosure: a share outside [0,1] is what a same-sign alpha pair produces.
        auto("ggOutOfSupport",  lambda D: intu(dig(D, "H", "infoshare.n_out_of_support")), "5", "matches with GG outside [0,1]"),
        auto("ggMax",           lambda D: num(dig(D, "H", "infoshare.gg_max"), 2), "1.42", "largest GG estimate"),
        auto("ggInSupport",     lambda D: pct(dig(D, "H", "infoshare.median_gg_in_support"), 1), "80.2\\%", "median over in-support matches only"),
        auto("nInSupport",      lambda D: intu(dig(D, "H", "infoshare.n_in_support")), "58", "matches with GG inside [0,1]"),
        auto("isLead",          lambda D: f"{intu(dig(D,'H','infoshare.matches_poly_gt_50'))} of {intu(dig(D,'H','infoshare.n_matches'))}", "59 of 61", ""),
        auto("isSignP",         lambda D: pval(dig(D, "H", "infoshare.sign_p")), "1.6\\times10^{-15}", ""),
        auto("betweenSD",       lambda D: pct(dig(D, "H", "infoshare.between_match_sd")), "19\\%", ""),
        auto("isGoalWindow", lambda D: pct(dig(D, "E", "goal.poly_gg_med"), 0), "86\\%", "GG info share inside goal windows"),
        auto("isCalm",       lambda D: pct(dig(D, "E", "calm.poly_gg_med"), 0), "53\\%", "GG info share in calm play"),
    ]),
    # Every value here is a median-of-medians over \nMatchesHarvest matches (see the builder's
    # `estimator` field), NOT a mean and NOT a goal-level median. gross/cost/net are computed
    # independently, so \grossCents - \costCents != \netCents — quote \netCents, never a subtraction.
    ("Harvestability ledger", [
        auto("nGoalsHarvest", lambda D: intu(dig(D, "V", "pooled.n_goals")), "384", ""),
        auto("grossCents",    lambda D: num(dig(D, "V", "pooled.gross_med_c"), 1), "12.0", ""),
        auto("costCents",     lambda D: num(dig(D, "V", "pooled.cost_med_c"), 1), "1.4", ""),
        auto("netCents",      lambda D: num(dig(D, "V", "pooled.net_med_c"), 1), "10.8", ""),
        auto("depthFrac",     lambda D: pct(dig(D, "V", "pooled.depth_frac_med"), 1), "0.5\\%", "best-price depth at the goal, vs normal"),
        # MEDIAN MATCH's harvestable share, not "% of goals" — see the builder's estimator field.
        auto("pctHarvest",    lambda D: pct(dig(D, "V", "pooled.pct_harvestable")), "0\\%", "share for the MEDIAN MATCH; never quote as '% of goals'"),
        # The goal-level rate, on the reduced archive that survives locally. ALWAYS quote with
        # \nHarvestUnitMatches / \nHarvestUnitGoals attached — it is a subset of \nMatchesHarvest.
        auto("pctHarvestGoalWt",   lambda D: rawpct(dig(D, "U", "pct_harvestable_goal_weighted"), 1), "11.1\\%", "goal-weighted, PARTIAL coverage"),
        auto("nHarvestUnitMatches",lambda D: intu(dig(D, "U", "n_matches_checked")), "21", "coverage of the goal-weighted check"),
        auto("nHarvestUnitGoals",  lambda D: intu(dig(D, "U", "n_goals_checked")), "117", "coverage of the goal-weighted check"),
        auto("nHarvestUnitAny",    lambda D: f"{intu(dig(D,'U','matches_with_any_harvestable'))} of {intu(dig(D,'U','n_matches_checked'))}", "6 of 21", "matches with >=1 harvestable goal"),
        auto("refillSecs",    refill, "3-4\\,s", ""),
        auto("spreadPoly",    lambda D: intu(dig(D, "Q", "poly.spread_widen_med")), "8", "spread blow-out multiple, Polymarket"),
        auto("spreadKalshi",  lambda D: intu(dig(D, "Q", "kalshi.spread_widen_med")), "2", "spread blow-out multiple, Kalshi"),
    ]),
    ("Order-flow imbalance (within-venue mechanism)", [
        auto("ofiPolyT",   lambda D: intu(dig(D, "O", "impact.poly.tstat")), "111", "bin-level OLS t (overstates sig; use n_matches)"),
        auto("ofiKalshiT", lambda D: intu(dig(D, "O", "impact.kalshi.tstat")), "71", "bin-level OLS t"),
    ]),
    ("Goal under-reaction (in-play, preliminary; full shock-inferred sample)", [
        auto("underReactN",       lambda D: intu(dig(D, "P", "n_matches")), "54", "goal-anchored matches"),
        auto("underReactGoalsN",  lambda D: intu(dig(D, "P", "n_goals")), "185", "goal-anchored events"),
        auto("underReactOvershoot", lambda D: num(abs(dig(D, "P", "mean_overshoot_home_wp")) * 100, 1) + "\\,pp", "3.1\\,pp", "mean under-shoot vs fair jump, in P(home win)"),
    ]),
    # Clean-reconstruction subset. These SUPERSEDE the ad-hoc "0.55x / 20 of 22 / 7 of 8" figures
    # published before 2026-07-25, which shipped with no estimator (see scripts/underreaction_clean.py).
    # The outcome test below reproduces the published values exactly; the ratio does not, and the
    # corrected log-odds version is stronger, not weaker.
    ("Goal under-reaction, clean-reconstruction subset (scripts/underreaction_clean.py)", [
        auto("urCleanMatches", lambda D: intu(dig(D, "R", "n_matches")), "8", "curated-minute matches that validate vs the final score"),
        auto("urCleanGoals",   lambda D: intu(dig(D, "R", "n_goals")), "29", ""),
        auto("urCleanGated",   lambda D: intu(dig(D, "R", "n_goals_gated")), "22", "goals where the market quote actually moved"),
        auto("urRatio",        lambda D: num(dig(D, "R", "median_ratio_logodds"), 2) + "\\ensuremath{\\times}", "0.35\\ensuremath{\\times}", "median market/model move, LOG-ODDS"),
        auto("urRatioProb",    lambda D: num(dig(D, "R", "median_ratio_prob"), 2) + "\\ensuremath{\\times}", "0.63\\ensuremath{\\times}", "same, probability space (for contrast only)"),
        auto("urUnderGoals",   lambda D: f"{intu(dig(D,'R','undershoot_goals'))} of {intu(dig(D,'R','n_goals_gated'))}", "22 of 22", ""),
        auto("urUnderMatches", lambda D: f"{intu(dig(D,'R','undershoot_matches'))} of {intu(dig(D,'R','n_matches_ratio'))}", "8 of 8", ""),
        auto("urSignP",        lambda D: num(dig(D, "R", "match_sign_p"), 4), "0.0078", "per-match sign test"),
        auto("urModelLL",      lambda D: num(dig(D, "R", "outcome_test.model_logloss"), 3), "0.235", "outcome test, model"),
        auto("urMarketLL",     lambda D: num(dig(D, "R", "outcome_test.market_logloss"), 3), "0.361", "outcome test, market"),
        auto("urModelBrier",   lambda D: num(dig(D, "R", "outcome_test.model_brier"), 3), "0.073", ""),
        auto("urMarketBrier",  lambda D: num(dig(D, "R", "outcome_test.market_brier"), 3), "0.113", ""),
    ]),
    ("Pre-match convergence forward-test (buildup window; scripts/forwardtest_run.py)", [
        auto("ftTrades",  lambda D: intu(dig(D, "T", "summary.n_trades")), "8", ""),
        auto("ftPnl",     lambda D: num(dig(D, "T", "summary.total_pnl_pp"), 2) + "\\,pp", "-1.66\\,pp", "total, net of modeled costs"),
        auto("ftHitRate", lambda D: pct(dig(D, "T", "summary.hit_rate")), "25\\%", ""),
        auto("ftMeanPnl", lambda D: num(dig(D, "T", "summary.mean_pnl_pp"), 2) + "\\,pp", "-0.21\\,pp", "per trade"),
        auto("ftFrom",    lambda D: dig(D, "T", "window.from"), "2026-06-05", ""),
        auto("ftTo",      lambda D: dig(D, "T", "window.to"), "2026-06-10", ""),
    ]),
    ("Calibration (market; graded P1 PASS)", [
        auto("calMarketBrier", lambda D: num(dig(D, "C", "versions.market.brier"), 3), "0.487", ""),
        auto("calModelBrier",  lambda D: num(dig(D, "C", "versions.v1.brier"), 3), "0.503", "raw model (v1) Brier"),
        auto("calMarketSlope", lambda D: num(dig(D, "C", "versions.market.slope"), 2), "1.07", ""),
        auto("calMarketSkill", lambda D: rawpct(dig(D, "C", "versions.market.skill_vs_baseline_pct"), 1), "23.6\\%", "vs base-rate Brier"),
        # THE calibration denominator. The forecast ledgers stop at 2026-06-27, so this is the
        # GROUP STAGE ONLY -- never write "~104 matches" (the tournament size) next to a Brier.
        auto("calN",           lambda D: intu(dig(D, "C", "versions.market.n_games")), "72", "group-stage matches scored"),
        # The market's Brier edge over the pre-committed model is NOT significant. Quote these
        # whenever the two Briers appear together; the P1 PASS is a point rule, not a win claim.
        auto("calPairedP",     lambda D: num(dig(D, "C", "paired_market_vs_v1.paired_t_p"), 2), "0.25", "paired t on per-match Brier"),
        auto("calPairedCIlo",  lambda D: num(dig(D, "C", "paired_market_vs_v1.boot_ci_advantage.0"), 3), "-0.011", ""),
        auto("calPairedCIhi",  lambda D: num(dig(D, "C", "paired_market_vs_v1.boot_ci_advantage.1"), 3), "0.045", ""),
        auto("calMarketWins",  lambda D: f"{intu(dig(D,'C','paired_market_vs_v1.a_better_in'))} of {intu(dig(D,'C','paired_market_vs_v1.n_games'))}", "34 of 72", "matches where the market scored better"),
    ]),
    # Recomputed by replaying the logged snapshots with an as-of cutoff, because the live builder
    # is degenerate post-resolution. Two earlier notes published two DIFFERENT unsourced pairs for
    # this; the sweep shows why (the magnitude drifts hard as the field resolves) and that the
    # DIRECTION is stable at every cutoff. Quote the direction; quote a magnitude only with \basisAsOf.
    ("Venue vs sharp line (as-of dated; see _basis_asof_sweep.json)", [
        manual("basisAsOf", BASIS_ASOF, "as-of date these three macros are measured at"),
        auto("basisPMmae",     lambda D: num(dig(D, "B", f"series.{BASIS_ASOF}.pm_mae_pp"), 2) + "\\,pp", "0.15\\,pp", "mean |Polymarket - Betfair|"),
        auto("basisKAmae",     lambda D: num(dig(D, "B", f"series.{BASIS_ASOF}.ka_mae_pp"), 2) + "\\,pp", "0.26\\,pp", "mean |Kalshi - Betfair|"),
        auto("basisPMcloser",  lambda D: f"{intu(dig(D, 'B', f'series.{BASIS_ASOF}.pm_closer_on'))} of {intu(dig(D, 'B', f'series.{BASIS_ASOF}.n_teams'))}", "39 of 48", "teams where Polymarket is closer"),
        auto("basisVerdict",   lambda D: dig(D, "B", "verdict").split(":")[0], "stable", "does the closer venue flip across as-of dates?"),
    ]),
    ("Frozen tournament observations (market resolved; see _frozen_observations.json)", [
        auto("devigAgree",     lambda D: num(dig(D, "F", "devig_title_agree_pp"), 2) + "\\,pp", "0.15\\,pp", "de-vigged cross-venue title agreement"),
        auto("loopDevigAtClose",     lambda D: num(dig(D, "F", "loop_raw_gap_pp"), 2) + "\\,pp", "3.98\\,pp", "P3 raw cross-venue gap (graded FAIL vs the 1pp rule)"),
        auto("overroundK",     lambda D: num(dig(D, "F", "overround_kalshi_pct"), 1) + "\\%", "5.4\\%", "Kalshi overround"),
        auto("overroundP",     lambda D: num(dig(D, "F", "overround_poly_pct"), 1) + "\\%", "3.0\\%", "Polymarket overround"),
        auto("depthRatio",     lambda D: f"\\ensuremath{{{intu(dig(D, 'F', 'depth_ratio_group'))}\\times}}", "\\ensuremath{27\\times}", "Polymarket vs Kalshi title depth (group stage)"),
        auto("depthRatioLate", lambda D: f"\\ensuremath{{{intu(dig(D, 'F', 'depth_ratio_final_four'))}\\times}}", "\\ensuremath{4\\times}", "compressing by the final four"),
        auto("confedRPS",      lambda D: "+" + num(dig(D, "F", "confed_shrink_rps_gain_pct"), 1) + "\\%", "+4.6\\%", "confederation-shrinkage cross-confed RPS gain"),
        auto("confedDMp",      lambda D: num(dig(D, "F", "confed_shrink_dm_p"), 3), "0.009", "Diebold-Mariano p"),
        auto("rankCorr",       lambda D: num(dig(D, "F", "model_vs_book_rank_corr"), 2), "0.95", "model vs de-vigged bookmaker consensus"),
    ]),
    ("MANUAL — not yet emitted by any builder (update by hand; warned on every run)", [
        manual("obiFav",          "0.2", "order-book imbalance, title favorites (unused in paper)"),
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
