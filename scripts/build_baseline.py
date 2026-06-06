#!/usr/bin/env python3
"""Build the Layer 1 baseline end-to-end and print a few sanity checks.

    python scripts/build_baseline.py

Loads open results data, computes World Football Elo, fits the Elo->goals mapping,
and prints the current top teams plus a worked expectation for a real 2026 fixture.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xresidual import baseline, data, elo, residual  # noqa: E402


def main() -> int:
    print("loading results ...")
    df = data.load_results()
    print(f"  {len(df):,} matches, {df['date'].min().date()} -> {df['date'].max().date()}")

    print("computing Elo ...")
    res = elo.build_ratings(df)
    params = baseline.calibrate(res.calib)
    print(f"  fit on {params.n_matches:,} matches (>=1990): "
          f"beta={params.beta:.3f} goals/100 Elo, total_goals={params.total_goals:.2f}")

    print("\ntop 10 by current Elo:")
    top = sorted(res.ratings.items(), key=lambda kv: kv[1], reverse=True)[:10]
    for i, (team, r) in enumerate(top, 1):
        print(f"  {i:2d}. {team:<16} {r:6.0f}")

    # The real 2026 opener: Mexico (host) vs South Africa at Mexico City, so the
    # host home-advantage is ON and the altitude total-goals factor applies (§9).
    print("\nexample expectation — Mexico vs South Africa, Mexico City (host, altitude):")
    exp = baseline.make_expectation("Mexico", "South Africa", res.ratings, params,
                                    neutral=False, venue="Mexico City")
    flat = baseline.make_expectation("Mexico", "South Africa", res.ratings, params)
    print(f"  lambda: home={exp.lambda_home:.2f} away={exp.lambda_away:.2f}  "
          f"(neutral/sea-level would give total {flat.lambda_home + flat.lambda_away:.2f} "
          f"vs {exp.lambda_home + exp.lambda_away:.2f} here)")
    print(f"  P(win/draw/loss) = {exp.p_home:.3f} / {exp.p_draw:.3f} / {exp.p_away:.3f}"
          f"  (sum={sum(exp.wdl):.4f})")
    print(f"  E[goal diff]={exp.exp_goal_diff:+.2f}  sd={exp.sd_goal_diff:.2f}")

    # what a 1-0 South Africa upset would score as a residual
    z = residual.goal_diff_z(exp, actual_goal_diff=-1)
    ls = residual.log_score(exp, residual.OUTCOME_AWAY)
    print(f"  if S.Africa won 1-0: goal-diff z={z:+.2f}, log-score={ls:.2f} nats")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
