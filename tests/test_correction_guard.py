"""The 2026-09-18 correction must hold: withdrawn figures may appear on a live surface only while
being withdrawn, never stated as fact. These pin the guard in scripts/check_claims.py."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import check_claims as cc  # noqa: E402

FILLER = "Some unrelated text about the group stage and the draw rate. " * 8


@pytest.mark.parametrize("claim", [
    "Polymarket leads Kalshi by a median +600 ms on goals.",
    "The Gonzalo-Granger share is 81.0% Polymarket.",
    "Polymarket carries an 81% information share.",
    "It leads 61 of 63 cointegrated matches.",
    "Some 57 of 66 matches lean one way.",
    "In short, the market beats my model.",
    "The price leader's book withdraws hardest at a goal.",
])
def test_withdrawn_claims_stated_as_fact_are_caught(claim):
    assert cc.banned_hits(FILLER + claim + " " + FILLER), claim


@pytest.mark.parametrize("claim", [
    "This finding is withdrawn: Polymarket leads Kalshi by a median +600 ms was the sampling.",
    "A market with no lead at all reproduces the +600 ms result.",
    "It previously claimed an 81% information share, now withdrawn.",
    "The claim is that the market is better calibrated, not that the market beats my model.",
])
def test_withdrawn_claims_quoted_in_correction_context_pass(claim):
    assert not cc.banned_hits(FILLER + claim + " " + FILLER), claim


def test_live_surfaces_are_clean():
    """Every live surface passes the guard as committed."""
    for s in cc.SURFACES:
        path = os.path.join(cc.ROOT, s)
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace") as fh:
                assert not cc.banned_hits(fh.read()), s


def test_archive_is_not_a_surface():
    """The withdrawn material is a frozen record; scanning it would force it to be rewritten."""
    assert not any(s.startswith("archive/") for s in cc.SURFACES)
