"""Append-only snapshot storage.

The logger's one job is to not lose data, so writes are append-only JSONL, one
file per UTC day, flushed and fsync'd on every record. Nothing rewrites or
truncates an existing file: you can't reconstruct intraday cross-venue history
after the fact, so a bad rewrite would be unrecoverable.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class Quote:
    """One observation of one outcome of one market at one instant."""

    ts_utc: str                      # ISO-8601, UTC, when we recorded it
    venue: str                       # "polymarket" | "kalshi" | "betfair"
    market_id: str                   # venue-native market/event id
    market_label: str                # human-readable, e.g. "Brazil vs Croatia — Brazil win"
    outcome: str                     # e.g. "win" / "yes" / team name
    bid: Optional[float] = None      # best bid (probability units, 0..1)
    ask: Optional[float] = None      # best ask (probability units, 0..1)
    mid: Optional[float] = None      # (bid+ask)/2 when both present, else best available
    last: Optional[float] = None     # last traded price, if exposed
    volume: Optional[float] = None   # cumulative traded volume, if exposed
    liquidity: Optional[float] = None  # venue liquidity proxy (depth/$), if exposed
    extra: dict[str, Any] = field(default_factory=dict)  # venue-specific raw bits


def _day_path(data_dir: str, ts: datetime) -> str:
    return os.path.join(data_dir, f"snapshots-{ts:%Y-%m-%d}.jsonl")


def append(data_dir: str, quote: Quote) -> None:
    """Append a single quote as one JSON line, durably."""
    os.makedirs(data_dir, exist_ok=True)
    ts = datetime.now(timezone.utc)
    path = _day_path(data_dir, ts)
    line = json.dumps(asdict(quote), separators=(",", ":"), ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
