#!/usr/bin/env python3
"""Assemble model-vs-market pairs across every WC market layer and scan for mispricing.

Reuses the (model, market) probabilities we already generate (_groupsim, _knockout,
_elimination) and runs xresidual.mispricing to produce (a) the ranked current edges and
(b) the favourite-longshot TERM STRUCTURE — the bias by market layer, ordered from the
deep liquid markets (efficient) to the thin structural ones (soft). Writes
viz/model/_mispricing.js.

    python scripts/build_mispricing.py
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import mispricing  # noqa: E402

VIZ = os.path.join(ROOT, "viz", "model")
OUT = os.path.join(VIZ, "_mispricing.js")

# layer -> liquidity/depth rank (5 = deepest & most liquid, 1 = thinnest & newest)
DEPTH = {"winner": 5, "advance-R32": 4, "reach-QF": 3, "reach-SF": 2, "elim-champion": 1}

# Per-layer verdict — what the model-vs-market gap actually means, after adjudication.
# The advance-R32 gap was checked against an INDEPENDENT third source (bookmaker h2h):
# bookmakers rate the minnows higher than our model too, so that gap is our model being
# too harsh on minnow advancement, NOT market softness. The deep-run favourite-overpricing
# is genuine but partly our model running low on a few favourites even in the liquid market.
VERDICT = {
    "winner":       ("efficient",        "model agrees with the sharp market (±0.4pp)"),
    "advance-R32":  ("our model, not the market", "bookmakers + Polymarket agree against us — model under-rates minnow advancement"),
    "reach-QF":     ("thin-market softness", "favourites overpriced on deep runs (partly model tilt)"),
    "reach-SF":     ("thin-market softness", "favourites overpriced on deep runs (partly model tilt)"),
    "elim-champion":("thinnest market",    "favourite/champion overpricing (#11), partly model tilt"),
}


def _load(name):
    p = os.path.join(VIZ, name)
    return json.loads(open(p, encoding="utf-8").read().split("=", 1)[1].rstrip().rstrip(";"))


def build_contracts() -> list[dict]:
    ko = _load("_knockout.js")["reach"]
    gs = _load("_groupsim.js")["groups"]
    el = {t["team"]: t for t in _load("_elimination.js")["teams"]}
    C = []
    for r in ko:
        t, m, k = r["team"], r["model"], r["market"]
        if k:
            C.append({"layer": "winner", "team": t, "model": m["win"], "market": k.get("win")})
            C.append({"layer": "reach-QF", "team": t, "model": m["qf"], "market": k.get("qf")})
            C.append({"layer": "reach-SF", "team": t, "model": m["sf"], "market": k.get("sf")})
    for L in gs:
        for x in gs[L]:
            C.append({"layer": "advance-R32", "team": x["team"], "model": x["padv"], "market": x.get("mkt")})
    for t, e in el.items():
        C.append({"layer": "elim-champion", "team": t,
                  "model": e["model"].get("champion"), "market": e["market"].get("champion")})
    return C


def main() -> int:
    scanned = mispricing.scan(build_contracts())
    ts = sorted(mispricing.term_structure(scanned), key=lambda r: -DEPTH.get(r["layer"], 0))
    for r in ts:                                # attach depth + adjudicated verdict
        r["depth"] = DEPTH.get(r["layer"], 0)
        r["verdict"], r["verdict_note"] = VERDICT.get(r["layer"], ("", ""))
    edges = mispricing.top_edges(scanned, n=8)

    print("=== FLB term structure (deep/liquid -> thin/structural) ===")
    print(f"{'layer':<14}{'depth':>6}{'n':>4}{'|gap|':>7}{'fav_gap':>9}{'longshot_gap':>14}{'FLB spread':>12}")
    for r in ts:
        print(f"{r['layer']:<14}{DEPTH.get(r['layer'],0):>6}{r['n']:>4}{r['mean_abs_gap']:>7}"
              f"{str(r['fav_gap']):>9}{str(r['longshot_gap']):>14}{str(r['flb_spread']):>12}")
    print("\n  read: fav_gap<0 = favourites overpriced, longshot_gap>0 = longshots underpriced;")
    print("  FLB spread ~0 in the deep markets, growing into the thin ones = the bias term structure.")

    # the same event, two markets: 'champion' in the liquid winner market vs the thin elimination market
    win = {c["team"]: c for c in scanned if c["layer"] == "winner"}
    elim = {c["team"]: c for c in scanned if c["layer"] == "elim-champion"}
    print("\n=== same event (CHAMPION), two markets: liquid winner-market gap vs thin elimination-market gap ===")
    print(f"{'team':<12}{'winner gap':>11}{'elim gap':>10}")
    for t in sorted(win, key=lambda t: -elim.get(t, {}).get("market", 0))[:6]:
        if t in elim:
            print(f"{t:<12}{win[t]['gap']:>+11.2f}{elim[t]['gap']:>+10.2f}")

    print("\n=== top current edges (host-confounded excluded) ===")
    print("BACK (model > market, underpriced):")
    for c in edges["backs"]:
        print(f"  {c['team']:<12} {c['layer']:<14} model {c['model']:.1f} vs mkt {c['market']:.1f}  (+{c['gap']:.1f})")
    print("FADE (model < market, overpriced):")
    for c in edges["fades"]:
        print(f"  {c['team']:<12} {c['layer']:<14} model {c['model']:.1f} vs mkt {c['market']:.1f}  ({c['gap']:.1f})")

    payload = {"term_structure": ts, "depth": DEPTH, "edges": edges,
               "n_contracts": len(scanned)}
    os.makedirs(VIZ, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.MISPRICING = " + json.dumps(payload) + ";\n")
    print(f"\nwrote {os.path.relpath(OUT, ROOT)} ({len(scanned)} contracts across {len(ts)} layers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
