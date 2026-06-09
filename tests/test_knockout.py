"""Tests for the knockout bracket — third-place assignment (FIFA Annex C). No network.

The third-place matcher is the most logic-heavy part of the sim and previously had no
tests; a greedy version produced group-stage rematches in ~3% of simulations. These
checks pin the hard invariants: every qualifying-third set gets a legal, rematch-free
perfect matching.

Run:  python tests/test_knockout.py
"""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xresidual import knockout as ko  # noqa: E402

GROUPS = sorted("ABCDEFGHIJKL")                       # 12 groups in the 2026 format
THIRD_SLOTS = [(i, ko.R32[i][2][1]) for i in range(16) if ko.R32[i][2][0] == "3"]
ALLOWED = dict(THIRD_SLOTS)


def _winner_group(i):
    for feeder in (ko.R32[i][1], ko.R32[i][2]):
        if feeder[0] == "W":
            return feeder[1]
    return None


def test_there_are_eight_third_slots():
    assert len(THIRD_SLOTS) == 8


def test_table_never_forces_a_rematch():
    # each third slot pairs a group WINNER with a third; the winner's own group must not
    # be in the slot's allowed set, else even a correct matching could rematch them.
    for i, allowed in THIRD_SLOTS:
        wg = _winner_group(i)
        assert wg is not None, f"slot {i} has no winner feeder"
        assert wg not in allowed, f"slot {i} allows winner's own group {wg}"


def test_assign_is_legal_perfect_matching_for_all_495_sets():
    # exhaustive: every way 8 of 12 thirds can qualify must get a bijective assignment
    # that respects every slot's Annex-C allowed set (which => no group-stage rematch).
    for combo in itertools.combinations(GROUPS, 8):
        qual = set(combo)
        res = ko._assign(qual, THIRD_SLOTS)
        assert len(res) == 8, f"{combo}: only {len(res)} slots filled"
        assert set(res.values()) == qual, f"{combo}: assigned groups != qualifying set"
        for idx, g in res.items():
            assert g in ALLOWED[idx], f"{combo}: slot {idx} got {g} outside allowed"


def test_assign_is_deterministic():
    q = set("ABCDEFGH")
    assert ko._assign(q, THIRD_SLOTS) == ko._assign(q, THIRD_SLOTS)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
