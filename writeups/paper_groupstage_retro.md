# Paper book — group-stage retrospective (settled 2026-06-28)

The 2026 World Cup group stage is closed out on the paper book. 10 resolved positions
settled at their binary outcomes (`paper/paper.py close`), leaving 6 knockout/season
positions open.

## Result

| | |
|---|--:|
| Money deployed (closed) | $1,225 |
| Realized P&L (net of 100bps) | **+$77.0** (+6.3% ROI) |
| Open (knockout/season) | 6 positions, −$12.4 unrealized |
| **Combined** | **+$64.5** |
| Win rate (closed) | 64% |

## P&L by lane — the edge landed where the research said it would

| Lane | n | staked | realized | ROI | win% |
|---|--:|--:|--:|--:|--:|
| **Advance (FLB / favourite–longshot)** | 21 | $600 | **+$181** | **+30%** | 86% |
| BTTS / single-game | 8 | $150 | −$45 | −30% | 12% |
| Group winner | 4 | $175 | −$72 | −41% | 25% |
| Champion / season | 2 | $200 | +$12 | +6% | 100% |
| Reach QF | 1 | $100 | +$1 | — | 100% |

- **The advance / favourite–longshot basket carried the book** (+$181 on $600). Both sides of the
  tilt paid: fading overpriced weak-team-advance (NO, +$117) and backing underpriced favourites
  (YES, +$65). This is the FLB wedge the project documented, working live, and it got the most
  capital — correct allocation toward the researched edge.
- **The losses were confined to the no-edge lanes** the project's own guardrails flag: BTTS (the
  model is flat on totals) and group-winner (a low-edge coin-flip market). Cutting both would have
  taken the book from +$77 to ~+$194. They are pure variance leakage.

## The honest caveats

1. **Correlation inflates the win rate.** The 21 advance bets all resolve on one event (the group
   stage), so it is closer to one big correlated bet than 21 independent edges. "86%" is not a
   repeatable hit rate.
2. **CLV is ~neutral (49% positive).** Closing-line value is the skill signal that doesn't depend on
   who won, and it is a coin flip. Positive P&L with neutral CLV means this group stage was more
   outcome-realisation than demonstrated edge. A promising live data point, not a proven edge.

## Going forward

- **Prune the no-edge lanes** (BTTS, group-winner) — documented non-edges adding variance.
- **Concentrate on the FLB / reach-round lane** through the knockouts (the 6 open positions are
  mostly reach-round NO fades — same thesis).
- **Grade on CLV, not P&L.** If the tilt is real, CLV should turn positive over the knockouts; if it
  stays ~50%, the group-stage win was variance and we say so.
