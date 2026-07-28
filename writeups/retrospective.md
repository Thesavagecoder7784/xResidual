# The 2026 World Cup, in residuals

**Post-tournament retrospective.** Prabhat M. ([repo](https://github.com/Thesavagecoder7784/xResidual) · [portfolio](https://thesavagecoder7784.github.io/))

> Written after the final, 2026-07-19. Every number here comes from an artifact committed in this
> repo, most of them frozen before the matches they describe. Where a claim rests on a small sample
> I say so and give the n.

A residual is what's left when you subtract expectation from reality. For thirty-nine days I ran two
expectations side by side — my own Elo-and-Skellam model, pre-committed match by match to an
append-only ledger, and the live prices of two real-money prediction markets — and let the World Cup
supply the reality. This is what the leftovers say.

The short version: **the tournament's chalk held at the top, my model's errors were almost entirely
draws, and the market had already priced most of what surprised me.** The most interesting finding
of the whole project isn't a prediction at all. It's a measurement of how quickly one venue prices a
goal before the other, and how completely that head start fails to be worth money.

---

## 1. The chalk held, and that is not a victory lap

Before a ball was kicked I logged a champion distribution. Its top four, in order:

| rank | team | my model | market |
|---|---|---|---|
| 1 | Spain | 16.5% | 17.0% |
| 2 | France | 14.2% | 16.1% |
| 3 | England | 11.6% | 10.8% |
| 4 | Argentina | 9.7% | 8.9% |

The actual final four were Spain, France, England and Argentina. Spain won it.

That looks like a hit, and in the narrow sense it is a timestamped one — the ledger cannot be edited
after the fact. But I want to be precise about what it is worth, because this is exactly the kind of
result that invites over-reading:

- **The market said the same thing.** Its top four were the same four teams. There is no model edge
  being demonstrated here; there is a favourite set that both forecasters agreed on, and it held.
- **It is one draw from a distribution.** Four semi-finalists from a 48-team field is a single
  sample. If the model is well-calibrated, an outcome this chalky should happen sometimes, and
  chalk holding is not evidence the numbers were right — only that they were not embarrassed.
- **The interesting part is underneath.** Portugal, Brazil, Germany and the Netherlands — the 5th
  through 8th ranked contenders, carrying 24% of the probability mass between them — all failed to
  reach the semi-finals. The tournament did not skip its favourites. It skipped its *middle class*.

So: the headline is chalk. The information is in the residuals.

## 2. My model's errors were draws, almost all of them

Scoring all 72 pre-committed group-stage forecasts by surprisal (the negative log of the probability
I assigned to what actually happened), the eight worst calls of the tournament were:

| match | outcome | my model gave | surprise |
|---|---|---|---|
| Spain 0-0 Cape Verde | draw | 6.8% | 2.69 nats |
| Ecuador 0-0 Curaçao | draw | 9.2% | 2.39 |
| Qatar 1-1 Switzerland | draw | 10.5% | 2.25 |
| Australia 2-0 Turkey | Australia win | 14.3% | 1.94 |
| England 0-0 Ghana | draw | 14.6% | 1.92 |
| Saudi Arabia 1-1 Uruguay | draw | 15.2% | 1.89 |
| Uruguay 2-2 Cape Verde | draw | 16.8% | 1.78 |
| Portugal 1-1 DR Congo | draw | 17.2% | 1.76 |

**Seven of the eight are draws.** Six of those seven are the same shape: a strong side fails to break
down a weaker one that came to defend. Mean surprisal across all 72 games was 0.845 nats.

This is a structural bias, not bad luck. A Poisson-family goal model with a Dixon-Coles low-score
correction still under-produces the specific scoreline where a heavy favourite is held — because the
underdog's defensive posture is a *choice* conditioned on the opponent, and a rating-difference model
has no representation of that choice. Nothing in Elo knows that Cape Verde will park against Spain
and not against Uruguay.

For the record, this is the one place I flirted with an edge and got it wrong. Mid-tournament I
thought mismatch draws were systematically under-priced, on 5 of 10 with p = 0.013. By 18 June it had
regressed to 6 of 17 and I retracted it. It is marked retracted in `FINDINGS.md` rather than deleted,
which is the point of keeping a findings log at all.

## 3. The market already knew

Here is the part that makes the residual framing earn its keep. On the games that surprised *me*
most, was the market surprised too?

No. Across the 39 group games where I have both a frozen forecast and a closing market price, on my
eight worst calls the market priced the realised outcome **+2.7pp higher than I did, on average.**
And on realised draws generally:

- my model, average probability assigned to draws that actually happened: **21.1%**
- the market, same games: **25.8%** (n = 13 realised draws)

The market was carrying about five extra points of draw risk, and it was right to. That gap is the
whole thesis of this project in one number: where my model and a liquid price disagree, the prior
should be that the model is wrong, and here it was.

The formal version of this is the pre-registered calibration test (P1), graded on all 72 group games:
the de-vigged market scored a **Brier of 0.4868** against my pre-committed model's **0.5033**, with a
reliability slope of 1.07 against my 0.87. My slope below 1 is the favourite-longshot signature —
backing favourites a shade too hard, which is the same bias the draw failures express.

One honesty note I insisted on in the paper and will repeat here: that Brier difference is **not
statistically significant** on 72 games. The correct claim is that the market is at least as sharp as
a carefully-built independent model, not that it beat it. A single tournament cannot resolve a gap
that small.

## 4. What the 48-team format actually did

Two format-native reads survived the tournament.

**Goals and draws rose together.** The group stage finished at **2.99 goals per game with 27.8% of
matches drawn**. That figure is convention-free, since no group game goes to extra time. Across all
104 matches you have to say which convention you mean, because five knockout ties were level at 90
minutes and decided later: **2.96 goals per game and 23.1% drawn counting extra time** (the usual
basis for comparing World Cups), or 2.88 and 27.9% on regulation-time scores alone. I flag this
because the gap is nearly five points on the draw rate, and a retrospective that quietly picked the
flattering convention would not be worth much. That combination is the unusual part —
scoring rates and draw rates normally move against each other, and here both sat high. An early read
through 33 games had it at 3.09 goals per game, which is the figure the frozen group-stage card
carries; the tournament finished cooler than it started, and I would not now call it the highest-
scoring modern World Cup without qualifying which slice you mean.

**Jeopardy migrated to goal difference.** With eight of twelve third-placed teams advancing, the last
team into the Round of 32 and the first one out finish **level on points 72% of the time** in
simulation. The format did not remove the drama; it moved it from the league table to the tiebreaker,
which is a worse place for it to live, because goal difference rewards running up the score in a game
whose result is already settled. It also manufactured dead rubbers among the giants: 18 of the
biggest teams had clinched before their final group game.

## 5. The finding I would actually defend: a real lead nobody can trade

The model was the yardstick. The microstructure work is the contribution.

Across **86 matches** captured tick-by-tick on both venues, Polymarket reprices a goal before Kalshi
**72% of the time** (281 of 392 decisive events), at a **median 600 ms**. Hardened against the fact
that events cluster inside matches, **57 of 66 matches lean Polymarket** (sign test p ≈ 1.2×10⁻⁹).
The formal decomposition agrees: a **Gonzalo-Granger information share of 81.0%**, leading **61 of 63**
cointegrated matches. And it concentrates exactly where it should — about **86% of price discovery
inside goal windows versus 53% in calm play.** The lead is a news-event phenomenon, not a background
hum.

Then the part I care about most. A real 600 ms head start on a repeated, exogenous shock sounds like
free money, and on a spread-only calculation it prices like it: across **405 goals in 66 matches** the
lagging venue is stale by a median **12.0 cents**, netting **+10.8 cents on paper** after costs, on
100% of goals.

It is not free money, because **at the instant of the goal the book is gone** — spread roughly 8×
wider, best-price depth under 1% of normal. Gate the ledger on what is actually resting and **the
median match yields no harvestable goal at all.** Harvestable goals exist (~11% goal-weighted on the
21-match subset still reconstructible from the archive, clustered in 6 of those 21) but they are a
minority you cannot identify in advance, because the depth vanishes in the same instant the signal
fires.

That collapse is a market maker pulling quotes against flow it correctly suspects is informed. It is
adverse selection, observed live, at millisecond resolution, on an event whose timing nobody
controls. The lead is real *and* un-harvestable, and those two facts have the same cause.

I nearly published the opposite. My first harvest ledger said +10.2 cents on 100% of goals and I
believed it for about a day. It was a bug: it credited the full move while ignoring that the quote
being lifted had withdrawn. Finding an edge and then correctly measuring how little of it survives
contact with the book is the actual skill being demonstrated here.

## 6. The scorecard, including the parts I lost

Eleven predictions, locked before kickoff with their grading rules, graded in public on 19 July:
**6 pass, 2 fail, 3 inconclusive.** The two failures are the ones worth stating plainly.

**P3, law of one price, FAILED.** I predicted the raw cross-venue title gap would average ≤ 1pp. It
averaged **3.98pp**. I was wrong about the level — but the reason is instructive rather than
embarrassing: de-vigged, the two venues agree to **0.15pp**. The gap is house margin, not
disagreement. Price-level parity fails while belief-level parity holds.

**P10, goal overreaction, FAILED.** I predicted the documented "fade the overreaction after a
surprising goal" edge would show positive paper P&L. It came in at **−0.285pp mean, −0.821pp on the
surprising-goal subset.** The edge is arbed away on these venues. This was pre-registered as a
publishable result either way, and the negative is more useful than the positive would have been.

Three came back inconclusive for reasons I could not fix by trying harder. P2 because prediction
markets quote two-way and simply do not price the draw, so there is no like-for-like favourite-
longshot comparison. P8 because my sigma metric assumed a continuously-priced series, and prediction
market mids are step functions — about 98% flat at one-second resolution — so the denominator
collapses into the noise floor and the z-score stops meaning anything. That is a design error in the
pre-registration, and the honest grade is inconclusive rather than a number I would have to disown.

## 7. The paper book: one lane worked

I ran a paper-trading book all tournament, 46 positions, all settled: **+$148.10 on $1,452 staked.**
The aggregate hides everything interesting.

| lane | n | net |
|---|---|---|
| advance-to-knockouts / reach-R16 | 22 | **+156.2** |
| reach-QF / SF / final | 9 | **+112.8** |
| stage-of-elimination | 2 | +12.0 |
| match draw/tie | 3 | −0.5 |
| never-won-the-cup | 1 | −15.2 |
| both-teams-to-score / totals | 5 | **−44.8** |
| group winner | 4 | **−72.4** |

The advance-market favourite-longshot lane made **+$269**. The two lanes where I had no modelled
edge — group winner and BTTS — gave back **−$117**. Traded on its own, the advancement lane would
have returned roughly twice the book. The lesson is not "I found an edge"; it is that I could tell
afterwards which of my bets were edge and which were noise, and the noise was a third of the book.

One caveat I will not bury: the deeper reach-round lane is concentrated. A single position (Belgium
to reach the quarter-finals, entered at 0.275, resolved at 1.0) is +$79 of that +$113. Remove it and
the lane is roughly flat. Only the group-to-R32 advance lane is diversified enough to call robust.

## 8. What I would do differently

- **Model the underdog's choice, not just the rating gap.** Every one of my worst calls was a
  favourite held by a side that chose to defend. That is a modelling gap with a known shape, and it
  is the first thing I would build next.
- **Pre-register metrics against the data-generating process you will actually have.** P8 died
  because I wrote a volatility test for a continuous price series and then pointed it at a step
  function. The rule failed before the tournament started; I just could not see it yet.
- **Capture more than the marquee matches.** 86 of 104 is good coverage, but captures were
  prioritised toward high-liquidity games — which is precisely the variable the harvestability
  result turns on. The direction of that bias favours finding harvestable edges, and I still found
  almost none, so the conclusion is if anything conservative. But a random capture schedule would
  have been cleaner.
- **Treat the archive as primary from day one.** The raw tapes are transient by design and the
  collection VM is now decommissioned. Roughly two-thirds of the per-game harvest archives did not
  survive, which is why the goal-weighted harvestability rate is pinned to a 21-match subset forever.
  That is a permanent, self-inflicted limit on my own dataset.

## 9. What the residuals actually said

The market is very hard to beat, and I did not beat it. On the games that surprised me, it was less
surprised. On calibration it was at least as sharp. On the one structural bias I found in myself —
draws in mismatches — it was already carrying the risk I was missing.

What it could not do was hide its own mechanics. The most durable thing here is not a forecast; it is
that on a repeated, precisely-timed, genuinely exogenous shock, you can watch one venue lead the other
by 600 milliseconds, watch the liquidity disappear in exactly that window, and demonstrate with a
depth-gated ledger that the two facts are the same fact. A lead you cannot trade is not a failure to
find alpha. It is a measurement of why the alpha isn't there — which is the more useful thing to
know, and the harder one to be honest about.

---

*Every claim above is reproducible from this repository. `python scripts/grade_prereg.py` prints the
scorecard from committed artifacts; `python scripts/emit_macros.py --check` verifies that every number
in the paper still matches the JSON it came from. The pre-registration is a git commit that predates
kickoff. Raw venue tapes are not redistributed — see `REPRODUCING.md` for what ships and why.*
