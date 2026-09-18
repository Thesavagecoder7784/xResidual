#!/usr/bin/env python3
"""Do the public surfaces still agree with the artifacts they came from -- and stay corrected?

Two jobs.

1. AGREEMENT. For each headline figure it holds the canonical value (read from an artifact or
   computed by the grader, never hard-coded) and flags any live surface that states a DIFFERENT
   value for the same quantity. A check whose pattern matches nothing fails too: a pattern that
   matches nothing looks exactly like one that matches and agrees.
2. THE CORRECTION HOLDS. On 2026-09-18 the cross-venue lead-lag finding was withdrawn
   (CORRECTION.md). Its figures may still appear on a live surface, but only while being withdrawn;
   stated as fact anywhere, they fail the check. So does "the market beats my model", which the
   model-vs-market comparison does not support.

    python scripts/check_claims.py           # report
    python scripts/check_claims.py -v        # show every match, not just failures

Exit 1 if any surface disagrees with its artifact, so it can gate a commit or CI run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Surfaces that carry headline claims in prose: the live, public ones. The withdrawn cross-venue
# material in archive/ is deliberately NOT scanned -- it is a frozen record of what was claimed, and
# the guard below exists to keep its figures from reappearing here. The manuscript (paper/arxiv/) is
# private and predates the 2026-09-18 correction; it is out of scope until it is rewritten.
SURFACES = [
    "README.md", "FINDINGS.md", "METHODOLOGY.md", "REPRODUCING.md", "CORRECTION.md",
    "PREREGISTRATION-ADDENDUM.md", "writeups/retrospective.md",
    "docs/index.html", "docs/method.html", "docs/results.html",
]

# A withdrawn figure may still be QUOTED on a live surface, but only in the act of withdrawing it.
# A mention counts as correction context when one of these words sits within CONTEXT_CHARS of it.
CONTEXT_CHARS = 300
WITHDRAWN_CONTEXT = (r"withdrawn|artifact|no lead|placebo|previously|reproduces|reported that|"
                     r"originally|correction|revised|regraded|did not survive|was the sampling|"
                     r"once a second|one message a second|In July|until 2026-09-18|moved from|"
                     r"PASS to INCONCLUSIVE|6 · 2 · 3|6 / 2 / 3|became inconclusive|lead of (?:exactly )?zero|"
                     r"zero-lead|known-truth|true lead|one-per-second")


def _j(path: str):
    with open(os.path.join(ROOT, path)) as fh:
        return json.load(fh)


def _tally() -> str:
    """The live pre-registration grade, computed by the grader itself -- never typed here."""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import grade_prereg as gp  # noqa: E402
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        rows = [g() for g in gp.GRADERS]
    count = lambda v: sum(1 for r in rows if r["verdict"] == v)
    return f"{count(gp.PASS)},{count(gp.FAIL)},{count(gp.INC)}"


def _digits(x: str) -> str:
    return ",".join(re.findall(r"\d+", x))


def canonical() -> list[dict]:
    """Every headline figure, its true value from the artifact, and how it may be written."""
    cal = _j("writeups/_calibration_results.json")["versions"]
    mkt, v1 = cal["market"], cal["v1"]
    harv = _j("writeups/_harvest_results.json")["pooled"]
    unit = _j("writeups/_harvest_unit_check.json")
    loop = _j("writeups/_loop_window_results.json")
    dec = _j("writeups/_lead_deconvolution_results.json")["masses"]
    sb = _j("writeups/_sampling_bias_results.json")
    zero = next(r for r in sb["lead_lag_placebo"]
                if r["grid"] == "kalshi_ticker_timestamps" and r["true_lag_ms"] == 0)
    mb, vb = f"{mkt['brier']:.3f}", f"{v1['brier']:.3f}"
    against = r"\s*(?:vs\.?|against)\s*(?:my\s*(?:own\s*)?(?:model'?s?\s*)?)?"
    return [
        # The pre-registration grade. Historical tallies (6/2/3) are legitimate only where the text is
        # explaining the regrade, which the context rule allows.
        dict(name="pre-registration tally", value=_tally(), norm=_digits, unit="",
             pattern=r"(\d\s*(?:pass|PASS)[^0-9]{0,8}\d\s*(?:fail|FAIL)[^0-9]{0,8}\d\s*(?:inconclusive|INCONCL))",
             historical_ok=True),
        dict(name="market Brier", value=mb, unit="",
             pattern=rf"(0\.\d{{3}}){against}{vb}"),
        dict(name="model Brier (v1)", value=vb, unit="",
             pattern=rf"{mb}{against}(0\.\d{{3}})"),
        dict(name="market calibration slope", value=f"{mkt['slope']:.2f}", unit="",
             pattern=r"slope\s*(?:of\s*)?\**(\d\.\d{2})\**\s*(?:against|vs)"),
        dict(name="model calibration slope", value=f"{v1['slope']:.2f}", unit="",
             pattern=r"slope\s*(?:of\s*)?\**\d\.\d{2}\**" + against + r"(\d\.\d{2})"),
        dict(name="de-vigged gap while books normalize", value=f"{loop['raw_gap_pp_median']:.2f}", unit="pp",
             pattern=r"(0\.\d{2})\s*(?:pp|points?)\b[^.]{0,80}?(?:both books|normali[sz])"),
        dict(name="Kalshi overround", value=f"{loop['overround_kalshi_pct_median']:.1f}", unit="%",
             pattern=r"overround[^.]{0,40}?(\d\.\d)%\s*(?:on Kalshi\s*)?(?:against|vs)"),
        dict(name="Polymarket overround", value=f"{loop['overround_poly_pct_median']:.1f}", unit="%",
             pattern=r"overround[^.]{0,40}?\d\.\d%\s*(?:on Kalshi\s*)?(?:against|vs\.?)\s*(\d\.\d)%"),
        dict(name="harvest gross move", value=f"{harv['gross_med_c']:.1f}", unit="c",
             pattern=r"median\s*(?:gross\s*)?\**(\d{2}\.\d)\**\s*(?:-?\s*cents?|¢)"),
        # 1-2 digits, and both word orders, for the reasons recorded in git history of this file.
        dict(name="goal-weighted harvestable", value=str(round(unit["pct_harvestable_goal_weighted"])), unit="%",
             pattern=r"(?:~?(\d{1,2})(?:\.\d)?%\s*goal-weighted"
                     r"|goal-weighted[^.]{0,40}?(?:is|:)\s*(?:\*{1,2}|<b>)?\s*~?(\d{1,2})(?:\.\d)?%)"),
        dict(name="deconvolved Kalshi-first", value=str(round(dec["kalshi"] * 100)), unit="%",
             pattern=r"(\d{2})%\s*(?:of goals\s*)?Kalshi[- ]first"),
        dict(name="deconvolved no lead", value=str(round(dec["none"] * 100)), unit="%",
             pattern=r"(\d{2})%\s*(?:no lead|neither)"),
        dict(name="deconvolved Polymarket-first", value=str(round(dec["poly"] * 100)), unit="%",
             pattern=r"(\d{2})%\s*Polymarket[- ]first"),
        dict(name="zero-lead placebo", value=f"{zero['poly_first']} of {zero['n_gated']}", unit="",
             pattern=r"(\d{2}\s*of\s*\d{2})\s*windows"),
    ]


# Phrasings that must not appear on a live surface. Each may carry an `unless` context: the phrase is
# then allowed only where that context sits within CONTEXT_CHARS -- i.e. while it is being withdrawn.
BANNED = [
    # The withdrawn cross-venue finding, stated as fact.
    (r"\+?600\s?ms", "the withdrawn +600 ms cross-venue lead (CORRECTION.md)", WITHDRAWN_CONTEXT),
    (r"81(?:\.0)?%\s*(?:Gonzalo|information|info|component|Polymarket)",
     "the withdrawn 81% information share (CORRECTION.md)", WITHDRAWN_CONTEXT),
    (r"Polymarket (?:leads|discovers|moves first|reprices (?:a )?goals? (?:first|before))",
     "the withdrawn claim that Polymarket leads (CORRECTION.md)", WITHDRAWN_CONTEXT),
    (r"(?:leads?|leading)\s*(?:in\s*)?61 of 63", "the withdrawn 61-of-63 lead (CORRECTION.md)", WITHDRAWN_CONTEXT),
    (r"57 of 66", "the withdrawn per-match lean (CORRECTION.md)", WITHDRAWN_CONTEXT),
    (r"(?:price leader|leading venue)[^.]{0,80}(?:withdraws|empties|vanishes) hardest",
     "the withdrawn depth asymmetry (FINDINGS #38)", WITHDRAWN_CONTEXT),
    # The model-vs-market guardrail: the Brier gap is a point result (paired p = 0.25).
    (r"(?:market|it)\s+(?:beat|beats|out-?predict(?:s|ed)?)\s+(?:my|the)\s+(?:own\s+)?(?:pre-?\w+\s+)?model",
     "'the market beats my model' -- a point result (p = 0.25); claim 'better calibrated' (FINDINGS guardrail)",
     r"\bnot\b|never"),
    (r"405\s+goals",
     "'405 goals' -- build_harvest.py appends one row per CONTRACT per shock, so these are "
     "goal-shock observations (~2 per goal). The whole 104-match tournament produced 308 goals.", None),
    (r"(?<![\d.])(?<!not \")(?<!never as \')0%\s*of\s*goals",
     "'0% of goals' -- the estimator is a median ACROSS MATCHES. Say 'the median match yields no "
     "harvestable goal'.", None),
    (r"5\s*(?:to|-|–)\s*8\s*cent", "the uncited '5 to 8 cent' press figure", None),
    (r"highest scoring rate of the modern era",
     "unqualified scoring superlative -- scope it to the 33-game window it was measured on", r"33 group games"),
]


def banned_hits(body: str) -> list[tuple[int, str]]:
    """(line, reason) for every banned phrasing in `body` that is not being withdrawn in context."""
    hits = []
    for pat, why, unless in BANNED:
        for m in re.finditer(pat, body, re.I):
            near = body[max(0, m.start() - CONTEXT_CHARS): m.end() + CONTEXT_CHARS]
            if unless and re.search(unless, near, re.I):
                continue      # quoted in the act of withdrawing it
            hits.append((body.count("\n", 0, m.start()) + 1, why))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--allow-missing", action="store_true",
                    help="Do not fail when a surface file is absent. For contexts where the "
                         "manuscript is deliberately not present (e.g. the public repo, where "
                         "paper/arxiv is private). Coverage is still reported either way.")
    args = ap.parse_args()

    claims = canonical()
    text = {}
    missing = []
    for s in SURFACES:
        p = os.path.join(ROOT, s)
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace") as fh:
                text[s] = fh.read()
        else:
            # Same principle as the silent-pass guard below: an ABSENT surface is
            # indistinguishable from a surface that agrees, so it must be reported. This
            # checker printed "CLEAN -- every surface agrees" while silently scanning 12 of 15
            # from a fresh clone, which is precisely the reassurance it exists to prevent.
            missing.append(s)

    print("=" * 78)
    print("  CLAIM CONSISTENCY — prose surfaces vs the artifacts they came from")
    print("=" * 78)
    expected = len(SURFACES)
    print(f"  {len(claims)} headline figures · {len(text)} of {expected} surfaces\n")

    if missing:
        print("  MISSING SURFACES — not scanned, so not certified")
        for s in missing:
            print(f"    -- {s}")
        print()

    failures = 0
    for c in claims:
        want = str(c["value"])
        hits, bad = 0, []
        for s, body in text.items():
            for m in re.finditer(c["pattern"], body, re.I):
                # First non-None group: patterns may carry alternatives (the same figure gets
                # written in more than one word order), and only one branch captures per match.
                grp = next((g for g in m.groups() if g is not None), None)
                if grp is None:
                    continue
                got = re.sub(r"\s+", " ", grp).strip()
                hits += 1
                norm = c.get("norm", lambda x: x.replace(" ", ""))
                if norm(got) == norm(want) or got in c.get("allow", set()):
                    continue
                if c.get("historical_ok"):
                    near = body[max(0, m.start() - CONTEXT_CHARS): m.end() + CONTEXT_CHARS]
                    if re.search(WITHDRAWN_CONTEXT, near, re.I):
                        continue      # an old figure quoted while explaining that it changed
                bad.append(f"{s}: says {got}, artifact says {want}")
        if hits == 0:
            # Silent-pass guard. A pattern that matches nothing looks identical to a pattern that
            # matches and agrees, so an unmaintained check would quietly certify a drifting number
            # forever. Treat it as a failure of the checker itself.
            print(f"  ?? {c['name']:36} {want}{c['unit']:4} PATTERN MATCHED NOTHING "
                  f"-- the check is broken, not the claim")
            failures += 1
            continue
        status = "ok " if not bad else "!! "
        if bad or args.verbose:
            print(f"  {status}{c['name']:36} {want}{c['unit']:4} ({hits} mention(s))")
        for b in bad:
            print(f"       {b}")
            failures += 1

    print("\n  BANNED PHRASINGS")
    for s, body in text.items():
        for line, why in banned_hits(body):
            print(f"    !! {s}:{line}: {why}")
            failures += 1

    incomplete = bool(missing) and not args.allow_missing

    print("\n" + "=" * 78)
    if failures:
        print(f"  {failures} DISAGREEMENT(S)")
    elif missing:
        # Never say "every surface" when some were not read. The claim is scoped to coverage.
        label = "PARTIAL" if args.allow_missing else "INCOMPLETE"
        note = ("absent by design here and not certified"
                if args.allow_missing else "not scanned. Coverage is not a pass")
        print(f"  {label} — {len(text)} of {expected} surfaces agree with their artifacts;\n"
              f"  {len(missing)} {note} (listed above).")
    else:
        print(f"  CLEAN — all {expected} surfaces agree with their artifacts")
    print("=" * 78)
    return 1 if (failures or incomplete) else 0


if __name__ == "__main__":
    sys.exit(main())
