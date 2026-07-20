#!/usr/bin/env python3
"""Generate the four manuscript figures from the committed result JSONs.

    python scripts/build_paper_figures.py     # -> paper/arxiv/figures/*.pdf

Figures (names match the \\figbox calls in the LaTeX):
  leadlag_dist   signed cross-venue lead-time distribution over the decisive events
  infoshare_ci   per-match Gonzalo-Granger share, sorted, with the pooled median CI band
  reliability    market vs model calibration reliability diagram
  book_collapse  spread blow-out + depth withdrawal at the goal (two panels, no dual axis)

Palette: Okabe-Ito (published colorblind-safe) — Polymarket blue, Kalshi vermillion.
Reads artifacts only; edits nothing under xresidual/.
"""
from __future__ import annotations

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = os.path.join(ROOT, "writeups")
OUT = os.path.join(ROOT, "paper", "arxiv", "figures")

# Okabe-Ito (CVD-safe by construction)
POLY, KALSHI, MODEL = "#0072B2", "#D55E00", "#8a8175"
INK, MUTE, REF = "#1b1813", "#4a443b", "#9a9488"

plt.rcParams.update({
    "font.family": "serif", "font.size": 9, "axes.titlesize": 10,
    "axes.edgecolor": "#cfc8ba", "axes.linewidth": 0.8, "axes.labelcolor": INK,
    "text.color": INK, "xtick.color": MUTE, "ytick.color": MUTE,
    "figure.dpi": 150, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
})


def _load(name):
    with open(os.path.join(W, name)) as f:
        return json.load(f)


