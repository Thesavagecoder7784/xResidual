# xResidual — one page

*A live, pre-registered study of the two main prediction-market venues, run through the 2026 World
Cup. Longer: [README](../README.md) · the retraction: [CORRECTION.md](../CORRECTION.md) · every number
traced to the script that made it: [REPRODUCING.md](../REPRODUCING.md).*

**The setup.** Own tick capture on Kalshi and Polymarket across 86 matches, an independent forecasting
model whose every forecast was timestamped against the live price before kickoff, and eleven
falsifiable predictions committed to a tagged commit before the tournament started. They were graded
in public on 19 July; after one grade was revised toward caution in September, the tally is **5 pass, 2
fail, 4 inconclusive**. Everything but the raw tapes, which the
venues' terms restrict, rebuilds from a clean clone.

**Fair value.** On the 72 group games the model forecast before kickoff, the de-vigged market scored
a Brier of 0.487 against my model's 0.503, with a calibration slope of 1.07 against 0.87 — the
market was better calibrated and my model's probabilities ran too extreme. The Brier gap on its own is
not significant (paired p = 0.25), so the claim is calibration, not a win. Seven of my eight worst
calls were draws, and on those the market already carried the realised outcome 2.7 points higher than I did. Where an independent model and a liquid
price disagree, the prior should be that the model is wrong.

**What the cross-venue gap is worth.** Walking both order books level by level, net of Kalshi's fee,
discarding sub-tick flicker and requiring at least half a cent per contract of net edge: the entire
World Cup cross-venue arbitrage held about $4,855 of capacity for about $38 of locked profit, and the
winner market — the deepest book — netted zero, efficient to the tick. An unfiltered version of the
same walk had reported $427–$1,200, which was phantom depth on longshot books. What separates the two
venues is cost, not opinion: de-vigged they sat a median 0.17 points apart over the 20 days on which
both books normalized, while overround ran 5.6% on Kalshi against 2.1% on Polymarket. The crowds only
partly overlap: the international Polymarket book captured here is close-only for US users, who trade a
separate CFTC-regulated exchange, and Kalshi restricts several dozen jurisdictions.

**In-play.** A goal moves the price a median 12.0¢, comfortably more than a follower pays in spread,
but the quote books only about a third of an independent model's fair move in log-odds and undershoots
on all 22 goals where it moved. The dislocation is still mostly not tradeable: both books empty at the
goal and refill in three to four seconds, leaving about 9% of goals harvestable and clustered in
matches that could not be identified in advance. Both pre-registered tests of tradability came back
null — a convergence trade lost 0.21 points per trade, and ex-ante prediction of which matches would be
harvestable scored an AUC of 0.274 against a permutation p = 0.50.

**The measurement failure, and why it's the most useful part.** The original headline was a sub-second
cross-venue lead. It is withdrawn. Kalshi's price was read from a channel capped at one message per
second while Polymarket's came from a full book updating about every 10 ms, so one venue was late by
construction — and a synthetic Kalshi with a lead of exactly zero, observed at the real timestamps,
reports Polymarket first in 26 of 29 windows, which is the published result. Inverting the 427
published measurements against the estimator's measured response recovers no systematic lead in either
direction. Two other numbers died the same way: the $1,200 arbitrage above, and an information-share
figure broken by a floating-point residue in my own replacement rebuild, caught on review. A
sentence-level claim checker, pinned by its own regression tests, now fails CI if any withdrawn
figure is restated as fact on a public page.

**Paper book.** 46 positions, all closed: +$148 on $1,452. The favourite–longshot lane on advance
markets made +$181, and it is the one market where closing-line value also backs the model — 74% of 46
directional calls drifted its way by the close. The reach-round lane's +$88 has no such support, so it
counts as outcome rather than edge, and the two lanes flagged as edgeless before trading lost $117.

**Next.** The November midterms settle the lead question cheaply and on macro contracts: build the
Kalshi mid from `orderbook_delta`, which the logger already records, run the known-truth placebo before
estimating anything, and pre-register the test first.
