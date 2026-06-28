"""Knockout-stage Monte Carlo for 2026 (Round of 32 -> Final), built on the
group-stage simulation in group_sim.py.

Half the Round of 32 is fixed by group position alone (winner / runner-up ties); the
other eight ties each pair a group winner against one of the eight best third-placed
teams, via FIFA's Annex C combination table. Annex C is a lookup over the C(12,8)=495
possible sets of qualifying thirds, but it encodes two rules we reproduce directly:
each third-place slot may only receive a third from a fixed set of groups, and no
group-stage rematch is allowed. We resolve each simulation's assignment with a
most-constrained-first matching consistent with those rules. The exact Annex C row
only disambiguates the rare case of multiple valid matchings and has negligible
effect on aggregate reach-round probabilities.

Knockout ties use the same Elo strength as the group model, at a neutral venue, with
draws resolved in proportion to each side's strength (a penalty-shootout proxy via
the Elo expected score).
"""

from __future__ import annotations

import numpy as np

from . import elo, wc2026_teams

# Round of 32 skeleton. Each match: (id, slotA, slotB); a slot is
#   ("W", group) winner · ("R", group) runner-up · ("3", allowed-groups) a best third.
R32 = [
    (73, ("R", "A"), ("R", "B")),
    (74, ("W", "E"), ("3", set("ABCDF"))),
    (75, ("W", "F"), ("R", "C")),
    (76, ("W", "C"), ("R", "F")),
    (77, ("W", "I"), ("3", set("CDFGH"))),
    (78, ("R", "E"), ("R", "I")),
    (79, ("W", "A"), ("3", set("CEFHI"))),
    (80, ("W", "L"), ("3", set("EHIJK"))),
    (81, ("W", "D"), ("3", set("BEFIJ"))),
    (82, ("W", "G"), ("3", set("AEHIJ"))),
    (83, ("R", "K"), ("R", "L")),
    (84, ("W", "H"), ("R", "J")),
    (85, ("W", "B"), ("3", set("EFGIJ"))),
    (86, ("W", "J"), ("R", "H")),
    (87, ("W", "K"), ("3", set("DEIJL"))),
    (88, ("R", "D"), ("R", "G")),
]
R32_IDS = [m[0] for m in R32]
# feeder trees: (match_id, feeder_a, feeder_b)
R16 = [(89, 74, 77), (90, 73, 75), (91, 76, 78), (92, 79, 80),
       (93, 83, 84), (94, 81, 82), (95, 86, 88), (96, 85, 87)]
QF = [(97, 89, 90), (98, 93, 94), (99, 91, 92), (100, 95, 96)]
SF = [(101, 97, 98), (102, 99, 100)]
FN = [(104, 101, 102)]


# FIFA's published Annex-C third-place assignment for the ACTUAL 2026 qualifying set, verified
# against the official Round-of-32 draw (FIFA / ESPN / Sky, Jun 2026). The allowed-set matching
# below is NON-UNIQUE — several legal matchings exist for a given qualifying set — so the LIVE
# bracket must follow FIFA's specific table, not an arbitrary valid one. (The arbitrary matching
# is what put Belgium vs Algeria instead of the real Belgium vs Senegal.) Keyed by the set of
# groups whose third qualified; value is {winner group -> the third's group}. Converted to slot
# indices in _assign off the R32 structure, so it survives any reordering of R32.
_FIFA_THIRD_TABLE = {
    frozenset("BDEFIJKL"): {"E": "D", "I": "F", "A": "E", "L": "K",
                            "D": "B", "G": "I", "B": "J", "K": "L"},
}


def _assign(qual: set, slots: list) -> dict:
    """Match the eight qualifying third-place groups to the eight third slots. slots: list of
    (r32_index, allowed_groups). Returns {r32_index -> group letter}.

    FIFA assigns the thirds from a PUBLISHED per-combination table, not a free matching — and
    within a slot's allowed-groups set there are usually several legal matchings, so picking an
    arbitrary one is wrong (it draws the real bracket incorrectly). So: if FIFA's table for this
    qualifying set is known (_FIFA_THIRD_TABLE), use it. Otherwise fall back to a constraint-
    respecting bipartite matching (Kuhn's algorithm), which at least never produces a group-stage
    rematch — used only for hypothetical qualifying sets that didn't occur."""
    fifa = _FIFA_THIRD_TABLE.get(frozenset(qual))
    if fifa is not None:
        slot_win = {idx: R32[idx][1][1] for idx, _ in slots}   # slot index -> its (W, group) winner
        out = {idx: fifa[w] for idx, w in slot_win.items() if w in fifa}
        if len(out) == len(slots):                              # full, valid table hit
            return out

    adj = {idx: sorted(g for g in qual if g in allowed) for idx, allowed in slots}
    match: dict[str, int] = {}              # group letter -> slot index

    def augment(idx: int, seen: set) -> bool:
        for g in adj[idx]:
            if g in seen:
                continue
            seen.add(g)
            if g not in match or augment(match[g], seen):
                match[g] = idx
                return True
        return False

    for idx in sorted(adj, key=lambda i: len(adj[i])):   # fewest options first, deterministic
        augment(idx, set())
    return {idx: g for g, idx in match.items()}


