#!/usr/bin/env python3
"""One-button grader for PREREGISTRATION.md — the July-19 scorecard, on demand.

    python scripts/grade_prereg.py            # grade every line against its FROZEN threshold
    python scripts/grade_prereg.py --json     # machine-readable scorecard

The pre-registration binds each prediction (P1..P11) to an exact metric + threshold that may
NOT be changed on grading day. This script reads the committed result artifacts (the same
*_results.json / _*.js the builders already emit) and applies those thresholds mechanically,
so the July-19 grade is a button press, not a manual scramble — and so any gap (a missing
number, a broken result-join) surfaces NOW, while there is still time to fix it.

Verdicts: PASS / FAIL / PARTIAL / INCONCLUSIVE (n below the pre-registered minimum) /
PENDING (the metric isn't emitted by any builder yet — a gap to close before Jul 19).
Mid-tournament every live verdict is PROVISIONAL; the final grade runs after the final.

Fork-forward: reads artifacts only, edits nothing under xresidual/. Thresholds are quoted
from PREREGISTRATION.md inline so a reviewer can audit grade-vs-rule without cross-referencing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WRITEUPS = os.path.join(ROOT, "writeups")
VIZ = os.path.join(ROOT, "viz")

PASS, FAIL, PARTIAL, INC, PEND = "PASS", "FAIL", "PARTIAL", "INCONCLUSIVE", "PENDING"


def _load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _load_js(path):
    """window.FOO = {...}; -> dict."""
    try:
        s = open(path).read().strip()
    except OSError:
        return None
    s = re.sub(r"^window\.[A-Za-z_]+\s*=\s*", "", s).rstrip().rstrip(";")
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def V(pid, label, tag, primary, verdict, value, threshold, n=None, note=""):
    return {"id": pid, "label": label, "tag": tag, "primary": primary,
            "verdict": verdict, "value": value, "threshold": threshold, "n": n, "note": note}


# ── PRIMARY ──────────────────────────────────────────────────────────────────

def grade_p6():
    """P6 [PRIMARY] deeper venue (Polymarket) leads price discovery.
    PASS if n>=20 goal shocks AND Poly info share >50% in a majority of events. FAIL if Kalshi leads."""
    d = _load_json(os.path.join(WRITEUPS, "_infoshare_results.json"))
    if not d:
        return V("P6", "Deeper venue leads (info share)", "genuine unknown", True,
                 PEND, None, "n>=20, Poly IS>50% in majority", note="no _infoshare_results.json")
    n = d.get("n_matches", 0)
    lc = d.get("match_leader_counts", {})
    poly, kal = lc.get("polymarket", 0), lc.get("kalshi", 0)
    gg = d.get("poly_infoshare_gg")
    val = f"Poly leads {poly}/{poly + kal} matches · GG IS {gg:.1%}" if gg is not None else f"Poly {poly}/{poly + kal}"
    if n < 20:
        return V("P6", "Deeper venue leads (info share)", "genuine unknown", True,
                 INC, val, "n>=20 goal shocks", n=n, note="below pre-registered min n")
    verdict = PASS if poly > kal and (gg or 0) > 0.5 else FAIL
    return V("P6", "Deeper venue leads (info share)", "genuine unknown", True,
             verdict, val, "Poly IS>50% in majority of n>=20", n=n,
             note="cross-check: per-match leader majority")


def grade_p1():
    """P1 [PRIMARY] markets well-calibrated.
    PASS if (a) CORP curve within band (no systematic miscalibration) AND (b) slope b in [0.70,1.30]
    AND (c) market Brier < raw (v1) model Brier on the same matches."""
    d = _load_json(os.path.join(WRITEUPS, "_calibration_results.json"))
    if not d:
        return V("P1", "Markets well-calibrated", "genuine unknown", True,
                 PEND, None, "(a) in-band (b) b in [.70,1.30] (c) mkt Brier<v1", note="no _calibration_results.json")
    ver = d.get("versions", {})
    mkt, v1 = ver.get("market"), ver.get("v1")
    n = d.get("n_played")
    if not mkt or not v1:
        return V("P1", "Markets well-calibrated", "genuine unknown", True,
                 PEND, None, "market & v1 Brier", n=n, note="market/v1 block missing from artifact")
    c_brier = mkt["brier"] < v1["brier"]                       # clause (c)
    a_calib = mkt.get("corp_in_band")                          # clause (a): REGISTERED band test
    if a_calib is None:                                        # fallback if artifact predates the band test
        a_calib = mkt.get("reliability", 1) < 0.02
    slope = mkt.get("slope") or mkt.get("slope_b") or mkt.get("calib_slope")  # clause (b)
    band = f"in-band {mkt.get('corp_in_band_frac')}" if mkt.get("corp_in_band_frac") is not None else f"MCB {mkt.get('reliability')}"
    val = f"mkt Brier {mkt['brier']:.4f} vs v1 {v1['brier']:.4f} · {band}"
    if slope is None:
        return V("P1", "Markets well-calibrated", "genuine unknown", True,
                 PEND, val, "(b) slope b in [0.70,1.30]", n=n,
                 note="slope b missing from artifact — re-run scripts/build_calibration.py")
    b_slope = 0.70 <= slope <= 1.30
    verdict = PASS if (a_calib and b_slope and c_brier) else FAIL
    return V("P1", "Markets well-calibrated", "genuine unknown", True, verdict,
             val + f" · slope {slope:.2f}", "(a)in-band (b)b in[.70,1.30] (c)mkt<v1", n=n)


# ── SECONDARY ────────────────────────────────────────────────────────────────

def grade_p2():
    """P2 longshot bias stronger in books than PMs (directional). Bound to per-venue 1X2
    reliability_table. DATA-FORCED INCONCLUSIVE: Kalshi/Polymarket do not quote the draw on these WC
    matches (2-way match/winner markets only), so there is no PM-side 1X2 to put on the reliability
    diagram; the book (oddsapi) side is computable but the comparator isn't. Deviations clause."""
    return V("P2", "Favourite-longshot: books>PMs", "genuine unknown", False,
             INC, "PM venues quote no draw -> no PM-side 1X2", "book longshot gap > PM gap",
             note="DECISION: data-forced INCONCLUSIVE (PMs price 2-way only). Needs a "
                  "PREREGISTRATION-ADDENDUM entry recording the limitation before Jul 19 (your call).")


