#!/usr/bin/env python3
"""The model's knockout bracket -> docs/data/bracket.js.

    python scripts/build_bracket.py

Runs the joint sim conditioned on every game played so far (group AND knockout results), then
tallies the most-likely team in each bracket slot and the model's projected advancer for each
tie. So the bracket is PROJECTED before the group stage, fills in with the REAL teams once the
group stage resolves, and updates after every knockout game (a played tie becomes deterministic
in the conditioned sim — the actual winner advances and the rest re-forecasts on updated state).
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import baseline, data, elo, group_sim, knockout, wc2026_teams  # noqa: E402
from blend import blended_ratings  # noqa: E402
from prediction_board import wc_played_results  # noqa: E402
from pull_forecast_data import ISO  # noqa: E402

OUT = os.path.join(ROOT, "docs", "data", "bracket.js")
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")


def live_results():
    """Played group results from the live site ledger (docs/data/matches.js) — the freshest feed,
    ahead of the Elo results feed mid-tournament. Returns ({(c1,c2):(s1,s2),...}, standings-by-team
    with actual points/GD/played so far)."""
    p = os.path.join(ROOT, "docs", "data", "matches.js")
    if not os.path.exists(p):
        return {}, {}
    try:
        d = json.loads(re.search(r"=\s*(\{.*\});", open(p, encoding="utf-8").read(), re.S).group(1))
    except Exception:
        return {}, {}
    results, st = {}, {}
    for m in d.get("matches", []):
        if not m.get("played"):
            continue
        t1, t2, s1, s2 = m["t1"], m["t2"], int(m["s1"]), int(m["s2"])
        results[(t1, t2)] = (s1, s2); results[(t2, t1)] = (s2, s1)
        grp = str(m.get("group", "")).replace("Group ", "")
        for tm, gf, ga in ((t1, s1, s2), (t2, s2, s1)):
            r = st.setdefault(tm, {"played": 0, "pts": 0, "gd": 0, "group": grp})
            r["played"] += 1; r["gd"] += gf - ga
            r["pts"] += 3 if gf > ga else (1 if gf == ga else 0)
    return results, st
ROUNDS = [("Round of 32", "R32"), ("Round of 16", "R16"), ("Quarter-finals", "QF"),
          ("Semi-finals", "SF"), ("Final", "Final")]


def main() -> int:
    df = data.load_results()
    res = elo.build_ratings(df)
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)
    fx = pd.read_csv(FIXTURES)
    # Condition on the freshest results: the live site ledger (matches.js) runs ahead of the Elo
    # results feed mid-tournament, so prefer it when it carries more games. `standings` = the actual
    # points/GD so far, shown on the projected group tables.
    live, standings = live_results()
    fallback = wc_played_results(df, fx)
    grp_results = live if len(live) >= len(fallback) else fallback
    sim, det = group_sim.simulate(fx, ratings, params, return_detail=True,
                                  sigma=group_sim.MODEL_SIGMA, results=grp_results)
    gidx = det["gidx"]

    # knockout results so far (games after the group stage) -> {frozenset(idxA,idxB): winner_idx}
    grp = fx[fx["group"].astype(str).str.startswith("Group")]
    group_end = pd.to_datetime(grp["date"]).max()
    d = df[df["tournament"] == "FIFA World Cup"].copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d[d["date"] > group_end]
    # Bridge result names and the gidx keys to the Elo convention so feed-name differences
    # (USA/United States, Bosnia variants) match regardless of which convention gidx uses.
    bridge = lambda t: wc2026_teams.elo_name(wc2026_teams.canonical(t))
    gidx_b = {bridge(k): v for k, v in gidx.items()}
    ko_res = {}
    for r in d.itertuples(index=False):
        h, a = bridge(r.home_team), bridge(r.away_team)
        if h in gidx_b and a in gidx_b and r.home_score != r.away_score:   # KO ties resolve to a winner
            w = h if r.home_score > r.away_score else a
            ko_res[frozenset((gidx_b[h], gidx_b[a]))] = gidx_b[w]

    ko = knockout.simulate(det, sim, ratings, return_matchups=True, return_slots=True,
                           return_paths=True, results=ko_res or None)
    mu, names, paths = ko["matchups"], ko["teams_arr"], ko["paths"]
    pmap = {"R32": paths["w32"], "R16": paths["w16"], "QF": paths["wqf"],
            "SF": paths["wsf"], "Final": paths["champ"].reshape(paths["champ"].shape[0], -1)}
    n = mu["R32"].shape[0]

    rate = {names[i]: float(ko["rating_arr"][i]) for i in range(len(names))}

    def mode(col):
        v, c = np.unique(col, return_counts=True)
        i = int(c.argmax())
        return names[int(v[i])], c[i] / n

    rounds = []
    for label, key in ROUNDS:
        arr, win = mu[key], pmap[key]
        matches = []
        for j in range(arr.shape[1]):
            ta, pa = mode(arr[:, j, 0])
            tb, pb = mode(arr[:, j, 1])
            wt, wp = mode(win[:, j])
            final = bool(pa > 0.999 and pb > 0.999 and wp > 0.999)   # both teams fixed + a result in
            if wt not in (ta, tb):  # projected, and marginal modes don't form a coherent tie ->
                ra, rb = rate.get(ta, 1500.0), rate.get(tb, 1500.0)  # use the Elo head-to-head pick
                wt, wp = (ta, 1 / (1 + 10 ** ((rb - ra) / 400))) if ra >= rb else (tb, 1 / (1 + 10 ** ((ra - rb) / 400)))
            matches.append({"a": ta, "pa": int(round(pa * 100)), "b": tb, "pb": int(round(pb * 100)),
                            "pick": wt, "wp": int(round(wp * 100)), "final": final})
        rounds.append({"round": label, "matches": matches})

    champ, cp = mode(paths["champ"].reshape(-1))

    # projected group standings (conditioned): each team by its advance probability, with win-group
    # probability and actual points so far — rendered under the bracket.
    groups = {}
    for t, r in sim.items():
        s = standings.get(t, {})
        groups.setdefault(r["group"], []).append({
            "team": t, "iso": ISO.get(t, ""),
            "p1": round(r["p1"] * 100), "padv": round(r["padv"] * 100),
            "pts": s.get("pts", 0), "pl": s.get("played", 0), "gd": s.get("gd", 0)})
    for g in groups:
        groups[g].sort(key=lambda x: (-x["padv"], -x["pts"], -x["gd"]))

    payload = {"asof": datetime.now(timezone.utc).isoformat(),
               "group_done": bool((len(grp_results) // 2) >= 72),
               "rounds": rounds, "champion": {"team": champ, "p": round(float(cp) * 100, 1), "final": bool(cp > 0.999)},
               "groups": groups}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.BRACKET = " + json.dumps(payload, separators=(",", ":")) + ";\n")
    print(f"wrote {os.path.relpath(OUT, ROOT)}: champion pick {champ} {cp*100:.1f}% · "
          f"{len(ko_res)} knockout games conditioned · group_done={payload['group_done']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
