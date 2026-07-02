#!/usr/bin/env python3
"""Fork-forward knockout resolver — the v1 `xresidual/` core stays FROZEN (empty diff); this new
script imports it read-only and fixes the knockout advance probabilities.

v1's knockout tie (xresidual/knockout.play) resolves a whole knockout game as ONE Elo coin-flip
`p = 1/(1+10**((r2-r1)/400))` — no 90'/draw/ET/pens split, no home advantage. That over-credits
favorites (England 79% to beat Mexico vs a ~58% sharp line). This fork resolves it correctly:

  1. 90' win/draw/loss from the SAME goal model v1 uses (group_sim._match_components -> Skellam),
     which already carries home-advantage + altitude — v1's knockout path just threw them away.
  2. A COMPRESSED penalty-shootout: favorites win only ~57% of shootouts, capped ~60% even vs a
     much weaker side (arXiv 2510.17641), so the tie is far closer to a coin-flip than open play.
  3. A tunable co-host home-advantage multiplier (full 0.47-goal HA overstates a co-hosted event).
  4. A logit-SHRINKAGE recalibration toward the sharp bookmaker line, mopping up the residual
     rating miscalibration (squad-value blend over-rates England, under-rates Brazil) the mechanical
     fix can't reach.

Params (kappa, ha_mult, shrink) are CALIBRATED to the sharp line, not hand-set. This is an analysis/
forecast tool; it does NOT touch the committed forward ledger.

    python scripts/knockout_v2.py            # calibrate vs the sharp line, print v1 vs fixed vs sharp
"""
from __future__ import annotations
import os, sys, re
import numpy as np
from scipy.stats import skellam

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "scripts")); sys.path.insert(0, os.path.join(ROOT, "logger"))
from xresidual import data, elo, baseline, group_sim, wc2026_teams  # noqa: E402  (read-only)
from blend import blended_ratings  # noqa: E402

_R, _P, _RAT = None, None, None
def _model():
    global _R, _P, _RAT
    if _RAT is None:
        df = data.load_results(); res = elo.build_ratings(df)
        _P = baseline.calibrate(res.calib); _RAT = blended_ratings(res.ratings)
    return _RAT, _P

def _logit(p): p = min(max(p, 1e-4), 1-1e-4); return np.log(p/(1-p))
def _sig(x): return 1/(1+np.exp(-x))

def probs90(a, b, ground, ha_mult=1.0):
    """90' P(a win), P(draw), P(b win) from v1's goal model, with a scalable home-advantage."""
    rat, params = _model()
    r1, r2, adv, tot = group_sim._match_components(a, b, ground, rat, params)   # v1, read-only
    sup = params.beta * ((r1 - r2 + adv * ha_mult) / 100.0)
    l1 = max((tot + sup) / 2.0, group_sim.LAMBDA_FLOOR); l2 = max((tot - sup) / 2.0, group_sim.LAMBDA_FLOOR)
    return float(1 - skellam.cdf(0, l1, l2)), float(skellam.pmf(0, l1, l2)), float(skellam.cdf(-1, l1, l2))

def corrected_adv(a, b, ground, kappa=0.5, ha_mult=1.0):
    """P(a advances) = P(a win 90') + P(draw) * P(a wins the tie), tie compressed toward 50/50."""
    pa, pd, pb = probs90(a, b, ground, ha_mult)
    share = pa / (pa + pb) if (pa + pb) > 0 else 0.5
    tie = min(max(0.5 + (share - 0.5) * kappa, 0.40), 0.60)   # empirical shootout cap ~57-60%
    return pa + pd * tie

def v1_adv(a, b):
    rat, _ = _model()
    r1 = rat.get(wc2026_teams.elo_name(a), elo.INIT_RATING); r2 = rat.get(wc2026_teams.elo_name(b), elo.INIT_RATING)
    return 1 / (1 + 10 ** ((r2 - r1) / 400.0))

