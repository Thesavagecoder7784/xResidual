# Correction: the cross-venue lead-lag finding is withdrawn

*2026-09-18.*

Until this date, this repository, its site and its desk note said that **Polymarket discovers the
price of a goal before Kalshi**: first in 72% of 392 repricing events, by a median of +600 ms, with an
81.0% Gonzalo-Granger information share and a lead in 61 of 63 cointegrated matches. That finding is
withdrawn. It was produced by how the data was read, not by the markets.

## What went wrong

The capture recorded both venues at full resolution. The analysis did not use it that way.

Kalshi's mid-price was built only from Kalshi's `ticker` channel
([`xresidual/ws_events.py:111`](xresidual/ws_events.py#L111),
[`scripts/stream_micro.py:63`](scripts/stream_micro.py#L63)). Kalshi documents that channel as
event-driven, but it is capped at one message per second per market: in the busiest seconds of a match
the order book changes 200–380 times while the ticker sends at most one message. Polymarket's mid was
rebuilt from its full order book, updating roughly every 10 ms. Kalshi's own full-resolution
`orderbook_delta` stream was subscribed to and recorded on every capture, and never read.

A price you only look at once a second always looks late — by up to a second, about half a second on
average. The published lead, now withdrawn, was 600 ms.

## How it was established

Not by argument. By a test where the right answer is known in advance
([`scripts/sampling_bias_check.py`](scripts/sampling_bias_check.py)):

- Take real Polymarket price paths around real goals. Build a "Kalshi" that is **the same price at the
  same instant** — a lead of exactly zero — and observe it at Kalshi's real one-per-second timestamps.
  Given that zero-lead market, the published estimator reports **Polymarket first in 26 of 29 windows,
  at a median +600 ms.**
- Give the same estimator both prices at full resolution and it recovers the true lead to within one
  200 ms bin. The fault is the sampling, not the estimator.
- A true 300 ms *Kalshi* lead still reads as Polymarket-first.
- The information share is not identified either. With no lead at all, sampling alone hands the
  always-fresh series 95–100% of the Hasbrouck share on all four contracts tested, and relabelling which
  venue is sampled faster moves the "leader" with it. With both venues rebuilt at full resolution and
  checked against Kalshi's own quotes (three contracts, two matches), Polymarket's component share goes
  from 94% to 51%, from 88% to 85%, and from 85% to 71%. So the published 81%, now withdrawn, measured
  the sampling as much as the markets; at full resolution Polymarket still carries the larger share on
  two of the three contracts, and three contracts cannot say how large a real lead, if any, would be.

The calm-play placebo and the exogenous goal clock, which the original analysis relied on, could not
catch this: both check things downstream of the price series, and both inherit the problem.

## What changes

- **Withdrawn:** the +600 ms lead, the 72% first-mover share, the 57-of-66 per-match lean, the
  clock-verified 75%, the 81.0% component and 75.2% Hasbrouck information shares, and the
  goal-vs-calm contrast (86% vs 53%).
- **Withdrawn:** that the leading venue's order book empties hardest at a goal. With both venues
  sampled the same way (21 goal shocks across 2 matches), it does not hold: Kalshi's book collapses at
  least as hard.
- **Regraded:** pre-registered prediction P6 ("the deeper venue leads price discovery") moves from
  PASS to INCONCLUSIVE, so the scorecard is now **5 pass / 2 fail / 4 inconclusive**, not 6 / 2 / 3.
  The reasoning is logged in [PREREGISTRATION-ADDENDUM.md](PREREGISTRATION-ADDENDUM.md) (entry A-P6).

## What survives, and its limits

The results that do not rest on Kalshi's timing at second resolution:

- The market out-calibrated my pre-registered model (market Brier 0.487 vs 0.503; calibration slope
  1.07 vs 0.87). P1, the other named primary, still passes.
- The cross-venue gap is mostly margin, not disagreement: a median 0.17 pp de-vigged across the 20
  days both books normalized, against overround of 5.6% on Kalshi and 2.1% on Polymarket. Pre-registered
  P3 still fails as graded: its de-vigged gap reached 3.98 pp at the close, as the field resolved.
- The market under-reacts to goals: on the 8 matches whose goal timeline validates against the final
  score, it books about a third of the model's fair move, undershooting on all 22 goals where the
  quote moved. This was measured on Polymarket alone, 30 seconds after each goal. It is a small sample.
- Order books empty at a goal on both venues, so most of the move a follower would chase has little
  resting behind it. Two limits: "the median match yields nothing" uses the harshest depth measure, the
  low point across the goal, and where the raw book survives (21 events, 2 matches), depth read at the
  moment a follower could act leaves 11–33% of those events harvestable. And the harvest ledger picks
  which venue is "the follower" by the same timing comparison withdrawn above. The defensible claim is
  that most of the dislocation is not harvestable, not that none of it is.

## What the data does say

The estimator's response to a known lead is measurable, so the 427 published lead measurements can be
inverted against it ([`scripts/lead_deconvolution.py`](scripts/lead_deconvolution.py), validated on
known inputs held out from the fit). The recovered distribution of true leads is about **58% Kalshi-first, 8% no lead and 35% Polymarket-first** (bootstrap 95% intervals 44–67%, 0–35% and 19–44%, resampling matches). Treat the split as rough: it moves with how the model is specified (an
earlier, narrower specification gave 38/39/23), and the Kalshi and Polymarket intervals touch. What held
in every specification is that Kalshi-first events outnumber Polymarket-first ones and that there is no
systematic Polymarket lead. This is exploratory, not a pre-registered result.

## Where the old material is

The desk note, the price-discovery writeup, the blog post, the SSRN draft and the June 14
microstructure pre-registration are in [`archive/cross-venue/`](archive/cross-venue/), unchanged. The
scripts stay where they were, because the tests above run on them. The full audit — every result sorted
by whether it survives — is [`writeups/recovery-audit.md`](writeups/recovery-audit.md).

## Why it was missed

Every check this project ran asked whether the numbers were consistent: prose against artifacts,
artifacts against rebuilds, the paper against a fresh clone. None asked whether the input was right.
A pipeline can be perfectly self-consistent and uniformly wrong. The known-truth placebo that exposed
this took about an hour to build; it should have been the first test, not the last.
