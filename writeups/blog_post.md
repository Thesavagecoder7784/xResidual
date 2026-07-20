# Who discovers the price of a goal first? A live tick-level look at Kalshi vs Polymarket

*A public write-up of the flagship result from [xResidual](https://github.com/Thesavagecoder7784/xResidual), a project I ran through the 2026 World Cup. The full 4-page desk note and all the code are in the repo. This is the readable version.*

---

## The question

Two large real-money prediction markets — **Kalshi** (US, regulated) and **Polymarket** (global, on-chain) — priced every 2026 World Cup outcome, continuously, side by side. When a goal goes in, both books reprice within seconds. So here's a question a trading desk actually cares about:

**Which venue discovers the new price first — and if one leads, can you trade the lag?**

I built a 24/7 millisecond capture pipeline for both order books and let it run for the whole tournament. This is what **86 matches** of tick data say.

## Polymarket leads

Measuring "who's first" naively — eyeballing which book ticks — is a trap, because trades are hard to sign (the documented misclassification rate on these venues is ~59%). So I work on **de-vigged order-book mids** and use the standard price-discovery decomposition — Hasbrouck (1995) information share and Gonzalo–Granger (1995) — which lives entirely on quotes and sidesteps the trade-direction problem.

The answer is consistent across two independent estimators:

- **Information share:** Polymarket carries **~79%** of price discovery (per-match median), and leads in **61 of 63** cointegrated matches.
- **Reaction lead:** on a goal, Polymarket reprices first in **57 of 66** matches, a **median ~600 ms** ahead.

It's the deeper book — Polymarket quotes roughly 27× Kalshi's size at the same spread — so this is what you'd expect: **size discovers price.** Not a surprising *direction*. The interesting part is what happens when you ask whether it's tradeable.

### Making it honest

Goal events cluster within matches — they aren't independent — so a naive binomial p-value overstates significance. I hardened it: a **match-resampling cluster bootstrap** (design effect just 1.13, so the clustering is mild here), and the reviewer-proof version is the per-match sign test — **57 of 66 matches** lean Polymarket (p ≈ 5×10⁻⁸), **61 of 63** on the information share (p ≈ 5×10⁻¹⁴). The effect gets *more* significant as matches accumulate, which is what a real effect does and a spurious one doesn't.

## And then it isn't a trade

Here's the part that matters. If Kalshi reprices a goal ~600 ms behind Polymarket, a follower who lifts Kalshi's stale quote the instant Polymarket moves should make money. On paper, they do: a stale-quote ledger over **405 goals** shows a gross gap of ~12¢, ~+10.8¢ net of the spread, on *every* goal. Free money.

Except the quote isn't there.

**At the goal, the book vanishes.** Best-price depth collapses to **~0.5% of normal**, the spread blows out **~8×** on Polymarket / ~2× on Kalshi, and the book takes **3–4 seconds to refill**. There is no resting size to hit at the stale price — by the time depth returns, the quote has caught up. Gated on the depth actually resting in the book, **0% of that +10.8¢ is harvestable.**

That collapse-and-refill is not a glitch. It's the **market-maker pulling quotes against toxic, information-motivated flow** — adverse selection, observed in real time. The apparent edge *is* the cost of immediacy. The lead is genuine, measurable, and **information, not alpha.**

This is the honest, pro-market reading: price discovery here is real and almost none of it is harvestable — and the methods that separate "real" from "harvestable" (de-vig before you call any gap, cross the true bid/ask, read the depth at the event) are the contribution as much as any single number.

## The discipline around it

The result I trust is the one I committed to *before* I could see it. The whole project was **pre-registered** — six falsifiable predictions in a timestamped git commit before kickoff, graded in public with proper scoring rules on **July 19**, hits and misses both. Along the way the process did its job:

- A tentative pre-tournament edge (a draw-pricing effect) **regressed** once more games landed — marked retracted, not buried.
- An order-flow signal came back a **clean null** — reported as a null.
- When my own model disagreed with a liquid price, I checked it against an independent bookmaker consensus before believing it — which is how I found and fixed a **structural bias in my own baseline** instead of mistaking it for an edge.

And the headline that falls out of grading myself: **the market is better calibrated than my own pre-committed model.** That's the point of the exercise. These markets are very hard to beat; the interesting work is measuring *how* they work, not pretending to out-predict them.

## Why now — and why the World Cup was just a testbed

This isn't a historical curiosity. As of mid-2026, DRW, Wintermute, and IMC are building **dedicated Polymarket/Kalshi desks** — for exactly this: cross-venue microstructure, cross-platform arbitrage, reacting to news before convergence. I mapped where that edge lives (sub-second, at the depth collapse, against adverse flow) and proved retail latency can't take it. That's the reconnaissance; the desks have the infrastructure.

The sport is incidental. Goals are just a clean, repeated, *exogenous* information shock — the ideal natural experiment for measuring price discovery. **The same methods price an FOMC decision or a CPI print** — which is where prediction markets are actually heading: the institutional volume is in macro and economic-data contracts (the Fed now studies Kalshi as an economic barometer), and that's the durable, regulation-safe core of this market. A goal shock and a CPI surprise are the same measurement problem. The World Cup was the cleanest place to build the tools; the tools travel.

**The full desk note, the pre-registration, and all the code — including the live capture pipeline — are in the [repo](https://github.com/Thesavagecoder7784/xResidual).** Finding an edge and correctly proving you can't trade it is, I'd argue, exactly the job.
