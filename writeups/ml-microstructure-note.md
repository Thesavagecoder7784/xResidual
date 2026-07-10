# Does the order book predict the next tick? An ML slice — and why I don't claim the edge

*An ML extension of [xResidual](https://github.com/Thesavagecoder7784/xResidual)'s order-flow work, on the same tapes, with the validation that decides whether to believe it. Reproducible: [`scripts/ml_microstructure.py`](../scripts/ml_microstructure.py).*

## The question

The flagship OFI study regresses next-second mid returns on order-flow imbalance *linearly*. The microstructure-ML literature says a fuller book-state feature set carries real, if small, short-horizon predictability, and that nonlinearity matters. So: *on our tapes, does gradient boosting on the full book state (OFI, spread, depth, imbalance, microprice deviation, lagged returns) beat the linear baseline at predicting the next 1-second mid move — and if it looks like it does, does that survive scrutiny?*

## The first result looked great. Then I attacked it.

A single chronological train/test split (4 train / 2 test matches, 141k/74k bin-rows) gave the GBM **56.3% out-of-sample directional accuracy** vs 51% for linear-OFI — and the linear models were worthless out of sample. Encouraging. But a single split on six matches is exactly the kind of number that lies, so I ran three checks.

**(1) Permutation-null control — is there hidden leakage?** Shuffle the training labels and refit: R² → −0.0003, direction → 47.4% (≈50%). **Clean.** The pipeline isn't cheating; the gridding is last-value-forward-filled (no look-ahead), and features at bin *i* strictly precede the target over *i+1*.

**(2) Raw vs de-drifted direction — is it microstructure or just trend?** The model's *raw* up/down accuracy is **69–73%** — but a prediction-market mid drifts steadily toward the resolving outcome, and predicting "the drift continues" is trivial, not alpha. Standardizing the return per contract removes that drift; what's left — the genuine book-state signal — is the **56.3%**, not the 70%.

**(3) Leave-one-match-out — does even that survive?** Retraining on five matches and testing on the held-out sixth, six times over:

| | mean | range | matches > 50% |
|--|--|--|--|
| de-drifted (microstructure) direction | **52.2%** | [33%, 62%] | **4 / 6** |
| raw (incl. drift) direction | 72.9% | — | 6 / 6 |

**This is the honest verdict.** The de-drifted microstructure signal is **weak and match-dependent** — ~52% on average, with one match actually at 33% and only four of six above a coin flip. The clean-looking 56.3% was a favorable split. The robust 70% is drift, not tradeable microstructure.

## What I actually conclude

- **The pipeline is sound and leakage-free** (permutation null clean), and gradient boosting does beat the linear baseline in aggregate — nonlinearity in book state carries *some* information (book imbalance is the dominant feature, as the microprice intuition predicts).
- **But I do not claim a robust edge.** Beyond the trivial drift, the short-horizon signal is ~52% directional in leave-one-match-out — real-but-weak and not proven at this sample size. That's consistent with the literature (short-horizon LOB predictability is small and hard) and with a thin six-match window (the VM prunes raw tapes at 48h).
- **And even the aggregate signal isn't a trade** — the same lesson as the flagship's un-harvestable lead: a ~52–56% directional edge at a 1-second horizon is smaller than the spread and slower than the latency to act on it.

## Why this is the right kind of result

It closes the "ML on tick data" gap — but the point isn't the number, it's the discipline: I built the model, then a permutation null, a drift/microstructure decomposition, and leave-one-match-out *caught my own first result being optimistic*, and I report the weaker truth. Finding a promising ML signal and correctly declining to claim it — separating drift from alpha, demanding it generalize across matches before believing it — is the same honesty the whole project runs on, and it's exactly the judgment a trading desk needs a hire to already have.
