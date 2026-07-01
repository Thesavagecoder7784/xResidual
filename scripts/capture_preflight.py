#!/usr/bin/env python3
"""Pre-flight capture check — verify EVERY upcoming match will capture cross-venue, HOURS before
kickoff, so a discovery break (a name mismatch, a late Kalshi listing, a market-format change) is
caught while there's still time to fix it — instead of at kickoff, when the game is already gone.

    python scripts/capture_preflight.py            # check upcoming games, print status
    python scripts/capture_preflight.py --hours 24 # horizon (default 18h)

Exit code is 1 (so a systemd timer surfaces it via `systemctl --failed`) when any game inside the
ALERT window is missing Kalshi markets — the dangerous case that silently drops a game to
Polymarket-only. Games where markets simply haven't listed yet (still far out) are informational,
not failures. This is the forward-looking complement to capture_audit.py (which flags misses only
AFTER kickoff, too late to act)."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "logger"))
import match_scheduler as ms   # noqa: E402

KALSHI_ALERT_S = 3 * 3600     # Kalshi lists hours ahead; still missing <3h out = a discovery/name bug
POLY_ALERT_S = 45 * 60        # Polymarket lists per-game markets close to KO, so only alert <45m out


def main() -> int:
    ap = argparse.ArgumentParser(description="pre-flight cross-venue capture check")
    ap.add_argument("--hours", type=float, default=18.0, help="how far ahead to check")
    args = ap.parse_args()
    now = datetime.now(timezone.utc)

    try:
        import envtools
        import ws_capture
        env = envtools.load_env()
    except Exception as e:
        print(f"preflight: cannot load env/ws_capture ({e})")
        return 0

    upcoming = [f for f in ms.load_fixtures()
                if 0 < (f["kickoff"] - now).total_seconds() <= args.hours * 3600]
    print(f"pre-flight · {now:%Y-%m-%d %H:%M}Z · {len(upcoming)} game(s) in the next {args.hours:.0f}h")

    alerts = []
    for f in upcoming:
        ms.resolve_fixture(f)                       # placeholder slot / drifted time -> real teams
        dt = (f["kickoff"] - now).total_seconds()
        try:
            k, p, pairs = ws_capture.discover_match_markets(env, f["team1"], f["team2"])
            nk, npoly, npairs = len(k), len(p), len(pairs)
        except Exception as e:
            nk = npoly = npairs = -1
        placeholder = ms._is_placeholder(f["team1"]) or ms._is_placeholder(f["team2"])
        # a game is at risk if Kalshi is missing within its window (discovery/name bug — Kalshi lists
        # early), or Polymarket is missing only when we're already very close to kickoff.
        kalshi_bad = (not placeholder) and (nk <= 0) and dt <= KALSHI_ALERT_S
        poly_bad = (not placeholder) and nk > 0 and npoly == 0 and dt <= POLY_ALERT_S
        if placeholder:
            verdict = "TEAMS-UNRESOLVED (feeders not done; will resolve nearer KO)"
        elif nk < 0:
            verdict = "DISCOVERY-ERROR"; alerts.append(f)
        elif nk > 0 and npoly > 0:
            verdict = f"OK · cross-venue ({npairs} pairs)"
        elif nk > 0:
            verdict = "kalshi ready · poly lists nearer KO" + (" · ALERT" if poly_bad else "")
        elif npoly > 0:
            verdict = "POLY-ONLY · KALSHI MISSING" + (" · ALERT" if kalshi_bad else "")
        else:
            verdict = "neither venue listed yet" + (" · ALERT" if kalshi_bad else "")
        if kalshi_bad or poly_bad:
            alerts.append(f)
        mark = "  ⚠️" if f in alerts else "  ·"
        print(f"{mark} T{dt/3600:+5.1f}h  {f['team1'][:14]:14s} v {f['team2'][:16]:16s}  k={nk} p={npoly} pairs={npairs}  {verdict}")

    if alerts:
        print(f"\n*** {len(alerts)} GAME(S) NOT READY FOR CROSS-VENUE CAPTURE — investigate now ***")
        return 1
    print("\nall clear: every near-term game is on track for cross-venue capture (or teams not yet set)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