def simulate(detail: dict, out: dict, ratings: dict[str, float], seed: int = 11,
             return_matchups: bool = False, return_slots: bool = False,
             return_paths: bool = False, results: dict | None = None) -> dict:
    """Run the knockout bracket on the group-stage simulation `detail`/`out`.

    Returns {reach: {team -> {r16,qf,sf,final,win}}, r32: [{id, winner_slot,
    matchups:[{a,b,p}]}]} where reach probabilities are over the same simulations.

    With return_paths=True also returns result["paths"] = the per-sim round-winner
    arrays of global team indices (w32 (n,16) reached R16, w16 (n,8) reached QF,
    wqf (n,4) reached SF, wsf (n,2) reached final, champ (n,1)), from which a per-team
    per-sim tournament depth and the champion's group are reconstructed jointly.
    """
    teams, gidx, pos, adv = detail["teams"], detail["gidx"], detail["pos"], detail["adv_mat"]
    n, nT = pos.shape[0], len(teams)
    rows = np.arange(n)
    rng = np.random.default_rng(seed)
    rating_arr = np.array([ratings.get(wc2026_teams.elo_name(t), elo.INIT_RATING) for t in teams])

    bygrp = {}
    for t in teams:
        bygrp.setdefault(out[t]["group"], []).append(t)
    letters = sorted(bygrp)

    win_of, ru_of, third_of, qual_of = {}, {}, {}, {}
    for L in letters:
        cols = np.array([gidx[t] for t in bygrp[L]])
        sub = pos[:, cols]
        win_of[L] = cols[np.argmax(sub == 0, axis=1)]
        ru_of[L] = cols[np.argmax(sub == 1, axis=1)]
        third_of[L] = cols[np.argmax(sub == 2, axis=1)]
        qual_of[L] = adv[rows, third_of[L]]

    # Build the Round-of-32: position slots vectorized, third slots per simulation.
    r32 = np.zeros((n, 16, 2), dtype=int)
    for i, (_mid, a, b) in enumerate(R32):
        for j, (kind, val) in enumerate((a, b)):
            if kind == "W":
                r32[:, i, j] = win_of[val]
            elif kind == "R":
                r32[:, i, j] = ru_of[val]
    slots = [(i, R32[i][2][1]) for i in range(16) if R32[i][2][0] == "3"]
    for s in range(n):
        qual = {L for L in letters if qual_of[L][s]}
        for i, g in _assign(qual, slots).items():
            r32[s, i, 1] = third_of[g][s]

    eps = detail.get("eps")   # per-sim team-strength offsets, consistent with the group stage
    rr = np.arange(n)[:, None]

    def play(pairs):
        a, b = pairs[:, :, 0], pairs[:, :, 1]
        r1, r2 = rating_arr[a], rating_arr[b]
        if eps is not None:
            r1 = r1 + eps[rr, a]
            r2 = r2 + eps[rr, b]
        p1 = 1.0 / (1.0 + 10 ** ((r2 - r1) / 400.0))
        w1 = rng.random(p1.shape) < p1
        wnr = np.where(w1, a, b)
        if results:                                   # fix knockout games already played to reality
            for k in range(a.shape[1]):
                ca, cb = a[:, k], b[:, k]
                if (ca == ca[0]).all() and (cb == cb[0]).all():   # deterministic pairing (post-group)
                    win = results.get(frozenset((int(ca[0]), int(cb[0]))))
                    if win is not None:
                        wnr[:, k] = win
        return wnr

    def build(level, prevwin, prev_ids):
        pid = {mid: k for k, mid in enumerate(prev_ids)}
        pairs = np.zeros((n, len(level), 2), dtype=int)
        for k, (_mid, f1, f2) in enumerate(level):
            pairs[:, k, 0] = prevwin[:, pid[f1]]
            pairs[:, k, 1] = prevwin[:, pid[f2]]
        return pairs

    w32 = play(r32)                                             # reached Round of 16
    r16p = build(R16, w32, R32_IDS); w16 = play(r16p)          # reached QF
    qfp = build(QF, w16, [m[0] for m in R16]); wqf = play(qfp)  # reached SF
    sfp = build(SF, wqf, [m[0] for m in QF]); wsf = play(sfp)   # reached Final
    fnp = build(FN, wsf, [m[0] for m in SF]); champ = play(fnp)  # champion

    def tally(arr):
        c = np.zeros(nT)
        v, k = np.unique(arr, return_counts=True)
        c[v] = k
        return c / n

    reach_arr = {"r16": tally(w32), "qf": tally(w16), "sf": tally(wqf),
                 "final": tally(wsf), "win": tally(champ)}
    reach = {t: {kf: round(float(reach_arr[kf][gidx[t]]) * 100, 1) for kf in reach_arr}
             for t in teams}

    # Per group winner: who they most likely meet in the Round of 32, and how hard
    # the draw is (mean opponent Elo). The winner identity is itself uncertain, so we
    # also surface the most likely team to be that winner.
    name = np.array(teams)
    winner_opp = []
    for i, (mid, a, b) in enumerate(R32):
        for j, (kind, val) in enumerate((a, b)):
            if kind != "W":
                continue
            L = val
            opp = r32[:, i, 1 - j]
            v, c = np.unique(opp, return_counts=True)
            order = np.argsort(-c)
            opps = [{"team": name[v[k]], "p": round(float(c[k]) / n * 100, 1)} for k in order[:5]]
            wv, wc = np.unique(r32[:, i, j], return_counts=True)
            wtop = wv[np.argmax(wc)]
            winner_opp.append({
                "group": L, "via_third": b[0] == "3",
                "winner": name[wtop], "winner_p": round(float(wc.max()) / n * 100, 1),
                "mean_opp_elo": round(float(rating_arr[opp].mean()), 0),
                "opps": opps})
    winner_opp.sort(key=lambda r: r["mean_opp_elo"])  # kindest route first
    result = {"reach": reach, "winner_opp": winner_opp}
    if return_matchups:
        # per-round (n, matches, 2) arrays of global team indices, for "do A and B meet?"
        result["matchups"] = {"R32": r32, "R16": r16p, "QF": qfp, "SF": sfp, "Final": fnp}
    if return_slots:
        # the R32 fills + ratings, for path-difficulty-by-finishing-position analysis
        result["r32"] = r32
        result["rating_arr"] = rating_arr
        result["teams_arr"] = list(teams)
    if return_paths:
        # per-sim round winners (global team indices): the joint outcome needed to price
        # confederation furthest/worst-advancing and group-of-champion markets, which the
        # marginal reach probabilities alone cannot express.
        result["paths"] = {"w32": w32, "w16": w16, "wqf": wqf, "wsf": wsf, "champ": champ}
    return result


