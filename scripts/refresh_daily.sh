#!/usr/bin/env bash
# Daily refresh for xResidual: update the paper track record, regenerate every _*.js
# from the latest logged snapshots, and re-render every card PNG. Wired to launchd
# (com.xresidual.render). Run manually any time with:  bash scripts/refresh_daily.sh
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-/usr/local/bin/python3}"
cd "$ROOT"
echo "===== refresh $(date -u +%FT%TZ) ====="
# Pull the latest international results FIRST so everything downstream (Elo, the tournament
# sim, per-match residuals, and the calibration grade) sees matches played since the last run.
# The martj42 source is daily-updated and includes World Cup matches ~1-2 days after kickoff,
# so the residual/calibration deliverables update on a one-day lag instead of freezing.
echo "-- refresh international results (residuals + calibration depend on this)"
"$PY" -c "from xresidual import data; df=data.load_results(refresh=True); print('  results ->', df['date'].max(), len(df), 'rows')" || echo "  results refresh failed (continuing on cache)"
echo "-- forward-test (paper track record)"
"$PY" scripts/forwardtest_run.py || echo "  forwardtest failed (continuing)"
echo "-- goal-overreaction backtest (in-play edge test)"
"$PY" scripts/overreaction_run.py || echo "  overreaction failed (continuing)"
echo "-- elimination market: capture + model-vs-market coherence"
"$PY" scripts/build_elimination.py || echo "  elimination build failed (continuing)"
echo "-- re-mark paper book to live prices (paper/book.md)"
"$PY" paper/paper.py report || echo "  paper re-mark failed (continuing)"
# NOTE: the live-site data (docs/data/*.js) and the pre-committed ledgers (paper/*.jsonl) are
# owned and published by the always-on VM. deploy/refresh_site_vm.sh runs prediction_board,
# build_matches, build_bracket, and build_dashboard there and commits the results every ~30 min.
# Running those here would regenerate VM-owned TRACKED files, dirty the working tree, and collide
# on the next pull ("your local changes would be overwritten"). So this laptop refresh deliberately
# does NOT write docs/data or the ledgers. `git pull` brings the VM's published copies down.
echo "-- build all viz data + render all cards (the laptop's job: PNGs from viz/_*.js)"
"$PY" scripts/build_all.py || echo "  build_all reported failures (see above)"
echo "===== done $(date -u +%FT%TZ) ====="
