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
average. The published lead was 600 ms.

## How it was established

Not by argument. By a test where the right answer is known in advance
([`scripts/sampling_bias_check.py`](scripts/sampling_bias_check.py)):

- Take real Polymarket price paths around real goals. Build a "Kalshi" that is **the same price at the
  same instant** — a lead of exactly zero — and observe it at Kalshi's real one-per-second timestamps.
  The published estimator reports **Polymarket first in 26 of 29 windows, at a median +600 ms.**
- Give the same estimator both prices at full resolution and it recovers the true lead exactly. The
  fault is the sampling, not the estimator.
- A true 300 ms *Kalshi* lead still reads as Polymarket-first.
- The information share fails the same way: whichever venue is sampled faster gets the larger share,
  and swapping which one that is swaps the "leader". On the one match whose Kalshi book could be rebuilt
  and verified, Polymarket's share falls from 88% to 53%.

The calm-play placebo and the exogenous goal clock, which the original analysis relied on, could not
catch this: both check things downstream of the price series, and both inherit the problem.

## What changes

- **Withdrawn:** the +600 ms lead, the 72% first-mover share, the 57-of-66 per-match lean, the
  clock-verified 75%, the 81.0% component and 75.2% Hasbrouck information shares, and the
  goal-vs-calm contrast (86% vs 53%).
- **Withdrawn:** that the leading venue's order book empties hardest at a goal. With both venues
  sampled the same way, the comparison reverses.
- **Regraded:** pre-registered prediction P6 ("the deeper venue leads price discovery") moves from
  PASS to INCONCLUSIVE, so the scorecard is now **5 pass / 2 fail / 4 inconclusive**, not 6 / 2 / 3.
  The reasoning is logged in [PREREGISTRATION-ADDENDUM.md](PREREGISTRATION-ADDENDUM.md) (entry A-P6).

## What does not change

Everything that did not depend on Kalshi's timing at second resolution:

- The market out-calibrated my pre-registered model (market Brier 0.487 vs 0.503; calibration slope
  1.07 vs 0.87). P1, the other named primary, still passes.
- The cross-venue gap is margin, not disagreement: 0.17 pp de-vigged on every day both books
  normalized, against overround of 5.6% on Kalshi and 2.1% on Polymarket.
- The market under-reacts to goals, booking about a third of the model's fair move. This was measured
  on Polymarket alone, 30 seconds after each goal.
- Order books empty at a goal on both venues, so the dislocation a follower would chase has nothing
  resting behind it. Once-a-second sampling made Kalshi's book look *deeper* than it was, so the
  un-harvestable conclusion is, if anything, understated.

## What the data does say

The estimator's response to a known lead is measurable, so the 427 published lead measurements can be
inverted against it ([`scripts/lead_deconvolution.py`](scripts/lead_deconvolution.py), validated on
known inputs before use). The recovered distribution of true leads: **38% Kalshi first, 39% no lead,
23% Polymarket first.** There is real cross-venue structure, in both directions, and no systematic
Polymarket lead. This is exploratory, not a pre-registered result.

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
