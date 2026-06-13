# Cross-Venue Price Discovery in World Cup Prediction Markets

**Working draft, 2026.** Prabhat M. ([repo](https://github.com/Thesavagecoder7784/xResidual) · [portfolio](https://thesavagecoder7784.github.io/))

> Status: this is a live, phased note. The pre-match microstructure results (Sections 5.1, 6)
> are final; the in-play price-discovery and event-study results (Sections 5.2, 5.3) and the
> pre-registration grade (Section 7) fill in as the 2026 World Cup is played and are marked
> ⟦PENDING⟧. Every empirical claim here is bound to code and to a pre-registration committed
> before kickoff (PREREGISTRATION.md), so the open results are falsifiable, not flexible.

---

## Abstract

Two large real-money prediction markets, Kalshi (US, regulated) and Polymarket (global,
on-chain), priced every 2026 World Cup outcome continuously alongside the Betfair Exchange and
the global bookmaker consensus. Using millisecond-resolution order-book and trade captures
across all three venues, plus an on-chain trade-flow layer reconstructed from Polymarket's CTF
Exchange, we study **where price is discovered**: which venue moves first when information
arrives, and whether that leadership flips between the quiet pre-match regime and the
high-information in-play regime. We decompose each cross-venue quote into belief and margin and
find the widely-quoted "5 to 8 cent" inter-venue gap is **almost entirely the house margin**:
de-vigged, the two prediction markets agree to ~0.15pp on the title race, and a relative-value
convergence trade returns a documented loss net of costs. The residual belief gap is small but
structured by audience (a home-crowd tilt). The central price-discovery result, estimated via
Hasbrouck (1995) information share and Gonzalo-Granger (1995) component share on mid-price
moves around ⟦N⟧ goal events, is reported in Section 5.2. We pre-register the direction (the
deeper-liquidity venue leads) and grade it honestly.

**Contribution.** The cross-venue, pre-match-vs-in-play price-discovery comparison across
regulated, on-chain, and exchange venues is, to our knowledge, the named-but-unexplored
question in the recent prediction-market microstructure literature; everything else here is a
careful replication or a methods contribution (the confederation-shrinkage baseline correction,
Section 4.3, and the on-chain trade-direction layer, Section 3.2).

---

## 1. Introduction

Real-money prediction markets aggregate dispersed information into a single live probability.
The 2026 World Cup is a natural experiment: a 39-day, 104-match global event priced
simultaneously by a US-regulated venue (Kalshi), a global on-chain venue (Polymarket), and a
mature betting exchange (Betfair), with a dense, exogenous, and precisely-timed information
stream (goals). The recent literature (Hawkes et al., 2026; the prediction-market SoK, 2026)
maps the field and names a gap: **cross-venue price discovery has not been measured**, in
particular whether discovery leadership differs between the low-information pre-match window and
the high-information in-play window. This note answers that question.

We ask three things, in order of novelty:

1. **Price discovery (novel).** When information arrives, which venue's mid-price moves first,
   and does the answer flip pre-match vs in-play? (Sections 5.2, 5.3.)
2. **Law of one price (replication).** How large is the true cross-venue belief gap once each
   venue's overround is removed, and is there a tradeable convergence edge? (Sections 5.1, 6.)
3. **Calibration and the favorite-longshot bias (replication).** Are these markets
   well-calibrated on a 48-team field, and is the favorite-longshot bias weaker in prediction
   markets than in bookmakers? (Section 5.4, ⟦PENDING⟧ final calibration.)

Framing note, held throughout: the market is the subject, not the opponent. Where our
independent model disagrees with a liquid price, the prior is that the model is wrong, and we
test that prior against a third source before claiming an edge (Section 4.3).

## 2. Related work

- **Price discovery.** Hasbrouck (1995) information share and Gonzalo-Granger (1995) component
  share are the standard tools for attributing price discovery across venues trading one asset;
  we apply them to de-vigged mid-prices to sidestep the order-direction problem (Section 3.2).
- **Soccer betting and information.** Croxson and Reade (2014) show betting prices update
  efficiently and near-instantly to goals, with no systematic drift, the in-play benchmark our
  event study (5.3) builds on.
- **Favorite-longshot bias.** Snowberg and Wolfers (2010) decompose the bias into risk-love vs
  misperception; we measure its strength by probability decile and compare books vs prediction
  markets (5.4).
- **Prediction-market efficiency / microstructure.** Hawkes et al. (2026) and the SoK (2026)
  survey efficiency and microstructure of modern (incl. on-chain) prediction markets and flag
  cross-venue discovery as open. ⟦confirm exact titles/venues for both references⟧

## 3. Data and infrastructure

### 3.1 Capture
A 24/7 collector logs Kalshi and Polymarket order books and the Odds API bookmaker/exchange
lines on a fixed cadence, and, per marquee match, a millisecond WebSocket capture records every
book and trade message from both prediction venues to an append-only tape with a local-clock
timestamp on each event. A dry-run friendly capture recorded ~172k events at a 6ms median
inter-event time (Section 5.3), so timestamp resolution is far finer than the tens-of-seconds
scale on which a goal reprices, the regime where lead-lag is identified. Connection-control
events (connect / disconnect / sequence gap) are logged in-band so the analyzer masks venue
outages rather than mistaking them for quiet markets.

### 3.2 The order-direction problem and the on-chain layer
Inferring trade direction from a public WebSocket feed is unreliable (a documented ~59%
classification ceiling), which corrupts any order-flow-imbalance (OFI) signal. We avoid it two
ways: (i) all price-discovery estimation uses **mid-price moves**, which are direction-agnostic;
and (ii) for true signed flow we read Polymarket's CTF Exchange `OrderFilled` events directly
from the chain (Polygon RPC / subgraph), giving exact taker direction for the OFI study (5.5).

## 4. Methods

### 4.1 De-vigging
Implied probabilities are recovered from quotes by multiplicative de-vigging (removing each
venue's overround), so cross-venue comparisons are belief-to-belief, not quote-to-quote. The
closing (last pre-kickoff) quote is the calibration forecast.

### 4.2 Price discovery
On the synchronized de-vigged mid-price series for a contract across venues, we estimate the
Hasbrouck (1995) information share (with the standard upper/lower bounds) and the
Gonzalo-Granger component share, computed separately for the pre-match and in-play windows. The
event study (5.3) classifies each goal by surprise (pre-goal win-probability of the scoring
side) and measures the reaction path: overshoot magnitude and mean-reversion half-life,
following the overreaction-to-surprise literature.

### 4.3 The independent baseline and its correction
An Elo-plus-squad-value goal model (Skellam goal-difference, Dixon-Coles low-score correction,
format-aware Monte Carlo) serves as an **independent reference**, not a competitor to the
market: it lets us ask "where do model and market disagree, and who is right" against a third
source (de-vigged bookmaker match odds). A methods contribution falls out of this: raw Elo
inflates near-disconnected confederations (they mostly play themselves), so we apply an
empirical-Bayes confederation shrinkage estimated from inter-confederation "bridge" games and
scaled per team by global connectivity. It validates out-of-sample (+4.6% cross-confederation
ranked-probability score, Diebold-Mariano p ~= 0.009; within-confederation untouched as a
placebo).

## 5. Results

### 5.1 Law of one price holds; the visible gap is margin (final)
De-vigged, Polymarket and Kalshi title prices agree to **~0.15pp on average** across the 48-team
field; the largest standing gap is England (~1pp). The "5 to 8 cent" gap the press quotes is
**mostly the house margin**: Kalshi's overround runs ~5.4% vs Polymarket's ~3.0% (~1.8x), so the
durable venue difference is *cost, not price*. Anchored to the Betfair Exchange (the sharpest
soccer market we log), Polymarket sits marginally closer to the sharp line (mean abs error
~0.12pp vs ~0.16pp). The small surviving belief gap is **structured by audience**: the American
book is richer on USA, Mexico, Netherlands; the global book on England, Portugal, Japan, Brazil,
a home-crowd tilt.

A liquidity asymmetry underlies this: Polymarket quotes roughly **27x the depth of Kalshi at the
same spread** on the title market, so the two venues are integrated on price but very different
on capacity.

### 5.2 Cross-venue price discovery ⟦PENDING in-play sample⟧
> Hasbrouck information share and Gonzalo-Granger component share, Kalshi vs Polymarket (and vs
> Betfair), pre-match vs in-play, over ⟦N⟧ goal events from the marquee-match captures.
> Pre-registered direction (P6): the **deeper-liquidity venue leads**, and we expect the
> in-play window to sharpen the leadership relative to the quiet pre-match window. Fills as the
> tournament generates clean in-play tapes; first marquee captures in hand, sample accruing.

### 5.3 Goal-shock event study ⟦PENDING in-play sample⟧
> Per goal (target ~260 over the tournament): surprise classification, overshoot, and
> mean-reversion half-life, with abnormal-return windows, benchmarked against Croxson-Reade
> (efficient, near-instant updating, no drift). Framework validated on the first live tape
> (5.6); the sample is the tournament itself.

### 5.4 Calibration and the favorite-longshot bias ⟦calibration PENDING; FLB descriptive, in⟧
The favorite-longshot bias is visible pre-tournament in the 1-cent tick structure of longshot
contracts. The half-spread by probability decile and the books-vs-prediction-markets comparison
are reported here as a **descriptive replication** (Snowberg-Wolfers, 2010); the *graded*
calibration verdict (CORP reliability, Brier decomposition, slope) lands after the group stage
and again at the final, and is pre-registered (P1: the markets are well-calibrated).

### 5.5 Order-flow imbalance to short-horizon returns ⟦PENDING in-play sample⟧
> On-chain signed OFI regressed on next-interval mid return; coefficient, R-squared, and regime
> dependence. The on-chain layer and the regression are built; the in-play volume is the input
> that accrues.

### 5.6 Infrastructure validation (final)
The in-play pipeline was proven end-to-end before the tournament on a warm-up friendly:
~172k events at 6ms median spacing, with the goal-shock detector hardened from 11 false triggers
to 3. The capture is live and self-correcting (Section 3.1).

## 6. A disclosed signal and forward-test: a clean null (final)

The law-of-one-price result (5.1) predicts there is no convergence arbitrage to harvest, and we
tested that out-of-sample rather than asserting it. Rule: when the de-vigged Polymarket-Kalshi
belief gap on a title widens past 1.0pp, go long the cheap venue and short the rich one, exit on
convergence below 0.3pp or after a horizon, net of a 0.5pp modeled round-trip cost
(fee + half-spread). Buildup result: **6 trades, -2.6pp total, 0% hit rate, per-trade Sharpe
-1.95.** The gap is real but does not converge enough to clear costs: the visible "edge" is a
cost illusion, exactly what law-of-one-price implies. Reported as a negative result because it
is one; the in-play goal-shock signal (5.3) is the forward-test that continues live.

## 7. Pre-registration and grading ⟦PENDING Jul 19⟧

Six falsifiable, dated predictions were committed to a tagged git commit before kickoff
(PREREGISTRATION.md), with binding methods, named primaries, and PASS/FAIL/INCONCLUSIVE decision
states under proper scoring rules. The two primaries are **P6** (cross-venue lead-lag: the
deeper venue leads) and **P1** (the markets are well-calibrated). Graded publicly on 2026-07-19.

## 8. Discussion and limitations

The headline is pro-market. Across a five-layer model-vs-market scan of 238 contracts, the
liquid winner market is efficient (mean |model - market| ~0.4pp); the only soft corners are
thin, new, or structural, and where our model disagreed most (minnow advancement, isolated
confederations) an independent bookmaker sided with the market and the error was ours to fix
(Section 4.3). Limitations, stated plainly: single-tournament sample; the calibration n (~104
matches) supports a wide slope band, not a tight one, so the calibration claims stay
appropriately humble; the study is read-only and paper-only (no orders, no capital); and the
in-play results depend on clean marquee-match captures, the data-quality risk we actively
manage.

## References

- Croxson, K. and Reade, J. J. (2014). Information and Efficiency: Goal Arrival in Soccer Betting. *The Economic Journal*.
- Gonzalo, J. and Granger, C. W. J. (1995). Estimation of Common Long-Memory Components in Cointegrated Systems. *Journal of Business & Economic Statistics*.
- Hasbrouck, J. (1995). One Security, Many Markets: Determining the Contributions to Price Discovery. *The Journal of Finance*.
- Hawkes, et al. (2026). ⟦prediction-market efficiency/microstructure; confirm exact title and venue⟧.
- Snowberg, E. and Wolfers, J. (2010). Explaining the Favorite-Longshot Bias: Is it Risk-Love or Misperceptions? *Journal of Political Economy*.
- ⟦SoK on prediction markets, 2026; confirm exact title and venue⟧.
