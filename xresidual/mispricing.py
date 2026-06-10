"""Model-vs-market mispricing scanner + the favourite-longshot term structure.

One engine for a finding that recurs across our work: the favourite-longshot bias shows up
at every market layer (the tick, group-winner, reach-round, elimination) and is absent in
the deep, liquid markets. `scan()` turns (model, market) probability pairs into signed edges
(back / fade) with the FLB direction and confound flags; `term_structure()` aggregates by
layer to show the bias is ~0 where liquidity is deep and grows where it is thin.

That shape is self-validating: a model that AGREES with the sharp, liquid markets (gap ~0)
and disagrees only with the thin ones — always in the same direction (favourites overpriced,
longshots underpriced) — is detecting market softness, not its own error. The deep-market
agreement is the control that rules out "the model is just biased everywhere."
"""
from __future__ import annotations

# Home advantage confounds the model-market gap for the host nations, so their edges are
# not clean (we can't tell market mispricing from our model under-rating home advantage).
HOSTS = {"USA", "Mexico", "Canada"}


def scan(contracts: list[dict]) -> list[dict]:
    """Each contract: {layer, team, model, market} with model/market as probabilities in the
    SAME units (we use percent). Returns the contracts annotated with:
      gap   = model - market   (>0: market underprices -> BACK; <0: overprices -> FADE)
      side  = 'back' | 'fade'
      confound = team is a host (home-advantage-confounded, exclude from clean edges)
    Contracts with a missing model or market are dropped."""
    out = []
    for c in contracts:
        m, k = c.get("model"), c.get("market")
        if m is None or k is None:
            continue
        gap = m - k
        out.append({**c, "gap": round(gap, 2), "side": "back" if gap > 0 else "fade",
                    "abs_gap": round(abs(gap), 2), "confound": c.get("team") in HOSTS})
    return out


def _mean(xs):
    xs = list(xs)
    return round(sum(xs) / len(xs), 2) if xs else None


def term_structure(scanned: list[dict]) -> list[dict]:
    """Per layer: how soft is it, and is the softness the FLB shape? Splits each layer at
    its median market price into favourites (high) and longshots (low):
      fav_gap      <0  -> favourites OVERpriced (the fade side of FLB)
      longshot_gap >0  -> longshots UNDERpriced (the back side of FLB)
      flb_spread = longshot_gap - fav_gap  -> the size of the bias (≈0 = efficient layer)
      mean_abs_gap     -> overall mispricing magnitude in the layer
    """
    layers: dict[str, list] = {}
    for c in scanned:
        layers.setdefault(c["layer"], []).append(c)
    rows = []
    for layer, cs in layers.items():
        prices = sorted(x["market"] for x in cs)
        med = prices[len(prices) // 2]
        fav = _mean(x["gap"] for x in cs if x["market"] >= med)
        lng = _mean(x["gap"] for x in cs if x["market"] < med)
        rows.append({
            "layer": layer, "n": len(cs),
            "mean_abs_gap": _mean(x["abs_gap"] for x in cs),
            "fav_gap": fav, "longshot_gap": lng,
            "flb_spread": round(lng - fav, 2) if (fav is not None and lng is not None) else None,
        })
    return rows


def top_edges(scanned: list[dict], n: int = 8, exclude_confounded: bool = True) -> dict:
    """The cleanest current edges: biggest BACKs (model>market) and FADEs (model<market),
    optionally dropping host-confounded contracts."""
    pool = [c for c in scanned if not (exclude_confounded and c["confound"])]
    backs = sorted([c for c in pool if c["gap"] > 0], key=lambda c: -c["gap"])[:n]
    fades = sorted([c for c in pool if c["gap"] < 0], key=lambda c: c["gap"])[:n]
    return {"backs": backs, "fades": fades}
