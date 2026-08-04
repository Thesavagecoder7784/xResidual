# Reproducing the paper

Every number, table, and figure in the manuscript (`paper/arxiv/`) maps to a script and
a committed derived artifact. This document is the map. It has two tiers:

- **Tier A — reproduce from shipped artifacts (no venue credentials needed).** The
  aggregated per-match result JSONs in `writeups/_*_results.json` are committed to the
  repo. From them, every paper number and figure regenerates. This is what a reviewer
  runs. `_leadlag_results.json` ships **redacted**: per-event venue quote levels and
  absolute timestamps are stripped (see *Data availability*), leaving the derived
  which-venue-led-by-how-many-ms measurements every published statistic is computed from.
  Verified lossless — the hardened statistics and all four figures regenerate unchanged
  from the redacted file.
- **Tier B — regenerate the artifacts from raw captures (needs your own credentials).**
  The raw order-book/trade tapes are **not** redistributed (see *Data availability*
  below). You regenerate them from the venues' public feeds, then rebuild the JSONs.

## Environment

```
docker build -t xresidual .
docker run --rm -v "$PWD:/xresidual" xresidual make check
```
or, natively (Python 3.12):
```
pip install -r requirements.txt
```

## Tier A — reproduce the paper numbers (one command)

```
make paper        # emit macros from JSON -> compile the PDF
```
which runs:
```
python scripts/emit_macros.py          # writeups/_*_results.json -> paper/arxiv/macros.tex
cd paper/arxiv && latexmk -pdf main.tex
```
`make check` (also run in CI) asserts the macros match the JSONs and runs the test suite,
so a stale paper number cannot be committed.

## Claim → script → artifact map

| Paper location | Claim | Script | Artifact |
|---|---|---|---|
| Abstract, §5.2 (Fig. leadlag) | Cross-venue lead-lag, cluster-robust | `scripts/build_leadlag.py` → `scripts/harden_leadlag_stats.py` | `_leadlag_results.json`, `_hardened_stats.json` |
| §5.2 (Fig. infoshare) | Hasbrouck / Gonzalo–Granger info share | `scripts/build_infoshare.py` → `scripts/harden_leadlag_stats.py` | `_infoshare_results.json`, `_hardened_stats.json` |
| §5.1 | Law of one price; depth asymmetry | `scripts/build_liquidity.py` | `_liquidity_results.json` |
| §5.3 | Goal-shock under-reaction | `scripts/build_livewp.py` | `_livewp_results.json` |
| §5.4 (Fig. reliability) | Calibration; favorite–longshot bias | `scripts/build_calibration.py` | `_calibration_results.json` |
| §5.5 | Order-flow imbalance | `scripts/build_ofi_leadlag.py` | `_ofi_results.json` |
| §6.2 (Fig. book_collapse) | Un-harvestability ledger | `scripts/build_harvest.py`, `scripts/build_liquidity.py` | `_harvest_results.json`, `_liquidity_results.json` |
| §6.2 | Harvestability at the goal unit (coverage-labelled) | `scripts/harvest_unit_check.py` | `_harvest_unit_check.json` |
| §5.4 | Market-vs-model paired Brier test | `scripts/build_calibration.py` | `_calibration_results.json` (`paired_market_vs_v1`) |
| §7 (Table) | Pre-registration scorecard | `scripts/grade_prereg.py` | graded from the above |
| All numeric macros | Single source of truth | `scripts/emit_macros.py` | `paper/arxiv/macros.tex` |

Seeds are fixed (`_hardened_stats.json` records `seed` and `n_bootstrap`), so the
hardened statistics are bit-reproducible.

> **Figures.** `make figures` (`scripts/build_paper_figures.py`) regenerates all four
> publication figures into `paper/arxiv/figures/` from the committed JSONs. They are
> byte-reproducible apart from the PDF creation timestamp. `main.tex` falls back to a
> labeled placeholder box for any figure that is absent, so the manuscript compiles either
> way.

## Tier B — regenerate artifacts from raw captures

```
python logger/ws_capture.py ...        # capture both venues' tapes (your own credentials)
python scripts/build_all.py            # tapes -> all writeups/_*_results.json
python scripts/harden_leadlag_stats.py # -> _hardened_stats.json (canonical)
```
The Kalshi WebSocket needs a Kalshi API key; the Polymarket on-chain fills need a Polygon
archive RPC. See `RUNBOOK.md`.

## Data availability

Code, the capture pipeline, the **derived** result artifacts (`writeups/_*_results.json`,
aggregated per-match statistics), the manuscript source (`paper/arxiv/`), the
pre-registration (a tagged pre-kickoff git commit), and content-hash provenance are public
in this repository (MIT). We do **not** redistribute the raw venue order-book and trade
captures: Kalshi's Data Terms and Developer Agreement, and Polymarket's Terms of Use,
restrict republication of their market data. Concretely, what is withheld is:

