# Build spec — Ground-truth signed-flow toxicity → forecast calibration, cross-venue

*Draft 2026-07-12. The genuinely-novel research direction from the Jul-12 deep-research survey. Execute post-Jul-19 (after the last tapes + the graded pre-reg). Feeds the SSRN paper (credential #1) + a citable dataset (credential #2).*

## The thesis (what's new, and why only we can do it)

Every public-feed prediction-market paper is stuck at **~59% trade-sign accuracy** (tick-rule ~50%, near-random), which flips the sign of effective spread on 67% of markets and Kyle's-λ on 60% (Dubach 2604.24366; Qin/Yang 2606.04217). So all signed-flow microstructure — VPIN, Kyle's-λ, order-flow toxicity, adverse selection — is unreliable off the public feed.

We can source **ground-truth signs on BOTH venues**:
- **Kalshi:** maker/taker (aggressor) is recorded *natively* in the trade data (`taker_side`, exchange-authoritative) — already in our websocket capture.
- **Polymarket:** the aggressor is recoverable from on-chain `OrderFilled` events on the CTFExchange (maker/taker addresses), via `eth_getLogs` on Polygon.

Combine that with a **pre-registered, publicly-graded calibrated forecast** (our frozen ledger) and the result is a study nobody in the literature can produce: **real order-flow toxicity, on ground-truth signs, on a non-election class, linked to out-of-sample forecast calibration** — and it generalizes to macro/election contracts (the Nov-midterm capture).

**Two named open questions it addresses:**
1. Dubach §8 (verbatim): *"are Polymarket's prices the leader or the follower..."* cross-venue — we answer on sports/in-play.
2. Qin/Yang: true VPIN predicts Brier calibration — we test whether it holds cross-venue on sports, and whether toxicity predicts *which venue leads*.

## What we already have (Phase 0 — inventory)
- ~80 WC matches of tick-level dual-venue websocket capture (order books + trades), Kalshi + Polymarket.
- Kalshi trades **already carry ground-truth `taker_side`** (verify the field is captured in `logger/`).
- Pre-registered forecasts, frozen in an append-only ledger, graded.
- Built pipelines: info-share (Hasbrouck/GG), lead-lag, OFI (top-of-book), harvestability/depth-collapse, cross-venue basis.
- **Missing:** the Polymarket on-chain sign leg (the roadmap Tier-3 piece).

## Phase 1 — On-chain harvest (Polymarket signs)
1. Map each WC match's Polymarket markets → **condition ID** (from the CLOB/Gamma market metadata) → the two/three **ERC-1155 outcome token IDs**.
2. Confirm the **CTFExchange** (and NegRiskCtfExchange) contract addresses on Polygon; get the `OrderFilled` event ABI.
3. `eth_getLogs` `OrderFilled` for those token IDs over each match window (a Polygon RPC — Alchemy/Infura/public). Precedent: 13.4M fills / 1 week / 77k addresses via direct `eth_getLogs` (Nechepurenko 2605.11640).
4. Parse each fill → `{maker, taker(=aggressor), assetId, makerAmount, takerAmount, price, blockTime}`. Taker = aggressor → the sign.
5. **Resolution caveat (scope carefully):** on-chain timestamps are **Polygon block time (~2s)**, NOT millisecond. So on-chain signs support the **toxicity/calibration** (slower) analysis, NOT the ms lead-lag (that stays on the websocket mids). Keep the two analyses on the right clock.

## Phase 2 — Sign validation (the credibility gate + a free robustness result)
1. Join on-chain fills to our Polymarket websocket trade feed (fuzzy match on time+price+size).
2. Compare our feed-inferred `side` (and the tick rule) against the on-chain aggressor.
3. Report our feed's sign accuracy — **expect ~59%**, replicating Dubach/Qin-Yang on a *new* (sports) dataset. That replication is itself citable, and it *justifies* using on-chain signs for everything downstream.

## Phase 3 — The toxicity panel (on true signs, BOTH venues)
Per match, on ground-truth signs (Kalshi native, Polymarket on-chain), compute:
- **VPIN** (volume-synchronized PIN) — volume-bucketed |buy−sell|/total.
- **Kyle's λ** — price impact per signed volume (Trump-YES precedent 0.53→0.01, Tsang/Yang).
- **Signed OFI** and **signed effective spread**.
- The **feed-inferred** versions alongside, to show they diverge/flip (the point).
- **Event-conditional:** does toxicity spike *before* goals (informed flow) vs at/after? This is the real adverse-selection test — and note the literature says orderbook-only "adverse selection" collapses to ~0 on real signs, so the *genuine* signal (if any) is here.

## Phase 4 — The calibration bridge (the novel contribution)
1. For each match, relate toxicity (VPIN/λ) to **calibration**: does higher informed-flow predict worse/better market Brier on that match?
2. **Market vs our pre-committed model**, conditioned on toxicity: when informed flow is high, does the market out-calibrate the model by more/less?
3. Cross-venue: does the **toxicity differential** between Kalshi and Polymarket predict **which venue leads** (info-share)? (Ties toxicity → price-discovery leadership — the field's open thread.)

## Phase 5 — Generalization
Run the identical pipeline on a **macro/election contract** (the Nov-midterm capture in the credential plan). Same ground-truth-signs method; shows the result isn't a sports artifact. This is the "method, not soccer" pivot made concrete.

## Deliverables
- **Dataset:** ground-truth signed-flow, dual-venue, per-match (Zenodo DOI) — credential #2.
- **Toxicity panel** per match/venue.
- **Paper:** *"Order-flow toxicity and forecast calibration in cross-venue prediction markets: evidence from ground-truth on-chain signs."* SSRN → arXiv q-fin.

## Honest risks (what could make this a null, reported as such)
- The on-chain↔websocket **join** may be imperfect (block-time vs ms, partial fills, order splitting). Budget real time for a robust match; report the match rate.
- The **toxicity↔calibration link may be weak** on ~80 sports matches — it could be a null. That's fine and still publishable (a clean null on ground-truth signs beats a spurious feed-based result).
- **Kalshi vs Polymarket sign mechanisms differ** (native field vs on-chain aggressor) — document that they're comparable but not identical.
- **Wash trading ~45% on sports** (Columbia) — must filter/flag wash fills before computing toxicity, or it contaminates VPIN.

## Effort & sequencing
~3–4 focused weeks: Phase 1–2 (~1 wk), Phase 3 (~1 wk), Phase 4 (~1 wk), writeup (~1 wk). Start **post-Jul-19**; the live-capture phase is essentially done (~80 matches), and the on-chain data is retrospective/permanent — nothing here is gated on games still being played.

## Key references
- Ng/Peng/Tao/Zhou, SSRN 5331995 — Poly leads Kalshi; large-trade OFI leads (election only).
- Dubach, arXiv 2604.24366 — the 59% problem; adverse selection collapses on real signs; §8 names the cross-venue open question.
- Qin/Yang, arXiv 2606.04217 (Polymarket-v1) — 1.2B on-chain trades, true VPIN predicts Brier.
- Tsang/Yang, arXiv 2603.03136 — on-chain Kyle's-λ; naive volume 2.4× overstated.
- Nechepurenko, arXiv 2605.11640 — the `eth_getLogs` OrderFilled method; on-chain toxicity panel.
- Gebele/Matthes, arXiv 2601.01706 — persistent LOOP violations (2–4%), semantic non-fungibility (NOT fleeting).
