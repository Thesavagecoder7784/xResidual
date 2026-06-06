# xResidual price logger

Records prediction-market quotes for 2026 World Cup markets across venues, on an
interval, append-only. **This is the one time-gated component of the project:**
intraday cross-venue price history cannot be reconstructed after the fact, so this
must run continuously from before the first match (June 11, 2026). It also doubles
as liquidity verification: markets it can't populate are markets we can't analyze
(see [METHODOLOGY.md](../METHODOLOGY.md) §6).

## Setup

```bash
pip install -r requirements.txt
cp config.example.json config.json   # then fill in real market ids
```

Credentials live in the repo-root `.env` (gitignored), read automatically:

```
KALSHI_ACCESS_KEY=...
KALSHI_PRIVATE_KEY_PEM_PATH=.kalshi_private_key.pem   # relative to repo root
ODDSAPI_KEY=...
```

## Run

```bash
python run.py                              # one pass over all configured venues
python run.py --loop 300                   # every 5 min, runs forever
python run.py --venues polymarket,kalshi   # restrict to a subset
```

**Active scheduler: `launchd`** (two user LaunchAgents in `~/Library/LaunchAgents/`).
launchd is used instead of cron because the repo lives under `~/Documents` (TCC-
protected): a user LaunchAgent inherits the login session's file access and reaches
`~/Documents` without Full Disk Access, whereas cron there fails silently. Verified
on this machine (agent wrote snapshots, exit 0).

- `com.xresidual.logger.free`: `StartInterval` 1800s + `RunAtLoad` → `polymarket,kalshi`
  (free; carries the fine-grained line movement Layer 4's velocity analysis needs).
- `com.xresidual.logger.oddsapi`: `StartCalendarInterval` 00/06/12/18 → `oddsapi`
  (every 6h ≈ 16 credits/day, within the 500/mo free tier; gives near-kickoff
  closing-line coverage once matches start).
- `com.xresidual.logger.orderbooks`: `StartInterval` 1800s + `RunAtLoad` → `orderbooks`
  (depth + spread snapshots for the full winner field on both venues; ~104 free calls
  per pass; powers the microstructure / lead-lag analysis).

Manage them:
```bash
launchctl list | grep xresidual                                   # status
launchctl kickstart -k gui/$(id -u)/com.xresidual.logger.free     # run now
launchctl bootout gui/$(id -u)/com.xresidual.logger.free          # stop/unload
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.xresidual.logger.free.plist  # reload
tail logger/data/launchd.log                                      # output
```

Agents auto-load at every login. **launchd handles sleep better than cron**: a job
whose scheduled time elapsed while the Mac slept runs once on wake (a fully powered-
off machine still misses runs). Use the real python binary path, not a shell alias.

Cron alternative (needs `/usr/sbin/cron` granted Full Disk Access for a `~/Documents`
repo): `*/30 * * * * cd /ABS/logger && /usr/local/bin/python3 run.py --venues polymarket,kalshi >> data/run.log 2>&1`

> **Tournament-time caveat:** daily Odds API is fine pre-tournament (lines barely
> move) and for the outright trajectory, but the match-calibration headline needs the
> *closing* line. Once matches start (June 11), increase the Odds API cadence (or run
> it shortly before kickoffs) so the last pre-match snapshot is genuinely close to
> kickoff.

## What it writes

Append-only JSONL, one file per UTC day: `data/snapshots-YYYY-MM-DD.jsonl`.
Each line is one `Quote` (see [storage.py](storage.py)): timestamp, venue, market id,
outcome, bid/ask/mid/last, volume, liquidity, and a venue-specific `extra`. Prices
are in **probability units (0–1)**; adapters convert (Kalshi cents → /100, Odds API
decimal odds → 1/odds renormalized to strip the overround per book).

Failed fetches are recorded as `outcome: "__error__"` rather than dropped, so
coverage gaps are auditable instead of silent.

## Venue status

| Venue | Auth | Status |
|---|---|---|
| Polymarket | none (public Gamma API) | **live**: winner field via `event_slug` (one call → 60 team markets) |
| Kalshi | access key + RSA private key | **live**: winner field (`KXMENWORLDCUP`, 56 markets) + per-match h2h (`KXWCGAME`, all 72 group games, tagged `market_type="match"`), each one list call |
| Odds API | API key | **live**: h2h + spreads + totals + outrights across many bookmakers, incl. Betfair Exchange (back + `*_lay`) |

Config supports two entry shapes per venue: a single market (`id`/`ticker`) or a
whole field (`event_slug`/`series_ticker`). The winner-field markets are tagged
`market_type="winner"`, so all three venues feed the Layer 4 trajectory.

## Real-time capture for lead–lag (`ws_capture.py`)

A separate, event-driven capturer for the cross-venue price-discovery flagship,
*not* the polling logger. It holds persistent websockets to Kalshi
(`orderbook_delta`/`ticker`/`trade`, authenticated) and Polymarket (`book`/
`price_change`, public) and stamps every event with a **local millisecond clock**,
the one reference that makes lead–lag immune to server-clock skew. Auto-reconnects,
heartbeats, append-only to `data/ws-events-*.jsonl`.

```bash
python ws_capture.py --match "Mexico vs South Africa" --seconds 9000  # auto-discover, capture
python ws_capture.py --outright-test --seconds 30                      # validate plumbing (live)
python ws_capture.py --kalshi <tickers> --polymarket <token_ids> --seconds 7200  # manual
```

`--match` discovers the markets for you, no need to paste tickers/token-ids. Kalshi
match markets (series `KXWCGAME`, all 72 group games) are live now; the opener
resolves to `KXWCGAME-26JUN11MEXRSA-{MEX,RSA,TIE}`. Analysis: `xresidual.ws_events`
reconstructs each venue's mid series (Kalshi from `ticker`; Polymarket from the book
snapshot + `price_change` deltas) and `lead_lag_ms` reports which venue moves first.

