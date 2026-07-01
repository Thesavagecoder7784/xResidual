#!/usr/bin/env python3
"""Auto-launch ws_capture for each World Cup fixture, hands-off.

    python scripts/match_scheduler.py            # launch any match in the lead window
    python scripts/match_scheduler.py --dry-run   # show what it WOULD do, launch nothing
    python scripts/match_scheduler.py --list       # print the upcoming-match schedule (UTC)

Designed to run every ~10 min from launchd (com.xresidual.matchwatch). On each tick it:
  1. reads data/wc2026_fixtures.csv and computes each kickoff in UTC,
  2. for any match kicking off inside the lead window (default: 35 min before to 10 min
     after kickoff) that hasn't been launched yet,
  3. spawns `ws_capture.py --match "A vs B" --seconds N` as a detached process (capture only;
     analysis runs on the laptop against pulled tapes, not on this small VM)
     (it survives this tick exiting), logging to data/capture-<key>.log,
  4. records the launch in data/captured-matches.json so it never double-launches.

Why a poller and not one long sleep: it's restart-safe (the state file is the memory),
it handles simultaneous kickoffs (each match gets its own process), and markets only
list close to kickoff — so discovery must happen at launch time, which ws_capture does.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGGER_DIR = os.path.join(ROOT, "logger")
DATA_DIR = os.path.join(LOGGER_DIR, "data")
FIXTURES = os.path.join(ROOT, "data", "wc2026_fixtures.csv")
STATE = os.path.join(DATA_DIR, "captured-matches.json")

LEAD_S = 35 * 60        # consider launching from 35 min before kickoff
GRACE_S = 10 * 60       # ... up to 10 min after (recovery if a tick was missed)
FORCE_S = 8 * 60        # launch regardless by 8 min before KO (don't miss the match)
CAPTURE_S = 10800       # knockout backstop: pre-match + 90' + stoppage + ET/pens + post
GROUP_CAPTURE_S = 9600  # group games can't reach ET/pens: 35' pre-roll + ~115' match + buffer,
                        # so cap them ~20 min tighter than the knockout backstop (less dead-air over-capture)


def kickoff_utc(date_str: str, time_str: str) -> datetime | None:
    """'2026-06-11' + '13:00 UTC-6' -> tz-aware UTC datetime."""
    m = re.match(r"(\d{1,2}):(\d{2})\s*UTC([+-]\d+)", str(time_str).strip())
    if not m:
        return None
    hh, mm, off = int(m.group(1)), int(m.group(2)), int(m.group(3))
    local = datetime.strptime(date_str, "%Y-%m-%d").replace(
        hour=hh, minute=mm, tzinfo=timezone(timedelta(hours=off)))
    return local.astimezone(timezone.utc)


def load_fixtures() -> list[dict]:
    import pandas as pd
    df = pd.read_csv(FIXTURES)
    out = []
    for r in df.itertuples():
        ko = kickoff_utc(r.date, r.time)
        if ko is None:
            continue
        # sanitize: placeholder slots carry '/' (e.g. 3C/E/F/H/I), which would break the
        # capture-<key>.log path in launch(). Replace it so the dedup key is filesystem-safe.
        key = f"{r.date}_{r.team1}_{r.team2}".replace(" ", "").replace("/", "-")
        out.append({"key": key, "team1": r.team1, "team2": r.team2,
                    "kickoff": ko, "ground": getattr(r, "ground", ""),
                    "group": str(getattr(r, "group", ""))})
    return sorted(out, key=lambda f: f["kickoff"])


ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"


def _is_placeholder(name: str) -> bool:
    """Knockout fixtures carry slot codes until the feeding games resolve: winner-of-match (W74),
    group position (1I, 2K), best-third (3A/B/C/D/F), loser (L101). No real WC team name contains a
    digit or slash, so that is a clean discriminator."""
    return bool(re.search(r"[0-9/]", str(name)))


_espn_cache: dict[str, list] = {}


def _espn_events(ko_utc: datetime) -> list[tuple[str, str, datetime]]:
    """ESPN scoreboard events in a +-1 day window around `ko_utc` -> [(home, away, kickoff_utc)].
    ESPN fills the knockout bracket with real team names as soon as the feeding game settles, so by
    the time a fixture enters the lead window its teams are named here even when our fixtures CSV
    still shows the slot code. Cached per window; failures degrade to []."""
    d0 = (ko_utc - timedelta(days=1)).strftime("%Y%m%d")
    d1 = (ko_utc + timedelta(days=1)).strftime("%Y%m%d")
    if d0 in _espn_cache:
        return _espn_cache[d0]
    out: list[tuple[str, str, datetime]] = []
    try:
        import requests
        r = requests.get(ESPN_URL, params={"dates": f"{d0}-{d1}", "limit": 200}, timeout=20)
        r.raise_for_status()
        for ev in r.json().get("events", []):
            comp = (ev.get("competitions") or [{}])[0]
            cs = comp.get("competitors") or []
            if len(cs) != 2:
                continue
            home = next((c for c in cs if c.get("homeAway") == "home"), cs[0])
            away = next((c for c in cs if c.get("homeAway") == "away"), cs[1])
            hn = home.get("team", {}).get("displayName", "")
            an = away.get("team", {}).get("displayName", "")
            try:
                ko = datetime.fromisoformat(str(ev.get("date", "")).replace("Z", "+00:00"))
            except Exception:
                ko = None
            if hn and an and ko and not (_is_placeholder(hn) or _is_placeholder(an)):
                out.append((hn, an, ko))
    except Exception:
        out = []
    _espn_cache[d0] = out
    return out


# Map any team name (ESPN's OR the fixtures' group-stage spelling) to the convention the Kalshi/
# Polymarket KNOCKOUT market titles use, which differs for a handful: Kalshi keys are usa / congodr
# / bosniaandherzegovina, so "United States", "DR Congo" and "Bosnia & Herzegovina" all miss raw.
# Applied to EVERY fixture (group stage is over, so only knockouts remain) — names not listed here
# already match and pass through unchanged.
_MARKET_NAME = {
    "united states": "USA",
    "dr congo": "Congo DR", "democratic republic of congo": "Congo DR",
    "bosnia-herzegovina": "Bosnia and Herzegovina", "bosnia & herzegovina": "Bosnia and Herzegovina",
    "korea republic": "South Korea", "ir iran": "Iran", "czechia": "Czech Republic",
    "côte d'ivoire": "Ivory Coast", "cote d'ivoire": "Ivory Coast",
}


def _market_name(name: str) -> str:
    return _MARKET_NAME.get(str(name).strip().lower(), name)


def resolve_fixture(f: dict) -> dict:
    """If a fixture carries placeholder slot names, replace team1/team2 with the real teams from
    ESPN (matched by kickoff time), mapped to the market-title convention discover_match_markets
    expects. Overwrites the names in place but PRESERVES f['key'] (built from the placeholder), so
    the launch-dedup state stays stable across ticks. No-op when names are already real or no ESPN
    event matches (then the existing wait/miss path applies, unchanged)."""
    best, best_d = None, 95 * 60        # match the scheduled kickoff within ~95 min
    for hn, an, ko in _espn_events(f["kickoff"]):
        d = abs((ko - f["kickoff"]).total_seconds())
        if d < best_d:
            best, best_d = (hn, an, ko), d
    if best:
        hn, an, ko = best
        if _is_placeholder(f["team1"]) or _is_placeholder(f["team2"]):
            f["team1"], f["team2"] = hn, an           # fill placeholder slots with the real teams
        f["kickoff"] = ko                             # correct any drift between CSV and actual KO
    # always normalize to the market-title convention — the knockout Kalshi spellings differ from
    # the fixtures' group spelling for DR Congo / Bosnia even when the fixture already names them.
    f["team1"], f["team2"] = _market_name(f["team1"]), _market_name(f["team2"])
    return f


def _load_state() -> dict:
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_state(state: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE)


def markets_ready(team1: str, team2: str) -> tuple[int, int] | None:
    """(kalshi_tickers, poly_tokens) for the match, or None if the check errors.
    Used to wait for BOTH venues to list before launching (lead-lag needs both), since
    Polymarket per-match markets appear later than Kalshi's."""
    try:
        if LOGGER_DIR not in sys.path:
            sys.path.insert(0, LOGGER_DIR)
        import envtools
        import ws_capture
        env = envtools.load_env()
        k, p, _ = ws_capture.discover_match_markets(env, team1, team2)
        return len(k), len(p)
    except Exception:
        return None


