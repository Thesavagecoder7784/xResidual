#!/usr/bin/env python3
"""Is this World Cup weird? -> viz/model/_weird.js  (CROSS: historical envelope x live).

    python scripts/build_weird.py

Card #4 of the "cross two ideas" set. It overlays THIS tournament's per-match surprise on
the surprise distribution of the last two World Cups, using one metric both feeds carry for
every game:

  p_out = the probability the model gave the result that actually happened. Low = a shock
          the model did not see coming; high = chalk. surprisal = -log2(p_out) in bits.

Historical (2018 + 2022, 128 matches) comes from the graded, no-lookahead backtest; 2026
comes from the live group-stage ledger (docs/data/matches.js, model_p committed pre-kickoff
-- the model results feed lags a few games behind the live score feed, so we read the ledger
the site already shows). It answers, honestly, whether 2026 is genuinely chaotic or just
feels that way -- the favourite-calm-while-the-pitch-is-loud through-line.
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import numpy as np  # noqa: E402
from xresidual import baseline, data, elo  # noqa: E402
from backtest_wc import run_year  # noqa: E402  (reuse the graded, no-lookahead per-match scorer)

OUT = os.path.join(ROOT, "viz", "model", "_weird.js")
MATCHES = os.path.join(ROOT, "docs", "data", "matches.js")
WINDOWS = {"2018": ("2018-06-01", "2018-07-31"), "2022": ("2022-11-01", "2022-12-31")}


def live_played():
    """2026 played group games from the site ledger -> [{p_out, upset, label}]."""
    raw = open(MATCHES, encoding="utf-8").read()
    d = json.loads(re.search(r"=\s*(\{.*\});", raw, re.S).group(1))
    out = []
    for m in d["matches"]:
        if not m.get("played"):
            continue
        p_out = float(m["model_p"])                       # model's prob of the actual W/D/L
        a, b = f"{m['t1']} {m['s1']}-{m['s2']} {m['t2']}", m["result"]
        upset = not m.get("correct", True)                # favourite did not get the win it was tipped for
        out.append({"p_out": round(p_out, 3), "upset": upset, "label": a})
    return out


def main() -> int:
    df = data.load_results()
    res = elo.build_ratings(df)
    cal = res.calib.copy()
    cal["tournament"] = df.sort_values("date").reset_index(drop=True)["tournament"].values
    years = {y: run_year(cal, baseline.calibrate(cal[cal["date"] < w[0]]), *w)
             for y, w in WINDOWS.items()}

    hist = [m["p_out"] for y in ("2018", "2022") for m in years[y]["matches"]]
    live = live_played()
    hp = np.array(hist); lp = np.array([m["p_out"] for m in live]) if live else np.array([0.5])
    SHOCK = 0.30                                           # model gave the result <30% = a shock

    payload = {
        "hist": sorted(hist),
        "live": sorted(live, key=lambda m: m["p_out"]),
        "shock": SHOCK,
        "stats": {
            "hist_n": len(hist), "live_n": len(live),
            "hist_med": round(float(np.median(hp)), 3), "live_med": round(float(np.median(lp)), 3),
            "hist_shock": round(float((hp < SHOCK).mean()) * 100, 1),
            "live_shock": round(float((lp < SHOCK).mean()) * 100, 1),
        },
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.WEIRD = " + json.dumps(payload) + ";\n")
    s = payload["stats"]
    print(f"wrote {os.path.relpath(OUT, ROOT)}")
    print(f"  historical (2018+22): n={s['hist_n']} median p_out={s['hist_med']:.0%} "
          f"shocks(<{int(SHOCK*100)}%)={s['hist_shock']}%")
    print(f"  2026 so far:          n={s['live_n']} median p_out={s['live_med']:.0%} "
          f"shocks={s['live_shock']}%")
    print("  biggest 2026 surprises:")
    for m in sorted(live, key=lambda m: m["p_out"])[:5]:
        print(f"    model gave {m['p_out']:.0%}  {m['label']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
