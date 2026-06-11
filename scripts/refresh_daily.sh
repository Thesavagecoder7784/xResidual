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
# Prediction board: log a fresh, pre-committed forecast batch vs the live market, then grade
# it. CLV (did the price drift toward the model?) scores from prices alone; calibration grades
# against outcomes as markets resolve (group-stage ~Jun 27, knockout rounds after). The ledger
# is append-only, so the track record builds itself hands-off across the tournament.
echo "-- prediction board: log forecast batch + score CLV + calibration"
"$PY" scripts/prediction_board.py || echo "  prediction board log failed (continuing)"
"$PY" scripts/prediction_board.py --score || echo "  CLV scoring failed (continuing)"
"$PY" scripts/prediction_board.py --calibrate || echo "  calibration failed (continuing)"
echo "-- dashboard: regenerate docs/data/dashboard.json for the live site"
"$PY" scripts/build_dashboard.py || echo "  dashboard build failed (continuing)"
echo "-- build all data + render all cards (incl. the prediction board)"
"$PY" scripts/build_all.py || echo "  build_all reported failures (see above)"
echo "===== done $(date -u +%FT%TZ) ====="
