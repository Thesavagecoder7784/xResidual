# Cross-Venue Price Discovery in Prediction Markets: Evidence from the 2026 World Cup on Kalshi and Polymarket

**Prabhat M.**
Purdue University — Mathematics & Statistics
Working paper · July 2026 · *Draft — comments welcome*
Code & data: github.com/Thesavagecoder7784/xResidual · Contact: pmanijam@purdue.edu

---

## Abstract

Using a purpose-built, millisecond-resolution capture of the order books of two large real-money prediction markets — Kalshi and Polymarket — across the entire 2026 FIFA World Cup, I measure which venue discovers price first when information arrives. Across 86 matches captured at tick resolution, Polymarket leads the repricing of a goal on 72% of decisive events (264 of 371, median lead ~600 ms) and, on a Hasbrouck (1995) / Gonzalo–Granger (1995) information-share decomposition computed on de-vigged mid-quotes, carries a ~80% share of price discovery, leading 61 of 63 cointegrated matches. Because the decomposition uses mid-quotes rather than signed trades, it is immune to the ~59% trade-direction-classification problem that limits public-feed studies of Polymarket. The result is cluster-robust (match-resampling bootstrap; per-match sign test p ≈ 3×10⁻⁹; design effect 1.13). Discovery concentrates sharply at the news: Polymarket's information share rises to ~86% in goal windows versus ~53% in calm play, and at the goal the book withdraws to ~0.5% of normal depth. A depth- and fee-gated harvestability ledger shows the lead is *mostly un-harvestable* — the ~12¢ stale-quote gap nets ~+10.8¢ on paper but is not capturable at size: 0% of goals clear a tradeable-depth bar (0% in the deepest-liquidity knockouts), and across all leads the median edge is smaller than the taker fee. The finding directly addresses the cross-venue price-discovery question that recent Polymarket microstructure work names but leaves open, and refines a concurrent claim of "economically meaningful" cross-venue arbitrage: the informational lead is real; the alpha is not.

**Keywords:** prediction markets; price discovery; market microstructure; information share; order flow; adverse selection; Kalshi; Polymarket.
**JEL:** G14, G13, D47, D82, C58.

---

## 1. Introduction

Prediction markets have grown into liquid, real-money venues whose prices are increasingly treated as forecasts of real-world events. As two large venues — the CFTC-regulated exchange Kalshi and the on-chain platform Polymarket — now list economically equivalent contracts on the same events, a basic microstructure question arises: **when new information arrives, which venue discovers the price first?**

The recent literature has begun to answer this for U.S. election contracts. Ng, Peng, Tao & Zhou (2026) find that Polymarket leads Kalshi in price discovery, particularly when liquidity is high, and that net order imbalance from large trades predicts returns. But two gaps remain. First, the result is established only on slow-moving election markets; whether the same venue leads on **fast, in-play information events** — and in a different asset class — is untested. Second, the leading single-venue Polymarket microstructure study (Dubach, 2026) explicitly leaves cross-venue price discovery as its named open question, because trade direction inferred from Polymarket's *public* feed matches on-chain ground truth only ~59% of the time, corrupting any signed-flow comparison.

This paper fills both gaps using a natural experiment with an unusually clean information structure: the 2026 World Cup, a three-week sequence of ~100 matches in which goals are discrete, exogenous, precisely-timed shocks. I capture both venues' full order books at millisecond resolution for 86 matches and ask, three ways at increasing rigor, which venue prices a goal first. Because all three measures are built on **mid-quotes and book changes rather than signed trades**, they sidestep the trade-direction problem by construction.

The contribution is threefold. (i) I show Polymarket's price-discovery leadership, established for elections, **generalizes to in-play sports**, with an information share of ~80% and a ~600 ms reaction lead. (ii) I show the lead **concentrates at the news event** and is accompanied by a collapse of quoted depth — adverse selection observed in real time. (iii) I show the lead is **mostly un-harvestable** after the cost of immediacy, refining the "economically meaningful arbitrage" reading of the cross-venue gap: what looks like free money is the compensation a liquidity supplier demands for standing in front of information-motivated flow. The project is pre-registered — eleven falsifiable predictions were committed to a timestamped repository before kickoff and graded in public — and reports its nulls and one retraction alongside its confirmations.

## 2. Data

