# xResidual

**A live look at how prediction markets price the 2026 World Cup — and what they reveal about it.**

Markets like **Kalshi** and **Polymarket** turn thousands of opinions and real money into a single, continuously-updating number: the live probability of every World Cup outcome. xResidual follows those numbers across all 104 matches (June 11 – July 19, 2026), alongside the global **bookmaker** consensus, to show what the sharpest real-time forecasts on earth reveal about the tournament — the title race, the shocks, how fast belief moves — and just how good these markets really are.

A *residual* is what's left after you subtract expectation from reality — the surprise. The markets supply the expectation; the World Cup supplies the surprises. This project is about both.

![The 2026 title race as the prediction markets price it through the buildup](viz/market/buildup_trajectory.png)

## What it does

Two kinds of question:

**🎯 What the markets reveal about the World Cup (the fun part)**
- **The title race in motion:** whose championship odds are climbing, whose are
  collapsing, and the biggest single-day repricings. ("The market doubled Morocco's
  semifinal odds in 90 minutes" is a story.)
- **The tournament's biggest shocks — and how fast the market absorbed them.** When an
  8%-underdog wins, even an efficient market is surprised; watching it re-price in
  real time is the interesting part (a ~3σ event — *not* the "12σ" nonsense you'll see
  elsewhere).
- **Where the prediction markets and the bookmakers see the tournament differently** —
  and how tightly the prediction markets agree with each other.

**📈 How well the markets work (the quant part)**
- Just how **calibrated** are prediction markets on a chaotic, expanded 48-team field?
  (Early research says: remarkably — this is a project about *demonstrating* that.)
- Do real-money prediction markets **aggregate information better than traditional
  bookmakers**?
- How does **price discovery** unfold — how fast does the market sharpen as news and
  kickoff approach?
- How tightly do **Kalshi and Polymarket converge** once you strip the margins?
  (So far: within ~0.1–0.2 percentage points on the title race.)

## Why this one exists

I've already built [QuantF1](https://thesavagecoder7784.github.io/) — a hierarchical
Bayesian, risk-adjusted performance model for Formula 1. xResidual is its **live,
public counterpart**: lighter, faster, running in real time during the tournament
rather than as a retrospective. Its edge is *timeliness* (this can only happen
June–July 2026) and *prediction-market microstructure* — comparing three venues as a
global event unfolds.

**What it is not:** a betting model or an attempt to out-predict the markets. The
whole premise is the opposite — these markets are *very hard to beat*, so instead of
competing with them, xResidual treats them as the best available lens on the
tournament and asks how they work. Findings travel because they're analysis;
predictions only travel when they're right.

## Findings

Running notes — each finding framed by the decision it implies — live in
[FINDINGS.md](FINDINGS.md). Pre-tournament reads already there: Polymarket quotes ~27×
Kalshi's depth at the same spread; every title favorite is sell-heavy; the
favorite–longshot bias is hiding in the 1¢ tick; and the "altitude → more goals" edge
doesn't survive a look at the historical data.

Tournament notes (updated weekly):

- Group-stage note — *pending June 2026*
- Knockout note — *pending July 2026*
- Tournament retrospective: *"The 2026 World Cup, in residuals"* — *pending*

## Under the hood

The accessible framing sits on a rigorous engine (full spec in [METHODOLOGY.md](METHODOLOGY.md)):

- **Expectation baseline** — World Football Elo (computed from 49k open results) →
  a Skellam goal model, host-aware with home advantage *calibrated to history*
  (~0.47 goals → `HOME_ADVANTAGE` ≈ 85). The "altitude → more goals" prior was
  tested on ~50k matches and dropped — the totals coefficient came back negative. An
  *independent* yardstick for measuring surprise — not a market-beater.
- **Independent tournament simulation** — a format-aware group→Final Monte Carlo
  (40k sims, 8 best thirds via FIFA Annex C, Dixon–Coles low-score correction), with
  a model-vs-market comparison. Pure Elo runs hotter on favourites than the market;
  diagnosing that as Elo's *blindness to squad value* and blending in Transfermarkt
  values (Peeters 2018) collapses the gap vs Opta from ~4.7pp to ~0.7pp — a transparent
  model corrected by the market's own key input.
- **Residuals** — per-match surprise as a log-score and a standardized z, with honest
  sigma discipline (real upsets are 1–3σ; >4σ means a broken model).
- **Sharpness & calibration** — CORP isotonic reliability diagrams with bootstrap
  consistency bands, an exact Brier decomposition, and multi-method vig removal
  (multiplicative / power / Shin) so findings survive the de-vig choice.
- **Microstructure** — order-book depth & spread, **order-book imbalance** (do the
  favorites sit bid or offered?), cross-venue convergence, price discovery / lead–lag
  (does Kalshi or Polymarket move first?), and **bookmaker dispersion** (which matches
  are the books most divided on?). *(Early reads: Polymarket quotes ~27× Kalshi's
  depth at the same ~0.1¢ spread; every title favorite is sell-heavy, OBI ≈ 0.2.)*
- **Trajectory** — implied championship probability and belief-update velocity over
  the tournament.

Validated before kickoff: the calibration stack reproduces a clean reliability
diagram on 3,850 historical international forecasts, and the live pipeline already
prints the title race and market-vs-baseline gaps for upcoming fixtures.

## A note on honesty (it's the point)

A single tournament is ~104 matches, so probability claims at the extremes carry wide
error bars — and the consistency bands show exactly where a finding is real versus
noise. Per-team "who's clutch" takes are flagged as small-sample color, never dressed
up as inference. Where the markets are sharp, the project says so; where reality
surprised them, that's the tournament doing its job, not the market failing. A claim
that can't be wrong isn't a finding.

## Repo layout

- `xresidual/` — the engine: Elo/Skellam baseline + residuals, `group_sim.py` /
  `knockout.py` (the format-aware tournament Monte Carlo), calibration (CORP),
  cross-venue microstructure, order-book imbalance, `ws_events` (ms lead–lag),
  trajectory, plots.
- `logger/` — append-only price logger across Kalshi / Polymarket / Odds API, plus
  `ws_capture.py` (real-time websocket capture for the lead–lag flagship). The live,
  time-gated data capture; runs via `launchd`.
- `scripts/` — `run_analysis.py` (full report), `make_figures.py` (figures),
  `build_baseline.py`, `calibration_backtest.py`, `build_group_sim.py` /
  `build_knockout.py` (write the simulation cards), `pull_forecast_data.py` /
  `build_insight_data.py` (write the market cards).
- `viz/` — editorial cards: `model/` (simulation: group openness, third-place lottery
  & cut-line, decisive games, R32 routes, model-vs-market, **value-blend diagnosis**,
  strength lenses, travel draw) and `market/` (group board, outlook, must-watch,
  longshot tick, buildup trajectory, lead–lag tape, **money map**, **FLB wedge**,
  **survival/paper-tigers**, **on-chain whales**). The analysis (`scripts/build_*.py`)
  and the rendered PNGs are public; the card HTML/CSS templates are kept private.
- `tests/` — 63 unit tests across the math core, calibration, microstructure,
  pipeline, plots, and lead–lag.

### Reproduce

```bash
pip install -r requirements.txt
python scripts/run_analysis.py        # live findings to date
python scripts/build_all.py           # regenerate every card's underlying data (_*.js)
```

> The analysis that produces each card (`scripts/build_*.py`) and the rendered **PNGs**
> are published; the editorial card **templates** (the HTML/CSS look) are kept private,
> so `build_all` regenerates the data here while the committed PNGs are the visuals.

Two layers, two reproducibility stories:

- **The model engine is fully reproducible from public sources.** `xresidual/data*.py`
  fetch results, fixtures, and historical forecasts (martj42, openfootball, 538) and
  cache them under `data/` on first run — so the simulation, calibration, and
  `viz/model/` cards regenerate from a clean clone with no inputs to supply.
- **The market layer streams from a live logger you run.** `logger/` records Kalshi /
  Polymarket / Odds API prices to `logger/data/` (git-ignored — those feeds aren't ours
  to redistribute). The generated `viz/market/` data and PNGs are committed so the cards
  render as-is; regenerating them yourself means running the logger with your own API
  keys (`cp logger/config.example.json logger/config.json`).

## Follow along

Threads at [@PrabhatM27](https://twitter.com/PrabhatM27) · part of my work at
[thesavagecoder7784.github.io](https://thesavagecoder7784.github.io/).

## License

MIT.
