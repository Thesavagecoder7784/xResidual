#!/usr/bin/env python3
"""P7b market skill: does the market out-forecast the RAW model on matches?
    -> writeups/_skill_results.json + viz/model/_skill.js

Pre-registration P7 clause (b) [genuine unknown]: the market's mean log-score is lower (better) than
the raw Elo/Skellam model's on completed matches — `pipeline.skill_comparison` over
`pipeline.build_match_table` (market = closing h2h consensus; baseline = the raw Elo baseline, the
same independent reference used throughout, NOT the squad-blended or confed-corrected sim rating).
Clause (a) (raw-Elo title favourite > market by >=5pp) is the pre-tournament observed gap, graded
from _blend.js by grade_prereg.py. PASS of P7 needs both.

Fork-forward: reads the frozen loaders + pipeline only; edits nothing under xresidual/.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import baseline, data, data_fixtures, elo, pipeline, trajectory  # noqa: E402

LOGGER = os.path.join(ROOT, "logger", "data")
OUT_JS = os.path.join(ROOT, "viz", "model", "_skill.js")
RESULTS = os.path.join(ROOT, "writeups", "_skill_results.json")


def main() -> int:
    fixtures = data_fixtures.load_fixtures()
    snapshots = trajectory.load_snapshots(LOGGER)
    res = elo.build_ratings(data.load_results())
    params = baseline.calibrate(res.calib)
    table = pipeline.build_match_table(fixtures, snapshots, res.ratings, params)

    payload = {"n_matches": int(len(table))}
    if not table.empty:
        skill = pipeline.skill_comparison(table)
        mkt = skill["market_mean_logscore"]
        base = skill["baseline_mean_logscore"]
        payload.update({"market_mean_logscore": round(float(mkt), 4),
                        "baseline_mean_logscore": round(float(base), 4),
                        "edge": round(float(base - mkt), 4),     # >0 => market better
                        "pass_b": bool(mkt < base)})
    os.makedirs(os.path.dirname(OUT_JS), exist_ok=True)
    with open(OUT_JS, "w") as f:
        f.write("window.SKILL = " + json.dumps(payload) + ";\n")
    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    json.dump(payload, open(RESULTS, "w"), indent=2)

    if payload["n_matches"]:
        print(f"P7b skill ({payload['n_matches']} matches): market log-score "
              f"{payload['market_mean_logscore']} vs raw model {payload['baseline_mean_logscore']} "
              f"({'PASS: market better' if payload['pass_b'] else 'FAIL: model better'})")
    else:
        print("P7b: no completed matches with market data yet")
    print(f"wrote {os.path.relpath(RESULTS, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
