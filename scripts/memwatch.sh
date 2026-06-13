#!/usr/bin/env bash
# Lightweight RAM/swap watchdog for the always-on VM (~900 MB RAM). Samples every SAMPLE_S
# seconds and appends one line to memwatch.log; when available RAM drops below WARN_MB or swap
# usage climbs past WARN_SWAP_MB (the swap-thrash / OOM risk during high-liquidity captures), it
# also writes a WARN line to memwatch.warn.log so incidents are trivial to grep after the fact.
# Itself tiny (bash + awk + pgrep); the unit caps it with MemoryMax so it can never be the problem.
set -u
LOG="${MEMWATCH_LOG:-/home/azureuser/xResidual/logger/data/memwatch.log}"
SAMPLE_S="${MEMWATCH_SAMPLE_S:-30}"
WARN_MB="${MEMWATCH_WARN_MB:-40}"          # baseline avail is ~57 MB idle; warn as captures eat into it
WARN_SWAP_MB="${MEMWATCH_WARN_SWAP_MB:-200}"
mkdir -p "$(dirname "$LOG")"
echo "$(date -u +%FT%TZ) memwatch start: sample=${SAMPLE_S}s warn<${WARN_MB}MB avail or >${WARN_SWAP_MB}MB swap" >> "$LOG"
while :; do
  avail=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
  swap=$(awk '/SwapTotal/{t=$2} /SwapFree/{f=$2} END{print int((t-f)/1024)}' /proc/meminfo)
  caps=$(pgrep -fc ws_capture.py 2>/dev/null || echo 0)
  ts=$(date -u +%FT%TZ)
  level="ok"
  if [ "${avail:-0}" -lt "$WARN_MB" ] || [ "${swap:-0}" -gt "$WARN_SWAP_MB" ]; then level="WARN"; fi
  echo "$ts avail=${avail}MB swap_used=${swap}MB captures=${caps} $level" >> "$LOG"
  if [ "$level" = "WARN" ]; then
    echo "$ts MEMWATCH low memory: avail=${avail}MB swap_used=${swap}MB captures=${caps}" >> "${LOG%.log}.warn.log"
  fi
  sleep "$SAMPLE_S"
done
