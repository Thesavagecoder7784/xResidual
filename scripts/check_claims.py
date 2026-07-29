#!/usr/bin/env python3
"""Do the prose surfaces still agree with the JSON artifacts they came from?

`emit_macros.py --check` already guarantees this for the LaTeX manuscript, and it has never
let a number drift. Everything else -- the README, FINDINGS, the desk note, the site, the
writeups, both submission packages -- carries the same headline figures as hand-typed prose
with nothing keeping them honest. Four separate published claims were found stale or
mislabelled on 2026-07-28 alone. This closes that gap.

For each headline figure it holds the canonical value (read from the artifact, never
hard-coded) and the surfaces that quote it, then flags any surface that states a DIFFERENT
value for the same quantity. It is deliberately narrow: it checks the numbers that appear in
an abstract or a headline paragraph, not every number in the repo.

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

# Surfaces that carry headline claims in prose.
SURFACES = [
    "README.md", "FINDINGS.md", "METHODOLOGY.md", "REPRODUCING.md",
    "writeups/price_discovery_note.html", "writeups/cross-venue-price-discovery.md",
    "writeups/ssrn_paper.md", "writeups/blog_post.md", "writeups/retrospective.md",
    "paper/arxiv/SSRN_submission.md", "paper/arxiv/JPM_submission.md",
    "docs/index.html", "docs/note.html", "docs/method.html",
]


def _j(path: str):
    with open(os.path.join(ROOT, path)) as fh:
        return json.load(fh)


def canonical() -> list[dict]:
    """Every headline figure, its true value from the artifact, and how it may be written."""
    hard = _j("writeups/_hardened_stats.json")
    ll, isr = hard["leadlag"], hard["infoshare"]
    harv = _j("writeups/_harvest_results.json")["pooled"]
    unit = _j("writeups/_harvest_unit_check.json")
    cal = _j("writeups/_calibration_results.json")["versions"]["v1"]

    return [
        dict(name="lead-lag share of decisive events",
             value=round(ll["poly_share_decisive"] * 100),
             pattern=r"(\d{2})%\s*of\s*(?:the\s*)?(?:392|decisive)", unit="%"),
        dict(name="decisive events",
             value=ll["n_events"], pattern=r"(\d{3})\s*decisive", unit=""),
        dict(name="median lead ms",
             value=int(ll["median_lead_ms"]), pattern=r"median\s*\+?(\d{3})\s*ms", unit="ms",
             # 400ms is the SIGNED pooled median (counts Kalshi-led events negative) and 500ms is
             # the superseded n=8 read, both discussed explicitly in the writeups. Neither is a
             # restatement of the headline, so neither is a drift.
             allow={"400", "500"}),
        dict(name="per-match lean",
             value=f"{ll['per_match_poly_leaning']} of {ll['per_match_total']}",
             pattern=r"(\d{2}\s*of\s*\d{2})\s*matches\s*lean", unit=""),
        dict(name="Gonzalo-Granger info share",
             value=round(isr["median_gg"] * 100, 1),
             pattern=r"(?:information share|GG|Gonzalo.Granger)[^.]{0,60}?(\d{2}\.\d)%", unit="%"),
        dict(name="info-share matches led",
             value=f"{isr['matches_poly_gt_50']} of {isr['n_matches']}",
             pattern=r"(\d{2}\s*of\s*\d{2})\s*cointegrated", unit=""),
        dict(name="harvest ledger rows",
             value=harv["n_goals"], pattern=r"(\d{3})\s*goal-shock", unit="obs"),
        dict(name="harvest gross cents",
             value=harv["gross_med_c"], pattern=r"median\s*(?:gross\s*)?(\d{2}\.\d)[\s-]*cent", unit="c"),
        dict(name="goal-weighted harvestable",
             value=round(unit["pct_harvestable_goal_weighted"]),
             pattern=r"~?(\d{2})%\s*goal-weighted", unit="%"),
        dict(name="model Brier (v1)",
             value=cal["brier"], pattern=r"model[^.]{0,40}?Brier[^.]{0,20}?(0\.\d{4})", unit=""),
    ]


BANNED = [
    (r"405\s+goals",
     "'405 goals' — build_harvest.py appends one row per CONTRACT per shock, so these are "
     "goal-shock observations (~2 per goal). 405 goals in 66 matches is also arithmetically "
     "impossible: the whole 104-match tournament produced 308."),
    # Exempt the corrective sentences that QUOTE the bad phrasing in order to forbid it.
    (r"(?<![\d.])(?<!not \")(?<!never as \')0%\s*of\s*goals",
     "'0% of goals' — the published estimator is a median ACROSS MATCHES. Correct phrasing: "
     "'the median match yields no harvestable goal'."),
    (r"5\s*(?:to|-|–)\s*8\s*cent",
     "the uncited '5 to 8 cent' press figure — we measure the raw gap at 3.98pp."),
    # Legitimate when explicitly scoped to the 33-game window it was measured on.
    (r"highest scoring rate of the modern era(?![^.]{0,200}33 group games)"
     r"(?<!through the first \*\*33 group games\*\*, 2026 is running \*\*3\.09 goals/game\*\* — the highest scoring rate of the modern era)",
     "unqualified scoring superlative — 2.99 g/g group / 2.88 full is scope-dependent and "
     "not backed by a shipped historical series."),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    claims = canonical()
    text = {}
    for s in SURFACES:
        p = os.path.join(ROOT, s)
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace") as fh:
                text[s] = fh.read()

    print("=" * 78)
    print("  CLAIM CONSISTENCY — prose surfaces vs the artifacts they came from")
    print("=" * 78)
    print(f"  {len(claims)} headline figures · {len(text)} surfaces\n")

    failures = 0
    for c in claims:
        want = str(c["value"])
        hits, bad = 0, []
        for s, body in text.items():
            for m in re.finditer(c["pattern"], body, re.I):
                got = re.sub(r"\s+", " ", m.group(1)).strip()
                hits += 1
                if got.replace(" ", "") != want.replace(" ", "") and got not in c.get("allow", set()):
                    bad.append(f"{s}: says {got}, artifact says {want}")
        status = "ok " if not bad else "!! "
        if bad or args.verbose:
            print(f"  {status}{c['name']:36} {want}{c['unit']:4} ({hits} mention(s))")
        for b in bad:
            print(f"       {b}")
            failures += 1

    # The rendered PDF is scanned too. Source-only scanning has a real blind spot: the abstract
    # wrote "\\nGoalsHarvest{} goals", which renders as "405 goals" but contains no such literal
    # string, so every source-level check passed while the built paper carried the mislabel. Caught
    # only by compiling. If main.pdf is absent this degrades quietly to source-only.
    pdf = os.path.join(ROOT, "paper", "arxiv", "main.pdf")
    if os.path.exists(pdf):
        try:
            import pypdf
            rendered = "\n".join(pg.extract_text() or "" for pg in pypdf.PdfReader(pdf).pages)
            text["paper/arxiv/main.pdf (rendered)"] = rendered
            print(f"  + scanning the rendered PDF ({len(pypdf.PdfReader(pdf).pages)} pages) "
                  f"— macros hide banned phrasings from a source-only scan")
        except Exception as e:  # noqa: BLE001
            print(f"  ! could not read main.pdf ({type(e).__name__}); source-only scan")

    print("\n  BANNED PHRASINGS")
    for pat, why in BANNED:
        for s, body in text.items():
            if re.search(pat, body, re.I):
                print(f"    !! {s}: {why}")
                failures += 1

    print("\n" + "=" * 78)
    print(f"  {'CLEAN — every surface agrees with its artifact' if not failures else f'{failures} DISAGREEMENT(S)'}")
    print("=" * 78)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