A single-clock collector records, 24/7 for the tournament, (a) Kalshi via its WebSocket/REST API and (b) Polymarket via its CLOB WebSocket, capturing top-of-book and full-depth updates, plus an Odds-API bookmaker-consensus layer as an external sharp benchmark, and an on-chain layer that reads Polymarket `OrderFilled` events from the Polygon CTF Exchange to recover ground-truth signed flow. For each match I pair contracts referencing the identical outcome (one Kalshi ticker and one Polymarket token per team and the draw), de-vig each venue's quotes to probabilities via a common multiplicative de-vig, and align the two mid-price series on a common millisecond clock. The event study runs on 86 matches; the information-share estimates run on the 60 matches (100 contracts) whose cross-venue spread passes an Augmented Dickey–Fuller cointegration guard. Order-book tapes routinely exceed one million events per match.

## 3. Methods

I measure the same phenomenon three ways, so the conclusion does not rest on any single technique.

**3a. Event-study reaction lead.** I detect repricing shocks (goals) on each venue's mid series and cross-correlate the two around each event to estimate which mid moves first, to the millisecond.

**3b. Information shares (the core).** The two de-vigged mids for one outcome are cointegrated with the natural vector (1, −1). On the ADF survivors I fit a bivariate vector error-correction model and report the Hasbrouck (1995) information-share bounds and the ordering-free Gonzalo–Granger (1995) permanent-component share. The venue that adjusts *less* to the spread is the one others converge toward — the price-discovery leader.

**3c. Mechanism.** I reconstruct order-flow imbalance (OFI) from top-of-book changes (Cont, Kukanov & Stoikov, 2014) and test (i) whether OFI moves each venue's own price and (ii) whether one venue's flow predicts the other's next move, and I recompute the lead on the imbalance-weighted microprice.

## 4. Results

**The winner market is efficient.** As a control, the de-vigged outright-winner prices agree across venues to within ~0.4 pp; there is no cross-venue level mispricing. The effect below is about *speed of discovery*, not level disagreement. Benchmarked against a sharp bookmaker line across 48 teams, Polymarket's mean absolute gap is 0.18 pp versus Kalshi's 0.26 pp, and Polymarket is closer on 22 teams to Kalshi's 11 — the venue that updates first also sits closest to the sharpest consensus.

**Polymarket leads, three ways.**

| Measure | Sample | Result |
|---|---|---|
| Reaction lead (event study) | 86 matches, 392 decisive events | Polymarket first in 264 (71%), median +600 ms |
| Reaction lead, per match (cluster-robust) | 64 matches | 57 of 66 lean Polymarket (sign test p ≈ 3×10⁻⁹; design effect 1.13) |
| Gonzalo–Granger share | 63 cointegrated matches | Polymarket ~80% (median), leads 61 of 63 (p ≈ 3×10⁻¹⁵) |
| Hasbrouck share (band) | 100 contracts | Polymarket ~74–92% |
| OFI → own-venue price impact | 81 matches | strong within-venue, both directions |
| OFI cross-venue lead | 81 matches | null — no clean asymmetry either direction |

All three point the same way. The mechanism check sharpens the interpretation: order flow clearly drives price *within* each venue but shows *no* cross-venue lead — the lead lives in the *price*, not in observable flow. Polymarket's mid simply updates to new information first.

## 5. The anatomy of a goal

Conditioning on the actual information event turns the pooled ~80% into a dynamic picture and answers the question any price leader should be asked: is the lead tradeable?

- **Discovery concentrates at the news.** Away from goals the venues are near-coequal (~53/47); the instant a goal lands, Polymarket carries ~86% of the permanent price move.
- **The same venue withdraws liquidity hardest.** At the goal the spread blows out (~8× on Polymarket, ~2× on Kalshi) and best-price depth collapses to under 1% of normal, refilling only after a few seconds. Unlike a betting exchange, which suspends on a goal (Croxson & Reade, 2014), these CLOBs never halt — so this is *informational* liquidity withdrawal, not a mechanical suspension.
- **So the lead is real but mostly not tradeable.** A naive ledger makes the stale follower look like free money: ~12¢ of staleness, +10.8¢ net of the spread, on every goal. But that quote has vanished — depth at the goal is ~0.5% of normal — so once gated on what is actually resting in the book, essentially **0% of goals clear a tradeable-depth bar at size, the four deepest-liquidity knockouts included** where one would put real size. Across all leads, the median edge (~0.5¢) is smaller than the taker fee (~1.4¢), so ~85% are net-negative after fees. Finding an edge and correctly measuring how little of it survives is the point.
- **The market under-reacts to the goal it just priced.** Benchmarked against a calibrated clock-and-Poisson model anchored to the pre-match price, the post-goal move is a median ~0.55× the model's fair jump in log-odds, under-shooting in 7 of 8 cleanly-reconstructed matches, with negligible reversion — a persistent under-reaction, reported as suggestive (the cluster-honest unit is the match).

