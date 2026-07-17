# Cross-Venue Price Discovery in World Cup Prediction Markets

**Working draft, 2026.** Prabhat M. ([repo](https://github.com/Thesavagecoder7784/xResidual) · [portfolio](https://thesavagecoder7784.github.io/))

> Status: this is a live, phased note. The pre-match microstructure results (Sections 5.1, 6.1)
> are final; the in-play price-discovery result (Section 5.2), its harvestability test (Section
> 6.2), and the OFI study (5.5) are now **firm** on the full marquee-match sample (84 matches,
> 377 repricing events) and reported as such; the goal-shock event study (Section 5.3) now carries a
> **preliminary** under-reaction result (suggestive, not firm); the calibration grade (Section 5.4)
> and the pre-registration grade (Section 7) fill in as the 2026 World Cup is played. Every empirical claim here is bound to code and to a
> pre-registration committed before kickoff (PREREGISTRATION.md), so the open results are
> falsifiable, not flexible.

---

## Abstract

Two large real-money prediction markets, Kalshi (US, regulated) and Polymarket (global,
on-chain), priced every 2026 World Cup outcome continuously, tracked against the global bookmaker
consensus. Using millisecond-resolution order-book and trade captures
across both venues, plus an on-chain trade-flow layer reconstructed from Polymarket's CTF
Exchange, we study **where price is discovered**: which venue moves first when information
arrives, and whether that leadership flips between the quiet pre-match regime and the
high-information in-play regime. We decompose each cross-venue quote into belief and margin and
find the widely-quoted "5 to 8 cent" inter-venue gap is **almost entirely the house margin**:
de-vigged, the two prediction markets agree to ~0.15pp on the title race, and a relative-value
convergence trade returns a documented loss net of costs. The residual belief gap is small but
structured by audience (a home-crowd tilt). The central price-discovery result, estimated on
mid-price moves around each goal shock, is now firm: across **84 matches and 377 decisive repricing
events Polymarket leads Kalshi 71% of the time** (269 vs 108; 67% if the 35 synchronous same-second
events count against it), at a **median +600ms** (IQR [0, +800]). The lead survives the clustering of
events within matches — a match-resampling bootstrap holds the 95% CI at [66%, 76%] (design effect just
1.13), and, the cluster-immune cut, **56 of 65 matches lean Polymarket** (sign-test p = 5×10⁻⁸). The
citable estimate is the formal decomposition: across **61 cointegrated matches** Polymarket carries a
**Gonzalo-Granger ~80.6% information share** (per-match median; Hasbrouck band ~73-90%) and **leads 50 of
51 matches** (sign-test p = 5×10⁻¹⁴, between-match SD ~20%), rising to ~86% inside goal windows (vs ~53%
in calm play). An early read (n=8) that flashed ~500ms and then appeared to wash out at n=24 was
small-sample noise on the *event-timing* metric; the full sample and the information-share
decomposition both confirm a real, direction-stable lead in the pre-registered direction (the
deeper-liquidity venue leads). We then ask the question the lead invites, and answer it with
disclosed forward-tests: the cross-venue gap is **not a harvestable edge**. The pre-match
convergence trade is a clean null (a cost illusion); and although a stale-quote ledger over 277
goals shows a **+10.8-cent** net gap **on paper** (100% of goals net-positive), best-price depth at the
goal collapses to ~0.5% of normal (spread ~8x on Polymarket, ~2x on Kalshi, refill ~3-4s), so **0% is
harvestable**. The lead
is a **liquidity-withdrawal result, not slow pricing**: real, but un-harvestable after the cost
of immediacy. The one corner where a mechanical view plausibly beats the human-driven price is
the favorite-longshot bias at price extremes. The through-line: price discovery here is real and
measurable, and almost none of it is harvestable, which is the honest pro-market reading.

**Contribution.** The cross-venue, pre-match-vs-in-play price-discovery comparison across
regulated, on-chain, and exchange venues is, to our knowledge, the named-but-unexplored
question in the recent prediction-market microstructure literature; everything else here is a
careful replication or a methods contribution (the confederation-shrinkage baseline correction,
Section 4.3, and the on-chain trade-direction layer, Section 3.2).

---

## 1. Introduction

Real-money prediction markets aggregate dispersed information into a single live probability.
The 2026 World Cup is a natural experiment: a 39-day, 104-match global event priced
simultaneously by a US-regulated venue (Kalshi) and a global on-chain venue (Polymarket), against
the global bookmaker consensus, with a dense, exogenous, and precisely-timed information
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
- **Prediction-market efficiency / microstructure.** Bürgi, Deng and Whelan (2025) document a
  favorite-longshot bias in 300,000+ Kalshi contracts and tie it to a maker-taker microstructure;
  the SoK of Rahman, Al-Chami and Clark (2025) maps the microstructure of modern (incl. on-chain)
  prediction markets. Neither measures cross-venue price discovery, the gap this note fills. The
  lead-lag arbitrage literature (Poutré, Dionne and Yergeau, 2024) supplies the §6.2 benchmark.
  Closest to this note, Ng, Peng, Tao and Zhou (2026) find Polymarket leads Kalshi and report an
  economically meaningful cross-venue arbitrage; we corroborate the lead on a clean, repeated,
  exogenous event stream (goals) but refine the arbitrage claim — net of the cost of immediacy the
  lead is real yet un-harvestable (§6.2).

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
durable venue difference is *cost, not price*. Anchored to the sharp bookmaker consensus,
Polymarket sits marginally closer to the sharp line (mean abs error
~0.18pp vs ~0.26pp). The small surviving belief gap is **structured by audience**: the American
book is richer on USA, Mexico, Netherlands; the global book on England, Portugal, Japan, Brazil,
a home-crowd tilt.

A liquidity asymmetry underlies this: Polymarket quotes roughly **27x the depth of Kalshi at the
same spread** on the title market, so the two venues are integrated on price but very different
on capacity.

### 5.2 Cross-venue price discovery: Polymarket leads in-play (firm)
The in-play lead-lag is estimated on binned mid-changes in a window around each auto-detected
goal shock. A quality gate keeps only events with genuine positive co-movement (best
cross-correlation >= 0.5) and a plausible lag (<= 8s), discarding spurious detections: a
"16-second lead at r = -0.70" is two books moving oppositely, a stale-tick artifact, not price
discovery. An early read on four matches (**n = 8**) put Polymarket a median +500ms ahead, then
at **n = 24** the event-timing median appeared to wash to ~+100ms on a near-even split, which we
flagged at the time as a possible small-sample null. **The full sample resolves it the other
way.** Across **84 matches and 377 decisive repricing events, Polymarket moves first in 269 vs
Kalshi's 108 (71%; 65% if the 35 synchronous same-second events count against it)**, at a **median
lead of +600ms** (pooled; +600ms among Polymarket-led events, bootstrap CI [600, 800]), in the
pre-registered direction (P6: the deeper-liquidity venue leads, and Polymarket quotes ~27x the depth,
Section 5.1). The n=24 wobble was noise in the event-timing point estimate, not a reversal of the lead.

Because the 377 events cluster within 67 lead-bearing matches, a naive event-level CI overstates precision, so we
harden it (`scripts/harden_leadlag_stats.py`). The clustering turns out to be mild — intra-match
correlation in *which* venue leads is low (ICC 0.033, design effect 1.13, effective N ≈ 255 of 308) —
so a match-resampling bootstrap barely widens the interval, from a naive Wilson [68%, 78%] to a
cluster-robust [66%, 76%]. The cluster-immune statement is the per-match one: **56 of 65 matches lean
Polymarket** (binomial sign-test p = 5×10⁻⁸, Wilcoxon p = 1×10⁻⁶), which no single high-event match
can drive.

The citable result is the formal decomposition (Section 4.2). Across the **61 cointegrated matches
(100 contracts)**, Polymarket carries a **Gonzalo-Granger ~79%** component share (per-match median,
bootstrap CI [74%, 88%]) and a **Hasbrouck information-share band of ~73-90%**, and it **leads in 50 of
the 51 matches** (sign-test p = 5×10⁻¹⁴) — a direction-stable result, not a thin majority, though with
real match-to-match spread (between-match SD ~20%). The lead is concentrated exactly
where information arrives: Polymarket's information share is **~86% inside goal windows** versus
**~53% in calm play**, i.e. the two venues co-discover in the quiet and Polymarket discovers
first on the shock. Each match's events and tape are archived per game so the sample is
auditable, not overwritten.

### 5.3 Goal-shock event study: the market under-reacts to goals (preliminary, clean sample)
A first in-play result, on the subset of matches with a **fully reconstructed goal timeline**
(curated goal minutes, and the final score reconstructs from the goal sequence — 8 group-stage
matches, 29 goals; the wider shock-inferred sample is reported but not relied on, below). For each
goal we compare two updates to the home win probability: the market's actual move (settled ~30s
after the goal) and an independent reference — a calibrated clock-and-Poisson in-play model whose
pre-goal probability is anchored to our pre-match forecast, so the goal's *fair* probability jump
is well defined. Both moves are taken in **log-odds**, so a 50→60% and a 10→20% update are
comparable and the result is not an artifact of the logistic curve being steepest at one-half.

The market's post-goal update is a median **0.55x** the model's fair update, and the market
under-shoots the fair move in **7 of 8 matches** (20 of 22 goals). The move is not given back —
the 60-second reversion is ~0 — so this is a *persistent* under-reaction, not a transient
overshoot. We guard against the obvious confound, that the *model* over-reacts rather than the
market under-reacting, with an **outcome test**: the model's larger post-goal probability is the
**better forecast of the eventual result** (log-loss 0.235 vs the market's 0.361; Brier 0.073 vs
0.113), so the larger jump was warranted. The under-reaction sits in the market, not in an
over-eager benchmark.

We report this as **suggestive, not firm.** The cluster-honest unit is the match, and 7 of 8 is a
sign-test *p* ≈ 0.07; the goal-level count (20 of 22, *p* < 0.001) overstates significance because
goals within a match share an outcome. On the full sample that also includes shock-inferred goal
times (27 matches) the direction is the same (market under-shoots in 24 of 27 matches) but the
outcome test is mixed — mislabeled shock-goals corrupt the model's fair jump, which is exactly why
the clean-reconstruction subset is the one we trust. Two cuts that looked striking at first — that
"underdog goals move the market twice as far," and a "value-of-a-goal" curve peaking for even
matchups — did **not** survive the log-odds correction: they were the logistic geometry, not
behaviour, and are not claimed. The finding should sharpen as the knockout sample (now capturing
cross-venue, Section 2) adds cleanly-timed goals.

> The full graded study (target ~260 goals: surprise classification, abnormal-return windows,
> mean-reversion half-life, benchmarked against Croxson-Reade efficient updating) fills in over the
> tournament; the framework is validated on the live tapes (5.6).

### 5.4 Calibration and the favorite-longshot bias (FLB in; calibration grade PENDING Jul 19)
The favorite-longshot bias is visible pre-tournament in the 1-cent tick structure of longshot
contracts. The half-spread by probability decile and the books-vs-prediction-markets comparison
are reported here as a **descriptive replication** (Snowberg-Wolfers, 2010); the *graded*
calibration verdict (CORP reliability, Brier decomposition, slope) lands after the group stage
and again at the final, and is pre-registered (P1: the markets are well-calibrated).

The favorite-longshot bias is also the one corner where a mechanical view plausibly beats the
human-driven price, and it is the only market-facing position the project actually takes. The
independent baseline's advance probabilities are systematically *more extreme* than the market in
both directions (favorites priced higher, longshots lower), the signature of the bias that
persists even in deep prediction markets at the contract-price extremes. A model carries no
psychological longshot premium, so its extremeness is in the exploitable direction. This
underwrites a small, diversified basket in the paper track record: fade the overpriced longshots,
back the underpriced favorites, sized as the modest systematic tilt it is rather than single-name
conviction. Whether it is a real edge or model tail-overconfidence is itself a calibration
question, graded after the group stage. Notably, it is the *advance* market that carries the
signal: it runs near-zero margin, whereas the reach-round ladder is 12 to 31% overround, where a
model's apparent "fades" are the vig, not an edge.

### 5.5 Order-flow imbalance to short-horizon returns (in)
On-chain signed OFI regressed on next-interval mid return is strongly significant **within** each
venue — t ~= 58 on Polymarket and t ~= 50 on Kalshi — so order flow moves price as expected
inside a book. But **cross-venue** order flow is *not* a clean lead: the cross-venue OFI relation
is contemporaneous, not predictive, so the price-discovery lead in 5.2 is carried by quote
revision, not by one venue's order flow front-running the other's price.

### 5.6 Infrastructure validation (final)
The in-play pipeline was proven end-to-end before the tournament on a warm-up friendly:
~172k events at 6ms median spacing, with the goal-shock detector hardened from 11 false triggers
to 3. The capture is live and self-correcting (Section 3.1).

## 6. Two disclosed forward-tests, two nulls

The two ways the cross-venue gap might be a harvestable edge, each tested out-of-sample rather
than asserted, each disclosed with its rule.

### 6.1 Pre-match convergence: a cost illusion (final)
The law-of-one-price result (5.1) predicts there is no convergence arbitrage to harvest, and we
tested that out-of-sample rather than asserting it. Rule: when the de-vigged Polymarket-Kalshi
belief gap on a title widens past 1.0pp, go long the cheap venue and short the rich one, exit on
convergence below 0.3pp or after a horizon, net of a 0.5pp modeled round-trip cost
(fee + half-spread). Buildup result: **6 trades, -2.6pp total, 0% hit rate, per-trade Sharpe
-1.95.** The gap is real but does not converge enough to clear costs: the visible "edge" is a
cost illusion, exactly what law-of-one-price implies.

### 6.2 In-play lead-lag: real lead, un-harvestable after the cost of immediacy (firm)
The §5.2 lead means Kalshi reprices a goal slightly behind Polymarket, so the natural follow-up
is whether that lag is capturable. We answer it with a **cost-of-immediacy ledger over 277
goals**: at the instant Polymarket reprices, the gross gap to Kalshi's stale quote averages
**~12.5¢**, and a follower pays **~1.3¢** to take Kalshi's posted price, leaving **~+10.8¢ net on
paper** (100% of goals net-positive). That paper number is a trap, and surfacing it is the point. At
the goal, Kalshi's best-price depth collapses to **~0.5% of its normal level** — the spread blows out
~8x on Polymarket and ~2x on Kalshi, and the book takes **~3-4s to refill**. There is no resting size to
hit at the stale price: by the time depth returns, the quote has caught up. So of the +10.8¢ paper
gap, **0% is harvestable**. The result is a **liquidity-withdrawal story, not slow pricing**: the
lead is real, the follower cost is small, and the edge still vanishes because immediacy is
withdrawn exactly when it would be valuable. This is consistent with the high-frequency lead-lag
literature: the naive mid-signal market-order strategy never clears the spread, and the versions
that *do* profit (Poutré, Dionne and Yergeau, 2024) require colocation and limit-order execution a
read-only, paper-only study cannot access. A real lead, un-harvestable net of the cost of
immediacy, which is to say not an edge for anyone trading across the two books.

This both corroborates and refines the contemporaneous finding of Ng, Peng, Tao and Zhou (2026,
SSRN 5331995) that Polymarket leads Kalshi: we confirm the lead on a clean, repeated, exogenous
event stream (goals), but on that stream the lead is **un-harvestable** once the cost of immediacy
is charged, which qualifies their "economically meaningful arbitrage" reading — the arbitrage is
real on paper but not economically meaningful net of the liquidity withdrawal at the event.

## 7. Pre-registration and grading ⟦PENDING Jul 19⟧

Six falsifiable, dated predictions were committed to a tagged git commit before kickoff
(PREREGISTRATION.md), with binding methods, named primaries, and PASS/FAIL/INCONCLUSIVE decision
states under proper scoring rules. The two primaries are **P6** (cross-venue lead-lag: the
deeper venue leads) and **P1** (the markets are well-calibrated). Graded publicly on 2026-07-19.

## 8. Discussion and limitations

The unifying finding is a discipline for telling real edges from mirages. The cross-venue gap was
probed three ways. The pre-match convergence trade is a cost illusion (6.1, a clean null). The
in-play lead-lag is a **real, direction-stable lead** — Polymarket first in 71% of 377 decisive events
at a +600ms median (56 of 65 matches lean Polymarket, sign-test p = 5×10⁻⁸), and a ~80.6% information
share leading 59 of 61 cointegrated matches (5.2) — that is nonetheless **un-harvestable net of the
cost of immediacy** (6.2: a +10.8¢ paper gap over 384 goals that 0% of is capturable because best-price
depth collapses to ~0.5% at the event). The
favorite-longshot wedge (5.4) is a real but modest systematic tilt, the lone position the project
takes. The lead is genuine; the gap is a liquidity-withdrawal artifact, not slow pricing; the
methods that separate real from harvestable — de-vigging before calling any gap, crossing the
real bid/ask, charging the follower cost, and reading depth at the event — are the contribution as
much as any single number. Price discovery here is genuine and measurable, and almost none of it
is harvestable, which is the honest reading and the pro-market one.

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
- Poutré, C., Dionne, G. and Yergeau, G. (2024). The profitability of lead-lag arbitrage at high frequency. *International Journal of Forecasting*, 40(3), 1002-1021. (The naive mid-signal market-order strategy never clears the spread; the profitable version needs colocation and limit orders, the basis for the §6.2 latency-mirage reading.)
- Bürgi, C., Deng, W. and Whelan, K. (2025). Makers and Takers: The Economics of the Kalshi Prediction Market. Working paper (SSRN 5502658). (300,000+ contracts: prices are informative and improve toward close but show a clear favorite-longshot bias; the §5.4 basis.)
- Snowberg, E. and Wolfers, J. (2010). Explaining the Favorite-Longshot Bias: Is it Risk-Love or Misperceptions? *Journal of Political Economy*.
- Rahman, N., Al-Chami, J. and Clark, J. (2025). SoK: Market Microstructure for Decentralized Prediction Markets (DePMs). arXiv:2510.15612.
- Ng, Peng, Tao and Zhou (2026). Working paper (SSRN 5331995). (Polymarket leads Kalshi in price discovery and reports economically meaningful cross-venue arbitrage; §6.2 corroborates the lead on a clean repeated-event stream but refines the arbitrage claim — the lead is un-harvestable net of the cost of immediacy.)
