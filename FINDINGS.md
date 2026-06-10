# Findings: a trader's read of the 2026 World Cup markets

A living log. Each entry states what the data shows, then *what it would mean to someone trading or making markets on it*. The point isn't the chart, it's the decision the chart implies. Methodology in [METHODOLOGY.md](METHODOLOGY.md); numbers regenerate from `scripts/run_analysis.py`.

Pre-tournament snapshot (data accumulating since June 5, 2026). Claims sharpen as the sample grows; small-sample reads are flagged.

**On multiplicity.** These are the survivors of a wider exploratory sweep, and the angles that didn't hold are logged as nulls rather than buried — altitude as a goals edge (#7), heat on the pre-match goal line and on cards (#13, #17), the group-winner watch-list "drama" (#14), and the cross-venue convergence paper-trade (#20). Read the numbered list as the reported set, nulls included, not a cherry-picked highlight reel. The binding, pre-committed tests (with significance and power thresholds set before outcomes) live in [PREREGISTRATION.md](PREREGISTRATION.md); the entries here are descriptive reads on pre-tournament data.

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
