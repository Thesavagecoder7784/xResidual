# What survives the sampling-bias finding

*2026-09-17, revised 2026-09-19 after two independent reviews. Companion to
`scripts/sampling_bias_check.py`, `scripts/matched_sampling_depth.py` and
`scripts/lead_deconvolution.py`, whose artifacts (`writeups/_sampling_bias_results.json`,
`_matched_sampling_results.json`, `_lead_deconvolution_results.json`) hold the numbers quoted here.*

## The defect, in one paragraph

Every Kalshi price in this repository is read from Kalshi's `ticker` channel (`xresidual/ws_events.py:111`,
`scripts/stream_micro.py:63`). Kalshi documents it as event-driven, but in practice it is capped at one
message per second per market: in the busiest seconds of a match the book changes 200–380 times and the
ticker still sends at most one message. Every Polymarket price is rebuilt from that venue's full book
stream, which updates about every 10 ms. Kalshi's own `orderbook_delta` stream, also ~10 ms, was recorded
on every capture and never used. A price observed once a second is observed late by construction, and the
cross-venue estimator cannot tell that apart from a venue being slow.

The size of the effect is measured, not assumed. Fed a synthetic Kalshi *identical to Polymarket* — a
lead of exactly zero — observed at Kalshi's real ticker timestamps, the published estimator reports
**Polymarket first in 26 of 29 windows at a median +600 ms**, the published headline. The bias runs +500
to +700 ms at every true lag tested, and a true 300 ms *Kalshi* lead still reads as Polymarket-first. At
full resolution the same estimator recovers the true lag to within one 200 ms bin, so the bias is the
sampling, not the estimator.

## The rule for reading everything else

A result is affected if it needs Kalshi *timing* at second or sub-second resolution. It is unaffected if
it uses Kalshi *levels* over hours or days, a Polymarket-only series, bookmaker lines, or the model
ledger. Kalshi's spread and depth sit in between: they come from the same capped feed, so they are coarse
at the one-second scale.

## Stands

| Result | Why it is unaffected, and its limits |
|---|---|
| Calibration: market Brier 0.487 vs model 0.503 (p = 0.25), CORP in-band, slope 1.07 vs 0.87 | Closing quotes and the model ledger |
| Venues mostly agree: a median 0.17 pp de-vigged gap over the 20 days both books normalized; overround 5.6% vs 2.1% | Daily snapshots. Pre-registered P3 still fails as graded, at the close, as the field resolved |
| P5 (closing beats opening Brier) and P7b (market vs model log score), n = 89 each | Bookmaker lines |
| Under-reaction: on the 8 matches whose goal timeline validates, the market books 0.34× the model's fair log-odds move, undershooting on all 22 goals where the quote moved | Polymarket mid at +30 s. The broader ~3pp read pools 17 matches whose reconstructed goals don't match the final score; the outcome test behind it rests largely on one stoppage-time goal (Ghana–Panama) |
| Detection over-fires at 1.25 events per goal vs the exogenous clock (104 matches, 308 goals) | A count against an external clock |
| Both forward-test nulls: convergence trade −0.21 pp/trade; ex-ante harvestable-match AUC 0.274 vs permutation p = 0.50 | Snapshots and per-match aggregates |
| The book collapses at the goal on both venues | Holds under both samplings where it can be compared (below: 15 shocks with a trusted Kalshi rebuild) |
| Pre-registration, its grading, CLV, the reproducibility apparatus | Independent of the tape |

## Falls

| Claim | Evidence against |
|---|---|
| +600 ms lead; Polymarket first in 72% of 392 events; 57 of 66 per-match lean; clock-verified 75% | Withdrawn: a zero-lead placebo reproduces the sign and the median |
| Gonzalo–Granger 81.0% / Hasbrouck 75.2% | Withdrawn as a measurement of the markets. With no lead, sampling alone gives the fresh series 95–100% of the Hasbrouck share on all four contracts tested, and the component share leaves [0, 1] on three of them. Relabelling which venue is fresh moves the "leader". With both venues at full resolution (three trusted contracts), Polymarket's component share goes 94%→51%, 88%→85% and 85%→71%: inflated, and not identified, but not reversed |
| Information share concentrates at news (86% goal vs 53% calm) | Withdrawn: same inputs, and the contrast is what coarse sampling predicts |
| The leading venue's book empties hardest | Withdrawn: with both venues sampled alike (21 shocks, 2 matches), Kalshi's book collapses at least as hard |
| Cross-venue order flow | Correlations no larger than 0.025 at any lag, on the same capped Kalshi feed. Not zero, but too small to carry a lead; not evidence either way |
| Which venue is "the follower" in the harvest ledger | Assigned by the withdrawn timing comparison. On England (14 shocks), the ticker labels Kalshi the follower 64% of the time and the full book 0% |

