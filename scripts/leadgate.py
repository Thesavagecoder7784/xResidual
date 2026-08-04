#!/usr/bin/env python3
"""Co-movement gate sensitivity for the lead-lag result.
    -> writeups/_leadgate_results.json

    python scripts/leadgate.py --check     # verify against the shipped artifact, write nothing
    python scripts/leadgate.py             # regenerate from the per-game leadlag archives

WHY THIS EXISTS. This artifact was produced ad-hoc and no generator was ever committed, so
three macros (nEventsThree, gateShareThree, gateEventsLong) sat outside the "regenerates with
one command" guarantee the paper makes. Same defect, and same fix, as scripts/harvest_ci.py.

WHAT IT ANSWERS. build_leadlag.py admits an event when the two venues co-move with best
cross-correlation >= 0.5 at a lag of <= 8 s. Eight seconds is permissive, so the fair question
is whether the long-lag tail is carrying the result. This re-counts the which-venue-first
split at progressively tighter gates. The answer in the paper is that tightening the gate
RAISES Polymarket's share -- the tail dilutes the estimate rather than producing it, which is
why the loose gate is reported as the conservative choice.

Reads the derived per-game archives only. No tape, no venue data written.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEADLAG = os.path.join(ROOT, "viz", "market", "leadlag")
OUT = os.path.join(ROOT, "writeups", "_leadgate_results.json")

PUBLISHED_GATE_MS = 8000
GATES = (8000, 5000, 3000)
# Bucket edges. The first bucket is STRICTLY under 1 s: 12 events sit at exactly 1000 ms, and
# putting them in the 0-1s bucket instead moves the split 239/70 -> 251/58. Matching the
# shipped artifact pins the convention rather than leaving it to whoever reruns this.
BUCKETS = (("0_1s", lambda x: x < 1000),
           ("1_3s", lambda x: 1000 <= x <= 3000),
           ("beyond_3s", lambda x: x > 3000))


def events() -> list[tuple[str, str, float]]:
    """(match, leader, signed_lag_ms) for every DECISIVE event. Synchronous events carry no
    lead and are excluded, as in the pooled result."""
    out = []
    for f in sorted(glob.glob(os.path.join(LEADLAG, "*.json"))):
        try:
            d = json.load(open(f))
        except Exception:  # noqa: BLE001
            print(f"  ! unreadable, skipped: {os.path.basename(f)}")
            continue
        match = d.get("match") or os.path.basename(f)
        for p in d.get("pairs", []):
            for e in p.get("events", []):
                ld = e.get("lead")
                if not isinstance(ld, dict):
                    continue
                leader = str(ld.get("leader") or "").lower()
                lag = ld.get("best_lag_ms")
                if leader in ("polymarket", "kalshi") and lag is not None:
                    out.append((match, leader, float(lag)))
    return out


def at_gate(ev, gate_ms: int) -> dict:
    sub = [(m, ld, lag) for m, ld, lag in ev if abs(lag) <= gate_ms]
    poly = sum(1 for _, ld, _ in sub if ld == "polymarket")
    kal = len(sub) - poly
    by = {}
    for m, ld, _ in sub:
        p, k = by.get(m, (0, 0))
        by[m] = (p + (ld == "polymarket"), k + (ld == "kalshi"))
    lean = [(p > k) - (p < k) for p, k in by.values()]
    npos = sum(1 for x in lean if x > 0)
    n_used = npos + sum(1 for x in lean if x < 0)
    med = st.median([abs(lag) for _, ld, lag in sub if ld == "polymarket"]) if poly else None
    return {
        "n_events": len(sub),
        "poly_share": round(poly / len(sub), 4) if sub else None,
        # Median lead is CONDITIONAL on Polymarket leading, matching the manuscript's headline.
        "median_lead_ms": med,
        "per_match": f"{npos} of {n_used}",
        "_kalshi_events": kal,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="compare to the shipped artifact; write nothing")
    args = ap.parse_args()

    ev = events()
    if not ev:
        print("  !! no leadlag archives found — nothing to compute")
        return 1
    lags = [abs(lag) for _, _, lag in ev]
    res = {
        "gate_ms_published": PUBLISHED_GATE_MS,
        "n_events_published": sum(1 for x in lags if x <= PUBLISHED_GATE_MS),
        "buckets": {name: sum(1 for x in lags if fn(x)) for name, fn in BUCKETS},
        "sensitivity": {f"{g}ms": at_gate(ev, g) for g in GATES},
        "note": ("co-movement gate sensitivity: which-venue-first split re-counted at tighter "
                 "lag gates, from the per-game leadlag archives. median_lead_ms is conditional "
                 "on Polymarket leading, as in the manuscript."),
    }
    for g in GATES:
        s = res["sensitivity"][f"{g}ms"]
        print(f"  gate {g:>5}ms  n={s['n_events']:>4}  poly={s['poly_share']}  "
              f"median_lead={s['median_lead_ms']}  per-match {s['per_match']}")
    print(f"  buckets: {res['buckets']}")

    if args.check:
        shipped = json.load(open(OUT))
        bad = []
        for g in GATES:
            k = f"{g}ms"
            for fld in ("n_events", "poly_share"):
                a, b = shipped["sensitivity"].get(k, {}).get(fld), res["sensitivity"][k][fld]
                if a != b:
                    bad.append(f"sensitivity.{k}.{fld}: shipped={a} fresh={b}")
        for name in ("beyond_3s", "0_1s", "1_3s"):
            a, b = shipped["buckets"].get(name), res["buckets"][name]
            if a != b:
                bad.append(f"buckets.{name}: shipped={a} fresh={b}")
        if shipped.get("n_events_published") != res["n_events_published"]:
            bad.append("n_events_published differs")
        for b in bad:
            print("  !!", b)
        print("  " + ("CHECK CLEAN — regenerates the shipped artifact exactly"
                      if not bad else f"{len(bad)} FIELD(S) DIFFER"))
        return 1 if bad else 0

    with open(OUT, "w") as fh:
        json.dump(res, fh, indent=1)
    print(f"  wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
