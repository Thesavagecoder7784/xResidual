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

*Correction, 2026-07-28:* the first two bullets above were accurate as policy but not as
practice until this date — `viz/market/leadlag/` (54 files) and `viz/model/overreaction/`
(24 files) had been committed before the corresponding `.gitignore` rules existed, so they
shipped in the public repository despite this statement. They have been removed from tracking;
the statement is now true as written.

**A limitation to state plainly:** Tier B is not re-runnable by a third party. The tapes are
transient by design (`scripts/cleanup_tapes.sh` prunes them after processing) and the collection
VM has been decommissioned, so anyone re-running Tier B must re-capture a live event from the
venues' feeds with their own credentials; they cannot reconstruct this tournament.

*Update, 2026-07-25:* the per-game archives had themselves survived only in part on the analysis
machine — for the harvest ledger, 21 of the 66 matches behind the pooled figure. They were
recovered in full from a VM disk backup, and the goal-weighted harvestability rate was re-pooled
over the whole ledger accordingly (it moved from 11.1% on the 21-match subset to **9.1%** on all
66). Every affected artifact regenerates bit-identically from those archives.

**What that does *not* fix — read this before quoting a coverage claim.** Recovery restored the
numbers on *this machine*; it did not put the archives in the repository. `viz/market/{harvest,
infoshare,ofi}` are gitignored, and only the files committed before those rules existed still
ship. So a reviewer cloning this repository re-runs the affected checks on a strict subset:

| Archive | Ships in a clone | Present locally | Numbers computed on the full set |
|---|---:|---:|---|
| `viz/market/harvest` | 21 | 66 used (74 files) | `_harvest_unit_check`, `_harvest_ci_results`, `_harvest_gate_results`, `pct_harvestable_goal_weighted` |
| `viz/market/infoshare` | 18 | 80 | `_identification_results` (ADF sweep, ILS bounds) |
| `viz/market/ofi` | 24 | 83 | `_ofi_ci_results` (match-clustered OFI null) |
| `viz/market/leadlag` | 0 (by policy) | 86 | `_leadgate_results`, `_detection_results`, `_clock_verified_results` |

`viz/market/leadlag` is withheld deliberately — it retains per-event quote levels and absolute
`t_ms`, so it falls under the redistribution limits above and is expected to be unreproducible.
The other three carry no quote levels and no timestamps; they are the class this document already
lists as shipping, and their absence is an artefact of the `.gitignore`-after-tracking sequence,
not a policy decision. Until those archives are committed, the pooled Tier A `writeups/*.json`
are the durable evidence for those figures, and `writeups/_harvest_unit_check.json` records both
its ledger coverage and its git-tracked coverage (`n_matches_tracked`) so the gap is a committed
number rather than a footnote.
