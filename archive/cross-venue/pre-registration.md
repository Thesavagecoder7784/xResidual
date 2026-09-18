# Pre-registration: cross-venue prediction-market microstructure (2026 World Cup)

**Registered:** 2026-06-14, before the captured pool is large enough to test any hypothesis below.
**Author:** @PrabhatM27 · **Repo:** github.com/Thesavagecoder7784/xResidual
**Status at registration:** 4 cross-venue matches (8 goal events) for lead-lag, 1 match for the OFI
mechanism, 1 surprising goal for the overreaction test. None is conclusive yet. That is the point
of pre-registering now: the predictions, parameters, and decision rules are fixed in advance, so a
later confirmation is a genuine out-of-sample result and not a pattern fished from the data.

## Data

Kalshi and Polymarket are recorded tick by tick (full order books, every trade) for each World Cup
match by an always-on collector (`logger/ws_capture.py`, scheduled by `match_scheduler.py`, 35 min
pre-kickoff, 3 h per match). Tapes are parsed once on a laptop into per-match JSON summaries, which
are the durable, auditable record (`viz/market/{leadlag,ofi}`, `viz/model/overreaction`); the
pooled results rebuild from those JSONs. The pre-committed forecasts and these per-match summaries
are committed to git as timestamped receipts. Note: a material fraction of captures are single-
venue (Polymarket lists late, the scheduler force-launches near kickoff), so the **cross-venue** n
(H1, H2) grows slower than the match count; `capture_audit.py` tracks this.

## Hypotheses, predictions, and decision rules

Each parameter referenced is **frozen** at the value in the code today (listed in the last section).
No parameter will be changed after results accrue; if a method needs revising, it forks to a new,
separately pre-registered version, leaving this one's verdict on the record.

### H1. Polymarket leads Kalshi in price discovery around goals
- **Prediction:** on goal shocks, Polymarket's mid moves first; pooled median cross-venue lead is in
  Polymarket's favour, and Polymarket leads on a clear majority of events.
- **Literature anchor:** Ng, Peng, Tao & Zhou (2025), *Price Discovery and Trading in Modern
  Prediction Markets* (SSRN 5331995), find Polymarket leads Kalshi when liquidity is high.
- **Test statistic:** pooled median lead (ms) and leader share, gated to genuine co-moves
  (`best_corr >= 0.5`, `|lag| <= 8000 ms`); secondarily, Polymarket's Hasbrouck information share > 0.5.
- **Decision rule (evaluate at n >= 20 gated cross-venue events):** *confirmed* if median lead > 0
  toward Polymarket and leader share >= 65% with a one-sided sign test p < 0.05; *refuted* if the
  lead is centred on 0 or favours Kalshi; *inconclusive* otherwise.

### H2. Order flow is the mechanism, and Polymarket's flow leads Kalshi's price
- **H2a (impact):** each venue's 1 s mid return is positively related to its own order-flow
  imbalance (OFI). **Anchor:** Cont, Kukanov & Stoikov (2014). **Already met in sign** at
  registration (positive on both venues). Decision: *confirmed* if the pooled OFI→return correlation
  is positive on both venues and positive in a clear majority of individual matches; this is a sanity
  check, not the novel claim. (Significance note: the per-bin OLS t-stat is NOT a valid test here,
  since 1 s return bins are autocorrelated and nested within matches, so the effective sample is far
  below the bin count. All H2 decisions are judged on effect size plus consistency ACROSS MATCHES,
  never the bin t-stat.)
- **H2b (cross-venue mechanism):** Polymarket's OFI predicts Kalshi's *next* mid move more than the
  reverse, i.e. the predictive correlation peaks at a **positive** lead lag for Poly→Kalshi and
  exceeds the Kalshi→Poly correlation. This would be the order-flow reason H1 holds.
- **Test statistic:** standardized predictive correlation by lag (bins of 1 s, lags -3..+3 s),
  pooled by sufficient statistics. **Decision (evaluate at n >= 15 cross-venue matches):**
  *confirmed* if Poly→Kalshi peaks at lag >= +1 s with |corr| at least 1.3x the best Kalshi→Poly
  correlation AND the asymmetry holds in a clear majority of individual matches; *refuted* if
  symmetric or reversed; *inconclusive* otherwise.

### H3. Goal overreaction is real but surprise-conditional
- **Prediction:** fading the price move after a **surprising** goal (an underdog scoring; the side
  that gains was below 0.40 win-prob beforehand) earns positive P&L net of modeled cost; fading
  **ordinary** goals does not.
- **Literature anchor:** Choi & Hui (2014), *The Role of Surprise* (JEBO); "Profiting from
  overreaction in soccer betting odds" (2020), ~2.46% after commissions for surprising goals;
  against the efficient-market reading of Croxson & Reade (2014, *Economic Journal*).
- **Test statistic:** mean fade P&L (pp, net of 0.5pp/side cost), split into the surprising subset
  (`summary_surprising`) and all goals. Trade: enter 120 s after the shock, exit at 360 s, fade the
  spike. **Decision (evaluate at n >= 20 surprising goals):** *confirmed* if the surprising-goal
  mean P&L > 0 with a one-sample t > 2 and the all-goals mean is not larger; *refuted* if the
  surprising-goal fade is <= 0 at that n; *inconclusive* otherwise. **We will not call the fade a
  "mirage" without conditioning on surprise** (the earlier all-goals framing was an error, since
  corrected).

### H4. The cross-venue price lead is not tradeable after costs
- **Prediction:** a market-order strategy acting on H1's lead, crossing the real bid/ask at an entry
  latency >= 1 s, earns <= 0 net of the spread. **Anchor:** Poutré, Dionne & Yergeau (2024); the
  ~$40M of observed Polymarket-Kalshi arbitrage is bot-driven, seconds-lived, and cost-eroded.
- **Status:** already supported by the disclosed latency forward-test (edge at 0 s latency decays to
  0 by 1-2 s). Decision: *confirmed* if the forward-test stays <= 0 at >= 1 s latency as the pool
  grows; this guards against over-claiming H1 as a trade.

## Frozen analysis parameters

- Lead-lag: shock `min_jump = 0.04`, lead via cross-correlation, bin 200 ms, gate `best_corr >= 0.5`,
  `|lag| <= 8000 ms`.
- OFI: bin 1000 ms, lag sweep -3..+3 s, per-match standardization, sufficient-statistic pooling,
  microprice = imbalance-weighted (also tested vs mid).
- Overreaction: `entry_s = 120`, `exit_s = 360`, `min_jump = 0.05`, `confirm_ms = 20000`,
  `refractory_ms = 300000`, goal gate = top-N persistent shocks where N = the match's actual goal
  count, surprise cutoff = gain-side prior `< 0.40`, modeled cost 0.5pp/side.
- Tournament model (separate track): v1 frozen at file level; v2 = zero-inflated-Skellam draws +
  temperature T = 1.611 fit out-of-sample on 2018+2022.

## Stopping rule and commitments

- The World Cup provides a fixed, finite sample (104 matches). Each hypothesis is evaluated **once**
  per threshold above; if a threshold is not reached by the tournament's end, the result is reported
  as *inconclusive (n = X)*, not stretched.
- Every captured match enters the pool (no selection on result); misses are logged by the daily
  capture audit and disclosed.
- Results are reported the same way whether they confirm or refute. The per-match JSONs and the git
  history are the audit trail; this file is not edited after registration except to record outcomes
  in a dated "Results" section appended below.

## Results (appended as thresholds are reached)

_None yet. Pool too small. Findings to date are tracked live at /lab.html and labeled "forming."_
