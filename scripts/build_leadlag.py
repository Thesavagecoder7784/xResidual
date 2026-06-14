#!/usr/bin/env python3
"""Auto-fire the cross-venue lead-lag flagship on captured websocket data.

    python scripts/build_leadlag.py

No hand-typed goal time, no hand-typed tickers. Reads the ws-events captured by
logger/ws_capture.py, reads the cross-venue pairs that capture recorded
(ws-pairs-*.jsonl), auto-detects price shocks (a goal / red card shows up as a fast
large mid move), and for every shock measures which venue repriced first. Writes:

  - viz/market/_leadlag.js     the cleanest (largest) event, for leadlag_tape.html
  - writeups/_leadlag_results.json   every event + the pooled lead, for the writeup

Safe to run anytime: with no capture yet it prints what's missing and exits 0, so it
can sit at the end of a capture (ws_capture --analyze) or in build_all without failing.
"""
from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import ws_events as we  # noqa: E402

DATA_DIR = os.path.join(ROOT, "logger", "data")
LEADLAG_DIR = os.path.join(ROOT, "viz", "market", "leadlag")  # per-match files, named after the game
RESULTS_OUT = os.path.join(ROOT, "writeups", "_leadlag_results.json")  # pooled aggregate (cumulative)
MIN_JUMP = 0.04  # probability-units move that counts as a shock (~a goal's worth)
# Lead quality gate (post-filter; xresidual/ws_events is v1-frozen). lead_lag_ms picks the lag by
# |corr|, so it can lock onto a spurious ANTI-correlation — a "-16s lead at r=-0.70" is the two
# venues moving oppositely (noise / a stale quote), not price discovery. Keep a lead only if the
# venues genuinely CO-moved (best_corr >= MIN_LEAD_CORR) within a plausible window
# (|lag| <= MAX_LEAD_MS). Rejected shocks still count as detected, but don't pollute the pooled lead.
MIN_LEAD_CORR = 0.5
MAX_LEAD_MS = 8000


def gate_leads(results: list[dict]) -> int:
    """Null out (in place) any event lead that fails the co-movement / plausibility gate, so
    pool_leads ignores it. Annotates the event with lead_rejected. Returns how many were dropped."""
    dropped = 0
    for r in results:
        for e in r.get("events", []):
            ll = e.get("lead")
            if not ll:
                continue
            if ll["best_corr"] < MIN_LEAD_CORR or abs(ll["best_lag_ms"]) > MAX_LEAD_MS:
                e["lead_rejected"] = {
                    "best_lag_ms": ll["best_lag_ms"], "best_corr": round(ll["best_corr"], 2),
                    "why": "weak/anti-corr" if ll["best_corr"] < MIN_LEAD_CORR else "lag>cap"}
                e["lead"] = None
                dropped += 1
    return dropped


def tape_config(label: str, ev: dict) -> dict:
    """leadlag_tape.html CONFIG for one (gated) event of a pair."""
    ll = ev.get("lead") or {}
    rx = ev.get("poly_reaction") or ev.get("kalshi_reaction") or {}
    return {"match": label, "moment": f"shock · Δ{ev['jump']*100:+.0f}¢",
            "market": label,
            "leadSec": round(abs(ll.get("best_lag_ms", 0)) / 1000, 2),
            "leader": (ll.get("leader") or "synchronous").capitalize(),
            "base": rx.get("pre", 0.5), "post": rx.get("settle", 0.5),
            "corr": round(ll.get("best_corr", 0), 3)}


def wc_captures(data_dir: str) -> list[str]:
    """Capture suffixes with a cross-venue pairs file whose Kalshi side is a WC GAME (a
    KXWCGAME ticker), oldest first. That filter keeps real World Cup matches and drops
    warm-up friendlies (e.g. Argentina-Iceland), outright-tests, and unpaired captures."""
    caps = []
    for path in sorted(glob.glob(os.path.join(data_dir, "ws-events-*.jsonl"))):
        suf = os.path.basename(path)[len("ws-events-"):-len(".jsonl")]
        pairs = we.load_pairs(data_dir, capture=suf)
        if pairs and any(str(p.get("kalshi", "")).startswith("KXWCGAME") for p in pairs):
            caps.append(suf)
    return caps


def _match_label(cap: str) -> str:
    slug = cap.split("-", 1)[1] if "-" in cap else cap          # drop the timestamp prefix
    return slug.replace("-vs-", " vs ").replace("-", " ").title().replace(" Vs ", " vs ")


