#!/usr/bin/env python3
"""One-command rebuild of the whole visualization pipeline.

    python scripts/build_all.py                # rebuild every _*.js, then render every card
    python scripts/build_all.py --offline      # skip the two network builders (forecast, on-chain)
    python scripts/build_all.py --data-only     # regenerate _*.js, don't render PNGs
    python scripts/build_all.py --render-only    # re-render PNGs from existing _*.js
    python scripts/build_all.py --models-only    # just the model/ pipeline (offline)
    python scripts/build_all.py --markets-only   # just the market/ pipeline

The pipeline is: data builders (scripts/*.py -> viz/*/_*.js) then render (viz/render.sh
-> .png). Every step is continue-on-error, so one failed builder (e.g. a network hiccup
on a live feed) never blocks the rest, and the run ends with a pass/fail summary so a
partial rebuild is auditable. Cards that inline their own data (buildup_trajectory,
leadlag_tape) have no builder; they're rendered like any other.

Reproducibility: from a clean checkout with the logged snapshots present,
`python scripts/build_all.py` regenerates the entire viz/ surface.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (script, needs_network). Model builders are offline compute; most market builders
# read the logged JSONL snapshots (offline); only these two hit a live API at build time.
MODEL_BUILDERS = [
    ("build_group_sim.py", False),
    ("build_knockout.py", False),
    ("build_blend_check.py", False),
    ("build_collision.py", False),
    ("build_storylines.py", False),
    ("build_lenses.py", False),
    ("build_travel.py", False),
    ("build_heat.py", False),
    ("build_incentive.py", False),
    ("build_drawluck.py", False),
    ("build_mispricing.py", False),     # last: reads _groupsim/_knockout/_elimination
]
MARKET_BUILDERS = [
    ("pull_forecast_data.py", True),    # Polymarket Gamma (live)
    ("build_insight_data.py", False),
    ("build_money_map.py", False),
    ("build_flb_wedge.py", False),
    ("build_survival.py", False),
    ("build_basis.py", False),
    ("build_buildup_trajectory.py", False),
    ("build_onchain.py", True),         # Polymarket data-api (live)
]


def run(cmd, label):
    """Run a subprocess, stream nothing but a status line; return (ok, seconds)."""
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
        ok = r.returncode == 0
    except subprocess.TimeoutExpired:
        return False, time.time() - t0, "timeout"
    dt = time.time() - t0
    tail = "" if ok else (r.stderr.strip().splitlines() or ["?"])[-1][:140]
    return ok, dt, tail


def builders_for(args):
    sel = []
    if not args.markets_only:
        sel += [("model", s, n) for s, n in MODEL_BUILDERS]
    if not args.models_only:
        sel += [("market", s, n) for s, n in MARKET_BUILDERS]
    return sel


def cards_for(args):
    buckets = []
    if not args.markets_only:
        buckets.append("model")
    if not args.models_only:
        buckets.append("market")
    cards = []
    for b in buckets:
        d = os.path.join(ROOT, "viz", b)
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".html"):
                cards.append(f"{b}/{fn}")
    return cards


def main() -> int:
    ap = argparse.ArgumentParser(description="Rebuild all xResidual visualizations.")
    ap.add_argument("--offline", action="store_true", help="skip the live-network builders")
    ap.add_argument("--data-only", action="store_true", help="build _*.js, don't render")
    ap.add_argument("--render-only", action="store_true", help="render only, reuse _*.js")
    ap.add_argument("--models-only", action="store_true")
    ap.add_argument("--markets-only", action="store_true")
    args = ap.parse_args()

    results = []  # (kind, name, ok, secs, note)

    if not args.render_only:
        print("── building data (_*.js) " + "─" * 40)
        for kind, script, needs_net in builders_for(args):
            if needs_net and args.offline:
                print(f"  skip  {script}  (offline)")
                continue
            ok, dt, note = run([sys.executable, os.path.join("scripts", script)], script)
            mark = "ok " if ok else "FAIL"
            print(f"  {mark}  {script:<26} {dt:5.1f}s  {('' if ok else '· ' + note)}")
            results.append(("build", script, ok, dt, note))

    if not args.data_only:
        print("── rendering cards (.png) " + "─" * 39)
        render = os.path.join(ROOT, "viz", "render.sh")
        for card in cards_for(args):
            ok, dt, note = run(["bash", render, card], card)
            mark = "ok " if ok else "FAIL"
            print(f"  {mark}  {card:<34} {dt:5.1f}s  {('' if ok else '· ' + note)}")
            results.append(("render", card, ok, dt, note))

    # provenance + staleness: stamp the batch, and flag any card data older than a static
    # input it was built from (the "changed the model, forgot to regenerate a card" check).
    try:
        sys.path.insert(0, ROOT)
        from xresidual import provenance, group_sim, data as _data
        try:
            from blend import DEFAULT_W as _W
        except Exception:
            _W = None
        inputs = {
            "results": getattr(_data, "_CACHE_PATH",
                               os.path.join(ROOT, "data", "cache", "international_results.csv")),
            "fixtures": os.path.join(ROOT, "data", "wc2026_fixtures.csv"),
            "squad_values": os.path.join(ROOT, "scripts", "squad_values.py"),
        }
        viz = os.path.join(ROOT, "viz")
        changed = provenance.inputs_changed_since(viz, inputs)   # vs the PRIOR build's record
        prov = provenance.stamp(ROOT, inputs=inputs, params={
            "blend_w": _W, "sigma": group_sim.MODEL_SIGMA, "dc_rho": group_sim.DC_RHO})
        provenance.write_provenance(viz, prov)                   # then record this build
        if changed and not args.render_only:
            note = ", ".join(c["input"] for c in changed)
            print(f"provenance: viz/_provenance.js · git {prov['git']} · inputs changed since "
                  f"last build ({note}) — now rebuilt")
        else:
            print(f"provenance: viz/_provenance.js · git {prov['git']} · inputs unchanged")
    except Exception as e:
        print(f"provenance step skipped: {type(e).__name__}: {e}")

    n_ok = sum(1 for *_, ok, _, _ in results if ok)
    n_fail = len(results) - n_ok
    total = sum(dt for *_, dt, _ in results)
    print("─" * 64)
    print(f"done · {n_ok} ok · {n_fail} failed · {total:.0f}s total")
    if n_fail:
        print("failed:", ", ".join(name for _, name, ok, _, _ in results if not ok))
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
