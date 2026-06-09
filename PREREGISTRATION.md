# xResidual — Pre-Registration of 2026 World Cup Market Predictions

**Locked:** 2026-06-08, before a ball is kicked (kickoff Jun 11).
**Graded:** 2026-07-19, after the final, in public, every line, hits and misses both.
**Lock mechanism:** this file is fixed at commit tag `prereg-v1`. It is never rewritten.
Any forced change goes in `PREREGISTRATION-ADDENDUM.md` (see Deviations). The commit
timestamp is the proof the calls came before the outcomes.

---

## Why this exists

Real research bets its reputation before the outcome is known. A claim that can't be
wrong isn't a finding. So I'm committing in public, in advance, to specific falsifiable
predictions about how the 2026 World Cup markets behave, each bound to the exact code and
threshold I'll grade it by. This is about market efficiency and microstructure, not about
beating the market. When a result shocks the board, that's the tournament doing its job,
never "the market was wrong."

To keep myself honest, three commitments up front:
- **No moving the goalposts.** Every metric, function, and threshold is fixed in this
  file. I don't get to choose them on July 19.
- **Power and novelty are labeled.** Each prediction is tagged either *genuine unknown*
  (the outcome is not yet visible) or *observed, extrapolated* (already true in the
  buildup; I'm betting it persists, which is weaker evidence). Match-level claims have
  real sample (about 104 matches); title-outcome claims are N=1 and are not scored.
- **Multiplicity is controlled.** Two predictions are named **primary**; the rest are
  secondary. I report all of them regardless, so I can't cherry-pick a "hit" after the
  fact.

---

## Binding methods (fixed now, no post-hoc choices)

These remove the researcher degrees of freedom. They apply to every prediction below.

- **Data.** Logged snapshots in `logger/data/snapshots-*.jsonl`, window 2026-06-05 to the
  final. In-play tick data captured via `logger/ws_capture.py`. Nothing is hand-edited.
- **De-vigging.** Always multiplicative, via `devig.implied_probabilities(method=
  "multiplicative")`. No alternative de-vig is tried.
- **Universe.** Title market: the 48 qualified teams. Cross-venue gap claims: the top-12
  teams by market probability at each pass. Match claims: all completed matches.
- **Missing / void.** Abandoned or walkover matches are dropped. A team is included in a
  cross-venue pass only if both venues quote it (per `microstructure.cross_venue_divergence`).
  Draws count as their own W/D/L outcome.
- **Scoring.** Proper rules only: `calibration.brier_score` and `residual.log_score`.
  Calibration via `calibration.calibration_regression` (returns intercept a, slope b) and
  `calibration.corp` (isotonic MCB / DSC / UNC with 500-sample bootstrap bands).
- **Decision states.** Each prediction resolves to PASS, FAIL, or INCONCLUSIVE. Capture
  -dependent predictions have a stated minimum n; below it the verdict is INCONCLUSIVE and
  reported as such, never quietly dropped.
- **Code-before-data.** Two metrics aren't implemented yet (P6, P8). Their methods are
  fully specified here, and the code (`microstructure.information_share`, the σ routine)
  will be committed **before any in-play data is captured**, so the method still predates
  the data it grades.

---

## Primary predictions (named in advance)

### P6 [PRIMARY · genuine unknown] Cross-venue lead-lag: the deeper venue leads
**Claim.** When a goal reprices the in-play markets, the deeper book (Polymarket or the
Betfair Exchange) leads Kalshi more often than the reverse.
**Metric.** Hasbrouck information share from a VECM on time-aligned, de-vigged mid-price
series around each goal (`microstructure.information_share`, committed before capture).
Computed on **mid-price moves, not signed flow**: public WebSocket trade-direction is only
~59% accurate (Hawkes et al. 2026), so signed metrics use the on-chain layer instead.
Cross-check: sign of the cross-correlation peak in `microstructure.lead_lag` (already
implemented).
**PASS** if, over n ≥ 20 clean goal shocks, the deeper venue's information share exceeds
50% in a majority of events. **FAIL** if Kalshi leads. **INCONCLUSIVE** if n < 20.
**Buildup reading:** Polymarket quotes ~27× the depth of Kalshi at equal spread, which
motivates the direction without proving it.

### P1 [PRIMARY · genuine unknown] The markets are well-calibrated
**Claim.** De-vigged match (1X2) prices are calibrated: teams priced near p% win about p%.
**Metric.** `pipeline.calibration_report(which="mkt")` → CORP (`calibration.corp`) plus
the calibration regression slope b.
**PASS** if the CORP reliability band contains the identity line across the bulk of the
support (no systematic miscalibration) AND slope b ∈ **[0.70, 1.30]** AND market Brier <
the raw model's Brier on the same matches. The wide slope band is deliberate: ~104 matches
is a modest sample, so I report the slope with its bootstrap CI rather than pretend to
tight precision.
**Buildup reading:** near-zero (~2%) overround on the title field; untestable until results.

---

## Secondary predictions

### P2 [secondary · genuine unknown] Favourite–longshot bias: in the books, weaker in PMs
**Claim.** De-vigged sportsbook (1X2) prices overprice longshots vs how often they win;
the prediction markets show less of it.
**Metric.** `calibration.reliability_table` by venue; compare the lowest priced-probability
bin's (predicted − observed) gap, books vs PMs, with Wilson CIs.
**PASS** if the book gap exceeds the PM gap. Graded **directional** (one tournament of
longshots is thin); effect size and CI reported, not a precise coefficient.
**Buildup reading:** de-vigged, books price longshots ~1.5× higher than PMs (slope 0.92).

### P5 [secondary · genuine unknown] Price discovery: closing beats opening
**Claim.** Prices sharpen toward kickoff.
**Metric.** `pipeline.closing_line_wdl` at the last pre-kickoff snapshot vs the first
logged snapshot (opening), both de-vigged; Brier on each.
**PASS** if closing Brier < opening Brier on resolved matches, pooled across venues.
**Buildup reading:** discovery code in place; no in-play data yet.

### P7 [secondary · part observed, part unknown] Model more top-heavy; market better-calibrated
**Claim.** The raw Elo/Skellam model gives the title favourite a higher probability than
the market, and the market out-forecasts the raw model on matches.
**Metric.** (a) title odds from `build_blend_check.py` (raw Elo vs market); (b)
`pipeline.skill_comparison` log-score, market vs baseline.
**PASS** if (a) raw-Elo favourite prob beats the market's by ≥ 5pp pre-tournament
[*observed*: Spain ~28% vs ~16%], AND (b) market mean log-score < raw-model mean log-score
[*genuine unknown*].
**Note.** Squad-value blend cuts title-odds error vs Opta from ~4.7pp to ~0.7pp — a
consistency check against two forecasters, not a backtest (no historical squad values).

### P3 [secondary · observed, extrapolated] Law of one price holds
**Claim.** Kalshi and Polymarket de-vigged title prices stay close all tournament.
**Metric.** Mean absolute de-vigged top-12 cross-venue gap (`microstructure
.cross_venue_divergence`) over the full series.
**PASS** if that mean stays ≤ **1.0pp** through the final.
**Buildup reading:** ~0.14–0.15pp; largest standing gap England (~1pp). *Already true; I'm
betting it persists.*

### P4 [secondary · observed, extrapolated] The visible gap is mostly vig
**Claim.** Most of the raw cross-venue gap is house margin, and Kalshi's margin stays the
larger.
**Metric.** Raw vs de-vigged mean gap, and per-venue overround, from `build_basis.py`.
**PASS** if the de-vigged mean gap is < **half** the raw mean gap over the series, AND
Kalshi overround > Polymarket overround at the close.
**Buildup reading:** de-vig collapses the gap to ~0.15pp; overround Kalshi ~4.4% vs PM
~3.0%. *Already true; betting it persists.*

### P8 [secondary · genuine unknown] Sigma-sanity: the big shocks are small
**Claim.** The largest single-match in-play repricings are modest, no "12-sigma" events.
**Metric.** z = (largest one-second mid-price move in the match) / (standard deviation of
one-second mid returns over the prior 30 minutes), per contract. Routine committed before
capture.
**PASS** if the biggest z of the tournament is ≤ **4σ**, with typical largest shocks 2–3σ.
**Buildup reading:** none yet; defined here so it can't be reverse-fit.

### P9 [secondary · genuine unknown · underpowered] Heat slows the second half (in-play)
**Claim.** Heat's *pre-match* effect on total goals is a null (Finding 13), so this tests
the channel the sports-science literature actually supports — in-play intensity. In
extreme-heat afternoon games (FIFPRO extreme-risk city + afternoon kickoff) the second half
slows, so the **late-goal rate is lower** and the **in-play total drifts toward the under
faster** than in cool/evening games.
**Metric.** (a) late-goal rate = goals after the 75th minute per match, extreme-heat
afternoon games vs the rest; (b) second-half drift of the de-vigged in-play total from the
match captures, extreme vs cool. Routine committed before capture.
**PASS** if both point the predicted way (lower late-goal rate AND faster under-drift in
extreme-heat games). **INCONCLUSIVE** if fewer than 8 extreme-heat afternoon games are
captured with clean in-play data — likely, since there are only ~9 such games.
**Power flag.** Underpowered by construction (~9 games); this is a pre-registered *test* of
the in-play channel, not a claim, and will most likely resolve INCONCLUSIVE. Stated anyway
so the reframe (heat is in-play, not a pre-match goals factor) is on the record in advance.

### P10 [secondary · genuine unknown] Goal-overreaction reverts (the edge test)
**Claim.** In-play prices **overreact to surprising goals** and partially revert within a
few minutes (documented at ~2-3% per trade; Choi & Hui, "Role of Surprise"). I test whether
a *fixed* fade rule still captures it on 2026 World Cup prediction markets, net of costs.
**Metric & rule (frozen in committed code before kickoff, so this is out-of-sample):** on
each auto-detected goal shock (≥4¢ mid move), take the side **against** the move, enter
**+2 min**, exit **+6 min**, charge a **0.5pp** round-trip cost (`ws_events.overreaction_backtest`,
`scripts/overreaction_run.py`). Surprise = |jump| / pre-price.
**PASS** if mean per-trade PnL is **> 0** net of cost across captured shocks **and** the
reversion is larger for higher-surprise goals. **FAIL** if mean PnL ≤ 0 (the classic edge
is gone / arbed away on PMs). **INCONCLUSIVE** if fewer than 20 clean captured shocks.
**Honesty.** This is my one explicit *trading-edge* test. I can't trade it (F-1); the point
is to validate or falsify a documented edge on live data with a pre-committed rule. A FAIL
("this edge no longer exists on prediction markets") is a real, publishable finding, not a
disappointment.

### P11 [secondary · genuine unknown] The new elimination market converges to coherence
**Claim.** Polymarket's brand-new "stage of elimination" market is incoherent today: **~27%
mean overround** and cross-team reach-sums far above the bracket's slots (it prices **~6.5
semifinalists vs 4**, ~1.4 champions vs 1). As it matures and results resolve uncertainty,
it should converge toward coherence.
**Metric.** From the daily captured series (`build_elimination.py` -> `_elimination.js`):
(a) mean per-team overround; (b) the worst slot-sum deviation, e.g. |Σ reach-SF − 4|.
**Baseline (locked at first commit, 2026-06):** overround 27.1%, Σ reach-SF = 6.5 (so the
worst slot-sum deviation |Σ reach-SF − 4| = 2.5), Σ champion = 1.42.
**PASS** if, at the market's close, both (a) the mean per-team overround and (b) the worst
slot-sum deviation have each fallen **by at least one-third** from baseline (overround
27.1% → ≤ 18.1%; deviation 2.5 → ≤ 1.67). **PARTIAL** if exactly one clears the one-third
bar; **FAIL** if neither improves or either widens.
**Pro-market note.** This predicts the market *becoming* efficient, not that it is "wrong"
now: a new, thin market learning coherence in real time, time-stamped before it tightened.

