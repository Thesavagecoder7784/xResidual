# Notes

A running scratchpad of decisions, dead ends, and things I still want to do. Less polished than the rest of the repo on purpose.

## Decisions I'd defend

- **Home advantage = 85 Elo, not 100.** The 100 I started with implied way more than the ~0.47 goals you actually see in the data. Recalibrated it down. Small thing, but it was making the host sims too hot.
- **Dropped the altitude factor.** I went in assuming thin air → more goals (it's the folk-wisdom prior for Mexico City). Regressed total goals on venue altitude across ~50k matches and the coefficient came back *negative*. So it's gone. Leaving it in would just have been me forcing a prior the data didn't back.
- **Blended squad value into Elo.** Pure Elo loved Argentina and underrated France/England, because Elo only sees results, not how good the squad actually is. Peeters (2018) says transfer value out-predicts ratings for internationals, so I blended Transfermarkt values in. The gap vs Opta went from ~4.7pp to ~0.7pp. This was the moment the model stopped arguing with the market.
- **Multiplicative devig as the default, but I keep power and Shin around.** The margin isn't loaded evenly across the board, so the method matters at the longshots. The favourites (where most of my findings live) barely move, but I'd rather report the sensitivity than pick one quietly.

## Things I'm not sure about

- The cross-venue basis residuals (USA/Mexico richer on Kalshi, England/Portugal/Japan richer on Polymarket) are one snapshot so far. It *looks* like a home-crowd tilt, but I won't believe it until the logged series shows it holding for a week+.
- The "most open field in recent World Cups" line is true as far as I can check, but the 48-team format mechanically flattens the top, so I keep it as "recent," never "ever."
- Whether anyone actually leads price discovery (Kalshi vs Polymarket) is still open — I can't answer it until matches start throwing goals at both books.

## TODO

- Capture a marquee match end-to-end and fill in `writeups/lead-lag.md` (it's a scaffold until then).
- First calibration check-in after the group stage (~Jun 27): CORP reliability + Brier decomposition.
- Grade the pre-registration predictions publicly after the final.
- The goal model holds total goals flat (2.76/match) and only splits it by strength, so it under-produces blowouts. If I want real scoreline/blowout probabilities I need totals to scale with the mismatch. Not done yet.

## Stack notes

- Logger runs on `launchd`, append-only JSONL, one file a day. The one rule is never lose data, so every write is flushed and fsync'd.
- ws capture stamps every event with one local ms clock on purpose — that's what makes a cross-venue lead real instead of clock skew.
- `python scripts/build_all.py` rebuilds everything. Heavy AI assistance throughout; the design calls and the stats decisions are mine.