def process_capture(cap: str, events=None, pairs=None) -> str | None:
    """Parse ONE capture's tape, gate the leads, and write its per-game <slug>.js + <slug>.json.
    This is the heavy step (a 1 GB tape parses to several GB of dicts), so it runs ONCE per match,
    then never again — the pooled aggregate is rebuilt from the JSONs, not the tapes. Run on the
    laptop, not the 900 MB collection VM. Returns the match label, or None if the tape is unusable.
    `events`/`pairs` can be passed in (already loaded) so one tape parse can feed several pipelines."""
    BEFORE_S, AFTER_S, BIN_MS = 10, 20, 200       # match auto_lead_lag defaults
    if events is None:
        events = we.load_ws_events(DATA_DIR, capture=cap)
    if pairs is None:
        pairs = we.load_pairs(DATA_DIR, capture=cap)
    if not events or not pairs:
        return None
    results = we.auto_lead_lag(events, pairs, min_jump=MIN_JUMP)
    dropped = gate_leads(results)
    match = _match_label(cap)
    slug = cap.split("-", 1)[1] if "-" in cap else cap     # game slug -> filename
    for r in results:
        r["match"] = match
        r.pop("tape", None)               # rebuilt on demand via event_window; keep JSON lean
    # <slug>.js = the cleanest gated event's tape card; <slug>.json = the match's analysis
    mbest = None
    for r in results:
        for e in r["events"]:
            if e.get("lead") and (mbest is None or e["jump"] > mbest[1]["jump"]):
                mbest = (r, e)
    if mbest:
        r, e = mbest
        tape = we.event_window(events, r["kalshi"], r["poly"], e["t_ms"], BEFORE_S, AFTER_S, BIN_MS)
        cfg = tape_config(r["label"], e)
        cfg["match"] = match              # dek title -> the full matchup, not just the team/market
        with open(os.path.join(LEADLAG_DIR, slug + ".js"), "w", encoding="utf-8") as f:
            f.write("window.LEADLAG = " + json.dumps(
                {"config": cfg, "match": match,
                 "data": {"poly": tape["poly"], "kalshi": tape["kalshi"]}}) + ";\n")
    mpooled = we.pool_leads(results)
    with open(os.path.join(LEADLAG_DIR, slug + ".json"), "w", encoding="utf-8") as f:
        json.dump({"match": match, "capture": cap, "pooled": mpooled,
                   "pairs": results, "min_jump": MIN_JUMP}, f, indent=2)
    n_leads = sum(1 for r in results for e in r["events"] if e.get("lead"))
    n_shocks = sum(r["n_events"] for r in results)
    tag = (f"{mpooled['leader']} {mpooled['median_lead_ms']:+.0f}ms" if mpooled else "no clean lead")
    print(f"  processed {match:<24} {len(events):>10,} ev · {n_shocks:>2} shocks · {n_leads:>2} leads"
          + (f" · dropped {dropped}" if dropped else "") + f"  -> {slug}.{{js,json}} ({tag})")
    del events
    return match


def pool_from_archive() -> dict | None:
    """Rebuild the pooled aggregate from EVERY per-game JSON in the archive. Parses no tapes, so it
    is instant and scales: each match is processed once into its JSON; pooling just reads the JSONs.
    The tapes are transient (delete after processing); the per-game JSONs are the source of truth."""
    all_results, matches = [], []
    for path in sorted(glob.glob(os.path.join(LEADLAG_DIR, "*.json"))):
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict) or "pairs" not in d:
            continue
        matches.append(d.get("match", os.path.basename(path)[:-5]))
        all_results.extend(d["pairs"])
    pooled = we.pool_leads(all_results)
    os.makedirs(os.path.dirname(RESULTS_OUT), exist_ok=True)
    with open(RESULTS_OUT, "w", encoding="utf-8") as f:
        json.dump({"pairs": all_results, "pooled": pooled,
                   "n_matches": len(matches), "min_jump": MIN_JUMP}, f, indent=2)
    if pooled:
        lo, hi = pooled["iqr_ms"]
        print(f"POOLED · n={pooled['n']} across {len(matches)} matches · {pooled['leader']} leads "
              f"(median {pooled['median_lead_ms']:+.0f}ms, IQR [{lo:+.0f},{hi:+.0f}]) · "
              f"leader share {pooled['leader_share']:.0%}")
    else:
        print(f"POOLED · no clean cross-venue leads across {len(matches)} match(es) yet")
    print(f"wrote {os.path.relpath(RESULTS_OUT, ROOT)} (pooled from {len(matches)} per-game JSON(s))")
    return pooled


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="incremental cross-venue lead-lag: process NEW tapes, "
                                             "then pool from the per-game JSON archive")
    ap.add_argument("--all", action="store_true",
                    help="re-process every WC tape present, not just the new ones")
    ap.add_argument("--pool-only", action="store_true",
                    help="rebuild the pooled aggregate from the per-game JSONs; parse no tapes")
    args = ap.parse_args()
    os.makedirs(LEADLAG_DIR, exist_ok=True)
    if args.pool_only:
        pool_from_archive()
        return 0
    caps = wc_captures(DATA_DIR)
    done = lambda c: os.path.exists(os.path.join(
        LEADLAG_DIR, (c.split("-", 1)[1] if "-" in c else c) + ".json"))
    todo = caps if args.all else [c for c in caps if not done(c)]
    if todo:
        print(f"processing {len(todo)} new tape(s) of {len(caps)} present; the rest already archived:")
        for cap in todo:
            process_capture(cap)
    else:
        print(f"no new tapes to process ({len(caps)} present, all archived); re-pooling.")
    pool_from_archive()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
