"""Format-aware Monte Carlo of the 2026 group stage (builds on the §2 baseline and
the §9 host-advantage / altitude adjustments in METHODOLOGY.md).

The 2026 format changes what "advancing" means: 48 teams, 12 groups of four,
single round-robin. The top two of each group advance automatically AND the eight
best third-placed teams (compared across all 12 groups) also go through, so 32 of 48
reach the Round of 32. Finishing third is usually survivable, and the real cut
line sits between the surviving thirds and the rest.

Market quotes can't express this cleanly: the per-group winner / second-place /
advance markets are priced in independent order books and don't reconcile to a
joint distribution (their third-place residuals don't sum to the eight wildcard
spots). So we simulate it. Each draw plays the real fixture list with the Elo +
Poisson baseline (host advantage and altitude applied), ranks each group with the
points -> goal-difference -> goals-for tiebreak, then selects the eight best thirds
*jointly*. By construction the outputs are coherent: sum P(advance) = 32 and
sum P(qualify as a third) = 8 over the field.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import poisson

from . import elo, venues_wc2026, wc2026_teams
from .baseline import LAMBDA_FLOOR, BaselineParams

# Dixon-Coles low-score dependence parameter (1997). Independent Poisson under-counts
# 0-0 and 1-1 draws; rho<0 restores that mass at the expense of 1-0/0-1. A documented
# literature prior (≈ original fit), tunable; set to 0.0 to recover plain Poisson.
DC_RHO = -0.11

# Calibrated team-strength uncertainty (Elo SD), for published probability forecasts.
# Chosen by out-of-sample RPS on 13k competitive international matches since 2006
# (importance × recency weighted), cross-checked against the market (~50) and Glicko-RD
# (tens of Elo) — see scripts/calibrate_sigma.py. The bare engine default is sigma=0;
# rating-isolation diagnostics (the value-blend check, the draw-luck counterfactual) keep
# it at 0 on purpose so they isolate ratings / the draw rather than dispersion.
MODEL_SIGMA = 60.0
_GMAX = 9  # goal grid cap for the Dixon-Coles joint sampler (P(>9) is negligible)
_GRID = np.arange(_GMAX + 1)


def _dc_sample(l1: float, l2: float, rho: float, n: int, rng) -> tuple:
    """Sample n (home, away) scorelines from the Dixon-Coles-corrected joint."""
    if rho == 0.0:
        return rng.poisson(l1, n), rng.poisson(l2, n)
    joint = np.outer(poisson.pmf(_GRID, l1), poisson.pmf(_GRID, l2))
    joint[0, 0] *= 1.0 - l1 * l2 * rho     # tau(0,0) = 1 - lambda*mu*rho
    joint[0, 1] *= 1.0 + l1 * rho          # tau(0,1) = 1 + lambda*rho
    joint[1, 0] *= 1.0 + l2 * rho          # tau(1,0) = 1 + mu*rho
    joint[1, 1] *= 1.0 - rho               # tau(1,1) = 1 - rho
    flat = np.clip(joint, 0.0, None).ravel()
    flat /= flat.sum()
    idx = rng.choice(flat.size, size=n, p=flat)
    return idx // (_GMAX + 1), idx % (_GMAX + 1)


def _dc_sample_vec(l1, l2, rho: float, rng):
    """Per-sim Dixon-Coles scorelines where l1, l2 are PER-SIM rate arrays (the
    team-strength-uncertainty path can't share one joint pmf grid). Plain Poisson
    proposal, then accept/reject so the four low-score cells carry the DC tau weight
    (rho<0 lifts 0-0, trims 0-1 and 1-0). This is the same correction the scalar
    `_dc_sample` applies, so the published (sigma>0) forecast and the sigma=0 diagnostics
    share one goal model instead of silently diverging on draw rates."""
    l1 = np.asarray(l1, dtype=float); l2 = np.asarray(l2, dtype=float)
    g1, g2 = rng.poisson(l1), rng.poisson(l2)
    if rho == 0.0:
        return g1, g2

    def _tau(a, b, idx):
        t = np.ones(len(idx))
        m = (a == 0) & (b == 0); t[m] = 1.0 - l1[idx[m]] * l2[idx[m]] * rho
        m = (a == 0) & (b == 1); t[m] = 1.0 + l1[idx[m]] * rho
        m = (a == 1) & (b == 0); t[m] = 1.0 + l2[idx[m]] * rho
        m = (a == 1) & (b == 1); t[m] = 1.0 - rho
        return np.clip(t, 0.0, None)

    # tau_max bounds the DC weight per sim: the 0-0 cell (1-rho*l1*l2) and the 1-1 cell
    # (1-rho) are the only ones >1 when rho<0. Accept with prob tau/tau_max, resample rest.
    tau_max = np.maximum(1.0 - rho, 1.0 - rho * l1 * l2)
    todo = np.ones(len(l1), dtype=bool)
    for _ in range(64):                      # acceptance ~0.9/iter; cap guards termination
        idx = np.where(todo)[0]
        if idx.size == 0:
            break
        acc = rng.random(idx.size) < _tau(g1[idx], g2[idx], idx) / tau_max[idx]
        todo[idx[acc]] = False
        rej = idx[~acc]
        if rej.size:
            g1[rej], g2[rej] = rng.poisson(l1[rej]), rng.poisson(l2[rej])
    return g1, g2

# Host city -> host nation (Elo-convention name). Cities not listed are in the USA.
_MX_CITIES = {"Mexico City", "Guadalajara", "Monterrey"}
_CA_CITIES = {"Toronto", "Vancouver"}
_GROUND_ALIAS = {"New York/New Jersey": "New York New Jersey"}


def _city(ground: str) -> str:
    """Normalize a fixture 'ground' ('Boston (Foxborough)') to a venue key."""
    base = str(ground).split(" (")[0].strip()
    return _GROUND_ALIAS.get(base, base)


def _host_nation(city: str) -> str:
    if city in _MX_CITIES:
        return "Mexico"
    if city in _CA_CITIES:
        return "Canada"
    return "United States"


def _elo_name(team: str) -> str:
    return wc2026_teams.elo_name(wc2026_teams.canonical(team))


def _match_components(t1: str, t2: str, ground: str, ratings: dict[str, float],
                      params: BaselineParams) -> tuple[float, float, float, float]:
    """(rating1, rating2, host-adv, total-goals) for one fixture. Shared by the scalar
    and the per-sim (team-strength-uncertainty) goal paths."""
    r1 = ratings.get(_elo_name(t1), elo.INIT_RATING)
    r2 = ratings.get(_elo_name(t2), elo.INIT_RATING)
    city = _city(ground)
    host = _host_nation(city)
    adv = 0.0
    if _elo_name(t1) == host:
        adv = elo.HOME_ADVANTAGE
    elif _elo_name(t2) == host:
        adv = -elo.HOME_ADVANTAGE
    tot = params.total_goals * venues_wc2026.total_goals_factor(venues_wc2026.altitude_of(city))
    return r1, r2, adv, tot


def _match_lambdas(t1: str, t2: str, ground: str, ratings: dict[str, float],
                   params: BaselineParams) -> tuple[float, float]:
    """Poisson rates for one group fixture, with host advantage + altitude."""
    r1, r2, adv, tot = _match_components(t1, t2, ground, ratings, params)
    sup = params.beta * ((r1 - r2 + adv) / 100.0)
    return max((tot + sup) / 2.0, LAMBDA_FLOOR), max((tot - sup) / 2.0, LAMBDA_FLOOR)


def _rank_key(pts, gd, gf, rng):
    """Sortable score encoding the FIFA order points -> GD -> GF, with a tiny random
    jitter to break exact ties (drawing of lots)."""
    return pts * 1e7 + (gd + 100.0) * 1e3 + gf + rng.random(pts.shape) * 1e-3


def simulate(fixtures: pd.DataFrame, ratings: dict[str, float], params: BaselineParams,
             n: int = 40000, seed: int = 7, return_detail: bool = False, rho: float = DC_RHO,
             sigma: float = 0.0):
    """Run `n` group-stage simulations. Returns a dict keyed by canonical team name:
    {p1, p2, p3, p4, top2, padv, p3adv} as probabilities, plus the group letter.

    With `return_detail=True` also returns a second dict of per-simulation arrays for
    downstream analysis (match leverage, the third-place cut line, knockout seeding):
      teams   : list of canonical team names (column order of adv_mat)
      gidx    : {team -> column index}
      adv_mat : (n, 48) bool, did the team advance that simulation
      pos     : (n, 48) int8, finishing place 0..3 (1st..4th); 9 if not in that group
      matches : list of (group, team1, team2, sign) where sign is (n,) int8 of np.sign(g1-g2)
      cutline : (n,) int, points of the 8th (last-qualifying) third-placed team
      missed  : (n,) int, points of the 9th third (first to miss out)
    """
    rng = np.random.default_rng(seed)
    grp = fixtures[fixtures["group"].astype(str).str.startswith("Group")].copy()
    grp["G"] = grp["group"].str.replace("Group ", "", regex=False).str.strip()
    letters = sorted(grp["G"].unique())
    rows = np.arange(n)

    group_teams = {L: sorted(set(grp[grp["G"] == L]["team1"]) | set(grp[grp["G"] == L]["team2"]))
                   for L in letters}
    all_canon = [wc2026_teams.canonical(t) for L in letters for t in group_teams[L]]
    gidx = {t: i for i, t in enumerate(all_canon)}
    nT = len(all_canon)
    # Team-strength uncertainty: each sim draws a per-team rating offset, held constant
    # across that team's whole tournament (group + knockouts). This widens the predictive
    # distribution to the right amount instead of treating each rating as known exactly.
    eps = rng.normal(0.0, sigma, size=(n, nT)) if sigma > 0 else None
    adv_mat = np.zeros((n, nT), dtype=bool)
    pos = np.full((n, nT), 9, dtype=np.int8)
    matches = []

    out = {}
    thirds_key_cols, thirds_team_cols, thirds_pts_cols, thirds_gidx_cols = [], [], [], []
    for L in letters:
        sub = grp[grp["G"] == L]
        teams = group_teams[L]
        canon = [wc2026_teams.canonical(t) for t in teams]
        idx = {t: i for i, t in enumerate(teams)}
        k = len(teams)
        pts = np.zeros((n, k)); gd = np.zeros((n, k)); gf = np.zeros((n, k))
        for row in sub.itertuples(index=False):
            i, j = idx[row.team1], idx[row.team2]
            if eps is not None:
                r1, r2, adv, tot = _match_components(row.team1, row.team2, row.ground, ratings, params)
                gi, gj = gidx[canon[i]], gidx[canon[j]]
                sup = params.beta * ((r1 + eps[:, gi] - r2 - eps[:, gj] + adv) / 100.0)
                l1a = np.clip((tot + sup) / 2.0, LAMBDA_FLOOR, None)
                l2a = np.clip((tot - sup) / 2.0, LAMBDA_FLOOR, None)
                g1, g2 = _dc_sample_vec(l1a, l2a, rho, rng)   # DC on per-sim lambdas
            else:
                l1, l2 = _match_lambdas(row.team1, row.team2, row.ground, ratings, params)
                g1, g2 = _dc_sample(l1, l2, rho, n, rng)
            w1, w2, dr = g1 > g2, g2 > g1, g1 == g2
            pts[:, i] += w1 * 3 + dr; pts[:, j] += w2 * 3 + dr
            gd[:, i] += g1 - g2;      gd[:, j] += g2 - g1
            gf[:, i] += g1;           gf[:, j] += g2
            if return_detail:
                matches.append((L, wc2026_teams.canonical(row.team1),
                                wc2026_teams.canonical(row.team2),
                                np.sign(g1 - g2).astype(np.int8)))

        order = np.argsort(-_rank_key(pts, gd, gf, rng), axis=1)  # col0 = 1st place
        place = np.empty((n, k), dtype=int)                       # team-local-idx -> finishing place
        for r in range(k):
            place[rows, order[:, r]] = r

        for li, t in enumerate(canon):
            rec = out.setdefault(t, {"p1": 0, "p2": 0, "p3": 0, "p4": 0, "padv": 0, "p3adv": 0, "group": L})
            pl = place[:, li]
            rec["p1"] += int(np.sum(pl == 0)); rec["p2"] += int(np.sum(pl == 1))
            rec["p3"] += int(np.sum(pl == 2)); rec["p4"] += int(np.sum(pl == 3))
            rec["padv"] += int(np.sum(pl <= 1))            # top two: automatic
            pos[:, gidx[t]] = pl
            adv_mat[pl <= 1, gidx[t]] = True

        third_local = order[:, 2]
        thirds_team_cols.append(np.array(canon)[third_local])
        thirds_pts_cols.append(pts[rows, third_local].astype(int))
        thirds_gidx_cols.append(np.array([gidx[c] for c in canon])[third_local])
        thirds_key_cols.append(_rank_key(pts[rows, third_local], gd[rows, third_local],
                                         gf[rows, third_local], rng))

    # Across the 12 groups, the eight best third-placed teams also advance.
    K = np.stack(thirds_key_cols, axis=1)            # (n, 12)
    T = np.stack(thirds_team_cols, axis=1)           # (n, 12)
    P = np.stack(thirds_pts_cols, axis=1)            # (n, 12) third's points
    GI = np.stack(thirds_gidx_cols, axis=1)          # (n, 12) third's global index
    order12 = np.argsort(-K, axis=1)
    best8 = order12[:, :8]
    for s in range(n):
        for c in best8[s]:
            t = T[s, c]
            out[t]["padv"] += 1
            out[t]["p3adv"] += 1
            adv_mat[s, GI[s, c]] = True

    cutline = P[rows, order12[:, 7]]                 # 8th-best third: the last in
    missed = P[rows, order12[:, 8]]                  # 9th third: first out

    for t, rec in out.items():
        for kf in ("p1", "p2", "p3", "p4", "padv", "p3adv"):
            rec[kf] = rec[kf] / n
        rec["top2"] = rec["p1"] + rec["p2"]
    if not return_detail:
        return out
    detail = {"teams": all_canon, "gidx": gidx, "adv_mat": adv_mat, "pos": pos,
              "matches": matches, "cutline": cutline, "missed": missed, "eps": eps}
    return out, detail