## The matched-sampling test on depth

Median depth at the goal as a fraction of calm. Kalshi's book is rebuilt from its snapshot and delta
messages and used only where the rebuild matches Kalshi's own ticker quote at least 95% of the time.

| contract | shocks | Poly, full res | Poly, cut to 1 Hz | Kalshi, 1 Hz ticker | Kalshi, full book |
|---|---|---|---|---|---|
| England | 14 | 0.35% | 3.5% | 0.09% | 0.0% |
| France | 6 | 1.6% | 5.1% | 0.14% | (rebuild not trusted: 82%) |
| Spain | 1 | 3.6% | 25.2% | 1.55% | 0.30% |

The collapse holds on both venues under both samplings. The *comparison between* venues does not survive:
at matched sampling Kalshi's book collapses at least as hard as Polymarket's. The goal-sized move is
unchanged by the sampling (England 7.65¢ on the ticker vs 7.75¢ on the full book; Spain 7.31¢ both ways).

An earlier version of this table used a rebuild with a floating-point bug — emptied price levels kept a
residue above the "live" threshold — which left England and one other contract untrusted and produced an
information-share figure (88% → 53%) that has since been corrected. Sizes are now held to Kalshi's 2-dp
fixed point.

One caution on harvestability that the sampling does not settle: the published "median match yields no
harvestable goal" uses the harshest depth statistic, the low point across the goal. On the 21 events
where the raw book survives, depth read at the instant a follower could act leaves 11–33% of them
harvestable. The defensible claim is "mostly not harvestable", not "never".

## Can anything be salvaged? By inverting the measurement, roughly

Comparing both venues one second apart is fair but uninformative: at 1 Hz with 200 ms bins, a sub-second
lead of either sign collapses to "synchronous". What works is to measure the estimator's response to a
*known* input — shift a real Polymarket path by a known lag, observe it at 1 Hz, record what the estimator
reports — and invert the 427 published measurements against that response by non-negative least squares
(`scripts/lead_deconvolution.py`). The current version fixes problems a review found in the first: bins
centred on the 200 ms grid, a lag grid to ±7 s (measured lags reach ±8 s), a noise component, a bootstrap
that resamples matches and the windows behind the response, and self-tests held out from the fit.

Held-out known-truth self-tests: a true zero reads 76% no-lead (17% leaks to Polymarket), a true 600 ms Polymarket
lead 97% Polymarket, a true 300 ms Kalshi lead 89% Kalshi.

| Recovered true lead | share | bootstrap 95% |
|---|---|---|
| Kalshi first | 58% | 44–67% |
| No lead | 8% | 0–35% |
| Polymarket first | 35% | 19–44% |

Read this as rough. The model has 18 components and 15 bins, so it fits almost anything (chi-square 0.6),
and the split moves with the specification: a narrower lag grid gave 38/39/23. The response is also built
from each match's cleanest event, which is not a random sample of the 427. What held in every version is
that Kalshi-first events outnumber Polymarket-first ones and that there is no systematic Polymarket lead.
Two direct reads agree with that direction: the published median lead (+400 ms) sits below what the
zero-lead placebo produces (+600 ms), and Kalshi-first readings are common in the published data (111 of
427) while the zero-lead placebo produces them in 1 of 29 windows.

**What can be claimed.** Not "Polymarket leads". The venues are within about a second of each other
in-play, with no systematic ordering and some sign that Kalshi leads more often than it follows. The
published ordering was produced by the feed cadence.

## What could resurrect the lead claim

Nothing in this repository. The raw tapes survive for three matches holding 15 of the 392 events, and one
of the three carries no Polymarket. A future capture can settle it cheaply — build the Kalshi mid from
`orderbook_snapshot` + `orderbook_delta`, which the logger already records — but this tournament cannot be
re-estimated.

## Public surfaces

Corrected on 2026-09-18 and revised 2026-09-19: `README.md`, `FINDINGS.md`, `METHODOLOGY.md`,
`REPRODUCING.md`, `CORRECTION.md`, `writeups/retrospective.md`, `viz/README.md`, the pre-registration
scorecard (P6 regraded on the information-share placebo, entry A-P6), and the site. The withdrawn material
moved unchanged to `archive/cross-venue/`; `docs/note.html` and `docs/lab.html` stay at their URLs behind a
correction banner. `scripts/check_claims.py` fails if a withdrawn figure is stated as fact, judged one
sentence at a time, and `tests/test_correction_guard.py` pins it against every bypass the review found.

Outside this repository and still to correct: the portfolio site at thesavagecoder7784.github.io.
