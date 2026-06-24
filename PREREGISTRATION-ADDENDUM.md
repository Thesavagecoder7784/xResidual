# Pre-registration addendum

Logged deviations and methods corrections to [PREREGISTRATION.md](PREREGISTRATION.md),
per its "Deviations" clause. Each entry is dated and reasoned. Corrections made *before*
any in-tournament data is graded (kickoff 2026-06-11) are method fixes, not result-driven
choices; they are recorded here so the public record shows exactly what changed and why.

---

## 2026-06-09 — CORP consistency bands now computed under the null of calibration (affects P1)

**What changed.** `calibration.corp` previously built its bands by a *pair bootstrap*
(resample the (forecast, outcome) pairs, refit isotonic/PAV, take pointwise percentiles).
That produces a confidence band for the *fitted* recalibration curve — an object centered
on the fit, not the 45° line — which is the wrong reference for the P1 calibration test and,
because it resampled the flattened W/D/L points independently, also treated a match's three
mutually-exclusive outcomes as independent (effective n ≈ 3× too large, bands ~√3 too narrow).

The band is now the **Dimitriadis–Gneiting–Jordan (2021) consistency band**: the forecasts
are held fixed, outcomes are resampled *from* them under the null that the forecasts are
calibrated, PAV is refit, and the pointwise 2.5/97.5 percentiles form the band. The **match is
the resampling unit** — one coherent categorical outcome (exactly one of home/draw/away) is
drawn per match — so the dependence among a match's three events is respected. Under the null
the band brackets the 45° identity line, and the P1 test reads: *the estimated CORP curve stays
within the band across the bulk of the support.*

**Why now.** This is a methods bug in the uncertainty quantification, found in a pre-kickoff
code review on 2026-06-09. It is fixed before any live match is graded, so it cannot be
outcome-driven. The point estimates (MCB / DSC / UNC and the exact Brier identity) are
unchanged; only the band — and the wording of the P1 PASS rule — is corrected.

**Effect on the grade.** The P1 PASS condition still requires (a) no systematic miscalibration
on the reliability diagram, (b) slope b ∈ [0.70, 1.30], and (c) market Brier < raw-model Brier.
Only the construction of (a)'s band changed; the threshold, the slope window, and the Brier
comparison are untouched. The corrected band is wider (correct outcome dependence) and correctly
centered, so if anything it is a *more conservative* test of calibration.

**Code.** `xresidual/calibration.py::corp` (new `wdl_n` argument; null-of-calibration
resampling). Callers passing match-level grouping: `xresidual/pipeline.py`,
`scripts/calibration_backtest.py`, `scripts/make_figures.py` (via `plots.reliability_diagram`).
Validated by `tests/test_calibration.py` (decomposition identity + low-MCB-under-calibration).

---

## 2026-06-10 — Confederation-bias correction added to the rating (affects the §12 simulation, not a scored prediction)

**What changed.** The simulation's input rating now applies a per-confederation
empirical-Bayes offset before the squad-value blend (`xresidual/confed_bias.py`, METHODOLOGY
§13). Pure Elo is zero-sum and confederations are near-disconnected clusters, so weak ones
inflate; the offset re-levels them using cross-confederation results only, shrunk per team by
its cross-confederation game count. This shifts advancement/title probabilities (CONCACAF/AFC/OFC
down, UEFA/CONMEBOL up; New Zealand's advance prob ~39% → ~20%).

**Why now / why it's not result-driven.** Found in a pre-kickoff model review on 2026-06-09–10
and fixed before any live match is graded. It is calibrated and validated entirely on the
historical results (`scripts/calibrate_confed_offsets.py`): a time-split, cross- vs within-
confederation stratified backtest, +4.6% out-of-sample cross-confederation RPS, Diebold–Mariano
p≈0.009 over a flat offset, within-confederation slice unchanged (placebo). No in-tournament
data touches it.

**Effect on the grades.** None to the *prediction* rules. The simulation is not itself a scored
prediction (it's the §12 independent forecaster, used as a sanity check vs market/Opta in P7).
If anything it strengthens P7's "model converges to the market" reading: post-correction the
model agrees with the de-vigged bookmaker consensus at 0.95 rank correlation (median 0.2pp). The
P1 calibration test runs on the per-match baseline (§2), which is unaffected.

## 2026-06-10 — Goal-overreaction shock detector hardened (binding method for P10)

**What changed.** `xresidual/ws_events.detect_shocks` now fires only on a mid move **≥5pp within
60s that PERSISTS** (retains ≥50% of the jump 20s later), with a **5-minute refractory**
(previously 4pp / 30s, no persistence check). This rejects thin-market noise blips and stops one
goal's gradual reprice being counted multiple times.

**Why now.** Tuned in a pre-kickoff dry-run capture of the Argentina–Iceland friendly
(2026-06-09), where the un-hardened detector turned 3 real goals into 11 "shocks." Fixed before
the tournament; no graded P10 trade has occurred (the friendly is a dry-run, excluded from the
P10 record because a favourite-win has no *surprising* goal to fade).

**Effect on the grade.** P10's decision rule (fade a detected shock, enter +2min, exit +6min, net
of modeled cost) is unchanged; only the shock-*detection* thresholds are tightened, and they are
now frozen for the tournament. The change makes the test *more* conservative (fewer, cleaner
events), and is logged here so the P10 record can't be accused of a post-hoc threshold tweak.

---

## 2026-06-24 — P2 graded INCONCLUSIVE: the prediction markets do not quote the draw

**What changed.** Nothing in the rule; this records that P2's bound metric cannot be computed, per
the Deviations clause ("grade the original rule as INCONCLUSIVE where it can't be met"). P2 compares
the favourite-longshot bias in the bookmakers' **1X2** (win/draw/loss) prices against the prediction
markets', using `calibration.reliability_table` *by venue*. Building the grader surfaced that Kalshi
and Polymarket list only **two-way** per-match contracts on these World Cup games (a team-to-win
`match`/`winner` market with no draw outcome); only the Odds-API bookmaker feed prices a three-way
1X2. There is therefore **no PM-side 1X2 reliability curve** to put opposite the books, so the
book-vs-PM comparison the prediction names is not defined on the captured data.

**Why now.** Found on 2026-06-24 while building `scripts/grade_prereg.py`, the mechanical grader for
this file. It is a property of what the venues *list*, not a modelling choice, and it cannot be made
outcome-driven (the missing draw contract was never available to fit to).

**Effect on the grade.** **P2 → INCONCLUSIVE**, reported as such, never quietly dropped. The
book-side longshot reliability is still computable and may be reported *descriptively* (one venue,
no graded comparison). P2 was a *secondary*, directional, explicitly thin prediction; the two named
primary predictions (P1, P6) are unaffected. No other prediction's metric is touched.
