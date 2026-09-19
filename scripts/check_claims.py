#!/usr/bin/env python3
"""Do the public surfaces still agree with the artifacts they came from -- and stay corrected?

Two jobs.

1. AGREEMENT. For each headline figure it holds the canonical value (read from an artifact or
   computed by the grader, never hard-coded) and flags any live surface that states a DIFFERENT
   value for the same quantity. Paired figures ("0.487 vs 0.503") are checked as pairs, so both
   halves drifting together cannot slip through. A check whose pattern matches nothing fails too: a
   pattern that matches nothing looks exactly like one that matches and agrees.
2. THE CORRECTION HOLDS. On 2026-09-18 the cross-venue lead-lag finding was withdrawn
   (CORRECTION.md). Its figures may still appear on a live surface, but only in a sentence that is
   itself withdrawing them; stated as fact anywhere, they fail the check. So does "the market beats
   my model", which the model-vs-market comparison does not support.

Everything is judged one sentence at a time. An earlier version exempted any mention within 300
characters of a generic word like "correction" or "reproduces", which covered most of the README and
let "The true lead is +600 ms" through. HTML surfaces are reduced to their visible text first.

    python scripts/check_claims.py           # report
    python scripts/check_claims.py -v        # show every match, not just failures

Exit 1 if any surface disagrees with its artifact, so it can gate a commit or CI run.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Live, public surfaces that carry headline claims. The withdrawn material in archive/ and the two
# archived site pages (docs/note.html, docs/lab.html) are deliberately NOT scanned: they are a frozen
# record behind a correction banner, which tests/test_correction_guard.py checks is still there. The
# manuscript (paper/arxiv/) is private and predates the correction.
SURFACES = [
    "README.md", "FINDINGS.md", "METHODOLOGY.md", "REPRODUCING.md", "CORRECTION.md",
    "PREREGISTRATION-ADDENDUM.md", "writeups/retrospective.md", "writeups/recovery-audit.md",
    "viz/README.md", "docs/index.html", "docs/method.html", "docs/results.html",
]

# A sentence may quote a withdrawn figure only if it is withdrawing it. These markers are deliberately
# narrow: each one says, on its own, that the figure is being retracted or explained as an artifact.
WITHDRAWAL = re.compile(
    r"\bwithdrawn\b|\bwithdraw(?:ing)?\s+(?:it|this|that|the)\b|sampling artifact|\ban artifact\b|"
    r"\bartifact of\b|no lead at all|market (?:in which|with) no lead|with no lead\b|zero-lead|"
    r"lead of (?:exactly )?zero|known-truth|\bpreviously\b|\boriginally\b|until (?:this date|2026-09-18)|"
    r"earlier version|reported that|claimed that|was produced by|did not survive|cannot distinguish|"
    r"not \"?Polymarket leads|In July this section|was the sampling|withdrawal|neither venue leads", re.I)

# A superseded tally may appear only in a sentence explaining that the grade changed.
TALLY_HISTORY = re.compile(
    r"until 2026-09-18|mov(?:ed|es) from|regraded|revised|19 July|July 19|became inconclusive|"
    r"not 6|original(?:ly)? graded|before the regrade", re.I)

# "The market beats my model" may appear only in a sentence that denies it.
DENIES_BEAT = re.compile(r"\bnot (?:that )?(?:it |the market )?beat|\bnever\b[^.]{0,20}\bbeat", re.I)

_WORDNUM = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7"}


def visible_text(path: str, raw: str) -> str:
    """HTML reduced to what a reader sees: no scripts, styles or tags, entities decoded."""
    if not path.endswith(".html"):
        return raw
    raw = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<[^>]+>", "", raw)
    return html.unescape(raw)


def sentences(text: str):
    """(line, sentence) pairs. Blocks split on blank lines and list/table/quote markers, then at a
    sentence end: [.!?] followed by whitespace and a capital or digit. Decimals ("0.487") and common
    abbreviations ("vs.", "e.g.") are not sentence ends. Line is where the sentence starts."""
    text = re.sub(r"(?m)^[ \t]*>[ \t]?", "", text)      # blockquotes read as ordinary prose
    out = []
    pos = 0
    end = re.compile(r"(?<!\bvs\.)(?<!e\.g\.)(?<!i\.e\.)(?<!\bcf\.)(?<!\bp\.)(?<=[.!?])\s+(?=[\"'*(\[_]*[A-Z0-9])")
    for block in re.split(r"(\n\s*\n|\n(?=\s*(?:[-*|]|\d+\.)\s))", text):
        if block and block.strip():
            i = 0
            for m in end.finditer(block):
                seg = re.sub(r"\s+", " ", block[i:m.start()]).strip()
                if seg:
                    out.append((text.count("\n", 0, pos + i) + 1, seg))
                i = m.end()
            seg = re.sub(r"\s+", " ", block[i:]).strip()
            if seg:
                out.append((text.count("\n", 0, pos + i) + 1, seg))
        pos += len(block)
    return out


def _j(path: str):
    with open(os.path.join(ROOT, path)) as fh:
        return json.load(fh)


def _tally() -> str:
    """The live pre-registration grade, computed by the grader itself -- never typed here."""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import contextlib
    import io
    import grade_prereg as gp  # noqa: E402
    with contextlib.redirect_stdout(io.StringIO()):
        rows = [g() for g in gp.GRADERS]
    count = lambda v: sum(1 for r in rows if r["verdict"] == v)
    return f"{count(gp.PASS)},{count(gp.FAIL)},{count(gp.INC)}"


def _norm(groups) -> str:
    vals = [_WORDNUM.get(g.lower(), g) for g in groups if g is not None]
    return ",".join(re.sub(r"[\s*]+", "", v) for v in vals)


def canonical() -> list[dict]:
    """Every headline figure: its true value from the artifact, how it may be written, and (for
    patterns that could match unrelated text) what the sentence must also contain."""
    cal = _j("writeups/_calibration_results.json")["versions"]
    mkt, v1 = cal["market"], cal["v1"]
    harv = _j("writeups/_harvest_results.json")["pooled"]
    unit = _j("writeups/_harvest_unit_check.json")
    loop = _j("writeups/_loop_window_results.json")
    dec = _j("writeups/_lead_deconvolution_results.json")["masses"]
    sb = _j("writeups/_sampling_bias_results.json")
    zero = next(r for r in sb["lead_lag_placebo"]
                if r["grid"] == "kalshi_ticker_timestamps" and r["true_lag_ms"] == 0)
    num = r"\**(\d\.\d{2,3})\**"
    vs = r"\s*(?:vs\.?|against)\s*(?:my\s*(?:own\s*)?(?:model'?s?\s*)?)?"
    return [
        dict(name="pre-registration tally", value=_tally(), history=TALLY_HISTORY,
             patterns=[
                 r"\b(\d{1,2})\s*(?:pass(?:es|ed)?|PASS)\b[^0-9]{0,14}?(\d{1,2})\s*(?:fail(?:s|ed)?|FAIL)\b"
                 r"[^0-9]{0,16}?(\d{1,2})\s*(?:inconclusive|INCONCL)",
                 r"\b(\d)\s*/\s*(\d)\s*/\s*(\d)\s*(?:pre-reg|graded)",
                 r"\bPASS\s*(\d{1,2})\W{0,4}FAIL\s*(\d{1,2})\W{0,4}INCONCL\w*\s*(\d{1,2})",
                 r"\b(one|two|three|four|five|six|seven)\s+pass(?:ed)?,\s*(one|two|three|four)\s+fail(?:ed)?,"
                 r"\s*and\s+(one|two|three|four|five)\s+(?:are\s+)?inconclusive"]),
        dict(name="Brier, market vs model", value=f"{mkt['brier']:.3f},{v1['brier']:.3f}",
             patterns=[r"(0\.\d{3})" + vs + r"(0\.\d{3})"], must=r"Brier", mustnot=r"log-loss|outcome"),
        dict(name="calibration slope, market vs model", value=f"{mkt['slope']:.2f},{v1['slope']:.2f}",
             patterns=[r"slope\s*(?:of\s*)?" + num + vs + num]),
        dict(name="de-vigged gap while books normalize", value=f"{loop['raw_gap_pp_median']:.2f}",
             patterns=[r"(0\.\d{2})\s*(?:pp|points?)\b"], must=r"normali[sz]"),
        dict(name="overround, Kalshi vs Polymarket",
             value=f"{loop['overround_kalshi_pct_median']:.1f},{loop['overround_poly_pct_median']:.1f}",
             patterns=[r"(\d\.\d)%\s*(?:on Kalshi\s*)?(?:against|vs\.?)\s*(?:Polymarket'?s?\s*)?(\d\.\d)%"],
             must=r"overround"),
        dict(name="harvest: the goal-sized move", value=f"{harv['gross_med_c']:.1f}",
             patterns=[r"median\s*(?:gross\s*)?\**(\d{2}\.\d)\**\s*(?:-?\s*cents?|¢|c\b)"]),
        dict(name="goal-weighted harvestable", value=str(round(unit["pct_harvestable_goal_weighted"])),
             patterns=[r"~?(\d{1,2})(?:\.\d)?%\s*goal-weighted",
                       r"goal-weighted[^.]{0,40}?(?:is|:)\s*~?(\d{1,2})(?:\.\d)?%",
                       r"About\s*(\d{1,2})% of goals"]),
        dict(name="deconvolved split (Kalshi / none / Polymarket)",
             value=f"{round(dec['kalshi'] * 100)},{round(dec['none'] * 100)},{round(dec['poly'] * 100)}",
             patterns=[r"(\d{1,2})%\s*(?:of goals\s*)?Kalshi[- ]first,?\s*(\d{1,2})%\s*(?:no lead|neither),?"
                       r"\s*(?:and\s*)?(\d{1,2})%\s*Polymarket[- ]first"]),
        dict(name="zero-lead placebo", value=f"{zero['poly_first']} of {zero['n_gated']}",
             patterns=[r"(\d{2}\s*of\s*\d{2})\s*(?:gated\s*)?windows"], must=r"Polymarket"),
    ]


# Phrasings that must not appear on a live surface. `exempt`, if given, is the sentence-level marker
# under which the phrase is allowed (i.e. while it is being withdrawn or denied).
BANNED = [
    (r"\+?600\s?(?:ms|milliseconds)\b", "the withdrawn +600 ms cross-venue lead (CORRECTION.md)", WITHDRAWAL),
    (r"\b8[01](?:\.\d)?\s*(?:%|percent)\s*(?:Gonzalo|information|info|component|of price discovery|Polymarket)",
     "the withdrawn 81% information share (CORRECTION.md)", WITHDRAWAL),
    (r"(?:information|info)[- ]share[^.]{0,40}?\b8[01](?:\.\d)?\s*(?:%|percent)",
     "the withdrawn 81% information share (CORRECTION.md)", WITHDRAWAL),
    (r"Polymarket(?:'s price)?\s+(?:leads|led|leading|discovers|discovered|moves first|moved first|"
     r"(?:re)?prices (?:a |the )?goals? (?:first|before))",
     "the withdrawn claim that Polymarket leads (CORRECTION.md)", WITHDRAWAL),
    (r"\b61\s*(?:of|/)\s*63\b", "the withdrawn 61-of-63 lead (CORRECTION.md)", WITHDRAWAL),
    (r"\b57\s*(?:of|/)\s*66\b", "the withdrawn per-match lean (CORRECTION.md)", WITHDRAWAL),
    (r"(?:price leader|leading venue|venue that leads)[^.]{0,80}(?:withdraws|empties|vanishes|collapses) (?:the )?hardest",
     "the withdrawn depth asymmetry (FINDINGS #38)", WITHDRAWAL),
    (r"\b(?:markets?|it)\s+(?:beat|beats|outperform(?:s|ed)?|out-?predict(?:s|ed)?|was better than)\s+"
     r"(?:my|the)\s+(?:own\s+)?(?:pre-?\w+\s+|v\d\s+)?model",
     "'the market beats my model' -- a point result (p = 0.25); claim 'better calibrated' (FINDINGS guardrail)",
     DENIES_BEAT),
    (r"405\s+goals\b",
     "'405 goals' -- the ledger has one row per CONTRACT per shock, so these are goal-shock observations "
     "(~2 per goal). The whole 104-match tournament produced 308 goals.", None),
    (r"(?<![\d.])0%\s*of\s*goals",
     "'0% of goals' -- the estimator is a median ACROSS MATCHES. Say 'the median match yields no "
     "harvestable goal'.", re.compile(r"not \"|never as", re.I)),
    (r"5\s*(?:to|-|–)\s*8\s*cent", "the uncited '5 to 8 cent' press figure", None),
    (r"highest scoring rate of the modern era",
     "unqualified scoring superlative -- scope it to the 33-game window it was measured on",
     re.compile(r"33 group games", re.I)),
]


def banned_hits(body: str, path: str = "x.md") -> list[tuple[int, str]]:
    """(line, reason) for every banned phrasing in `body` stated outside a sentence that withdraws it."""
    hits = []
    for line, sent in sentences(visible_text(path, body)):
        for pat, why, exempt in BANNED:
            if re.search(pat, sent, re.I) and not (exempt and exempt.search(sent)):
                hits.append((line, why))
    return hits


def claim_hits(claim: dict, body: str, path: str = "x.md"):
    """(line, value-as-written, ok) for every mention of `claim` in `body`."""
    out = []
    want = _norm([str(claim["value"])])
    for line, sent in sentences(visible_text(path, body)):
        if "must" in claim and not re.search(claim["must"], sent, re.I):
            continue
        if "mustnot" in claim and re.search(claim["mustnot"], sent, re.I):
            continue
        for pat in claim["patterns"]:
            for m in re.finditer(pat, sent, re.I):
                got = _norm(m.groups())
                ok = got == want or got == str(claim["value"]).replace(" ", "")
                if not ok and "history" in claim and claim["history"].search(sent):
                    ok = True      # a superseded figure, quoted while explaining that it changed
                out.append((line, got, ok))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--allow-missing", action="store_true",
                    help="Do not fail when a surface file is absent. Coverage is still reported.")
    args = ap.parse_args()

    claims = canonical()
    text, missing = {}, []
    for s in SURFACES:
        p = os.path.join(ROOT, s)
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace") as fh:
                text[s] = fh.read()
        else:
            # An ABSENT surface is indistinguishable from one that agrees, so it must be reported.
            missing.append(s)

    print("=" * 78)
    print("  CLAIM CONSISTENCY — public surfaces vs the artifacts they came from")
    print("=" * 78)
    print(f"  {len(claims)} headline figures · {len(text)} of {len(SURFACES)} surfaces\n")
    if missing:
        print("  MISSING SURFACES — not scanned, so not certified")
        for s in missing:
            print(f"    -- {s}")
        print()

    failures = 0
    for c in claims:
        want = str(c["value"])
        found = [(s, line, got, ok) for s, body in text.items() for line, got, ok in claim_hits(c, body, s)]
        if not found:
            print(f"  ?? {c['name']:46} {want:10} PATTERN MATCHED NOTHING -- the check is broken, not the claim")
            failures += 1
            continue
        bad = [f for f in found if not f[3]]
        if bad or args.verbose:
            print(f"  {'!! ' if bad else 'ok '}{c['name']:46} {want:10} ({len(found)} mention(s))")
        for s, line, got, _ in bad:
            print(f"       {s}:{line}: says {got}, artifact says {want}")
            failures += 1

    print("\n  BANNED PHRASINGS")
    for s, body in text.items():
        for line, why in banned_hits(body, s):
            print(f"    !! {s}:{line}: {why}")
            failures += 1

    incomplete = bool(missing) and not args.allow_missing
    print("\n" + "=" * 78)
    if failures:
        print(f"  {failures} DISAGREEMENT(S)")
    elif missing:
        label = "PARTIAL" if args.allow_missing else "INCOMPLETE"
        print(f"  {label} — {len(text)} of {len(SURFACES)} surfaces agree; {len(missing)} not scanned (listed above).")
    else:
        print(f"  CLEAN — all {len(SURFACES)} surfaces agree with their artifacts")
    print("=" * 78)
    return 1 if (failures or incomplete) else 0


if __name__ == "__main__":
    sys.exit(main())