- the raw tapes (`logger/data/ws-events-*.jsonl`, `snapshots-*.jsonl`);
- the per-game archives that retain per-event quote levels or wall-clock timestamps —
  `viz/market/leadlag/` (dual-venue tick price series, and per-event `kalshi_reaction` /
  `poly_reaction` levels with absolute `t_ms`) and `viz/model/overreaction/` (per-trade
  price levels with absolute `t_ms`);
- per-event quote levels (`kalshi_reaction` / `poly_reaction`) and absolute wall-clock
  timestamps (`t_ms`) inside the pooled lead-lag artifact, stripped by
  `scripts/build_leadlag.py` before it is written.

The remaining per-game archives that *do* ship — `viz/market/{harvest,infoshare,ofi,liquidity,
eventis,livewp,sigma}/` — carry only aggregated per-match statistics (counts, medians,
correlations, regression sufficient statistics), with no quote levels and no timestamps.

What ships is measurement, not market data: counts, per-match shares, medians, regression
statistics, and signed lead times in milliseconds. No third-party raw market data is
redistributed with this paper.

### Reproducible by method, not by dataset

This study is deliberately **method-reproducible rather than data-reproducible**, and the
distinction is a design choice rather than a shortfall.

Kalshi's Developer Agreement limits API data to facilitating the member's own trading and
forbids sharing it with third parties absent written authorization (§3, §3.1); its Data Terms
restrict republication of Kalshi Data; Polymarket's terms govern its off-chain order-book
feed. A study of two live venues therefore cannot ship its inputs, no matter how much its
author would prefer to. Given that constraint, there are two honest options: publish nothing,
or publish everything that *can* be published and be exact about the boundary. This repository
takes the second.

What that means in practice:

| Layer | Ships | Why |
|---|---|---|
| Capture pipeline (`logger/`) | **Yes** | Our code, not their data. Re-point it at either venue's public feed with your own credentials. |
| Analysis code (`scripts/`, `xresidual/`) | **Yes** | Every estimator, gate and statistic, including the ones that produced null results. |
| Derived per-match statistics | **Yes** | Counts, medians, shares, regression sufficient statistics. Measurement, not market data. |
| Pooled artifacts (`writeups/_*_results.json`) | **Yes** | Every published number regenerates from these — see Tier A. |
| Pre-registration | **Yes** | Tagged pre-kickoff commit; predictions cannot be edited after the fact. |
| Raw tapes, per-event quote levels, wall-clock timestamps | **No** | Third-party market data under the terms above. |

A reader can therefore audit every inferential step — re-derive each published figure from the
shipped aggregates, read the exact code that produced them, and check the pre-registered
predictions against the graded outcome — without ever receiving a byte of redistributable
venue data. What cannot be re-run is the capture itself, which requires your own accounts and
a live tournament.

This is the same posture as most credible empirical work on proprietary or licensed data
(CRSP, TAQ, exchange feeds): the code and the derived statistics are the scientific object;
the vendor's raw feed is not the author's to hand out. Treating the boundary as something to
state precisely, rather than to blur, is the point.

*Correction, 2026-07-28:* the first two bullets above were accurate as policy but not as
practice until this date — `viz/market/leadlag/` and `viz/model/overreaction/` had been
committed before the corresponding `.gitignore` rules existed, so they shipped in the public
repository despite this statement. They were removed from tracking on that date.

*Correction, 2026-08-04:* the note above concluded "the statement is now true as written."
That was wrong, and the error is worth recording because it is a general one. **Removing a
file from tracking does not remove it from the repository** — the objects remain reachable
from earlier commits, so the working tree is clean while the distributed artifact is not.
Untracking is a forward-looking fix that answers "what ships next" and says nothing about
what already shipped. The removal was necessary and correct; the conclusion drawn from it
was not.

Excising those paths from history is what actually makes the statement above true, and
`scripts/purge_history.sh` performs and verifies it (`--check` audits without modifying
anything; it must report `TOTAL: 0` from a fresh clone once the rewrite has been pushed).
**Until that reports zero, treat the bulleted withholding statement above as a statement of
policy, not of fact.**

**A limitation to state plainly:** Tier B is not re-runnable by a third party, and is not
fully re-runnable by us either. The tapes are transient by design (`scripts/cleanup_tapes.sh`
prunes them after processing), the collection VM has been decommissioned, and the per-game
archives survive only in part on the analysis machine — for the harvest ledger, 21 of the 66
matches behind the pooled figure. The committed Tier A artifacts are therefore the durable
evidence base, and the goal-level harvestability check
(`writeups/_harvest_unit_check.json`) reports its own reduced coverage rather than implying
the full sample. Anyone re-running Tier B must re-capture a live event from the venues'
feeds with their own credentials; they cannot reconstruct this tournament.
