#!/usr/bin/env python3
"""Does the model add information BEYOND a sharp external forecast? (incremental value)

    python scripts/encompassing_test.py

Calibration alone ("the model is well-calibrated") does NOT show the model is useful — the
market price is also well-calibrated. The question a quant asks is: does my model carry
information a sharp reference forecast doesn't already have? This is a forecast-encompassing
test (Fair-Shiller / Diebold-Mariano).

Benchmark: FiveThirtyEight's SPI match forecasts (data/spi_matches_intl.csv, ~4.6k
internationals 2019-2024 with prob1/probtie/prob2 + final scores) — a respected public
model. NOT the betting market: historical international closing odds aren't in the repo, so
SPI is the sharpest available proxy. The market version of this test is pre-registered to
grade on 2026 results, since we now log Polymarket/Kalshi prices per market.

My model = the project's point-in-time Elo + Skellam W/D/L expectation (no lookahead: each
SPI match is scored on the rating the chronological Elo held BEFORE it). Aligned to SPI by
(date, teams). Reports: head-to-head log-loss + Brier, a Diebold-Mariano test on the
per-match log-loss difference (bootstrap), and the optimal forecast-combination weight on my
model (w*~0 => my model is encompassed by SPI / adds nothing; w*>0 => it adds info).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import baseline, data, elo, wc2026_teams  # noqa: E402

SPI = os.path.join(ROOT, "data", "spi_matches_intl.csv")
EPS = 1e-12


def _canon(name: str) -> str:
    return wc2026_teams.canonical(str(name)).lower()


def outcome_idx(gd: int) -> int:
    return 0 if gd > 0 else (2 if gd < 0 else 1)   # 0=home,1=draw,2=away


def main() -> int:
    print("building point-in-time Elo (no lookahead) ...")
    res = elo.build_ratings(data.load_results())
    params = baseline.calibrate(res.calib)
    cal = res.calib.copy()
    cal["d"] = pd.to_datetime(cal["date"]).dt.strftime("%Y-%m-%d")
    cal["h"] = cal["home_team"].map(_canon)
    cal["a"] = cal["away_team"].map(_canon)
    lut = {(r.d, r.h, r.a): (r.dr_eff, bool(r.neutral)) for r in cal.itertuples(index=False)}

    spi = pd.read_csv(SPI).dropna(subset=["prob1", "prob2", "probtie", "score1", "score2"])
    print(f"SPI matches with probs+results: {len(spi)}")

    my, sp, y = [], [], []          # my probs, SPI probs (each [H,D,A]), realized outcome idx
    matched = 0
    for r in spi.itertuples(index=False):
        d = str(r.date)[:10]
        t1, t2 = _canon(r.team1), _canon(r.team2)
        if (d, t1, t2) in lut:           # SPI team1 == home
            dr, neu = lut[(d, t1, t2)]; flip = False
        elif (d, t2, t1) in lut:         # teams listed in the other order
            dr, neu = lut[(d, t2, t1)]; flip = True
        else:
            continue
        matched += 1
        home, away = (r.team2, r.team1) if flip else (r.team1, r.team2)
        exp = baseline.make_expectation(home, away, {home: dr, away: 0.0}, params, neutral=neu)
        myp = [exp.p_home, exp.p_draw, exp.p_away]
        spp = [r.prob1, r.probtie, r.prob2] if not flip else [r.prob2, r.probtie, r.prob1]
        gd = int(r.score1 - r.score2) * (-1 if flip else 1)
        my.append(myp); sp.append(spp); y.append(outcome_idx(gd))

    my = np.clip(np.array(my), EPS, 1); my /= my.sum(1, keepdims=True)
    sp = np.clip(np.array(sp), EPS, 1); sp /= sp.sum(1, keepdims=True)
    y = np.array(y)
    rows = np.arange(len(y))
    print(f"aligned to my Elo: {matched} matches ({matched/len(spi)*100:.0f}% of SPI)\n")

    # per-match scores on the realized outcome
    ll_my = -np.log(my[rows, y]); ll_sp = -np.log(sp[rows, y])
    onehot = np.eye(3)[y]
    br_my = ((my - onehot) ** 2).sum(1); br_sp = ((sp - onehot) ** 2).sum(1)

    print(f"{'forecast':<14}{'log-loss':>10}{'brier':>9}")
    print(f"{'my model':<14}{ll_my.mean():>10.4f}{br_my.mean():>9.4f}")
    print(f"{'538 SPI':<14}{ll_sp.mean():>10.4f}{br_sp.mean():>9.4f}")
    print(f"{'uniform 1/3':<14}{-np.log(1/3):>10.4f}{(2/3):>9.4f}")

    # Diebold-Mariano on the per-match log-loss difference (d>0 => my model worse).
    d = ll_my - ll_sp
    rng = np.random.default_rng(0)
    boot = np.array([d[rng.integers(0, len(d), len(d))].mean() for _ in range(2000)])
    lo, hi = np.percentile(boot, [2.5, 97.5])
    t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))
    print(f"\nDiebold-Mariano (log-loss diff, my - SPI): mean {d.mean():+.4f}  "
          f"95% CI [{lo:+.4f}, {hi:+.4f}]  t={t:+.2f}")
    verdict = ("my model SIGNIFICANTLY WORSE than SPI" if lo > 0 else
               "my model SIGNIFICANTLY BETTER than SPI" if hi < 0 else
               "no significant difference vs SPI")
    print(f"  -> {verdict}")

    # Forecast-combination (encompassing) weight: p = w*my + (1-w)*SPI, minimize log-loss.
    ws = np.linspace(0, 1, 101)
    losses = [(-np.log((w * my + (1 - w) * sp)[rows, y])).mean() for w in ws]
    w_star = ws[int(np.argmin(losses))]
    print(f"\nforecast-combination weight on my model: w* = {w_star:.2f}")
    print(f"  (w*~0 => my model adds nothing over SPI / is encompassed; "
          f"w*~1 => SPI adds nothing; in between => both carry information)")
    print("\nNOTE: benchmark is 538 SPI (a sharp public MODEL), not the betting market. The "
          "market-price version is pre-registered to grade on 2026 results we now log.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
