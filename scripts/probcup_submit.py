#!/usr/bin/env python3
"""Probability Cup — MODEL bot (Bot 1).

Prices the goal-based markets the xResidual scoreline model owns — the match-winner
question and the total-goals line — for every open match, and submits them to the Jump
Trading Probability Cup via the SP_API_KEY bot. Markets the model does not price (team
stats, cards, player props) are left untouched; those are the second bot's job.

  python scripts/probcup_submit.py            # dry run: print what it WOULD submit
  python scripts/probcup_submit.py --submit   # actually POST predictions

Probabilities: P(team win) and P(total goals <= N) from independent-Poisson rates
(consistent with baseline.make_expectation / skellam). One prediction per market — the
run is idempotent (skips markets already predicted by this bot; use --update to PATCH).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from scipy.stats import poisson, skellam

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import baseline, data, elo, wc2026_teams as W  # noqa: E402
from blend import blended_ratings  # noqa: E402

BASE = "https://api.sportspredict.com/api/v1"
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")


def load_key(name="SP_API_KEY"):
    for l in open(os.path.join(ROOT, ".env")):
        if l.startswith(name + "="):
            return l.strip().split("=", 1)[1]
    raise SystemExit(f"{name} not in .env")


def call(key, path, method="GET", body=None):
    cmd = ["curl", "-s", "-X", method, BASE + path,
           "-H", f"Authorization: Bearer {key}", "-H", "Content-Type: application/json"]
    if body:
        cmd += ["-d", json.dumps(body)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=40).stdout
    try:
        return json.loads(out)
    except Exception:
        return out[:300]


def fixture_utc(date, t):
    m = re.match(r"(\d+):(\d+)\s*UTC([+-]\d+)", str(t))
    if not m:
        return None
    hh, mm, off = int(m.group(1)), int(m.group(2)), int(m.group(3))
    local = datetime.fromisoformat(f"{date}T{hh:02d}:{mm:02d}:00")
    return (local - timedelta(hours=off)).replace(tzinfo=timezone.utc)  # local -> UTC


H2_SHARE, H1_SHARE = 0.53, 0.47   # empirical 2nd/1st-half share of match goals


def _eid(t):
    return W.elo_name(W.canonical(t))


def _btts_and_total(lh, la, n, kmax=16):
    """P(home>=1 AND away>=1 AND home+away>=n)."""
    ph, pa = poisson.pmf(np.arange(kmax + 1), lh), poisson.pmf(np.arange(kmax + 1), la)
    s = 0.0
    for i in range(1, kmax + 1):
        for j in range(1, kmax + 1):
            if i + j >= n:
                s += ph[i] * pa[j]
    return float(s)


def price_market(question, t1, t2, exp):
    """Return a 0-1 probability for any GOAL-DERIVED market (priced from the Poisson
    scoreline distribution), else None. Half markets use an empirical 47/53 goal split."""
    lh, la = exp.lambda_home, exp.lambda_away          # t1 = home, t2 = away
    lt = lh + la
    id1, id2 = _eid(t1), _eid(t2)
    q = question.strip()

    def side(name):                                    # -> (lam_for, lam_against, p_win) or None
        e = _eid(name)
        if e == id1:
            return lh, la, exp.p_home
        if e == id2:
            return la, lh, exp.p_away
        return None

    m = re.match(r"will (.+?) win the match\b", q, re.I)                      # match winner
    if m:
        s = side(m.group(1).strip()); return s[2] if s else None
    m = re.match(r"will the match have (\d+) or (fewer|more) total goals", q, re.I)  # full total
    if m:
        n = int(m.group(1))
        return float(poisson.cdf(n, lt)) if m.group(2).lower() == "fewer" else float(poisson.sf(n - 1, lt))
    m = re.match(r"will both teams score and the match have (\d+) or more total goals", q, re.I)
    if m:
        return _btts_and_total(lh, la, int(m.group(1)))
    m = (re.match(r"will (.+?) score at least (\d+) goal", q, re.I)
         or re.match(r"will (.+?) score (\d+) or more total goals", q, re.I))   # team goals >= N
    if m:
        s = side(m.group(1).strip()); return float(poisson.sf(int(m.group(2)) - 1, s[0])) if s else None
    m = re.match(r"will (.+?) score in the (second|first) half", q, re.I)        # team scores in half
    if m:
        s = side(m.group(1).strip())
        return float(1 - np.exp(-s[0] * (H2_SHARE if m.group(2).lower() == "second" else H1_SHARE))) if s else None
    m = re.match(r"will the second half have (\d+) or more total goals", q, re.I)
    if m:
        return float(poisson.sf(int(m.group(1)) - 1, lt * H2_SHARE))
    if re.match(r"(at halftime, will the match be tied|will the match be tied at halftime)", q, re.I):
        return float(skellam.pmf(0, lh * H1_SHARE, la * H1_SHARE))               # 1st-half draw
    m = re.match(r"at halftime, will (.+?) be winning", q, re.I)
    if m:
        s = side(m.group(1).strip()); return float(skellam.sf(0, s[0] * H1_SHARE, s[1] * H1_SHARE)) if s else None
    m = re.match(r"will (.+?) score more goals than (.+?) in the second half", q, re.I)
    if m:
        s = side(m.group(1).strip()); return float(skellam.sf(0, s[0] * H2_SHARE, s[1] * H2_SHARE)) if s else None
    if re.match(r"will the second half have more (total )?goals than the first half", q, re.I):
        return float(skellam.sf(0, lt * H2_SHARE, lt * H1_SHARE))                # H2 > H1
    return None


def clamp(p):
    return max(1, min(99, int(round(p * 100))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--submit", action="store_true", help="actually POST predictions")
    ap.add_argument("--update", action="store_true", help="PATCH markets already predicted")
    args = ap.parse_args()

    key = load_key("SP_API_KEY")
    res = elo.build_ratings(data.load_results())
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)
    rt = lambda t: ratings.get(W.elo_name(W.canonical(t)), elo.INIT_RATING)

    fx = pd.read_csv(FIXTURES)
    fxmap = {}
    for r in fx.itertuples(index=False):
        u = fixture_utc(r.date, r.time)
        if u is not None:
            fxmap[u.strftime("%Y-%m-%dT%H:%M")] = (r.team1, r.team2)

    ev = call(key, "/events?limit=100")
    eid = next(e["id"] for e in ev if "Probability Cup" in e.get("title", ""))
    lob = call(key, f"/lobbies?event_id={eid}")
    lid = lob[0]["id"]
    if not lob[0].get("joined"):
        call(key, f"/lobbies/{lid}/join", "POST")
    allmk = call(key, f"/markets?lobby_id={lid}")             # all open markets in ONE call
    preds = call(key, f"/predictions?lobby_id={lid}")
    if not isinstance(allmk, list):
        raise SystemExit(f"markets fetch failed: {allmk}")
    mine = {p["market_id"] for p in preds if isinstance(p, dict)} if isinstance(preds, list) else set()

    bym = {}
    for mk in allmk:
        bym.setdefault(mk["match"]["id"], []).append(mk)

    todo, skipped, unmatched, n_match = [], 0, [], 0
    for mid, mks in bym.items():
        match = mks[0]["match"]
        teams = fxmap.get(match.get("opening_time", "")[:16])
        if not teams:
            unmatched.append((match.get("name"), match.get("opening_time", "")[:16]))
            continue
        n_match += 1
        t1, t2 = teams
        exp = baseline.make_expectation(t1, t2, {t1: rt(t1), t2: rt(t2)}, params, neutral=True)
        lam_tot = exp.lambda_home + exp.lambda_away
        for mk in mks:
            p = price_market(mk["question"], t1, t2, exp)
            if p is None:
                continue
            if mk["id"] in mine and not args.update:
                skipped += 1
                continue
            todo.append({"market_id": mk["id"], "lobby_id": lid, "probability": clamp(p),
                         "_q": mk["question"], "_m": match.get("name")})

    print(f"matched {n_match}/{len(bym)} matches · {len(todo)} markets to price · {skipped} already done")
    if unmatched:
        print("  UNMATCHED:", unmatched[:6])
    for t in todo[:24]:
        print(f"  [{t['_m']:<16}] {t['probability']:>2}%  {t['_q']}")
    if len(todo) > 24:
        print(f"  ... +{len(todo) - 24} more")

    if not args.submit:
        print("\nDRY RUN — re-run with --submit to post these.")
        return
    sub = [{k: t[k] for k in ("market_id", "lobby_id", "probability")} for t in todo]
    ok = 0
    for i in range(0, len(sub), 50):
        r = call(key, "/predictions/batch", "POST", {"predictions": sub[i:i + 50]})
        ok += r.get("succeeded", 0) if isinstance(r, dict) else 0
    print(f"submitted: {ok}/{len(sub)} succeeded")


if __name__ == "__main__":
    main()
