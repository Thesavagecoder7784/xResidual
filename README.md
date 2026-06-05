# xResidual

**A live look at how prediction markets price the 2026 World Cup — and what they reveal about it.**

Markets like **Kalshi** and **Polymarket** turn thousands of opinions and real money
into a single, continuously-updating number: the live probability of every World Cup
outcome. xResidual follows those numbers across all 104 matches
(June 11 – July 19, 2026), alongside the global **bookmaker** consensus, to show what
the sharpest real-time forecasts on earth reveal about the tournament — the title
race, the shocks, how fast belief moves — and just how good these markets really are.

A *residual* is what's left after you subtract expectation from reality — the
surprise. The markets supply the expectation; the World Cup supplies the surprises.
This project is about both.

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

## Live findings

Updated weekly during the tournament. Each links to the thread and the notebook.

- Group-stage note — *pending June 2026*
- Knockout note — *pending July 2026*
- Tournament retrospective: *"The 2026 World Cup, in residuals"* — *pending*

## Under the hood

The accessible framing sits on a rigorous engine (full spec in [METHODOLOGY.md](METHODOLOGY.md)):

- **Expectation baseline** — World Football Elo (computed from 49k open results) →
  a Skellam goal model, 2026 host/altitude-aware. An *independent* yardstick for
  measuring surprise — not a market-beater.
- **Residuals** — per-match surprise as a log-score and a standardized z, with honest
  sigma discipline (real upsets are 1–3σ; >4σ means a broken model).
- **Sharpness & calibration** — CORP isotonic reliability diagrams with bootstrap
  consistency bands, an exact Brier decomposition, and multi-method vig removal
  (multiplicative / power / Shin) so findings survive the de-vig choice.
- **Microstructure** — order-book depth & spread, cross-venue convergence, and
  price discovery / lead–lag (does Kalshi or Polymarket move first?) across the
  venues. *(Early read: Polymarket quotes ~27× Kalshi's depth at the same ~0.1¢
  spread on the title race.)*
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

- `xresidual/` — the engine: Elo/Skellam baseline + residuals, calibration (CORP),
  cross-venue microstructure, trajectory, plots.
- `logger/` — append-only price logger across Kalshi / Polymarket / Odds API
  (the live, time-gated data capture; runs via `launchd`).
- `scripts/` — `run_analysis.py` (full report), `make_figures.py` (figures),
  `build_baseline.py`, `calibration_backtest.py`.
- `tests/` — 42 unit tests across the math core, calibration, microstructure, and pipeline.

```bash
pip install -r requirements.txt
python scripts/run_analysis.py     # live findings to date
python scripts/make_figures.py     # render the charts
```

## Follow along

Threads at [@PrabhatM27](https://twitter.com/PrabhatM27) · part of my work at
[thesavagecoder7784.github.io](https://thesavagecoder7784.github.io/).

## License

MIT.
