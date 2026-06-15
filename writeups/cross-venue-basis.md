# Two venues, one price: decomposing the Kalshi–Polymarket World Cup basis

*xResidual · [@PrabhatM27](https://twitter.com/PrabhatM27) · pre-tournament snapshot, 2026-06-06*

> **TL;DR.** The much-quoted price gap between Kalshi and Polymarket on the 2026 World
> Cup winner market is **mostly the house margin, not disagreement**. Strip each venue's
> overround and the two crowds' *beliefs* agree to **≈0.15pp on average** across 48
> teams. The durable difference is **cost**: Kalshi's margin (~5.4%) runs roughly **1.8×**
> Polymarket's (~3.0%). The small belief gap that survives is **structured by audience**:
> a primarily-American book (Kalshi) prices its own region richer (USA, Mexico,
> Netherlands), a global book (Polymarket) prices traditional and football-mad powers richer
> (England, Portugal, Japan, Brazil). And against the Betfair Exchange as a sharp
> benchmark, **Polymarket sits marginally closer** (mean abs error ~0.12pp vs ~0.16pp).

## Why this is interesting

Two independent venues trade the *same* contract ("Team X wins the 2026 World Cup"),
so cross-venue price differences are a clean, model-free window into how a market prices
information. The popular framing is that the venues "disagree," and the press routinely
quotes a 5–8¢ gap. That framing conflates two very different things: a difference in
*belief* (the crowds think a team's chances differ) and a difference in *margin* (the
venue charges a different vig). A trader cares which one it is, because only the first is
information and only the second is a recurring cost.

This also sharpens a question the microstructure literature leaves open. The leading
study of Polymarket ([*Anatomy of a Decentralized Prediction Market*,
2026](https://arxiv.org/html/2604.24366v1)) explicitly does not resolve whether
Polymarket leads or follows Kalshi. Price *discovery* (who moves first) needs in-play
shocks and is treated separately in this project (the cross-venue lead-lag study,
forthcoming once a marquee match is captured); price
*levels* (who is richer, and by how much, once margin is removed) can be measured today,
pre-tournament, and is the subject of this note.

This is not a "markets are wrong" exercise. Both venues are efficient and have largely
converged; the interesting object is the *structure* of the tiny residual that remains.

## Data

- **Venues.** Polymarket (Gamma API) and Kalshi (`KXMENWORLDCUP`), the full 48-team
  winner field on each, plus the Betfair Exchange outright (via The Odds API) as a sharp
  reference. All prices are logged by `logger/` into append-only JSONL.
- **Snapshot.** A single instant, **2026-06-06 ~09:12 UTC**. This is the central caveat
  (see Robustness); the logger accumulates the series needed to test persistence.
- **Price.** Polymarket mid = the YES price; Kalshi mid = (best bid + best ask)/2; Betfair
  = de-vigged implied probability from decimal odds.

## Method

The core move is to **decompose each quote into belief + margin**:

1. **De-vig.** For each venue, the raw winner prices sum to more than 1, the overround.
   Normalise each venue's field to sum to 1 (multiplicative de-vig), giving a *fair
   belief* per team. The raw sum, minus 1, is the venue's **margin**.
2. **Basis.** For every team, `basis = P_polymarket − P_kalshi` in percentage points,
   computed on the de-vigged beliefs. Positive = the global book prices the team higher;
   negative = the American book does. I also keep the *raw* (pre-de-vig) basis, so the
   margin's contribution to the visible gap is explicit.
3. **Sharp anchor.** Compare each retail venue to the Betfair Exchange (the deepest,
   sharpest soccer market available) by mean absolute error across the field, to see
   which retail crowd tracks the sharp price more closely.
4. **Aggregate.** Sum the de-vigged beliefs by confederation to get each venue's implied
   "which continent wins" distribution.

Code: `scripts/build_basis.py` (regenerates `viz/market/_basis.js`); de-vig in
`xresidual/devig.py`; card `viz/market/cross_venue_basis.html`.

## The findings

**1. The gap has all but closed.** On the favourites the two venues price within ~0.5¢
of each other raw (Spain 15.95¢ vs 16.45¢; France 16.05 vs 16.15). De-vigged, the mean
absolute belief gap across all 48 teams is **≈0.15pp**. The "5–8¢ gap" that circulated
earlier in the cycle has compressed as volume arrived: convergence, in real time.

**2. The durable difference is cost, not price.** Polymarket's overround is **~3.0%**;
Kalshi's is **~5.4%**, roughly 1.8×. So most of the *visible* gap on a favourite is the
margin being loaded differently, not the crowds disagreeing. Spain is the clean example:
a raw gap of −0.50pp shrinks to a −0.11pp belief gap once each venue's vig is removed. The
recurring, structural venue difference is that the same exposure costs nearly twice the
margin on one book.

**3. The residual belief gap is structured by audience.** What survives de-vigging is
small but not random. It lines up with who is in the room:

| Polymarket (global) richer | Kalshi (American) richer |
|---|---|
| England +1.02 · Portugal +0.75 | Netherlands −0.72 · Mexico −0.59 |
| Japan +0.72 · Brazil +0.38 | Germany −0.45 · USA −0.26 |

A primarily-American order book pays up for its home region (USA, Mexico) and a couple of
adjacent favourites; a global, soccer-literate book pays up for traditional powers
(England, Portugal) and football-mad markets (Japan, Brazil). This is a **home-crowd
tilt**, exactly the kind of audience-composition signal a venue-aware market maker would
skew around.

**4. The global book is marginally sharper.** Anchored to the Betfair Exchange,
Polymarket's mean absolute error is **~0.12pp** vs Kalshi's **~0.16pp**. Suggestive, not
decisive (see Robustness), but it points the same direction as (3): the global crowd is,
if anything, a touch closer to the sharp price.

**5. The continent market agrees too.** Aggregated to "which continent wins," the venues
are nearly identical: Europe **70.3%** (Polymarket) vs **69.9%** (Kalshi), South America
**20.5** vs **20.2**. The only visible continent-level tilt is North America (3.7% Kalshi
vs 2.8% Polymarket), which is just the USA/Mexico home tilt from (3) aggregating up.

## Robustness & honesty

- **Single snapshot.** Every number here is one instant. The structured residuals in (3)
  are the claim most exposed to this. They must be shown to *persist* across snapshots
  before being leaned on. The logger captures the series to do exactly that; until then
  this is a measurement, not an established regularity.
- **De-vig method.** I use multiplicative (proportional) de-vig. The literature
  (Štrumbelj 2014; Shin) shows margin is loaded unevenly, most at the longshots, so the
  method choice shifts the tails. The favourites (where the basis story lives) are
  least sensitive to it; `xresidual/devig.py` can re-run the field under power/Shin to
  quantify that, and the qualitative ranking is stable.
- **Longshot noise.** Kalshi mids on illiquid longshots come from wide bid/ask spreads
  and are noisy; the card and the residual table restrict to teams with ≥1% implied
  probability, where both venues are tightly quoted.
- **The sharp anchor is itself European/global.** Betfair is a global exchange, so
  "Polymarket tracks it closer" partly *reflects* the same global-audience overlap rather
  than independently proving Polymarket is sharper. It is consistent with (3), not a
  clean external proof, stated as suggestive.
- **What would make this wrong.** If, with more snapshots, the team-level residuals flip
  sign with no audience pattern, then (3) is noise and only (1)–(2) survive. (1)–(2) are
  robust: they are just the overrounds and the mean gap.

## What it means

Decompose a cross-venue quote into *belief + margin* and almost the entire visible gap is
margin. So the naive "buy here, sell there" reading of the 5–8¢ gap is mostly an illusion
of vig (and, with separate USDC/KYC-walled pools and per-venue fees, not arbitrageable
anyway). The genuinely informative part is the residual: the price difference that remains
after margin is a faint fingerprint of *who is trading where*, a home-crowd tilt, with
the global book marginally closer to the sharp line. Two efficient venues, one price; the
interesting structure is in the last fraction of a cent.

## Reproduce

```bash
python scripts/build_basis.py     # reads logged JSONL -> viz/market/_basis.js
./viz/render.sh market/cross_venue_basis.html
```

See also [FINDINGS.md](../FINDINGS.md) #12; the companion price-*discovery* (lead-lag)
study is forthcoming once a marquee match is captured. Code + methodology: the xResidual repo.