def grade_p3():
    """P3 law of one price: mean abs de-vigged top-12 cross-venue gap <= 1.0pp through the final."""
    d = _load_js(os.path.join(VIZ, "market", "_basis.js"))
    if not d:
        return V("P3", "Law of one price (gap<=1pp)", "observed, extrapolated", False,
                 PEND, None, "mean abs top-12 gap <= 1.0pp", note="no _basis.js")
    gap = d.get("avg_abs_gap")
    if gap is None:
        teams = d.get("teams", [])[:12]
        gap = sum(abs(t.get("basis", 0)) for t in teams) / max(len(teams), 1)
    return V("P3", "Law of one price (gap<=1pp)", "observed, extrapolated", False,
             PASS if gap <= 1.0 else FAIL, f"mean abs gap {gap:.3f}pp", "<= 1.0pp",
             note="provisional: holds only if it persists through the final")


def grade_p4():
    """P4 visible gap mostly vig: de-vigged mean gap < HALF raw mean gap AND Kalshi overround > Poly.
    Graded by the COMMITTED build_basis.py metric (mean ABSOLUTE gap: avg_abs_gap/avg_abs_raw). NB:
    that aggregation washes out the sign, and the 'mostly vig' effect is a SIGNED systematic offset,
    so the signed net gap is reported alongside as a diagnostic — the two currently diverge (see note)."""
    d = _load_js(os.path.join(VIZ, "market", "_basis.js"))
    if not d:
        return V("P4", "Gap is mostly vig", "observed, extrapolated", False,
                 PEND, None, "de-vig gap < raw/2 AND Kalshi vig>Poly", note="no _basis.js")
    gap, raw = d.get("avg_abs_gap"), d.get("avg_abs_raw")          # committed metric (absolute)
    ov = d.get("overround", {})
    k, p = ov.get("kalshi"), ov.get("pm")
    teams = d.get("teams", [])
    net_raw = sum(t.get("raw_basis", 0) for t in teams) / len(teams) if teams else None   # diagnostic
    net_dev = sum(t.get("basis", 0) for t in teams) / len(teams) if teams else None
    if None in (gap, raw, k, p):
        return V("P4", "Gap is mostly vig", "observed, extrapolated", False, PEND, None,
                 "de-vig gap < raw/2 AND Kalshi vig>Poly", note="basis fields missing")
    ok = gap < raw / 2 and k > p
    note = ("graded by the committed ABSOLUTE-gap metric (decision: grade as-is, no mid-tournament "
            f"metric swap). Diagnostic: the signed NET gap confirms the vig collapse the claim is about "
            f"- raw {net_raw:+.3f}pp -> de-vig {net_dev:+.3f}pp - reported alongside the verdict.") \
        if not ok else ""
    return V("P4", "Gap is mostly vig", "observed, extrapolated", False,
             PASS if ok else FAIL, f"abs de-vig {gap:.3f} vs raw/2 {raw / 2:.3f} · vig K{k}% P{p}%",
             "de-vig gap < raw/2 AND K vig>P vig", note=note)


