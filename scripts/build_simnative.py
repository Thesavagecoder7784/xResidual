#!/usr/bin/env python3
"""Sim-native Polymarket markets: ones our joint tournament Monte Carlo prices for free,
but the market must quote in isolation (so they can drift from a coherent distribution).

    python scripts/build_simnative.py

Four families, all read off ONE consistent simulation (same group + knockout draw the
elimination / reach-round cards use):

  1. group-of-champion        P(the eventual champion came from group X)        — 12 legs
  2. furthest-advancing-<conf>  which nation of a confederation goes deepest     — per conf
  3. worst-placed-<conf>        which nation of a confederation finishes lowest   — per conf
  4. total-tournament-goals     P(total goals over/under the listed line)         — 1 line

(1)-(3) come straight off the per-sim joint outcome (champion's group; each team's depth
and finishing place), which marginal reach probabilities cannot express. (4) needs goals
in the knockout rounds, which the advancement engine doesn't model (it resolves ties by
the Elo expected score). So we DECOUPLE: advancement stays Elo-based (untouched, validated),
and we separately sample a Dixon-Coles scoreline for each knockout match that the bracket
actually played, plus extra-time goals when regulation is drawn (shootout goals never count
toward a totals line). The goal sum is over all 104 matches (72 group + 31 bracket + the
third-place playoff).

Pro-market framing: a gap is a candidate to investigate, never proof the market is wrong.
Tie-heavy legs (furthest/worst, where the market has an explicit wins->goals tiebreak we
approximate by splitting tied-deepest teams equally) are reported with their tie rate so the
softness of the comparison is visible. The totals line carries goal-model + extra-time
assumptions and should clear the same out-of-sample bar as any totals edge before it's acted on.
"""
from __future__ import annotations

import ast
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import baseline, data, elo, group_sim, knockout, venues_wc2026, wc2026_teams as W  # noqa: E402
from xresidual.baseline import LAMBDA_FLOOR  # noqa: E402
from blend import blended_ratings  # noqa: E402
from prediction_board import wc_played_results  # noqa: E402

OUT = os.path.join(ROOT, "viz", "model", "_simnative.js")
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
N = 60000
SEED = 7

# market team name -> our canonical name (only the spellings that differ)
ALIAS = {"Türkiye": "Turkey", "Czechia": "Czech Republic",
         "Bosnia and Herzegovina": "Bosnia & Herzegovina", "United States": "USA"}
PLACEHOLDER = {"Country A", "Other", "Field", "Any other team"}

CONF_SLUGS = {
    "CAF": "world-cup-furthest-advancing-caf-nation",
    "UEFA": "world-cup-furthest-advancing-uefa-nation",
    "AFC": "world-cup-furthest-advancing-afc-nation",
    "CONCACAF host": "world-cup-furthest-advancing-host-nation",
    "CONCACAF non-host": "world-cup-furthest-advancing-non-host-concacaf-nation",
}
WORST_SLUGS = {
    "UEFA": "world-cup-worst-placed-uefa-nation-20260605230132680",
    "CAF": "world-cup-worst-placed-caf-nation",
    "CONMEBOL": "world-cup-worst-placed-conmebol-nation-20260605230144897",
    "AFC": "world-cup-worst-placed-afc-nation",
    "CONCACAF host": "world-cup-worst-placed-host-nation-20260605174221892",
    "CONCACAF non-host": "world-cup-worst-placed-non-host-concacaf-nation-20260605201215810",
}
GROUP_CHAMP_SLUG = "world-cup-group-of-champion-20260605001357294"


def gamma_event(slug: str) -> dict | None:
    try:
        r = requests.get("https://gamma-api.polymarket.com/events",
                         params={"slug": slug}, timeout=20).json()
        e = r[0] if isinstance(r, list) and r else r
        return e if isinstance(e, dict) else None
    except Exception:
        return None


def yes_prices(ev: dict) -> dict:
    """{market team-title -> Yes price}, placeholders dropped."""
    out = {}
    for m in ev.get("markets", []):
        title = m.get("groupItemTitle")
        if not title or title in PLACEHOLDER:
            continue
        pr = m.get("outcomePrices")
        pr = ast.literal_eval(pr) if isinstance(pr, str) else pr
        if pr:
            try:
                out[title] = float(pr[0])
            except (TypeError, ValueError):
                pass
    return out