---

## Descriptive calls: single-realization (N=1), reported but NOT scored

The format/model implies these. One tournament can't score them, so I report what happened
without claiming a graded hit.

- **D1.** Third-place cut-line ~3 points (one win); ~30 teams live for the 8 berths.
- **D2.** Incentive incompatibility: in Groups C and A the runner-up's first-two-round path
  projects easier (Brazil ~48 Elo, Mexico ~28). Realized opponent strengths reported.
- **D3.** Best-third cushioning: a strong side that finishes third (e.g. Senegal, Group I)
  still advances; the draw's real damage falls on Pot 3–4 bubble teams (Tunisia, Australia).
- **D4.** Highest-leverage group games are midtable six-pointers, not favourite-vs-favourite.
- **D5.** Altitude and heat are exposure, not edges. I commit now to *not* claiming a heat
  or altitude goals edge after the fact.

---

## What would make me wrong (and that's fine)

- Kalshi leading price discovery (P6 FAIL). Genuinely interesting if it happens.
- The prediction markets showing more favourite–longshot bias than the books (P2 FAIL).
- The raw model out-calibrating the market (P7b FAIL) — the market left something on the table.
- Cross-venue gaps blowing past 1pp in-tournament (P3 FAIL) — segmented venues, not one market.

## Deviations

If reality forces a change (a venue API breaks, capture fails, a match is abandoned), I log
it in `PREREGISTRATION-ADDENDUM.md` with the date and reason, and grade the original rule as
INCONCLUSIVE where it can't be met. **This file is never edited after the `prereg-v1` tag.**

Every line gets a public hit / miss / inconclusive with the number on 2026-07-19. The
misses are the point.

*Method in [METHODOLOGY.md](METHODOLOGY.md). Numbers regenerate from
`scripts/run_analysis.py`. Pro-market throughout: this measures how sharp these markets
are, not where they're "wrong."*
