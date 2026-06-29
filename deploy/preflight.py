#!/usr/bin/env python3
"""Pre-kickoff health check — one green/red board for the collection VM.

    python3 deploy/preflight.py

Run from the laptop any time, especially ~1h before a match. Does ONE ssh round-trip to
gather raw VM state, then evaluates every "must be true for capture to work" condition
locally and prints PASS/FAIL per line. Exit code 0 only if every check passes.

(Logic runs on the laptop on purpose — ssh only returns plain text, so there's no nested
heredoc/quoting to break.)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime, timezone

KEY = os.environ.get("KEY", "/Users/prabhatm/Documents/GitHub/xResidual/Sportslogging_key.pem")
VM = os.environ.get("VM", "azureuser@57.154.16.193")
DATA = "/home/azureuser/xResidual/logger/data"

# one remote bundle; single ssh round-trip. Sections are split on ###markers locally.
REMOTE = f"""
echo '###UPTIME';     uptime -p 2>/dev/null || uptime
echo '###ENABLED';    systemctl is-enabled xresidual-logger-free.timer xresidual-logger-orderbooks.timer xresidual-logger-oddsapi.timer xresidual-matchwatch.timer 2>/dev/null
echo '###SVC';        grep 'polymarket:' {DATA}/svc.log 2>/dev/null | tail -1
echo '###DISK';       df --output=pcent / | tail -1
echo '###MEMAVAIL';   free -m | awk '/^Mem:/{{print $7}}'
echo '###SWAP';       free -m | awk '/^Swap:/{{print $3"/"$2}}'
echo '###MATCHWATCH'; tail -1 {DATA}/matchwatch.log 2>/dev/null
echo '###FAILED';     systemctl --failed --no-legend 2>/dev/null | wc -l
"""

GREEN, RED, RST = "\033[32m", "\033[31m", "\033[0m"
fails = 0


def chk(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    tag = f"{GREEN}PASS{RST}" if ok else f"{RED}FAIL{RST}"
    print(f"  [{tag}] {name:<28} {detail}")


def main() -> int:
    now = datetime.now(timezone.utc)
    print(f"=== VM preflight  {now:%Y-%m-%d %H:%M:%S}Z  ({VM}) ===")
    try:
        out = subprocess.run(["ssh", "-i", KEY, "-o", "ConnectTimeout=20", VM, REMOTE],
                             capture_output=True, text=True, timeout=40).stdout
    except Exception as e:
        print(f"  [{RED}FAIL{RST}] ssh to VM                    {e}")
        return 1
    sec = {}
    cur = None
    for line in out.splitlines():
        if line.startswith("###"):
            cur = line[3:]; sec[cur] = []
        elif cur:
            sec[cur].append(line)
    g = lambda k: "\n".join(sec.get(k, [])).strip()

    chk("VM reachable + up", bool(g("UPTIME")), g("UPTIME"))

    n_en = sum(1 for x in g("ENABLED").split() if x == "enabled")
    chk("4 collector timers enabled", n_en == 4, f"{n_en}/4 enabled")

    m = re.search(r"\[([0-9T:.+-]+)\].*polymarket: (\d+) ok / (\d+) err.*kalshi: (\d+) ok / (\d+) err", g("SVC"))
    if m:
        ts = datetime.fromisoformat(m.group(1)); age = (now - ts).total_seconds() / 60
        pok, perr, kok, kerr = map(int, m.group(2, 3, 4, 5))
        chk("last logger tick fresh", age < 35, f"{age:.0f} min ago")
        chk("logger tick clean", perr == 0 and kerr == 0, f"poly {pok}ok/{perr}err · kalshi {kok}ok/{kerr}err")
        chk("expanded markets live", pok >= 300 and kok >= 900, f"poly {pok} (≥300) · kalshi {kok} (≥900)")
    else:
        chk("last logger tick fresh", False, "no parseable polymarket line in svc.log")

    disk = re.sub(r"\D", "", g("DISK"))
    chk("disk < 85% used", disk.isdigit() and int(disk) < 85, f"{disk}% used")
    avail = g("MEMAVAIL")
    chk("memory not exhausted", avail.isdigit() and int(avail) > 60, f"{avail} MB avail · swap {g('SWAP')}")

    mw = g("MATCHWATCH")
    nxt = re.search(r"next: (.+?) in (\d+) min", mw)
    if nxt:
        mins = int(nxt.group(2))
        chk("matchwatch armed (sees next)", True, f"{nxt.group(1)} in {mins//60}h{mins%60:02d}m")
    else:
        # also OK if a capture is currently in-window (line won't say "next:")
        chk("matchwatch armed (sees next)", bool(mw), mw[:60] or "no matchwatch.log line")

    chk("no failed services", g("FAILED") == "0", f"{g('FAILED')} failed units")

    ok = fails == 0
    print(f"\n=== {GREEN+'ALL CLEAR — capture is armed'+RST if ok else RED+str(fails)+' CHECK(S) FAILED — investigate before kickoff'+RST} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
