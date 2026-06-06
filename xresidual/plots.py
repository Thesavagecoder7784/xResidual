"""Figures for the findings: reliability diagrams, trajectories, devig comparison.

The analysis layers produce numbers; this renders them. Uses a headless backend so
it runs under launchd / on a server. Every function saves a PNG and returns its path.

The reliability diagram is the main one: it overlays the CORP isotonic calibration
curve (with bootstrap consistency band) on the classic binned points (with Wilson
CIs), against the 45-degree line. A claim of mis/well-calibration is only visible
where the band departs from the diagonal.
"""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from . import calibration as cal  # noqa: E402
from . import devig as _devig  # noqa: E402

_INK = "#1b1b1f"
_ACCENT = "#2f6fed"
_BAND = "#2f6fed"
_GRID = "#e6e6ea"


def _save(fig, path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _style(ax):
    ax.set_facecolor("white")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(True, color=_GRID, linewidth=0.8)
    ax.tick_params(colors=_INK, labelsize=9)


def reliability_diagram(p, y, path: str, n_bins: int = 10,
                        title: str = "Market calibration") -> str:
    """CORP isotonic curve + consistency band + binned points vs the 45-degree line."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    corp = cal.corp(p, y)
    tab = cal.reliability_table(p, y, n_bins)
    a, b = cal.calibration_regression(p, y)

    fig, ax = plt.subplots(figsize=(6, 6))
    _style(ax)
    ax.plot([0, 1], [0, 1], "--", color="#9aa0aa", lw=1.2, label="perfect calibration")
    ax.fill_between(corp.grid, corp.band_lo, corp.band_hi, color=_BAND, alpha=0.15,
                    label="CORP 95% consistency band")
    ax.plot(corp.grid, corp.recal, color=_ACCENT, lw=2.0, label="CORP (isotonic) curve")

    t = tab[tab["n"] > 0]
    yerr = np.vstack([t["obs_freq"] - t["ci_lo"], t["ci_hi"] - t["obs_freq"]])
    ax.errorbar(t["mean_pred"], t["obs_freq"], yerr=yerr, fmt="o", color=_INK,
                ms=4, lw=0.8, capsize=2, alpha=0.8, label="binned (Wilson CIs)")

    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_xlabel("forecast probability", color=_INK)
    ax.set_ylabel("observed frequency", color=_INK)
    ax.set_title(f"{title}\nMCB={corp.mcb:.4f}  DSC={corp.dsc:.3f}  slope b={b:.3f}",
                 color=_INK, fontsize=11)
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    return _save(fig, path)


def trajectory_chart(long, path: str, top_n: int = 8,
                     title: str = "Championship probability trajectory") -> str:
    """Implied championship probability over time for the top_n current teams."""
    latest_ts = long["ts"].max()
    order = (long[long["ts"] == latest_ts].sort_values("prob", ascending=False)
             ["team"].head(top_n).tolist())
    fig, ax = plt.subplots(figsize=(8, 5))
    _style(ax)
    cmap = plt.get_cmap("tab10")
    for i, team in enumerate(order):
        g = long[long["team"] == team].sort_values("ts")
        ax.plot(g["ts"], g["prob"], marker="o", ms=3, lw=1.8, color=cmap(i % 10), label=team)
    ax.set_ylabel("implied P(win tournament)", color=_INK)
    ax.set_xlabel("date", color=_INK)
    ax.set_title(title, color=_INK, fontsize=11)
    ax.legend(loc="best", fontsize=8, frameon=False, ncol=2)
    fig.autofmt_xdate()
    return _save(fig, path)


def velocity_chart(vel_df, path: str, top_n: int = 10,
                   title: str = "Belief-update velocity") -> str:
    """Horizontal bars of how fast the market is revising each team."""
    d = vel_df.head(top_n).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 5))
    _style(ax)
    ax.barh(d["team"], d["velocity_per_day"], color=_ACCENT, alpha=0.85)
    ax.set_xlabel("total variation in P(win) per day", color=_INK)
    ax.set_title(title, color=_INK, fontsize=11)
    return _save(fig, path)


def divergence_chart(div_df, path: str, top_n: int = 12,
                     title: str = "Cross-venue divergence (Kalshi vs Polymarket)") -> str:
    """Horizontal bars of mean |implied-prob gap| between venues, per team."""
    by_team = (div_df.groupby("team")["divergence"].mean()
               .sort_values(ascending=False).head(top_n).iloc[::-1])
    fig, ax = plt.subplots(figsize=(7, 5))
    _style(ax)
    ax.barh(by_team.index, by_team.values * 100, color=_ACCENT, alpha=0.85)
    ax.set_xlabel("mean |Kalshi - Polymarket| implied prob (percentage points)", color=_INK)
    ax.set_title(title, color=_INK, fontsize=11)
    return _save(fig, path)


_PALETTE = ["#2f6fed", "#e8635a", "#1ea896", "#e0a32e", "#7d5ba6",
            "#3a8d5b", "#c2553f", "#5a6b7b"]


def buildup_trajectory(long, path: str, top_n: int = 7,
                       title: str = "The title race during the buildup",
                       subtitle: str = "Implied championship probability · Kalshi + Polymarket, de-vigged",
                       footnote: str = "xResidual · @PrabhatM27") -> str:
    """Polished trajectory: top-N teams' implied championship probability over time,
    with direct end-of-line labels (de-collided) instead of a legend. `long` is a
    [ts, team, prob] frame (one row per day per team)."""
    latest = long["ts"].max()
    order = (long[long["ts"] == latest].sort_values("prob", ascending=False)
             ["team"].head(top_n).tolist())

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.grid(True, axis="y", color=_GRID, linewidth=0.9)
    ax.tick_params(colors=_INK, labelsize=9, length=0)

    ends = []
    for i, team in enumerate(order):
        g = long[long["team"] == team].sort_values("ts")
        color = _PALETTE[i % len(_PALETTE)]
        ax.plot(g["ts"], g["prob"] * 100, lw=2.6, color=color,
                solid_capstyle="round", solid_joinstyle="round", alpha=0.95)
        ax.scatter(g["ts"].iloc[-1], g["prob"].iloc[-1] * 100, s=22, color=color, zorder=3)
        ends.append([g["prob"].iloc[-1] * 100, team, color])

    # de-collide end labels: enforce a minimum vertical gap
    ends.sort(reverse=True)
    gap = (max(e[0] for e in ends) - min(e[0] for e in ends)) * 0.06 + 0.6
    for j in range(1, len(ends)):
        if ends[j - 1][0] - ends[j][0] < gap:
            ends[j][0] = ends[j - 1][0] - gap
    xmax = long["ts"].max()
    xpad = (xmax - long["ts"].min()) * 0.02
    for y, team, color in ends:
        ax.annotate(f"{team}", (xmax + xpad, y), color=color, fontsize=10.5,
                    fontweight="bold", va="center", annotation_clip=False)

    ax.set_ylabel("P(win tournament)  %", color=_INK, fontsize=10)
    ax.set_ylim(bottom=0)
    ax.margins(x=0.02)
    import matplotlib.dates as mdates
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
    fig.suptitle(title, x=0.06, y=0.97, ha="left", fontsize=15,
                 fontweight="bold", color=_INK)
    ax.set_title(subtitle, loc="left", fontsize=10, color="#6b7280", pad=10)
    fig.text(0.06, 0.01, footnote, fontsize=8, color="#9aa0aa")
    fig.subplots_adjust(right=0.86, top=0.88, bottom=0.1, left=0.08)
    return _save(fig, path)


def obi_chart(obi_snapshot_df, path: str, venue: str = "polymarket", top_n: int = 12,
              title: str = "Order-book imbalance — top teams") -> str:
    """Bid-share per team (OBI). A reference line at 0.5; bars left of it are
    sell-heavy. Reveals e.g. that favorites are systematically offered, not bid."""
    d = obi_snapshot_df[obi_snapshot_df["venue"] == venue].head(top_n).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 5))
    _style(ax)
    colors = [_ACCENT if v >= 0.5 else "#e06c4f" for v in d["obi"]]
    ax.barh(d["team"], d["obi"], color=colors, alpha=0.85)
    ax.axvline(0.5, color="#9aa0aa", ls="--", lw=1.2)
    ax.set_xlim(0, 1)
    ax.set_xlabel("bid share  (OBI; <0.5 = sell-heavy)", color=_INK)
    ax.set_title(f"{title} — {venue}", color=_INK, fontsize=11)
    return _save(fig, path)


def contested_chart(dispersion_df, path: str, top_n: int = 10,
                    title: str = "Most contested matches (bookmaker disagreement)") -> str:
    """Horizontal bars of cross-bookmaker implied-prob spread per match outcome."""
    d = dispersion_df.head(top_n).iloc[::-1]
    labels = [f"{r.market_label} — {r.outcome}" for r in d.itertuples()]
    fig, ax = plt.subplots(figsize=(8, 5))
    _style(ax)
    ax.barh(labels, d["dispersion"] * 100, color=_ACCENT, alpha=0.85)
    ax.set_xlabel("cross-bookmaker spread in implied prob (percentage points)", color=_INK)
    ax.set_title(title, color=_INK, fontsize=11)
    return _save(fig, path)


def devig_comparison(decimal_odds, outcome_labels, path: str,
                     title: str = "Implied probability by de-vig method") -> str:
    """Grouped bars of implied probabilities under each de-vig method (sensitivity)."""
    methods = _devig.DEFAULT_METHODS
    probs = {m: _devig.implied_probabilities(decimal_odds, m) for m in methods}
    x = np.arange(len(outcome_labels))
    w = 0.8 / len(methods)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    _style(ax)
    cmap = plt.get_cmap("Blues")
    for i, m in enumerate(methods):
        ax.bar(x + i * w, probs[m], w, label=m, color=cmap(0.45 + 0.18 * i))
    ax.set_xticks(x + w * (len(methods) - 1) / 2)
    ax.set_xticklabels(outcome_labels)
    ax.set_ylabel("implied probability", color=_INK)
    ax.set_title(title, color=_INK, fontsize=11)
    ax.legend(fontsize=8, frameon=False)
    return _save(fig, path)
