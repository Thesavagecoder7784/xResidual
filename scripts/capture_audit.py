#!/usr/bin/env python3
"""Audit World Cup match capture: every fixture whose kickoff has passed should be in the launch
state. The scheduler is robust, but a match it NEVER launches (VM down across the match's whole
window, or neither venue ever lists in time) leaves no trace at all, it is simply absent from the
state file. This is the one silent-miss mode, and matches are the scarce resource, so this makes a
miss loud. Also flags degraded captures: single-venue (lead-lag needs both) or a tiny tape (a
capture that died early).

    python scripts/capture_audit.py          # human report; exit 1 only on a NEW (unacknowledged) miss
    python scripts/capture_audit.py --json    # machine-readable status line
    python scripts/capture_audit.py --ack     # acknowledge current misses into the baseline, then commit+deploy

Run on the VM, where captured-matches.json is authoritative. Wire to a daily timer so a miss is
caught the next day rather than discovered months later when the pool is short a game.

Misses are permanent, so a plain `exit 1 if any miss` leaves the daily service RED forever after the
first unrecoverable loss — alarm fatigue that hides the NEXT miss. So known-unrecoverable misses are
recorded in `capture_audit_baseline.json` (keyed by kickoff, since bracket placeholders make the name
unstable); the audit is RED only on a miss that is NOT in that baseline, and reports the acknowledged
ones quietly. Acknowledging is deliberate (`--ack` + commit), so a fresh miss can never be auto-silenced.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import unicodedata
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from match_scheduler import load_fixtures, _load_state, LEAD_S, GRACE_S, DATA_DIR  # noqa: E402

MIN_TAPE_MB = 5.0       # a real 3h capture is ~1 GB; a few MB or less = died early / degenerate
ACK_FILE = os.path.join(ROOT, "scripts", "capture_audit_baseline.json")


def _ack_key(kickoff) -> str:
    """Stable identity for a fixture across bracket-placeholder renames: kickoff to the minute (UTC)."""
    return kickoff.isoformat()[:16]


def _load_ack() -> dict:
    """{kickoff_key: note} of acknowledged, unrecoverable misses. Absent/broken file = no acks."""
    try:
        with open(ACK_FILE) as fh:
            return json.load(fh).get("acknowledged", {}) or {}
    except (FileNotFoundError, ValueError):
        return {}


def _norm(s: str) -> str:
    """lowercase, drop accents and non-alphanumerics, for loose team<->tape-slug matching."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return "".join(c for c in s.lower() if c.isalnum())


def _tape_mb(team1: str, team2: str) -> float | None:
    """Size (MB) of this match's events tape if still on disk, else None (cleaned at 48h is fine)."""
    t1, t2 = _norm(team1), _norm(team2)
    for path in glob.glob(os.path.join(DATA_DIR, "ws-events-*.jsonl")):
        slug = _norm(os.path.basename(path))
        if t1 in slug and t2 in slug:
            return os.path.getsize(path) / 1e6
    return None


def audit() -> dict:
    now = datetime.now(timezone.utc)
    fixtures = load_fixtures()
    state = _load_state()
    acked = _load_ack()
    rows, missed_new, missed_ack, degraded = [], [], [], []
    counts = {"captured": 0, "missed": 0, "missed_new": 0, "missed_ack": 0, "in_window": 0, "upcoming": 0}
    for f in fixtures:
        dt = (f["kickoff"] - now).total_seconds()
        match = f"{f['team1']} vs {f['team2']}"
        if f["key"] in state:
            st = state[f["key"]]
            mk = st.get("markets", {}) or {}
            single = not (mk.get("kalshi") and mk.get("poly"))
            mb = _tape_mb(f["team1"], f["team2"])
            small = mb is not None and mb < MIN_TAPE_MB
            counts["captured"] += 1
            tags = []
            if single:
                tags.append("SINGLE-VENUE")
            if small:
                tags.append(f"TINY-TAPE({mb:.1f}MB)")
            status = "captured" + (" · " + ", ".join(tags) if tags else "")
            if tags:
                degraded.append((match, tags))
        elif dt > LEAD_S:
            counts["upcoming"] += 1
            status = "upcoming"
        elif dt > -GRACE_S:
            counts["in_window"] += 1
            status = "in-window (launch pending)"
        else:
            counts["missed"] += 1
            if _ack_key(f["kickoff"]) in acked:
                counts["missed_ack"] += 1
                status = "MISSED · acknowledged historical loss"
                missed_ack.append((match, f["kickoff"]))
            else:
                counts["missed_new"] += 1
                status = "MISSED — kickoff passed, never launched"
                missed_new.append((match, f["kickoff"]))
        rows.append({"match": match, "kickoff": f["kickoff"].isoformat(), "dt_h": round(dt / 3600, 1),
                     "status": status})
    return {"now": now.isoformat(), "counts": counts, "rows": rows,
            "missed_new": [{"match": m, "kickoff": k.isoformat()} for m, k in missed_new],
            "missed_ack": [{"match": m, "kickoff": k.isoformat()} for m, k in missed_ack],
            "degraded": [{"match": m, "tags": t} for m, t in degraded]}


