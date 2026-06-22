# Visualizations

Every xResidual chart, by what it's *sourced from*: `model/` reads our own Elo + Poisson
simulation, `market/` reads logged venue prices (Polymarket, Kalshi, The Odds API) and the
captured in-play tapes. Flags (`flags/`) and `render.sh` are shared at the top level.

> Note: the card **templates** (`*.html`) and `render.sh` are kept out of the public repo;
> the rendered PNGs and the analysis that feeds them (`scripts/build_*.py`, `_*.js`) are
> what's published. The commands below are the maintainer's local workflow.

Render any card from the repo root, e.g.:

```
./viz/render.sh model/group_openness.html      # -> viz/model/group_openness.png
./viz/render.sh market/cross_venue_basis.html  # -> viz/market/cross_venue_basis.png
```

Each card ships in the same paper / crimson editorial house style (`Fraunces` display,
`Spline Sans` body, `IBM Plex Mono` labels) at 1600×900, rendered 2× to a 3200×1800 PNG, so
the feed reads as one brand.

---

## `model/` — our Elo + Poisson simulation

The independent fundamental model: blended (Elo + squad-value) ratings → supremacy → Skellam
→ group-stage + knockout Monte Carlo. Most cards condition on every game played so far.
Data: `_groupsim.js` (`build_group_sim.py`), `_knockout.js` (`build_knockout.py`),
`_elimination.js`, `_simnative.js`, `_mispricing.js`, plus the per-card builders noted below.

### Qualification & format (the advancement/leverage family)

| Card | What it shows |
|---|---|
| `group_openness` | advancement per group — top-2 vs the third-place lottery — with a market overlay |
| `third_place_lottery` | which group sends its third-placed team through (8 of 12 do) |
| `third_place_cutline` | the points the last-qualifying third needs (about one win, median 3 pts) |
| `jeopardy_gd` | **NEW** — the final R32 ticket is decided on goal difference: the last third in and the first out finish level on points 86% of the time. The data answer to the "no jeopardy" format critique |
| `garbage_time` | **NEW (cross: GD-jeopardy × leverage)** — for a third-placed team, advancing is a goal-difference cliff: one goal dragging it from −1 to level GD is worth **+28pp** of reaching the R32, scoreable in garbage time of a settled game. The highest-leverage goal nobody watches |
| `decisive_games` | Schilling match leverage — the midtable six-pointers swing qualification most, not the glamour ties |
| `bubble` | the whole qualification fight is a handful of coin flips: most teams are already locked above 70% or below 30% to advance |
| `r32_routes` | the likely Round-of-32 opponent and draw difficulty per group (via the Annex C feeder tree) — winning your group is an unequal prize |
| `group_incentive` | does winning your group pay? 1st-vs-2nd knockout-path difficulty (incentive incompatibility) |
| `draw_luck` | who won the group draw — each team's top-2 odds in its real group vs its mean over legal re-draws (isolates draw luck, best-third safety net handled) |
| `travel_burden` | the group-stage travel draw — the brutal trips land on the bubble teams (underpowered; reference only) |
| `heat_exposure` | who drew the worst heat schedule (FIFPRO extreme-risk venues × afternoon kickoffs) |

### Model diagnosis & calibration (how the model thinks)

| Card | What it shows |
|---|---|
| `elo_value_blend` | the model's blind spot — Elo is value-blind; blending in Transfermarkt squad value collapses the error vs Opta (~4.7pp → ~0.7pp) |
| `strength_lenses` | three reads on the same field — Elo vs squad value vs market — and where they disagree |
| `model_vs_market` | model title odds vs de-vigged Polymarket: the favourites-run-hot divergence |
| `market_efficiency` | model vs market across every layer (238 contracts) — how sharp the market is, and where the thin structural markets drift |
| `backtest_wc` | the per-match baseline backtested on 2018 + 2022 (no lookahead) — "two World Cups in residuals" |
| `elimination` | our 7-way stage-of-elimination distribution vs Polymarket's new market (a coherence edge the sim prices for free) |
| `model_blindspot` | **NEW (cross: squad-value lean × live results)** — where the model leaned against the market, the market won (corr −0.82, n=9): teams it rated above the market are underperforming, below are overperforming. The disagreement was information |

### Match-outcome findings

