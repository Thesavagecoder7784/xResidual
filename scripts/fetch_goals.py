#!/usr/bin/env python3
"""Pull exact goal minutes for finished World Cup matches from football-data.org -> data/wc_goals.json,
the goal source build_livewp.py prefers over shock-inference (shocks get the sequence right but the
minutes too rough for the per-goal fair-value comparison).

    python scripts/fetch_goals.py            # all finished WC matches
    python scripts/fetch_goals.py --force    # re-fetch even matches already cached

Reads FOOTBALL_DATA_KEY from the environment or .env. Free tier is 10 req/min, so it throttles.
Run on the laptop (which holds the key); the resulting JSON is pushed to the VM, so the key never
leaves the laptop. Keyed by "Home vs Away" with football-data's own names; build_livewp canonicalises
names (the bridge) when it reads, so spelling differences (DR Congo, Côte d'Ivoire, ...) don't matter.
"""
from __future__ import annotations

import json
import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "wc_goals.json")
BASE = "https://api.football-data.org/v4"
COMP = "WC"          # FIFA World Cup competition code on football-data.org
THROTTLE_S = 6.5      # free tier: 10 requests / minute


def load_key() -> str | None:
    k = os.environ.get("FOOTBALL_DATA_KEY")
    if k:
        return k.strip()
    envp = os.path.join(ROOT, ".env")
    if os.path.exists(envp):
        for line in open(envp):
            if line.strip().startswith("FOOTBALL_DATA_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def get(path: str, key: str) -> dict:
    r = requests.get(BASE + path, headers={"X-Auth-Token": key}, timeout=30)
    r.raise_for_status()
    return r.json()


def main() -> int:
    force = "--force" in sys.argv
    key = load_key()
    if not key:
        print("no FOOTBALL_DATA_KEY in env or .env"); return 1
    existing = {}
    if os.path.exists(OUT) and not force:
        try:
            existing = json.load(open(OUT))
        except Exception:
            existing = {}

    try:
        matches = get(f"/competitions/{COMP}/matches?status=FINISHED", key).get("matches", [])
    except requests.HTTPError as e:
        print(f"competition matches fetch failed ({e}) — is WC on this key's free tier?"); return 1
    print(f"{len(matches)} finished WC match(es) on the feed")

    out = dict(existing)
    fetched = 0
    for m in matches:
        h, a = m["homeTeam"]["name"], m["awayTeam"]["name"]
        label = f"{h} vs {a}"
        if label in out and not force:
            continue
        try:
            det = get(f"/matches/{m['id']}", key)
        except requests.HTTPError as e:
            print(f"  {label}: detail fetch failed ({e})"); time.sleep(THROTTLE_S); continue
        goals = []
        for g in det.get("goals", []) or []:
            minute = g.get("minute")
            if minute is None:
                continue
            goals.append({"minute": int(minute), "injury": int(g.get("injuryTime") or 0),
                          "team": g["team"]["name"], "scorer": (g.get("scorer") or {}).get("name")})
        if goals:
            out[label] = sorted(goals, key=lambda x: (x["minute"], x["injury"]))
            fetched += 1
            print(f"  {label}: {len(goals)} goals")
        else:
            print(f"  {label}: no goal detail (free-tier restriction?) — left to shock-inference")
        time.sleep(THROTTLE_S)

    json.dump(out, open(OUT, "w"), indent=2)
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(out)} matches ({fetched} newly fetched)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
