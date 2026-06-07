#!/usr/bin/env python3
"""Who won the draw? -> viz/model/_drawluck.js.

    python scripts/build_drawluck.py

Draw luck, done the way the draw-fairness literature does it (Csato 2025): re-run the
ACTUAL 2026 draw many times under its real constraints (four pots of 12, one team per
pot per group, <=1 team per confederation per group except UEFA which allows two, hosts
pre-assigned), and for each team compare its odds of ADVANCING to the Round of 32 in its
REAL group against its mean odds over all the legal random re-draws. The gap is how much
the draw helped or hurt it; the spread across re-draws is how much the draw *mattered*.
Advancing = top two OR one of the eight best third-placed teams, selected jointly across
all 12 groups in each re-draw, so the format's best-third safety net is handled correctly
(it cushions a bad draw). Neutral venue throughout, so this is opponent strength only -
not heat or hosting. Pots are the actual FIFA pots; hosts seeded into Pot 1.
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
from xresidual import baseline, data, elo, group_sim as GS, wc2026_teams as W  # noqa: E402
from xresidual.baseline import LAMBDA_FLOOR  # noqa: E402
from blend import blended_ratings  # noqa: E402
from pull_forecast_data import ISO, KIT, INK, ensure_flag  # noqa: E402

OUT = os.path.join(ROOT, "viz", "model", "_drawluck.js")
GROUPS = list("ABCDEFGHIJKL")
HOSTS = {"USA", "Mexico", "Canada"}
N_DRAWS = 1500          # legal random re-draws for the expected baseline
N_RR = 3000             # sims per group when estimating top-2 odds in a re-draw
N_REAL = 40000          # sims for the realized-group top-2 odds (tighter)

CONFED = {
    "UEFA": ["Spain", "France", "England", "Portugal", "Germany", "Netherlands", "Belgium",
             "Croatia", "Switzerland", "Norway", "Austria", "Sweden", "Turkey", "Scotland",
             "Czech Republic", "Bosnia & Herzegovina"],
    "CONMEBOL": ["Argentina", "Brazil", "Uruguay", "Colombia", "Ecuador", "Paraguay"],
    "CAF": ["Morocco", "Senegal", "Ivory Coast", "Ghana", "Egypt", "Algeria", "Tunisia",
            "South Africa", "DR Congo", "Cape Verde"],
    "CONCACAF": ["USA", "Mexico", "Canada", "Panama", "Haiti", "Curaçao"],
    "AFC": ["Japan", "South Korea", "Iran", "Australia", "Saudi Arabia", "Qatar", "Iraq",
            "Uzbekistan", "Jordan"],
    "OFC": ["New Zealand"],
}
CONFED_OF = {t: c for c, ts in CONFED.items() for t in ts}

# The actual 2026 draw pots (FIFA, by Nov-2025 ranking; hosts seeded into Pot 1).
POTS = [
    ["USA", "Mexico", "Canada", "Spain", "Argentina", "France", "England", "Brazil",
     "Portugal", "Netherlands", "Belgium", "Germany"],
    ["Croatia", "Morocco", "Colombia", "Uruguay", "Switzerland", "Japan", "Senegal",
     "Iran", "South Korea", "Ecuador", "Austria", "Australia"],
    ["Norway", "Panama", "Egypt", "Algeria", "Scotland", "Paraguay", "Tunisia",
     "Ivory Coast", "Uzbekistan", "Qatar", "Saudi Arabia", "South Africa"],
    ["Jordan", "Cape Verde", "Ghana", "Curaçao", "Haiti", "New Zealand", "Czech Republic",
     "Sweden", "Turkey", "Bosnia & Herzegovina", "DR Congo", "Iraq"],
]


def field_advance(groups, rate, n, rng, beta, tot):
    """Per team -> P(advance to R32), simulating the FULL neutral group stage so the
    eight best third-placed teams are selected jointly across all 12 groups (top 2
    auto-qualify; a third advances if its points/GD/GF rank in the best eight thirds).
    Plain Poisson (DC's tweak is negligible for placement). Returns {team: p_advance}."""
    rows = np.arange(n)
    place_of, group_of, third_keys = {}, {}, []
    for gi, gteams in enumerate(groups):
        r4 = [rate(t) for t in gteams]
        k = len(gteams)
        pts = np.zeros((n, k)); gd = np.zeros((n, k)); gf = np.zeros((n, k))
        for i in range(k):
            for j in range(i + 1, k):
                sup = beta * ((r4[i] - r4[j]) / 100.0)
                l1 = max((tot + sup) / 2.0, LAMBDA_FLOOR); l2 = max((tot - sup) / 2.0, LAMBDA_FLOOR)
                g1, g2 = rng.poisson(l1, n), rng.poisson(l2, n)
                w1, w2, dr = g1 > g2, g2 > g1, g1 == g2
                pts[:, i] += w1 * 3 + dr; pts[:, j] += w2 * 3 + dr
                gd[:, i] += g1 - g2; gd[:, j] += g2 - g1
                gf[:, i] += g1; gf[:, j] += g2
        key = pts * 1e7 + (gd + 100.0) * 1e3 + gf + rng.random((n, k)) * 1e-3
        order = np.argsort(-key, axis=1)
        place = np.empty((n, k), dtype=int)
        for r in range(k):
            place[rows, order[:, r]] = r
        for li, t in enumerate(gteams):
            place_of[t] = place[:, li]; group_of[t] = gi
        third_keys.append(key[rows, order[:, 2]])           # the 3rd-placed team's rank key
    best8 = np.argsort(-np.stack(third_keys, axis=1), axis=1)[:, :8]
    third_adv = np.zeros((n, len(groups)), dtype=bool)      # did group gi's third make the best 8?
    np.put_along_axis(third_adv, best8, True, axis=1)
    out = {}
    for t in place_of:
        pl = place_of[t]
        adv = (pl <= 1) | ((pl == 2) & third_adv[:, group_of[t]])
        out[t] = float(adv.mean())
    return out


def random_legal_draw(pots, host_groups, rng):
    """One uniform-ish legal draw: one team per pot per group, <=1 per confederation
    (UEFA <=2), hosts fixed. Constructive with restart on dead ends (FIFA's approach)."""
    for _ in range(800):
        groups = {g: [] for g in GROUPS}
        gconf = {g: {} for g in GROUPS}

        def place(t, g):
            groups[g].append(t); c = CONFED_OF[t]; gconf[g][c] = gconf[g].get(c, 0) + 1

        for t, g in host_groups.items():
            place(t, g)
        seq = [[t for t in pots[0] if t not in host_groups], pots[1], pots[2], pots[3]]
        ok = True
        for need_len, pool in zip((0, 1, 2, 3), seq):
            order = list(pool); rng.shuffle(order)
            for t in order:
                c = CONFED_OF[t]
                lim = 2 if c == "UEFA" else 1
                elig = [g for g in GROUPS if len(groups[g]) == need_len and gconf[g].get(c, 0) < lim]
                if not elig:
                    ok = False; break
                place(t, elig[int(rng.integers(len(elig)))])
            if not ok:
                break
        if ok and all(len(v) == 4 for v in groups.values()):
            return groups
    return None


def main() -> int:
    res = elo.build_ratings(data.load_results())
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)
    fx = pd.read_csv(os.path.join(ROOT, "data", "wc2026_fixtures.csv"))
    grp = fx[fx["group"].astype(str).str.startswith("Group")].copy()
    grp["G"] = grp["group"].str.replace("Group ", "", regex=False).str.strip()

    def rate(t):
        return ratings.get(W.elo_name(W.canonical(t)), elo.INIT_RATING)

    real_groups = {L: sorted(set(grp[grp["G"] == L]["team1"]) | set(grp[grp["G"] == L]["team2"]))
                   for L in sorted(grp["G"].unique())}
    real_groups = {L: [W.canonical(t) for t in ts] for L, ts in real_groups.items()}
    teams = [t for ts in real_groups.values() for t in ts]
    missing = [t for t in teams if t not in CONFED_OF]
    assert not missing, f"no confederation for: {missing}"
    host_groups = {h: L for L, ts in real_groups.items() for h in ts if h in HOSTS}
    pots = POTS
    pot_of = {t: i for i, p in enumerate(pots) for t in p}
    assert set(teams) == set(pot_of), \
        f"pot/fixture mismatch: {set(teams) ^ set(pot_of)}"

    # sanity: the realized groups must be exactly one-team-per-pot (they are, by the draw)
    okc = sum(1 for ts in real_groups.values()
              if sorted(pot_of[t] for t in ts) == [0, 1, 2, 3])
    print(f"{okc}/12 realized groups are exactly one-per-pot (using FIFA's actual pots)")

    rng = np.random.default_rng(13)
    # realized advance odds (full neutral group stage on the actual groups)
    realized = field_advance(list(real_groups.values()), rate, N_REAL, rng,
                             params.beta, params.total_goals)

    # expected advance odds over legal random re-draws of the whole field
    print(f"running {N_DRAWS} legal re-draws ...")
    acc = {t: [] for t in teams}
    fails = 0
    for _ in range(N_DRAWS):
        draw = random_legal_draw(pots, host_groups, rng)
        if draw is None:
            fails += 1; continue
        for t, p in field_advance(list(draw.values()), rate, N_RR, rng,
                                  params.beta, params.total_goals).items():
            acc[t].append(p)
    if fails:
        print(f"  ({fails} draws hit a dead end and were skipped)")

    rows = []
    for t in teams:
        exp = float(np.mean(acc[t])); sd = float(np.std(acc[t]))
        rows.append({
            "team": t, "iso": ISO.get(t, ""), "color": KIT.get(t, INK),
            "group": [L for L, ts in real_groups.items() if t in ts][0],
            "p_adv": round(realized[t] * 100, 1), "p_adv_avg": round(exp * 100, 1),
            "swing": round((realized[t] - exp) * 100, 1), "impact": round(sd * 100, 1),
        })
    rows.sort(key=lambda r: -r["swing"])

    for r in rows:
        ensure_flag(r["iso"])
    payload = {"teams": rows, "n_draws": N_DRAWS, "method": "legal-redraw"}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.DRAWLUCK = " + json.dumps(payload) + ";\n")
    print(f"wrote {os.path.relpath(OUT, ROOT)}")
    print("luckiest:", [(r["team"], r["swing"]) for r in rows[:5]])
    print("unluckiest:", [(r["team"], r["swing"]) for r in rows[-5:]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