def launch(f: dict, capture_s: int) -> int:
    """Spawn a detached ws_capture for one match. Returns the child PID."""
    log_path = os.path.join(DATA_DIR, f"capture-{f['key']}.log")
    log = open(log_path, "a", encoding="utf-8")
    # Capture only — NO --analyze. The post-capture overreaction analysis is memory-heavy and
    # swap-thrashes this ~900 MB VM (it wedged in D-state for 40+ min on the USA tape, near-OOM).
    # Per the VM/laptop split, the VM owns capture; analysis runs on the laptop against pulled tapes.
    proc = subprocess.Popen(
        [sys.executable, "ws_capture.py", "--match", f"{f['team1']} vs {f['team2']}",
         "--seconds", str(capture_s)],
        cwd=LOGGER_DIR, stdout=log, stderr=log, start_new_session=True)
    return proc.pid


def main() -> int:
    ap = argparse.ArgumentParser(description="auto-launch ws_capture per WC fixture")
    ap.add_argument("--dry-run", action="store_true", help="show launches, do nothing")
    ap.add_argument("--list", action="store_true", help="print upcoming schedule and exit")
    ap.add_argument("--seconds", type=int, default=CAPTURE_S, help="capture duration")
    ap.add_argument("--lead", type=int, default=LEAD_S, help="lead window seconds before KO")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    fixtures = load_fixtures()

    if args.list:
        print(f"{len(fixtures)} fixtures · now {now:%Y-%m-%d %H:%M}Z")
        for f in fixtures[:12]:
            dt = (f["kickoff"] - now).total_seconds() / 3600
            print(f"  {f['kickoff']:%Y-%m-%d %H:%M}Z  {f['team1']} vs {f['team2']:<16} "
                  f"(T{dt:+.1f}h)  {f['ground']}")
        return 0

    state = _load_state()
    launched_now, deferred = [], []
    for f in fixtures:
        if f["key"] in state:
            continue                                   # already handled
        # Resolve names AND correct the kickoff from ESPN for near-term fixtures (ESPN is cached per
        # day, so this is ~1 call/tick) BEFORE the window test — otherwise a placeholder name or a
        # drifted CSV time (Mexico's CSV said 01:00Z, actual KO 02:00Z) misaligns the whole window.
        if (f["kickoff"] - now).total_seconds() <= args.lead + 3 * 3600:
            resolve_fixture(f)
        dt = (f["kickoff"] - now).total_seconds()      # recompute with the corrected kickoff
        if not (-GRACE_S < dt <= args.lead):           # outside the launch window
            continue
        ready = markets_ready(f["team1"], f["team2"])  # (kalshi, poly) or None
        both = bool(ready) and ready[0] > 0 and ready[1] > 0
        any_mkt = bool(ready) and (ready[0] > 0 or ready[1] > 0)
        force = dt <= FORCE_S                           # near KO: launch regardless of...
        # ...the "wait for BOTH venues" preference. But NEVER launch with zero markets on
        # either venue: ws_capture would subscribe to nothing and write a 0-byte tape (exactly
        # what happened to South Korea-Czech). Force overrides "wait for both", not "need >=1".
        if not (both or (force and any_mkt)):
            deferred.append((f, dt, ready))            # keep waiting for markets to list
            if args.dry_run:
                why = "no markets on either venue yet" if force else "both venues not yet listed"
                print(f"WOULD wait {f['team1']} vs {f['team2']} (T{dt/60:+.0f}m, k/p={ready}, {why})")
            continue
        if args.dry_run:
            print(f"WOULD launch {f['team1']} vs {f['team2']} "
                  f"(KO {f['kickoff']:%H:%M}Z, T{dt/60:+.0f}m, k/p={ready}, forced={force and not both})")
            continue
        # group games can't go to extra time/penalties, so cap their capture tighter than the
        # knockout backstop (saves ~20 min of post-match dead air per group tape). Only when using
        # the default --seconds; an explicit override is always respected.
        cap = GROUP_CAPTURE_S if (f.get("group", "").startswith("Group") and args.seconds == CAPTURE_S) else args.seconds
        pid = launch(f, cap)
        state[f["key"]] = {
            "launched_utc": now.isoformat(), "pid": pid,
            "kickoff_utc": f["kickoff"].isoformat(),
            "match": f"{f['team1']} vs {f['team2']}",
            "markets": {"kalshi": ready[0] if ready else None, "poly": ready[1] if ready else None},
            "forced": bool(force and not both)}
        launched_now.append((f, pid, ready))

    if args.dry_run:
        return 0
    if launched_now:
        _save_state(state)
        for f, pid, ready in launched_now:
            print(f"[{now:%Y-%m-%d %H:%M}Z] launched pid={pid} {f['team1']} vs {f['team2']} "
                  f"(KO {f['kickoff']:%H:%M}Z, k/p={ready}, {args.seconds}s)")
    for f, dt, ready in deferred:
        print(f"[{now:%H:%M}Z] waiting on markets for {f['team1']} vs {f['team2']} "
              f"(T{dt/60:+.0f}m, k/p={ready}); retry next tick")
    if not launched_now and not deferred:
        nxt = next((f for f in fixtures if f["key"] not in state and f["kickoff"] > now), None)
        if nxt:
            mins = (nxt["kickoff"] - now).total_seconds() / 60
            print(f"[{now:%H:%M}Z] no match in window; next: {nxt['team1']} vs "
                  f"{nxt['team2']} in {mins:.0f} min")
        else:
            print(f"[{now:%H:%M}Z] no upcoming uncaptured fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
