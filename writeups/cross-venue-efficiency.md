# Cross-venue efficiency: what the arbitrage exploration taught (and why the code is gone)

I spent a stretch building cross-venue arbitrage tooling between **Kalshi** (US retail) and
**Polymarket** (global, crypto-native): live scanners, an order-book capacity walker, and a
paper execution bot (REST and websocket). The code has been **retired** — not because it
failed, but because what it *found* pointed somewhere else. This is the record of the
findings and the strategic conclusion, kept after the code was removed.

## What I found

**1. Cross-venue efficiency tracks liquidity, almost perfectly.**
On the **winner** market (the deepest, ~$1.9B Polymarket volume), the two venues are welded
together: average devigged gap **0.13pp**, and it held that tight across every logged day
(0.12–0.17pp, June 5–10), i.e. it was already arbitraged before I started watching and is
*maintained* continuously. The thinner **derivative** markets (advance, reach-round) drift
further apart — that's where any residual lives.

**2. The whole opportunity is tiny, and bounded to the dollar.**
Walking the *live* order books on both venues, level by level, net of Kalshi's fee, and
discarding sub-tick flicker: the entire cross-venue WC arbitrage holds **~$4,855 of capacity
for ~$38 of locked profit (~0.8%)**, almost all of it in thin derivative markets. The deep
**winner market nets $0** — efficient to the tick. (Methodological lesson: an unfiltered
walk reported a fragile, swinging "$427–$1,200" dominated by **sub-tick flicker on longshot
books** — 1.0c-tick noise and phantom depth. The robust number after requiring ≥0.5c/contract
net edge and a realistic depth cap is ~$38. The flashy headline was an artifact; the honest
number is small.)

**3. Polymarket is the sharper book.**
Anchored to the sharpest global soccer market logged (Betfair Exchange), Polymarket tracks
the sharp price closer than Kalshi (mean abs error **0.09 vs 0.13pp** across 48 teams). The
global crypto crowd does better price discovery than US retail.

**4. A faint, real home/crowd bias.**
CONCACAF is the *only* confederation Kalshi prices richer than Polymarket (≈ −0.1pp pooled,
t ≈ −2.5), strongest on **Mexico/USA to win the cup** — believable US-retail patriotism on
the longshot lines. Real and directionally consistent, but economically negligible.

## What it means

Put together, these are the **footprint of the arbitrageurs who are already there**, not an
opening. And the structure explains why an individual can't take it:

- **Cross-venue arb is a firm-dominated *execution* game** — latency (co-location), capital
  (inventory through settlement), and **legal structure**. Access is mirror-image: US persons
  can't use Polymarket (geofenced); Kalshi is US-regulated and harder for non-US entities. So
  a single party can rarely touch both — which is *why* the prices diverge (segmented crowds)
  **and** why few can close the gap. The residual that survives sits *below the cost-of-capture
  floor* (a month of locked capital for 0.8%, before transfer/KYC frictions).
- **The open moat for an individual is forecasting, not arbitrage.** Firms compete on price
  *reaction*; they largely do **not** compete on *fair value* — knowing where an event
  resolves, especially in niche / derivative / in-play soccer markets they model only
  "basically." That is a research and domain-modeling game where co-location and balance
  sheet don't help, and a focused individual can.

So the project's center of gravity moved: away from "out-execute the arb desks" (a race you
lose by definition) and toward **a live-scored forecasting edge in World Cup markets** — the
model benchmarked against the price, calibration measured on real results, on top of the
proprietary in-play capture. The arb work was the reconnaissance that mapped the terrain; the
forecasting record is the destination. The price-fetch helpers it left behind
(`scripts/venue_prices.py`) stay, because comparing the model to the live market price is
exactly what the forecasting work needs.

## Honest caveats
- All of this is pre/early-tournament and a point-in-time snapshot; the gaps breathe as
  order flow hits and bots re-close them.
- "Polymarket sharper than Kalshi" and the home bias are descriptive measurements on a small
  window, not claims of a tradable edge.
