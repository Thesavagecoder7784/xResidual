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

    def assign_round(arr):
        """Greedy one-team-per-slot projection for a round. Filling each slot with its independent
        modal team double-books a team that is the most-likely occupant of two mutually-exclusive
        slots (e.g. Bosnia as Group-B runner-up AND as a best-third — it can be one or the other in
        any single sim, never both). Instead, rank every (slot, team) by its sim count and assign
        greedily, skipping any slot or team already taken, so no team appears twice in one round."""
        cand = []
        for j in range(arr.shape[1]):
            for side in (0, 1):
                v, c = np.unique(arr[:, j, side], return_counts=True)
                cand += [(int(ci), j * 2 + side, int(vi)) for vi, ci in zip(v, c)]
        cand.sort(reverse=True)
        asg, used = {}, set()
        for ci, slot, ti in cand:
            if slot in asg or ti in used:
                continue
            asg[slot] = (names[ti], ci / n)
            used.add(ti)
        for j in range(arr.shape[1]):                 # fallback: any slot left unfilled keeps its mode
            for side in (0, 1):
                asg.setdefault(j * 2 + side, mode(arr[:, j, side]))
        return asg

    name_idx = {names[i]: i for i in range(len(names))}

    def reach_p(arr, team):
        """P(`team` reaches this round) — it appears in ANY slot of the round across sims. We use
        round-level reach, not exact-slot occupancy: the deduped + chained projection deliberately
        moves a team onto a slot the raw sim rarely fills with it, so slot-level counts read ~0
        (the '0%' bug). Round-level is the coherent 'how likely to reach this stage' the card wants."""
        idx = name_idx.get(team)
        return float((arr == idx).any(axis=2).any(axis=1).sum()) / n if idx is not None else 0.0

    # Build a COHERENT bracket: project the R32 slots (deduped), then advance each match's pick into
    # the next round, chaining up — so every R16+ team is actually the winner of the two matches that
    # feed it. Filling each round independently with its marginal mode left R16+ slots showing the
    # most-likely team to REACH that slot, which often wasn't either feeder's winner (the connectors
    # led to a team not in the two matches above it — the "not accurate" bug). The pick prefers the
    # sim's conditional advancer (= the real result once a knockout tie is played) and falls back to
    # the Elo head-to-head for a purely projected tie, so it is always one of the slot's two teams.
    rounds, prev_winners = [], None
    for ri, (label, key) in enumerate(ROUNDS):
        arr, win = mu[key], pmap[key]
        nm = arr.shape[1]
        if ri == 0:
            asg = assign_round(arr)
            slots = [asg[s] for s in range(nm * 2)]            # deduped R32 occupants
        else:
            slots = [(w, reach_p(arr, w)) for w in prev_winners]   # chain the winners; round-level reach %
        matches, winners = [], []
        for j in range(nm):
            ta, pa = slots[2 * j]
            tb, pb = slots[2 * j + 1]
            wt, wp = mode(win[:, j])                            # sim advancer
            # Use the sim's advancer ONLY when a real knockout result has decided this tie (the
            # winner is one of the two shown teams AND near-certain). Otherwise it's a marginal mode
            # of the slot — which can name a team at 21% even though it's the "pick" — so fall back to
            # the model head-to-head of the TWO TEAMS ACTUALLY SHOWN, giving a coherent >50% pick.
            if wt not in (ta, tb) or wp < 0.95:
                ra, rb = rate.get(ta, 1500.0), rate.get(tb, 1500.0)
                wt, wp = (ta, 1 / (1 + 10 ** ((rb - ra) / 400))) if ra >= rb else (tb, 1 / (1 + 10 ** ((ra - rb) / 400)))
            matches.append({"a": ta, "pa": int(round(pa * 100)), "b": tb, "pb": int(round(pb * 100)),
                            "pick": wt, "wp": int(round(wp * 100)),
                            "final": bool(pa > 0.999 and pb > 0.999 and wp > 0.999)})
            winners.append(wt)
        rounds.append({"round": label, "matches": matches})
        prev_winners = winners

    # champion = the bracket's Final winner (coherent with the traced path), with its marginal P(win)
    champ = prev_winners[0] if prev_winners else None
    v, c = np.unique(paths["champ"].reshape(-1), return_counts=True)
    cp = {names[int(vi)]: ci / n for vi, ci in zip(v, c)}.get(champ, 0.0)

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
