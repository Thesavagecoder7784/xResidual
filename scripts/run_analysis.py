#!/usr/bin/env python3
"""Run the full xResidual analysis over current data.

    python scripts/run_analysis.py

Loads fixtures (openfootball), the logged market snapshots, and the Elo baseline,
then reports: completed-match calibration (Layer 3) + market-vs-baseline skill once
matches are played, the live championship trajectory (Layer 4), and, pre-tournament,
a market-vs-baseline preview for upcoming fixtures that already have odds.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xresidual import (baseline, data, data_fixtures, elo, microstructure,  # noqa: E402
                       pipeline, trajectory, wc2026_teams)

LOGGER_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "logger", "data")


def main() -> int:
    print("loading fixtures, snapshots, baseline ...")
    fixtures = data_fixtures.load_fixtures()
    snapshots = trajectory.load_snapshots(LOGGER_DATA)
    res = elo.build_ratings(data.load_results())
    params = baseline.calibrate(res.calib)
    played = int(fixtures["played"].sum())
    print(f"  {len(fixtures)} fixtures, {played} played | "
          f"{0 if snapshots.empty else len(snapshots):,} logged quotes")

    # ---- Layer 3: calibration on completed matches -------------------------
    table = pipeline.build_match_table(fixtures, snapshots, res.ratings, params)
    print(f"\n=== completed matches with market data: {len(table)} ===")
    if not table.empty:
        rep = pipeline.calibration_report(table, which="mkt")
        skill = pipeline.skill_comparison(table)
        print(f"market calibration: Brier={rep['brier']:.4f}  ECE={rep['ece']:.4f}  "
              f"slope b={rep['calib_b']:.3f} (a={rep['calib_a']:+.3f})")
        print(f"CORP: MCB={rep['corp']['MCB']:.4f} DSC={rep['corp']['DSC']:.4f} "
              f"UNC={rep['corp']['UNC']:.4f}")
        print(f"mean log-score — market {skill['market_mean_logscore']:.3f} vs "
              f"baseline {skill['baseline_mean_logscore']:.3f} "
              f"(lower=better; market expected to win)")
    else:
        print("  (none yet — calibration begins once matches are played)")

    # ---- Layer 4: live championship trajectory -----------------------------
    long = trajectory.outright_probabilities(snapshots, teams=wc2026_teams.WC2026_TEAMS)
    if not long.empty:
        latest_ts = long["ts"].max()
        latest = long[long["ts"] == latest_ts].sort_values("prob", ascending=False)
        print(f"\n=== live championship probabilities (oddsapi, {latest_ts:%Y-%m-%d %H:%M}Z) ===")
        for _, r in latest.head(8).iterrows():
            print(f"  {r['team']:<16} {r['prob']:.3f}")
        vel = trajectory.belief_velocity(long)
        if (vel["n_obs"] > 1).any():
            print("  fastest market revision:",
                  ", ".join(f"{r.team} ({r.velocity_per_day:+.3f}/day)"
                            for r in vel.head(3).itertuples()))

    # ---- cross-venue divergence + price discovery (Kalshi vs Polymarket) ----
    panel = microstructure.venue_outright_panel(snapshots)
    if not panel.empty:
        div = microstructure.cross_venue_divergence(panel)
        s = microstructure.divergence_summary(div)
        if s.get("n"):
            print(f"\n=== cross-venue divergence (Kalshi vs Polymarket, {s['n']} team-passes) ===")
            print(f"  mean {s['mean_divergence']*100:.2f}pp  median {s['median_divergence']*100:.2f}pp  "
                  f"p95 {s['p95_divergence']*100:.2f}pp  max {s['max_divergence']*100:.2f}pp")
            print("  most divergent:",
                  ", ".join(f"{t} ({d*100:.1f}pp)" for t, d in s["top_divergent_teams"].items()))
        disc = microstructure.price_discovery(panel)
        if not disc.empty and (disc["n_obs"] > 1).any():
            mv = disc.head(3)
            print("  most price churn:",
                  ", ".join(f"{r.team}/{r.venue} (TV {r.total_variation*100:.1f}pp)"
                            for r in mv.itertuples()))

    # ---- order-book microstructure (depth, spread, cross-venue lead-lag) ----
    ob = microstructure.orderbook_panel(snapshots)
    if not ob.empty:
        liq = microstructure.liquidity_summary(ob)
        print(f"\n=== order-book microstructure ({ob['team'].nunique()} teams) ===")
        for _, r in liq.iterrows():
            print(f"  {r['venue']:<11} median spread {r['median_spread']*100:.2f}c  "
                  f"median bid-depth {r['median_bid_depth']:,.0f} contracts")
        venues_present = set(liq["venue"])
        if {"kalshi", "polymarket"} <= venues_present:
            k = liq[liq.venue == "kalshi"]["median_bid_depth"].iloc[0]
            p = liq[liq.venue == "polymarket"]["median_bid_depth"].iloc[0]
            if k:
                print(f"  -> Polymarket median depth is {p / k:.1f}x Kalshi's")
        # order-book imbalance: are favorites sell-heavy?
        snap = microstructure.obi_snapshot(ob)
        favs = snap[snap.venue == "polymarket"].head(5)
        if not favs.empty:
            print("  order-book imbalance (Polymarket, top teams; <0.5 = sell-heavy):",
                  ", ".join(f"{r.team} {r.obi:.2f}" for r in favs.itertuples()))
            pred = microstructure.obi_predicts_returns(ob)
            if pred.get("corr") is not None:
                print(f"  OBI->next-move corr: {pred['corr']:+.2f} (n={pred['n']}) — {pred['reading']}")

        # lead-lag on the most-traded team (meaningful once enough passes accrue)
        if ob["ts"].nunique() >= 6:
            top_team = (ob.groupby("team")["mid"].mean().sort_values(ascending=False).index[0])
            ll = microstructure.lead_lag(ob, top_team)
            if ll:
                print(f"  lead-lag ({top_team}): {ll['leader']} leads by "
                      f"{ll['best_lag_passes']} passes (corr {ll['best_corr']:+.2f}, "
                      f"{ll['n_passes']} passes)")
        else:
            print("  (lead-lag needs more passes — accumulating)")

    # ---- bookmaker dispersion: which matches are the books most divided on? ----
    disp = microstructure.bookmaker_dispersion(snapshots)
    if not disp.empty:
        print(f"\n=== most contested matches (bookmaker dispersion, {int(disp['n_books'].max())} books) ===")
        for r in microstructure.most_contested(disp, 5).itertuples():
            print(f"  {r.market_label:<32} {r.outcome:<14} {r.dispersion*100:.1f}pp spread")

    # ---- pre-tournament preview: market vs baseline for upcoming fixtures ---
    if table.empty:
        print("\n=== market vs baseline preview (upcoming fixtures with odds) ===")
        shown = 0
        for f in fixtures[~fixtures["played"]].itertuples(index=False):
            cl = pipeline.closing_line_wdl(snapshots, f.team1, f.team2)
            if cl is None:
                continue
            b = pipeline.baseline_wdl(f.team1, f.team2, res.ratings, params, ground=f.ground)
            print(f"  {f.date} {f.team1} v {f.team2} @ {f.ground}")
            print(f"     market   {cl['p_home']:.2f}/{cl['p_draw']:.2f}/{cl['p_away']:.2f}"
                  f"   baseline {b['p_home']:.2f}/{b['p_draw']:.2f}/{b['p_away']:.2f}")
            shown += 1
            if shown >= 5:
                break
        if shown == 0:
            print("  (no h2h odds logged yet — the oddsapi agent runs daily at 12:00)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
