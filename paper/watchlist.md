# Watchlist — structural parlays (unpriced, model views ready)

Markets where our model has a clear view but the venue **hasn't quoted yet** (no bid/ask/
last). When any gets a real quote, compare to the model number and trade only if the gap is
real and survives the caveat. All Kalshi.

| market | model view | trade when priced if… | caveat |
|---|---|---|---|
| `KXWCHOSTKO` — all 3 hosts reach knockouts | **~60%** (USA 75 × Mex 89 × Can 91, independent groups) | market ≪ 60% → buy; ≫ 60% → fade | model likely over-weights home advantage; shade the 60% down |
| `KXWCTOTALGOAL` — tournament total goals | **~287** (2.76 g/match × 104; ~270–280 WC-adjusted) | a strike materially below ~275 trades cheap → over | 2.76 is calibrated on *all* internationals; WC runs ~2.65, so lean ~270–280 |
| `KXWCGROUPWINELIM` — group winners out in R32 | **~3–4 of 12** (group winners ~65–70% to win their R32) | the 3+/4+ strikes price far from ~30–35% | single-elimination variance is high; estimate, not a sim |

**How to use:** re-check quotes when a match nears or daily; refresh the model views from the
latest sim. These are *contingent* trades — no position until there's a price and a gap.

These came out of the full World Cup market sweep (June 2026). The held positions and the
findings live in `theses.md` / `FINDINGS.md`; this file is just the not-yet-priced queue.
