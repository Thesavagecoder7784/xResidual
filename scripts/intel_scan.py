#!/usr/bin/env python3
"""Overlay qualitative intel on model-vs-market gaps, and verify the open paper book.

    python scripts/intel_scan.py

The model is regime-blind (pure ratings/blend) and so is, to a degree, the liquid market.
Qualitative intel (a March-2026 coaching change, a confirmed injury, a player revolt) is
only an EDGE where it makes one of them provably wrong in a direction we can trade. This
pulls the model probability (from the joint sim) and the live Polymarket mid for the flagged
teams across advance / group-winner / reach-round / champion, prints the gap, and tags the
direction the intel predicts. Then it re-checks every open position against model + intel.

PAPER ONLY (F-1). Market prices are live mids, not depth-aware.
"""
from __future__ import annotations

import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "logger"))
from xresidual import baseline, data, elo, group_sim, knockout, wc2026_teams  # noqa: E402
from blend import blended_ratings  # noqa: E402
from venue_prices import poly_quotes  # noqa: E402

FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")

# intel overlay: team -> (direction the intel pushes the TRUE prob vs a regime-blind model,
#                         one-line reason). 'high' = model/market likely too high (fade).
INTEL = {
    "Morocco": ("high", "new coach Mar-2026, never managed a senior side; model blind to it"),
    "Uruguay": ("high", "Bielsa player-revolt + lame-duck; milder, partly dated to 2024"),
    "Spain":   ("low_near", "Yamal hamstring, likely misses 1-2 group games (model full-strength)"),
    "Brazil":  ("mixed", "Ancelotti 1st WC + Neymar calf for opener; but group-rivals weaker"),
}


def mid(q):
    b, a = q
    return (b + a) / 2 if b is not None and a is not None else (a or b)


def main() -> int:
    print("building joint sim ...")
    res = elo.build_ratings(data.load_results())
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)
    fixtures = pd.read_csv(FIXTURES)
    sim, det = group_sim.simulate(fixtures, ratings, params, return_detail=True, sigma=group_sim.MODEL_SIGMA)
    reach = knockout.simulate(det, sim, ratings)["reach"]   # team -> {r16,qf,sf,final,win} in %

    # live Polymarket mids
    adv = {t: mid(q) for t, q in poly_quotes(["world-cup-team-to-advance-to-knockout-stages"]).items()}
    qf = {t: mid(q) for t, q in poly_quotes(["world-cup-nation-to-reach-quarterfinals"]).items()}
    sf = {t: mid(q) for t, q in poly_quotes(["world-cup-nation-to-reach-semifinals"]).items()}
    win = {t: mid(q) for t, q in poly_quotes(["world-cup-winner"]).items()}
    groups = {sim[t]["group"] for t in sim}
    gw = {}
    for L in {sim[wc2026_teams.canonical(t)]["group"] for t in ["Brazil", "Morocco", "Spain", "Uruguay"] if wc2026_teams.canonical(t) in sim}:
        gw.update({t: mid(q) for t, q in poly_quotes([f"world-cup-group-{L.lower()}-winner"]).items()})

    def line(team, mkt_name, model_p, mkt_p):
        if mkt_p is None:
            return f"    {mkt_name:<16} model {model_p*100:5.1f}%   market   n/a"
        gap = (model_p - mkt_p) * 100
        return f"    {mkt_name:<16} model {model_p*100:5.1f}%   market {mkt_p*100:5.1f}%   gap {gap:+5.1f}pp"

    print("\n================ INTEL-OVERLAID DIVERGENCE (model vs live Polymarket) ================")
    for team in ["Morocco", "Brazil", "Uruguay", "Spain"]:
        t = wc2026_teams.canonical(team)
        if t not in sim:
            continue
        d, why = INTEL[team]
        L = sim[t]["group"]
        print(f"\n{team}  (Group {L})  — intel: {why}")
        print(line(team, "advance", sim[t]["padv"], adv.get(t)))
        print(line(team, f"win Group {L}", sim[t]["p1"], gw.get(t)))
        print(line(team, "reach QF", reach[t]["qf"] / 100, qf.get(t)))
        print(line(team, "reach SF", reach[t]["sf"] / 100, sf.get(t)))
        print(line(team, "champion", reach[t]["win"] / 100, win.get(t)))
        # interpretation
        if d == "high":
            print(f"    >> intel says model is too HIGH here. Where market <= model, the market already "
                  f"discounts {team} (trust market); where market >= model, FADE candidate.")
        elif d == "low_near":
            print(f"    >> model is full-strength (Yamal-blind). If market still ~= model, market hasn't "
                  f"priced the injury -> near-term FADE on early matches; if market < model, already priced.")
        else:
            print(f"    >> mixed: own-team downside (opener) vs weaker group rivals. Group-win may run HIGHER than model.")

    # full Group C picture (the book-relevant group)
    cL = sim[wc2026_teams.canonical("Brazil")]["group"]
    print(f"\n---- Group {cL} winner: model vs market (every team) ----")
    for t in sorted([x for x in sim if sim[x]["group"] == cL], key=lambda x: -sim[x]["p1"]):
        print(line(t, t, sim[t]["p1"], gw.get(t)))

    # ---------------- verify the open paper book ----------------
    import json
    book = [p for p in json.load(open(os.path.join(ROOT, "paper", "positions.json"))) if p["status"] == "open"]
    print("\n================ OPEN POSITION CHECK (model + intel) ================")
    NOTE = {
        2: ("Germany NOT champion", "Germany has a Musiala-rhythm question -> mild SUPPORT for the NO"),
        3: ("Senegal advance", "Senegal are 2025 AFCON champions, in form -> SUPPORT"),
        4: ("Brazil NOT win Group C", "Morocco (main rival) destabilized -> Brazil more likely to win -> UNDERCUTS"),
        6: ("Turkey reach QF", "no specific intel flag -> NEUTRAL, ride the model edge"),
    }
    for p in book:
        lbl, note = NOTE.get(p["id"], (p["market"], "no note"))
        print(f"  #{p['id']} {lbl:<26} entry {p['entry_price']:.2f}  -> {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
