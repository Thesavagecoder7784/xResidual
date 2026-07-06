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

---

## 2026-06-25 — P8 graded INCONCLUSIVE: the 1-second return-std denominator is degenerate

**What changed.** Nothing in the rule; this records that P8's committed metric cannot be meaningfully
evaluated on the captured data, per the Deviations clause. P8 measures z = (largest one-second mid
move in a match) / (standard deviation of one-second mid returns over the prior 30 minutes), per
contract, and asks whether the tournament's biggest z stays ≤ 4σ. Running the routine over the in-play
tapes (`scripts/build_sigma.py`, 10 matches) returns z of **40 to 390σ** on every game — not a fat-tail
finding but a divide-by-near-zero artifact.

**Why.** Prediction-market mids are step functions that sit flat almost every second: at the largest
move, the prior 30-minute window of one-second returns is **96–99.7% zeros** (nonzero fraction
0.003–0.039). The return standard deviation therefore collapses to the noise floor (~0.04–0.2¢), so an
ordinary goal-sized move (8–43¢) reads as hundreds of sigma. Requiring ≥5% nonzero activity does not
rescue it (still 80–350σ, and most matches have no contract that active). The metric implicitly assumes
a continuously-priced series (the equities setting it comes from); a sparse prediction-market mid is not
one. Found on 2026-06-25 in a check of the σ pool, not reverse-fit.

**Effect on the grade.** **P8 → INCONCLUSIVE**, reported as such, never a fabricated FAIL — reporting
"390σ, so the markets have 12-sigma shocks" would be a false finding, the opposite of what the data
shows. The grader (`scripts/grade_prereg.py`) now returns INCONCLUSIVE when the denominator is
degenerate (nonzero fraction < 0.10) rather than a bogus FAIL. Note in passing: Kalshi mids are sparser
than Polymarket's (the largest-z artifacts are mostly Kalshi), which is consistent with Polymarket
leading price discovery (P6) — Kalshi is the thinner follower. P8 was a secondary; the two primaries
(P1, P6) are unaffected, and no other prediction's metric is touched.

## 2026-07-06 — P9 graded INCONCLUSIVE: underpowered by construction, and the in-play half is not retro-computable

**What changed.** Nothing in the rule; this records that P9 resolves INCONCLUSIVE, exactly as its own
committed text pre-flagged. P9 (heat slows the second half) is a *secondary* test whose registered rule
already says: "**INCONCLUSIVE if fewer than 8 extreme-heat afternoon games are captured with clean in-play
data — likely, since there are only ~9 such games**," with an explicit power flag that it "will most likely
resolve INCONCLUSIVE." This entry puts the resolution on the record before the July-19 grade so it reads as
the disclosed limitation it always was, not a late dodge.

**Why.** Two independent reasons, either sufficient. (1) **Power:** the qualifying set — FIFPRO
extreme-risk city *and* afternoon kickoff — is only ~9 games for the whole tournament, below the committed
n≥8-with-clean-data threshold once the clean-in-play-data requirement is applied. (2) **Data:** the second
sub-metric, second-half drift of the de-vigged in-play total, needs the raw tick tapes, but those are pruned
at 48h to fit the VM's disk (only a trailing window survives — 13 tapes at grading time, none of them the
extreme-heat afternoon games, which were played earlier). So the in-play-drift half cannot be evaluated
retroactively at all, and PASS requires *both* halves to point the predicted way. The late-goal-rate half
(goals after the 75th minute, from goal timelines) is computable, but one half of a two-part conjunctive
test, on ~9 games, is not a gradeable result. This is the same data-forced posture as P8, disclosed in
advance rather than discovered.

**Effect on the grade.** **P9 → INCONCLUSIVE**, per its own registered power/data clause — reported as
such, not stretched into a PASS or FAIL off an underpowered half-metric. P9 was a secondary and a
deliberately-flagged genuine unknown; the primaries (P1, P6) and the scored FAIL/PASS results are
unaffected. All three inconclusives (P2, P8, P9) are now documented data-forced or underpowered
limitations, so the July-19 scorecard carries no undocumented gap.
