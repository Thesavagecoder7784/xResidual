# Findings: a trader's read of the 2026 World Cup markets

A living log. Each entry states what the data shows, then *what it would mean to someone trading or making markets on it*. The point isn't the chart, it's the decision the chart implies. Methodology in [METHODOLOGY.md](METHODOLOGY.md); numbers regenerate from `scripts/run_analysis.py`.

Pre-tournament snapshot (data accumulating since June 5, 2026). Claims sharpen as the sample grows; small-sample reads are flagged.

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
runs ~5.0% vs Polymarket's ~2.6% (~2×), so the durable venue difference is *cost,
not price*. The small belief-gap that does survive is structured by audience: the
American book (Kalshi) is richer on USA, Mexico, Netherlands; the global book
(Polymarket) is richer on England, Portugal, Japan, Brazil. Anchored against the
Betfair Exchange (the sharpest soccer market I log), Polymarket sits marginally
closer to the sharp line (mean abs error ~0.13pp vs ~0.16pp).

**The trader's read.** Decompose a cross-venue quote into *belief + margin* and almost
all of the visible gap is margin, so the relative-value trade isn't "buy here, sell
there" on price, it's recognising that the same exposure costs ~2× the vig on one venue.
The residual belief gap is the interesting microstructure: it lines up with who's in the
room. A primarily-American book pays up for its home region (USA, Mexico) while a global,
soccer-literate book pays up for traditional powers (England, Portugal) and football-mad
markets (Japan, Brazil). That's a *home-crowd tilt*, exactly the kind of structural
signal a venue-aware maker would skew around, and the Betfair anchor says the global
crowd is, if anything, the marginally sharper of the two. (Single-snapshot read; the
logged series is what confirms the tilt persists.)

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
> (Kalshi's vig ~2× Polymarket's). What little belief-gap is left? A home-crowd tilt:
> the US book pays up for USA & Mexico, the global book for England, Portugal, Japan. 🧵

*(Tone: curious, pro-market, specific, humble on sample size. Lead with the number,
explain the mechanism, link the repo. No "markets are wrong" framing; these are
markets working, observed closely.)*
