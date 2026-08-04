#!/usr/bin/env python3
"""Is the harvestability gate measuring the follower's actual problem? (section 6.2)
    -> writeups/_depth_instant_results.json

    python scripts/depth_instant.py --data-dir ~/xResidual-vm-backup/logger-data
    python scripts/depth_instant.py --check    # verify against the shipped artifact

WHY THIS EXISTS. The ledger gates harvestability on TROUGH depth: the minimum top-of-book size
over a window running 1s before to 4s after the shock, divided by the pre-goal median
(build_harvest.py, SPREAD_WIN). A referee's obvious objection is that this is not the
follower's problem. The follower acts at the signal, somewhere in [0, +600ms]; a book that is
full at t=0 and empties at t=+2.5s is tradeable but scores as collapsed under a trough taken
over five seconds. The paper concedes the statistic is "systematically the harsher of the two"
and then sweeps the THRESHOLD (25% -> 1%) rather than the STATISTIC, which does not answer it.

WHAT THIS DOES. Recomputes the ledger on the raw tapes with four depth statistics side by side:

    trough    min depth over [-1s, +4s]        (the published statistic)
    at_zero   depth at the anchor instant      (last known top-of-book at t=0)
    win_min   min depth over [0, +600ms]       (worst case inside the follower's window)
    win_med   median depth over [0, +600ms]    (typical case inside it)

and records WHERE the trough falls (`trough_offset_ms`). The claim the paper needs is that the
trough sits inside the follower's window, so the two statistics are measuring one regime and the
distinction is immaterial. That is a testable claim, and this tests it rather than asserting it.

COVERAGE, STATED UP FRONT. Complete raw tapes survive for three matches only (the collection
host was decommissioned; see Data availability). This is therefore a book-reconstruction
VALIDATION of the depth statistic on the only captures where reconstruction is possible, not a
re-estimate of the ledger, and it is reported as such. The three are not adversely selected for
the purpose: they are among the most liquid matches of the tournament, so they are where a
follower is MOST likely to find resting size. Finding none there is the strong version of the
null; finding some would bound the published claim, which is why the test is worth running.

Everything else -- event detection, the consensus-mid jump filter, the follower assignment, the
pre-goal baseline -- is imported from or mirrors build_harvest.py exactly, so the `trough`
column is a regression test on this script: it must reproduce the shipped per-match archives.

Reads tapes read-only. Writes nothing under xresidual/ and mutates no archive.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import statistics as st
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import ws_events as we                  # noqa: E402
import stream_micro as sm                              # noqa: E402
from build_liquidity import detect_shocks              # noqa: E402
from build_harvest import (MIN_JUMP, PRE, POST, REACT_WIN, SPREAD_WIN,  # noqa: E402
                           fee, _win_med, _react_time, _spread_med)

OUT = os.path.join(ROOT, "writeups", "_depth_instant_results.json")
DEFAULT_DATA = os.path.join(ROOT, "logger", "data")

FOLLOWER_WIN = (0, 600)    # the interval in which a follower could actually transact
BUILD_GATE = 0.25          # build_harvest.py summ(): harvestable requires depth_frac >= 0.25


def depth_stats(ftob, t):
    """The four depth statistics for one shock, all sharing the same pre-goal denominator."""
    dep = lambda r: (r["bid_sz"] or 0.0) + (r["ask_sz"] or 0.0)
    pre = [dep(r) for r in ftob if t + PRE[0] <= r["t"] <= t + PRE[1]]
    if not pre or st.median(pre) <= 0:
        return None
    base = st.median(pre)

    trough_rows = [(r["t"] - t, dep(r)) for r in ftob
                   if t + SPREAD_WIN[0] <= r["t"] <= t + SPREAD_WIN[1]]
    win_rows = [dep(r) for r in ftob
                if t + FOLLOWER_WIN[0] <= r["t"] <= t + FOLLOWER_WIN[1]]
    # Last top-of-book at or before the anchor: what a follower would see the instant it fires.
    at_zero = None
    for r in ftob:
        if r["t"] <= t:
            at_zero = dep(r)
        else:
            break
    if not trough_rows:
        return None

    off, trough = min(trough_rows, key=lambda x: x[1])
    return {
        "trough": trough / base,
        "trough_offset_ms": off,
        "at_zero": (at_zero / base) if at_zero is not None else None,
        "win_min": (min(win_rows) / base) if win_rows else None,
        "win_med": (st.median(win_rows) / base) if win_rows else None,
        "n_win_obs": len(win_rows),
    }


def process(cap, data_dir):
    pairs = we.load_pairs(data_dir, capture=cap)
    path = os.path.join(data_dir, f"ws-events-{cap}.jsonl")
    if not pairs or not os.path.exists(path):
        return None
    bundle = sm.stream_all(path, pairs)
    rows = []
    for pr in pairs:
        kt, pa = pr.get("kalshi"), pr.get("poly")
        if not kt or not pa:
            continue
        km, pm = bundle["k_mid"].get(kt, []), bundle["p_mid"].get(pa, [])
        ktob, ptob = bundle["k_tob"].get(kt, []), bundle["p_tob"].get(pa, [])
        if len(km) < 20 or len(pm) < 20:
            continue
        for t in detect_shocks(pm):
            pre_k, pre_p = _win_med(km, t + PRE[0], t + PRE[1]), _win_med(pm, t + PRE[0], t + PRE[1])
            post_k, post_p = _win_med(km, t + POST[0], t + POST[1]), _win_med(pm, t + POST[0], t + POST[1])
            if None in (pre_k, pre_p, post_k, post_p):
                continue
            pre_c, post_c = (pre_k + pre_p) / 2, (post_k + post_p) / 2
            gross = abs(post_c - pre_c)
            if gross < MIN_JUMP:
                continue
            rk = _react_time(km, pre_k, t + REACT_WIN[0], t + REACT_WIN[1])
            rp = _react_time(pm, pre_p, t + REACT_WIN[0], t + REACT_WIN[1])
            if rk is None or rp is None:
                continue
            foll, ftob = ("kalshi", ktob) if rp <= rk else ("poly", ptob)
            spr = _spread_med(ftob, t + SPREAD_WIN[0], t + SPREAD_WIN[1])
            if spr is None or spr <= 0:
                continue
            d = depth_stats(ftob, t)
            if d is None:
                continue
            net = gross - (spr / 2.0 + fee(foll, post_c))
            rows.append({"follower": foll, "net": net, **d})
    return rows


def summarise(rows):
    """Harvestable share under each statistic, on identical events. `trough` must reproduce the
    shipped archives; the other three are the answer to the objection."""
    out = {}
    for key in ("trough", "at_zero", "win_min", "win_med"):
        usable = [r for r in rows if r.get(key) is not None]
        if not usable:
            out[key] = None
            continue
        harv = sum(1 for r in usable if r["net"] > 0 and r[key] >= BUILD_GATE)
        out[key] = {
            "n": len(usable),
            "median_depth_frac": round(st.median(r[key] for r in usable), 4),
            "pct_harvestable": round(harv / len(usable) * 100, 1),
        }
    # STALENESS DIAGNOSTIC. at_zero and win_* read the last OBSERVED top-of-book. If the
    # follower's venue has not messaged an update inside the window, that reading is the
    # pre-goal book still standing on the tape, not size known to be there -- so these
    # statistics can only over-state what is available. Counting the updates is what
    # separates "depth was there" from "we had not yet been told it was gone".
    nobs = [r.get("n_win_obs", 0) for r in rows]
    out["window_updates"] = {
        "n": len(nobs),
        "median_updates_in_window": int(st.median(nobs)),
        "pct_no_update_in_window": round(sum(1 for v in nobs if v == 0) / len(nobs) * 100, 1),
        "pct_one_or_fewer": round(sum(1 for v in nobs if v <= 1) / len(nobs) * 100, 1),
    }
    offs = [r["trough_offset_ms"] for r in rows]
    out["trough_timing"] = {
        "n": len(offs),
        "median_offset_ms": int(st.median(offs)),
        # The claim to test: does the trough land inside the window the follower could act in?
        "pct_within_follower_window": round(
            sum(1 for o in offs if FOLLOWER_WIN[0] <= o <= FOLLOWER_WIN[1]) / len(offs) * 100, 1),
        "pct_within_1s": round(sum(1 for o in offs if o <= 1000) / len(offs) * 100, 1),
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=DEFAULT_DATA,
                    help="directory holding ws-events-*.jsonl and ws-pairs-*.jsonl")
    ap.add_argument("--check", action="store_true",
                    help="compare against the shipped artifact; write nothing")
    args = ap.parse_args()
    data_dir = os.path.expanduser(args.data_dir)

    caps = sorted(os.path.basename(p)[len("ws-events-"):-len(".jsonl")]
                  for p in glob.glob(os.path.join(data_dir, "ws-events-*.jsonl")))
    if not caps:
        print(f"  !! no raw tapes in {data_dir} — nothing to reconstruct")
        return 1
    print(f"  raw tapes found: {len(caps)}")

    all_rows, per_match = [], {}
    for cap in caps:
        rows = process(cap, data_dir)
        if not rows:
            print(f"  skip {cap}: no qualifying shocks")
            continue
        per_match[cap] = summarise(rows)
        all_rows.extend(rows)
        s = per_match[cap]
        print(f"  {cap[:42]:<44} {len(rows):3d} obs · trough {s['trough']['pct_harvestable']:5.1f}%"
              f" · at_zero {s['at_zero']['pct_harvestable'] if s['at_zero'] else float('nan'):5.1f}%"
              f" · win_med {s['win_med']['pct_harvestable'] if s['win_med'] else float('nan'):5.1f}%")

    if not all_rows:
        print("  !! no qualifying shocks on any tape")
        return 1

    payload = {
        "n_tapes": len(per_match),
        "n_observations": len(all_rows),
        "follower_window_ms": list(FOLLOWER_WIN),
        "trough_window_ms": list(SPREAD_WIN),
        "depth_gate": BUILD_GATE,
        "pooled": summarise(all_rows),
        "per_capture": per_match,
        "note": ("book-reconstruction validation of the depth statistic on the only captures for "
                 "which complete raw tapes survive; NOT a re-estimate of the ledger. Event "
                 "detection, jump filter, follower assignment and pre-goal baseline are "
                 "build_harvest.py's. The 'trough' column is the published statistic and serves "
                 "as this script's regression test."),
    }
    p = payload["pooled"]
    print(f"\n  pooled over {payload['n_observations']} observations on {payload['n_tapes']} tapes")
    for key in ("trough", "at_zero", "win_min", "win_med"):
        s = p[key]
        if s:
            print(f"    {key:<9} median depth {s['median_depth_frac']:.4f} of calm"
                  f" · harvestable {s['pct_harvestable']:.1f}%  (n={s['n']})")
    tt = p["trough_timing"]
    print(f"    trough lands at a median {tt['median_offset_ms']}ms;"
          f" {tt['pct_within_follower_window']}% inside the follower window,"
          f" {tt['pct_within_1s']}% within 1s")

    if args.check:
        shipped = json.load(open(OUT))
        bad = [k for k, v in payload.items() if k != "note" and shipped.get(k) != v]
        for k in bad:
            print(f"  !! {k} differs")
        print("  " + ("CHECK CLEAN — regenerates the shipped artifact exactly"
                      if not bad else f"{len(bad)} FIELD(S) DIFFER"))
        return 1 if bad else 0

    with open(OUT, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"  wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
