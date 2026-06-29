# xResidual collector — Azure VM operations

The **collection** half of xResidual runs 24/7 on an always-on Azure VM, so no match capture
is ever lost to a sleeping laptop. The laptop keeps **analysis + rendering + posting** on data
pulled down from the VM. This is the operational runbook: how it's wired, the daily loop,
health checks, troubleshooting, and how to rebuild it from scratch.

Deployed and verified 2026-06-09, two days before the World Cup opener.

```
   Azure VM  (always on, collects)            Laptop  (analyses, renders, posts)
   ────────────────────────────────           ──────────────────────────────────
   logger-free        every 30 min            make pull              (rsync data down)
   logger-orderbooks  every 30 min      →      bash scripts/refresh_daily.sh
   logger-oddsapi     00/06/12/18 UTC          git add -A && commit && push
   matchwatch         every 10 min
     └─ auto-captures each fixture (~3h)
```

The VM **never renders** (headless Chrome won't fit in ~900 MB RAM) — that stays on the laptop.
The VM **only collects**. The laptop is the single place analysis history lives and where cards
are built.

---

## The VM

| | |
|---|---|
| Name | `Sportslogging` |
| Subscription | Azure for Students (~$7–8/mo against the $100 credit) |
| Size | Standard **B2ats v2** — 2 vCPU, ~900 MB RAM, **+ 2 GB swap file** |
| OS | Ubuntu Server 22.04 LTS (Gen2) |
| Address | `azureuser@57.154.16.193` |
| SSH key | `Sportslogging_key.pem` in the repo root (chmod 600); override with `XRES_KEY`/`KEY`/`LEADLAG_KEY` |
| Repo path | `/home/azureuser/xResidual` |
| venv | `/home/azureuser/xResidual/.venv` |
| Inbound | SSH (22) only |

**Keep Azure auto-shutdown OFF** (Portal → VM → Auto-shutdown) — this box must run 24/7.

---

## Daily loop

From the repo root on the laptop:

```bash
make pull                       # rsync the VM's logger/data down  (see Makefile note below)
bash scripts/refresh_daily.sh   # forwardtest + P10 + elimination + paper report + render 26 cards
git add -A && git commit && git push
```

The `make` shortcuts (run from the repo root). If you symlinked `ln -s deploy/Makefile Makefile`,
drop the `-f`; otherwise prefix every target with `-f deploy/Makefile`:

| command | what it does |
|---|---|
| `make pull` | rsync `logger/data/` **down** from the VM (snapshots, captures, analysis) |
| `make push-code` | rsync code/source **up** (excludes `.git`, `.venv`, `logger/data`, `*.png`) |
| `make push-secrets` | push `.env`, `logger/config.json`, `.kalshi_private_key.pem` up |
| `make status` | timer schedule + last log lines |
| `make timers` | next/last run of each timer |
| `make logs` | tail all VM logs |
| `make ssh` | shell into the VM |

---

## What runs on the VM (systemd timers)

Four timers, installed in `/etc/systemd/system/`, enabled via `deploy/systemd/install-units.sh`:

| timer | command | schedule |
|---|---|---|
| `xresidual-logger-free` | `run.py --venues polymarket,kalshi` | every 30 min |
| `xresidual-logger-orderbooks` | `run.py --venues orderbooks` | every 30 min |
| `xresidual-logger-oddsapi` | `run.py --venues oddsapi` | 00/06/12/18 UTC |
| `xresidual-matchwatch` | `scripts/match_scheduler.py` | every 10 min |

`matchwatch` polls the fixture list and, ~35 min before each kickoff, spawns a detached ~3 h
`ws_capture` for that match. Its unit sets **`KillMode=process`** — required, because the
scheduler exits immediately after spawning the capture, and systemd's default
(`control-group`) would otherwise kill the detached capture along with it.

Logs land in `logger/data/svc.log` (loggers) and `logger/data/matchwatch.log` (scheduler).

---

## Health checks

```bash
make status                                    # timers + last svc.log lines
make ssh                                        # then, on the VM:
  grep -c snapshot ~/xResidual/logger/data/svc.log         # snapshots collected today
  systemctl list-timers 'xresidual-*' --no-pager           # all four scheduled?
  ls -la ~/xResidual/logger/data/ws-events-*.jsonl         # captures landed (after a match)
```

A healthy logger line looks like:
`snapshot — polymarket: 60 ok / 0 err, kalshi: 264 ok / 0 err`.
(Order books showing a few `err` is normal — some markets don't expose a book pre-tournament.)

---

## Secrets

Live only on the two machines, never in git:

- repo-root `.env` — `KALSHI_ACCESS_KEY`, `KALSHI_PRIVATE_KEY_PEM_PATH`, `ODDSAPI_KEY`
- `logger/config.json` — Polymarket/Kalshi market ids + oddsapi feed config
- `.kalshi_private_key.pem` — Kalshi RSA key (chmod 600)

`KALSHI_PRIVATE_KEY_PEM_PATH` is stored relative, and `envtools.resolve_path` resolves it
against the repo root, so the same `.env` works unchanged on both machines.
Re-push after any change: `make push-secrets`.

---

## Notes & gotchas

- **`make` needs the Xcode license** on macOS (`sudo xcodebuild -license`, done 2026-06-09).
  Before that, run the underlying `rsync`/`ssh` commands directly.
- **No double-collection.** The laptop's four launchd *collectors*
  (`com.xresidual.logger.{free,orderbooks,oddsapi}`, `com.xresidual.matchwatch`) are unloaded so
  the VM is the single source of truth. The laptop keeps `com.xresidual.render` and
  `com.xresidual.forwardtest`, which run on pulled data. Re-enable a collector if ever needed
  with `launchctl load -w ~/Library/LaunchAgents/<label>.plist`.
- **Transition day (2026-06-09 only).** The VM started mid-day, so its first
  `snapshots-2026-06-09.jsonl` was thinner than the laptop's full day. The two were merged into
  a complete 19,876-line file; the laptop's pre-cutover copy is kept at
  `snapshots-2026-06-09.laptop.bak`. From 2026-06-10 the VM owns complete daily files and
  `make pull` just overwrites cleanly — no merge needed.
- **Code changes:** `make push-code`, then restart on the VM only if you edited a *unit file*
  (`sudo systemctl daemon-reload && sudo systemctl restart 'xresidual-*.timer'`). Logic changes
  in the Python are picked up on the next tick automatically.
- **Odds API quota** is 500 calls/mo (free tier); 4×/day per feed stays well under. Don't
  shorten the oddsapi interval without checking the quota.

---

## Rebuild from scratch (disaster recovery)

If the VM is lost, provision a fresh Ubuntu 22.04 VM (B2ats v2, SSH-only inbound, auto-shutdown
off), point `deploy/Makefile`'s `VM`/`KEY` at it, then from the repo root:

```bash
make first-deploy                 # push code + secrets, run setup.sh (swap, venv, deps)
make ssh                          # then on the VM:
  cd ~/xResidual/logger && ../.venv/bin/python run.py --venues polymarket,kalshi   # smoke test
  bash ~/xResidual/deploy/systemd/install-units.sh                                  # enable timers
```

`deploy/` contents:

```
deploy/
  README.md            ← this file
  Makefile             ← laptop control panel (VM ip + key path at the top)
  setup.sh             ← run on the VM: swap + venv + deps  (idempotent)
  systemd/
    install-units.sh   ← run on the VM: copy units, enable + start timers
    xresidual-logger-free.{service,timer}
    xresidual-logger-orderbooks.{service,timer}
    xresidual-logger-oddsapi.{service,timer}
    xresidual-matchwatch.{service,timer}
```
