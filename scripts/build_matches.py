#!/usr/bin/env python3
"""Per-game group-stage predictions -> docs/data/matches.json (+ committed ledger).

    python scripts/build_matches.py

Predicts all 72 group-stage games with the model (W/D/L from the Elo + goal model), commits
each prediction once to an append-only ledger (so it's pre-registered and point-in-time), and
joins the actual result as each game is played — with the running match-level accuracy and
log-loss. Feeds the dashboard's group-stage board.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from xresidual import baseline, data, elo, wc2026_teams  # noqa: E402
from blend import blended_ratings  # noqa: E402

LEDGER = os.path.join(ROOT, "paper", "match_forecasts.jsonl")
OUT = os.path.join(ROOT, "docs", "data", "matches.js")  # JS global (loads via <script src>)
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")


def main() -> int:
    df = data.load_results()
    res = elo.build_ratings(df)
    params = baseline.calibrate(res.calib)
    ratings = blended_ratings(res.ratings)

    def rt(team):
        return ratings.get(wc2026_teams.elo_name(wc2026_teams.canonical(team)), elo.INIT_RATING)

    fx = pd.read_csv(FIXTURES)
    grp = fx[fx["group"].astype(str).str.startswith("Group")].copy()

    # committed predictions (append-only, point-in-time): commit any group game not yet logged
    committed = {}
    if os.path.exists(LEDGER):
        for l in open(LEDGER, encoding="utf-8"):
            r = json.loads(l)
            committed[r["key"]] = r
    new = 0
    for row in grp.itertuples(index=False):
        key = f"{row.date}|{wc2026_teams.canonical(row.team1)}|{wc2026_teams.canonical(row.team2)}"
        if key in committed:
            continue
        t1, t2 = row.team1, row.team2
        exp = baseline.make_expectation(t1, t2, {t1: rt(t1), t2: rt(t2)}, params, neutral=True)
        rec = {"key": key, "committed": datetime.now(timezone.utc).isoformat(),
               "md": str(row.round), "group": str(row.group).replace("Group ", ""),
               "date": str(row.date), "t1": wc2026_teams.canonical(t1), "t2": wc2026_teams.canonical(t2),
               "p1": round(exp.p_home, 4), "pd": round(exp.p_draw, 4), "p2": round(exp.p_away, 4)}
        committed[key] = rec
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        new += 1

    # actual results: join WC 2026 group games by canonical team pair (orientation-aware)
    d = df[df["tournament"] == "FIFA World Cup"].copy()
    d = d[pd.to_datetime(d["date"]) >= pd.Timestamp("2026-06-11")]
    actual = {}
    for r in d.itertuples(index=False):
        h, a = wc2026_teams.canonical(r.home_team), wc2026_teams.canonical(r.away_team)
        actual[frozenset((h, a))] = (h, a, int(r.home_score), int(r.away_score))

    matches, n_played, hits, ll = [], 0, 0, 0.0
    for rec in sorted(committed.values(), key=lambda r: (r["date"], r["group"])):
        probs = {"t1": rec["p1"], "draw": rec["pd"], "t2": rec["p2"]}
        fav = max(probs, key=probs.get)
        m = {**{k: rec[k] for k in ("md", "group", "date", "t1", "t2", "p1", "pd", "p2")},
             "fav": fav, "played": False}
        res_ = actual.get(frozenset((rec["t1"], rec["t2"])))
        if res_:
            h, a, hs, as_ = res_
            s1, s2 = (hs, as_) if h == rec["t1"] else (as_, hs)   # orient to committed t1/t2
            outcome = "t1" if s1 > s2 else ("t2" if s2 > s1 else "draw")
            p_act = {"t1": rec["p1"], "draw": rec["pd"], "t2": rec["p2"]}[outcome]
            m.update({"played": True, "s1": s1, "s2": s2, "result": outcome,
                      "model_p": round(p_act, 3), "correct": (fav == outcome)})
            n_played += 1
            hits += (fav == outcome)
            ll += -__import__("math").log(max(p_act, 1e-9))
        matches.append(m)

    payload = {"asof": datetime.now(timezone.utc).isoformat(), "n": len(matches), "played": n_played,
               "accuracy": round(hits / n_played, 3) if n_played else None,
               "logloss": round(ll / n_played, 3) if n_played else None,
               "matches": matches}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.GAMES = " + json.dumps(payload, separators=(",", ":")) + ";\n")
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(matches)} group games "
          f"({new} newly committed) · {n_played} played"
          + (f" · favourite hit {hits}/{n_played} ({hits/n_played*100:.0f}%)" if n_played else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