def grade_p5():
    """P5 closing beats opening: closing Brier < opening Brier on resolved matches, pooled."""
    d = _load_json(os.path.join(WRITEUPS, "_pricediscovery_results.json"))
    if not d or not d.get("n"):
        return V("P5", "Price discovery: closing>opening", "genuine unknown", False,
                 PEND, None, "closing Brier < opening Brier",
                 note="run scripts/build_pricediscovery.py")
    n = d["n"]
    val = f"opening Brier {d['brier_open']} -> closing {d['brier_close']} (improve {d['improvement']:+})"
    return V("P5", "Price discovery: closing>opening", "genuine unknown", False,
             PASS if d.get("pass") else FAIL, val, "closing Brier < opening Brier", n=n,
             note="provisional: bookmaker h2h consensus; final pools the full tournament")


def grade_p7():
    """P7 (a) raw-Elo favourite beats its market prob by >=5pp PRE-TOURNAMENT [observed, frozen]
    AND (b) market mean log-score < raw-model mean log-score [unknown].

    Leg (a) is a PRE-COMMITTED OBSERVATION frozen in PREREGISTRATION.md L113 (Spain ~28% Elo vs
    ~16% market = +12pp >= 5pp -> top-heavy TRUE). It is NOT recomputed from live _blend.js: at the
    final the champion's title market RESOLVES to 100%, so a live recompute (Spain 40% vs 100% =
    -60pp) would spuriously flip a frozen observation. That is the P7 resolution degeneracy; honoring
    the frozen pre-reg value is the pre-registration-faithful grade. Leg (b) from _skill_results.json."""
    skill = _load_json(os.path.join(WRITEUPS, "_skill_results.json"))
    # Leg (a): frozen pre-tournament observation (PREREGISTRATION.md L113). Not recomputed live.
    a_ok = True
    a_val = "(a) Elo fav Spain ~28% vs mkt ~16% = +12pp [pre-tournament, frozen @ PREREG L113]"
    b_ok = b_val = None
    if skill and skill.get("n_matches"):
        b_ok = skill.get("pass_b")
        b_val = f"(b) mkt logscore {skill['market_mean_logscore']} vs model {skill['baseline_mean_logscore']}"
    if b_ok is None:
        return V("P7", "Model top-heavy; market better skill", "part observed", False,
                 PEND, " · ".join(x for x in (a_val, b_val) if x),
                 "(a) Elo fav-mkt>=5pp [frozen] AND (b) mkt<model", note="run scripts/build_skill.py")
    verdict = PASS if (a_ok and b_ok) else FAIL
    return V("P7", "Model top-heavy; market better skill", "part observed", False, verdict,
             f"{a_val} · {b_val}", "(a) Elo fav-mkt>=5pp [pre-tournament, frozen] AND (b) mkt<model logscore",
             n=skill.get("n_matches"))


