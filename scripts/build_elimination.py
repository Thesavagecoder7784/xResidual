#!/usr/bin/env python3
"""Stage-of-elimination: our model's 7-way distribution vs Polymarket's new market.

    python scripts/build_elimination.py

Polymarket now lists, per team, a "stage of elimination" event (group / R32 / R16 / QF /
SF / final / champion). Our tournament sim already produces the same distribution, so this:

  1. builds each team's model 7-way distribution from ONE consistent simulation
     (reach-R32 = group-stage P(advance); r16..win from the knockout sim, so differencing
     never goes negative),
  2. fetches the market, de-vigs it (the 7 mutually-exclusive Yes prices are normalised to
     sum to 1; the per-team raw sum is the overround),
  3. runs coherence checks the market can fail: per-team overround, the cross-team slot
     sums (sum of reach-R32 must be 32, R16 16, QF 8, SF 4, final 2, champion 1), and the
     champion leg vs the separate winner market,
  4. flags the biggest model-vs-market divergences as candidate mispricings,
  5. appends a timestamped snapshot of every leg to the logger so the series is captured.

Pro-market framing: a divergence is a candidate to investigate, not proof the market is
wrong. The coherence violations (sum != 1, slot sums off) are the cleaner signals.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import baseline, data, elo, group_sim, knockout, wc2026_teams as W  # noqa: E402
from pull_forecast_data import ISO, KIT, INK, ensure_flag, team_probs  # noqa: E402
from blend import blended_ratings  # noqa: E402
from prediction_board import wc_played_results  # noqa: E402

OUT = os.path.join(ROOT, "viz", "model", "_elimination.js")
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
SNAP = os.path.join(ROOT, "logger", "data", f"snapshots-{datetime.now(timezone.utc):%Y-%m-%d}.jsonl")

STAGES = ["group", "r32", "r16", "qf", "sf", "final", "champion"]
LABEL = {"Group Stage": "group", "Round of 32": "r32", "Round of 16": "r16",
         "Quarterfinals": "qf", "Semifinals": "sf", "Final": "final", "Champion": "champion"}
# sum over all teams of P(reach stage) must equal the number of slots at that stage
SLOTS = {"r32": 32, "r16": 16, "qf": 8, "sf": 4, "final": 2, "champion": 1}


def slugify(team: str) -> str:
    t = unicodedata.normalize("NFKD", team).encode("ascii", "ignore").decode()
    t = t.lower().replace("&", " ").replace("'", "")
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return f"world-cup-{t}-stage-of-elimination"


def _flt(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fetch_market(team: str) -> dict | None:
    """{stage -> Yes price} for a team's elimination event, or None if not listed."""
    try:
        ev = requests.get("https://gamma-api.polymarket.com/events",
                          params={"slug": slugify(team)}, timeout=15).json()
        ev = ev[0] if isinstance(ev, list) and ev else ev
        if not isinstance(ev, dict):
            return None
    except Exception:
        return None
    import ast
    out = {}
    for m in ev.get("markets", []):
        stage = LABEL.get(m.get("groupItemTitle"))
        if not stage:
            continue
        pr = m.get("outcomePrices")
        pr = ast.literal_eval(pr) if isinstance(pr, str) else pr
        yes = _flt(pr[0]) if pr else None
        if yes is not None:
            out[stage] = yes
    return out if len(out) >= 6 else None


def model_distribution() -> dict:
    """team -> {stage -> P}, the model's 7-way elimination distribution (sums to 1)."""
    df = data.load_results()
    res = elo.build_ratings(df)
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)   # Elo + squad value (Finding #10), not raw Elo
    fx = pd.read_csv(FIXTURES)
    grp_results = wc_played_results(df, fx)   # condition on games played (was UNCONDITIONED -> stale cards)
    out, det = group_sim.simulate(fx, ratings, params, return_detail=True,
                                  sigma=group_sim.MODEL_SIGMA, results=grp_results)
    ko = knockout.simulate(det, out, ratings,
                           results=knockout.played_ko_results(det, fx))["reach"]   # {team: {r16,qf,sf,final,win}}
    dist = {}
    for team, r in ko.items():
        padv = out.get(W.elo_name(W.canonical(team)), {}).get("padv")
        if padv is None:
            padv = out.get(team, {}).get("padv")
        if padv is None:
            continue
        r16, qf, sf, fin, win = r["r16"]/100, r["qf"]/100, r["sf"]/100, r["final"]/100, r["win"]/100
        d = {"group": 1 - padv, "r32": padv - r16, "r16": r16 - qf, "qf": qf - sf,
             "sf": sf - fin, "final": fin - win, "champion": win}
        d = {k: max(v, 0.0) for k, v in d.items()}
        s = sum(d.values()) or 1.0
        dist[team] = {k: v / s for k, v in d.items()}
    return dist


