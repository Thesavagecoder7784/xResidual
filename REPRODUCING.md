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

**Which scripts are Tier B, and how they behave without their inputs.** The robustness scripts
divide by what they read, and the division follows the withholding policy exactly:

| Reads | Scripts | From a fresh clone |
|---|---|---|
| `viz/market/{harvest,infoshare,ofi}` — aggregate, published | `harvest_ci.py`, `harvest_predict.py`, `identification_check.py`, `ofi_ci.py` | Reproduce their artifacts **bit-identically** |
| `writeups/_*.json` — published | `clock_verified_leadlag.py`, `depth_instant.py` | Reproduce from the shipped artifacts |
| `viz/market/leadlag/` — **per-event, withheld** | `detection_check.py`, `leadgate.py` | **Exit 1 and change nothing** |

That last row is Tier B and cannot be otherwise: the input is the per-event venue data this
document commits to withholding. Both scripts fail loudly rather than quietly. `detection_check.py`
did not always — it wrote `n_archives: 0` over a good artifact and exited 0, so anyone who cloned
the repository and ran it destroyed the shipped numbers without seeing an error. It now refuses,
matching `leadgate.py`. A script that silently produces a null result from missing inputs is worse
than one that crashes.

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
of Use restrict republication of Kalshi Data; Polymarket's terms govern its off-chain
order-book feed. A study of two live venues therefore cannot ship its inputs, no matter how
much its author would prefer to. Given that constraint, there are two honest options: publish
nothing, or publish the least that still lets a reader check the work, and be exact about the
boundary. This repository takes the second.

**Stated precisely, because the distinction matters.** What follows is a description of what
is withheld and why — it is not a claim that everything which *does* ship is affirmatively
licensed. It is not. Kalshi's Data Terms of Use §II enumerate "creating derivative works",
"compiling ... to create collections, compilations, databases" and "conducting 'text and data
mining'" among prohibited uses, and the Developer Agreement bars collecting or storing API
data except to facilitate one's own trading (§3.1), accessing the API for "benchmarking"
purposes (§3.5), and public statements about Kalshi's services without prior written approval
(§6.4). A cross-venue price-discovery study is not obviously outside any of those. Derived
aggregates are a mitigation — they are the minimum that supports the inferences, and they
carry no quote levels and no timestamps — but a mitigation is not a permission, and this
section should not be read as asserting one. The honest description of this repository's
position is that it withholds everything whose redistribution would be plainly improper and
publishes the remainder under a reading of the terms that the venue has not confirmed.
Written authorization is the fix, and asking for it is the open item.

What that means in practice:

| Layer | Ships | Why |
|---|---|---|
| Capture pipeline (`logger/`) | **Yes** | Our code, not their data. Re-point it at either venue's public feed with your own credentials. |
| Analysis code (`scripts/`, `xresidual/`) | **Yes** | Every estimator, gate and statistic, including the ones that produced null results. |
| Derived per-match statistics | **Yes** | Counts, medians, shares, regression sufficient statistics — measurement rather than market data, though see the caveat above on derivative works. |
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

It is a stricter posture than the surrounding literature takes. Bürgi, Deng and Whelan's study
of Kalshi ("Makers and Takers", University College Dublin WP2025/19 and GWU FORCPGM 2026-001,
January 2026) obtains transaction-level data on 300,000+ contracts by registering for the API
and pulling it with Python scripts, and neither discusses the terms nor restricts what it
publishes. Becker's `prediction-market-analysis` releases 72.1
million Kalshi and Polymarket trades — execution price, taker side and timestamp per trade —
publicly on GitHub under MIT. Marriott (SSRN 6583921) reconstructs tick-level limit order
books for every Kalshi market from the WebSocket stream and publishes the method and aggregate
dataset characteristics while withholding the ticks, which is the closest analogue to the
position taken here. The field norm is to state the collection method and move on; this
repository states the constraint as well, which is a choice rather than a requirement.

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
anything; from a fresh clone, once the rewrite has been pushed, it must report `PURGED_TOTAL:
0` alongside one restored blob for each redacted artifact the paper still reproduces from).
**Until that reports zero, treat the bulleted withholding statement above as a statement of
policy, not of fact.**

*Third correction, 2026-08-04:* the paragraph above stating that the aggregate per-game archives
"do ship" was, until this date, false in the other direction. A blanket `.gitignore` rule covered
`viz/market/{ofi,liquidity,infoshare,harvest,eventis,livewp}`, but files already tracked when the
rule landed kept shipping — so an arbitrary subset reached a clone (20 of 74 harvest, 17 of 80
infoshare, 22 of 83 ofi) while this document claimed the directories were public. The robustness
scripts that read them (`harvest_ci.py`, `harvest_predict.py`, `identification_check.py`,
`ofi_ci.py`) therefore ran on a quarter of the data from a fresh clone and produced numbers
differing from the committed artifacts, with no error raised. All 359 files are now tracked; they
carry counts, medians and regression statistics only, so nothing about the withholding position
changes. Verified by cloning and regenerating: the three scripts reproduce their artifacts
bit-identically. Note that this is the *same* defect as the correction below, with its sign
flipped — an ignore rule added after tracking neither withholds nor ships what you think.

*Second correction, 2026-08-04:* the audit behind that first correction swept `viz/` and
stopped there, and so missed `paper/positions.json` and `paper/book.md`. Three of the paper
book's 46 rows are Kalshi positions, and each carried a market ticker, entry and exit quote
levels, and a share count that divides straight back into the entry price — the same category
of per-event venue data the correction above is about, sitting in a directory nobody thought
of as data. Those rows are now redacted in place (stake, timing and realized P&L are ours and
are unchanged), the three `.bak` copies are dropped, and all of it is included in the history
rewrite. The general lesson is the one worth keeping: an audit scoped by directory finds
exactly what that directory holds, and per-event venue data is wherever you happened to write
it down.

**A limitation to state plainly:** Tier B is not re-runnable by a third party, and is not
fully re-runnable by us either. The tapes are transient by design (`scripts/cleanup_tapes.sh`
prunes them after processing), the collection VM has been decommissioned, and the per-game
archives survive only in part on the analysis machine — for the harvest ledger, 21 of the 66
matches behind the pooled figure. The committed Tier A artifacts are therefore the durable
evidence base, and the goal-level harvestability check
(`writeups/_harvest_unit_check.json`) reports its own reduced coverage rather than implying
the full sample. Anyone re-running Tier B must re-capture a live event from the venues'
feeds with their own credentials; they cannot reconstruct this tournament.