def _clean(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def fig_leadlag():
    d = _load("_leadlag_results.json")
    signed = []          # best_lag_ms is already signed: + = Polymarket first, - = Kalshi first
    for pair in d.get("pairs", []):
        for ev in pair.get("events", []):
            ld = ev.get("lead")
            if ld and ld.get("leader") in ("polymarket", "kalshi"):
                signed.append(float(ld["best_lag_ms"]))
    a = np.array(signed, float)
    npoly, nkal = int((a > 0).sum()), int((a < 0).sum())
    lim = 3000
    inside = a[np.abs(a) <= lim]
    n_over = int((np.abs(a) > lim).sum())
    edges = np.arange(-lim, lim + 1, 200)
    counts, _ = np.histogram(inside, bins=edges)
    centers = (edges[:-1] + edges[1:]) / 2
    med = float(np.median(a[a > 0]))

    fig, ax = plt.subplots(figsize=(6.3, 2.9))
    ax.bar(centers, counts, width=180,
           color=[POLY if c > 0 else KALSHI for c in centers], alpha=0.9)
    top = ax.get_ylim()[1]
    ax.axvline(0, color=REF, lw=0.8)
    ax.axvline(med, color=POLY, lw=1.4, ls="--")
    ax.annotate(f"median +{med:.0f} ms", (med, top * 0.80), ha="right",
                xytext=(-6, 0), textcoords="offset points", color=POLY, fontsize=8.5)
    ax.text(0.02, 0.95, f"Kalshi first\n{nkal} events", transform=ax.transAxes,
            color=KALSHI, fontsize=8.5, va="top")
    ax.text(0.98, 0.95, f"Polymarket first\n{npoly} events", transform=ax.transAxes,
            color=POLY, fontsize=8.5, va="top", ha="right")
    ax.text(0.98, 0.62, f"+{n_over} events beyond ±3 s\n(gated ≤ 8 s)", transform=ax.transAxes,
            color=MUTE, fontsize=7.5, va="top", ha="right")
    ax.set_xlabel(r"cross-venue lead time $\Delta t$  (ms; + = Polymarket leads)")
    ax.set_ylabel("goal events")
    ax.set_xlim(-lim, lim)
    _clean(ax)
    _save(fig, "leadlag_dist")


def fig_infoshare():
    d = _load("_infoshare_results.json")
    H = _load("_hardened_stats.json")["infoshare"]
    gg = sorted(float(m["poly_gg"]) for m in d["per_match"])
    x = np.arange(1, len(gg) + 1)
    lo, hi = H["median_ci"]
    med = H["median_gg"]

    fig, ax = plt.subplots(figsize=(6.3, 3.1))
    ax.axhspan(lo, hi, color=POLY, alpha=0.10, lw=0)
    ax.axhline(med, color=POLY, lw=1.3, ls="--")
    ax.axhline(0.5, color=REF, lw=0.9, ls=":")
    cols = [POLY if v >= 0.5 else KALSHI for v in gg]
    ax.vlines(x, 0.5, gg, color=cols, lw=0.8, alpha=0.5)
    ax.scatter(x, gg, s=18, c=cols, zorder=3, edgecolor="white", linewidth=0.4)
    nlead = sum(v >= 0.5 for v in gg)
    ax.annotate(f"pooled median {med*100:.1f}%  (95% CI {lo*100:.0f}–{hi*100:.0f}%)",
                (1, med), xytext=(2, 6), textcoords="offset points", color=POLY, fontsize=8.5)
    ax.text(0.98, 0.06, f"{nlead} of {len(gg)} matches lead Polymarket",
            transform=ax.transAxes, ha="right", fontsize=8.5, color=MUTE)
    ax.set_xlabel("cointegrated match (sorted by share)")
    ax.set_ylabel("Polymarket Gonzalo–Granger share")
    ax.set_ylim(0, 1.02)
    ax.set_xlim(0, len(gg) + 1)
    _clean(ax)
    _save(fig, "infoshare_ci")


def fig_reliability():
    C = _load("_calibration_results.json")["versions"]
    fig, ax = plt.subplots(figsize=(4.2, 4.0))
    ax.plot([0, 1], [0, 1], color=REF, lw=0.9, ls="--", zorder=1)
    for key, color, lab in [("v1", MODEL, "model (raw)"), ("market", POLY, "market")]:
        v = C.get(key)
        if not v:
            continue
        curve = v["reliability_curve"]
        f = [p["f"] for p in curve]
        o = [p["o"] for p in curve]
        n = [p["n"] for p in curve]
        ax.plot(f, o, color=color, lw=1.4, zorder=2, label=lab)
        ax.scatter(f, o, s=[max(12, x_) for x_ in n], color=color,
                   edgecolor="white", linewidth=0.5, zorder=3)
    mk = C["market"]
    ax.text(0.04, 0.96, f"market: Brier {mk['brier']:.3f}, slope {mk['slope']:.2f}",
            transform=ax.transAxes, fontsize=8.5, va="top", color=MUTE)
    ax.set_xlabel("forecast probability")
    ax.set_ylabel("observed frequency")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.legend(frameon=False, loc="lower right", fontsize=8.5)
    _clean(ax)
    _save(fig, "reliability")


def fig_book_collapse():
    Q = _load("_liquidity_results.json")
    spread = [Q["poly"]["spread_widen_med"], Q["kalshi"]["spread_widen_med"]]
    depth = [Q["poly"]["depth_withdraw_med"] * 100, Q["kalshi"]["depth_withdraw_med"] * 100]
    labs = ["Polymarket", "Kalshi"]
    cols = [POLY, KALSHI]

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.3, 2.9))
    # Panel A: spread blow-out (x normal)
    a1.axhline(1, color=REF, lw=0.9, ls="--")
    a1.bar(labs, spread, color=cols, width=0.55, alpha=0.9)
    for i, v in enumerate(spread):
        a1.text(i, v + 0.2, f"{v:.0f}×", ha="center", fontsize=9, color=INK)
    a1.text(0.02, 0.95, "calm = 1×", transform=a1.transAxes, fontsize=8, color=MUTE, va="top")
    a1.set_ylabel("spread at the goal  (× calm)")
    a1.set_ylim(0, max(spread) * 1.25)
    _clean(a1)
    # Panel B: depth withdrawal (% of calm)
    a2.bar(labs, depth, color=cols, width=0.55, alpha=0.9)
    for i, v in enumerate(depth):
        a2.text(i, v + 0.05, ("≈0%" if v < 0.5 else f"{v:.0f}%"), ha="center", fontsize=9, color=INK)
    a2.text(0.02, 0.95, "calm = 100%", transform=a2.transAxes, fontsize=8, color=MUTE, va="top")
    a2.set_ylabel("best-price depth at the goal  (% of calm)")
    a2.set_ylim(0, max(max(depth) * 1.6, 2.0))
    _clean(a2)
    fig.suptitle("The book withdraws at the goal — adverse selection in real time",
                 fontsize=9.5, y=1.02, color=INK)
    _save(fig, "book_collapse")


def _save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".pdf")
    fig.savefig(path)
    plt.close(fig)
    print(f"  wrote figures/{name}.pdf")


def main():
    print("building manuscript figures ->", os.path.relpath(OUT, ROOT))
    fig_leadlag()
    fig_infoshare()
    fig_reliability()
    fig_book_collapse()


if __name__ == "__main__":
    main()
