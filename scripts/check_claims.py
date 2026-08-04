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
    calall = _j("writeups/_calibration_results.json")
    cal = calall["versions"]["v1"]
    # Real location, verified: versions.market.brier (also mirrored as paired_market_vs_v1.brier_a).
    # No literal fallback -- a silent fallback would defeat the point of reading from the artifact.
    mkt_brier = calall["versions"]["market"]["brier"]

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
        # TWO measures, two guards. The old single rule matched a bare "information share" and
        # so accepted either number for either name -- which is precisely the conflation the
        # manuscript was carrying (the GG COMPONENT share was called an information share in the
        # abstract). Splitting the rule makes the checker enforce the distinction: "component
        # share"/"Gonzalo-Granger" must be followed by the GG number, "Hasbrouck" by its own.
        dict(name="Gonzalo-Granger component share",
             value=round(isr["median_gg"] * 100, 1),
             pattern=r"(?:component share|GG|Gonzalo.Granger)[^.]{0,60}?(\d{2}\.\d)%", unit="%"),
        dict(name="Hasbrouck information share",
             value=round(isr["median_hasbrouck"] * 100, 1),
             pattern=r"Hasbrouck[^.]{0,60}?(\d{2}\.\d)%", unit="%"),
        dict(name="info-share matches led",
             value=f"{isr['matches_poly_gt_50']} of {isr['n_matches']}",
             pattern=r"(\d{2}\s*of\s*\d{2})\s*cointegrated", unit=""),
        dict(name="harvest ledger rows",
             value=harv["n_goals"], pattern=r"(\d{3})\s*goal-shock", unit="obs"),
        dict(name="harvest gross cents",
             value=harv["gross_med_c"], pattern=r"median\s*(?:gross\s*)?(\d{2}\.\d)[\s-]*cent", unit="c"),
        # 1-2 digits, not 2: the full-ledger re-pool moved this from 11% to 9%, and a \d{2}
        # pattern then matched nothing at all -- caught only by the zero-mention guard below.
        # BOTH word orders: "9% goal-weighted" and "goal-weighted rate is 9.1%". The second
        # phrasing sat stale in three surfaces through a re-pool because only the first matched.
        dict(name="goal-weighted harvestable",
             value=round(unit["pct_harvestable_goal_weighted"]),
             # The emphasis marker between "is" and the number may be markdown (**) or HTML
             # (<b>): docs/note.html sat stale behind a <b> tag while the guard reported CLEAN.
             pattern=r"(?:~?(\d{1,2})(?:\.\d)?%\s*goal-weighted"
                     r"|goal-weighted[^.]{0,40}?(?:is|:)\s*(?:\*{1,2}|<b>)?\s*~?(\d{1,2})(?:\.\d)?%)",
             unit="%"),
        # The artifact carries 4 dp (0.5033) but the manuscript macro rounds to 3 (0.503), so the
        # comparison is made at the precision the paper prints. Demanding 4 dp matched nothing and
        # passed silently -- the failure mode the zero-mention guard below now catches.
        # Anchored on the MARKET Brier (also artifact-derived) because the manuscript contains a
        # second "Brier X vs. Y" pair for the under-reaction outcome test (0.073 vs 0.113). Both
        # numbers in the anchor come from artifacts, so nothing is hard-coded.
        dict(name="model Brier (v1)",
             value=round(cal["brier"], 3),
             pattern=rf"Brier\s+{round(mkt_brier, 3)}\s+vs\.?\\?\s+(0\.\d{{3}})", unit=""),
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
            missing.append("paper/arxiv/main.pdf (rendered)")
    else:
        missing.append("paper/arxiv/main.pdf (rendered)")

    expected = len(SURFACES) + 1  # +1 for the rendered PDF
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
                if got.replace(" ", "") != want.replace(" ", "") and got not in c.get("allow", set()):
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
    for pat, why in BANNED:
        for s, body in text.items():
            if re.search(pat, body, re.I):
                print(f"    !! {s}: {why}")
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
