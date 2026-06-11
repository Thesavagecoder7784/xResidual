#!/usr/bin/env python3
"""Overlay qualitative intel on model-vs-market gaps, and verify the open paper book.

    python scripts/intel_scan.py

The model is regime-blind (pure ratings/blend) and so is, to a degree, the liquid market.
Qualitative intel (a March-2026 coaching change, a confirmed injury, a player revolt) is
only an EDGE where it makes one of them provably wrong in a direction we can trade. This
pulls the model probability (from the joint sim) and the live Polymarket mid for the flagged
teams across advance / group-winner / reach-round / champion, prints the gap, and tags the
direction the intel predicts. Then it re-checks every open position against model + intel.

DISCRETIONARY COMMENTARY: the INTEL overlay is hand-curated, subjective judgement — NOT a
model output. The published forecasts (advance / group / bracket / champion) stand entirely
independent of it; this tool only *annotates* where intel might explain a model-vs-market gap.
Nothing here is committed to a ledger or shown on the site.

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
INTEL = {  # refreshed 2026-06-11 (kickoff day) from the deeper injury/coaching sweep
    "Brazil":      ("high", "Rodrygo ACL OUT (tournament), Estêvão hamstring doubtful, Neymar out for the opener vs a strong Morocco — model is squad-blind to all of it"),
    "Egypt":       ("high", "Salah (hamstring) doubtful — model is talisman-blind, so its advance optimism is overstated"),
    "Japan":       ("high", "Mitoma (hamstring) and Minamino (ACL) both OUT — two key attackers gone; fade the deep runs"),
    "Netherlands": ("high", "Xavi Simons (ACL) out and Timber out — a midfield/defence hit the model can't see"),
    "Morocco":     ("high", "new coach Ouahbi (Mar-2026), untested at senior level — but the defensive identity is player-driven, so milder than the headline"),
    "Spain":       ("neutral", "Yamal and N.Williams fit for the opener (maybe minutes-limited) — earlier injury-fade thesis resolved; model ~ correct"),
    "Senegal":     ("back", "2025 AFCON champions, in form — model's bullishness over the market is supported; Koulibaly thigh a mild doubt"),
    "Algeria":     ("back", "strong recent form under Petkovic (beat the Netherlands, drew Uruguay) — supports the model rating it above the market"),
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
    for L in {sim[wc2026_teams.canonical(t)]["group"] for t in INTEL if wc2026_teams.canonical(t) in sim}:
        gw.update({t: mid(q) for t, q in poly_quotes([f"world-cup-group-{L.lower()}-winner"]).items()})

    def line(team, mkt_name, model_p, mkt_p):
        if mkt_p is None:
            return f"    {mkt_name:<16} model {model_p*100:5.1f}%   market   n/a"
        gap = (model_p - mkt_p) * 100
        return f"    {mkt_name:<16} model {model_p*100:5.1f}%   market {mkt_p*100:5.1f}%   gap {gap:+5.1f}pp"

    print("\n================ INTEL-OVERLAID DIVERGENCE (model vs live Polymarket) ================")
    print("  [DISCRETIONARY COMMENTARY — hand-curated judgement, NOT model output. The published")
    print("   forecasts stand without it; this only annotates where intel might explain a gap.]")
    for team in INTEL:
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
            print(f"    >> intel reads the model too HIGH. Where market >= model it's a FADE candidate; "
                  f"where market <= model the price already discounts it.")
        elif d == "back":
            print(f"    >> intel SUPPORTS the model over the market — a BACK candidate where market < model.")
        else:
            print(f"    >> no live intel edge; model and market should roughly agree.")

    # full Group C picture (the book-relevant group)
    cL = sim[wc2026_teams.canonical("Brazil")]["group"]
    print(f"\n---- Group {cL} winner: model vs market (every team) ----")
    for t in sorted([x for x in sim if sim[x]["group"] == cL], key=lambda x: -sim[x]["p1"]):
        print(line(t, t, sim[t]["p1"], gw.get(t)))

    # systematic advance divergence across the whole field — the favorite-longshot check
    gaps = sorted(((sim[t]["padv"] * 100 - adv[t] * 100, t) for t in sim if adv.get(t) is not None),
                  key=lambda x: x[0])
    print("\n---- SYSTEMATIC advance divergence (model - market) — favorite-longshot check ----")
    print("  biggest FADES (market overprices a weak team's advance — classic longshot bias):")
    for g, t in gaps[:6]:
        print(f"    {g:+5.1f}pp  {t:<16} model {sim[t]['padv']*100:4.1f}  market {adv[t]*100:4.1f}")
    print("  biggest BACKS (model rates an in-form side above the market):")
    for g, t in sorted(gaps, reverse=True)[:6]:
        print(f"    {g:+5.1f}pp  {t:<16} model {sim[t]['padv']*100:4.1f}  market {adv[t]*100:4.1f}")

    # ---------------- verify the open paper book ----------------
    import json
    book = [p for p in json.load(open(os.path.join(ROOT, "paper", "positions.json"))) if p["status"] == "open"]
    print("\n================ OPEN POSITION CHECK (model + intel) ================")
    NOTE = {
        2: ("Germany NOT champion", "Germany has a Musiala-rhythm question -> mild SUPPORT for the NO"),
        3: ("Senegal advance", "Senegal are 2025 AFCON champions, in form -> SUPPORT"),
        4: ("Brazil NOT win Group C", "Brazil now missing Rodrygo (ACL) + Estêvão doubtful + Neymar (opener) -> SUPPORTS the NO"),
        6: ("Turkey reach QF", "no specific intel flag -> NEUTRAL, ride the model edge"),
    }
    for p in book:
        lbl, note = NOTE.get(p["id"], (p["market"], "no note"))
        print(f"  #{p['id']} {lbl:<26} entry {p['entry_price']:.2f}  -> {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