# ---- calibration against the sharp line ----
def calibrate(games):
    """games = [(a, b, ground, sharp_a_adv)]. Grid-search kappa & ha_mult to min MAE vs sharp,
    then fit a logit shrinkage p_cal = sigmoid(alpha + beta*logit(corrected)) to mop up the residual."""
    best = None
    for kappa in np.arange(0.2, 0.75, 0.05):
        for ha in np.arange(0.0, 1.05, 0.1):
            err = np.mean([abs(corrected_adv(a, b, g, kappa, ha) - s) for a, b, g, s in games])
            if best is None or err < best[0]: best = (err, kappa, ha)
    _, kappa, ha = best
    # logit shrinkage on the corrected probs
    X = np.array([_logit(corrected_adv(a, b, g, kappa, ha)) for a, b, g, *_ in games])
    Y = np.array([_logit(s) for *_, s in games])
    beta = float(np.cov(X, Y)[0, 1] / np.var(X)) if np.var(X) > 0 else 1.0
    alpha = float(Y.mean() - beta * X.mean())
    return kappa, ha, alpha, beta

def calibrated_adv(a, b, ground, kappa, ha, alpha, beta):
    return float(_sig(alpha + beta * _logit(corrected_adv(a, b, ground, kappa, ha))))


def main():
    # sharp line + venues for the current knockout games, pulled live
    import envtools, requests
    env = envtools.load_env(); KEY = env.get("ODDSAPI_KEY")
    def norm(s): return re.sub(r'[^a-z0-9]', '', (s or '').lower())
    # ESPN venues
    ven = {}
    e = requests.get("https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard",
                     params={"dates": "20260702-20260712", "limit": 100}, timeout=20).json()
    for evt in e.get("events", []):
        comp = (evt.get("competitions") or [{}])[0]; cs = comp.get("competitors") or []
        v = ((comp.get("venue") or {}).get("address") or {}).get("city", "")
        if len(cs) == 2 and v:
            ven[frozenset((norm(cs[0].get("team", {}).get("displayName")), norm(cs[1].get("team", {}).get("displayName"))))] = v
    # sharp h2h -> advance
    r = requests.get("https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds",
                     params={"apiKey": KEY, "regions": "uk,eu", "markets": "h2h", "oddsFormat": "decimal"}, timeout=20)
    games = []
    for g in r.json():
        h, a = g.get("home_team"), g.get("away_team"); acc = {}; nb = 0
        for bk in g.get("bookmakers", []):
            for m in bk.get("markets", []):
                if m["key"] != "h2h": continue
                o = {x["name"]: x["price"] for x in m["outcomes"] if x.get("price")}
                if len(o) < 3: continue
                tot = sum(1/v for v in o.values()); nb += 1
                for n, v in o.items(): acc[n] = acc.get(n, 0) + (1/v)/tot
        if nb == 0: continue
        acc = {n: v/nb for n, v in acc.items()}; d = acc.get("Draw", 0); s = acc.get(h, 0) + acc.get(a, 0) or 1
        sharp_h = acc.get(h, 0) + d * acc.get(h, 0) / s
        grd = ven.get(frozenset((norm(h), norm(a))), "")
        games.append((h, a, grd, sharp_h))
    kappa, ha, alpha, beta = calibrate(games)
    print(f"calibrated: kappa={kappa:.2f}  co-host HA mult={ha:.2f}  shrinkage beta={beta:.2f} (a={alpha:+.2f})")
    print(f"  (beta<1 => model over-extreme; shrink toward the market)\n")
    print(f"{'game':30s}{'venue':10s}{'v1':>6}{'fixed':>7}{'calib':>7}{'sharp':>7}")
    mv1 = mfx = mcal = 0.0
    for h, a, g, s in games:
        v1 = v1_adv(h, a); fx = corrected_adv(h, a, g, kappa, ha); cal = calibrated_adv(h, a, g, kappa, ha, alpha, beta)
        mv1 += abs(v1-s); mfx += abs(fx-s); mcal += abs(cal-s)
        print(f"{h[:13]+' v '+a[:12]:30s}{(g or 'neutral')[:9]:10s}{v1*100:5.0f}%{fx*100:6.0f}%{cal*100:6.0f}%{s*100:6.0f}%")
    n = len(games)
    print(f"\nMAE vs sharp:  v1 {mv1/n*100:.1f}pp   fixed {mfx/n*100:.1f}pp   calibrated {mcal/n*100:.1f}pp   (n={n})")

if __name__ == "__main__":
    raise SystemExit(main())