def devig(prices: dict) -> dict:
    """Normalise mutually-exclusive Yes legs to sum to 1 (multiplicative de-vig)."""
    s = sum(prices.values()) or 1.0
    return {k: v / s for k, v in prices.items()}, round((s - 1) * 100, 1)


def _neutral_lambdas(r1, r2, params):
    """Per-sim DC Poisson rates for a neutral-venue knockout match (no host adv/altitude)."""
    sup = params.beta * ((r1 - r2) / 100.0)
    l1 = np.clip((params.total_goals + sup) / 2.0, LAMBDA_FLOOR, None)
    l2 = np.clip((params.total_goals - sup) / 2.0, LAMBDA_FLOOR, None)
    return l1, l2


def knockout_goals(matchups, third_pair, rating_arr, eps, params, rho, rng) -> np.ndarray:
    """Total goals over all knockout matches per sim: regulation DC scoreline + extra time
    (30 min ~ 1/3 of the rate) when regulation is drawn; shootout goals never counted."""
    n = rating_arr.shape[0] if eps is None else eps.shape[0]
    rounds = [matchups["R32"], matchups["R16"], matchups["QF"], matchups["SF"],
              matchups["Final"], third_pair]
    rr = np.arange(third_pair.shape[0])
    total = np.zeros(third_pair.shape[0], dtype=np.int64)
    for pairs in rounds:                                  # (n, m, 2) global team indices
        for c in range(pairs.shape[1]):
            a, b = pairs[:, c, 0], pairs[:, c, 1]
            r1, r2 = rating_arr[a].astype(float), rating_arr[b].astype(float)
            if eps is not None:
                r1 = r1 + eps[rr, a]; r2 = r2 + eps[rr, b]
            l1, l2 = _neutral_lambdas(r1, r2, params)
            g1, g2 = group_sim._dc_sample_vec(l1, l2, rho, rng)
            total += g1 + g2
            drawn = g1 == g2                              # regulation draw -> extra time
            if drawn.any():
                e1, e2 = group_sim._dc_sample_vec(l1[drawn] / 3.0, l2[drawn] / 3.0, rho, rng)
                total[drawn] += e1 + e2
    return total


def conf_credit(rank_key, primary, member_cols, pick_max: bool):
    """Resolve the confederation winner per sim with the market's FULL tie-break baked into
    `rank_key` (latest stage -> most wins -> most goals -> fewest conceded, + lots jitter),
    so there is exactly one winner per sim (no equal-split bias). `primary` is the headline
    criterion only (depth for furthest, finish for worst), used to REPORT how often the
    tie-break was actually invoked (>=2 members share the primary extremum)."""
    cols = np.array(member_cols)
    sub = rank_key[:, cols]
    pick = sub.argmax(axis=1) if pick_max else sub.argmin(axis=1)   # unique (jitter breaks ties)
    counts = np.bincount(pick, minlength=len(cols)).astype(float)
    p = sub.shape[0]
    psub = primary[:, cols]
    ext = psub.max(axis=1, keepdims=True) if pick_max else psub.min(axis=1, keepdims=True)
    tie_rate = float(((psub == ext).sum(axis=1) > 1).mean())        # primary-criterion ties
    return counts / p, tie_rate


