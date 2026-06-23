# Methodology

This document commits, up front, to the variance models and scoring rules used
everywhere downstream. If a claim in a thread or notebook isn't grounded in something
defined here, it isn't a finding.

## 0. The central question

I am not forecasting match outcomes, and I am not trying to beat the markets.
I study **how three markets (Kalshi, Polymarket, and the bookmaker consensus)
price the World Cup, and what they reveal about it**, in real time. Three lenses, all
built on the same variance model:

- **Residuals**: the tournament's surprises, measured against the market's
  expectation (and how fast the market re-priced them).
- **Microstructure**: how the venues converge, who incorporates information faster,
  and how prediction markets compare to traditional bookmakers.
- **Calibration / sharpness**: over the match population, how good are the markets'
  probabilities?

A single forecast cannot be evaluated: a 65% price followed by a loss is not an
error, because 35% events occur 35% of the time. So a surprise is the tournament
doing its job, not the market failing, and calibration is only defined over a
*population* of forecasts. The 2026 World Cup supplies one (≈104 matches), so those
population-level claims carry the inferential weight, while the cross-venue and
residual lenses also work per-match. Anything computed per-team (n = 3–7) is
descriptive color, never an inferential claim.

## 1. Outcome spaces and notation

For each match `m` I work with two outcome representations:

- **Result**: a categorical outcome `y_m ∈ {home win, draw, away win}` (W/D/L from a
  fixed reference team). Forecasts are probability vectors `p_m = (p_W, p_D, p_L)`.
- **Goal differential**: `d_m = goals_home − goals_away`, an integer.

Two distinct objects are tracked and must not be confused:

- The **market** forecast `q_m`: implied probabilities recovered from prices (§5).
  This is the object under study.
- The **baseline** forecast `b_m`: a model from public data, Elo + xG (§2). This is
  an *independent* benchmark, used only for the secondary "can a public-data model
  beat the market?" question. **It is never used to judge the market's calibration**,
  because the baseline itself ingests market information and judging the market
  against a market-derived yardstick is circular.

## 2. Expectation baseline (Layer 1)

A per-match expectation built from public data, independent of the calibration test.

### Goal differential: Skellam

Model each team's goals as Poisson with team-and-match-specific rates:

```
goals_home ~ Poisson(λ_home)
goals_away ~ Poisson(λ_away)
d_m = goals_home − goals_away ~ Skellam(λ_home, λ_away)
```

The Skellam distribution (difference of two independent Poissons) gives a closed-form
PMF and CDF over integer goal differentials, including its mean (`λ_home − λ_away`)
and variance (`λ_home + λ_away`).

The rates `λ` are derived from **World Football Elo**, in two calibrated steps:

1. **Expected goal supremacy:** `sup = β · (Δr_eff / 100)`, where `Δr_eff` is the
   effective pre-match rating gap (home − away rating, plus a home-advantage term at
   non-neutral venues, mostly off for the World Cup). `β` is fit by
   least-squares-through-origin on historical `(Δr_eff, goal_diff)` pairs.
2. **Expected total goals:** `tot` = mean historical total goals.

Then `λ_home = (tot + sup)/2`, `λ_away = (tot − sup)/2`, clipped to a small positive
floor. This makes the model internally consistent: `E[d] = sup` and `Var[d] = tot`,
so the §3 z-score denominator is `√tot` by construction.

