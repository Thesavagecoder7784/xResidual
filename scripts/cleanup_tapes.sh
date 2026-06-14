#!/usr/bin/env bash
# Delete capture tapes (ws-events-*.jsonl) older than TAPE_KEEP_DAYS to keep the VM's disk in
# check over a 72-game tournament (~0.5-1.2 GB/game would otherwise fill the 62 GB box).
#
# Safe by construction:
#   - only ws-events-*.jsonl tapes are deleted; the tiny ws-pairs-*.jsonl alignment records stay.
#   - a tape being written has a fresh mtime, so an in-progress capture is never matched.
#   - the 2-day window leaves ample time to pull a tape before it's removed.
# Per the incremental lead-lag design, a tape is disposable once pulled + processed into its
# per-game JSON, so age is a safe proxy for "done with it".
set -u
DIR="${TAPE_DIR:-/home/azureuser/xResidual/logger/data}"
KEEP_DAYS="${TAPE_KEEP_DAYS:-2}"
LOG="$DIR/tape_cleanup.log"

avail() { df -BG --output=avail "$DIR" 2>/dev/null | tail -1 | tr -dc '0-9'; }
before=$(avail)
# -mmin (minutes), not -mtime: -mtime +N floors the age and means "older than N+1 days". Minutes
# give an exact KEEP_DAYS*24h cutoff, so KEEP_DAYS=2 really keeps the last 48h.
mapfile -t gone < <(find "$DIR" -maxdepth 1 -name 'ws-events-*.jsonl' -mmin "+$((KEEP_DAYS * 1440))" -print -delete 2>/dev/null)
after=$(avail)
echo "$(date -u +%FT%TZ) tape-cleanup: removed ${#gone[@]} tape(s) older than ${KEEP_DAYS}d; avail ${before}G -> ${after}G" >> "$LOG"
for f in "${gone[@]}"; do echo "  - $(basename "$f")" >> "$LOG"; done
