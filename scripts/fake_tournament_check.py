#!/usr/bin/env python3
"""Drive a complete FAKE 2026 tournament through the pipeline to validate the logic end-to-end
— especially the result-resolution that can't otherwise be tested until real games are played.

    python scripts/fake_tournament_check.py

Fabricates a coherent full tournament (group results -> real bracket -> knockout winners ->
champion), monkeypatches it in as the results feed, and checks: group conditioning, knockout
conditioning, and that _resolve_outcomes grades advance/group-win/reach-round/champion
against reality correctly. Read-only on real ledgers; writes nothing.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import baseline, data, elo, group_sim, knockout, wc2026_teams as W  # noqa: E402
from blend import blended_ratings  # noqa: E402
import prediction_board as PB  # noqa: E402

FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
OK, BAD = "\033[32mOK\033[0m", "\033[31mFAIL\033[0m"


def main() -> int:
    fx = pd.read_csv(FIXTURES)
    df_real = data.load_results()
    res = elo.build_ratings(df_real)
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)
    rt = lambda t: ratings.get(W.elo_name(W.canonical(t)), elo.INIT_RATING)

    # 1. fake GROUP results: higher-rated team wins 2-0 (decisive -> deterministic standings)
    grp = fx[fx["group"].astype(str).str.startswith("Group")]
    gres = {}
    srng = np.random.default_rng(7)
    for r in grp.itertuples(index=False):               # sample one realistic scoreline per game
        a, b = W.canonical(r.team1), W.canonical(r.team2)   # (varied scores -> distinct standings
        l1, l2 = group_sim._match_lambdas(r.team1, r.team2, r.ground, ratings, params)  # -> tie-free
        g1, g2 = int(srng.poisson(l1)), int(srng.poisson(l2))                           # -> det. R32)
        gres[(a, b)] = (g1, g2)
        gres[(b, a)] = (g2, g1)
    sim, det = group_sim.simulate(fx, ratings, params, n=3000, sigma=0.0,
                                  return_detail=True, results=gres)
    print(f"[1 groups]    sum P(advance) = {sum(r['padv'] for r in sim.values()):.1f}  (want 32)")

    # 2. fake KNOCKOUT = one realization of the conditioned sim
    ko = knockout.simulate(det, sim, ratings, return_matchups=True, return_paths=True,
                           return_slots=True, seed=3)
    mu, paths, nm = ko["matchups"], ko["paths"], ko["teams_arr"]
    champ_arr = paths["champ"].reshape(paths["champ"].shape[0], -1)
    truth = {  # ground-truth sets from realization 0
        "advance": {nm[int(x)] for x in mu["R32"][0].flatten()},
        "reach_qf": {nm[int(x)] for x in mu["QF"][0].flatten()},
        "reach_sf": {nm[int(x)] for x in mu["SF"][0].flatten()},
        "reach_final": {nm[int(x)] for x in mu["Final"][0].flatten()},
        "champion": {nm[int(champ_arr[0, 0])]},
    }
    fake_champ = nm[int(champ_arr[0, 0])]
    print(f"[2 knockout]  fake champion = {fake_champ}  ·  finalists = {truth['reach_final']}")

    # 3. knockout CONDITIONING: feed the fake ties back -> champion must be deterministic
    fake_ko = []
    for rk, wk in [("R32", "w32"), ("R16", "w16"), ("QF", "wqf"), ("SF", "wsf"), ("Final", "champ")]:
        arr = mu[rk]
        win = champ_arr if wk == "champ" else paths[wk]
        for j in range(arr.shape[1]):
            fake_ko.append((rk, int(arr[0, j, 0]), int(arr[0, j, 1]), int(win[0, j])))
    ko_res = {frozenset((a, b)): w for _, a, b, w in fake_ko}
    reach2 = knockout.simulate(det, sim, ratings, return_paths=True, results=ko_res)["reach"]
    print(f"[3 ko-cond]   reach champion {fake_champ}: {reach2[fake_champ]['win']}%  -> "
          f"{OK if reach2[fake_champ]['win'] > 99 else BAD}")

    # 4. build the fake results feed and monkeypatch it in
    grp_end = pd.to_datetime(grp["date"]).max()
    ko_fx = fx[~fx["group"].astype(str).str.startswith("Group")]
    exact = {"R32": "Round of 32", "R16": "Round of 16", "QF": "Quarter-final",
             "SF": "Semi-final", "Final": "Final"}
    rdate = {}
    for k, lbl in exact.items():
        m = ko_fx[ko_fx["round"].astype(str) == lbl]
        rdate[k] = (pd.to_datetime(m["date"]).min() if len(m) else grp_end + pd.Timedelta(days=5))
    rows = []
    for r in grp.itertuples(index=False):
        a, b = W.canonical(r.team1), W.canonical(r.team2)
        rows.append(dict(date=str(r.date), home_team=a, away_team=b, home_score=gres[(a, b)][0],
                         away_score=gres[(a, b)][1], tournament="FIFA World Cup", neutral=True))
    for rk, a, b, w in fake_ko:
        rows.append(dict(date=rdate[rk].strftime("%Y-%m-%d"), home_team=nm[a], away_team=nm[b],
                         home_score=1 if w == a else 0, away_score=0 if w == a else 1,
                         tournament="FIFA World Cup", neutral=True))
    fake_df = pd.concat([df_real, pd.DataFrame(rows)], ignore_index=True)
    data.load_results = lambda *a, **k: fake_df.copy()   # monkeypatch the feed

    # 5. resolution: grade the real pre-committed ledger against the fake tournament
    led = [json.loads(l) for l in open(os.path.join(ROOT, "paper", "forecasts.jsonl"))]
    out = PB._resolve_outcomes(led)
    resolved = {i: y for i, y in out.items() if y is not None}
    print(f"[4 resolve]   {len(resolved)}/{len(led)} forecasts resolved")
    for mkt in ("advance", "group_win", "reach_qf", "reach_sf", "reach_final", "champion"):
        checks = [(led[i]["team"], y) for i, y in resolved.items() if led[i]["market"] == mkt]
        if not checks:
            continue
        if mkt == "group_win":
            print(f"   group_win    : {sum(y for _, y in checks)} winners marked ({len(checks)} resolved) — sanity check only")
            continue
        bad = [(t, y) for t, y in checks if bool(y) != (t in truth.get(mkt, set()))]
        print(f"   {mkt:<12}: {len(checks)} resolved, {len(bad)} wrong  -> {OK if not bad else BAD}"
              + (f"   e.g. {bad[:3]}" if bad else ""))

    # 6. calibration sanity
    pairs = [(led[i]["model"], y) for i, y in resolved.items()]
    p = np.array([a for a, _ in pairs]); y = np.array([b for _, b in pairs], float)
    print(f"[5 calib]     Brier {np.mean((p - y) ** 2):.3f}  log-loss "
          f"{np.mean(-(y*np.log(np.clip(p,1e-9,1))+(1-y)*np.log(np.clip(1-p,1e-9,1)))):.3f}  on {len(pairs)} resolved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
