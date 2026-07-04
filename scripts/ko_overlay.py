"""Shared knockout-results conditioning from the live ESPN scores overlay.

The frozen `xresidual.knockout.played_ko_results` reads only the martj42 Elo feed, which lags ~2 days
on knockout games and records penalty ties as level scores (no advancer). This fork-forward helper
reads `data/cache/wc_scores_overlay.json` (ESPN, refreshed within a site cycle) and returns the same
`{frozenset(idxA, idxB): winner_idx}` shape, using ESPN's `advancer` flag so penalty/ET shootouts
settle to the side that actually went through. Centralised so EVERY builder (build_bracket,
prediction_board, ...) conditions the knockout identically — the previous per-file copies are exactly
how prediction_board silently went stale (France frozen at its group projection).
"""
import json
import os

from xresidual import wc2026_teams


def _load_games(root: str) -> list:
    """Combine the rolling ESPN overlay (recent games) with the persistent advancer ledger (every
    shootout ever seen). The overlay ages games out after ~36h and martj42 drops the advancer, so the
    ledger is what keeps a penalty/ET tie resolvable for the rest of the tournament. Ledger is a
    {pair_key: record} dict; overlay is a list — both carry the same fields, so we flatten to one list."""
    games = []
    for fname in ("wc_scores_overlay.json", "ko_advancers.json"):
        path = os.path.join(root, "data", "cache", fname)
        if not os.path.exists(path):
            continue
        try:
            obj = json.loads(open(path, encoding="utf-8").read())
        except Exception:
            continue
        games += list(obj.values()) if isinstance(obj, dict) else obj
    return games


def overlay_ko_results(det: dict, fx, root: str) -> dict:
    import pandas as pd
    games = _load_games(root)
    if not games:
        return {}
    grp = fx[fx["group"].astype(str).str.startswith("Group")]
    group_end = pd.to_datetime(grp["date"]).max().date()
    bridge = lambda t: wc2026_teams.elo_name(wc2026_teams.canonical(t))
    gidx_b = {bridge(k): v for k, v in det["gidx"].items()}
    out = {}
    for g in games:
        ct = g.get("commence_time")
        try:
            if not ct or pd.to_datetime(ct).date() <= group_end:
                continue
        except Exception:
            continue
        h, a = bridge(g.get("home_team", "")), bridge(g.get("away_team", ""))
        if h not in gidx_b or a not in gidx_b:
            continue
        adv = g.get("advancer")
        if adv:                                    # ESPN advancer flag — settles penalty/ET ties too
            wb = bridge(adv)
            if wb in gidx_b:
                out[frozenset((gidx_b[h], gidx_b[a]))] = gidx_b[wb]
        else:                                      # fallback: decisive regulation score
            hs, as_ = g.get("home_score"), g.get("away_score")
            if hs is not None and as_ is not None and hs != as_:
                out[frozenset((gidx_b[h], gidx_b[a]))] = gidx_b[h if hs > as_ else a]
    return out
