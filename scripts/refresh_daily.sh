#!/usr/bin/env bash
# Daily refresh for xResidual: update the paper track record, regenerate every _*.js
# from the latest logged snapshots, and re-render every card PNG. Wired to launchd
# (com.xresidual.render). Run manually any time with:  bash scripts/refresh_daily.sh
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-/usr/local/bin/python3}"
cd "$ROOT"
echo "===== refresh $(date -u +%FT%TZ) ====="
echo "-- forward-test (paper track record)"
"$PY" scripts/forwardtest_run.py || echo "  forwardtest failed (continuing)"
echo "-- goal-overreaction backtest (in-play edge test)"
"$PY" scripts/overreaction_run.py || echo "  overreaction failed (continuing)"
echo "-- elimination market: capture + model-vs-market coherence"
"$PY" scripts/build_elimination.py || echo "  elimination build failed (continuing)"
echo "-- re-mark paper book to live prices (paper/book.md)"
"$PY" paper/paper.py report || echo "  paper re-mark failed (continuing)"
echo "-- build all data + render all cards"
"$PY" scripts/build_all.py || echo "  build_all reported failures (see above)"
echo "===== done $(date -u +%FT%TZ) ====="