### Match-day routine (the only hands-on task)
1. **A few hours before**, check whether Polymarket has listed the match yet:
   `python ws_capture.py --match "X vs Y" --seconds 60`, look at the "polymarket
   tokens" line. Per-match Polymarket markets appear close to kickoff; Kalshi's are
   already up.
2. **~30 min before kickoff**, launch the real capture:
   `python ws_capture.py --match "X vs Y" --seconds 9000` (covers pre-match + match).
3. **After**, run `xresidual.ws_events.lead_lag_ms(...)` on the captured file.

Caveats: the cross-venue lead–lag needs **both** venues, so it only works once
Polymarket lists the match (re-run `--match` close to kickoff). Knockout matchups
only get tickers after the bracket is set. Until Polymarket's match market appears,
the cleanest cross-venue lead–lag is on the **outright winner** market (both venues
have it now) during a big match.

The Odds API replaced a direct Betfair integration: one call returns h2h and
outright odds across many books *including* Betfair Exchange. Lay prices arrive
tagged `market_type: *_lay`; filter to back/`h2h` for calibration and don't mix them.

## Odds API quota (important)

Free tier = **500 credits/month**. Cost per call = (#markets × #regions). The
configured setup is 2 feeds (match h2h + outright winner) × 1 region = **2 credits
per pass**.

- Tournament ≈ 39 days (Jun 11 – Jul 19) → ~650 free credits available.
- At 2 credits/pass that's ~325 passes ≈ **one pass every ~3 hours**.

To go finer (more regions, or 5-min cadence on match days), upgrade the plan.
Polymarket and Kalshi are free, so poll those every 5 min regardless.

## Status / checklist

- [x] Credentials wired and validated (Kalshi signing, Odds API key).
- [x] Odds API live (match h2h + outright winner, overround stripped).
- [ ] Add Polymarket Gamma market ids to `config.json` (optional; Odds API already covers match + outright).
- [ ] Add Kalshi tickers to `config.json` for the WC markets you want.
- [ ] Verify the WC sport keys are still active closer to June 11 (`/v4/sports`).
- [ ] Schedule the two crons; confirm `data/snapshots-*.jsonl` is growing.
