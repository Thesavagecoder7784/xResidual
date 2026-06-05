# Methodology

This document is the spine of the project. It commits, up front, to the variance
models and scoring rules used everywhere downstream. If a claim in a thread or
notebook isn't grounded in something defined here, it isn't a finding.

## 0. The central question

We are not forecasting match outcomes, and we are not trying to beat the markets.
We study **how three markets — Kalshi, Polymarket, and the bookmaker consensus —
price the World Cup, and what they reveal about it**, in real time. Three lenses, all
built on the same variance model:

- **Residuals** — the tournament's surprises, measured against the market's
  expectation (and how fast the market re-priced them).
- **Microstructure** — how the venues converge, who incorporates information faster,
  and how prediction markets compare to traditional bookmakers.
- **Calibration / sharpness** — over the match population, how good are the markets'
  probabilities?

A single forecast cannot be evaluated: a 65% price followed by a loss is not an
error, because 35% events occur 35% of the time. So a surprise is the tournament
doing its job, not the market failing — and calibration is only defined over a
*population* of forecasts. The 2026 World Cup supplies one (≈104 matches), so those
population-level claims carry the inferential weight, while the cross-venue and
residual lenses also work per-match. Anything computed per-team (n = 3–7) is
descriptive color, never an inferential claim.

## 1. Outcome spaces and notation

For each match `m` we work with two outcome representations:

- **Result**: a categorical outcome `y_m ∈ {home win, draw, away win}` (W/D/L from a
  fixed reference team). Forecasts are probability vectors `p_m = (p_W, p_D, p_L)`.
- **Goal differential**: `d_m = goals_home − goals_away`, an integer.

Two distinct objects are tracked and must not be confused:

- The **market** forecast `q_m` — implied probabilities recovered from prices (§5).
  This is the object under study.
- The **baseline** forecast `b_m` — a model from public data, Elo + xG (§2). This is
  an *independent* benchmark, used only for the secondary "can a public-data model
  beat the market?" question. **It is never used to judge the market's calibration**,
  because the baseline itself ingests market information and judging the market
  against a market-derived yardstick is circular.

## 2. Expectation baseline (Layer 1)

A per-match expectation built from public data, independent of the calibration test.

### Goal differential — Skellam

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
   non-neutral venues — mostly off for the World Cup). `β` is fit by
   least-squares-through-origin on historical `(Δr_eff, goal_diff)` pairs.
2. **Expected total goals:** `tot` = mean historical total goals.

Then `λ_home = (tot + sup)/2`, `λ_away = (tot − sup)/2`, clipped to a small positive
floor. This makes the model internally consistent: `E[d] = sup` and `Var[d] = tot`,
so the §3 z-score denominator is `√tot` by construction.

