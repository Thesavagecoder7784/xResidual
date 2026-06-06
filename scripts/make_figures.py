#!/usr/bin/env python3
"""Generate the project's figures from current data into figures/.

    python scripts/make_figures.py

Pre-tournament this draws the reliability diagram from the 538 backtest (real
forecasts), plus the live championship trajectory / velocity and a de-vig
comparison from the logged snapshots. During the tournament, point the reliability
diagram at the live match table (pipeline.calibration_report) instead.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xresidual import calibration as cal  # noqa: E402
from xresidual import (data_spi, microstructure, plots, trajectory,  # noqa: E402
                       wc2026_teams)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(ROOT, "figures")
LOGGER_DATA = os.path.join(ROOT, "logger", "data")


def main() -> int:
    made = []

    # 1) Reliability diagram, from the 538 historical backtest (real forecasts).
    df = data_spi.load_spi_intl()
    p, y = cal.flatten_wdl(df["p_home"], df["p_draw"], df["p_away"], df["outcome"])
    made.append(plots.reliability_diagram(
        p, y, os.path.join(FIG, "reliability_538_backtest.png"),
        title="Calibration backtest — 538 international forecasts"))

    # 2 & 3) Trajectory + velocity, from logged outright snapshots.
    snaps = trajectory.load_snapshots(LOGGER_DATA)
    long = trajectory.outright_probabilities(snaps, teams=wc2026_teams.WC2026_TEAMS) \
        if not snaps.empty else long_empty()
    if not long.empty and long["ts"].nunique() >= 1:
        made.append(plots.trajectory_chart(long, os.path.join(FIG, "trajectory.png")))
        vel = trajectory.belief_velocity(long)
        if (vel["n_obs"] > 1).any():
            made.append(plots.velocity_chart(vel, os.path.join(FIG, "velocity.png")))

    # 3b) Buildup title-race trajectory (Kalshi+Polymarket winner, incl. backfill).
    if not snaps.empty:
        panel = microstructure.venue_outright_panel(snaps)
        if not panel.empty and panel["ts"].dt.floor("1D").nunique() >= 3:
            panel = panel.assign(ts=panel["ts"].dt.floor("1D"))
            daily = panel.groupby(["ts", "team"])["prob"].median().reset_index()
            daily["prob"] = daily["prob"] / daily.groupby("ts")["prob"].transform("sum")
            made.append(plots.buildup_trajectory(daily, os.path.join(FIG, "buildup_trajectory.png")))

    # 4) Cross-venue divergence: Kalshi vs Polymarket on the outright winner.
    if not snaps.empty:
        panel = microstructure.venue_outright_panel(snaps)
        div = microstructure.cross_venue_divergence(panel)
        if not div.empty:
            made.append(plots.divergence_chart(div, os.path.join(FIG, "cross_venue_divergence.png")))

    # 5) Order-book imbalance + most-contested matches (microstructure).
    if not snaps.empty:
        ob = microstructure.orderbook_panel(snaps)
        if not ob.empty:
            made.append(plots.obi_chart(microstructure.obi_snapshot(ob),
                                        os.path.join(FIG, "order_book_imbalance.png")))
        disp = microstructure.bookmaker_dispersion(snaps)
        if not disp.empty:
            made.append(plots.contested_chart(disp, os.path.join(FIG, "most_contested.png")))

    # 6) De-vig comparison: illustrative 3-way market (favourite / draw / underdog).
    made.append(plots.devig_comparison(
        [1.45, 4.20, 8.00], ["home", "draw", "away"],
        os.path.join(FIG, "devig_comparison.png")))

    print("figures written:")
    for m in made:
        print("  " + os.path.relpath(m, ROOT))
    return 0


def long_empty():
    import pandas as pd
    return pd.DataFrame(columns=["ts", "team", "prob"])


if __name__ == "__main__":
    raise SystemExit(main())
