# Extending xResidual to macro: are Kalshi's economic contracts calibrated?

*A short extension of the [xResidual](https://github.com/Thesavagecoder7784/xResidual) methodology from sports to the market segment that actually matters institutionally. Reproducible: [`scripts/macro_calibration.py`](../scripts/macro_calibration.py).*

## Why this exists

The World Cup was a clean **testbed** — goals are exogenous, repeated information shocks, ideal for measuring price discovery. But the durable value of prediction markets isn't sports; it's **macro/economic event contracts** (CPI, Fed decisions, GDP), which the Fed and NBER now study as forecasters and where the institutional volume is heading. So I pointed the same tools at that market.

**First finding — a structural one.** *Cross-venue* price discovery isn't available on macro: **Polymarket doesn't run CPI/Fed/GDP contracts** (it's politics/crypto/culture); **Kalshi is the macro venue.** So the right question for a single venue is the one institutions actually ask when they use these markets as a **signal source**: *are they calibrated?*

## Method

Pull every **settled** Kalshi market in the macro series (`KXCPI`, `KXCPIYOY`, `KXFED`, `KXFEDDECISION`, `KXGDP`), take each market's last-traded probability at a fixed **lead before resolution** (from daily candlesticks, strictly before the cut so there's no look-ahead), pair it with the binary outcome, and score calibration (Brier vs base-rate, log-loss, a reliability table) across several horizons.

## Result: calibrated, and sharpening as the release nears

| Forecast horizon | Brier (market) | Brier (base rate) | Brier skill |
|--|--|--|--|
| ~3 days out | 0.017 | 0.25 | **+93%** |
| ~14 days out | 0.016 | 0.25 | **+94%** |
| ~30 days out | 0.039 | 0.25 | **+84%** |

The market is **exceptionally calibrated** close to the release and degrades gracefully with horizon — its Brier roughly **doubles from 3 days to 30 days out**, exactly the "forecast sharpens as the event nears" shape you'd hope for. Even a **month ahead**, an +84% Brier skill score over the base rate means Kalshi's macro markets are a strong forecast, not noise. The reliability table is monotone — low-priced strikes almost never hit, high-priced ones almost always do.

This is the same headline as the sports flagship, now on the contracts that count: **the market is a very good forecaster, and the interesting work is measuring *how* good, at what horizon — not trying to beat it.**

## Honest limitations

Small and clustered: only ~5–7 distinct macro *releases* so far, and the CPI/GDP **threshold ladders cluster within a single release** (one CPI print resolves the whole -0.4/-0.3/-0.2… strike ladder at once), so the honest unit is the release, not the ~50 markets — read the reliability *shape*, not a tight confidence interval. This is a proof-of-concept that the methodology transfers and the signal is real, not a definitive calibration study; it tightens as Kalshi's macro history accumulates.

## Why it matters

Two things. (1) It shows the xResidual toolchain isn't sports-specific — the **same price-discovery and calibration machinery prices an FOMC or CPI contract**, which is where the regulatory safety and the institutional demand live. (2) It's a live demonstration of the **"prediction markets as a calibrated macro signal"** use case — the stage-one institutional adoption that the Fed, Goldman, and the macro desks are actually acting on.