def main() -> int:
    print(f"simulating the tournament (n={N}) ...")
    df = data.load_results()
    res = elo.build_ratings(df)
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)                # Elo + squad value (Finding #10)
    fx = pd.read_csv(FIXTURES)
    grp_results = wc_played_results(df, fx)               # condition on games played (was UNCONDITIONED)
    out, det = group_sim.simulate(fx, ratings, params, n=N, seed=SEED,
                                  return_detail=True, sigma=group_sim.MODEL_SIGMA, results=grp_results)
    ko = knockout.simulate(det, out, ratings, return_paths=True,
                           return_matchups=True, return_slots=True,
                           results=knockout.played_ko_results(det, fx))
    teams = ko["teams_arr"]; gidx = det["gidx"]; rating_arr = ko["rating_arr"]
    pos = det["pos"]; adv = det["adv_mat"]; eps = det.get("eps")
    paths = ko["paths"]; n = pos.shape[0]; rows = np.arange(n)
    name = np.array(teams)

    # --- per-sim tournament DEPTH (deepest round reached) and FINISH score ---------------
    # depth: 1 reached R32 (advanced), 2 R16, 3 QF, 4 SF, 5 Final, 6 champion; 0 = group exit.
    depth = np.zeros((n, len(teams)), dtype=np.int8)
    depth[adv] = 1
    for arr, dv in [(paths["w32"], 2), (paths["w16"], 3), (paths["wqf"], 4),
                    (paths["wsf"], 5), (paths["champ"], 6)]:
        for c in range(arr.shape[1]):
            depth[rows, arr[:, c]] = dv
    # finish score (higher = better): depth dominates; within group exits, place breaks it
    # (4th < 3rd). pos is 0..3 (1st..4th) for that team's group, 9 if not applicable.
    place = np.where(pos == 9, 3, pos)                     # treat the unused as worst
    finish = depth.astype(np.int32) * 4 + (3 - place)

    # The market's exact resolution order, encoded as one sortable key per (sim, team):
    #   furthest: latest stage -> most TOTAL wins -> most goals for -> fewest conceded -> lots
    #   worst:    lowest finish -> fewest wins -> fewest goals -> most conceded -> lots
    # total wins = group wins + knockout wins (a team reaching depth d won d-1 knockout ties).
    # Goals/conceded use the group stage (knockout goals are unmodeled; they only matter in
    # the third-order tie where wins AND group goals also tie, which is vanishingly rare).
    ko_wins = np.clip(depth.astype(np.int32) - 1, 0, None)
    total_wins = det["wins"].astype(np.int32) + ko_wins
    gf = det["gf"].astype(np.int32); ga = det["ga"].astype(np.int32)
    jit = np.random.default_rng(SEED + 2).random((n, len(teams))) * 0.5
    furthest_key = (depth.astype(np.float64) * 1e9 + total_wins * 1e6
                    + gf * 1e3 - ga + jit)
    worst_key = (finish.astype(np.float64) * 1e9 + total_wins * 1e6
                 + gf * 1e3 - ga + jit)

    champ_group = name[paths["champ"][:, 0]]               # champion's team, per sim

    # --- total tournament goals ----------------------------------------------------------
    rng = np.random.default_rng(SEED + 1)
    sfp = ko["matchups"]["SF"]                              # (n,2,2) the two SF pairings
    wsf = paths["wsf"]                                     # (n,2) SF winners
    # third-place playoff: the two SF losers
    loser = np.where(sfp[:, :, 0] == wsf, sfp[:, :, 1], sfp[:, :, 0])  # (n,2)
    third_pair = np.stack([loser[:, 0], loser[:, 1]], axis=1)[:, None, :]  # (n,1,2)
    ko_goals = knockout_goals(ko["matchups"], third_pair, rating_arr, eps,
                              params, group_sim.DC_RHO, rng)
    total_goals = det["group_goals"].astype(np.int64) + ko_goals
    print(f"  model total tournament goals: mean {total_goals.mean():.1f} "
          f"(group {det['group_goals'].mean():.1f} + ko {ko_goals.mean():.1f}), "
          f"median {int(np.median(total_goals))}")

    payload = {"generated": datetime.now(timezone.utc).isoformat(),
               "n_sims": n, "families": []}

    # =====================================================================================
    # 1. group-of-champion
    # =====================================================================================
    ev = gamma_event(GROUP_CHAMP_SLUG)
    if ev:
        # market title -> group letter
        legs = {}
        for m in ev.get("markets", []):
            t = m.get("groupItemTitle") or ""
            if t in PLACEHOLDER or not t.startswith("Group"):
                continue
            pr = m.get("outcomePrices"); pr = ast.literal_eval(pr) if isinstance(pr, str) else pr
            legs[t.split(" ")[1]] = float(pr[0])           # "Group C (...)" -> "C"
        grp_of = {t: out[W.elo_name(W.canonical(t))]["group"] if W.elo_name(W.canonical(t)) in out
                  else out[t]["group"] for t in teams}
        champ_letter = np.array([grp_of[t] for t in champ_group])
        model = {L: round(float((champ_letter == L).mean()) * 100, 1) for L in legs}
        mkt, over = devig(legs)
        rows_out = sorted(({"name": f"Group {L}", "model": model[L],
                            "market": round(mkt[L] * 100, 1),
                            "gap": round((model[L] - mkt[L] * 100), 1)} for L in legs),
                          key=lambda r: -abs(r["gap"]))
        payload["families"].append({"key": "group-of-champion", "title": "Group of the champion",
                                    "overround_pct": over, "tie_rate": 0.0, "rows": rows_out})
        print(f"\ngroup-of-champion (overround {over}%):")
        for r in rows_out[:4]:
            print(f"  {r['name']:9} model {r['model']:5}%  market {r['market']:5}%  gap {r['gap']:+.1f}")

    # =====================================================================================
    # 2 & 3. confederation furthest / worst
    # =====================================================================================
    def price_conf(slug, kind):
        ev = gamma_event(slug)
        if not ev:
            return None
        legs = yes_prices(ev)
        member_cols, titles = [], []
        for title in legs:
            canon = ALIAS.get(title, title)
            col = gidx.get(canon)
            if col is None:                                # try elo-name round trip
                col = gidx.get(W.canonical(canon))
            if col is None:
                print(f"    [skip] {slug.split('-')[3]}: no sim team for '{title}'")
                continue
            member_cols.append(col); titles.append(title)
        if not member_cols:
            return None
        if kind == "furthest":
            credit, tie_rate = conf_credit(furthest_key, depth, member_cols, pick_max=True)
        else:
            credit, tie_rate = conf_credit(worst_key, finish, member_cols, pick_max=False)
        sub_legs = {t: legs[t] for t in titles}
        mkt, over = devig(sub_legs)
        rows_out = sorted(({"name": titles[i], "model": round(float(credit[i]) * 100, 1),
                            "market": round(mkt[titles[i]] * 100, 1),
                            "gap": round(float(credit[i]) * 100 - mkt[titles[i]] * 100, 1)}
                           for i in range(len(titles))), key=lambda r: -abs(r["gap"]))
        return {"overround_pct": over, "tie_rate": round(tie_rate, 3), "rows": rows_out}

    for conf, slug in CONF_SLUGS.items():
        r = price_conf(slug, "furthest")
        if not r:
            continue
        payload["families"].append({"key": f"furthest-{conf}",
                                     "title": f"Furthest-advancing {conf} nation", **r})
        print(f"\nfurthest-advancing {conf} (overround {r['overround_pct']}%, tie-rate {r['tie_rate']}):")
        for x in r["rows"][:4]:
            print(f"  {x['name']:22} model {x['model']:5}%  market {x['market']:5}%  gap {x['gap']:+.1f}")

    for conf, slug in WORST_SLUGS.items():
        r = price_conf(slug, "worst")
        if not r:
            continue
        payload["families"].append({"key": f"worst-{conf}",
                                     "title": f"Worst-placed {conf} nation", **r})
        print(f"\nworst-placed {conf} (overround {r['overround_pct']}%, tie-rate {r['tie_rate']}):")
        for x in r["rows"][:4]:
            print(f"  {x['name']:22} model {x['model']:5}%  market {x['market']:5}%  gap {x['gap']:+.1f}")

    # =====================================================================================
    # 4. total tournament goals over/under
    # =====================================================================================
    tot_ev = gamma_event("world-cup-total-tournament-goals-ou-264pt5-20260608175819175")
    if tot_ev:
        # the event is a single Over/Under market; find the line and the Over price
        line, p_over_mkt = 264.5, None
        for m in tot_ev.get("markets", []):
            pr = m.get("outcomePrices"); pr = ast.literal_eval(pr) if isinstance(pr, str) else pr
            outc = m.get("outcomes"); outc = ast.literal_eval(outc) if isinstance(outc, str) else outc
            if pr and outc:
                d = {o.lower(): float(p) for o, p in zip(outc, pr)}
                p_over_mkt = d.get("over") or d.get("yes")
        p_over_model = float((total_goals > line).mean())
        payload["total_goals"] = {
            "line": line, "model_mean": round(float(total_goals.mean()), 1),
            "model_p_over": round(p_over_model * 100, 1),
            "market_p_over": None if p_over_mkt is None else round(p_over_mkt * 100, 1),
            "gap": None if p_over_mkt is None else round((p_over_model - p_over_mkt) * 100, 1),
            "note": "model goals: group DC scorelines + neutral-venue knockout DC + extra time; "
                    "shootout goals excluded. Carries goal-model + ET assumptions."}
        print(f"\ntotal goals O/U {line}: model P(over) {p_over_model*100:.1f}%  "
              f"market {None if p_over_mkt is None else round(p_over_mkt*100,1)}%")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.SIMNATIVE = " + json.dumps(payload) + ";\n")
    print(f"\nwrote {os.path.relpath(OUT, ROOT)}: {len(payload['families'])} families")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
