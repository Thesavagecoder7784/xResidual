# Findings: a trader's read of the 2026 World Cup markets

A living log. Each entry states what the data shows, then *what it would mean to someone trading or making markets on it*. The point isn't the chart, it's the decision the chart implies. Methodology in [METHODOLOGY.md](METHODOLOGY.md); numbers regenerate from `scripts/run_analysis.py`.

Live snapshot, updated 2026-07-03: the World Cup is **in progress** — the Round of 32 is nearly complete and the Round of 16 is underway. Data has accumulated since June 5, 2026. Claims sharpen as the sample grows; small-sample reads are flagged, and the early pre-tournament reads below now have first contact with results to test them against.

> **Model limitations & claim guardrail (audited 2026-06-26).** The core methods are sound (Elo, Skellam, CORP+consistency bands, info-share VECM/Hasbrouck-GG, OFI, the sims); these are the edges where the model *misleads*, so check any public claim against them.
> - **CAN claim:** BTTS (calibrated, esp. BTTS-YES); the cross-venue flagship (Polymarket leads ~73% of decisive events / ~79% info share, 48 of 56 and 50 of 51 matches respectively, lead un-harvestable — significance is the **match**, never the event); and the headline — **the market is better calibrated than the pre-committed model** (P1, in-band, +17% skill over 58 games).
> - **Do NOT claim:** a **totals/Over edge** (the model is flat — one global total-goals constant gives ~52% Over for every game); a **BTTS-NO / "won't score"** on an attacking side (the model under-rates in-form attacks, e.g. Norway λ≈1.0 vs 3.5 scored); an **advancement** call against the market (the model over-rates bubble third-place teams); or **"model beats the market"** off one game (the 58-game result is the opposite — a lone rested-USA upset where pre-committed v1 had Turkey 39% to the market's 24% is a real timestamped win but n=1 and reason-adjacent). Harvest "0%" is a conservative **bound**, significance is **match-level only**, and the results feed lags 1-2 days (verify standings against current data).

**On multiplicity.** These are the survivors of a wider exploratory sweep, and the angles that didn't hold are logged as nulls — or retracted out of sample — rather than buried: altitude as a goals edge (#7), heat on the pre-match goal line and on cards (#13, #17), the group-winner watch-list "drama" (#14), the cross-venue convergence paper-trade (#20), and the now-**retracted** mismatch-draw read (#31). Read the numbered list as the reported set — nulls and retractions included — not a cherry-picked highlight reel. The binding, pre-committed tests (with significance and power thresholds set before outcomes) live in [PREREGISTRATION.md](PREREGISTRATION.md); the descriptive reads here are kept honest by grading against those.

---

## 1. Polymarket quotes ~27× the depth of Kalshi, at the same spread

Across all 48 title contracts, median best-level bid depth is ~8.2M contracts on Polymarket vs ~305k on Kalshi, while the top-of-book spread is ~0.1¢ on both.

**The trader's read.** Spread tells you the cost of crossing; depth tells you how much you can do before you move the price. Same spread, ~27× the depth means Polymarket is where size goes on the World Cup outright: a marketable order that barely dents Polymarket would walk through several levels on Kalshi. If you're *allocating* liquidity (the market-maker's actual job), Kalshi's thin-but-tight book is the more delicate inventory problem. You're quoting a competitive spread without much cushion,
so adverse selection bites harder. Neither is "better"; they're different regimes, and a maker would size and skew very differently on each.

## 2. Every title favorite is sell-heavy

Order-book imbalance (bid share of top-of-book depth) sits at ~0.16–0.27 for *every* top contender on Polymarket, i.e. roughly 75–85% of resting size is on the offer.

**The trader's read.** The book wants to *sell* favorites, not buy them. Two readings, both interesting: (a) holders of favorite-YES are queued to take profit / provide exit liquidity, so a maker on the bid is absorbing persistent one-sided flow and should quote with that adverse-selection skew in mind; (b) it's the favorite–longshot structure showing up in the book itself, since people don't love *holding* a low-payout favorite, so supply piles up. Either way, "favorites are structurally offered" is a standing feature to quote around, not noise. The live test, arming as passes accumulate: does today's imbalance predict tomorrow's price move?

## 3. The two prediction markets agree to ~0.15pp: law of one price holds

Median cross-venue divergence (Kalshi vs Polymarket, de-vigged) on the title race is ~0.15pp; the largest standing gap is England (~1pp).

**The trader's read.** This is what an efficient, well-integrated market looks like: the same outcome is priced within a fraction of a cent across two independent venues, so there's no free lunch sitting on the screen. The standing England gap is the one worth watching. It's the most-traded contract, so a persistent gap there is more likely a real audience/fee difference than a stale quote. The open question this
sets up, *when news breaks, which venue moves first?*, is the price-discovery
question, and the lead–lag machinery is in place to answer it once matches start
generating shocks.

## 4. The books agree Argentina is a favorite; they disagree on *how much*

Across 14 bookmakers, the widest cross-book disagreement is Jordan vs Argentina
(7.5pp on Argentina), then Cape Verde vs Saudi Arabia and DR Congo vs Uzbekistan.

**The trader's read.** Dispersion marks where information is least settled. It's not
the toss-ups that divide the books, it's *how dominant* a heavy favorite is against a
low-information opponent (a debutant, a thin sample). For someone shopping a line,
those are the matches where venue choice matters most; for an analyst, dispersion is a
cleaner uncertainty proxy than the consensus price alone.

## 5. The model is more confident than the market, as it should be

The Elo/Skellam baseline prices the opener Mexico–South Africa at ~0.86 vs the market's
~0.67 (home advantage calibrated to history: ~0.47 goals → HOME_ADVANTAGE ≈ 85).

**The trader's read.** The baseline is *supposed* to lose this contest. Markets price
things a rating system can't (squad news, motivation, money), and the literature is
clear that betting-odds consensus out-forecasts Elo. The baseline's job here isn't to
beat the market; it's the independent yardstick that lets me *measure surprise*. When
a result lands far from the market, that's the residual worth a thread; when it lands
far from the baseline but near the market, that's the market knowing something the
model doesn't.

## 6. The favorite–longshot bias is hiding in the tick

Absolute spreads are flat, ~1¢ on *every* contract, favorite or longshot, both
venues. But relative to price, a 1¢ spread is ~1.1% of a 16% favorite and **~16–18%
of a 1.5% longshot**, 15–17× wider.

**The trader's read.** The classic favorite–longshot bias is usually hunted for in
the *prices*; here it's baked into the *tick structure*. Because the tick can't go
below 1¢, longshots are structurally expensive to trade in/out of: your round-trip
cost on a 1.5% team is a sixth of your stake before you're right about anything. That
caps how efficient longshot pricing can be (no one arbs a 16%-spread market), which is
itself a mechanism behind the favorite–longshot bias the literature documents.

## 7. What the market expects to be a goal-fest (and why altitude isn't the edge)

Inverting the over/under lines to implied expected goals: the market expects the most
in **Germany–Curaçao (4.3)**, Brazil–Haiti (3.9), Spain–Cape Verde (3.6), and
the fewest in Ivory Coast–Ecuador (2.1).

The twist: the "thin air → more goals" prior doesn't survive contact with history. The
market's median implied total at the 7 high-altitude matches (Mexico City, Guadalajara)
is already *lower* (2.48) than at sea level (2.64), and when I regressed total goals on
home-venue altitude across ~50k matches (controlling for team strength), the coefficient
came back **negative and significant** (~−0.15 goals/1000 m), the opposite sign of the
old prior. So I removed the altitude-totals factor from the model entirely.

**The trader's read.** This is the model being disciplined, not the market being wrong:
I had a folk-physics prior, tested it on real data, and it didn't hold, so it's gone.
The market was already pricing altitude games *lower*, and history backs that side. (A
real altitude effect does exist on goal *difference* for an adapted home side, but that
applies only to Mexico at home, and I leave it out rather than widen the host edge.)

## 8. The third-place lottery is wide open: about one win is enough

The independent tournament Monte Carlo (40k sims, format-aware via FIFA Annex C) says
**8 of the 12 third-placed teams advance** to the Round of 32, and the cut-line for the
last qualifying third is essentially one win: a median of 3 points is enough to go
through.

**The trader's read.** "Finishing third" is barely an elimination in this format, so a
third-place exit contract should price more like a coin-flip than a write-off, and a
single group win flips a team from bubble to through. For market-watchers, the live
question is *which* group sends its third: the cut-line is so low that goal difference
and the order of fixtures, not raw quality, decide the last few seats.

## 9. The decisive games are the midtable six-pointers, not the glamour ties

Ranking group matches by Schilling leverage (how much a single result swings the
simulated advancement field), the highest-impact fixtures are the midtable
"six-pointers" between two bubble teams, not the marquee clashes between two
favourites who were both advancing anyway.

**The trader's read.** The repricing energy lives where qualification is genuinely in
the balance. A favourite-vs-favourite tie is a great watch but moves the advancement
board little; the unglamorous 2nd-vs-3rd seed match is where a goal redraws the whole
group. For anyone trading advancement (not outright) markets, the six-pointers are the
events to be positioned and capture-ready for.

## 10. The model runs hotter on favourites than the market does

My pure Elo/Skellam simulation gives **Spain ~28% to win the title; the market and Opta
have it ~16%** (Argentina ~19% vs ~10%). I chased the cause, and it isn't host, altitude,
or home-advantage. It's that Elo only sees results: it over-rates teams whose record
outruns their squad (Argentina) and under-rates squad-strong sides (France, England,
Germany). Blending in Transfermarkt squad value, which Peeters (2018) showed
*out-predicts* Elo for internationals, collapses the mean title-odds error vs Opta
from ~4.7pp to ~0.7pp, landing the model on the market and Opta at once. (I lack
historical squad values, so that's a consistency check against two independent sharp
forecasters, not a backtest.)

**The trader's read.** When a clean fundamental model is *more* top-heavy than the
market, the gap is a measure of what the market knows that the model doesn't (squad
quality, form, news, money), plus its natural caution. The useful part: most of this gap
turned out to be squad value specifically, fixable rather than mysterious, and blending it
in makes the model agree with the market. The market stays the better-calibrated of the
two; the exercise just shows exactly *what* it was pricing that a ratings model wasn't.

## 11. The flattest pre-tournament field in recent World Cups

The top of the 2026 winner market sits at **~16%** (Spain and France, Polymarket, with a
near-zero ~2% overround), and the top four are ~49% combined. For comparison, the
pre-tournament *favourite* was priced ~20% in 2010 (Spain, 4/1) and 2022 (Brazil, 4/1)
and ~18% in 2018 (Germany/Brazil, +450), so 2026's top is lower than any recent edition.

**The trader's read.** Genuine parity is part of it, but part is *mechanical*: a 48-team
field with an extra knockout round (the Round of 32) spreads championship probability
across more teams and adds a round of variance, so the favourite is structurally lower
than in a 32-team event. Worth saying out loud so the openness isn't oversold as pure
parity. The defensible claim is "most open pre-tournament field in recent World Cups,"
not "ever": pre-expansion tournaments aren't an apples-to-apples comparison, and outright
de-vigging conventions differ across sources. Stated carefully, it's a clean, checkable
hook; stated as "most open ever," it's the kind of line that invites a correction.

## 12. Two venues, one price: the cross-venue gap is mostly vig, and the residual is structured

Following up on #3: stripping each venue's overround, the de-vigged title prices on
Polymarket and Kalshi agree to **~0.15pp on average** across the field. The "5–8¢ gap"
the press quotes is mostly the house margin, not disagreement. Kalshi's overround
runs ~5.4% vs Polymarket's ~3.0% (~1.8×), so the durable venue difference is *cost,
not price*. The small belief-gap that does survive is structured by audience: the
American book (Kalshi) is richer on USA, Mexico, Netherlands; the global book
(Polymarket) is richer on England, Portugal, Japan, Brazil. Anchored against the
Betfair Exchange (the sharpest soccer market I log), Polymarket sits marginally
closer to the sharp line (mean abs error ~0.12pp vs ~0.16pp).

**The trader's read.** Decompose a cross-venue quote into *belief + margin* and almost
all of the visible gap is margin, so the relative-value trade isn't "buy here, sell
there" on price, it's recognising that the same exposure costs ~1.8× the vig on one venue.
The residual belief gap is the interesting microstructure: it lines up with who's in the
room. A primarily-American book pays up for its home region (USA, Mexico) while a global,
soccer-literate book pays up for traditional powers (England, Portugal) and football-mad
markets (Japan, Brazil). That's a *home-crowd tilt*, exactly the kind of structural
signal a venue-aware maker would skew around, and the Betfair anchor says the global
crowd is, if anything, the marginally sharper of the two. (Single-snapshot read; the
logged series is what confirms the tilt persists.)

## 13. The heat draw is lopsided, but it's exposure, not an edge

FIFPRO names six host cities "extremely high risk" of heat-stress injury for afternoon kickoffs (Atlanta, Dallas, Houston, Kansas City, Miami, Monterrey). Scoring each team's group games by venue and local kickoff time, the draw is uneven: **Netherlands and Portugal drew the worst** (two extreme-risk games each), while four teams (Paraguay, Turkey, New Zealand, Panama) drew none.

**The trader's read.** Heat is a real competitive factor people are talking about, and the schedule draw is a clean, sourced piece of context. But I checked whether it's actually *priced* and it doesn't survive scrutiny. Raw market implied totals are *higher* at hot matches (~3.13 vs ~2.59 goals), but only because the schedule happened to put blowouts (Germany–Curaçao, Spain vs minnows) in hot afternoon slots, which is team mismatch, not heat. Isolating a heat effect would need to control for strength, and with only ~9 extreme-heat matches pre-tournament it's underpowered. So heat stays exposure/context, never a model input or a claimed edge, the same call I made on altitude. The honest version is a map of who drew the brutal schedule, not a goals prediction.

## 14. The heat draw is a TV artifact, and the watch-list isn't in on it

Following #13: the kickoff times explain *why* the heat draw is lopsided. A US afternoon kickoff is a European evening, so European sides get scheduled into US afternoons for home prime-time TV, and that's the heat window. **European-involved group games sit in the afternoon slot 50% of the time vs 18% for everyone else, and 23% are extreme-heat vs 0% without** — all 23 UK prime-time matches are US-afternoon. So Netherlands and Portugal didn't get unlucky; Europe pays a heat tax for its own audience.

I also tested the obvious next question, are the most-watchable games stuck in the heat, and the answer is no. Mean drama (bookmaker closeness + implied goals) is flat across slots (~0.34 afternoon vs ~0.36 evening), and the top-15 must-watch games skew to evening US prime-time. Reporting the null.

**The trader's read.** The schedule is fixed and known in advance, so whatever heat does to play (slower tempo, late-game fatigue) is concentrated on European teams in identifiable slots — that's priceable context, not a surprise to fade in-running. And the watch-list null is the useful discipline: the intuitive "best games are buried in the heat" connection sounds right and just isn't there, so I checked instead of assuming.

## 15. Winning your group mostly pays, but not in Group C (or A)

For each group I measured the expected opponent Elo over the first two knockout rounds (R32 + projected R16) for the **group winner vs the runner-up**, over 60k sims on the fixed bracket. In 10 of 12 groups winning pays, often by a lot: the winner draws materially weaker early opponents (Portugal **+124**, Argentina **+121**, England **+116** Elo easier). But in **Groups C and A the runner-up's path is the easier one**: Brazil's group winner faces a **~48-Elo-tougher** opening than finishing second, Mexico's about 28. (Group B is a coin-flip.)

**The trader's read.** This is incentive incompatibility (Csató et al.) made concrete: a fixed bracket can reward losing. The magnitudes are modest (a few percent of win-probability over two rounds, not a reason to tank), and it's a first-two-rounds measure, so deeper paths can move it. But it's a real structural quirk: in a couple of groups the "always win your group" cliché is wrong, and a side already safely through could rationally rest players or treat the last group game as the lighter priority. Pro-market framing: the schedule, not any team, creates the edge, and it's identifiable in advance, so it's priceable rather than a scandal.

## 16. The best-third safety net cushions the group of death — the draw really bites the bubble

I measure draw luck on what matters — odds of **reaching the Round of 32** (top two *or* one of the eight best thirds) — by re-running the actual draw 1,500 times under FIFA's real constraints (pots, confederation rules, hosts fixed) and comparing each team's real group to a fair re-draw (Csató 2025 method; a full neutral group-stage sim each re-draw, so the best thirds are picked jointly). The headline is counterintuitive: **the safety net protects the strong**. Senegal, drawn into Group I (France's group of death), saw its odds of *winning* the group fall ~22pp from the draw — but its odds of *advancing* fall just **~7pp (still ~81%)**, because a quality side that finishes third usually grabs a best-third spot. The draw's real victims are the **bubble teams** whose only realistic route is a third place and whose group kills it: **Tunisia −17, Australia −12**. The biggest gift draws went to minnows who landed soft groups: **Bosnia +21, Egypt +17, Czechia +15**.

**The trader's read.** The eight-best-thirds rule is a shock absorber: it makes a brutal draw nearly costless for a strong side (stumble to third, still go through) and concentrates the draw's real impact on the Pot 3–4 bubble, where a third place is the only door. So "group of death" panic is *overpriced* for the favourites and *underpriced* for the minnows — exactly the kind of mispricing an advancement market can carry. As with heat and the group-finish incentive, the edge is structural (the draw plus the format), identifiable in advance.

## 17. Heat's real effect is in-play, not in the pre-match goal line

Following #13/#14. The sports-science literature is consistent that heat's robust effect on football is physical and in-play: players cover less ground and reduce their second-half workload in the heat (documented back to the 2014 Brazil World Cup), while the effect on shots and goals is weak and contested (some studies even find attacking efficiency *rises* in warmth). That matches what the pre-match data showed here: no clean heat signal in implied total goals. So the sharp version of the heat question isn't "does the market underprice goals in hot games" (a null), it's in-play: do extreme-heat afternoon games slow in the second half — fewer goals after the 75th minute, and does the live total drift toward the under faster than in cool games?

I pre-registered this as **P9** (graded Jul 19): late-goal rate plus second-half in-play total drift, extreme-heat afternoon games vs the rest. It is underpowered by construction (~9 extreme-heat afternoon games), so it will most likely resolve inconclusive. It is a falsifiable *test* of the in-play channel, not a claim.

I also checked the adjacent "heat moves cards, not goals" angle (cards-per-foul rises with temperature in the literature). **Not pursuable here:** the Odds API feed I log carries only h2h, totals, spreads, and outrights — no cards/bookings market — so there is no data to test it without a new source.

**The trader's read.** This is the disciplined progression of a null. Pre-match, heat is exposure, not an edge (#13). The one place it could still bite is in-running, the second-half slowdown, and that is exactly where the in-play capture can test it, live, on a pre-committed rule. Reporting the mechanism honestly — and the data gap that kills the cards angle — beats forcing a goals story the evidence does not support.

## 18. The heat schedule doesn't ease off in the knockouts, it intensifies

A natural worry: do the heat-drawn teams carry that load into the knockouts? Two separate things, and only one is clean. **The schedule is the clean one.** Every knockout slot's venue and kickoff time is already fixed, so this is deterministic, not a forecast: the dangerous afternoon-in-an-extreme-city share **roughly doubles** from the group stage to the knockouts (**14% → 28%**), with afternoon kickoffs rising 38% → 56% and extreme-heat cities 36% → 47%. Even the semi-finals (Dallas 14:00, Atlanta 15:00) and the final (New York 15:00) are afternoon slots. Same mechanism as the group stage (US afternoon = global/European prime-time TV), plus it is early-mid July by then, hotter than mid-June.

Because the bracket is a fixed tree of venue-assigned slots, a team's entire knockout venue path is set the moment it finishes 1st or 2nd in its group. Summing group plus win-out-path heat, the heaviest total loads fall on **Netherlands and Argentina** (each with two extreme-heat knockout games on the path).

The cumulative-*fatigue* claim (heat-laden teams underperform later) is the weaker story: it is confounded with team strength (the heat-exposed sides are mostly strong Europeans who advance anyway), the literature supports per-match slowdown rather than cross-match carryover, and the sample is tiny. So cumulative load is reported as exposure, never as a claimed edge.

**The trader's read.** The heat story has an arc: the group stage is who drew the hard schedule, and the knockouts are where the tax intensifies and compounds on the deep-running (mostly European) sides. It stays exposure, identifiable in advance, never a model input. The honest output maps who carries the most heat into each round; it does not claim heat decides the knockouts.

## 19. The market overbets favourites to win their group

Comparing the blended model's P(finish 1st) against Polymarket's 12 group-winner markets, the clear favourite is systematically overpriced to top its group and the second-tier team underpriced. **Germany to win Group E is ~68% in the market vs ~50% in the model; Brazil to win Group C is ~72% vs ~57%** — while the strong challengers are cheap: Morocco (Group C) **20% vs 32%**, Ecuador (Group E) **22% vs 32%**. (The host cases, Canada and Switzerland in Group B, are left out: that gap is a home-advantage modelling disagreement, not a clean bias.)

**The trader's read.** This is the favourite-longshot bias again, one layer down. The crowd backs the obvious name to win its group the way it overpays for longshots elsewhere, even when the group is genuinely contested. Group C is the tell: Morocco (a 2022 semifinalist) makes Brazil's first place far from a lock, which is the *same* reason the bracket hands Brazil's runner-up an easier path (#15). So the favourite-to-win-group leg is rich and the strong challenger's leg is cheap. Together with the new elimination market's deep-run overpricing, these are the two places the World Cup markets are visibly soft, and both are the same favourite-overbet instinct showing up in the less-liquid market layers, never in the deep ones (the winner and continent markets are coherent and efficient).

## 20. The cross-venue convergence trade doesn't pay (a null)

The other side of #12. The de-vigged gap being mostly margin (#3, #12) predicts there is *no* arbitrage to harvest from it — so I paper-traded it to check, out-of-sample: when the Polymarket–Kalshi belief gap on a title widens past 1.0pp, go long the cheap venue and short the rich one, exit on convergence below 0.3pp or after 8 passes, net of a 0.5pp modeled round-trip cost. Result over the buildup: **6 trades, −2.6pp total, 0% hit rate, per-trade Sharpe −1.95** (`viz/*/_forwardtest.js`). The gap is real but it doesn't converge enough to clear costs.

**The trader's read.** This is the honest confirmation of #12: the visible gap is the vig, and once you pay the vig to trade it there's nothing left. A negative result, reported as one — the convergence "edge" is a cost illusion, which is exactly what the law-of-one-price finding implied.

## 21. The market is sharp where it's liquid — and where we disagree, it's usually us

The favourite-longshot threads (#6, #11, #19) and the reach-round check are really one question, so I scanned it systematically: our model's probability against the de-vigged market for **238 contracts across five layers**, from the deepest liquid market to the thinnest structural one. The mean |model − market| gap, by layer:

| layer | depth | mean abs gap | verdict |
|---|---|---|---|
| Winner | deepest / most liquid | **0.4pp** | efficient — model agrees with the sharp market |
| Advance (R32) | liquid | 4.3pp | **our model, not the market** (see below) |
| Reach QF | thinner | 3.3pp | thin-market softness (partly model tilt) |
| Reach SF | thin | 1.9pp | thin-market softness (partly model tilt) |
| Champion (elimination mkt) | thinnest / newest | 1.0pp | favourite overpricing (#11), partly model tilt |

Two things make this more than a chart. First, the **winner market is efficient** — our model and the market agree to under half a point — which is the control that says the divergences elsewhere aren't just the model being biased everywhere. Second, I refused to take the biggest gap at face value: the **advance-layer** divergence (our model says minnows like Tunisia and South Africa advance ~26% vs the market's ~37%) was adjudicated against an **independent third source, the bookmakers' de-vigged match odds**. Bookmakers rate those teams *higher* than our model too (Tunisia expected group points 2.45 vs our 1.92; South Africa 2.57 vs 1.89), siding with the market. So that gap is **our model under-rating minnow advancement in the generous 48-team format — not market softness.** The same event drives it home: "champion" prices efficiently in the liquid winner market but is overpriced in the thin elimination market.

**The trader's read.** This is the synthesis of half the findings into one term structure, and the headline is pro-market: the World Cup market is **hard to beat wherever there's liquidity**, and the only genuinely soft corners are thin, new, or structural — the favourite deep-run overpricing, sized small and caveated. The point isn't a basket of edges; it's the discipline — scan every layer, check your own signals against an independent source before believing them, and report honestly when the market wins, which here it mostly does.

---

## 22. Elo inflates weak confederations — the market wasn't fooled, the edge was ours to fix

Chasing the thin-market "edges" from #21 to ground — Mexico, Canada, Japan all *looked* underpriced to advance — hit the same wall every time: an independent bookmaker sided with the market, not us. The common cause was structural. Elo is zero-sum, and the six confederations are near-disconnected islands in the match graph: they mostly play themselves, with only sparse inter-confederation "bridge" games to anchor the global scale, so weak confederations quietly inflate against weak regional opponents. Measured on 49k results, in cross-confederation games CONCACAF runs ~40 Elo and OFC ~160 Elo *below* what their ratings imply, while UEFA/CONMEBOL run above. New Zealand was advancing in ~39% of our sims; corrected, it's ~20%.

The fix is an empirical-Bayes confederation shrinkage (`xresidual/confed_bias.py`): a per-confederation offset estimated from the bridge games only, scaled per team by how globally-connected it is (Mexico plays everyone → barely corrected; an isolated minnow → fully corrected). Validated out-of-sample — **+4.6% cross-confederation RPS, Diebold–Mariano p≈0.009, within-confederation untouched as a placebo** — and the literature backs it (a known connectivity artifact; the fix is textbook James–Stein / Glicko-RD shrinkage).

**The trader's read.** This is the inverse of an edge story, and the more honest one: the apparent mispricings in the thin advance/reach markets weren't the market being soft, they were *us* over-rating teams from weak confederations. The market had already priced what our Elo couldn't see. After the correction the model agrees with the de-vigged bookmaker consensus at **0.95 rank correlation** (median 0.2pp), and the only gaps left are defensible team-specific calls — we like Spain/Argentina a touch more than the market, Brazil a touch less — that I won't curve-fit away. The contribution is a sharper model and a clean template: check a "market mispricing" against an independent third source before believing it.

## 23. First live in-play tape: the pipeline works, and the overreaction edge needs a real surprise

Captured the Argentina–Iceland friendly end-to-end — **172,892 millisecond-stamped order-book events**, the full chain (VM capture → pull → reconstruct mids → fade backtest) proven on live in-play data for the first time. Argentina opened a 0.84 favourite and won 3–0; the market jumped only on Barco's 8' opener and shrugged off the 72'/86' goals — a 0.91 favourite extending a lead isn't news.

That makes it a clean dry-run but a deliberately *weak* test of the goal-overreaction edge (P10): the documented reversion fades **surprising** goals, and a heavy favourite scoring is the opposite of surprising, so there was nothing to fade — exactly as theory predicts. It did expose one methodology fix: the naive shock detector turned 3 goals into 11 "shocks" on a thin friendly, so it's now hardened (a ≥5pp move that *persists* 20s later, 5-min refractory) — 11 → 3. **The real test waits for a genuine surprise**: an underdog scoring, or a favourite conceding, once the tournament starts.

## 24. Two World Cups, dry-run: the model is well-calibrated, real shocks are 2–3σ, and 2022 was the chaotic one

Before trusting the framework live on 2026, I ran it end-to-end on **two** completed tournaments — every 2018 and 2022 World Cup match (128 in all). **No lookahead, audited:** each game is scored with the point-in-time pre-match Elo (the rating is causal by construction — verified identical to ~0.01 Elo whether or not post-tournament data exists), and each tournament's goal-model params are calibrated *strictly* on matches before it. Two tournaments, not one, on purpose: 2022 was upset-heavy, so a single sample can't tell a real model property from that year's noise. Running 2018 separates them — and it overturned a lesson I'd drawn from 2022 alone.

| | 2018 | 2022 |
|---|---|---|
| median \|z\| · max \|z\| | 0.60σ · **2.6σ** | 0.70σ · **3.4σ** |
| Brier skill vs climatology | **+13.6%** | +4.9% |
| beats base rate on log-loss | **yes** | no |
| confident calls (P≥.65): predicted → actual | **72% → 71%** | 74% → 60% |

Three reads:

1. **The model is well-calibrated — 2022 was the outlier, not a flaw.** This is the correction. In 2018 the model's confident calls were essentially perfect — it said 72%, they came in at 71% — and it beat a base-rate constant on every metric. The 2022 "overconfidence" (74% → 60%) and its lone log-loss miss were an **upset-heavy tournament**, not a property of the model. Looking at 2022 alone, I'd wrongly concluded the model fails where it's most confident; 2018 shows it doesn't. The yardstick is sound.

2. **The biggest residual is *always* a favourite getting stunned.** Both years' top misses are exactly that — Germany losing to Korea & Mexico in 2018; Saudi/Argentina, Cameroon/Brazil, Tunisia/France in 2022. The *mechanism* varies (2018's Germany–Korea was a must-win collapse; 2022's Cameroon–Brazil was a rotated dead rubber), but the **pattern is the law** — and it's the empirical backbone of the favourite-fade thesis (#19, #21).

3. **The sigma discipline holds across both — now on 128 matches.** The biggest residual in either tournament is **2.6–3.4σ**, medians ~0.65σ. No "12σ" anywhere, two World Cups running — the anti-hyperbole stance (#21) is now backed by more than a single sample.

**The trader's read.** This is the empirical twin of the pre-registration, and a small lesson in why you run the second test: *the same framework, on 2018 and 2022, did this* — confirmed the sigma claim, showed the model is genuinely calibrated (2018), and identified the one universal residual (favourites stunned), while correcting the overconfidence read that one chaotic tournament had suggested. The honest caveat: both were **32-team** events, so this validates the **per-match expectation / residual / calibration** layer (format-agnostic), **not** the 48-team bracket simulation — that can't be backtested on a different format. The yardstick is sound and self-aware; the bracket rests on its construction and its agreement with the 2026 market. (`scripts/backtest_wc.py`, no-lookahead, both years, reusable.)

## 25. The first 4-timezone World Cup: the jet-lag everyone's worried about mostly washes out

2026 is the first World Cup played across multiple time zones (Pacific −7 to Eastern −4, a **3-hour span**), and the obvious story is jet lag deciding games. The travel **burden** is real and brutally unequal — Bosnia fly **5,061 km** in the group stage, Egypt **372** (Seattle–Vancouver–Seattle, one time zone, never leaves the Pacific). But the performance **effect** is a different question, and three things kill it:

1. **The recovery math zeroes it out.** Model the residual penalty the way the science does — `max(0, |zones| − resync_rate·rest_days)`, with re-sync ~1.0 zone/day westward and ~0.67/day eastward (east is the hard direction, because the body clock's free-running period is >24h). With 4–6 day group-stage gaps and a max 3-zone spread, **the residual is 0 across all 96 group-stage travel legs.** Even a worst-case knockout hop — 3 zones east on 3 days' rest — leaves ~1 residual zone ≈ 4 Elo ≈ **0.6% win probability**, and it's rare.

2. **Football's cleanest study finds nothing.** A randomization-inference paper built precisely to handle the confounding ("Jet Lag Does Not Impact Football Performance," 2023) concludes the effect is **not reliably detectable** in football. The cross-sport evidence is thin too: the best-quantified result (NBA, *Frontiers* 2022) is home-teams-traveling-east only, p≈0.05 — one marginal cell. Folklore wildly overstates it.

3. **It can't be fit from our data anyway.** A few-% effect against international football's variance, confounded with home/away, opponent quality, and competition tier — so it would have to be an imported literature prior, not a fitted edge.

**The trader's read.** This joins **altitude (#7)** and the **"12σ" shocks (#21)** as a folk-wisdom prior that doesn't survive rigor: the headline-friendly thing isn't where the signal is. So I **did not** add a jet-lag term to the model — modelled honestly with recovery it's ~0 for 2026, and manufacturing an effect football's own cleanest study denies would be the opposite of the discipline. The deliverable is the *descriptive* burden (a clean, novel, validatable fact — the schedule is the schedule) plus the myth-bust: **the travel is real, the jet-lag edge isn't.** (`scripts/build_travel.py`, timezone + residual-zone analysis.)

---

## 26. The goals-and-draws paradox: 2026 is scoring like no modern World Cup while drawing like a defensive one

Through the first **33 group games**, 2026 is running **3.09 goals/game** — the highest scoring rate of the modern era (1970–2022) — *and* a **~30% draw rate**, which sits in the top tier historically. Plotted on the goals-vs-draws map, no modern World Cup has occupied this corner: high scoring and high draws usually trade off, and 2026 is doing both at once. (`draws_paradox`.)

**The trader's read.** This is **descriptive/structural only — not a "broken law."** The historical goals-vs-draws relationship is real but *weak* (r ≈ −0.35), so a single tournament landing off-trend is well within what a weak correlation allows, and both rates typically ease in the knockouts (tighter, more cautious football, plus extra time/penalties changing the draw math). So the honest framing is a striking *snapshot* of an unusual tournament, not a claim that the underlying tendency has changed. For a market-maker the so-what is modest but real: if you priced totals and draw lines off a prior that assumes the usual goals/draws trade-off, the early 2026 sample is a reminder that this field is generating both — though with only 33 games and a knockout reversion ahead, it's a watch item, not a re-pricing mandate. The tournament is simply doing something rare, in plain view.

## 27. The 48-team group stage didn't kill the jeopardy — it moved it to goal difference

A live critique of the expanded format is that the group stage has "no jeopardy" — too many teams advance, nothing's at stake. The conditioned tournament Monte Carlo (40k sims) is the data rebuttal: the **last third-placed team that advances and the first team that misses out finish level on points 72% of the time**, and the qualification cut lands on **exactly 3 points (one win) 87% of the time**. So the final Round-of-32 ticket is overwhelmingly decided by **goal difference, not points**. (`jeopardy_gd`.)

**The trader's read.** The jeopardy didn't disappear, it relocated — from "win or go home" to "every goal margin is a tiebreak input." That sharpens the read on #8 and #9: with the cut-line pinned at one win and ties broken on GD, a late goal in a settled-looking blowout still moves the advancement field, because it moves a team's GD relative to the bubble pack across other groups. For anyone trading advancement (not outright), it means the relevant live variable in dead-rubber-looking games is the **scoreline**, not just the result — the six-pointers (#9) decide who's level on points, and goal difference decides who survives being level. The format is doing its job; the stakes just live one tiebreak deeper than the points table shows.

## 28. The in-play market under-reacts to goals by about 5pp

An independent in-play win-probability model — independent-Poisson on remaining goals, calibrated to each game's **pre-match** probabilities — run against the live order-book tape shows the market **under-reacts to goals by ~5pp**: immediately after a goal, the traded price moves less than the model's recomputed fair value implies, then drifts the rest of the way. (`livewp_underreaction` / `live_match`.)

**The trader's read.** This is the live, real-surprise counterpart to the dry-run in #23 (where a heavy favourite extending a lead was *non*-news and nothing moved). A ~5pp under-reaction to genuine goal information is the in-play repricing edge the pipeline was built to catch — small, but directionally the documented under-reaction-to-news pattern, observed on this tournament's tape rather than imported. Caveats stay loud: it's an early, modest-sample read, the magnitude is sensitive to exactly when you mark "post-goal," and it's the *descriptive* sibling of the pre-registered goal-reaction test (P10), graded Jul 19 — not yet a pre-committed result. Treated carefully, it says the market does fully price the goal, just not instantly, and the lag is where a fast in-play book lives.

## 29. Cross-venue price discovery, matured: Polymarket leads, and it survives the trade-classification problem

The flagship is now mature across **72 captured matches**. Two layers agree. (1) **Lead–lag:** an event study over **308 decisive events** finds Polymarket moves first **226 vs Kalshi 82 = 73% of the time** (67% counting the 30 synchronous same-second ties), and — hardened against the clustering of events within matches (`scripts/harden_leadlag_stats.py`) — **48 of 56 matches lean Polymarket** (sign-test p≈5×10⁻⁸; cluster-robust CI [68%, 79%], design effect just 1.21), at a **median +400ms**. (2) **Information share, done rigorously:** a VECM with an ADF cointegration gate, decomposed via **Hasbrouck (1995)** information share and the **Gonzalo–Granger (1995)** permanent-component share, computed on order-book **mids**, puts **Polymarket's Gonzalo–Granger share near 79%** across **51 cointegrated matches / 83 contracts** — a per-match median, with individual matches scattering widely (between-match SD ~20%; the honest unit is the match, not the contract or the bin) — leading in **50 of 51** (sign-test p≈5×10⁻¹⁴). Within-venue mechanism: **order-flow imbalance → price impact** (Cont–Kukanov–Stoikov 2014, book-derived; strongly significant within-venue, both venues — bin-level t overstates significance, judged across matches). A 4-page desk research note is at `writeups/price_discovery_note.pdf`. (`leadlag`, `infoshare`, `ofi`.)

**The trader's read.** This is the payoff of the price-discovery question #3 set up before kickoff — and the methodological point is the contribution. Because the information share is computed on **mids, not signed trades**, it sidesteps the **~59% trade-direction-classification accuracy** problem that is the open question in the 2026 Polymarket paper (arXiv 2604.24366): you don't have to guess who initiated a trade to know where the permanent price component is formed. The convergent answer — lead–lag and information share both naming Polymarket the price leader, robust across 72 matches and 50 of 51 cointegrated ones — is exactly what #1's depth finding predicted: size goes where the discovery happens. For a maker, the so-what is concrete: on World Cup goal news, Polymarket is the reference price and Kalshi the follower. But the lead, while real, is **un-harvestable after the cost of immediacy**: across 277 goals the gross stale-quote gap is **~12.0¢** and the cost ~1.3¢, leaving **+10.8¢ net on paper** — yet depth at the goal collapses to **~0.5% of normal**, so **0% is actually harvestable**. This refines the "economically meaningful arbitrage" claim of Ng, Peng, Tao & Zhou (2026, SSRN 5331995): the price lead is genuine, but you cannot trade it at size. The markets are working; this just measures *which one works first* — and that you can't get paid for knowing.

## 29b. Two extensions: macro calibration, and an honestly-killed ML slice

Two July extensions that show the toolchain travels — and the discipline to not over-claim. **(1) Macro (`scripts/macro_calibration.py`).** Cross-venue price discovery isn't available on macro (Polymarket doesn't run CPI/Fed/GDP — Kalshi is *the* macro venue), so the right question is the signal-source one: are these markets calibrated? They are — Kalshi's CPI/Fed/GDP contracts are well-calibrated forecasters that sharpen toward the release (Brier skill vs base-rate ~93% at 3 days out → ~84% at 30 days), on a thin ~5–7-release sample. The same "the market is a great forecaster, measure *how* good" headline as the flagship, on the contracts that matter institutionally. **(2) ML microstructure (`scripts/ml_microstructure.py`), a cautionary tale.** A gradient-boosted next-1s mid-return model on the order-book tapes first looked strong (56.3% out-of-sample directional, beats the linear OFI baseline). Then the validation killed it: a permutation-null is clean (no leakage), but the eye-catching *raw* 70% direction is mostly trivial price drift, and **leave-one-match-out on the de-drifted signal is ~52% (one match 33%, only 4/6 > 50%)** — fragile, not an edge, at a six-match sample. Reported as such. Book state carries *some* nonlinear information (imbalance dominant), but beyond drift it's weak and unproven — and, like the flagship lead, wouldn't survive spread + latency anyway.

## 30. The favourites stumbled — and the title market re-sorted instead of panicking

The group stage handed the contenders genuine jolts: **Spain held 0–0 by Cape Verde, Portugal 1–1 with DR Congo.** The title market's response was orderly — the top contenders moved only about **±3pp**, and the move was a **re-sort among the contenders**, not a repricing of the whole field. (`chaos_mirage`.)

**The trader's read.** This is the flat-field finding (#11) doing its job under live stress. In a field where the top sits at ~16% with the top four ~49% combined, a favourite dropping points is *information about ordering*, not about whether a title is suddenly up for grabs — so probability shifts *between* near-equal contenders rather than draining out of the top. The ~±3pp move is the market absorbing a surprise with the composure a deep, liquid outright market should have: the tournament delivered the shock (its job), and the price did the bookkeeping (its job). No panic to fade, no overreaction to capture — just a sharp market re-weighting a parity field, which is what #11 said this structure would produce.

## 31. RETRACTED — the mismatch-draw underpricing read did not survive out of sample

**Retraction, recorded honestly.** An earlier *tentative* read held that the market under-prices **mismatch draws** (a heavy favourite held when the underdog parks the bus). It **regressed out of sample**: by **June 18, 2026** the hit rate was **6/17 = 35%**, **not significant versus the model**, and **Canada 6–0 Qatar** was a clean counterexample of a mismatch resolving exactly as priced. The earlier **"5/10, p = 0.013"** figure is **stale — do not cite it.** (`mismatch_draws`.)

**The trader's read.** This is the discipline the whole log is supposed to enforce: a promising small-sample signal, tested as the sample grew, and reported as failed rather than quietly dropped or re-anchored on its best early number. The market was pricing those mismatches about right; the apparent edge was small-sample noise that the tournament unwound. Kept on the board, with its history, precisely *because* a finding that can't be wrong isn't a finding — and this one turned out to be wrong, which is worth more on the record than buried. The pre-registered tests (PREREGISTRATION.md) remain the binding scorecard; this descriptive read is now closed as a null.

## 32. The most valuable goal is the one nobody's watching: advancement is decided by points, with goal difference only as the tiebreak

*(Supersedes the earlier `garbage_time` card, whose tweet was retracted on June 22 — its "+28pp / +35pp" figure was a points-confounded conditional that conflated "more points" with "better GD." The rigorous version below conditions on points first.)*

Crossing the goal-difference jeopardy of #27 with the match-leverage idea of #9 turns up a sharp, counterintuitive number once the **points confound is removed**. In the 40k conditioned sims, advancement is decided by **points**, with goal difference only the tiebreak: a third-placed team that is **ahead on points advances 100% of the time, level on points 73%, and behind on points 0%** — and it lands **level on points 39%** of the time, where GD actually bites. Conditioned at that bubble (level on points), a single goal is worth **+12 percentage points of advancement — the causal effect**, not the confounded +35pp the old conditional implied. (`points_first`.)

**The trader's read.** Because the cut is a points decision with a GD tiebreak (#27), the highest-leverage *action* in the group stage isn't winning a marquee match — it's the goal margin in games whose *result* is already settled but whose team sits level on points with the bubble pack. A bubble team level on points and 3–0 up should keep scoring, because that fourth goal swings its qualification at the tiebreak. For an advancement trader the so-what is concrete: in dead-rubber-looking blowouts involving a bubble team, the live variable is the *scoreline running up*, not the result — but only when points are level, which happens about 39% of the time. Caveat: it's the model's conditional curve (large n, but one model on one field), and the goal-difference leverage exists *only* at the level-on-points hinge — ahead on points a goal is worthless, behind on points nearly so.

## 33. The patriotic premium: the US exchange pays up for the hosts, and the price leader proves it's sentiment

Crossing the cross-venue basis (the home-crowd tilt in the Kalshi–Polymarket gap) with the price-discovery result of #29 produces a clean, explainable bias. Benchmarked against the Betfair sharp line across 48 teams, **Kalshi (US-regulated) prices the USA +2.36pp above the sharp line versus +0.53pp on Polymarket** — a **+1.83pp** home premium — and across the three North American hosts Kalshi runs **+0.82pp richer than Polymarket** against a ~0.00pp all-field baseline. The tilt reverses for the global giants: Polymarket pays up for Argentina, Spain, and Germany. (`patriotic_premium`.)

**The trader's read.** What lifts this above a basis curiosity is the cross with #29: the venue that *leads* price discovery (Polymarket) and the sharp line both disagree with Kalshi's host pricing, so the gap reads as **sentiment, not information** — US traders pay a patriotic premium for US teams on the US book. It's a directionally tradeable lean (treat the Polymarket/sharp number as fair, fade the host premium on Kalshi), though magnitudes are small (~1–2pp) and inside realistic costs for everyone but the USA. The clean, benchmarked version is the contribution: a measurable national-sentiment bias with a built-in proof of which side is mispriced.

## 34. Where the model argued with the market, the market won

Crossing the squad-value blend diagnosis (the model's known lean toward star-laden squads) with the live group-stage results gives the cleanest validation yet of the model-vs-market story. Across the nine strongest teams, the model's lean versus the market (blend minus market title odds) correlates **−0.82** with each team's live points-versus-expectation: **every team the model rated above the market is underperforming** (Spain, leaned +3.2pp, is −1.85 points; Portugal +1.0pp, −1.40) **and every team it rated below is overperforming** (France, USA, Argentina). (`model_blindspot`.)

**The trader's read.** This is the squad-value blind spot (the model trusts talent; the market trusts form) caught in real time, and it lands pro-market: where the transparent fundamental model and the price disagreed, the price was the better forecast — its caution on the teams the model liked and its faith in the ones it doubted both paid off. The caveat is loud: **n = 9, one group stage, descriptive** — a −0.82 on nine points is suggestive, not inferential, and it will regress. But the direction is exactly what the blend diagnosis predicted, and it's a useful reminder that the model's residual *against* the market is itself a signal about the model, not the market.

**Also tested, didn't land (recorded honestly).** Two further crosses were run and came back null: the favourite–longshot bias is **not** explained by on-chain whale concentration (premium-vs-concentration correlation ≈ 0, n = 4), and "the favourite's price is set by trading everyone else" — longshots turn over **~13× harder per unit of probability** than favourites — is real but mostly restates the money-map finding rather than adding a new one. Neither was built into a card.

## 35. The market's probability staircase never breaks: the nested ladder is arbitrage-free

Every team carries a full nested ladder of contracts in the snapshot cross-section — P(advance to R32) ≥ P(reach R16) ≥ P(reach QF) ≥ P(reach SF) ≥ P(reach final) ≥ P(win). Coherence requires the probability to fall monotonically down that ladder (you cannot reach the final without reaching the semi). Scanning **282 adjacent-rung comparisons across 106 team-venue ladders, there are zero violations** beyond a one-cent tolerance: the market never prices a team likelier to win the cup than to reach the final.

**The trader's read.** A clean, quiet pro-market result: the nested World Cup markets are internally arbitrage-free, so there is no free lunch in any rung pair (buy "reach the final," sell "win it"). It is the cross-market analogue of #29's cross-venue efficiency — within a venue, across the round ladder, the prices are mutually consistent to the tick. For a desk it sets the baseline: any apparent edge in these markets is a *level* disagreement with your model, not a structural arbitrage the book left open. The market does its bookkeeping.

## 36. The cost of a bet isn't fixed: the obscure markets cost 20× the title

From 57k order-book snapshots, the **median quoted spread scales with attention.** The headline **title market trades at 0.1c**; the single-match, advance, group-winner and reach-round markets at **~1.0c**; and the obscure derived markets — **finish-third and stage-of-elimination — at 2.0c, twenty times the title's spread.** The house margin tracks the same gradient: the title overround runs **~2% on Polymarket versus ~5–9% on Kalshi** (roughly 3×), and Kalshi's widened to **9.5% on kickoff day**, when uncertainty and volume peaked. (`liquidity_tax`.)

**The trader's read.** Liquidity, sharp pricing and crowd attention all pool in the markets everyone watches, so the title is priced to the tick and the derived markets carry a real spread tax. This makes the Probability-Cup thesis concrete: if a harvestable edge exists anywhere it is in the expensive, thin corners (elimination stage, third place), not the razor-tight headline market — but the same spread that lets a mispricing survive is the cost of trading it, so the bar there is the ~2c round-trip, not the title's 0.1c. The margin term-structure adds the timing read: the house widens at peak uncertainty (kickoff), exactly when a taker most wants in.

## 37. Which title hopes are the most contested: a belief-volatility ranking

Over the buildup, **Argentina (±1.46pp), Spain (±1.35pp) and Portugal (±1.32pp)** carried the most volatile Polymarket title prices, with Portugal swinging across a **5.3pp range** on a ~7% base. The favourites' beliefs moved most; the mid-table and longshots barely twitched.

**The trader's read.** Belief volatility is a cleaner "what's actually in play" signal than the level: a price that moves is one the market keeps re-evaluating as information lands, and here it concentrates in the contenders whose ordering is genuinely unsettled (#11's flat field doing its thing — probability sloshes *between* near-equal favourites rather than draining out of the top). For content it is the velocity engine; for a maker it flags where realized vol, and therefore the value of being fast (#29), is highest. Caveat: it is buildup-window vol on one venue, and a team resolving toward 0 or 1 as it clinches reads as "volatile" for mechanical reasons — so it is a contested-ness proxy, not a tradeable signal on its own.

**Also tested, didn't build (recorded honestly).** Four further snapshot extractions were run and set aside: cross-market price discovery (does a team's advance price move before its title price on a goal?) is **infeasible at the ~30-min snapshot cadence** — it needs tick data the tapes carry only for the match contract, not the title ladder; the cross-venue *advance*-market basis is **contaminated by settlement lag** (one venue marks a clinched team to 100% before the other) and clean only at a small ~2–3pp level; the Kalshi "third-place" market does **not** map to the model's P(finish 3rd) (it prices ~0% where the model says up to 87% — a market-definition mismatch, not a disagreement); and mid-tournament calibration was underpowered at n = 33. **Group-stage update (n = 72, Jun 28):** the full read is now in — across all 72 group games the **market is the best-calibrated forecaster (23% Brier skill, reliability slope 1.07 ≈ perfect) and beats the pre-committed model** (v1 21%, slope 0.87); v3's higher raw skill is overfit on a smaller sample. This is the P1 deliverable's group-stage read (surfaced on method.html); the binding final grade still lands July 19.

---

### The anatomy of a goal (tape-based microstructure, #38–#40)

Three measurements on the captured order-book tapes (~20 matches), all sign-free (mids + book changes, robust to the ~59% trade-direction problem), that together describe what happens to both venues in the seconds around a goal — and complete the price-discovery flagship (#29).

## 38. The order book vanishes at a goal — and the price leader withdraws hardest

Around each detected goal shock (~370 across ~20 matches), the top of book collapses. On **Polymarket the spread blows out ~8× and best-price depth falls to under 1% of its pre-goal level**; on **Kalshi the spread roughly doubles and depth falls to ~1%**. Both books refill (spread back within 1.5× baseline) in **~3–4 seconds**. The striking cross: the venue that prices the goal *first* (Polymarket, #29) also **withdraws liquidity the hardest**. (`book_vanishes`.)

**The trader's read.** This is informational adverse selection in the open: at a goal, makers face being picked off by anyone who saw the goal, so they pull quotes until the new level is clear. The novelty for prediction markets is the contrast with betting exchanges — Betfair *suspends* the market and cancels resting orders on a goal, so its depth collapse is mechanical; Kalshi and Polymarket **never suspend**, so this withdrawal is genuine information-driven liquidity provision, not a halt. The so-what feeds #40: the goal is priced into a book with almost nothing resting in it.

## 39. Price discovery isn't a steady hum — it concentrates at goals

Conditioning the flagship's information share on the news (the same VECM / Gonzalo–Granger estimator, run in ±180s goal windows vs 360s calm windows), Polymarket's share of price discovery is **~86% at goals (136 windows) versus ~53% in calm play (217 windows)** — Hasbrouck tells the same story (~82% vs ~56%). In quiet periods the two venues are roughly coequal; the instant a goal lands, Polymarket does the overwhelming majority of the discovery. (`goal_discovery`.)

**The trader's read.** This sharpens #29's static ~78% into something more useful: the lead is **a news-event phenomenon, not a background constant** — Polymarket leads *because* it incorporates the goal first, and away from goals there is little to lead. For anyone aggregating prediction-market signals, the prescription is conditional: weight Polymarket's mid as the leading indicator *especially on the goals*, where the gap is widest. Caveat: it is windowed VECM on ~20 matches, a couple of low-liquidity matches (Brazil–Haiti, Ecuador) invert in the noise, and this reports conditional IS/GG rather than the noise-robust Putniņš ILS (the natural refinement). The pooled direction is unambiguous.

## 40. The cross-venue lead is real — and untradeable. The edge is a mirage

The honest capstone, and a caught error worth recording. A first pass at a harvestability ledger said a reactor on the lagging venue could net **+10.2c on 100% of goals** — a too-good-to-be-true result that was a *bug*: it credited the full goal move while ignoring that the quote you'd lift has withdrawn. Gating on available depth gives the real answer: the lagging venue is stale by a gross **~11.4c** for ~**711ms**, **net-positive on paper on 100% of goals after the spread — but the depth at the goal is 0.4% of normal, so 0% is actually harvestable.** (`edge_mirage`.)

**The trader's read.** This is the pro-market punchline of the whole microstructure program, and it lands *because* it nearly went the other way. The cross-venue lead (#29) is genuinely there, and on a naive spread-only calculation it looks like free money on every goal — exactly the kind of "edge" the discipline exists to kill. The thing that kills it isn't the spread; it's the **liquidity withdrawal (#38)**: by the time the lead is observable, the resting quote that would carry the edge is gone. So "the news is in the price before you can trade it" (Croxson-Reade 2014) holds here for a specific, measured reason — not slow pricing, but a book that empties in the same instant it reprices. The lead is a property of *price discovery*, not a tradable opportunity. The honest version, recorded with its correction, is worth more than the headline it replaced.

---

## Thread drafts (the public voice)

**Thread A, depth (microstructure):**
> Same World Cup, same ~0.1¢ spread, but Polymarket is quoting ~27× the depth Kalshi
> is on the title race. A quick look at what "liquidity" actually means on a
> prediction market, and why same-spread ≠ same-market. 🧵

**Thread B, order-book imbalance:**
> Pulled the order books for every 2026 World Cup title contract. Every single
> favorite is *sell-heavy*: ~80% of resting size is on the offer. Here's what that
> says about who's holding favorites and why. 🧵

**Thread C, cross-venue:**
> Kalshi and Polymarket price the World Cup winner within ~0.15pp of each other. The
> law of one price, holding in real time across two independent venues. The one
> contract they disagree on most? England. 🧵

**Thread D, the gap is vig, not disagreement:**
> The "Kalshi vs Polymarket World Cup gap" is real, but strip each venue's margin and
> the two crowds agree on every title price to ~0.15pp. The durable difference is *cost*
> (Kalshi's vig ~1.8× Polymarket's). What little belief-gap is left? A home-crowd tilt:
> the US book pays up for USA & Mexico, the global book for England, Portugal, Japan. 🧵

**Thread E, the bug was ours, not the market's:**
> I thought I'd found World Cup market mispricings: Canada, Mexico, Japan all looked
> cheap to advance. Then I checked against an independent bookmaker — and it sided with
> the market every time. The culprit wasn't the market. It was my Elo. A thread on why
> ratings quietly *inflate* weak confederations, and the empirical-Bayes fix. 🧵

*(Tone: curious, pro-market, specific, humble on sample size. Lead with the number,
explain the mechanism, link the repo. No "markets are wrong" framing; these are
markets working, observed closely.)*