**Data sources (and a constraint).** Elo is *computed from scratch* over the
MIT-licensed [martj42/international_results](https://github.com/martj42/international_results)
match history (≈49k internationals), not scraped, so the ratings are fully
reproducible. (ClubElo is club-football only and unusable here; eloratings.net has no
clean API.) The original plan also blended in recent xG, but **FBref/Opta dropped
free xG on 2026-01-20**, so live national-team xG is no longer freely available. The
baseline is therefore Elo-driven; an xG term can later be folded into `sup`/`tot`
from a paid feed (Sportmonks, API-Football) or StatsBomb open data without changing
the interface.

### Result: multinomial

`P(W), P(D), P(L)` follow directly from the Skellam PMF by summing over
`d > 0`, `d = 0`, `d < 0`. This keeps the result and goal-difference models mutually
consistent (one generative process, two views).

## 3. Per-match residual (Layer 2)

How surprising was a single result, given a forecast? This is a per-match quantity
and uses **proper scoring rules and standardized deviations, not Brier**, which is
an aggregate score (§4) and carries no information on n = 1.

- **Result surprisal (log score):** `S_m = −log p_m(y_m)`, the negative log of the
  probability the forecast assigned to the outcome that actually happened. Higher =
  more surprising. Reported in nats (or bits).
- **Goal-differential z:** standardized deviation against the Skellam expectation,
  ```
  z_m = (d_m − E[d_m]) / sd[d_m] = (d_m − (λ_home − λ_away)) / sqrt(λ_home + λ_away)
  ```

### Sigma discipline

Soccer surprises are small. Calibration sanity:

| z (or equivalent tail) | reading |
|---|---|
| 0–1σ | unremarkable |
| 1–2σ | mild surprise; most "upsets" live here |
| 2–3σ | genuinely notable |
| 3–4σ | rare; double-check inputs |
| > 4σ | **almost certainly a misspecified variance model, not a miracle** |

A 12σ event has probability ≈ 10⁻²⁷. No thread will ever claim one. Saudi Arabia
beating Argentina at ~8% implied is ≈ 3.4σ on a Bernoulli win indicator and ≈ 1.4σ on
goal differential, the order of magnitude real upsets reach.

## 4. Market calibration: the headline (Layer 3)

Computed on `(market forecast, realized outcome)` pairs **directly**. The baseline
(§2) is not involved.

### Reliability: CORP (primary) + binned (intuition)

The **primary** reliability diagram is **CORP** (Consistent, Optimally binned,
Reproducible; Dimitriadis, Gneiting & Jordan, *PNAS* 2021): recalibrate forecasts by
isotonic regression (pool-adjacent-violators) instead of ad-hoc bins. This removes
the well-known instability of binning-and-counting under arbitrary bin choices and
yields **consistency bands** computed *under the null of calibration*: holding the
forecasts fixed, outcomes are resampled from them (the match is the resampling unit,
so a match's three mutually-exclusive W/D/L events stay coherent and dependent), PAV
is refit, and the pointwise 2.5/97.5 percentiles form the band. The band therefore
brackets the 45° identity line under the null, and the calibration claim is
"significant" only where the estimated CORP curve leaves that band. (This is the DGJ
consistency band — not a pair-bootstrap confidence band for the fitted curve, which
is miscentered for the test and would treat the 3N events as independent.)

The classic **binned** reliability table (mean prediction vs. observed frequency,
with Wilson CIs and **stated bin counts**) is retained for intuition. With n ≈ 104
matches, extreme-probability bins are sparse, so tail claims carry the widest bands
and are caveated hardest.

### Score decomposition: CORP (exact) + Murphy (binned)

The **CORP** decomposition splits the Brier score (or any proper score) as

```
Brier = MCB − DSC + UNC
```

- **MCB** (miscalibration, lower better): score of the forecasts minus score of their
  PAV-recalibrated version, the calibration penalty, measured *without binning*.
- **DSC** (discrimination, higher better): how much forecasts separate outcomes.
- **UNC** (uncertainty): base-rate difficulty, `ō(1−ō)`.

Crucially the identity is **exact for the raw score** (MCB is measured against the
recalibrated forecast, not coarse bins), unlike the classic Murphy
`Brier = Reliability − Resolution + Uncertainty`, which holds only up to within-bin
variance. I report both; CORP is the headline. For the multinomial result, the same
decomposition generalizes via the multi-category (ranked-probability) Brier.

### Calibration regression

As a binned-diagram-free check, regress the outcome indicator on the logit of the
implied probability:

```
logit(P(win)) = α + β · logit(q_win)
```

Perfect calibration ⇒ `α = 0, β = 1`. `β < 1` indicates overconfidence (the
favorite–longshot bias signature), and `α ≠ 0` indicates a directional tilt.

### Stratified questions

The same machinery, sliced:

- **Favorite–longshot bias**: realized frequency vs. implied probability at the
  tails (the least-data, most-caveated region).
- **Group vs. knockout efficiency**: calibration metrics computed within each stage.
- **Cross-venue update speed**: using the logged price time series (§5, §6),
  price discovery between Kalshi / Polymarket / Betfair on shared markets — matured
  into the §16 information-share machinery (the project's flagship).

## 5. Recovering implied probabilities from prices

Raw prices are not probabilities. For each venue:

- **Binary/contract markets (Kalshi, Polymarket):** price ≈ probability already, but
  remove the spread (use mid of bid/ask) and renormalize a market's contracts so they
  sum to 1 (remove the book's overround).
- **Bookmaker decimal odds (via the Odds API, incl. Betfair Exchange):** convert to
  `1/odds`, then strip the overround.

**Vig removal is a reported sensitivity, not a silent choice.** Proportional
(multiplicative) normalization is the naive default, but the margin is empirically
loaded more onto longshots, so the method shifts implied probabilities, most at the
tails and for soft books. I therefore compute implied probabilities under
**multiplicative, power, and Shin** methods (Shin models insider trading; the
academic standard) and report the spread. A calibration finding only counts if it
survives the devig choice. The logger stores **raw decimal odds**, so any method can
be re-applied to the full logged series after the fact. (Implementation:
`xresidual/devig.py`, wrapping penaltyblog.)

Each recovered `q_m` is tagged with its venue, timestamp, and a liquidity measure
(see §6). The **closing quote (last before kickoff)** is the calibration forecast:
it is the most efficient price the market reaches, aggregating all late information
(injuries, lineups, sharp money); the full time series feeds trajectory and lead–lag
analysis.

## 6. Data, liquidity, and the usable n

The theoretical population is 104 matches. The *usable* n depends on which markets
actually carry tradeable quotes. Winner markets are liquid across venues; individual
group-stage matches between lower-profile teams may not be.

The price logger (`logger/`, see repo README) is therefore **operationally
load-bearing and time-gated**: intraday cross-venue price history cannot be
reconstructed after the fact. It must run continuously from before the first match
(June 11, 2026). It also doubles as liquidity verification: markets it cannot
populate are markets I cannot analyze.

Reporting rule: **never quote n = 104 when the liquid subset is smaller.** Calibration
is reported on the liquid sub-population (stratified by a liquidity threshold); thin
markets get descriptive treatment only, and the split is stated explicitly.

## 7. Tournament trajectory (Layer 4)

From the logged winner-market series, track each team's implied championship
probability over time. Define a **belief-update velocity** as the magnitude of
revision per unit time (e.g. per match-day), and separate teams the market is
actively learning about (high velocity) from those already priced in (flat). Winner
markets are liquid, so this layer is well-supported even where per-match markets are
not.

### Format-aware tournament simulation, and team-strength uncertainty

The `model/` cards (advancement, third-place lottery and cut-line, decisive games,
knockout reach, title odds, dream-matchups, the group-finish incentive) come from a
vectorised Monte Carlo on the §2 baseline: sample every group fixture (Dixon–Coles
Poisson), rank each group (points → GD → GF), advance the top two plus the eight best
third-placed teams *jointly*, then play the fixed Round-of-32 → Final bracket (FIFA Annex
C resolves the third-place slots). Outputs are coherent by construction
(ΣP(advance) = 32, ΣP(qualify as a third) = 8).

A point-estimate rating treats a team's strength as known exactly, which leaves the
predictive distribution over-confident at the tails. So each simulation draws a per-team
strength offset `N(0, σ)`, **held constant across that team's whole tournament** (group
and knockouts), with **σ = 60 Elo**. σ is fit, not guessed: chosen by out-of-sample
Ranked Probability Score on ~13k competitive international matches since 2006 (weighted by
match importance × recency; `scripts/calibrate_sigma.py`), cross-checked against the
market's favourite concentration (~50) and the Glicko rating-deviation literature (tens of
Elo for national teams). The match-level RPS surface is flat over σ ≈ 60–80, so the lower,
market-consistent end is taken — σ's real effect is at the *tournament* level, where it
correlates a team's matches and widens the tails to a calibrated width.

Two analyses deliberately keep **σ = 0** because they isolate a single effect rather than
publish a probability forecast: the **value-blend check** (isolating what the *ratings*
do) and the **draw-luck counterfactual** (isolating what the *draw* does).

## 8. Team-level color (demoted, descriptive only)

Per-team residual summaries (e.g. "overperformed expectation in 3 of 4 matches,
largest +1.8σ vs. France") are reported as narrative color. **No Sortino ratios, no
bootstrap CIs presented as inferential**, since n = 3–7 cannot support them, and dressing
small-sample noise as a risk-adjusted metric is exactly the error this project is
designed to avoid.

## 9. Playing conditions specific to 2026

The 2026 tournament breaks two assumptions a generic baseline would make:

- **Not fully neutral.** The hosts (Mexico, USA, Canada) play group matches at home
  venues, so the Elo home-advantage term must be *on* for host fixtures, not forced to
  neutral. The magnitude is *calibrated to history*: regressing goal difference on a
  home dummy over ~50k matches puts a home side at ~0.47 goals, so `HOME_ADVANTAGE`
  is set to ≈ 85 Elo (down from 100, which implied ~0.54 goals, ~15% too high and
  inflating the 2026 hosts). All other matches are neutral.
- **Altitude: I tested it, and it didn't hold up.** Mexico City (~2,200 m, the
  highest-ever WC venue) and Guadalajara (~1,566 m) have thinner air, and the folk
  prior is "thin air → more goals." Regressing *total* goals on home-venue altitude
  across ~50k matches (controlling for team strength) gives a **negative, significant**
  coefficient (~−0.15 goals/1000 m), the opposite sign of the old +3%/1000 m prior.
  Altitude also touches only 7 of 72 group matches (all Mexico City / Guadalajara),
  and toggling it moved the hosts' advancement by <1pt. So the totals adjustment is
  **disabled** (factor set to 0). For honesty: a real altitude effect *does* show up on
  goal *difference* (home supremacy when adapted, ~+0.14 goals/1000 m, statistically
  significant), but it applies only to Mexico at home and is deliberately left out,
  since folding it in would only widen the host edge I am trying not to overstate.

Format (fixes n): 48 teams, 12 groups of 4, top two + eight best third-placed teams
→ Round of 32 → 104 matches over 39 days. Calibration n is bounded by 104 (further
reduced to the liquid subset, §6).

## 10. Prior art and positioning

Soccer betting-market (in)efficiency is well-studied. This project's novelty is the
*venue-comparative, market-grade calibration of a single major tournament in real
time*, not the discovery that markets are roughly efficient. Key anchors:

- The **traditional 1X2 market is biased** (favorite–longshot bias; favorites lose
  less than longshots), while the **Asian-handicap market is efficient/unbiased**
  (Ramírez, Reade & Singleton, *Int. J. Forecasting* 2025, "A Tale of Two Markets";
  Štrumbelj 2014 on implied probabilities). This is a **validation target**: I
  *expect* to find favorite–longshot bias (β < 1) in the h2h/1X2 feed. If I don't,
  that itself is the finding.
- Betting-odds consensus generally **out-forecasts Elo/FIFA-ranking models** (Leitner
  et al. 2010). So my Elo baseline is expected to be the *weaker* forecaster, which
  is fine: it is an independent reference, not a competitor to the market (§1).
- World-Cup-specific market (in)efficiency has been documented (e.g. *Int. J. Sport
  Finance* 2020). I differentiate by (a) cross-venue (prediction market vs sharp vs
  exchange), (b) CORP-grade calibration with consistency bands, and (c) live trajectory.

**Asian-handicap contrast (implemented).** The logger now also captures spreads and
totals (the Odds API exposes them), and `xresidual/asian_handicap.py` maps the
consensus handicap + totals lines to W/D/L probabilities via the same Skellam object
as the baseline. This lets me calibrate AH-implied probabilities against the same
outcomes as the 1X2 feed and report the efficiency contrast, a sharper result than
1X2 calibration alone. (Quota note: spreads+totals raise Odds API credit cost; the
closing line near kickoff is the priority capture if quota is tight.)

## 11. What would make this project wrong

Stated up front, because falsifiability is the point:

- If the calibration claims don't survive out-of-sample matches as the tournament
  progresses, they were noise.
- If recovered implied probabilities are sensitive to the overround-removal method
  (multiplicative vs power vs Shin, §5), the headline is fragile, so that sensitivity
  is reported alongside every calibration claim.
- If the liquid sub-population is too small for stable estimates, I say so and scope
  the claims down rather than overstate n; the CORP consistency bands make this visible.
- If the favorite–longshot bias the literature predicts fails to appear, I report the
  null rather than hunting for a slice that shows it.

A claim that cannot be wrong is not a finding.

## 12. Independent tournament simulation

Alongside the per-match baseline, the project runs a full **group-stage + knockout
Monte Carlo** (`xresidual/group_sim.py`, `xresidual/knockout.py`), 40,000 sims,
fully format-aware for 2026: the top two of each group plus the **8 best third-placed
teams** advance to the Round of 32, with the third-place bracket assignment following
**FIFA's Annex C constraints**, then simulated through to the Final. Match goals use the
same Elo-driven Skellam rates as §2, with a **Dixon–Coles low-score correction**
(`rho = −0.11`) that lifts the simulated draw rate from ~20% to ~22%, closer to the
empirical ~22–24%. The third-place teams are matched to the Round-of-32 winner slots
by a true **bipartite matching** (Kuhn's augmenting-path algorithm) that respects Annex C's
allowed-groups sets as hard constraints, so a group winner can never draw the third-placed
team from its own group — **no group-stage rematch in the R32** (verified 0 across 64k sims;
a greedy assignment silently produced ~3% rematches). The format invariants are **exact by
construction**: across sims the advancement probabilities sum to 32 and the third-place-
qualifier probabilities sum to 8, so any drift there is a code bug, not a modelling choice.

Validated against the Opta supercomputer, the simulation agrees strongly on most
advancement probabilities (Group C nearly identical; France / Norway / USA / Brazil /
Morocco within ~2pp). It is, however, **more top-heavy on favourites**:
e.g. it gives Spain ~28% to win the title vs ~16% from the market / Opta (Argentina
~19% vs ~10%). I traced the cause: not host, altitude, or home-advantage, but **Elo's
blindness to squad quality**. It rewards results, not the squad behind them, so it
over-rates teams whose record outruns their talent and under-rates squad-strong sides.
Blending in Transfermarkt squad value (Peeters 2018, which out-predicts Elo for
internationals) via `scripts/blend.py` (`0.4·z(Elo) + 0.6·z(log value)` through the
same sim) cuts the mean title-odds error vs Opta from ~4.7pp to ~0.7pp and converges
on the market too. So the overconfidence is largely a **fixable value-blindness**, not
an irreducible artifact. (I lack historical squad values, so this is a consistency
check against two independent sharp forecasters, not a backtest.) The pro-market reading
stands: the market already embeds squad value, form and news; the residual gap is the
rest, plus its natural caution. The simulated opener Mexico–South Africa sits at ~0.86.

## 13. Confederation-bias correction (empirical-Bayes shrinkage)

Elo is zero-sum: a result only transfers points between the two opponents, so the total
rating *inside* a confederation is conserved regardless of its true global level.
Confederations are near-disconnected clusters of the match graph, joined by sparse
inter-confederation "bridge" games, so the scale *between* clusters is weakly anchored and
drifts — weaker confederations accumulate inflated ratings against weak regional opponents,
and pure Elo cannot re-level them. Measured directly on the ~49k results, the recent
(since-2010) per-confederation Elo surprise in cross-confederation matches runs from UEFA
**+35** / CONMEBOL +24 (under-rated) to CONCACAF **−40**, AFC −22, OFC ~−160 (over-rated).

The fix (`xresidual/confed_bias.py`) is the standard remedy for a clustered comparison
graph: a per-confederation fixed-effect offset, applied as an **empirical-Bayes shrinkage**.
A base offset `δ[conf]` is estimated from cross-confederation results only (the games that
carry cross-cluster signal; UEFA = reference 0, recency-weighted 8y half-life). Each team
then gets `offset(team) = δ[conf] · K/(n_cross + K)`, where `n_cross` is its recency-weighted
count of cross-confederation games — the EB weight `τ²/(τ²+σ²)` with `σ² ∝ 1/n_cross`. A
globally-connected side (Mexico, Brazil; many intercontinental friendlies) is well-anchored
and lightly corrected; a regionally-isolated side falls back to its confederation prior. It
is applied to the raw Elo **before** the squad-value blend, so the globally-comparable squad
value corroborates the strong outliers rather than the blunt offset over-penalizing them.

Validation (`scripts/calibrate_confed_offsets.py`): a time-split, cross- vs within-
confederation stratified backtest. The shrinkage improves out-of-sample cross-confederation
RPS by **~+4.6%** (vs ~+3.9% for a flat per-confederation offset) and leaves the within-
confederation slice essentially unchanged (the placebo). The gain over the flat offset is
**significant after accounting for match dependence** (Diebold–Mariano with HAC SE, p ≈ 0.009;
team-cluster bootstrap 95% CI excludes 0) — and method b adds exactly one fitted parameter
(`K`) over method a, chosen on a held-out validation slice. Adjudicated against the
independent bookmaker, the corrected model agrees with the de-vigged outright consensus at
**0.95 rank correlation and a median 0.2pp** title-probability gap; the residual disagreements
are team-specific (Spain/Argentina a touch high, Brazil low — the Elo-vs-talent tension),
deliberately *not* curve-fit to the market. The literature endorses the approach: the bias is a
connectivity artifact (football-rankings.info 2022; Szczeciński & Roatis 2022, arXiv:2201.00691),
and connectivity-/uncertainty-weighted shrinkage is textbook empirical Bayes (James–Stein;
Efron–Morris; arXiv:1807.09236), with Glicko's rating deviation as the deployed analogue.

## 14. In-play capture and goal-overreaction detection (Layer 4, live)

The microstructure layer extends to live matches via `logger/ws_capture.py`: a single-clock,
**millisecond-stamped** websocket capture of the Kalshi and Polymarket order books for a named
fixture, written to per-capture files so each match is self-contained. From the reconstructed
mids, `xresidual/ws_events.py` auto-detects price shocks (goals, red cards) without a
hand-typed goal time, and `overreaction_backtest` fades them — the documented ~2–3%/trade
reversion after a *surprising* goal (Choi & Hui; "Role of Surprise"), entered ~2 min after and
held ~6 min, net of modeled cost. This is the P10 edge test, paper-only and disclosed. The
benchmark the live price is measured against is the in-play win-probability model (§17), which
re-prices each surprising goal to a fair value: the test reads the market as **under-reacting
to goals by ~5pp** relative to that benchmark before the fair value is reached.

Shock detection is tuned to reject thin-market noise (learned on the Argentina–Iceland friendly,
where the naive detector turned 3 goals into 11 "shocks"): a candidate fires only if the mid
moves **≥5pp within 60s AND the move persists** — still retaining ≥50% of the jump 20s later, so
a quote that flickers and snaps back is dropped while a goal that sticks is kept — with a 5-min
refractory (≈ the overreaction window) so one goal counts once. The friendly was a clean
pipeline dry-run but a *weak* edge test by construction: a 0.84 favourite scoring is not
surprising, so there is no overreaction to fade — exactly as the theory predicts. The live test
runs through the tournament on genuinely surprising goals.

## 15. Reproducibility and provenance

Every `scripts/build_all.py` run stamps a provenance record to `viz/_provenance.js`
(`xresidual/provenance.py`): the git SHA, the model parameters (blend weight, sigma, DC rho),
and **content-hash fingerprints** of every static input (results, fixtures, squad values). It
then compares each card's data against the inputs it was built from and **flags any card that is
stale** relative to an input that changed — a content-hash check, so it is touch-proof (editing
and re-saving a file with no real change does not trip it). The point is auditability: every
published card is traceable to the exact code and data that produced it, and the model can't be
changed without the build surfacing which cards now need regenerating. The simulation's own
format invariants (§12) are checked the same way — exact-by-construction, so a violation is a
code bug, not a silent modelling drift.

## 16. Price discovery across venues: lead–lag and information share (flagship)

This is the project's flagship microstructure result, and it matured over the tournament from
an early "which venue reads a goal first — does Kalshi or Polymarket move first?" framing into a
pooled, population-grade statement of price discovery. A standalone desk research note writes it
up in full (`writeups/price_discovery_note.pdf`).

**Pooled lead–lag (the headline).** Across the **34 captured matches** logged through
2026-06-20, **Polymarket leads ≈62% of goal repricings (103 vs 45 events, median +400ms)** — the venue that moves first when a goal
hits the book, pooled over every detected shock across all matches. Under the null of no lead
(a coin flip on which venue moves first), that lead is **≈4.8σ** naively (103 vs 45 of 148 decisive events). But the unit is the goal repricing,
not the match, so the inferential weight comes from the pool of shocks, not from any single
fixture; per-match leads are descriptive color.

**Information share (the mechanism).** The lead–lag count is corroborated by a structural
price-discovery decomposition. For each pair of matched contracts across the two venues, I fit a
**VECM on the two order-book MID series** and compute both the **Hasbrouck (1995) information
share** and the **Gonzalo–Granger (1995) permanent-component share**. The decomposition is
**gated by a cointegration test** (ADF / Engle–Granger): only matched contracts that pass are
pooled, since the shares are only defined when the two mids share a common stochastic trend.
Computing on **mids** is what makes this robust to the trade-direction-classification problem —
Lee–Ready-style signing misclassifies ≈59% of prediction-market trades (arXiv:2604.24366), so any
flow- or trade-signed discovery measure would inherit that error; the MID series carries no
direction to misclassify. Result: **Polymarket's permanent-component share is ≈78.6%**, and it
**leads in 20/21 cointegrated matches (34 contracts)** — the same venue, the same direction as the raw lead–lag
count, which is the cross-check that makes the flagship robust. The ≈62% lead and the ≈78.6%
information share are two independent reads of one fact: Polymarket is where this World Cup's
price is discovered.

## 17. In-play win-probability model

The benchmark against which a live price is judged (the §14 / §16 goal tests) is a model of
**fair win/draw/loss probability conditional on the live game state** (score and time elapsed).
Remaining goals for each side are modelled as **independent Poisson processes over the time left**,
so the in-play W/D/L distribution follows from convolving the two remaining-goal counts with the
current score — the same Skellam logic as §2, run on the remainder of the match rather than the
whole. The per-team in-play rates are **calibrated so that at minute 0 (kickoff, 0–0) the model
recovers the pre-kickoff market W/D/L probabilities exactly**; the rates are then carried forward
and the distribution is re-evaluated as the clock runs. On each goal, the state **snaps** to the
new score (a per-goal shock snap), and the model re-prices the remaining match from that new state.
This gives a continuous fair-value track that jumps at goals, which is precisely the object the
in-play "market under-reacts to goals (~5pp)" test fades the market against (§14): the gap between
where the price moves and where the WP model says it should move.

## 18. Order-flow imbalance: the within-venue mechanism

Lead–lag and information share (§16) describe *which venue* moves first; order-flow imbalance
explains *how* flow becomes price **inside** a venue. I compute **OFI à la Cont, Kukanov &
Stoikov (2014)** from **order-book level changes** — the signed change in depth at the best
quotes as the book updates. It is **book-derived, not trade-signed**, so like the §16 mids it is
**immune to the ≈59% trade-direction-classification problem** (arXiv:2604.24366): nothing is
inferred about whether a trade was buyer- or seller-initiated. Regressing contemporaneous mid
changes on OFI gives the within-venue impact channel, **strongly significant (t ≈ 30)** — the
mechanism linking flow to price impact that sits underneath the cross-venue lead. Where the book
detail supports it, the **microprice (Stoikov 2017)** — the size-weighted fair value between bid
and ask — is the natural companion estimate of where the next mid is headed, refining the plain
bid/ask mid the rest of the pipeline uses.

## 19. Draw-rate calibration: validated, applied forward only

The 2026 World Cup's 48-team format ran an unusually high draw rate, and the v2 draw-rate
adjustment (a recalibration of the Dixon–Coles low-score correction, §12) was **validated out of
sample** against the realized results. It is, however, **applied forward only**. The forward
ledger **locks every committed forecast** as of its capture timestamp — the whole point of a
forward-only ledger is that a forecast cannot be revised after the fact — so the draw fix is
**forked forward into new scripts and never back-edited into a committed forecast**. This is the
same discipline as the v1 file-level freeze (the §2/§12 core is not edited; improvements fork
forward), so the out-of-sample claim stays honest: the validation set is genuinely held out from
the forecasts the fix would change.
