"""Cross-venue convergence forward-test (paper only; no orders, no capital).

A disclosed, out-of-sample paper track record for the simplest microstructure signal:
when Kalshi and Polymarket disagree on a de-vigged title price, bet the gap converges.
This is deliberately NOT a Kelly / bankroll engine (that lives in other projects). It is
one honest signal with modeled costs, logged append-only so the equity curve is a real
forward record rather than a re-fittable backtest.

Decision rule (fixed, so there are no post-hoc choices):
  - At each 30-min pass, for each top-N title team, gap = polymarket - kalshi (de-vigged
    probability, via the same multiplicative de-vig the rest of the repo uses).
  - OPEN a convergence position on a team when |gap| >= ENTRY and none is open for it.
    Economically: long the cheaper venue, short the richer; you profit if |gap| shrinks.
  - CLOSE when |gap| <= EXIT (converged) or after MAX_HOLD passes (expired).
  - PnL per trade = (|gap_entry| - |gap_exit|) - COST, in probability points. COST is a
    modeled round-trip cost (fee + half-spread, both legs). Unit size; no compounding.

Everything here is paper. The deliverable is a verifiable, costed, out-of-sample signal
record, not a claim of executed P&L.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import microstructure as ms

# Fixed parameters (pre-committed so the rule can't be tuned to the outcome).
ENTRY = 0.010      # open when the de-vigged gap is >= 1.0pp
EXIT = 0.003       # call it converged at <= 0.3pp
COST = 0.005       # 0.5pp modeled round-trip cost (fee + half-spread, both legs)
MAX_HOLD = 8       # max hold in passes (~4h at the 30-min logging cadence)


def divergence_series(snapshots: pd.DataFrame, top_n: int = 12) -> pd.DataFrame:
    """[ts, team, kalshi, polymarket, gap] de-vigged, restricted to the top-N teams by
    mean Polymarket probability (the liquid, tradeable end of the field).

    The paper track record is LIVE-only: reconstructed/backfilled mids (no bid/ask, coarse
    cadence) are excluded so the disclosed equity curve isn't contaminated."""
    if "backfill" in snapshots.columns:
        snapshots = snapshots[snapshots["backfill"] != True]    # noqa: E712 (NaN-safe)
    panel = ms.venue_outright_panel(snapshots)
    div = ms.cross_venue_divergence(panel)
    if div.empty or "polymarket" not in div.columns or "kalshi" not in div.columns:
        return pd.DataFrame(columns=["ts", "team", "kalshi", "polymarket", "gap"])
    rank = div.groupby("team")["polymarket"].mean().sort_values(ascending=False)
    keep = set(rank.head(top_n).index)
    d = div[div["team"].isin(keep)].copy()
    d["gap"] = d["polymarket"] - d["kalshi"]
    return (d[["ts", "team", "kalshi", "polymarket", "gap"]]
            .sort_values(["ts", "team"]).reset_index(drop=True))


def run_convergence(div: pd.DataFrame, entry: float = ENTRY, exit: float = EXIT,
                    cost: float = COST, max_hold: int = MAX_HOLD) -> dict:
    """Simulate the convergence rule over the divergence series.

    Returns {trades, summary, equity}. A trade's `reason` is converged | expired | eod
    (eod = still open when the data ends; transient, not a real close)."""
    empty = {"trades": [], "summary": _summary([]), "equity": []}
    if div is None or div.empty:
        return empty
    passes = sorted(div["ts"].unique())
    by_ts = {ts: dict(zip(g["team"], g["gap"])) for ts, g in div.groupby("ts")}
    open_pos: dict[str, dict] = {}
    armed: dict[str, bool] = {}      # a team must reset below entry before re-entering
    trades: list[dict] = []
    for i, ts in enumerate(passes):
        cur = by_ts[ts]
        last = (i == len(passes) - 1)
        # update / close open positions
        for team, pos in list(open_pos.items()):
            if team not in cur:
                continue
            gap = cur[team]
            held = i - pos["entry_idx"]
            converged, expired = abs(gap) <= exit, held >= max_hold
            if converged or expired or last:
                pnl = (abs(pos["entry_gap"]) - abs(gap)) - cost
                trades.append({
                    "team": team, "entry_ts": str(pos["entry_ts"]), "exit_ts": str(ts),
                    "entry_gap": round(pos["entry_gap"], 5), "exit_gap": round(gap, 5),
                    "held_passes": int(held), "pnl_pp": round(pnl * 100, 4),
                    "reason": "converged" if converged else "expired" if expired else "eod",
                })
                del open_pos[team]
        # open new positions (only if flat and re-armed by a reset below entry)
        for team, gap in cur.items():
            if team in open_pos:
                continue
            if abs(gap) < entry:
                armed[team] = True                       # reset: ready to trade again
            elif armed.get(team, True):
                open_pos[team] = {"entry_ts": ts, "entry_gap": float(gap), "entry_idx": i}
                armed[team] = False
    return {"trades": trades, "summary": _summary(trades), "equity": _equity(trades)}


def _summary(trades: list[dict]) -> dict:
    if not trades:
        return {"n_trades": 0, "total_pnl_pp": 0.0, "hit_rate": None,
                "mean_pnl_pp": None, "per_trade_sharpe": None, "avg_hold": None}
    pnl = np.array([t["pnl_pp"] for t in trades], dtype=float)
    return {
        "n_trades": len(trades),
        "total_pnl_pp": round(float(pnl.sum()), 3),
        "hit_rate": round(float((pnl > 0).mean()), 3),
        "mean_pnl_pp": round(float(pnl.mean()), 4),
        "per_trade_sharpe": round(float(pnl.mean() / pnl.std()), 3) if pnl.std() > 0 else None,
        "avg_hold": round(float(np.mean([t["held_passes"] for t in trades])), 2),
    }


def _equity(trades: list[dict]) -> list[dict]:
    eq, cum = [], 0.0
    for t in sorted(trades, key=lambda x: x["exit_ts"]):
        cum += t["pnl_pp"]
        eq.append({"ts": t["exit_ts"], "cum_pnl_pp": round(cum, 3)})
    return eq
