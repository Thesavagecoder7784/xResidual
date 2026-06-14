#!/usr/bin/env bash
# Autonomous lead-lag sample sync (laptop side). Pulls any new PAIRED WC tape from the VM that is
# not yet in the local per-game archive, processes it into its JSON/.js (incremental — one tape
# parse), renders its PNG, rebuilds the pool, and deletes the local raw tape. Idempotent and safe
# to run repeatedly; the launchd agent (com.xresidual.leadlag-sync) fires it every ~2h.
#
# Why the laptop: parsing a 1 GB tape needs ~5-6 GB RAM, which would OOM the 900 MB collection VM.
# The per-game JSON is the durable artifact; the raw tape is disposable once processed.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY="${LEADLAG_KEY:-$HOME/Downloads/Sportslogging_key.pem}"
VM="${LEADLAG_VM:-azureuser@57.154.16.193}"
RD=/home/azureuser/xResidual/logger/data
LD="$ROOT/logger/data"; LL="$ROOT/viz/market/leadlag"; OV="$ROOT/viz/model/overreaction"; OFI="$ROOT/viz/market/ofi"
LOG="$LD/leadlag_sync.log"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# Use the interpreter that has the xResidual deps (numpy/sklearn etc.). launchd has a minimal
# PATH, so prefer the known-good full path, then fall back to a discovered python3.
PY="${LEADLAG_PY:-/usr/local/bin/python3.14}"
[ -x "$PY" ] || PY="$(command -v python3.14 || command -v python3)"
mkdir -p "$LL" "$LD" "$OV" "$OFI"
log(){ echo "$(date -u +%FT%TZ) $*" >> "$LOG"; }

# single-instance lock (mkdir is atomic; macOS has no flock)
LOCK="$LD/.leadlag_sync.lock"
if ! mkdir "$LOCK" 2>/dev/null; then log "another sync is running; skip"; exit 0; fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

ssh_(){ ssh -i "$KEY" -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new "$VM" "$@"; }

# 1. WC tapes on the VM that are paired (KXWCGAME), SETTLED (not written in 5 min = capture done),
#    and not yet in the local archive -> pull tape + pairs. (while-read + process substitution so
#    it works on macOS bash 3.2 and keeps `pulled` in the main shell.)
pulled=0
while IFS='|' read -r tape pairs slug; do
  [ -z "${slug:-}" ] && continue
  [ -f "$LL/$slug.json" ] && continue              # already in the archive
  log "pulling $slug"
  if scp -i "$KEY" -o ConnectTimeout=20 "$VM:$RD/$tape" "$VM:$RD/$pairs" "$LD/" >/dev/null 2>&1; then
    pulled=$((pulled+1))
  else
    log "  pull FAILED for $slug"
  fi
done < <(ssh_ "cd $RD 2>/dev/null && for p in ws-pairs-*.jsonl; do
  [ -e \"\$p\" ] || continue
  grep -q KXWCGAME \"\$p\" || continue
  t=\${p/pairs/events}; [ -e \"\$t\" ] || continue
  [ -n \"\$(find \"\$t\" -mmin +5 2>/dev/null)\" ] || continue
  slug=\$(echo \$p | sed -E 's/ws-pairs-[0-9TZ]+-//;s/\.jsonl//'); echo \"\$t|\$p|\$slug\"
done" 2>/dev/null || true)

# 2. process new tapes. build_micro_all loads each tape ONCE (~7 GB peak) and feeds every pipeline
#    that still needs it — lead-lag (cross-venue price discovery), the goal-gated overreaction fade,
#    and the OFI cross-venue mechanism — then pools each per-game archive. One parse, three analyses.
if [ "$pulled" -gt 0 ]; then
  log "processing $pulled new tape(s)"
  "$PY" "$ROOT/scripts/build_micro_all.py"      >> "$LOG" 2>&1 || log "  build_micro_all error"
fi

# 3. render any per-game .js whose .png is missing or stale
OVR='.series{stroke-dashoffset:0!important;animation:none!important}.reveal{opacity:1!important;animation:none!important}'
( cd "$ROOT/viz/market" && for js in "$LL"/*.js; do
    [ -e "$js" ] || continue
    g=$(basename "$js" .js); png="$LL/$g.png"
    [ -f "$png" ] && [ "$png" -nt "$js" ] && continue
    [ -x "$CHROME" ] || continue
    sed -e "s#src=\"_leadlag.js\"#src=\"leadlag/$g.js\"#" -e "s#<head>#<head><style>$OVR</style>#" leadlag_tape.html > "_tmp_$g.html"
    "$CHROME" --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
      --window-size=1600,900 --screenshot="$png" "file://$PWD/_tmp_$g.html" 2>/dev/null
    rm -f "_tmp_$g.html"; log "rendered $g.png"
  done )

# 4. delete only local tapes that produced ALL THREE per-game JSONs (lead-lag, overreaction, OFI);
#    keep a tape if any pipeline failed, so the next run can retry. The VM copy persists 48h anyway.
kept=0
for t in "$LD"/ws-events-*.jsonl; do
  [ -e "$t" ] || continue
  s=$(basename "$t" | sed -E 's/ws-events-[0-9TZ]+-//;s/\.jsonl//')
  if [ -f "$LL/$s.json" ] && [ -f "$OV/$s.json" ] && [ -f "$OFI/$s.json" ]; then rm -f "$t"; else kept=$((kept+1)); log "  KEPT unprocessed $s (retry next run)"; fi
done
log "sync done: $pulled pulled, $kept unprocessed kept"
