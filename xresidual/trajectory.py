"""Tournament probability trajectory — Layer 4 (METHODOLOGY.md §7).

Reads the logger's outright (tournament-winner) snapshots and builds, per team, the
implied-championship-probability time series and a belief-update velocity: how fast
the market is revising its estimate. Teams the market is actively learning about move
fast; priced-in teams stay flat.

Pure functions operate on DataFrames so they're testable without the live logger;
`load_snapshots` is the thin file reader over logger/data/snapshots-*.jsonl.
"""

from __future__ import annotations

import glob
import json
import os

import pandas as pd

_DAY = pd.Timedelta(days=1)


def load_snapshots(data_dir: str) -> pd.DataFrame:
    """Read all append-only JSONL snapshots into one flat DataFrame.

    `extra.*` keys are hoisted to top-level columns (market_type, bookmaker, point, …).
    """
    rows = []
    for path in sorted(glob.glob(os.path.join(data_dir, "snapshots-*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    if not rows:
        return pd.DataFrame()
    df = pd.json_normalize(rows)  # extra.market_type, extra.bookmaker, extra.point, ...
    df.columns = [c.replace("extra.", "") for c in df.columns]
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    return df


def outright_probabilities(df: pd.DataFrame, venue: str = "oddsapi",
                           market_type: str = "outrights",
                           teams: set[str] | None = None,
                           min_books: int = 1) -> pd.DataFrame:
    """Long [ts, team, prob]: median implied championship prob across bookmakers per
    timestamp, renormalized so the field sums to 1 at each timestamp.

    The pre-tournament outright market lists non-qualified teams (often quoted by a
    single book at residual prices), so:
      - `teams` restricts to a whitelist (e.g. the 48 qualified sides) — recommended
        for publication; source it from a fixtures feed (openfootball/worldcup.json).
      - `min_books` drops names quoted by fewer than this many bookmakers at a
        timestamp (a cheap filter for stale single-book longshots).
    Renormalization happens AFTER filtering, so dropped non-participants don't
    distort the field.
    """
    if df.empty:
        return pd.DataFrame(columns=["ts", "team", "prob"])
    sel = df[(df["venue"] == venue) & (df.get("market_type") == market_type)
             & (df["outcome"] != "__error__")].copy()
    if teams is not None:
        sel = sel[sel["outcome"].isin(teams)]
    if sel.empty:
        return pd.DataFrame(columns=["ts", "team", "prob"])
    # median across books + book count, per (timestamp, team)
    agg = (sel.groupby(["ts_utc", "outcome"])["mid"]
              .agg(prob="median", n_books="size").reset_index()
              .rename(columns={"ts_utc": "ts", "outcome": "team"}))
    agg = agg[agg["n_books"] >= min_books]
    # renormalize the surviving field per timestamp
    totals = agg.groupby("ts")["prob"].transform("sum")
    agg["prob"] = agg["prob"] / totals
    return agg[["ts", "team", "prob"]].sort_values(["ts", "team"]).reset_index(drop=True)


def belief_velocity(long: pd.DataFrame) -> pd.DataFrame:
    """Per-team revision metrics from a long [ts, team, prob] series.

    Columns: n_obs, first_prob, latest_prob, net_drift, total_variation,
    velocity_per_day (total variation / span in days), max_jump.
    Sorted by velocity_per_day descending — the teams the market is learning about.
    """
    out = []
    for team, g in long.sort_values("ts").groupby("team"):
        p = g["prob"].to_numpy()
        ts = g["ts"]
        diffs = pd.Series(p).diff().abs().dropna()
        span_days = max((ts.max() - ts.min()) / _DAY, 1e-9)
        tv = float(diffs.sum())
        out.append({
            "team": team,
            "n_obs": int(len(p)),
            "first_prob": float(p[0]),
            "latest_prob": float(p[-1]),
            "net_drift": float(p[-1] - p[0]),
            "total_variation": tv,
            "velocity_per_day": tv / span_days,
            "max_jump": float(diffs.max()) if len(diffs) else 0.0,
        })
    res = pd.DataFrame(out)
    return res.sort_values("velocity_per_day", ascending=False).reset_index(drop=True)


def to_timeseries(long: pd.DataFrame) -> pd.DataFrame:
    """Wide timestamp x team probability matrix for plotting."""
    if long.empty:
        return pd.DataFrame()
    return long.pivot_table(index="ts", columns="team", values="prob").sort_index()
