#!/bin/bash
# Run the three on-top-of-liquidity tape builds, each only in a safe window
# (no live ws_capture + >=650MB free), so they never compete with the collector.
cd ~/xResidual
log=logger/data/micro_extra_build.log
safe(){ [ "$(pgrep -fc ws_capture.py 2>/dev/null || echo 0)" -eq 0 ] && [ "$(free -m | awk '/Mem:/{print $7}')" -ge 650 ]; }
wait_safe(){ for i in $(seq 1 360); do safe && return 0; sleep 120; done; return 1; }
run(){ echo "START $1 $(date -u)" >> "$log"; python3 "$1" >> "$log" 2>&1; echo "END $1 $(date -u)" >> "$log"; }
echo "QUEUED $(date -u)" >> "$log"
for b in scripts/build_liquidity.py scripts/build_harvest.py scripts/build_event_is.py; do
  if wait_safe; then run "$b"; else echo "GAVE UP before $b $(date -u)" >> "$log"; exit 1; fi
done
echo "ALL DONE $(date -u)" >> "$log"