**Data sources (and a constraint).** Elo is *computed from scratch* over the
MIT-licensed [martj42/international_results](https://github.com/martj42/international_results)
match history (≈49k internationals), not scraped — so the ratings are fully
reproducible. (ClubElo is club-football only and unusable here; eloratings.net has no
clean API.) The original plan also blended in recent xG, but **FBref/Opta dropped
free xG on 2026-01-20**, so live national-team xG is no longer freely available. The
baseline is therefore Elo-driven; an xG term can later be folded into `sup`/`tot`
from a paid feed (Sportmonks, API-Football) or StatsBomb open data without changing
the interface.

### Result — multinomial

`P(W), P(D), P(L)` follow directly from the Skellam PMF by summing over
`d > 0`, `d = 0`, `d < 0`. This keeps the result and goal-difference models mutually
consistent (one generative process, two views).

## 3. Per-match residual (Layer 2)

How surprising was a single result, given a forecast? This is a per-match quantity
and uses **proper scoring rules and standardized deviations — not Brier**, which is
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
| 1–2σ | mild surprise — most "upsets" live here |
| 2–3σ | genuinely notable |
| 3–4σ | rare; double-check inputs |
| > 4σ | **almost certainly a misspecified variance model, not a miracle** |

A 12σ event has probability ≈ 10⁻²⁷. No thread will ever claim one. Saudi Arabia
beating Argentina at ~8% implied is ≈ 3.4σ on a Bernoulli win indicator and ≈ 1.4σ on
goal differential — that is the order of magnitude real upsets reach.

## 4. Market calibration — the headline (Layer 3)

Computed on `(market forecast, realized outcome)` pairs **directly**. The baseline
(§2) is not involved.

### Reliability — CORP (primary) + binned (intuition)

The **primary** reliability diagram is **CORP** (Consistent, Optimally binned,
Reproducible; Dimitriadis, Gneiting & Jordan, *PNAS* 2021): recalibrate forecasts by
isotonic regression (pool-adjacent-violators) instead of ad-hoc bins. This removes
the well-known instability of binning-and-counting under arbitrary bin choices and
yields resampling-based **consistency bands** — the calibration claim is "significant"
only where the 45° line leaves the band.

The classic **binned** reliability table (mean prediction vs. observed frequency,
with Wilson CIs and **stated bin counts**) is retained for intuition. With n ≈ 104
matches, extreme-probability bins are sparse, so tail claims carry the widest bands
and are caveated hardest.

### Score decomposition — CORP (exact) + Murphy (binned)

The **CORP** decomposition splits the Brier score (or any proper score) as

```
Brier = MCB − DSC + UNC
```

- **MCB** (miscalibration, lower better): score of the forecasts minus score of their
  PAV-recalibrated version — the calibration penalty, measured *without binning*.
- **DSC** (discrimination, higher better): how much forecasts separate outcomes.
- **UNC** (uncertainty): base-rate difficulty, `ō(1−ō)`.

Crucially the identity is **exact for the raw score** (MCB is measured against the
recalibrated forecast, not coarse bins), unlike the classic Murphy
`Brier = Reliability − Resolution + Uncertainty`, which holds only up to within-bin
variance. We report both; CORP is the headline. For the multinomial result, the same
decomposition generalizes via the multi-category (ranked-probability) Brier.

### Calibration regression

As a binned-diagram-free check, regress the outcome indicator on the logit of the
implied probability:

```
logit(P(win)) = α + β · logit(q_win)
```

Perfect calibration ⇒ `α = 0, β = 1`. `β < 1` indicates overconfidence (the
favorite–longshot bias signature); `α ≠ 0` indicates a directional tilt.

### Stratified questions

The same machinery, sliced:

- **Favorite–longshot bias** — realized frequency vs. implied probability at the
  tails (the least-data, most-caveated region).
- **Group vs. knockout efficiency** — calibration metrics computed within each stage.
- **Cross-venue update speed** — using the logged price time series (§5, §6), lead–lag
  between Kalshi / Polymarket / Betfair on shared markets.

## 5. Recovering implied probabilities from prices

Raw prices are not probabilities. For each venue:

- **Binary/contract markets (Kalshi, Polymarket):** price ≈ probability already, but
  remove the spread (use mid of bid/ask) and renormalize a market's contracts so they
  sum to 1 (remove the book's overround).
- **Bookmaker decimal odds (via the Odds API, incl. Betfair Exchange):** convert to
  `1/odds`, then strip the overround.

**Vig removal is a reported sensitivity, not a silent choice.** Proportional
(multiplicative) normalization is the naive default, but the margin is empirically
loaded more onto longshots, so the method shifts implied probabilities — most at the
tails and for soft books. We therefore compute implied probabilities under
**multiplicative, power, and Shin** methods (Shin models insider trading; the
academic standard) and report the spread. A calibration finding only counts if it
survives the devig choice. The logger stores **raw decimal odds**, so any method can
be re-applied to the full logged series after the fact. (Implementation:
`xresidual/devig.py`, wrapping penaltyblog.)

Each recovered `q_m` is tagged with its venue, timestamp, and a liquidity measure
(see §6). The **closing quote (last before kickoff)** is the calibration forecast —
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
(June 11, 2026). It also doubles as liquidity verification — markets it cannot
populate are markets we cannot analyze.

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

## 8. Team-level color (demoted, descriptive only)

Per-team residual summaries (e.g. "overperformed expectation in 3 of 4 matches,
largest +1.8σ vs. France") are reported as narrative color. **No Sortino ratios, no
bootstrap CIs presented as inferential** — n = 3–7 cannot support them, and dressing
small-sample noise as a risk-adjusted metric is exactly the error this project is
designed to avoid.

## 9. Playing conditions specific to 2026

The 2026 tournament breaks two assumptions a generic baseline would make:

- **Not fully neutral.** The hosts (Mexico, USA, Canada) play group matches at home
  venues — the Elo home-advantage term must be *on* for host fixtures, not forced to
  neutral. All other matches are neutral.
- **Altitude and heat shift scoring.** Mexico City (~2,200 m, the highest-ever WC
  venue) and Guadalajara (~1,566 m) have thinner air (faster ball, less air
  resistance); June–July heat plus mandatory hydration breaks affect tempo. Both
  plausibly move expected *total* goals (the Skellam `tot`) for matches at those
  venues. The baseline exposes `tot` as a per-match quantity precisely so a venue
  adjustment can be applied; absent a fitted effect we flag altitude/heat venues
  rather than silently assuming league-average totals.

Format (fixes n): 48 teams, 12 groups of 4, top two + eight best third-placed teams
→ Round of 32 → 104 matches over 39 days. Calibration n is bounded by 104 (further
reduced to the liquid subset, §6).

## 10. Prior art and positioning

Soccer betting-market (in)efficiency is well-studied — this project's novelty is the
*venue-comparative, market-grade calibration of a single major tournament in real
time*, not the discovery that markets are roughly efficient. Key anchors:

- The **traditional 1X2 market is biased** (favorite–longshot bias; favorites lose
  less than longshots), while the **Asian-handicap market is efficient/unbiased**
  (Ramírez, Reade & Singleton, *Int. J. Forecasting* 2025, "A Tale of Two Markets";
  Štrumbelj 2014 on implied probabilities). This is a **validation target**: we
  *expect* to find favorite–longshot bias (β < 1) in the h2h/1X2 feed. If we don't,
  that itself is the finding.
- Betting-odds consensus generally **out-forecasts Elo/FIFA-ranking models** (Leitner
  et al. 2010). So our Elo baseline is expected to be the *weaker* forecaster — which
  is fine: it is an independent reference, not a competitor to the market (§1).
- World-Cup-specific market (in)efficiency has been documented (e.g. *Int. J. Sport
  Finance* 2020). We differentiate by (a) cross-venue (prediction market vs sharp vs
  exchange), (b) CORP-grade calibration with consistency bands, and (c) live trajectory.

**Asian-handicap contrast (implemented).** The logger now also captures spreads and
totals (the Odds API exposes them), and `xresidual/asian_handicap.py` maps the
consensus handicap + totals lines to W/D/L probabilities via the same Skellam object
as the baseline. This lets us calibrate AH-implied probabilities against the same
outcomes as the 1X2 feed and report the efficiency contrast — a sharper result than
1X2 calibration alone. (Quota note: spreads+totals raise Odds API credit cost; the
closing line near kickoff is the priority capture if quota is tight.)

## 11. What would make this project wrong

Stated up front, because falsifiability is the point:

- If the calibration claims don't survive out-of-sample matches as the tournament
  progresses, they were noise.
- If recovered implied probabilities are sensitive to the overround-removal method
  (multiplicative vs power vs Shin, §5), the headline is fragile — so that sensitivity
  is reported alongside every calibration claim.
- If the liquid sub-population is too small for stable estimates, we say so and scope
  the claims down rather than overstate n; the CORP consistency bands make this visible.
- If the favorite–longshot bias the literature predicts fails to appear, we report the
  null rather than hunting for a slice that shows it.

A claim that cannot be wrong is not a finding.
