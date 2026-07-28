# Cross-Venue Price Discovery in World Cup Prediction Markets

**Working draft, 2026.** Prabhat M. ([repo](https://github.com/Thesavagecoder7784/xResidual) · [portfolio](https://thesavagecoder7784.github.io/))

> Status: **complete.** The 2026 World Cup finished on 2026-07-19 and every result below is final.
> The pre-match microstructure results (Sections 5.1, 6.1) are final; the in-play price-discovery
> result (Section 5.2), its harvestability test (Section 6.2), and the OFI study (5.5) are **firm**
> on the full marquee-match sample (86 matches, 392 repricing events); the goal-shock event study
> (Section 5.3) carries a **preliminary** under-reaction result (suggestive, not firm); the
> calibration grade (Section 5.4) and the pre-registration scorecard (Section 7) are graded. Every
> empirical claim here is bound to code and to a pre-registration committed before kickoff
> (PREREGISTRATION.md), so the results are falsifiable, not flexible.

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
mid-price moves around each goal shock, is now firm: across **86 matches and 392 decisive repricing
events Polymarket leads Kalshi 72% of the time** (281 vs 111; 66% if the 35 synchronous same-second
events count against it), at a **median +600ms** among Polymarket-led events (the signed pooled
distribution, which counts Kalshi-led events as negative, has a median +400ms and an IQR
[-200, +800]). The lead survives the clustering of
events within matches — a match-resampling bootstrap holds the 95% CI at [67%, 76%] (design effect just
1.13), and, the cluster-immune cut, **57 of 66 matches lean Polymarket** (sign-test p = 1.2×10⁻⁹). The
citable estimate is the formal decomposition: across **63 cointegrated matches** Polymarket carries a
**Gonzalo-Granger ~81.0% information share** (per-match median, bootstrap CI [77%, 87%]; Hasbrouck on the
same per-match unit ~75.2%, CI [68%, 87%]) and **leads 61 of
63 matches** (sign-test p = 4.4×10⁻¹⁶, between-match SD ~19%), rising to ~86% inside goal windows (vs ~53%
in calm play). An early read (n=8) that flashed ~500ms and then appeared to wash out at n=24 was
small-sample noise on the *event-timing* metric; the full sample and the information-share
decomposition both confirm a real, direction-stable lead in the pre-registered direction (the
deeper-liquidity venue leads). We then ask the question the lead invites, and answer it with
disclosed forward-tests: the cross-venue gap is **not a harvestable edge**. The pre-match
convergence trade is a clean null (a cost illusion); and although a stale-quote ledger over 405
goals in 66 matches shows a median **+10.8-cent** net gap **on paper** (100% of goals net-positive), best-price depth at the
goal collapses to ~0.5% of normal (spread ~8x on Polymarket, ~2x on Kalshi, refill ~3-4s), so **the
median match yields zero harvestable goals** (goal-weighted, on the archive subset that survives: ~11%,
clustered in a minority of matches a follower cannot identify in advance). The lead
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
   markets than in bookmakers? (Section 5.4.)

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
A 24/7 collector logged Kalshi and Polymarket order books and the Odds API bookmaker/exchange
lines on a fixed cadence, and, per marquee match, a millisecond WebSocket capture recorded every
book and trade message from both prediction venues to an append-only tape with a local-clock
timestamp on each event. A dry-run friendly capture recorded ~173k events at a 6ms median
inter-event time (Section 5.6), so timestamp resolution is far finer than the tens-of-seconds
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
field; the most persistent standing gap is **England**, the only team quoted apart at every as-of cutoff (mean ~0.8pp, peaking ~1.0pp pre-kickoff). The "5 to 8 cent" gap the press quotes is
**mostly the house margin**: Kalshi's overround runs ~5.4% vs Polymarket's ~3.0% (~1.8x), so the
durable venue difference is *cost, not price*.

Anchored to the sharp bookmaker consensus (Betfair Exchange), **Polymarket sits closer to the sharp
line than Kalshi at every as-of date we replay** — at 2026-06-22, mean absolute gap **0.15pp vs
0.26pp**, with Polymarket closer on **39 of 48** teams. The direction is stable across the whole
tournament (`scripts/basis_asof_sweep.py`); the *magnitude* is not, and has to be quoted with its
date, because once the field starts resolving Kalshi's winner book stops being a probability
distribution at all (its overround runs 6.5% in the group stage and ~2300% by the final). Two
earlier drafts of this note quoted two different undated pairs for this comparison; that is what
the as-of sweep exists to prevent. The small surviving belief gap is **structured by audience**: the American book (Kalshi) prices **USA, Netherlands and Mexico** richer, the global book (Polymarket) prices **England, France, Japan and Brazil** richer — a home-crowd tilt. These are the teams whose sign holds across the as-of cutoffs (`_basis_asof_sweep.json`); an earlier draft also listed Portugal on the global side, which the sweep puts on the American side, so it is dropped.

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
way.** Across **86 matches and 392 decisive repricing events, Polymarket moves first in 281 vs
Kalshi's 111 (72%; 66% if the 35 synchronous same-second events count against it)**, at a **median
lead of +600ms** (pooled; +600ms among Polymarket-led events, bootstrap CI [600, 800]), in the
pre-registered direction (P6: the deeper-liquidity venue leads, and Polymarket quotes ~27x the depth,
Section 5.1). The n=24 wobble was noise in the event-timing point estimate, not a reversal of the lead.

Because the 392 events cluster within 79 lead-bearing matches, a naive event-level CI overstates precision, so we
harden it (`scripts/harden_leadlag_stats.py`). The clustering turns out to be mild — intra-match
correlation in *which* venue leads is low (ICC 0.032, design effect 1.13, effective N ≈ 348 of 392) —
so a match-resampling bootstrap barely widens the interval, from a naive Wilson [67.0%, 75.9%] to a
cluster-robust [66.7%, 76.4%]. The cluster-immune statement is the per-match one: **57 of 66 matches lean
Polymarket** (binomial sign-test p = 1.2×10⁻⁹, Wilcoxon p = 7.2×10⁻⁸), which no single high-event match
can drive.

The citable result is the formal decomposition (Section 4.2). Across the **63 cointegrated matches
(104 contracts)**, Polymarket carries a **Gonzalo-Granger ~81.0%** component share (per-match median,
bootstrap CI [77%, 87%]) and a **Hasbrouck share of ~75.2%** on that same per-match unit (bootstrap CI
[68%, 87%]), and it **leads in 61 of
the 63 matches** (sign-test p = 4.4×10⁻¹⁶) — a direction-stable result, not a thin majority, though with
real match-to-match spread (between-match SD ~19%).

Two estimator caveats, stated rather than buried. The Hasbrouck **per-contract** identification width
(the Cholesky ordering bound) runs ~77-92%; that is an ordering-sensitivity diagnostic on the contract
unit and is *not* a confidence interval around the ~75.2% match-level share — earlier drafts printed the
two side by side, which put the point estimate below its own lower bound. And Gonzalo-Granger, being a
ratio of error-correction coefficients, is unbounded when both venues adjust with the same sign: **5 of
the 63 matches return a share above 1** (max 1.42). That is why the headline is a median and not a mean
— across the 58 in-support matches alone it is 80.2%, essentially unchanged. The lead is concentrated exactly
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

The market's post-goal update is a median **0.35x** the model's fair update in log-odds, and the
market under-shoots the fair move in **every one of the 22 goals** where its quote moved at all, and
in **8 of 8 matches** (per-match sign test p = 0.008). The move is not given back —
the 60-second reversion is ~0 — so this is a *persistent* under-reaction, not a transient
overshoot. (Of the 29 goals in these 8 matches, 7 are excluded because the market quote did not
move at all: 2 are stoppage-time goals in decided matches with no fair-value change, and 5 pair a
large fair jump with a quote pinned to the tick, which we treat as a missing quote rather than a
considered zero reaction. Those 5 are the most extreme apparent under-reactions in the sample, so
the exclusion moves the estimate *toward* the market, not away from it; ungated the ratio is
0.07x.) We guard against the obvious confound, that the *model* over-reacts rather than the
market under-reacting, with an **outcome test**: the model's larger post-goal probability is the
**better forecast of the eventual result** (log-loss 0.235 vs the market's 0.361; Brier 0.073 vs
0.113), so the larger jump was warranted. The under-reaction sits in the market, not in an
over-eager benchmark.

We report this as **suggestive, not firm.** The cluster-honest unit is the match, and 8 of 8 is a
sign-test *p* = 0.008 on eight matches; the goal-level count (22 of 22) overstates significance
because goals within a match share an outcome. Eight matches is a small sample however it is
scored.

> **Provenance note (2026-07-25).** Earlier drafts of this section reported "a median 0.55x, under-shooting
> in 7 of 8 matches (20 of 22 goals)". Those figures were computed ad hoc and shipped without an
> estimator, and they do not reproduce. The analysis is now written down in
> `scripts/underreaction_clean.py` and re-derived on every run. The outcome test below reproduces the
> published values *exactly*; the ratio does not, and the corrected log-odds version is stronger than
> what it replaces, not weaker. On the full sample that also includes shock-inferred goal
times (**54 matches, 185 goals**) the direction is the same — a mean under-shoot of **3.1pp** in
P(home win) versus the model's fair jump — but the
outcome test is mixed — mislabeled shock-goals corrupt the model's fair jump, which is exactly why
the clean-reconstruction subset is the one we trust. Two cuts that looked striking at first — that
"underdog goals move the market twice as far," and a "value-of-a-goal" curve peaking for even
matchups — did **not** survive the log-odds correction: they were the logistic geometry, not
behaviour, and are not claimed.

The wider study this section was scoped for — ~260 goals with surprise classification,
abnormal-return windows and a mean-reversion half-life benchmarked against Croxson-Reade — was not
delivered. The knockout captures did not add cleanly-timed goals: the clean-reconstruction subset
finished at the same 8 matches it started with, because curated goal minutes never arrived for the
later rounds. What is reported above is the whole of it, and it is reported as preliminary.

### 5.4 Calibration and the favorite-longshot bias (final)
The favorite-longshot bias is visible pre-tournament in the 1-cent tick structure of longshot
contracts. The half-spread by probability decile and the books-vs-prediction-markets comparison
are reported here as a **descriptive replication** (Snowberg-Wolfers, 2010).

The graded calibration verdict (P1, primary: **PASS**): the de-vigged market forecast scores a
**Brier of 0.487** — a **23.6%** skill gain over the base rate — with a calibration-regression
slope of **1.07** and every decile inside the bootstrap consistency band. This is graded on the
**72 group-stage matches**: the pre-committed forecast ledger closes on 2026-06-27, so the knockout
rounds carry no pre-registered model forecast and are not scored.

The market is at least as sharp as the independent model (0.487 vs **0.503**), but that is not a
win and should not be read as one. Paired on the same 72 matches the difference carries a bootstrap
95% CI of **[-0.011, +0.044]** and a paired-t **p = 0.25**, and the market scores better in only
**34 of 72** matches — its edge comes from margin on the matches it wins, not from winning more of
them. At this sample size the two are statistically indistinguishable. The claim is that the market
is well-calibrated, not that it beats the model.

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
venue across 83 matches — bin-level t ~= 115 on Polymarket and t ~= 72 on Kalshi — so order flow moves
price as expected inside a book. Those t-statistics are computed on ~1.2M one-second bins and are
badly overstated as significance tests (the bins are nested in matches, and the r² is 0.010 and 0.005
respectively); read them as "the sign is unambiguous", not as effect size. But **cross-venue** order flow is *not* a clean lead: the cross-venue OFI relation
is contemporaneous, not predictive, so the price-discovery lead in 5.2 is carried by quote
revision, not by one venue's order flow front-running the other's price.

### 5.6 Infrastructure validation (final)
The **capture** leg was exercised before the tournament on a warm-up friendly: ~173k events at 6ms
median spacing (`logger/data/capture-arg-isl.log`), with the goal-shock detector hardened from 11
false triggers to 3. Two limits that log records and earlier drafts of this note glossed: the
friendly carried **no Kalshi market**, so zero cross-venue pairs were formed and nothing
cross-venue was validated; and the two post-capture analysis steps aborted on a missing dependency.
The analysis legs were exercised on the tournament tapes themselves, not here. The capture is live
and self-correcting (Section 3.1).

## 6. Two disclosed forward-tests, two nulls

The two ways the cross-venue gap might be a harvestable edge, each tested out-of-sample rather
than asserted, each disclosed with its rule.

### 6.1 Pre-match convergence: a cost illusion (final)
The law-of-one-price result (5.1) predicts there is no convergence arbitrage to harvest, and we
tested that out-of-sample rather than asserting it. Rule: when the de-vigged Polymarket-Kalshi
belief gap on a title widens past 1.0pp, go long the cheap venue and short the rich one, exit on
convergence below 0.3pp or after a horizon, net of a 0.5pp modeled round-trip cost
(fee + half-spread). Buildup result (2026-06-05 to 06-10): **8 trades, -1.66pp total, 25% hit rate,
mean -0.21pp per trade.** The window is the pre-tournament buildup by necessity: once the field
starts resolving, a de-vigged convergence trade on the title market is degenerate (§5.1). The gap is
real but does not converge enough to clear costs: the visible "edge" is a cost illusion, exactly
what law-of-one-price implies.

### 6.2 In-play lead-lag: real lead, un-harvestable after the cost of immediacy (firm)
The §5.2 lead means Kalshi reprices a goal slightly behind Polymarket, so the natural follow-up
is whether that lag is capturable. We answer it with a **cost-of-immediacy ledger over 405 goals in
66 matches**: at the instant Polymarket reprices, the median gross gap to Kalshi's stale quote is
**12.0¢**, a follower pays a median **1.4¢** to take Kalshi's posted price, and the median net is
**+10.8¢ on paper** (100% of goals net-positive). Each of those three is a median across matches of
that match's median goal — computed independently, so they are not meant to subtract, and the
match, not the goal, is the unit. That paper number is a trap, and surfacing it is the point. At
the goal, Kalshi's best-price depth collapses to **~0.5% of its normal level** — the spread blows out
~8x on Polymarket and ~2x on Kalshi, and the book takes **~3-4s to refill**. There is usually no resting
size to hit at the stale price: by the time depth returns, the quote has caught up. So of the +10.8¢ paper
gap, **the median match yields zero harvestable goals**.

Be exact about that statistic, because it is a median across matches and it is easy to over-read. It
says the typical match offers a follower nothing — not that no goal anywhere was capturable. On the
portion of the per-game ledger still reconstructible from the archive (**21 matches, 117 goals**) the
goal-weighted rate is **11.1%**, and those goals cluster in **6 of the 21** matches. The honest claim is
therefore distributional: harvestable goals exist, they are a minority, they concentrate in a minority of
matches, and a follower has no way to know in advance which goal will leave depth behind — the book is
gone at the instant the signal fires. The result is a **liquidity-withdrawal story, not slow pricing**: the
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

## 7. Pre-registration and grading

**Eleven** falsifiable, dated predictions were committed to a tagged git commit before kickoff
(PREREGISTRATION.md), with binding methods, named primaries, and PASS/FAIL/INCONCLUSIVE decision
states under proper scoring rules. The two primaries are **P6** (cross-venue lead-lag: the
deeper venue leads) and **P1** (the markets are well-calibrated); both **pass**. Graded publicly on
2026-07-19 by `scripts/grade_prereg.py`: **6 pass, 2 fail, 3 inconclusive**. The two failures are
themselves results — P3 is the raw law-of-one-price gap that de-vigging explains as margin (5.1),
and P10 the goal-overreaction edge already arbed away — and the three inconclusives are data-forced
and recorded in PREREGISTRATION-ADDENDUM.md.

On P1 specifically: its frozen rule requires the market's Brier to beat the pre-committed model's on
the same matches, and it does (0.487 vs 0.503) — but that is a **point** comparison, which is what
was committed. Paired on the 72 scored matches the difference is **not significant** (paired-t
p = 0.25, bootstrap 95% CI [-0.011, +0.044]; the market scores better in only 34 of 72). P1 passes
exactly as written, and it certifies that the market is well-calibrated, not that it out-forecasts
the model.

## 8. Discussion and limitations

The unifying finding is a discipline for telling real edges from mirages. The cross-venue gap was
probed three ways. The pre-match convergence trade is a cost illusion (6.1, a clean null). The
in-play lead-lag is a **real, direction-stable lead** — Polymarket first in 72% of 392 decisive events
at a +600ms median (57 of 66 matches lean Polymarket, sign-test p = 1.2×10⁻⁹), and a ~81.0% information
share leading 61 of 63 cointegrated matches (5.2) — that is nonetheless **un-harvestable net of the
cost of immediacy** (6.2: a median +10.8¢ paper gap over 405 goals in 66 matches, of which the median
match yields nothing capturable because best-price depth collapses to ~0.5% at the event). The
favorite-longshot wedge (5.4) is a real but modest systematic tilt, the lone position the project
takes. The lead is genuine; the gap is a liquidity-withdrawal artifact, not slow pricing; the
methods that separate real from harvestable — de-vigging before calling any gap, crossing the
real bid/ask, charging the follower cost, and reading depth at the event — are the contribution as
much as any single number. Price discovery here is genuine and measurable, and almost none of it
is harvestable, which is the honest reading and the pro-market one.

The headline is pro-market. Across a five-layer model-vs-market scan of 238 contracts (a tournament-period read: the per-layer gaps below were measured while the field was live and cannot be re-derived now that it has resolved, though the 238-contract denominator is recorded in the scan artifact), the
liquid winner market is efficient (mean |model - market| ~0.4pp); the only soft corners are
thin, new, or structural, and where our model disagreed most (minnow advancement, isolated
confederations) an independent bookmaker sided with the market and the error was ours to fix
(Section 4.3). Limitations, stated plainly: single-tournament sample; the calibration n (72
group-stage matches — the pre-committed ledger does not reach the knockout rounds) supports a wide
slope band and cannot separate the market from the model (p = 0.25), so the calibration claims stay
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
