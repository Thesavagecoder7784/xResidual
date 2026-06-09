# Peru vs Spain: the first live in-play capture (2026-06-09)

The xResidual in-play layer (millisecond cross-venue capture, goal-shock detection, the
overreaction backtest) was built and unit-tested before the World Cup, but never run on a
real match with real goals. This is that dress rehearsal: a pre-tournament warm-up
friendly, Peru vs Spain, captured live on Polymarket. The point was not to find an edge on
a meaningless friendly. It was to prove the pipeline works on real goals, and to break it
on something that does not matter rather than on the June 11 opener.

It did both: it validated the capture end to end, and it caught two bugs that would have
crippled the tournament analysis.

## The capture

Polymarket-only (Kalshi does not list friendlies), all three legs (Spain win / draw /
Peru win), under `caffeinate` so the laptop could not sleep through it.

- **94,410 events over ~156 minutes**, about **10 events/second** on average.
- **Median 6 ms between events** during live play. Effectively millisecond resolution.
- Spain's win price was reconstructed from ~34,000 mid updates.

That resolution is far finer than the World Cup's central question needs: a goal reprices
over tens of seconds (see below), so a 6 ms tape with a single local clock can resolve
cross-venue lead-lag to tens of milliseconds. For the in-play layer, capture speed is not
the bottleneck.

## What it caught

Spain opened at 84% to win and finished at 100%. The detector flagged three goal-repricing
clusters, each preceded by a brief adverse dip, consistent with a comfortable Spain win:

- **~11 min:** Spain 84% to 92% to 94% (1-0).
- **~40 min:** Spain 94% to 98% (2-0), after a chaotic moment (below).
- **~81 min:** Spain back to ~100%.

The standout was the **~40 minute VAR/chance moment**, captured tick by tick: Peru spiked
1% to 5% to **25%** then crashed back to 1%, while Spain dropped 94% to 85% then recovered
to 98%. That is the price signature of a real Peru chance or a disallowed goal resolving
toward Spain. A 30-minutes-per-snapshot logger would never see it; the millisecond tape
caught the whole whipsaw.

## What the data showed (goal price-impact)

Beyond *catching* the goals, the tape gives a measured price-impact profile for this market.

| event | Spain win% path | net | what it was |
|---|---|---|---|
| Goal 1 (~11') | 84 -> 76 (dip) -> 94 | +9 pp | a goal, after a pre-goal attack dip |
| Goal 2 (~40') | 94 -> 65 (dip) -> 99 | +6 pp | the chance/VAR moment, then the goal |
| Goal 3 (~81') | 98 -> 92 -> 99 | +1 pp | late, market already near-certain |

Three things stand out:

- **A favourite's goal is worth roughly +6 to +9 pp of win probability, priced in over
  ~30 to 60 seconds.** Not instant. This is the direct reason a 4-second shock window
  missed the goals and a 60-second window catches them.
- **The chance/VAR moment is quantifiable.** At ~40 minutes Spain round-tripped
  **94 -> 65 -> 99%** in a couple of minutes: a ~29 pp overshoot-and-unwind as the market
  reacted to a Peru chance and then corrected. That single event is the most interesting
  microstructure of the match.
- **The repricing was permanent.** Spain climbed 84% to 100% and never gave the goals
  back; the overreaction fade lost on every leg precisely because there was nothing to
  revert. The market incorporated real information efficiently.

This is N=1 and Polymarket-only, so it is a descriptive case study, not a statistical
result. The point is the shape: goals reprice gradually, by single-digit-to-low-double-digit
points for a favourite, and they stick.

## Two bugs caught before the opener

**1. The goal-detection window was 10x too short.** `detect_shocks` defaulted to a 4-second
window. But this market repriced each goal **gradually over ~60 seconds**, so no 4-second
window ever saw the full move. The default detector caught only the sharp adverse blips and
**missed the goals entirely**. Widening the window to 60 seconds caught them cleanly
(+8, +11, +4 pp). Lowering the *jump threshold* would not have helped: at 4 seconds, even a
2 pp threshold only catches noise. The fix is the window, not the threshold, and it is now
propagated to both P10 (overreaction) and P6 (lead-lag).

**2. Stale capture files collided across days.** `load_pairs` and `load_ws_events` globbed
*every* dated file, so tokens and events from an earlier capture leaked into this match's
analysis (one read Spain at 94%, another at 16%, the World-Cup-winner token). Both now scope
to the latest capture day. Without this, the tournament's hands-off analysis would have
silently mixed matches.

Both were found on a friendly. Either one, undiscovered, would have produced wrong or empty
results on June 11.

## The overreaction result: correctly, no edge

P10 fades goal overreaction (enter ~2 min after a shock, exit ~6 min later, betting the
market overshot and reverts). On this match it logged 5 fades, all small losses: Spain
-0.5 pp over 3 trades, Draw -4.0 pp over 2 trades (-4.5 pp total, net of cost). The Peru
leg never threw a qualifying shock-to-fade, so it logged no trades. **That is the right
answer, and it validates the surprise-conditioning rather than the edge.**

The reason is in the surprise scores. Spain's goals carried surprise of only **0.05 to
0.13**: an 84% favourite scoring is exactly what the market expected, so there was nothing
to fade and the price never reverted (Spain just pulled away). The genuinely *surprising*
moves were Peru's transient spikes (surprise **0.94** on the 25%-to-1% whipsaw, **4.10** on
a flicker), but those did not revert either, because they were **real information
resolving** toward Spain, not an overreaction. High surprise is not overreaction unless it
reverts.

So the edge P10 targets, an underdog scoring a goal the market overshoots and then takes
back, did not occur in a one-sided favourite win. The machinery ran end to end and honestly
reported no edge. The real test of the *edge* still needs an upset goal, which the World Cup
will provide.

## What this proves, and what it does not

- **Proven:** capture, millisecond timestamping, mid reconstruction, goal detection (after
  the window fix), the overreaction backtest, and the data hygiene, all end to end on real
  live goals.
- **Not yet proven:** that the overreaction edge exists. This match had no surprising,
  reverting goal. P10 will be tested properly in the tournament.

Pro-market throughout: nothing here says the market was wrong. The friendly priced a
dominant favourite correctly and resolved a contested moment in real time. What the
rehearsal bought was confidence that on June 11 the pipeline will see the goals, time them
to the millisecond, and grade the edge honestly.