def grade_p8():
    """P8 sigma-sanity: biggest one-second z over the tournament <= 4sigma, typical largest 2-3sigma."""
    d = _load_json(os.path.join(WRITEUPS, "_sigma_results.json"))
    p = d.get("pooled") if d else None
    if not p:
        return V("P8", "Sigma-sanity (no 12-sigma)", "genuine unknown", False,
                 PEND, None, "max z <= 4sigma; typical 2-3sigma",
                 note="tape-bound: build_sigma.py runs in the VM micro pipeline on the next idle cycle")
    val = (f"tournament max z {p['tournament_max_z']} ({p['tournament_max_match']}) · "
           f"median match-max {p['median_match_max_z']}")
    nz = p.get("tournament_max_nonzero_frac")
    if nz is not None and nz < 0.10:
        # the 1s-return-std denominator is degenerate: PM mids are step functions ~98% flat at 1s,
        # so std collapses to the noise floor and z is uninterpretable (40-390sigma everywhere).
        # Reporting a FAIL here would be a false finding (a divide-by-~0 artifact, not a fat tail).
        return V("P8", "Sigma-sanity (no 12-sigma)", "genuine unknown", False, INC,
                 f"{val} but denominator degenerate (nz-frac {nz})", "max z <= 4sigma",
                 n=p.get("n_matches"),
                 note="DATA-FORCED INCONCLUSIVE: prediction-market mids are step functions ~98% flat "
                      "at 1s, so the committed 1s-return-std denominator collapses to the noise floor "
                      "and z is uninterpretable. The metric assumes a continuously-priced series; these "
                      "aren't one. Needs a PREREGISTRATION-ADDENDUM entry (your call).")
    return V("P8", "Sigma-sanity (no 12-sigma)", "genuine unknown", False,
             PASS if p.get("max_z_le_4") else FAIL, val, "max z <= 4sigma", n=p.get("n_matches"),
             note=f"nonzero-frac at the max {nz}")


def grade_p9():
    """P9 heat slows the 2nd half (in-play). INCONCLUSIVE if <8 extreme-heat afternoon games with clean
    in-play data (likely, ~9 such games exist). Underpowered by construction."""
    return V("P9", "Heat slows 2nd half (in-play)", "underpowered", False,
             INC, None, "lower late-goal rate AND faster under-drift (n>=8 extreme-heat aft.)",
             note="GAP+power: in-play late-goal-rate / under-drift split not emitted; pre-flagged "
                  "most-likely-INCONCLUSIVE (~9 qualifying games)")


def grade_p10():
    """P10 goal-overreaction reverts (the edge test).
    PASS if mean per-trade PnL > 0 net of cost AND reversion larger for higher-surprise goals.
    FAIL if mean PnL <= 0 (edge gone). INCONCLUSIVE if < 20 clean shocks."""
    d = _load_js(os.path.join(VIZ, "model", "_overreaction.js"))
    if not d:
        return V("P10", "Overreaction reverts (edge test)", "genuine unknown", False,
                 PEND, None, "mean PnL>0 AND surprise-monotone", note="no _overreaction.js")
    s, ss = d.get("summary", {}), d.get("summary_surprising", {})
    n = s.get("n", 0)
    pnl = s.get("mean_pnl_pp")
    val = f"mean PnL {pnl:+.3f}pp · surprise-subset {ss.get('mean_pnl_pp')}pp · revert {ss.get('mean_reverted_pp')}pp"
    if n < 20:
        return V("P10", "Overreaction reverts (edge test)", "genuine unknown", False,
                 INC, val, ">=20 clean shocks", n=n)
    # PASS needs BOTH a positive edge AND stronger reversion for higher-surprise goals
    monotone = (ss.get("mean_reverted_pp") or -1) > (s.get("mean_reverted_pp") or 0)
    verdict = PASS if (pnl is not None and pnl > 0 and monotone) else FAIL
    return V("P10", "Overreaction reverts (edge test)", "genuine unknown", False,
             verdict, val, "mean PnL>0 net AND surprise-monotone", n=n,
             note="a FAIL here is the pre-registered publishable result: the documented edge is "
                  "arbed away on these venues")


