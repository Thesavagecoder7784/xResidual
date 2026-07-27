#!/usr/bin/env python3
"""Which venue tracked the sharp line more closely — recomputed at frozen as-of dates.

    python scripts/basis_asof_sweep.py [--snapshots GLOB]

`build_basis.py` reports the LATEST quote per venue/team, which is the right thing during the
tournament and a degenerate thing after it: once the title market resolves, Kalshi's field sums to
~24x and the mean-absolute-gap comparison is meaningless. Two published notes disagreed on the
answer (~0.12pp vs ~0.16pp in one, ~0.18pp vs ~0.26pp in another) and neither was backed by a
committed artifact, so the claim was pulled from the flagship note and the manuscript.

This settles it by replaying the logged snapshots with an as-of cutoff, which recovers what the
comparison actually looked like while the market was live, and shows whether the answer is stable
across the tournament or an artifact of the day it was read. Emits
writeups/_basis_asof_sweep.json so the claim can be quoted from a versioned artifact or,
if the sweep shows it is unstable, stay retired on the record.

Reads snapshots only; edits nothing under xresidual/.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_basis as bb  # noqa: E402  reuse the published estimator verbatim

OUT = os.path.join(ROOT, "writeups", "_basis_asof_sweep.json")
# Cutoffs are inclusive upper bounds on ts_utc: each row is "the market as it stood then". The
# first three sit in the pre-tournament BUILDUP, which is the window _frozen_observations.json's
# overround values were taken in — including them lets those frozen numbers be checked rather than
# trusted (Polymarket's overround compresses from ~3% in the buildup to <1% by mid-group-stage, so
# a sweep that starts at kickoff makes the frozen 3.0% look wrong when it is simply earlier).
CUTOFFS = ["2026-06-06", "2026-06-08", "2026-06-10",
           "2026-06-15", "2026-06-22", "2026-06-29", "2026-07-06", "2026-07-13", "2026-07-18"]


def load_series(pattern, cutoffs):
    """One chronological pass -> {cutoff: rows-as-of}. The estimator only needs the LATEST quote
    per venue/team, so instead of re-reading ~1 GB of snapshots once per cutoff we walk the files in
    date order and snapshot the accumulated rows each time a cutoff is passed."""
    files = []
    for fp in glob.glob(pattern):
        day = os.path.basename(fp).replace("snapshots-", "").replace(".jsonl", "")
        if len(day) == 10:
            files.append((day, fp))
    files.sort()
    out, acc, pending = {}, [], sorted(cutoffs)
    for day, fp in files:
        while pending and day > pending[0]:
            out[pending.pop(0)] = list(acc)
        with open(fp) as f:
            for line in f:
                try:
                    acc.append(json.loads(line))
                except Exception:  # noqa: BLE001 — a torn final line must not kill the sweep
                    continue
    for c in pending:
        out[c] = list(acc)
    return out


def at(rows):
    """The published estimator, on a frozen row set -> (n_anchored, pm_mae, ka_mae, overrounds)."""
    pm_raw = bb.latest_winner(rows, "polymarket")
    ka_raw = bb.latest_winner(rows, "kalshi")
    sharp_raw = bb.latest_sharp(rows)
    if not (pm_raw and ka_raw and sharp_raw):
        return None
    pm, or_pm = bb.devig(pm_raw)
    ka, or_ka = bb.devig(ka_raw)
    sharp, _ = bb.devig(sharp_raw)
    anchored = [t for t in (set(pm) & set(ka)) if t in sharp]
    if len(anchored) < 20:
        return None
    pm_mae = sum(abs(pm[t] - sharp[t]) for t in anchored) / len(anchored) * 100
    ka_mae = sum(abs(ka[t] - sharp[t]) for t in anchored) / len(anchored) * 100
    pm_closer = sum(1 for t in anchored if abs(pm[t] - sharp[t]) < abs(ka[t] - sharp[t]))
    gap = sum(abs(pm[t] - ka[t]) for t in anchored) / len(anchored) * 100
    # Per-team detail, so the "widest standing gap is England (~1pp)" and the home-crowd-tilt team
    # lists in the notes stop being unsourced prose. Sign convention: positive = Kalshi prices the
    # team RICHER than Polymarket, which is the direction the American-book tilt should show up in.
    tilt = sorted(((t, (ka[t] - pm[t]) * 100) for t in anchored), key=lambda kv: -kv[1])
    widest = max(anchored, key=lambda t: abs(ka[t] - pm[t]))
    return {"n_teams": len(anchored), "pm_mae_pp": round(pm_mae, 3), "ka_mae_pp": round(ka_mae, 3),
            "widest_gap_team": widest, "widest_gap_pp": round(abs(ka[widest] - pm[widest]) * 100, 3),
            "kalshi_richer_top": [[t, round(v, 3)] for t, v in tilt[:4]],
            "poly_richer_top": [[t, round(-v, 3)] for t, v in tilt[-4:][::-1]],
            "closer": "Polymarket" if pm_mae < ka_mae else "Kalshi",
            "pm_closer_on": pm_closer, "ka_closer_on": len(anchored) - pm_closer,
            "cross_venue_gap_pp": round(gap, 3),
            "overround_poly_pct": round((or_pm - 1) * 100, 2),
            "overround_kalshi_pct": round((or_ka - 1) * 100, 2)}


def main() -> int:
    ap = argparse.ArgumentParser(description="replay the venue-vs-sharp comparison at frozen dates")
    ap.add_argument("--snapshots", default=bb.DATA_GLOB,
                    help="glob for snapshots-*.jsonl (point at the VM backup for full coverage)")
    args = ap.parse_args()

    by_cutoff = load_series(args.snapshots, CUTOFFS)
    series = {}
    for c in CUTOFFS:
        r = at(by_cutoff.get(c, []))
        series[c] = r
        if r:
            print(f"  {c}  n={r['n_teams']:>2}  PM {r['pm_mae_pp']:.3f}pp vs KA {r['ka_mae_pp']:.3f}pp"
                  f"  -> {r['closer']} closer (on {r['pm_closer_on']}/{r['ka_closer_on']} teams)"
                  f"  · cross-venue gap {r['cross_venue_gap_pp']:.3f}pp")
        else:
            print(f"  {c}  insufficient coverage")

    got = [v for v in series.values() if v]
    verdict = None
    if got:
        winners = {v["closer"] for v in got}
        verdict = ("stable: " + winners.pop()) if len(winners) == 1 else \
                  "UNSTABLE: the closer venue flips across as-of dates"
    out = {"source_glob": args.snapshots, "estimator":
           "build_basis.latest_winner/latest_sharp + multiplicative de-vig, replayed with an "
           "as-of cutoff; mean |venue - Betfair| across teams quoted by all three",
           "series": series, "verdict": verdict}
    json.dump(out, open(OUT, "w"), indent=1)
    print(f"\nverdict: {verdict}")
    print(f"wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