def reach_from_dist(d: dict) -> dict:
    """P(reach stage) = sum of elimination probs at that stage and beyond."""
    return {st: sum(d[s] for s in STAGES[i:]) for i, st in enumerate(STAGES) if st in SLOTS}


def main() -> int:
    print("simulating the tournament (model 7-way distribution) ...")
    model = model_distribution()

    print("fetching Polymarket elimination markets (48 teams) ...")
    winner = {}
    try:
        winner = team_probs("world-cup-winner")
    except Exception:
        pass
    teams, missing, slot_market = [], [], {k: 0.0 for k in SLOTS}
    ts = datetime.now(timezone.utc).isoformat()
    snap_lines = []
    for team in sorted(model, key=lambda t: -model[t]["champion"]):
        raw = fetch_market(team)
        if not raw:
            missing.append(team)
            continue
        present = {k: raw[k] for k in STAGES if k in raw}
        rawsum = sum(present.values())
        mdist = {k: present.get(k, 0.0) / rawsum for k in STAGES}     # de-vigged
        mreach = reach_from_dist(mdist)
        for st, p in mreach.items():
            slot_market[st] += p
        # biggest model-vs-market stage divergence
        diffs = {k: round((mdist[k] - model[team][k]) * 100, 1) for k in STAGES}
        top = max(diffs, key=lambda k: abs(diffs[k]))
        champ_mkt = round(mdist["champion"] * 100, 1)
        champ_win = round(winner.get(team, float("nan")) * 100, 1) if team in winner else None
        teams.append({
            "team": team, "iso": ISO.get(team, ""), "color": KIT.get(team, INK),
            "model": {k: round(model[team][k] * 100, 1) for k in STAGES},
            "market": {k: round(mdist[k] * 100, 1) for k in STAGES},
            "overround_pct": round((rawsum - 1) * 100, 1),
            "champ_market": champ_mkt, "champ_winner_mkt": champ_win,
            "champ_cross_gap": None if champ_win is None else round(champ_mkt - champ_win, 1),
            "top_div_stage": top, "top_div_pp": diffs[top], "divs": diffs,
        })
        for st in STAGES:
            snap_lines.append({"ts_utc": ts, "venue": "polymarket",
                               "market_id": slugify(team), "market_label": "WC2026 elimination",
                               "outcome": f"{team}|{st}", "mid": round(present.get(st, 0.0), 4),
                               "extra": {"market_type": "elimination", "team": team, "stage": st}})
        ensure_flag(ISO.get(team, ""))

    coherence = {"slot_sums": {k: round(slot_market[k], 2) for k in SLOTS},
                 "slot_targets": SLOTS,
                 "mean_overround_pct": round(sum(t["overround_pct"] for t in teams) / max(len(teams), 1), 1),
                 "n_teams": len(teams), "n_missing": len(missing)}
    payload = {"teams": teams, "coherence": coherence,
               "note": "model 7-way vs Polymarket; market de-vigged by normalising the 7 Yes legs"}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.ELIM = " + json.dumps(payload) + ";\n")

    # capture the snapshot (append-only, into the logger's day file)
    if snap_lines:
        with open(SNAP, "a", encoding="utf-8") as f:
            for r in snap_lines:
                f.write(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n")

    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(teams)} teams ({len(missing)} not listed)")
    print(f"mean overround {coherence['mean_overround_pct']}%  ·  slot sums "
          + ", ".join(f"{k}={coherence['slot_sums'][k]}/{v}" for k, v in SLOTS.items()))
    big = sorted(teams, key=lambda t: -abs(t["top_div_pp"]))[:6]
    print("biggest model-vs-market divergences:")
    for t in big:
        print(f"  {t['team']:14} {t['top_div_stage']:>8} {t['top_div_pp']:+.1f}pp  "
              f"(champ mkt {t['champ_market']}% vs winner-mkt {t['champ_winner_mkt']}%)")
    if missing:
        print(f"not listed yet: {', '.join(missing[:12])}{' ...' if len(missing) > 12 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
