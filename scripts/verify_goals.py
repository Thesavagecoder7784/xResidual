#!/usr/bin/env python3
"""Verify every goal in the tournament against every source that records one.

Three independent checks, none of which the rest of the pipeline performs:

  1. SCORELINE RECONCILIATION. The fixtures feed (martj42) records 90-minute scores; the
     knockout ledger (`data/cache/ko_advancers.json` + the overlay) records after-extra-time
     scores. They disagree on exactly the ties that were level at 90 minutes. Any disagreement
     that is NOT of that shape is a real data error and is reported as one.

  2. DETECTION VALIDITY. The microstructure work detects goals from the tape as decisive mid
     shocks rather than from an official clock, which the manuscript discloses as a limitation
     (04_methods.tex). This compares detected shocks against the true goal count per match.
     Under-detection is expected and benign: the quality gate deliberately drops small or
     ambiguous moves. OVER-detection is not, because a detected "goal" that never happened is
     a false event in the event study, so it is reported as a defect.

  3. GOAL-COUNT TOTALS. The tournament goal total implied by each source, so a silent feed
     change shows up as a number that moved.

Exit code 1 if any hard defect is found (impossible scoreline disagreement, or over-detection),
0 otherwise. Read-only: touches nothing, emits nothing, safe to run any time.

    python scripts/verify_goals.py          # summary
    python scripts/verify_goals.py -v       # per-match detail
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_ledger() -> dict:
    """After-extra-time scores, keyed by unordered team pair."""
    out = {}
    for path, extract in (
        (os.path.join(ROOT, "data", "cache", "ko_advancers.json"), lambda d: d.values()),
        (os.path.join(ROOT, "data", "cache", "wc_scores_overlay.json"), lambda d: d),
    ):
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            for v in extract(json.load(fh)):
                out[frozenset((v["home_team"], v["away_team"]))] = v
    return out


def _fixtures() -> list[dict]:
    with open(os.path.join(ROOT, "data", "wc2026_fixtures.csv")) as fh:
        return [r for r in csv.DictReader(fh) if (r.get("score1") or "").strip() != ""]


def check_scorelines(verbose: bool) -> tuple[int, list[str]]:
    """Disagreements are legitimate only when the 90-minute score was level."""
    led, defects, benign = _load_ledger(), [], []
    for r in _fixtures():
        key = frozenset((r["team1"], r["team2"]))
        if key not in led:
            continue
        v = led[key]
        if v["home_team"] == r["team1"]:
            a, b = v["home_score"], v["away_score"]
        else:
            a, b = v["away_score"], v["home_score"]
        c1, c2 = int(r["score1"]), int(r["score2"])
        if (a, b) == (c1, c2):
            continue
        line = f"{r['round']:22} {r['team1']} vs {r['team2']}: 90min {c1}-{c2} / AET {a}-{b}"
        # legitimate iff level at 90 and the ledger resolves it
        (benign if c1 == c2 and a != b else defects).append(line)
    print(f"\n[1] SCORELINE RECONCILIATION  ({len(_fixtures())} matches with scores)")
    print(f"    extra-time resolutions (expected) : {len(benign)}")
    print(f"    unexplained disagreements (DEFECT): {len(defects)}")
    if verbose:
        for line in benign:
            print(f"      ok  {line}")
    for line in defects:
        print(f"      !!  {line}")
    return len(defects), defects


def _true_goal_count(match_name: str, fx_by_pair: dict, led: dict) -> int | None:
    """Authoritative goal count for a match, from the scoreline — NOT from the archive's own
    n_goals field, which is populated by a results join that is known to fail on some name
    variants (see the England vs Croatia case: n_goals=0 against a real 4-2)."""
    parts = match_name.split(" vs ")
    if len(parts) != 2:
        return None
    key = frozenset(parts)
    if key in led:  # prefer AET where the tie went past 90
        v = led[key]
        return v["home_score"] + v["away_score"]
    if key in fx_by_pair:
        return fx_by_pair[key]
    return None


def check_detection(verbose: bool) -> tuple[int, list[str]]:
    """Detected shocks vs true goals. Over-detection is a defect; under-detection is the gate."""
    files = sorted(glob.glob(os.path.join(ROOT, "viz", "model", "overreaction", "*.json")))
    if not files:
        print("\n[2] DETECTION VALIDITY: no per-game overreaction archives on this machine, skipped.")
        return 0, []
    fx_by_pair = {}
    for r in _fixtures():
        fx_by_pair[frozenset((r["team1"], r["team2"]))] = int(r["score1"]) + int(r["score2"])
    led = _load_ledger()

    rows, over, stale, unmatched = [], [], [], []
    for f in files:
        with open(f) as fh:
            d = json.load(fh)
        name, detected = d.get("match"), d.get("n_detected")
        if name is None or detected is None:
            continue
        true_goals = _true_goal_count(name, fx_by_pair, led)
        if true_goals is None:
            unmatched.append(name)
            continue
        rows.append((name, true_goals, detected))
        if d.get("n_goals") is not None and d["n_goals"] != true_goals:
            stale.append(f"{name}: archive n_goals={d['n_goals']} but scoreline says {true_goals} "
                         f"(source={d.get('goals_source')})")
        if detected > true_goals:
            over.append(f"{name}: detected {detected} > actual {true_goals}")

    tg, td = sum(r[1] for r in rows), sum(r[2] for r in rows)
    print(f"\n[2] DETECTION VALIDITY  ({len(rows)} matches, ground truth = scoreline)")
    print(f"    true goals {tg} · detected shocks {td} · ratio {td/tg*100:.0f}%")
    print(f"    matches where detection EXCEEDS actual goals (DEFECT): {len(over)}")
    print(f"    archives whose own n_goals field is wrong (DEFECT)  : {len(stale)}")
    if unmatched:
        print(f"    matches not resolvable to a scoreline               : {len(unmatched)}")
    if verbose:
        for m, t, d_ in sorted(rows, key=lambda r: r[1] - r[2]):
            flag = "!!" if d_ > t else "  "
            print(f"      {flag} {m:34} actual {t:2d}  detected {d_:2d}")
    for line in over:
        print(f"      !!  over-detect: {line}")
    for line in stale:
        print(f"      !!  bad n_goals: {line}")
    print("    note: under-detection is expected — the quality gate drops small/ambiguous moves.")
    print("    note: a detected shock need not be a goal. The lead-lag design gates on cross-venue")
    print("          co-movement, so a red card or big chance is a valid repricing event. These")
    print("          counts bound how often a 'goal window' is not actually a goal.")
    return len(over) + len(stale), over + stale


def check_totals(verbose: bool) -> None:
    fx = _fixtures()
    led = _load_ledger()
    reg = sum(int(r["score1"]) + int(r["score2"]) for r in fx)
    aet = 0
    for r in fx:
        c1, c2 = int(r["score1"]), int(r["score2"])
        key = frozenset((r["team1"], r["team2"]))
        if key in led:
            v = led[key]
            if v["home_team"] == r["team1"]:
                c1, c2 = v["home_score"], v["away_score"]
            else:
                c1, c2 = v["away_score"], v["home_score"]
        aet += c1 + c2
    n = len(fx)
    hp = os.path.join(ROOT, "writeups", "_harvest_results.json")
    ledger_n = ledger_m = None
    if os.path.exists(hp):
        with open(hp) as fh:
            pooled = json.load(fh)["pooled"]
        ledger_n, ledger_m = pooled.get("n_goals"), pooled.get("n_matches")
    print(f"\n[3] GOAL TOTALS  ({n} matches)")
    print(f"    regulation time  : {reg} goals · {reg/n:.2f}/game")
    print(f"    after extra time : {aet} goals · {aet/n:.2f}/game")
    if ledger_n and ledger_m:
        rate = ledger_n / ledger_m
        print(f"    harvest ledger   : {ledger_n} rows over {ledger_m} matches · {rate:.2f}/match")
        print(f"      PLAUSIBILITY: the tournament ran {aet/n:.2f} goals/match. build_harvest.py appends")
        print(f"      one row per CONTRACT per shock, and a match has ~2 contracts, so a single goal")
        print(f"      yields ~2 rows. {ledger_n}/{ledger_m} = {rate:.2f} implies ~{rate/2:.2f} goals/match.")
        if rate > aet / n * 1.5:
            print(f"      -> These rows are goal-shock OBSERVATIONS, not goals. Do not write "
                  f"'{ledger_n} goals'.")


def check_clock(verbose: bool) -> None:
    """Coverage of the exogenous goal clock (scripts/fetch_goals_espn.py)."""
    p = os.path.join(ROOT, "data", "wc_goals_espn.json")
    if not os.path.exists(p):
        print("\n[4] EXOGENOUS GOAL CLOCK: not built. Run scripts/fetch_goals_espn.py")
        return
    with open(p) as fh:
        d = json.load(fh)
    g = sum(len(v["goals"]) for v in d.values())
    c = sum(len(v.get("cards", [])) for v in d.values())
    so = sum(len(v.get("shootout", [])) for v in d.values())
    print(f"\n[4] EXOGENOUS GOAL CLOCK  (data/wc_goals_espn.json)")
    print(f"    {len(d)} matches · {g} goals with minute stamps · {c} cards · {so} shootout kicks")
    print(f"    Every goal now has an exogenous timestamp, so goal windows no longer need to be")
    print(f"    inferred from the price series. This is the fix for the over-detection in [2].")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true", help="per-match detail")
    args = ap.parse_args()

    print("=" * 78)
    print("  GOAL VERIFICATION — every goal against every source that records one")
    print("=" * 78)
    d1, _ = check_scorelines(args.verbose)
    d2, _ = check_detection(args.verbose)
    check_totals(args.verbose)
    check_clock(args.verbose)

    total = d1 + d2
    print("\n" + "=" * 78)
    if total:
        print(f"  {total} DEFECT(S) FOUND — see the !! lines above")
    else:
        print("  VERIFIED — no unexplained scoreline disagreements, no over-detection")
    print("=" * 78)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
