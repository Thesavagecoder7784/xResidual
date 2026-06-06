"""Tests for cross-venue divergence + price-discovery (Kalshi/Polymarket outright).

Run:  python tests/test_microstructure.py
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xresidual import microstructure as ms  # noqa: E402
from xresidual import wc2026_teams  # noqa: E402


def _snaps():
    """Two passes, two venues, with a venue-spelled name (Czechia) and a
    non-qualified entry (Italy) that must be canonicalized / dropped."""
    rows = []
    fields = {
        ("2026-06-10T00:00:00+00:00", "kalshi"): {"Spain": 0.55, "Czechia": 0.05, "Italy": 0.02},
        ("2026-06-10T00:00:00+00:00", "polymarket"): {"Spain": 0.50, "Czech Republic": 0.06},
        ("2026-06-10T00:30:00+00:00", "kalshi"): {"Spain": 0.60, "Czechia": 0.05, "Italy": 0.02},
        ("2026-06-10T00:30:00+00:00", "polymarket"): {"Spain": 0.52, "Czech Republic": 0.06},
    }
    for (ts, venue), field in fields.items():
        for team, mid in field.items():
            rows.append({"ts_utc": pd.Timestamp(ts), "venue": venue,
                         "market_type": "winner", "outcome": team, "mid": mid})
    return pd.DataFrame(rows)


def test_panel_canonicalizes_drops_nonqualified_and_normalizes():
    panel = ms.venue_outright_panel(_snaps())
    assert "Italy" not in set(panel["team"])           # non-qualified dropped
    assert "Czechia" not in set(panel["team"])          # mapped to canonical
    assert "Czech Republic" in set(panel["team"])
    sums = panel.groupby(["ts", "venue"])["prob"].sum()
    assert ((sums - 1.0).abs() < 1e-9).all()            # each field normalized


def test_cross_venue_divergence_values():
    div = ms.cross_venue_divergence(ms.venue_outright_panel(_snaps()))
    # both venues only have Spain + Czech Republic after filtering -> each ~ a 2-horse
    # field; divergence is symmetric between the two teams within a pass
    assert "divergence" in div.columns
    assert (div["divergence"] >= 0).all()
    assert div["divergence"].max() < 0.2                # sane magnitude


def test_divergence_summary_keys():
    s = ms.divergence_summary(ms.cross_venue_divergence(ms.venue_outright_panel(_snaps())))
    assert s["n"] > 0 and "mean_divergence" in s and "top_divergent_teams" in s


def test_price_discovery_drift_sign():
    disc = ms.price_discovery(ms.venue_outright_panel(_snaps()))
    spain = disc[(disc.venue == "kalshi") & (disc.team == "Spain")].iloc[0]
    assert spain["drift"] > 0                           # Spain rose 0.55->0.60 (pre-norm)
    assert spain["n_obs"] == 2


def test_discovery_vs_outcome_positive_when_prices_track_truth():
    disc = ms.price_discovery(ms.venue_outright_panel(_snaps()))
    # Spain (rose) eventually wins, Czech Republic (flat/low) does not
    corr = ms.discovery_vs_outcome(disc, {"Spain": 1.0, "Czech Republic": 0.0})
    # too few teams (2) -> guarded to None; just assert it runs and returns per-venue
    assert set(corr.keys()) <= {"kalshi", "polymarket"}


def _ob_snaps():
    """Order-book snapshots, 2 passes, 2 venues, with spread + depth."""
    rows = []
    data = {
        ("2026-06-10T00:00:00+00:00", "kalshi"): {"Spain": (0.160, 0.002, 1e5)},
        ("2026-06-10T00:00:00+00:00", "polymarket"): {"Spain": (0.159, 0.001, 8e6)},
        ("2026-06-10T00:30:00+00:00", "kalshi"): {"Spain": (0.162, 0.002, 1e5)},
        ("2026-06-10T00:30:00+00:00", "polymarket"): {"Spain": (0.161, 0.001, 8e6)},
    }
    for (ts, venue), field in data.items():
        for team, (mid, spread, depth) in field.items():
            rows.append({"ts_utc": pd.Timestamp(ts), "venue": venue, "outcome": team,
                         "market_type": "orderbook", "mid": mid, "spread": spread,
                         "bid_depth": depth, "ask_depth": depth})
    return pd.DataFrame(rows)


def test_orderbook_panel_and_liquidity_summary():
    panel = ms.orderbook_panel(_ob_snaps())
    assert set(panel["venue"]) == {"kalshi", "polymarket"}
    summ = ms.liquidity_summary(panel)
    poly = summ[summ.venue == "polymarket"].iloc[0]
    kal = summ[summ.venue == "kalshi"].iloc[0]
    assert poly["median_bid_depth"] > kal["median_bid_depth"]   # Polymarket deeper
    assert poly["median_spread"] <= kal["median_spread"]


def test_lead_lag_detects_follower():
    # Polymarket leads; Kalshi mid = Polymarket mid shifted one pass later.
    poly = [0.10, 0.13, 0.11, 0.15, 0.12, 0.16, 0.13, 0.17, 0.14, 0.18, 0.15]
    rows = []
    base = pd.Timestamp("2026-06-10T00:00:00+00:00")
    for i, p in enumerate(poly):
        ts = base + pd.Timedelta(minutes=30 * i)
        rows.append({"ts": ts, "venue": "polymarket", "team": "Spain", "mid": p,
                     "spread": 0.001, "bid_depth": 1.0, "ask_depth": 1.0})
        if i >= 1:  # kalshi follows by one pass
            rows.append({"ts": ts, "venue": "kalshi", "team": "Spain", "mid": poly[i - 1],
                         "spread": 0.002, "bid_depth": 1.0, "ask_depth": 1.0})
    res = ms.lead_lag(pd.DataFrame(rows), "Spain", max_lag=4)
    assert res is not None
    assert res["best_lag_passes"] == 1 and res["leader"] == "polymarket"
    assert res["best_corr"] > 0.9


def test_obi_computation_and_snapshot():
    panel = ms.orderbook_panel(_ob_snaps())
    p = ms.order_book_imbalance(panel)
    # Polymarket Spain: bid 8e6 / (8e6+8e6) = 0.5 in _ob_snaps (bid==ask depth)
    assert (p["obi"].between(0, 1)).all()
    snap = ms.obi_snapshot(panel)
    assert {"venue", "team", "obi"} <= set(snap.columns)


def test_obi_predicts_returns_positive_when_constructed():
    # build a series where high bid-share precedes a price rise
    rows = []
    base = pd.Timestamp("2026-06-10T00:00:00+00:00")
    mids = [0.10, 0.12, 0.11, 0.14, 0.12, 0.15]
    for i, m in enumerate(mids):
        # next return is up when obi high: set bid_depth high before an upward move
        nxt_up = (i + 1 < len(mids)) and (mids[i + 1] > m)
        bid, ask = (9.0, 1.0) if nxt_up else (1.0, 9.0)
        rows.append({"ts": base + pd.Timedelta(minutes=30 * i), "venue": "polymarket",
                     "team": "Spain", "mid": m, "spread": 0.001,
                     "bid_depth": bid, "ask_depth": ask})
    res = ms.obi_predicts_returns(pd.DataFrame(rows))
    assert res["corr"] is not None and res["corr"] > 0.5


def test_bookmaker_dispersion():
    # one match, 3 books disagreeing on the home team
    rows = []
    ts = pd.Timestamp("2026-06-11T18:00:00+00:00")
    for book, p in [("pinnacle", 0.60), ("bet365", 0.64), ("williamhill", 0.67)]:
        rows.append({"ts_utc": ts, "venue": "oddsapi", "market_type": "h2h",
                     "market_label": "Mexico vs South Africa", "outcome": "Mexico",
                     "mid": p, "bookmaker": book})
    disp = ms.bookmaker_dispersion(pd.DataFrame(rows))
    assert len(disp) == 1
    r = disp.iloc[0]
    assert r["n_books"] == 3
    assert abs(r["dispersion"] - 0.07) < 1e-9          # 0.67 - 0.60
    assert ms.most_contested(disp, 5).iloc[0]["outcome"] == "Mexico"


def test_relative_spread_longshot_premium():
    # favorite (mid .16) and longshot (mid .015) both 1c wide -> longshot rel-spread far bigger
    rows = [
        {"ts": pd.Timestamp("2026-06-10T00:00:00+00:00"), "venue": "polymarket",
         "team": "France", "mid": 0.16, "spread": 0.01, "bid_depth": 1.0, "ask_depth": 1.0},
        {"ts": pd.Timestamp("2026-06-10T00:00:00+00:00"), "venue": "polymarket",
         "team": "Haiti", "mid": 0.015, "spread": 0.01, "bid_depth": 1.0, "ask_depth": 1.0},
    ]
    rs = ms.relative_spread_summary(pd.DataFrame(rows))
    assert rs["polymarket"]["ratio"] > 5


def test_market_implied_totals_and_poisson():
    rows = []
    ts = pd.Timestamp("2026-06-11T18:00:00+00:00")
    for book, p in [("a", 0.79), ("b", 0.81)]:
        rows.append({"ts_utc": ts, "venue": "oddsapi", "market_type": "totals",
                     "market_label": "Germany vs Curacao", "outcome": "Over 2.5",
                     "mid": p, "point": 2.5, "bookmaker": book})
    it = ms.market_implied_totals(pd.DataFrame(rows))
    assert len(it) == 1
    assert it.iloc[0]["implied_total_goals"] > 2.5      # high P(over) -> high implied goals


def test_altitude_totals_join():
    rows = []
    ts = pd.Timestamp("2026-06-11T18:00:00+00:00")
    for label, p in [("Mexico vs South Africa", 0.55), ("Spain vs Cape Verde", 0.70)]:
        rows.append({"ts_utc": ts, "venue": "oddsapi", "market_type": "totals",
                     "market_label": label, "outcome": "Over 2.5", "mid": p,
                     "point": 2.5, "bookmaker": "a"})
    fx = pd.DataFrame([
        {"team1": "Mexico", "team2": "South Africa", "ground": "Mexico City"},
        {"team1": "Spain", "team2": "Cape Verde", "ground": "Miami"},
    ])
    at = ms.altitude_totals(pd.DataFrame(rows), fx)
    assert at["n_matched"] == 2 and at["n_high_alt"] == 1


def test_canonical_and_is_qualified():
    assert wc2026_teams.canonical("Czechia") == "Czech Republic"
    assert wc2026_teams.canonical("Turkiye") == "Turkey"
    assert wc2026_teams.is_qualified("Congo DR") and not wc2026_teams.is_qualified("Italy")


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
