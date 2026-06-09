"""Cross-venue divergence and closing-line-value / price-discovery.

Both run on the free Kalshi + Polymarket outright (tournament-winner) markets, which
log every ~30 min, so these produce real findings from data accumulating now,
without the Odds API.

Cross-venue divergence (a market-efficiency diagnostic): for the same team at the
same time, do Kalshi and Polymarket agree after de-vigging? Persistent divergence is
either friction that arbitrage hasn't closed or evidence of segmented audiences.

Price discovery / CLV: how each venue's implied probability moves from its opening
observation onward, and (once outcomes are known) whether it moved *toward* the
truth (efficient discovery) or not.

Team names are canonicalized across venues (Czechia->Czech Republic, etc.) and the
field is restricted to the 48 qualified teams before normalizing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import wc2026_teams

FREE_VENUES = ("kalshi", "polymarket")


def venue_outright_panel(snapshots: pd.DataFrame, venues=FREE_VENUES,
                         round_minutes: int = 30) -> pd.DataFrame:
    """Long [ts, venue, team, prob]: each venue's winner field, canonicalized to the
    48 qualified teams and renormalized to sum to 1 per (venue, pass).

    Timestamps are floored to `round_minutes` to define a "pass". This both aligns
    the venues (logged in the same scheduled run) and is robust to a venue stamping
    each market with its own microsecond timestamp. `ts` in the output is the pass."""
    if snapshots.empty:
        return pd.DataFrame(columns=["ts", "venue", "team", "prob"])
    s = snapshots[(snapshots["venue"].isin(venues))
                  & (snapshots.get("market_type") == "winner")
                  & (snapshots["outcome"] != "__error__")].copy()
    if s.empty:
        return pd.DataFrame(columns=["ts", "venue", "team", "prob"])
    s["team"] = s["outcome"].map(wc2026_teams.canonical)
    s = s[s["team"].isin(wc2026_teams.WC2026_TEAMS)]
    s["ts"] = s["ts_utc"].dt.floor(f"{round_minutes}min")
    # median across rows in the pass, then renormalize the field per (pass, venue)
    agg = (s.groupby(["ts", "venue", "team"])["mid"].median()
             .rename("prob").reset_index())
    totals = agg.groupby(["ts", "venue"])["prob"].transform("sum")
    agg["prob"] = agg["prob"] / totals
    return agg.sort_values(["ts", "venue", "team"]).reset_index(drop=True)


def cross_venue_divergence(panel: pd.DataFrame) -> pd.DataFrame:
    """Per (pass, team), the gap between venues' implied probabilities.

    `panel` is already aligned by pass (venue_outright_panel floors timestamps).
    Returns long [ts, team, <venue cols...>, divergence] where divergence = max - min
    across venues that both quoted the team in that pass.

    Critically, each venue is renormalized over the COMMON set of teams it shares with
    the other venue in that pass *before* differencing. The panel normalizes each venue
    over its own field, but the venues list different numbers of teams (Kalshi ~30,
    Polymarket ~48), so the same team gets a systematically different implied prob purely
    from the denominator — a phantom divergence. Renormalizing over the shared field makes
    it apples-to-apples; otherwise the gap (and the forward-test convergence signal built
    on it) is biased by coverage, not real disagreement."""
    if panel.empty:
        return pd.DataFrame()
    wide = panel.pivot_table(index=["ts", "team"], columns="venue", values="prob")
    present = [c for c in FREE_VENUES if c in wide.columns]
    if len(present) < 2:
        return pd.DataFrame()
    wide = wide.dropna(subset=present)  # both venues quoted this team in this pass
    if wide.empty:
        return pd.DataFrame()
    # renormalize each venue over the common teams in each pass (apples-to-apples)
    wide[present] = wide.groupby(level="ts")[present].transform(lambda c: c / c.sum())
    wide["divergence"] = wide[present].max(axis=1) - wide[present].min(axis=1)
    return wide.reset_index()


def divergence_summary(div: pd.DataFrame) -> dict:
    """Aggregate divergence stats + the teams that disagree most across venues."""
    if div.empty:
        return {"n": 0}
    d = div["divergence"]
    by_team = (div.groupby("team")["divergence"].mean()
                  .sort_values(ascending=False))
    return {
        "n": int(len(d)),
        "mean_divergence": float(d.mean()),
        "median_divergence": float(d.median()),
        "p95_divergence": float(d.quantile(0.95)),
        "max_divergence": float(d.max()),
        "top_divergent_teams": by_team.head(5).round(4).to_dict(),
    }


def price_discovery(panel: pd.DataFrame) -> pd.DataFrame:
    """Per (venue, team): opening vs latest implied prob, drift, and path roughness.

    The outright analogue of closing-line value: how prices move as information
    arrives. `drift` = latest - opening; `total_variation` = summed |step| (how much
    the price churned); `n_obs` flags how much path we have so far."""
    if panel.empty:
        return pd.DataFrame()
    rows = []
    for (venue, team), g in panel.sort_values("ts").groupby(["venue", "team"]):
        p = g["prob"].to_numpy()
        rows.append({
            "venue": venue, "team": team, "n_obs": len(p),
            "open_prob": float(p[0]), "latest_prob": float(p[-1]),
            "drift": float(p[-1] - p[0]),
            "total_variation": float(np.abs(np.diff(p)).sum()),
        })
    return pd.DataFrame(rows).sort_values("total_variation", ascending=False).reset_index(drop=True)


def orderbook_panel(snapshots: pd.DataFrame, venues=FREE_VENUES,
                    round_minutes: int = 30) -> pd.DataFrame:
    """Long [ts, venue, team, mid, spread, bid_depth, ask_depth] from order-book
    snapshots (market_type='orderbook'), canonicalized to the 48 teams and aligned by
    pass. The substrate for the spread/depth and lead-lag analyses."""
    if snapshots.empty or "market_type" not in snapshots:
        return pd.DataFrame(columns=["ts", "venue", "team", "mid", "spread", "bid_depth", "ask_depth"])
    s = snapshots[(snapshots["venue"].isin(venues))
                  & (snapshots["market_type"] == "orderbook")
                  & (snapshots["outcome"] != "__error__")].copy()
    if s.empty:
        return pd.DataFrame(columns=["ts", "venue", "team", "mid", "spread", "bid_depth", "ask_depth"])
    s["team"] = s["outcome"].map(wc2026_teams.canonical)
    s = s[s["team"].isin(wc2026_teams.WC2026_TEAMS)]
    s["ts"] = s["ts_utc"].dt.floor(f"{round_minutes}min")
    return (s.groupby(["ts", "venue", "team"])
              .agg(mid=("mid", "median"), spread=("spread", "median"),
                   bid_depth=("bid_depth", "median"), ask_depth=("ask_depth", "median"))
              .reset_index().sort_values(["ts", "venue", "team"]).reset_index(drop=True))


def liquidity_summary(ob_panel: pd.DataFrame) -> pd.DataFrame:
    """Per-venue spread and depth, the headline microstructure comparison
    (e.g. 'Polymarket quotes ~Nx the depth of Kalshi at comparable spreads')."""
    if ob_panel.empty:
        return pd.DataFrame()
    return (ob_panel.groupby("venue")
            .agg(mean_spread=("spread", "mean"), median_spread=("spread", "median"),
                 mean_bid_depth=("bid_depth", "mean"), median_bid_depth=("bid_depth", "median"),
                 n=("team", "size")).reset_index())


def lead_lag(ob_panel: pd.DataFrame, team: str, max_lag: int = 6) -> dict | None:
    """Cross-venue price discovery: does one venue's mid move *before* the other's?

    Cross-correlates the two venues' mid-price changes at lags ±max_lag passes for one
    team. A positive best lag means Polymarket leads Kalshi (Kalshi's move at t lines
    up with Polymarket's move at t-lag); negative means Kalshi leads. This is the
    project's central question, and is meaningful only once enough passes accumulate."""
    g = ob_panel[ob_panel["team"] == team]
    wide = g.pivot_table(index="ts", columns="venue", values="mid").sort_index()
    if not {"kalshi", "polymarket"} <= set(wide.columns):
        return None
    wide = wide[["kalshi", "polymarket"]].dropna()
    dk = wide["kalshi"].diff().to_numpy()[1:]
    dp = wide["polymarket"].diff().to_numpy()[1:]
    if len(dk) < max_lag + 3 or np.std(dk) == 0 or np.std(dp) == 0:
        return None
    best_lag, best_corr = 0, 0.0
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            a, b = dk[lag:], dp[:len(dp) - lag] if lag else dp
        else:
            a, b = dk[:lag], dp[-lag:]
        if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
            continue
        c = float(np.corrcoef(a, b)[0, 1])
        if abs(c) > abs(best_corr):
            best_lag, best_corr = lag, c
    leader = ("polymarket" if best_lag > 0 else "kalshi" if best_lag < 0 else "synchronous")
    return {"team": team, "best_lag_passes": best_lag, "best_corr": best_corr,
            "leader": leader, "n_passes": int(len(wide))}


def information_share(price_a, price_b, label_a: str = "a", label_b: str = "b",
                      n_lags: int = 2) -> dict | None:
    """Price-discovery shares for two venues quoting the same contract (the P6 metric).

    The two de-vigged mid series are cointegrated with the natural vector (1, -1) (same
    outcome, so a - b is stationary). Fit a bivariate VECM by OLS,

        d a_t = alpha_a (a_{t-1} - b_{t-1}) + lags + e_a
        d b_t = alpha_b (a_{t-1} - b_{t-1}) + lags + e_b

    and report:
      - Gonzalo-Granger permanent-component shares (unique, ordering-free):
            gg_a = alpha_b / (alpha_b - alpha_a),  gg_b = -alpha_a / (alpha_b - alpha_a).
        The venue that adjusts *less* to the spread (smaller |alpha|) leads discovery.
      - Hasbrouck information-share bounds for `a` (low/high over the two Cholesky
        orderings of the residual covariance), plus the midpoint.
    Returns None if the series are too short or degenerate. Computed on mid-price moves,
    so it is robust to the ~59% WS trade-direction problem."""
    a = np.asarray(price_a, dtype=float)
    b = np.asarray(price_b, dtype=float)
    n = min(len(a), len(b))
    if n < n_lags + 12:
        return None
    a, b = a[:n], b[:n]
    # Cointegration guard: the (1,-1) spread must be stationary for the VECM/shares to
    # mean anything. Test it (ADF) rather than just asserting it; flag if it fails.
    try:
        from statsmodels.tsa.stattools import adfuller
        adf_p = float(adfuller(a - b, autolag="AIC")[1])
    except Exception:
        adf_p = None
    cointegrated = bool(adf_p is not None and adf_p < 0.10)
    da, db, z = np.diff(a), np.diff(b), a - b      # da[i] is the move into time i+1
    rows = range(n_lags, len(da))
    Z, X, Ya, Yb = [], [], [], []
    for i in rows:
        Z.append(z[i])                              # error-correction term z_{t-1}
        feats = []
        for k in range(1, n_lags + 1):
            feats += [da[i - k], db[i - k]]
        X.append(feats)
        Ya.append(da[i]); Yb.append(db[i])
    if len(Z) < n_lags + 6:
        return None
    D = np.column_stack([np.array(Z), np.array(X), np.ones(len(Z))])
    ca, *_ = np.linalg.lstsq(D, np.array(Ya), rcond=None)
    cb, *_ = np.linalg.lstsq(D, np.array(Yb), rcond=None)
    alpha_a, alpha_b = float(ca[0]), float(cb[0])
    ea, eb = np.array(Ya) - D @ ca, np.array(Yb) - D @ cb
    omega = np.cov(np.vstack([ea, eb]))
    denom = alpha_b - alpha_a
    if abs(denom) < 1e-12:
        return None
    gg_a = alpha_b / denom
    gg_b = -alpha_a / denom
    gamma = np.array([gg_a, gg_b])
    var_cf = float(gamma @ omega @ gamma)
    has_lo = has_hi = None
    if var_cf > 0:
        def is_first(perm):
            try:
                m = np.linalg.cholesky(omega[np.ix_(perm, perm)])
            except np.linalg.LinAlgError:
                return None
            return float((gamma[perm] @ m)[0] ** 2 / var_cf)
        is_a_first = is_first([0, 1])               # a ordered first -> a's upper share
        is_b_first = is_first([1, 0])               # b first -> a's lower share = 1 - that
        if is_a_first is not None and is_b_first is not None:
            has_lo, has_hi = sorted([is_a_first, 1.0 - is_b_first])
    # The VECM information shares are only interpretable if a - b is stationary (the
    # (1,-1) spread is a genuine error-correction term). On a non-cointegrated pair the
    # shares are a spurious-regression artifact, so suppress the leader/shares and let the
    # diagnostic alphas + adf_p stand — a consumer reading gg_a gets None, not a fake lead.
    spurious = not cointegrated
    leader = None if spurious else (label_a if gg_a >= gg_b else label_b)
    rnd = lambda x: None if (spurious or x is None) else round(x, 4)
    return {
        "leader": leader, "label_a": label_a, "label_b": label_b,
        "gg_a": rnd(gg_a), "gg_b": rnd(gg_b),
        "alpha_a": round(alpha_a, 5), "alpha_b": round(alpha_b, 5),
        "hasbrouck_a_lo": rnd(has_lo),
        "hasbrouck_a_hi": rnd(has_hi),
        "hasbrouck_a_mid": None if (spurious or has_lo is None) else round((has_lo + has_hi) / 2, 4),
        "cointegrated": cointegrated,
        "adf_p": None if adf_p is None else round(adf_p, 4),
        "n": int(len(Z)),
    }


def order_book_imbalance(ob_panel: pd.DataFrame) -> pd.DataFrame:
    """Add `obi` = bid_depth / (bid_depth + ask_depth) to an order-book panel.

    OBI is the classic short-horizon pressure signal: >0.5 = more resting size on the
    buy side than the sell side."""
    if ob_panel.empty:
        return ob_panel.assign(obi=[])
    p = ob_panel.copy()
    denom = p["bid_depth"] + p["ask_depth"]
    p["obi"] = (p["bid_depth"] / denom).where(denom > 0)
    return p


def obi_snapshot(ob_panel: pd.DataFrame) -> pd.DataFrame:
    """Latest OBI per (venue, team), e.g. to show favorites are sell-heavy."""
    p = order_book_imbalance(ob_panel)
    if p.empty:
        return p
    latest = p.sort_values("ts").groupby(["venue", "team"]).tail(1)
    return latest[["venue", "team", "mid", "obi", "bid_depth", "ask_depth"]] \
        .sort_values("mid", ascending=False).reset_index(drop=True)


def obi_predicts_returns(ob_panel: pd.DataFrame) -> dict:
    """Does OBI at pass t predict the mid move from t to t+1? (the MM test).

    Pools (obi_t - 0.5, mid_{t+1} - mid_t) across all (venue, team) series and
    correlates. Positive => buy-side imbalance precedes price rises (OBI is
    informative). Meaningful only once enough passes accumulate."""
    p = order_book_imbalance(ob_panel).dropna(subset=["obi"])
    xs, ys = [], []
    for _, g in p.sort_values("ts").groupby(["venue", "team"]):
        mid = g["mid"].to_numpy()
        obi = g["obi"].to_numpy()
        if len(mid) < 3:
            continue
        xs.extend(obi[:-1] - 0.5)
        ys.extend(np.diff(mid))
    if len(xs) < 5 or np.std(xs) == 0 or np.std(ys) == 0:
        return {"n": len(xs), "corr": None}
    corr = float(np.corrcoef(xs, ys)[0, 1])
    return {"n": len(xs), "corr": corr,
            "reading": "buy-side imbalance precedes price rises" if corr > 0
                       else "imbalance does not predict (or contrarian)"}


def relative_spread_summary(ob_panel: pd.DataFrame, fav_min: float = 0.05,
                            longshot_max: float = 0.02) -> dict:
    """The favorite-longshot bias hidden in the tick.

    Absolute spreads are tick-floored (~1c on every contract), but RELATIVE spread
    (spread / mid) explodes for longshots: a 1c spread is ~6% of a 16% favorite but
    ~65% of a 1.5% longshot. Returns median relative spread for favorites vs longshots
    per venue, and the ratio."""
    if ob_panel.empty:
        return {}
    p = ob_panel[(ob_panel["mid"] > 0) & ob_panel["spread"].notna()].copy()
    p["rel_spread"] = p["spread"] / p["mid"]
    out = {}
    for venue, g in p.groupby("venue"):
        fav = g[g["mid"] >= fav_min]["rel_spread"]
        lng = g[g["mid"] <= longshot_max]["rel_spread"]
        if len(fav) and len(lng):
            out[venue] = {"fav_rel_spread": float(fav.median()),
                          "longshot_rel_spread": float(lng.median()),
                          "ratio": float(lng.median() / fav.median())}
    return out


def _poisson_lambda_from_over(p_over: float, line: float = 2.5) -> float:
    """Implied expected total goals: the Poisson rate whose P(total > line) == p_over."""
    from scipy.optimize import brentq
    from scipy.stats import poisson
    k = int(np.floor(line))  # P(X > 2.5) = P(X >= 3) = 1 - cdf(2)
    f = lambda lam: (1 - poisson.cdf(k, lam)) - p_over
    if p_over <= 1e-6:
        return 0.0
    return float(brentq(f, 1e-6, 20.0))


def market_implied_totals(snapshots: pd.DataFrame, line: float = 2.5) -> pd.DataFrame:
    """Per match: consensus P(over `line`) and the implied expected total goals.
    Returns [match_label, p_over, n_books, implied_total_goals]."""
    if snapshots.empty or "market_type" not in snapshots:
        return pd.DataFrame()
    s = snapshots[(snapshots["venue"] == "oddsapi") & (snapshots["market_type"] == "totals")
                  & (snapshots["outcome"] != "__error__") & (snapshots.get("point") == line)].copy()
    if s.empty:
        return pd.DataFrame()
    s = s[s["ts_utc"] == s["ts_utc"].max()]
    over = s[s["outcome"].str.contains("over", case=False, na=False)]
    g = over.groupby("market_label")["mid"].agg(p_over="median", n_books="size").reset_index()
    g["implied_total_goals"] = g["p_over"].map(lambda p: _poisson_lambda_from_over(p, line))
    return g.sort_values("implied_total_goals", ascending=False).reset_index(drop=True)


def _altitude_of_ground(ground: str, venue_alt: dict) -> float | None:
    """Match a fixture 'ground' (e.g. 'Guadalajara (Zapopan)') to a venue altitude."""
    if not isinstance(ground, str):
        return None
    for city, alt in venue_alt.items():
        if city.lower() in ground.lower():
            return alt
    return None


def altitude_totals(snapshots: pd.DataFrame, fixtures: pd.DataFrame,
                    high_m: int = 1500) -> dict:
    """Does the market set higher totals at altitude? Joins implied totals to fixture
    venues and compares high-altitude vs sea-level matches. Pre-tournament this is the
    market's *expectation*; post-tournament, compare to realized goals."""
    from . import venues_wc2026
    it = market_implied_totals(snapshots)
    if it.empty or fixtures.empty:
        return {}
    fx = fixtures.copy()
    fx["market_label"] = fx["team1"] + " vs " + fx["team2"]
    merged = it.merge(fx[["market_label", "ground"]], on="market_label", how="inner")
    merged["altitude_m"] = merged["ground"].map(
        lambda g: _altitude_of_ground(g, venues_wc2026.VENUE_ALTITUDE_M))
    merged["high_alt"] = merged["altitude_m"].fillna(0) >= high_m
    hi = merged[merged["high_alt"]]["implied_total_goals"]
    lo = merged[~merged["high_alt"]]["implied_total_goals"]
    return {
        "n_matched": int(len(merged)), "n_high_alt": int(len(hi)),
        "high_alt_median_total": float(hi.median()) if len(hi) else None,
        "sea_level_median_total": float(lo.median()) if len(lo) else None,
        "altitude_grounds": sorted(merged[merged["high_alt"]]["ground"].unique().tolist()),
    }


def bookmaker_dispersion(snapshots: pd.DataFrame, market_type: str = "h2h") -> pd.DataFrame:
    """How much do the bookmakers disagree, per match outcome?

    Uses the multi-bookmaker odds feed: for each match and outcome, the spread of
    implied probabilities across books. Dispersion is an information-asymmetry /
    uncertainty proxy, and 'which matches are the books most divided on' is a story.
    Returns [match, outcome, n_books, mean_prob, dispersion (max-min), std]."""
    if snapshots.empty or "market_type" not in snapshots:
        return pd.DataFrame()
    s = snapshots[(snapshots["venue"] == "oddsapi")
                  & (snapshots["market_type"] == market_type)
                  & (snapshots["outcome"] != "__error__")].copy()
    if s.empty:
        return pd.DataFrame()
    # latest pass only, so we don't conflate disagreement with time drift
    s = s[s["ts_utc"] == s["ts_utc"].max()]
    g = (s.groupby(["market_label", "outcome"])["mid"]
           .agg(n_books="size", mean_prob="mean",
                dispersion=lambda x: x.max() - x.min(), std="std").reset_index())
    return g[g["n_books"] >= 3].sort_values("dispersion", ascending=False).reset_index(drop=True)


def most_contested(dispersion: pd.DataFrame, top_n: int = 8) -> pd.DataFrame:
    """The matches/outcomes the bookmakers most disagree on."""
    return dispersion.head(top_n) if not dispersion.empty else dispersion


def discovery_vs_outcome(discovery: pd.DataFrame, realized: dict[str, float]) -> dict:
    """Post-hoc CLV check: did prices move toward the realized outcome?

    `realized` maps team -> 1.0 (won tournament) / 0.0 (did not). Efficient discovery
    means drift correlates positively with (realized - open_prob): prices that started
    too low on the eventual winner rose, etc. Returns the correlation per venue.
    Call once the champion is known."""
    out = {}
    for venue, g in discovery.groupby("venue"):
        g = g[g["team"].isin(realized)]
        if len(g) < 3:
            out[venue] = None
            continue
        target = g["team"].map(realized) - g["open_prob"]
        corr = float(np.corrcoef(g["drift"], target)[0, 1]) if g["drift"].std() > 0 else float("nan")
        out[venue] = corr
    return out
