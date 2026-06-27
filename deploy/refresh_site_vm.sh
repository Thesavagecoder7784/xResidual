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

# Serialize all runs: the 30-min cadence timer (xresidual-site) AND the matchday-end trigger
# (xresidual-matchday) both call this. A blocking lock lets a triggered run wait out an in-flight
# cadence run rather than racing it on the git push into $PUB. -w caps the wait so we never wedge.
exec 9>"/tmp/xres-site-refresh.lock"
flock -w 1500 9 || { echo "  another site refresh holds the lock; skipping this run"; exit 0; }

echo "===== site refresh $(date -u +%FT%TZ) ====="
# Pull results first so the sim + calibration see matches played since the last run.
"$PY" -c "from xresidual import data; df=data.load_results(refresh=True); print('  results ->', df['date'].max(), len(df))" || echo "  results refresh failed (cache)"
# Fast-result overlay: merge final scores from ESPN's free scoreboard ahead of the martj42 feed
# (1-2d lag), so the model conditions same-day. No key, no quota — fetched fresh every cycle.
# Must run after the martj42 refresh and before every build below. martj42 stays canonical:
# once it carries a game, this defers to it.
"$PY" scripts/fetch_scores.py || echo "  scores overlay failed (cache)"
"$PY" scripts/prediction_board.py             || echo "  board log failed"
"$PY" scripts/prediction_board.py --score     || echo "  CLV failed"
"$PY" scripts/prediction_board.py --calibrate || echo "  calibrate failed"
"$PY" scripts/build_matches.py    || echo "  matches failed"
"$PY" scripts/build_matches_v2.py || echo "  matches v2 failed"   # parallel ZISM draw-calibrated model, vs v1
"$PY" scripts/build_matches_v3.py || echo "  matches v3 failed"   # v3 = v2 + format-conditional draw lift; live A/B vs v2 on the remaining group games
"$PY" scripts/build_bracket.py    || echo "  bracket failed"
"$PY" scripts/build_dashboard.py  || echo "  dashboard failed"
"$PY" scripts/build_dashboard_v2.py || echo "  dashboard v2 failed"   # temperature-calibrated board (v2)
"$PY" scripts/build_buildup_trajectory.py || echo "  buildup failed"   # title-race trajectory card data; INCREMENTAL (merges onto the seeded series), so the VM's limited snapshot retention never truncates the full May-onward history. Not published — kept fresh on the VM for the laptop to pull + render the card.
"$PY" scripts/venue_calibration.py || echo "  venue calibration failed"   # pending until ~Jun 27

# Microstructure: streaming single pass (lead-lag + OFI + overreaction) now fits the VM (~0.5 GB peak,
# was ~7 GB), so the VM processes settled tapes itself — no more laptop dependency. Then publish the
# pooled feeds into docs/data (the VM now BUILDS these; it used to only relay the laptop's copies).
# MEMORY GUARD: a ~800 MB tape (~0.7 GB peak) + a live capture (~150 MB) overruns the 898 MB VM and OOMs.
# So only process when NO capture is running — settled tapes wait for a gap between matches. Feeds below
# still republish every cycle regardless, so the live site stays current.
if pgrep -f "[w]s_capture.py" >/dev/null 2>&1; then
  echo "  capture live — deferring tape processing this cycle (memory guard); feeds still republished"
else
  "$PY" scripts/build_micro_all.py || echo "  micro_all failed"
fi
cp -f viz/market/_ofi.js docs/data/ofi.js 2>/dev/null || true
cp -f viz/market/_infoshare.js docs/data/infoshare.js 2>/dev/null || true
cp -f viz/market/_livewp.js docs/data/livewp.js 2>/dev/null || true
cp -f viz/model/_overreaction.js docs/data/overreaction.js 2>/dev/null || true
"$PY" - <<'PYLL' || echo "  leadlag feed extract failed"
import json
from datetime import datetime, timezone
d = json.load(open("writeups/_leadlag_results.json"))
open("docs/data/leadlag.js", "w").write("window.LEADLAG_POOLED = " + json.dumps(
    {"pooled": d.get("pooled"), "n_matches": d.get("n_matches"), "min_jump": d.get("min_jump"),
     "asof": datetime.now(timezone.utc).isoformat()}) + ";\n")
PYLL

# Publish: refresh the clone, copy regenerated data + the pre-committed forecast LEDGERS in,
# commit + push. Publishing the ledgers (the auditable "receipts") keeps origin in sync with
# the live track record — the timestamped commits are the proof of pre-commitment — and stops
# the laptop ever diverging from the VM-owned ledger. The VM is the single writer.
cd "$PUB" || { echo "  no publish clone at $PUB"; exit 1; }
git pull --rebase --autostash 2>&1 | tail -1
# The VM now builds leadlag/ofi/overreaction itself (streaming made them fit), so they publish
# straight from $REPO/docs/data with everything else — no exclude, no laptop relay.
rsync -a "$REPO/docs/data/" "$PUB/docs/data/"
mkdir -p "$PUB/paper"
rsync -a "$REPO/paper/forecasts.jsonl" "$REPO/paper/match_forecasts.jsonl" "$REPO/paper/match_forecasts_v2.jsonl" "$REPO/paper/match_forecasts_v3.jsonl" "$PUB/paper/" 2>/dev/null || true
git add docs/data paper/forecasts.jsonl paper/match_forecasts.jsonl paper/match_forecasts_v2.jsonl paper/match_forecasts_v3.jsonl
if git diff --cached --quiet; then
  echo "  no changes — nothing to publish"
else
  git -c user.email="vm@xresidual.local" -c user.name="xResidual VM" \
      commit -q -m "site data + ledger refresh $(date -u +%FT%TZ)"
  git push origin HEAD:main 2>&1 | tail -2 && echo "  published"
fi
echo "===== done $(date -u +%FT%TZ) ====="
