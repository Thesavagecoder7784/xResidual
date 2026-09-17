# What survives the sampling-bias finding

*2026-09-17. Companion to `scripts/sampling_bias_check.py` and `scripts/matched_sampling_depth.py`,
whose artifacts (`writeups/_sampling_bias_results.json`, `writeups/_matched_sampling_results.json`)
hold the numbers quoted here.*

## The defect, in one paragraph

Every Kalshi price in this repository is read from Kalshi's `ticker` channel, which publishes on a
fixed 1 Hz cadence (`xresidual/ws_events.py:107`, `scripts/stream_micro.py:63`). Every Polymarket
price is rebuilt from that venue's full book stream, which updates about every 10 ms. Kalshi's own
`orderbook_delta` stream, also ~10 ms, was subscribed to and recorded on every capture and never
used. A price observed once a second is observed late by construction, and the cross-venue estimator
cannot tell that apart from a venue being slow.

The size of the effect is measured, not assumed. Feeding the published estimator a synthetic Kalshi
that is *identical to Polymarket* — a true lead of exactly zero — observed at Kalshi's real ticker
timestamps returns **Polymarket first in 26 of 29 windows at a median +600 ms**, which is the
published headline. The bias runs +500 to +700 ms at every true lag tested, and a true 300 ms
*Kalshi* lead still reads as Polymarket-first. At full resolution the same estimator recovers the
true lag exactly, so the bias is the sampling and not the estimator.

## The rule for reading everything else

A result is affected if it needs Kalshi *timing* at second or sub-second resolution. A result is
unaffected if it uses Kalshi *levels* (a quote once a second is ample for a daily or hourly
quantity), a Polymarket-only series (full resolution), bookmaker lines, or the model ledger.

## Stands

| Result | Why it is unaffected |
|---|---|
| Calibration: market Brier 0.487 vs model 0.503 (p=0.25), CORP in-band, slope 1.07 vs 0.87 | Closing quotes + model ledger; no tape timing |
| Law of one price: 0.17 pp de-vigged gap on the 20 days both books normalize; overround 5.6% vs 2.1% | Poller snapshots, daily |
| P5 (closing beats opening Brier) and P7b (market vs model log score), n=89 each | Odds API bookmaker lines |
| Under-reaction: market books 0.34x the model's fair log-odds move, 22 of 22 goals, 8 matches | Measured on the **Polymarket** mid at +30 s. Immune |
| Detection over-fires at 1.25 events per goal vs the exogenous clock (104 matches, 308 goals, reconciled 104/104) | A count against an external clock |
| Both forward-test nulls: convergence trade -0.21 pp/trade; ex-ante harvestable-match AUC 0.274 vs permutation p=0.50 | Snapshots and per-match aggregates |
| The book collapses at the goal | Holds on both venues under both samplings (below) |
| Pre-registration, its grading, CLV, the reproducibility apparatus | Independent of the tape |

## Falls

| Claim | Evidence against |
|---|---|
| +600 ms lead; Polymarket first in 72% of 392 events; 57 of 66 per-match lean; clock-verified 75% | A zero-lead placebo reproduces all of it |
| Gonzalo-Granger 81.0% / Hasbrouck 75.2% | Zero-lead placebo hands the fresh series 74-250% GG and 95-100% Hasbrouck; label-flip makes *Kalshi* lead; at matched full resolution Polymarket falls 88%->53% (Spain) and 85%->71% (Argentina) |
| Information share concentrates at news (86% goal vs 53% calm) | Same inputs; the contrast is also what coarse sampling predicts |
| "The venue that leads is also the one whose book vanishes hardest" | Reverses under matched sampling: Kalshi collapses harder at both matched resolutions |
| Cross-venue OFI null | Kalshi order flow is 1 Hz, so the null is partly mechanical attenuation. Keep it as a null; do not cite it as evidence |
| Which venue is "the follower" in the harvest ledger | Assigned by the same biased reaction-time comparison |

## The matched-sampling test on depth

Median depth at the goal as a fraction of calm (21 shocks, 3 contracts; Kalshi rebuilds used only
where they match Kalshi's own quotes 97% of the time):

| contract | Poly, full res | Poly, cut to 1 Hz | Kalshi, 1 Hz ticker | Kalshi, full book |
|---|---|---|---|---|
| England | 0.35% | 3.5% | 0.09% | (rebuild not trusted) |
| France | 1.6% | 5.1% | 0.14% | (rebuild not trusted) |
| Spain | 3.6% | 25.2% | 1.55% | 0.30% |

Two things follow. The collapse is **real on both venues at every sampling** — the book does empty at
the goal, which is the mechanism the harvestability result rests on. But the *comparison between*
venues was an artifact of resolution: at matched sampling Kalshi's book collapses harder, the
opposite of what the paper says. Kalshi's 1 Hz depth also **understates** its own collapse, so the
un-harvestable conclusion is conservative with respect to this defect. The goal-sized move itself is
unchanged (7.31c on the ticker series, 7.31c on the full book), so the ledger's gross is not a
stale-quote effect.

## What could resurrect the lead claim

Nothing in this repository. The raw tapes survive for three matches holding 15 of the 392 events, and
one of the three carries no Polymarket. A future capture can settle it cheaply — build the Kalshi mid
from `orderbook_snapshot` + `orderbook_delta`, which the existing logger already records — but this
tournament cannot be re-estimated.

## Public surfaces still carrying the withdrawn numbers

`README.md`, `FINDINGS.md`, `METHODOLOGY.md`, `PREREGISTRATION.md` (P6 discussion),
`docs/method.html`, `docs/index.html`, `docs/lab.html`, `writeups/price_discovery_note.html`,
`writeups/ssrn_paper.md`, `writeups/blog_post.md`, `writeups/cross-venue-price-discovery.md`,
`writeups/lead-lag.md`, `writeups/retrospective.md`, `paper/theses.md`.
