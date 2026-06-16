#!/usr/bin/env bash
# Lightweight LIVE-SITE refresh for the always-on Azure VM.
#
# Regenerates the dashboard data (docs/data/*.js) from the latest international results and the
# VM's own collected market snapshots, then publishes it to GitHub Pages. This is the half of
# refresh_daily.sh that needs NO headless Chrome — the VM has ~900 MB RAM and never renders
# cards (those stay on the laptop). Wired to the xresidual-site systemd timer (every 30 min);
# commits only when the data actually changed, so idle cycles are free.
#
# Publishing uses a separate shallow git clone ($PUB) authed by the write deploy key, so the
# data-rich working tree ($REPO, rsync-synced, no .git) stays untouched.
set -uo pipefail
REPO="/home/azureuser/xResidual"
PUB="/home/azureuser/xres-pub"
PY="$REPO/.venv/bin/python"
export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/xres_deploy -o IdentitiesOnly=yes"
cd "$REPO" || exit 1

echo "===== site refresh $(date -u +%FT%TZ) ====="
# Pull results first so the sim + calibration see matches played since the last run.
"$PY" -c "from xresidual import data; df=data.load_results(refresh=True); print('  results ->', df['date'].max(), len(df))" || echo "  results refresh failed (cache)"
# Fast-result overlay: merge final scores from The Odds API ahead of the martj42 feed (1-2d lag),
# so the model conditions same-day. Cadence-guarded (SCORES_EVERY_H, default 6h); off-cadence
# cycles re-apply the cached overlay for free. Must run after the refresh (which wipes it) and
# before every build below. martj42 stays canonical — once it carries a game, this defers.
"$PY" scripts/fetch_scores.py                 || echo "  scores overlay failed (cache)"
"$PY" scripts/prediction_board.py             || echo "  board log failed"
"$PY" scripts/prediction_board.py --score     || echo "  CLV failed"
"$PY" scripts/prediction_board.py --calibrate || echo "  calibrate failed"
"$PY" scripts/build_matches.py    || echo "  matches failed"
"$PY" scripts/build_matches_v2.py || echo "  matches v2 failed"   # parallel ZISM draw-calibrated model, vs v1
"$PY" scripts/build_bracket.py    || echo "  bracket failed"
"$PY" scripts/build_dashboard.py  || echo "  dashboard failed"
"$PY" scripts/build_dashboard_v2.py || echo "  dashboard v2 failed"   # temperature-calibrated board (v2)
"$PY" scripts/build_buildup_trajectory.py || echo "  buildup failed"   # title-race trajectory card data; INCREMENTAL (merges onto the seeded series), so the VM's limited snapshot retention never truncates the full May-onward history. Not published — kept fresh on the VM for the laptop to pull + render the card.
"$PY" scripts/venue_calibration.py || echo "  venue calibration failed"   # pending until ~Jun 27

# Publish: refresh the clone, copy regenerated data + the pre-committed forecast LEDGERS in,
# commit + push. Publishing the ledgers (the auditable "receipts") keeps origin in sync with
# the live track record — the timestamped commits are the proof of pre-commitment — and stops
# the laptop ever diverging from the VM-owned ledger. The VM is the single writer.
cd "$PUB" || { echo "  no publish clone at $PUB"; exit 1; }
git pull --rebase --autostash 2>&1 | tail -1
rsync -a "$REPO/docs/data/" "$PUB/docs/data/"
mkdir -p "$PUB/paper"
rsync -a "$REPO/paper/forecasts.jsonl" "$REPO/paper/match_forecasts.jsonl" "$REPO/paper/match_forecasts_v2.jsonl" "$PUB/paper/" 2>/dev/null || true
git add docs/data paper/forecasts.jsonl paper/match_forecasts.jsonl paper/match_forecasts_v2.jsonl
if git diff --cached --quiet; then
  echo "  no changes — nothing to publish"
else
  git -c user.email="vm@xresidual.local" -c user.name="xResidual VM" \
      commit -q -m "site data + ledger refresh $(date -u +%FT%TZ)"
  git push origin HEAD:main 2>&1 | tail -2 && echo "  published"
fi
echo "===== done $(date -u +%FT%TZ) ====="