def played_ko_results(detail: dict, fixtures, results_df=None) -> dict | None:
    """Build the `results=` dict for simulate() from knockout games already played.

    Maps frozenset((idxA, idxB)) -> winner index for every FIFA World Cup game after the group
    stage with a decisive scoreline, so the knockout sim fixes settled ties to reality instead of
    re-projecting them from group state — the same conditioning the group sim already does, one
    round later. Bridges feed-name differences (USA/United States, Bosnia variants) to the Elo
    convention via elo_name(canonical(.)). Returns None when no knockout game has been played yet,
    so simulate() runs unconditioned. Centralised here so every card builder conditions identically
    (was inline in build_bracket.py only; the others silently went stale once the R32 was played)."""
    import pandas as pd
    if results_df is None:
        from . import data
        results_df = data.load_results()
    gidx = detail["gidx"]
    grp = fixtures[fixtures["group"].astype(str).str.startswith("Group")]
    group_end = pd.to_datetime(grp["date"]).max()
    d = results_df[results_df["tournament"] == "FIFA World Cup"].copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d[d["date"] > group_end]
    bridge = lambda t: wc2026_teams.elo_name(wc2026_teams.canonical(t))
    gidx_b = {bridge(k): v for k, v in gidx.items()}
    ko_res = {}
    for r in d.itertuples(index=False):
        h, a = bridge(r.home_team), bridge(r.away_team)
        if h in gidx_b and a in gidx_b and r.home_score != r.away_score:   # KO ties resolve to a winner
            w = h if r.home_score > r.away_score else a
            ko_res[frozenset((gidx_b[h], gidx_b[a]))] = gidx_b[w]
    return ko_res or None
