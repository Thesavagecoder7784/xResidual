# Notes

A running scratchpad of decisions, dead ends, and things I still want to do. Less polished than the rest of the repo on purpose.

## Decisions I'd defend

- **Home advantage = 85 Elo, not 100.** The 100 I started with implied way more than the ~0.47 goals you actually see in the data. Recalibrated it down. Small thing, but it was making the host sims too hot.
- **Dropped the altitude factor.** I went in assuming thin air → more goals (it's the folk-wisdom prior for Mexico City). Regressed total goals on venue altitude across ~50k matches and the coefficient came back *negative*. So it's gone. Leaving it in would just have been me forcing a prior the data didn't back.
- **Blended squad value into Elo.** Pure Elo loved Argentina and underrated France/England, because Elo only sees results, not how good the squad actually is. Peeters (2018) says transfer value out-predicts ratings for internationals, so I blended Transfermarkt values in. The gap vs Opta went from ~4.7pp to ~0.7pp. This was the moment the model stopped arguing with the market.
- **Multiplicative devig as the default, but I keep power and Shin around.** The margin isn't loaded evenly across the board, so the method matters at the longshots. The favourites (where most of my findings live) barely move, but I'd rather report the sensitivity than pick one quietly.
- **Corrected Elo's confederation inflation (empirical-Bayes shrinkage).** Elo is zero-sum and confederations barely play each other, so weak ones inflate against weak regional opponents — measured ~40 Elo on CONCACAF, ~160 on OFC. I almost traded the resulting "mispricings" (Canada/Mexico/Japan to advance) before an independent bookmaker told me it was *my* model, not the market. Fix is a per-confederation offset scaled per team by cross-confederation game count (Glicko-RD-style shrinkage), applied before the squad blend. +4.6% OOS cross-confed RPS, DM p≈0.009, placebo-clean within-confederation. I picked the count-based EB weight over my first `(1-share)^p` heuristic after a research check flagged the share-vs-count issue — same one parameter, but it actually means something.
- **Tightened the in-play shock detector after the Argentina–Iceland dry-run.** The naive version (4pp move in 60s, 30s refractory) turned 3 goals into 11 "shocks" on a thin friendly. Now: ≥5pp that *persists* ≥50% after 20s (kills flicker-and-snap-back blips), 5-min refractory (one goal = one shock). 11 → 3. A vol-relative threshold was tempting but ill-conditioned here — these markets sit dead flat between events, so realized vol ≈ 0 and everything looks like infinite sigma.
- **Left sigma alone — the dispersion isn't the problem.** When the model still ran a touch hot on a few mid-tier sides vs the bookmaker, the tempting move was to retune the team-strength uncertainty (sigma=60). But I checked: the title distribution is *not* under-dispersed — it's slightly *over*-concentrated vs the bookmaker (top-3 43% vs 39%), and matching the bookmaker's shape would mean over-riding a sigma that's calibrated out-of-sample on real match RPS, just to fit the market. The residual gaps are team-specific (we like Spain/Argentina a hair more, Brazil a hair less — the Elo-vs-talent tension), not a global dispersion error. So I didn't touch it; curve-fitting individual teams to the market is exactly the trap I avoid elsewhere.

## Things I'm not sure about

- The cross-venue basis residuals (USA/Mexico richer on Kalshi, England/Portugal/Japan richer on Polymarket) are one snapshot so far. It *looks* like a home-crowd tilt, but I won't believe it until the logged series shows it holding for a week+.
- The "most open field in recent World Cups" line is true as far as I can check, but the 48-team format mechanically flattens the top, so I keep it as "recent," never "ever."
- Whether anyone actually leads price discovery (Kalshi vs Polymarket) is still open — I can't answer it until matches start throwing goals at both books.

## TODO

- Capture a marquee match end-to-end and fill in `writeups/lead-lag.md` (it's a scaffold until then). *Partial:* captured Argentina–Iceland end-to-end (172k ms events), but Kalshi didn't list the friendly so there's no cross-venue pair yet — lead-lag still needs a match both books quote.
- The real goal-overreaction (P10) test still pending a *surprising* goal — the friendly favourite-win was a weak test by design. Detector is tightened and ready.
- First calibration check-in after the group stage (~Jun 27): CORP reliability + Brier decomposition.
- Grade the pre-registration predictions publicly after the final.
- The goal model holds total goals flat (2.76/match) and only splits it by strength, so it under-produces blowouts. If I want real scoreline/blowout probabilities I need totals to scale with the mismatch. Not done yet — and confirmed it matters: pricing the tournament-total-goals O/U showed the 2.76 baseline (fit on all internationals) runs hot vs WC scoring (~2.65), so any totals edge needs a WC-recalibrated goal model first. Left it; not chasing the totals market on an uncalibrated base.

## Stack notes

- Logger writes append-only JSONL, one file a day. The one rule is never lose data, so every write is flushed and fsync'd. (Started on laptop `launchd`; moved to the always-on VM below once captures couldn't depend on the laptop being awake.)
- ws capture stamps every event with one local ms clock on purpose — that's what makes a cross-venue lead real instead of clock skew.
- Captures are per-match files (`ws-events-<ts>-<slug>.jsonl`), and the live card archives per-match too (`live_match-<slug>.png` via `--render`) so a new fixture never overwrites the last one's tape. The shared `_livematch.js` stays for the 5s auto-refresh during a live match.
- Capture collection lives on an always-on Azure VM (systemd timers), not the laptop — `make pull` rsyncs the data down. Resolved the old laptop-sleep-misses-kickoff risk.
- `python scripts/build_all.py` rebuilds everything. Heavy AI assistance throughout; the design calls and the stats decisions are mine.
