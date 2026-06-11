#!/usr/bin/env python3
"""The prediction board — the model's forecasts, pre-committed and scored against the price.

    python scripts/prediction_board.py            # log a forecast batch + print the board + card
    python scripts/prediction_board.py --score     # score every logged forecast vs the live price (CLV)

The edge is not the model — it's the *proof* the model beats the price, in public. So this
takes the joint-sim probabilities across every WC market (champion, advance, group-winner,
reach-round), pairs each with the live market price, and APPENDS the batch to an append-only,
timestamped ledger (paper/forecasts.jsonl). That ledger is the track record: once logged, a
forecast can't be edited, so the later score is honest.

  forecast mode: snapshot model vs market, log the batch, print the board (title race + the
                 biggest model-vs-market calls), emit viz/market/_predboard.js for the card.
  --score mode:  re-price every open forecast and report Closing-Line-Value — did the market
                 drift TOWARD the model since the forecast? (% positive CLV, mean CLV in bp.)
                 CLV is measurable now, hit-rate-independent; calibration is added as markets
                 resolve. Aim is the derivative markets, where the model has a real shot.

PAPER / measurement only (F-1). Market = live Polymarket mid.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import baseline, data, elo, group_sim, knockout, wc2026_teams  # noqa: E402
from blend import blended_ratings  # noqa: E402
from venue_prices import poly_quotes  # noqa: E402

LEDGER = os.path.join(ROOT, "paper", "forecasts.jsonl")
OUT = os.path.join(ROOT, "viz", "market", "_predboard.js")
GROUPS = list("abcdefghijkl")


def mid(q):
    b, a = q
    return (b + a) / 2 if b is not None and a is not None else None


def wc_played_results(df, fx):
    """{(canon t1, canon t2): (g1, g2)} for GROUP-stage games already played, both
    orientations — so group_sim can fix them to reality and simulate only the rest. This is
    how the model 'learns' from the tournament: as games resolve, the forecast conditions on
    them (and once the group stage is done, the knockout runs on the real bracket)."""
    grp = fx[fx["group"].astype(str).str.startswith("Group")]
    pairs = {frozenset((wc2026_teams.canonical(r.team1), wc2026_teams.canonical(r.team2))) for r in grp.itertuples(index=False)}
    d = df[df["tournament"] == "FIFA World Cup"].copy()
    d = d[pd.to_datetime(d["date"]) >= pd.Timestamp("2026-06-11")]
    out = {}
    for r in d.itertuples(index=False):
        h, a = wc2026_teams.canonical(r.home_team), wc2026_teams.canonical(r.away_team)
        if frozenset((h, a)) not in pairs:
            continue                                       # only condition on group games
        hs, as_ = int(r.home_score), int(r.away_score)
        out[(h, a)] = (hs, as_)
        out[(a, h)] = (as_, hs)
    return out


def model_probs():
    df = data.load_results()
    res = elo.build_ratings(df)
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)
    fx = pd.read_csv(os.path.join(ROOT, "data", "wc2026_fixtures.csv"))
    results = wc_played_results(df, fx)                    # condition on games already played
    sim, det = group_sim.simulate(fx, ratings, params, return_detail=True,
                                  sigma=group_sim.MODEL_SIGMA, results=results)
    reach = knockout.simulate(det, sim, ratings)["reach"]
    return sim, reach


def market_prices():
    pm = {}
    pm["champion"] = {t: mid(q) for t, q in poly_quotes(["world-cup-winner"]).items()}
    pm["advance"] = {t: mid(q) for t, q in poly_quotes(["world-cup-team-to-advance-to-knockout-stages"]).items()}
    pm["group_win"] = {t: mid(q) for t, q in poly_quotes([f"world-cup-group-{g}-winner" for g in GROUPS]).items()}
    pm["reach_qf"] = {t: mid(q) for t, q in poly_quotes(["world-cup-nation-to-reach-quarterfinals"]).items()}
    pm["reach_sf"] = {t: mid(q) for t, q in poly_quotes(["world-cup-nation-to-reach-semifinals"]).items()}
    pm["reach_final"] = {t: mid(q) for t, q in poly_quotes(["world-cup-nation-to-reach-final"]).items()}
    return pm


def build_forecasts(sim, reach, pm):
    """one row per (market, team) where the model and the market both have a number."""
    mp = {"champion": lambda t: reach[t]["win"] / 100, "advance": lambda t: sim[t]["padv"],
          "group_win": lambda t: sim[t]["p1"], "reach_qf": lambda t: reach[t]["qf"] / 100,
          "reach_sf": lambda t: reach[t]["sf"] / 100, "reach_final": lambda t: reach[t]["final"] / 100}
    rows = []
    for mkt, fn in mp.items():
        for t in pm.get(mkt, {}):
            if t not in sim:
                continue
            q, p = fn(t), pm[mkt][t]
            if p is None or q is None:
                continue
            rows.append({"market": mkt, "team": t, "model": round(q, 4),
                         "mkt_at_forecast": round(p, 4), "edge_pp": round((q - p) * 100, 2)})
    return rows


def forecast_mode():
    sim, reach = model_probs()
    pm = market_prices()
    rows = build_forecasts(sim, reach, pm)
    batch = datetime.now(timezone.utc).isoformat()
    with open(LEDGER, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({"batch": batch, "ts_ms": int(time.time() * 1000), **r}) + "\n")

    title = sorted([r for r in rows if r["market"] == "champion"], key=lambda r: -r["model"])[:10]
    calls = sorted(rows, key=lambda r: -abs(r["edge_pp"]))[:16]
    print(f"=== xResidual prediction board · {batch[:19]}Z · {len(rows)} forecasts logged ===\n")
    print("TITLE RACE (model champion % vs market):")
    for r in title:
        print(f"   {r['team']:<14} model {r['model']*100:5.1f}%   market {r['mkt_at_forecast']*100:5.1f}%   {r['edge_pp']:+5.1f}pp")
    print("\nBIGGEST CALLS (where the model most disagrees with the price):")
    for r in calls:
        side = "model HIGHER" if r["edge_pp"] > 0 else "model LOWER"
        print(f"   {r['market']:<11} {r['team']:<14} {r['model']*100:5.1f}% vs {r['mkt_at_forecast']*100:5.1f}%  "
              f"{r['edge_pp']:+5.1f}pp  ({side})")

    payload = {"asof": batch, "n": len(rows),
               "title_race": [{"team": r["team"], "iso": wc2026_teams.iso(r["team"]) if hasattr(wc2026_teams, "iso") else "",
                               "model": round(r["model"] * 100, 1), "market": round(r["mkt_at_forecast"] * 100, 1),
                               "edge": r["edge_pp"]} for r in title],
               "calls": [{"market": r["market"], "team": r["team"], "model": round(r["model"] * 100, 1),
                          "price": round(r["mkt_at_forecast"] * 100, 1), "edge": r["edge_pp"]} for r in calls]}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.PREDBOARD = " + json.dumps(payload) + ";\n")
    print(f"\nlogged batch to {os.path.relpath(LEDGER, ROOT)} · wrote {os.path.relpath(OUT, ROOT)}")
    print("PAPER / pre-committed. Run --score any time to see CLV vs the live price.")
    return 0


def score_mode():
    if not os.path.exists(LEDGER):
        print("no forecasts logged yet — run without --score first.")
        return 1
    led = [json.loads(l) for l in open(LEDGER, encoding="utf-8")]
    pm = market_prices()
    scored = []
    for r in led:
        now_p = pm.get(r["market"], {}).get(r["team"])
        if now_p is None:
            continue
        # CLV: did the market move TOWARD the model since the forecast? signed by edge direction.
        drift = (now_p - r["mkt_at_forecast"]) * (1 if r["model"] > r["mkt_at_forecast"] else -1)
        scored.append({**r, "now": now_p, "clv_pp": drift * 100})
    if not scored:
        print("no logged forecasts could be re-priced (markets not live?).")
        return 0
    pos = sum(1 for s in scored if s["clv_pp"] > 0)
    mean_clv = sum(s["clv_pp"] for s in scored) / len(scored)
    print(f"=== CLV scoreboard · {len(scored)} forecasts re-priced ===")
    print(f"   positive CLV: {pos}/{len(scored)} ({pos/len(scored)*100:.0f}%)   mean CLV {mean_clv:+.2f}pp")
    print("   (positive = market drifted toward the model since the forecast = skill signal,")
    print("    hit-rate-independent. Calibration vs outcomes is added as markets resolve.)")
    for s in sorted(scored, key=lambda s: -s["clv_pp"])[:8]:
        print(f"   +{s['clv_pp']:5.2f}pp  {s['market']:<11} {s['team']:<14} "
              f"forecast {s['mkt_at_forecast']*100:.1f}% -> now {s['now']*100:.1f}%  (model {s['model']*100:.1f}%)")
    return 0


def _resolve_outcomes(led):
    """Determine the realized outcome (1/0) for each logged forecast from actual 2026 WC
    results, where the market has resolved; else None. Defensive — any failure -> None."""
    fx = pd.read_csv(os.path.join(ROOT, "data", "wc2026_fixtures.csv"))
    fx["date"] = pd.to_datetime(fx["date"])
    grp = fx[fx["group"].astype(str).str.startswith("Group")]
    tg = {}
    for r in grp.itertuples(index=False):
        tg[wc2026_teams.canonical(r.team1)] = str(r.group)
        tg[wc2026_teams.canonical(r.team2)] = str(r.group)
    group_end = grp["date"].max()
    ko = fx[~fx["group"].astype(str).str.startswith("Group")]

    def window(substr):
        s = ko[ko["round"].astype(str).str.contains(substr, case=False, na=False)]
        return (s["date"].min(), s["date"].max()) if len(s) else (None, None)
    win = {"reach_qf": window("quarter"), "reach_sf": window("semi"), "reach_final": window("final")}

    df = data.load_results()
    df = df[df["tournament"] == "FIFA World Cup"].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"] >= pd.Timestamp("2026-06-11")]
    if df.empty:
        return {}
    df["h"] = df["home_team"].map(wc2026_teams.canonical)
    df["a"] = df["away_team"].map(wc2026_teams.canonical)
    now = df["date"].max()
    ko_done = now > group_end                       # group stage complete?

    def in_window(team, w):
        lo, hi = w
        if lo is None or now < lo:
            return None                              # round not started -> unresolved
        m = df[((df.h == team) | (df.a == team)) & (df.date >= lo) & (df.date <= hi)]
        return 1 if len(m) else (0 if now > hi else None)

    def group_standings(letter):
        sub = df[(df.date <= group_end) & (df.h.map(tg).eq(letter) | df.a.map(tg).eq(letter))]
        teams = [t for t in tg if tg[t] == letter]
        if sub.shape[0] < 6:                          # group not complete (6 matches/group)
            return None
        pts = {t: [0, 0, 0] for t in teams}           # [pts, gd, gf]
        for r in sub.itertuples(index=False):
            hs, as_ = int(r.home_score), int(r.away_score)
            for t, gf, ga in ((r.h, hs, as_), (r.a, as_, hs)):
                if t not in pts:
                    continue
                pts[t][0] += 3 if gf > ga else (1 if gf == ga else 0)
                pts[t][1] += gf - ga
                pts[t][2] += gf
        return sorted(teams, key=lambda t: pts[t], reverse=True)

    out = {}
    for i, r in enumerate(led):
        t, mkt = r["team"], r["market"]
        try:
            if mkt == "advance":
                out[i] = (1 if len(df[((df.h == t) | (df.a == t)) & (df.date > group_end)]) else 0) if ko_done else None
            elif mkt == "group_win":
                st = group_standings(tg.get(t))
                out[i] = (1 if st and st[0] == t else 0) if st else None
            elif mkt in win:
                out[i] = in_window(t, win[mkt])
            elif mkt == "champion":
                fl = df[(df.date >= (win["reach_final"][0] or now)) & (df.date <= now)]
                if win["reach_final"][0] and now >= win["reach_final"][0] and len(fl):
                    g = fl.iloc[-1]
                    w = g["h"] if g["home_score"] > g["away_score"] else g["a"]
                    out[i] = 1 if t == w else 0
                else:
                    out[i] = None
            else:
                out[i] = None
        except Exception:
            out[i] = None
    return out


def calibrate_mode():
    if not os.path.exists(LEDGER):
        print("no forecasts logged yet — run without flags first.")
        return 1
    led = [json.loads(l) for l in open(LEDGER, encoding="utf-8")]
    res = _resolve_outcomes(led)
    pairs = [(led[i]["model"], y) for i, y in res.items() if y is not None]
    if not pairs:
        print("calibration: 0 resolved markets yet — pending until 2026 WC results land "
              "(group-stage markets resolve ~Jun 27, knockout rounds after). The forecasts are "
              "already locked in the ledger, so the grade will be honest when it comes.")
        return 0
    import numpy as np
    p = np.array([a for a, _ in pairs]); y = np.array([b for _, b in pairs], dtype=float)
    brier = float(np.mean((p - y) ** 2))
    eps = 1e-12
    logloss = float(np.mean(-(y * np.log(np.clip(p, eps, 1)) + (1 - y) * np.log(np.clip(1 - p, eps, 1)))))
    base = float(y.mean())
    bss = 1 - brier / (base * (1 - base) + eps)       # Brier skill vs base rate
    print(f"=== calibration · {len(pairs)} resolved forecasts ===")
    print(f"   Brier {brier:.4f}   log-loss {logloss:.4f}   Brier-skill vs base {bss:+.1%}   base rate {base:.1%}")
    print("   reliability (model bucket -> realized):")
    for lo in (0.0, 0.2, 0.4, 0.6, 0.8):
        m = (p >= lo) & (p < lo + 0.2)
        if m.sum():
            print(f"     {int(lo*100):>3}-{int(lo*100)+20:>3}%  predicted {p[m].mean()*100:5.1f}%  "
                  f"actual {y[m].mean()*100:5.1f}%  (n={int(m.sum())})")
    return 0


def main() -> int:
    if "--score" in sys.argv:
        return score_mode()
    if "--calibrate" in sys.argv:
        return calibrate_mode()
    return forecast_mode()


if __name__ == "__main__":
    raise SystemExit(main())