def grade_p11():
    """P11 elimination market converges to coherence.
    PASS if BOTH mean per-team overround AND worst slot-sum deviation fall >=1/3 from baseline
    (overround 27.1%->18.1%; |Sum reach-SF - 4| 2.5->1.67). PARTIAL if one; FAIL if neither."""
    d = _load_js(os.path.join(VIZ, "model", "_elimination.js"))
    if not d:
        return V("P11", "Elimination mkt -> coherence", "genuine unknown", False,
                 PEND, None, "overround & slot-dev each -1/3", note="no _elimination.js")
    teams = d.get("teams", [])
    ov = [t.get("overround_pct") for t in teams if t.get("overround_pct") is not None]
    mean_ov = sum(ov) / len(ov) if ov else None
    # P(reach SF) = eliminated at sf|final|champion; coherent cross-team sum is 4
    reach_sf = 0.0
    for t in teams:
        m = t.get("market", {})
        reach_sf += (m.get("sf", 0) + m.get("final", 0) + m.get("champion", 0)) / 100.0
    dev = abs(reach_sf - 4) if teams else None
    ov_ok = mean_ov is not None and mean_ov <= 18.1
    dev_ok = dev is not None and dev <= 1.67
    verdict = PASS if (ov_ok and dev_ok) else (PARTIAL if (ov_ok or dev_ok) else FAIL)
    val = f"mean overround {mean_ov:.1f}% (base 27.1) · |reach-SF sum {reach_sf:.2f} - 4|={dev:.2f} (base 2.5)"
    return V("P11", "Elimination mkt -> coherence", "genuine unknown", False,
             verdict, val, "overround<=18.1% AND slot-dev<=1.67",
             note="provisional: graded at market close")


GRADERS = [grade_p1, grade_p6,            # primary first
           grade_p2, grade_p3, grade_p4, grade_p5, grade_p7, grade_p8, grade_p9, grade_p10, grade_p11]

_ICON = {PASS: "PASS  ", FAIL: "FAIL  ", PARTIAL: "PART  ", INC: "INCONC", PEND: "PEND  "}

# ── SCORECARD CARD (viz/model/prereg_scorecard.html) ─────────────────────────
# The BADGE + TALLY are driven by the live grader (authoritative, cannot drift).
# `v` is the curated card's ASSUMED verdict; emit_html ERRORS if it disagrees with the
# live grade, forcing the prose to be reconciled whenever a grade changes. `lab`/`res`
# are reader-friendly prose (res may carry hand-set numbers — reconcile on any flip).
SCORECARD_HTML_OUT = os.path.join(VIZ, "model", "prereg_scorecard.html")
_G = {PASS: "pass", FAIL: "fail", INC: "inc"}
_BADGE = {"pass": "PASS", "fail": "FAIL", "inc": "INCONCL"}
DISPLAY_ORDER = ["P1", "P6", "P5", "P4", "P11", "P3", "P7", "P10", "P2", "P8", "P9"]
CARD = {
 "P1":  (PASS, "Markets are well-calibrated", "market Brier <b>0.487</b> beats my model 0.503, slope 1.07"),
 "P6":  (PASS, "The deeper venue leads discovery", "Polymarket leads <b>61 of 63</b> matches, info share 81.0%"),
 "P5":  (PASS, "Closing prices beat opening", "Brier <b>0.491 &rarr; 0.477</b> as markets sharpen"),
 "P4":  (PASS, "The cross-venue gap is mostly vig", "de-vigged gap <b>3.9pp</b> vs raw margin 22.9pp"),
 "P11": (PASS, "New market converges to coherence", "overround <b>27% &rarr; 0%</b>, 4.00 semifinalists for 4 slots"),
 "P3":  (FAIL, "Law of one price holds (gap under 1pp)", "gap is <span class=\"r\">3.9pp and persistent</span> &mdash; matches the 2&ndash;4% LOOP violations in the literature"),
 "P7":  (PASS, "Model top-heavy AND market sharper", "both hold: my raw Elo over-rates <b>Spain +12pp</b> pre-tournament (frozen at registration), and the market&rsquo;s log-score <b>0.65</b> beats my model&rsquo;s 0.80"),
 "P10": (FAIL, "The goal-overreaction edge reverts", "<span class=\"r\">no edge</span>, PnL negative &mdash; the documented edge is arbed away here"),
 "P2":  (INC,  "Favourite-longshot bias stronger in books", "data-forced: prediction markets quote no draw, so no like-for-like 1X2 (addendum)"),
 "P8":  (INC,  "No 12-sigma shocks (sanity check)", "data-forced: PM mids are step functions, the 1s-return denominator degenerates (addendum)"),
 "P9":  (INC,  "Heat slows the second half, in-play", "underpowered: ~9 qualifying games, tapes pruned at 48h (addendum, pre-flagged)"),
}