| Card | What it shows |
|---|---|
| `draws_paradox` | **NEW** — goals up *and* draws up: 2026 (3.09 g/g, 30% drawn) sits in a corner of the goals×draws map no modern World Cup has reached |
| `mismatch_draws` | the market under-prices a favourite parked to a draw by an organised minnow (the favourite's blind spot — **thesis since RETIRED**, regressed out of sample) |
| `draw_basket` | backing those mismatch-draws as a tradeable basket (companion to `mismatch_draws`; same retired thesis) |
| `overreaction_surprise` | fade a goal's overbet *only* after a surprising goal — the conditional version of the textbook reversion play |

### Fun / reach (entertaining, thin insight — interleave honestly)

| Card | What it shows |
|---|---|
| `collision` | Messi–Ronaldo and dream-matchup probabilities from the bracket sim |
| `collision_matrix` | symmetric heatmap: P(any two contenders meet in the knockouts) |
| `storylines` | the tournament's big questions answered by 200k sims (African final, host semi, the curse…) |

---

## `market/` — prediction-market / bookmaker / in-play data

Sourced from logged venue prices and the captured websocket tapes.
Data: `_forecast.js` (`pull_forecast_data.py`), `_insights.js` (`build_insight_data.py`);
the microstructure/tape cards read `docs/data/leadlag.js`, `_ofi.js`, `_livewp.js`,
`_livematch.js`; the trajectory cards inline their logged snapshots.

### Market structure & pricing

| Card | What it shows |
|---|---|
| `cross_venue_basis` | Kalshi vs Polymarket, two venues one price — the gap is mostly house margin; the residual belief gap is a structured home-crowd tilt (+ a Betfair sharp anchor). The most "prediction-market quant" card |
| `patriotic_premium` | **NEW (cross: home-crowd tilt × price leadership)** — the US exchange (Kalshi) prices the USA +2.4pp above the sharp line vs +0.5pp on the price-leading global venue; it pays up for the North American hosts, Polymarket for the European/South American giants. Sentiment, priced |
| `money_map` | where $ turnover concentrates — the favourites are the *least*-traded |
| `liquidity_tax` | **NEW** — the cost of a bet by market type: the title market trades at a 0.1c spread, the obscure derived markets (finish-third, stage-of-elimination) at 2.0c — 20× wider. Plus the vig term structure (Polymarket ~2% vs Kalshi ~5–9%, widening at kickoff) |
| `coherence_ladder` | **NEW** — the probability staircase: each team's nested ladder (reach R32 ≥ R16 ≥ QF ≥ SF ≥ Final ≥ win) descends monotonically; 0 arbitrage violations across 282 checks. The nested markets are internally consistent |
| `flb_wedge` | the favourite–longshot bias as a sportsbook-vs-prediction-market wedge |
| `longshot_tick` | the longshot tax hiding in the 1¢ tick |
| `onchain_whales` | on-chain: the longshot volume is a few whales, not a crowd |
| `survival` | conditional survival decoded — paper tigers vs deep runners |
| `group_board` | group-winner probability, de-vigged Polymarket (reference) |
| `outlook` | bracket-stage reach probabilities (reference) |
| `must_watch` | the most dramatic group games by bookmaker consensus (reference) |
| `predboard` | the prediction board — the model's live calls scored against the market |

### The live title race

| Card | What it shows |
|---|---|
| `buildup_trajectory` | the live title race — daily de-vigged championship odds (the recurring hero card) |
| `chaos_mirage` | the favourites stumbled but the title market only moved ±3pp — it re-sorted the contenders, it didn't panic |
| `contested_title` | **NEW** — belief volatility as small-multiple sparklines: the title prices that moved most over the buildup were the *contenders* (Argentina ±1.46pp, Spain, Portugal), not the longshots. A volatile price is one the crowd is still arguing over |

### Microstructure & in-play (the cross-venue price-discovery flagship)

Tape-derived, from the captured `ws_capture` websocket feeds. Processed by `build_micro_all.py`
(tapes are ~1.3 GB each, so they're parsed once on the VM and fed to every pipeline).

| Card | What it shows |
|---|---|
| `leadlag_lead` | the pooled flagship — Polymarket prices a goal first across the match pool (22 matches, ~62% of repricing events, ~3.4σ) |
| `leadlag_tape` | a single match's tape: who priced the goal first, to the millisecond |
| `ofi_mechanism` | order-flow imbalance → price impact, the within-venue mechanism (Cont-Kukanov-Stoikov; t≈30) |
| `live_match` | a match's in-play win-probability tape with auto-detected goal shocks |
| `livewp_underreaction` | our in-play win-probability model vs the live market — the market under-reacts to goals (~5pp) |
| `book_vanishes` | **NEW (anatomy of a goal)** — at a goal the order book evaporates: Polymarket spread ~8×, best-price depth →<1%; Kalshi 2×, →~1%; refill ~3–4s. The price leader withdraws hardest |
| `goal_discovery` | **NEW (anatomy of a goal)** — price discovery concentrates at the news: Polymarket's information share is ~86% in goal windows vs ~53% in calm play. The lead is a news-event phenomenon, not a steady hum |
| `edge_mirage` | **NEW (anatomy of a goal)** — the lead is real but untradeable: the stale follower is +10.2c on paper on every goal, but depth at the goal is 0.4% of normal → **0% harvestable**. The honest capstone |
| `adverse_selection` | **NEW (the maker's view)** — the same ~11c reframed from the quoter's side: a maker who holds a resting quote through a goal is picked off for ~11c, so the book-pull (8× spread, depth→0) *is* the adverse-selection defence. The "what a quoter loses" chart for a market-making audience |

> The rigorous information-share version (Hasbrouck 1995 + Gonzalo-Granger permanent-component,
> `build_infoshare.py` → `_infoshare.js`, Polymarket GG ~78%) feeds `leadlag_lead` and the desk
> research note (`writeups/price_discovery_note.pdf`), the flagship's release vehicle.

### Cross cards (model × market) — the "two ideas crossed" scatter set

A deliberately different idiom (scatter quadrant, not div-bars) that signals "two ideas" at a glance.

| Card | What it shows |
|---|---|
| `trap` | incentive path-delta × market group-win premium — the market pays up to win the groups where winning is the *harder* knockout path |
| `smartmoney` | on-chain whale concentration × model advance-edge — the teams the money piles into are the ones the model fades ("loud money, not smart money") |
| `stakes` | Schilling leverage × combined title odds — the deciders and the must-watches are different games |

---

## Rebuild data

**One command** regenerates every offline `_*.js` and re-renders every card (continue-on-error,
prints a pass/fail summary, stamps provenance):

```
python scripts/build_all.py             # everything: data + render
python scripts/build_all.py --pull      # rsync the VM's fresh snapshots + results cache first (condition on current games)
python scripts/build_all.py --offline   # skip the two live-network builders (forecast, on-chain)
python scripts/build_all.py --render-only   # re-render PNGs from existing _*.js
python scripts/build_all.py --models-only / --markets-only
```

Cards that **inline** their own data (`buildup_trajectory`, `leadlag_tape`, `draws_paradox`,
`jeopardy_gd`, …) have no builder — they're rendered like any other card.

### Individual builders

Model pipeline (offline compute):

```
python scripts/build_group_sim.py        # model/_groupsim.js   (openness, third-place lottery/cutline, decisive, bubble)
python scripts/build_knockout.py         # model/_knockout.js   (r32_routes, bracket reach)
python scripts/build_blend_check.py      # model/_blend.js      (elo_value_blend: Elo vs value-blend vs market/Opta)
python scripts/build_lenses.py           # model/_lenses.js     (strength_lenses)
python scripts/build_collision.py        # model/_collision.js  (collision, collision_matrix; 200k sims)
python scripts/build_storylines.py       # model/_storylines.js (narrative scenarios; 200k sims)
python scripts/build_travel.py           # model/_travel.js
python scripts/build_heat.py             # model/_heat.js
python scripts/build_incentive.py        # model/_incentive.js  (group_incentive)
python scripts/build_drawluck.py         # model/_drawluck.js   (draw_luck)
python scripts/build_elimination.py      # model/_elimination.js (7-way stage-of-elimination vs Polymarket)
python scripts/build_simnative.py        # model/_simnative.js  (format-native market families)
python scripts/build_mispricing.py       # model/_mispricing.js (model_vs_market, market_efficiency; runs LAST)
python scripts/backtest_wc.py            # model/_backtest_wc.js (2018+2022 backtest)
```

Market pipeline (logged prices; two builders hit a live API):

```
python scripts/pull_forecast_data.py     # market/_forecast.js   (Polymarket Gamma, live) + flags
python scripts/build_insight_data.py     # market/_insights.js
python scripts/build_money_map.py        # market/_money.js      (money_map)
python scripts/build_flb_wedge.py        # market/_flb.js        (flb_wedge, longshot_tick)
python scripts/build_survival.py         # market/_survival.js
python scripts/build_basis.py            # market/_basis.js      (cross_venue_basis + Betfair sharp anchor)
python scripts/build_buildup_trajectory.py  # market/_buildup.js (daily de-vigged title odds; auto-extends)
python scripts/build_onchain.py          # market/_onchain.js    (Polymarket on-chain wallet flow, live)
python scripts/build_trap.py             # market/_trap.js       (cross: incentive × group-win premium)
python scripts/build_smartmoney.py       # market/_smartmoney.js (cross: on-chain whales × model edge)
python scripts/build_stakes.py           # market/_stakes.js     (cross: leverage × title odds)
python scripts/prediction_board.py       # market/_predboard.js  (the prediction board)
```

Tape-based microstructure (run from the captured websocket data, usually on the VM):

```
python scripts/build_micro_all.py        # single-parse driver: feeds leadlag, infoshare, ofi, livewp, live_match
python scripts/build_leadlag.py          # docs/data/leadlag.js  (leadlag_tape, leadlag_lead)
python scripts/build_infoshare.py        # market/_infoshare.js  (Hasbrouck + Gonzalo-Granger info share)
python scripts/build_ofi_leadlag.py      # market/_ofi.js        (ofi_mechanism)
python scripts/build_livewp.py           # market/_livewp.js     (livewp_underreaction, live_match)
```
