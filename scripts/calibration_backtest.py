#!/usr/bin/env python3
"""Layer 3 calibration dry-run on historical 538 international forecasts.

    python scripts/calibration_backtest.py [--league "World Cup"]

Exercises the exact calibration code that will grade the live 2026 market data
(reliability diagram, Murphy/Brier decomposition, calibration regression, ECE) on a
real (forecast, outcome) set, so the headline analysis is validated before June 11.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xresidual import calibration as cal  # noqa: E402
from xresidual import data_spi  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default=None, help="filter to a competition substring")
    ap.add_argument("--bins", type=int, default=10)
    args = ap.parse_args()

    df = data_spi.load_spi_intl(league_contains=args.league)
    label = args.league or "all internationals"
    print(f"calibration backtest — {label}: {len(df):,} completed matches "
          f"({df['date'].min()} -> {df['date'].max()})")

    p, y = cal.flatten_wdl(df["p_home"], df["p_draw"], df["p_away"], df["outcome"])
    print(f"pooled binary events: {len(y):,} (3 per match), base rate {y.mean():.3f}\n")

    print("reliability table:")
    tab = cal.reliability_table(p, y, n_bins=args.bins)
    print("  bin          n     mean_pred   obs_freq   95% CI")
    for _, r in tab.iterrows():
        if r["n"] == 0:
            continue
        print(f"  {r['bin']:<11} {int(r['n']):>5}   {r['mean_pred']:>8.3f}   "
              f"{r['obs_freq']:>8.3f}   [{r['ci_lo']:.3f}, {r['ci_hi']:.3f}]")

    md = cal.murphy_decomposition(p, y, n_bins=args.bins)
    brier = cal.brier_score(p, y)
    ece = cal.expected_calibration_error(p, y, n_bins=args.bins)
    a, b = cal.calibration_regression(p, y)
    corp = cal.corp(p, y)

    print(f"\nBrier score (raw): {brier:.4f}")
    print(f"Murphy decomposition (binned): reliability={md.reliability:.4f}  "
          f"resolution={md.resolution:.4f}  uncertainty={md.uncertainty:.4f}")
    print(f"  check: REL - RES + UNC = {md.brier_binned:.4f} (binned Brier)")
    print(f"CORP decomposition (isotonic, exact): MCB={corp.mcb:.4f}  "
          f"DSC={corp.dsc:.4f}  UNC={corp.unc:.4f}")
    print(f"  check: MCB - DSC + UNC = {corp.mcb - corp.dsc + corp.unc:.4f} == raw Brier {corp.brier:.4f}")
    print(f"ECE: {ece:.4f}")
    print(f"calibration regression: a={a:+.3f}, b={b:.3f}  "
          f"(perfect = a 0.0, b 1.000)")

    print("\ninterpretation:")
    print(f"  - reliability {md.reliability:.4f}: "
          + ("well calibrated" if md.reliability < 0.005 else "some miscalibration"))
    if b < 0.95:
        print(f"  - b={b:.3f} < 1: forecasts slightly OVERconfident (favorite-longshot signature)")
    elif b > 1.05:
        print(f"  - b={b:.3f} > 1: forecasts slightly UNDERconfident")
    else:
        print(f"  - b={b:.3f}: ~unit slope, no systematic over/under-confidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