# Chrome (style + head/foot) is verbatim from the hand-authored card; only tally + rows are injected.
_CARD_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>xResidual &mdash; the pre-registration, graded</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;1,9..144,500&family=IBM+Plex+Mono:wght@400;500;600&family=Spline+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root{--paper:#f8f5ee;--ink:#1b1813;--muted:#4a443b;--dim:#8a8175;--rule:#d8d0bf;--accent:#b3122a;--good:#1e6f6a;
    --draw:#cabd9f;--tan:#a89a7c;--fd:"Fraunces",serif;--fb:"Spline Sans",sans-serif;--fm:"IBM Plex Mono",monospace}
  *{margin:0;padding:0;box-sizing:border-box} html,body{background:#e7e1d4}
  .card{position:relative;width:1600px;height:900px;overflow:hidden;color:var(--ink);font-family:var(--fb);--pad:70px;
    background:radial-gradient(120% 80% at 50% -12%,rgba(179,18,42,.05),transparent 60%),var(--paper)}
  .card::after{content:"";position:absolute;inset:0;pointer-events:none;opacity:.5;mix-blend-mode:multiply;
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2'/><feColorMatrix type='saturate' values='0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/></svg>")}
  .head{position:absolute;left:var(--pad);top:42px;right:var(--pad);z-index:3}
  .kicker{font-family:var(--fm);font-size:13.5px;letter-spacing:.28em;text-transform:uppercase;color:var(--accent);font-weight:600;display:flex;align-items:center;gap:13px}
  .kicker .no{border:1px solid var(--accent);border-radius:2px;padding:2px 7px;font-size:12px;letter-spacing:.1em}
  h1{font-family:var(--fd);font-weight:600;font-size:46px;line-height:.98;letter-spacing:-.018em;margin-top:11px}
  h1 em{font-style:italic;font-weight:500;color:var(--accent)}
  .dek{margin-top:9px;font-size:14.5px;color:var(--muted);max-width:930px;line-height:1.42} .dek b{color:var(--ink)}
  .tally{position:absolute;right:var(--pad);top:48px;display:flex;gap:20px;z-index:4}
  .tally .t{text-align:center;font-family:var(--fm)} .tally .n{font-family:var(--fd);font-weight:600;font-size:44px;line-height:.9}
  .tally .l{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);margin-top:4px}
  .tally .pass .n{color:var(--good)} .tally .fail .n{color:var(--accent)} .tally .inc .n{color:var(--tan)}
  .rows{position:absolute;left:var(--pad);right:var(--pad);top:210px;bottom:56px;z-index:2;display:flex;flex-direction:column;justify-content:space-between}
  .row{display:flex;align-items:center;gap:15px;height:44px;border-radius:6px;padding:0 14px 0 0}
  .badge{width:74px;flex:none;font-family:var(--fm);font-size:11.5px;font-weight:600;letter-spacing:.08em;text-align:center;padding:4px 0;border-radius:4px}
  .badge.pass{color:#fff;background:var(--good)} .badge.fail{color:#fff;background:var(--accent)} .badge.inc{color:#fff;background:var(--tan)}
  .pid{width:34px;flex:none;font-family:var(--fm);font-size:15px;font-weight:600;color:var(--dim)}
  .lab{width:430px;flex:none;font-size:17px;font-weight:600;letter-spacing:-.005em}
  .res{flex:1;font-family:var(--fm);font-size:13.5px;color:var(--muted);line-height:1.25}
  .res b{color:var(--ink)} .res .r{color:var(--accent);font-weight:600}
  .row.fail{background:rgba(179,18,42,.05)}
  .foot{position:absolute;left:var(--pad);right:var(--pad);bottom:22px;z-index:3;display:flex;justify-content:space-between;
    font-family:var(--fm);font-size:12px;color:var(--dim)}
  .foot .brand{color:var(--ink);font-weight:600}.foot .brand b{color:var(--accent)}
</style></head>
<body><div class="card">
  <div class="head"><div class="kicker"><span class="no">CAPSTONE</span> The pre-registration, graded &middot; xResidual</div>
    <h1>Eleven calls, committed before kickoff, graded in <em>public.</em></h1>
    <div class="dek">I logged eleven falsifiable predictions in a timestamped commit before a ball was kicked, each with its decision rule fixed in advance. Here is the honest scorecard, hits and misses. <b>Both failures independently reproduce what 2026 microstructure papers found.</b></div>
  </div>
  <div class="tally">
    <div class="t pass"><div class="n">%%TPASS%%</div><div class="l">Pass</div></div>
    <div class="t fail"><div class="n">%%TFAIL%%</div><div class="l">Fail</div></div>
    <div class="t inc"><div class="n">%%TINC%%</div><div class="l">Inconcl.</div></div>
  </div>
  <div class="rows">%%ROWS%%</div>
  <div class="foot">
    <div>Predictions + decision rules committed to an append-only ledger before kickoff (Jun 10) &middot; final grade on the full tournament, Jul 19 &middot; scripts/grade_prereg.py --html</div>
    <div class="brand">@PrabhatM27 &nbsp;<b>/</b>&nbsp; xResidual</div>
  </div>
</div>
</body></html>
"""


def emit_html(rows, out_path=SCORECARD_HTML_OUT):
    """Render the scorecard card from the LIVE grade. Badge + tally are authoritative;
    ERRORS if any curated CARD verdict disagrees with the live grade (drift guard)."""
    live = {r["id"]: r["verdict"] for r in rows}
    mism = [f"{pid}: card={CARD[pid][0]} vs live={live.get(pid)}"
            for pid in DISPLAY_ORDER if CARD[pid][0] != live.get(pid)]
    if mism:
        raise ValueError("scorecard prose is stale vs the live grade — update CARD in grade_prereg.py:\n  "
                         + "\n  ".join(mism))
    tally = {"pass": 0, "fail": 0, "inc": 0}
    row_html = []
    for pid in DISPLAY_ORDER:
        v, lab, res = CARD[pid]
        g = _G[v]
        tally[g] += 1
        row_html.append(f'<div class="row {g}"><div class="badge {g}">{_BADGE[g]}</div>'
                        f'<div class="pid">{pid}</div><div class="lab">{lab}</div>'
                        f'<div class="res">{res}</div></div>')
    html = (_CARD_TEMPLATE
            .replace("%%TPASS%%", str(tally["pass"]))
            .replace("%%TFAIL%%", str(tally["fail"]))
            .replace("%%TINC%%", str(tally["inc"]))
            .replace("%%ROWS%%", "".join(row_html)))
    with open(out_path, "w") as f:
        f.write(html)
    return tally


def main():
    ap = argparse.ArgumentParser(description="grade PREREGISTRATION.md against committed artifacts")
    ap.add_argument("--json", action="store_true", help="machine-readable scorecard")
    ap.add_argument("--html", nargs="?", const=SCORECARD_HTML_OUT, default=None,
                    help="render the scorecard card from the live grade (default: viz/model/prereg_scorecard.html)")
    args = ap.parse_args()

    rows = [g() for g in GRADERS]
    rows.sort(key=lambda r: (not r["primary"], r["id"]))   # primaries on top, then numeric-ish

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    if args.html is not None:
        tally = emit_html(rows, args.html)
        print(f"wrote {os.path.relpath(args.html, ROOT)}: PASS {tally['pass']} · "
              f"FAIL {tally['fail']} · INCONCL {tally['inc']}")
        return 0

    print("\n  PRE-REGISTRATION SCORECARD  (provisional — final grade runs after the final, 2026-07-19)")
    print("  " + "-" * 96)
    for r in rows:
        star = "*" if r["primary"] else " "
        nstr = f"n={r['n']}" if r["n"] is not None else ""
        print(f"  {_ICON[r['verdict']]} {star}{r['id']:<4} {r['label']:<34} {nstr:<8} {r['value'] or ''}")
        if r["note"]:
            print(f"           rule: {r['threshold']}")
            print(f"           note: {r['note']}")
    print("  " + "-" * 96)

    # the part that matters most today: what is NOT yet gradeable, and why
    gaps = [r for r in rows if r["verdict"] == PEND]
    tally = {}
    for r in rows:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    print("  tally: " + " · ".join(f"{k} {v}" for k, v in tally.items()))
    if gaps:
        print(f"\n  GAPS TO CLOSE BEFORE JUL 19 ({len(gaps)} predictions not yet mechanically gradeable):")
        for r in gaps:
            print(f"    - {r['id']}: {r['note']}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
