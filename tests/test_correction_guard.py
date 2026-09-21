"""The 2026-09-18 correction must hold: withdrawn figures may appear on a live surface only in a
sentence that is withdrawing them, never stated as fact. These pin the guard in scripts/check_claims.py,
including every bypass an independent review found in an earlier, looser version of it."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import check_claims as cc  # noqa: E402

FILLER = ("Some unrelated text about the group stage, now revised after the correction. "
          "The artifacts reproduce on a clean clone. ")


@pytest.mark.parametrize("claim", [
    # the original set
    "Polymarket leads Kalshi by a median +600 ms on goals.",
    "The Gonzalo-Granger share is 81.0% Polymarket.",
    "Polymarket carries an 81% information share.",
    "It leads 61 of 63 cointegrated matches.",
    "Some 57 of 66 matches lean one way.",
    "In short, the market beats my model.",
    "The price leader's book withdraws hardest at a goal.",
    # bypasses of the earlier 300-character context rule
    "The true lead is +600 ms: Polymarket reprices goals first.",
    "Polymarket leads Kalshi by +600 ms, and the result reproduces on every match.",
    "Polymarket leads Kalshi by +600 ms. Code and artifacts: see REPRODUCING.md.",
    "Polymarket leads Kalshi in 61 of 63 matches, a result the placebo test confirms.",
    # rewordings the earlier patterns missed
    "Polymarket led Kalshi by 600 milliseconds.",
    "Polymarket's information share is 81%.",
    "Its info share: 80.6%.",
    "It carries 81 percent of price discovery.",
    "In 61 of 63 matches Polymarket moved first.",
    "Polymarket won 61/63 matches.",
    "Markets beat my model.",
    "The market outperforms my model.",
    "The market beats the v1 model.",
    "The market beats my model, and not by a little.",
])
def test_withdrawn_claims_stated_as_fact_are_caught(claim):
    assert cc.banned_hits(FILLER + claim + " " + FILLER), claim


@pytest.mark.parametrize("claim", [
    "This finding is withdrawn: Polymarket leads Kalshi by a median +600 ms was the sampling.",
    "A market with no lead at all reproduces the +600 ms result.",
    "It previously claimed an 81% information share.",
    "So the claim is that the market is better calibrated, not that the market beats my model.",
    "When I fed my estimator a market in which neither venue leads, it reported +600 ms.",
])
def test_withdrawn_claims_in_a_withdrawing_sentence_pass(claim):
    assert not cc.banned_hits(FILLER + claim + " " + FILLER), claim


def test_html_is_read_as_visible_text():
    page = '<p>Polymarket <b>leads</b> Kalshi by <span class="x">+600</span>ms.</p>'
    assert cc.banned_hits(page, "page.html")


def test_blockquote_lines_are_one_sentence():
    quote = "> **Correction.** This project previously claimed that Polymarket prices goals\n> about 600 ms before Kalshi."
    assert not cc.banned_hits(quote)


def _tally_claim():
    return next(c for c in cc.canonical() if c["name"] == "pre-registration tally")


@pytest.mark.parametrize("text", [
    "The grade is 6 pass, 2 fail, 3 inconclusive.",
    "Graded: PASS 6 · FAIL 2 · INCONCL 3.",
    "6 / 2 / 3 pre-reg graded.",
    "Six passed, two failed, and three are inconclusive.",
])
def test_a_reverted_tally_is_caught_in_any_format(text):
    hits = cc.claim_hits(_tally_claim(), text)
    assert hits and not all(ok for _, _, ok in hits), text


def test_the_tally_may_be_quoted_while_explaining_the_regrade():
    hits = cc.claim_hits(_tally_claim(), "The tally moves from 6 pass / 2 fail / 3 inconclusive to 5 pass.")
    assert hits and all(ok for _, _, ok in hits)


def test_decimals_are_not_sentence_ends():
    assert [s for _, s in cc.sentences("Brier 0.487 vs. 0.503 on 72 games. Next.")] == \
        ["Brier 0.487 vs. 0.503 on 72 games.", "Next."]


def test_live_surfaces_are_clean():
    """Every live surface passes the guard as committed."""
    for s in cc.SURFACES:
        path = os.path.join(cc.ROOT, s)
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace") as fh:
                assert not cc.banned_hits(fh.read(), s), s


def test_archive_is_not_a_surface():
    """The withdrawn material is a frozen record; scanning it would force it to be rewritten."""
    assert not any(s.startswith("archive/") for s in cc.SURFACES)


@pytest.mark.parametrize("page", ["docs/note.html", "docs/lab.html"])
def test_archived_site_pages_keep_their_banner(page):
    """The archived pages are unscanned, so what protects a reader is the banner and noindex."""
    with open(os.path.join(ROOT, page), encoding="utf-8") as fh:
        s = fh.read()
    assert "withdrawn" in s[: s.index("</head>")].lower()          # the title/description say so
    assert 'content="noindex"' in s
    assert "Archived · withdrawn" in s
