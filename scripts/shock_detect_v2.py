#!/usr/bin/env python3
"""Goal-shock detection, v2: strip the settlement artifact, and record what price alone cannot do.

WHY. `xresidual.ws_events.detect_shocks` (v1, frozen) finds sharp, persistent mid moves. It is
labelled a GOAL detector, and `scripts/verify_goals.py` shows it firing more often than there
were goals in 49 of 86 matches, with all 7 goalless matches registering detections
(superseding the original 15-of-29 read, taken when 31 archives survived).

WHAT THE TAPES ACTUALLY SAY. Diagnosed on Belgium-Iran (0-0, 918 MB tape). The phantom events are
NOT noise and NOT smooth clock drift. Their burst concentration is 0.75-1.21, so each is a genuine
step, and v1's persistence filter passes them because they stick. What they are is the favourite's
win probability walking down as the clock runs on a goalless game:

    Belgium (Polymarket) mid: 0.695 at capture start -> 0.001 at capture end
      ... 0.165 (138.5min) -> 0.120 -> 0.095 -> 0.055 -> 0.035 -> 0.001

Prediction markets reprice the clock in discrete steps, and a step of >=5pp inside 60s is exactly
v1's trigger. So these are correct repricings, wrongly labelled goals.

WHAT PRICE ALONE CANNOT DO. Validated against the only match in the surviving archive with a known
goal clock: the Final, whose single goal was Torres at minute 106. That real goal shows up as a
-0.059 move on a contract already sliding toward zero, the same shape and size as the decay steps
above. A cross-contract opposition test does not separate them either, because in a three-outcome
market most of a losing favourite's probability flows into the draw, not into the opponent. An
earlier version of this module dropped shocks by POST value and by terminal run; validated on the
Final, that rule DELETED the real goal. Those guards were removed rather than shipped.

WHAT V2 THEREFORE DOES. One narrow, verified guard: drop moves that START from an already-resolved
price. Kalshi mids degenerate to exactly 0.500 once the book empties at settlement, so a contract
resting at 0.005 "jumps" +0.495 into that empty-book midpoint. That is a book artifact with no
information in it. On both validated tapes this removes 2 events each (~11%) and preserves the
real goal. It is a real fix to a real artifact, and it is not a fix for the labelling problem.

THE ACTUAL FIX, NOT IMPLEMENTED HERE. Anchor events to an exogenous goal clock instead of inferring
them from price. `data/wc_goals.json` already carries minute-level scorers for 9 matches and the
same data is public for all 104. The manuscript (04_methods.tex) concedes this: "a truly exogenous
goal clock would strengthen the design". Until then, prefer the term "repricing shock" over "goal".

SCOPE. Retro-fits nothing. Every published artifact was built with v1 and stands as published; the
lead-lag result gates on cross-venue co-movement and asks which venue moved first given a shared
shock, which does not require the shock to be a goal.

Fork-forward: a NEW scripts/ module. Edits nothing under xresidual/; v1 stays byte-identical.

    python scripts/shock_detect_v2.py <capture-id> [...]   # compare v1 vs v2 on real tapes
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xresidual import ws_events as we   # frozen v1 math, imported never modified

ABSORB_LO, ABSORB_HI = 0.03, 0.97


def terminal_run_start(series: list[tuple[int, float]],
                       lo: float = ABSORB_LO, hi: float = ABSORB_HI) -> int | None:
    """Timestamp at which the contract enters the absorbing run it never leaves, or None.

    NOT used by detect_shocks_v2 any more -- it deleted the Final's real goal. Kept because it is
    the right tool for measuring how long a contract spends resolved, which is a separate question.

    Walk back from the end while the mid stays outside [lo, hi]. If the series does not end
    resolved, there is no terminal run and nothing is suppressed."""
    if not series:
        return None
    if lo <= series[-1][1] <= hi:
        return None                       # still live at the end: no settlement to strip
    start = series[-1][0]
    for t, v in reversed(series):
        if lo <= v <= hi:
            break
        start = t
    return start


def detect_shocks_v2(series: list[tuple[int, float]], lo: float = ABSORB_LO,
                     hi: float = ABSORB_HI, **kw) -> list[dict]:
    """v1 detection, minus moves that begin from an already-resolved contract.

    NARROW BY DESIGN. An earlier, more aggressive version of this also dropped shocks whose
    POST value landed in the absorbing band, and dropped everything after the terminal run.
    Validating against the one match in the archive with a known goal clock (the Final, whose
    only goal was Torres at minute 106) showed that rule deleting the real goal: a genuine late
    goal pushes the losing contract toward zero, which is indistinguishable, by post-value alone,
    from settlement. Both aggressive guards are therefore gone. Only the `pre` guard survives,
    because a move that STARTS from an already-resolved price cannot be news about the match.

    What this catches, concretely: Kalshi mids degenerate to exactly 0.500 once the book empties
    at settlement, so a resolved contract sitting at 0.005 "jumps" +0.495 into that empty-book
    midpoint. That is a book artifact, not a repricing, and it is what the guard removes."""
    raw = we.detect_shocks(series, **kw)
    return [s for s in raw if lo <= s["pre"] <= hi]


def _main(caps: list[str]) -> int:
    import stream_micro as sm
    data = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logger", "data")
    print(f"{'capture':46} {'contract':14} {'v1':>4} {'v2':>4} {'dropped':>8}")
    tot1 = tot2 = 0
    for cap in caps:
        pairs = we.load_pairs(data, capture=cap)
        path = os.path.join(data, f"ws-events-{cap}.jsonl")
        if not pairs or not os.path.exists(path):
            print(f"  {cap}: no pairs/tape, skipped")
            continue
        bundle = sm.stream_all(path, pairs)
        for pr in pairs:
            for venue, book in (("poly", bundle["p_mid"]), ("kalshi", bundle["k_mid"])):
                s = book.get(pr.get(venue) or "", [])
                if len(s) < 20:
                    continue
                a, b = len(we.detect_shocks(s)), len(detect_shocks_v2(s))
                tot1 += a
                tot2 += b
                label = f"{pr.get('label','?')}/{venue}"
                print(f"  {cap[:44]:46} {label:14} {a:4d} {b:4d} {a-b:8d}")
    print(f"\n  TOTAL v1 {tot1} -> v2 {tot2}   ({tot1-tot2} settlement events removed, "
          f"{(tot1-tot2)/tot1*100:.0f}%)" if tot1 else "\n  nothing detected")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]) if len(sys.argv) > 1 else _main([
        "20260621T183221Z-belgium-vs-iran"]))