## 6. Robustness

**Immune to the trade-direction problem.** Dubach (2026) shows trade direction inferred from Polymarket's public feed matches on-chain ground truth only ~59% of the time, flipping the sign of effective spread on ~67% and Kyle's λ on ~60% of markets. Every estimate here is computed on mid-quote moves and book changes, not signed trades, so it is unaffected.

**No spurious shares.** The ADF gate drops non-cointegrated pairs, so an information share is reported only where the (1, −1) spread is genuinely stationary.

**Significance, stated honestly.** Goal events cluster within matches. The naive binomial and bin-level OFI t-statistics therefore overstate significance; the unit that carries the claim is the *match*. A match-resampling bootstrap gives an ICC of ~0.03 and a design effect of 1.13, and the per-match sign tests are decisive: 57 of 66 matches lean Polymarket on the reaction lead and 61 of 63 on the information share.

## 7. What this is *not*

**Not a trade.** The lead is a few hundred milliseconds and, at the goal, sits behind a book that has evaporated and a taker fee larger than the median edge. Documented cross-venue arbitrage exists but is fee-bounded and structural (Gebele & Matthes, 2026, attribute persistent ~2–4% cross-venue gaps to "semantic non-fungibility," not information). This is price-discovery *leadership* — a property of market structure — not free money. **Scope:** one tournament, one sport, a ~three-week window, 63 cointegrated matches; the format-agnostic price-discovery layer generalizes, the sport-specific magnitudes may not.

## 8. Conclusion

On a clean, repeated in-play information stream, Polymarket discovers the price of a goal first — ~600 ms ahead, ~80% of the information share, on 61 of 63 cointegrated matches — generalizing to fast sports events a result previously shown only for slow election contracts, and doing so on mid-quotes so it survives the trade-direction problem that limits public-feed work. The lead is genuine but mostly un-harvestable: it *is* the cost of immediacy, not alpha. The natural next step is the on-chain signed-flow layer — a ground-truth VPIN / order-flow-toxicity study that the public-feed literature cannot execute — and the generalization of the same cross-venue stack to macro and event contracts where the volume, and the stakes, are larger.

---

## References

- Cont, R., Kukanov, A., & Stoikov, S. (2014). The price impact of order book events. *Journal of Financial Econometrics*, 12(1), 47–88.
- Croxson, K., & Reade, J. J. (2014). Information and efficiency: Goal arrival in soccer betting. *The Economic Journal*, 124(575), 62–91.
- Dubach, [initials] (2026). The anatomy of a decentralized prediction market: Microstructure evidence from the Polymarket order book. *arXiv:2604.24366*.
- Gebele, [initials], & Matthes, [initials] (2026). Semantic non-fungibility and violations of the law of one price in prediction markets. *arXiv:2601.01706*.
- Gonzalo, J., & Granger, C. (1995). Estimation of common long-memory components in cointegrated systems. *Journal of Business & Economic Statistics*, 13(1), 27–35.
- Hasbrouck, J. (1995). One security, many markets: Determining the contributions to price discovery. *The Journal of Finance*, 50(4), 1175–1199.
- Ng, [initials], Peng, [initials], Tao, [initials], & Zhou, [initials] (2026). Price discovery and trading in modern prediction markets. *SSRN 5331995*.
- Qin, [initials], & Yang, [initials] (2026). Polymarket-v1: An on-chain prediction-market microstructure database. *arXiv:2606.04217*.

*Author note: reference initials and the on-chain signed-flow extension are to be completed before submission. Numbers current as of the tournament final; the pre-registration and its public grade are in the repository.*
