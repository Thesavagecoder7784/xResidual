"""One snapshot pass: read config + env, fetch venues, append every quote."""

from __future__ import annotations

import json
import os
from typing import Iterable, Optional

import storage
import venues

CONFIG_DEFAULT = os.path.join(os.path.dirname(__file__), "config.json")


def load_config(path: str = CONFIG_DEFAULT) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_once(config: dict, env: dict, data_dir: str,
             only: Optional[Iterable[str]] = None) -> dict:
    """Fetch configured venues once and append results. `only` restricts to a
    subset of venue names (e.g. {"oddsapi"} for a slower quota-bound cron).
    Returns a per-venue summary for the run loop to log."""
    only = set(only) if only else None
    summary: dict[str, dict] = {}
    for venue, fetcher in venues.FETCHERS.items():
        if only is not None and venue not in only:
            continue
        if not config.get(venue):
            continue
        quotes = fetcher(config, env)
        ok = errs = 0
        for q in quotes:
            storage.append(data_dir, q)
            if q.outcome == "__error__":
                errs += 1
            else:
                ok += 1
        summary[venue] = {"ok": ok, "errors": errs}
    return summary