def acknowledge() -> int:
    """Add every currently-unacknowledged miss to the baseline, then require commit+deploy to persist."""
    a = audit()
    if not a["missed_new"]:
        print("no new (unacknowledged) misses to acknowledge.")
        return 0
    try:
        with open(ACK_FILE) as fh:
            doc = json.load(fh)
    except (FileNotFoundError, ValueError):
        doc = {"acknowledged": {}}
    doc.setdefault("acknowledged", {})
    for m in a["missed_new"]:
        key = m["kickoff"][:16]
        doc["acknowledged"][key] = f"{m['match']} - acknowledged {a['now'][:10]} as unrecoverable"
        print(f"  + acknowledged {key}Z  {m['match']}")
    with open(ACK_FILE, "w") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    print(f"\nwrote {len(a['missed_new'])} acknowledgement(s) to {os.path.relpath(ACK_FILE, ROOT)}"
          "\n-> commit + deploy this file so the baseline persists (VM copy is rsync-overwritten otherwise).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="audit WC match capture for silent misses")
    ap.add_argument("--json", action="store_true", help="emit a machine-readable status line")
    ap.add_argument("--ack", action="store_true", help="acknowledge current misses into the baseline")
    args = ap.parse_args()
    if args.ack:
        return acknowledge()
    a = audit()
    c = a["counts"]
    if args.json:
        print(json.dumps({"counts": c, "missed_new": a["missed_new"],
                          "missed_ack": a["missed_ack"], "degraded": a["degraded"]}))
        return 1 if c["missed_new"] else 0

    print(f"capture audit · {a['now'][:16]}Z · {c['captured']} captured · "
          f"{c['missed_new']} NEW MISS · {c['missed_ack']} acknowledged · "
          f"{c['in_window']} in-window · {c['upcoming']} upcoming")
    # show played fixtures (captured/missed/in-window) and the next few upcoming
    for r in a["rows"]:
        if r["status"].startswith("upcoming") and r["dt_h"] > 12:
            continue                                   # don't spam far-future fixtures
        if "acknowledged" in r["status"]:
            mark = "⊘"                                 # known, acknowledged historical loss (not an alarm)
        elif "MISSED" in r["status"]:
            mark = "✗"                                 # NEW miss
        elif "SINGLE" in r["status"] or "TINY" in r["status"]:
            mark = "!"
        else:
            mark = "·"
        print(f"  {mark} {r['kickoff'][:16]}Z  {r['match']:<34} {r['status']}")
    if a["missed_new"]:
        print(f"\n  *** {len(a['missed_new'])} NEW MISS(ES) — not recoverable, the game is gone ***")
        print("      review, and if truly unrecoverable, acknowledge with `capture_audit.py --ack`")
    else:
        tail = f" ({c['missed_ack']} acknowledged historical, baseline)" if c["missed_ack"] else ""
        if a["degraded"]:
            print(f"\n  no new misses{tail}. {len(a['degraded'])} degraded capture(s) (single-venue/tiny).")
        else:
            print(f"\n  all played fixtures captured cleanly — no new misses{tail}.")
    return 1 if c["missed_new"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
