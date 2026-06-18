#!/usr/bin/env python3
"""Single-parse driver for every tape-based microstructure pipeline.

    python scripts/build_micro_all.py            # process NEW tapes once, feed all pipelines, pool
    python scripts/build_micro_all.py --all      # re-process every WC tape present

Each ws-events tape is ~1.3 GB and parses to ~7 GB of dicts, so loading it is by far the most
expensive step. The individual builders (build_leadlag, overreaction_build, build_ofi_leadlag)
each load it themselves when run alone — fine standalone, wasteful in the sync where all three run
on the same tape. This driver loads each tape ONCE and hands the in-memory events to every pipeline
that still needs it (its per-game JSON is missing), then pools each archive. Three parses -> one.

The builders are unchanged as standalone tools; this only orchestrates them. Pure laptop job
(never the 900 MB VM). Fork-forward: edits nothing in xresidual/.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import ws_events as we  # noqa: E402
import stream_micro as sm              # noqa: E402  streaming single-pass reader (fits the 900 MB VM)
import build_leadlag as ll             # noqa: E402
import overreaction_build as ovr       # noqa: E402
import build_ofi_leadlag as ofi        # noqa: E402
import build_infoshare as ish          # noqa: E402
import build_livewp as lw              # noqa: E402

DATA_DIR = os.path.join(ROOT, "logger", "data")
# (module, per-game archive dir, label) — one entry per tape-consuming pipeline
PIPELINES = [(ll, ll.LEADLAG_DIR, "lead-lag"),
             (ovr, ovr.OVR_DIR, "overreaction"),
             (ofi, ofi.OFI_DIR, "OFI"),
             (ish, ish.IS_DIR, "info-share"),
             (lw, lw.LW_DIR, "live-WP")]


def _slug(cap: str) -> str:
    return cap.split("-", 1)[1] if "-" in cap else cap


def _has_json(d_dir: str, cap: str) -> bool:
    return os.path.exists(os.path.join(d_dir, _slug(cap) + ".json"))


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="single-parse driver for the tape microstructure pipelines")
    ap.add_argument("--all", action="store_true", help="re-run every pipeline on every WC tape present")
    args = ap.parse_args()
    for _, d, _ in PIPELINES:
        os.makedirs(d, exist_ok=True)

    caps = ll.wc_captures(DATA_DIR)
    parsed = 0
    for cap in caps:
        need = [(mod, lbl) for mod, d, lbl in PIPELINES if args.all or not _has_json(d, cap)]
        if not need:
            continue
        print(f"parsing {cap} once for: {', '.join(lbl for _, lbl in need)}")
        pairs = we.load_pairs(DATA_DIR, capture=cap)
        tape = os.path.join(DATA_DIR, f"ws-events-{cap}.jsonl")
        sm_bundle = sm.stream_all(tape, pairs)              # ONE streaming pass (~MB, not ~7 GB)
        for mod, lbl in need:
            try:
                mod.process_capture(cap, pairs=pairs, sm_bundle=sm_bundle)
            except Exception as e:                          # one pipeline failing must not lose the others
                print(f"  {lbl} failed on {_slug(cap)}: {e}")
        del sm_bundle
        parsed += 1
    if not parsed:
        print(f"no tapes need processing ({len(caps)} present, all archived); re-pooling.")

    # rebuild every pooled aggregate from the per-game archives (parses no tapes)
    for mod, _, lbl in PIPELINES:
        print(f"--- pool: {lbl} ---")
        mod.pool_from_archive()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
