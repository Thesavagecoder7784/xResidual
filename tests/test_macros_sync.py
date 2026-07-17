"""Guardrail: the paper's canonical macros must match the committed result JSONs.

Run:  python tests/test_macros_sync.py     (or: pytest tests/test_macros_sync.py)

Fails if paper/arxiv/macros.tex has drifted from writeups/_*_results.json — i.e. a data
refresh landed without rerunning `python scripts/emit_macros.py`, or a number was
hand-edited. Folds the emitter's --check into the suite so a stale paper number can
never be committed. No network.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import emit_macros as EM  # noqa: E402

MACROS = os.path.join(ROOT, "paper", "arxiv", "macros.tex")

try:
    import pytest
except ImportError:  # allow standalone `python tests/test_macros_sync.py`
    pytest = None


def test_macros_in_sync_with_json():
    """macros.tex == what emit_macros would generate right now."""
    if not os.path.exists(MACROS):
        if pytest:
            pytest.skip("paper/arxiv/macros.tex not generated yet")
        return
    text, _, _, _ = EM.build(EM.load())
    committed = EM.parse_macros(open(MACROS).read())
    regenerated = EM.parse_macros(text)
    drifted = {k: (committed.get(k), v) for k, v in regenerated.items() if committed.get(k) != v}
    removed = [k for k in committed if k not in regenerated]
    msg = ""
    if drifted:
        msg = "macros.tex is STALE — run `python scripts/emit_macros.py`:\n" + "\n".join(
            f"  \\{k}: {o!r} -> {n!r}" for k, (o, n) in drifted.items()
        )
    if removed:
        msg += "\n" + "\n".join(f"  \\{k}: no longer emitted" for k in removed)
    assert not drifted and not removed, msg


def test_emit_is_deterministic():
    """Same inputs -> byte-identical output (so --check is meaningful)."""
    a, *_ = EM.build(EM.load())
    b, *_ = EM.build(EM.load())
    assert a == b, "emit_macros is not idempotent"


def test_flagship_macros_are_auto_wired():
    """The core price-discovery numbers must resolve from JSON, never silently fall back."""
    D = EM.load()
    flagship = [
        ("H", "leadlag.n_events"),
        ("H", "leadlag.poly_share_decisive"),
        ("H", "infoshare.median_gg"),
        ("H", "infoshare.sign_p"),
        ("V", "pooled.n_goals"),
        ("L", "pooled.poly_leads"),
    ]
    for key, path in flagship:
        try:
            EM.dig(D, key, path)
        except (KeyError, IndexError):
            raise AssertionError(
                f"canonical source {key}.{path} missing — a flagship paper number "
                f"would fall back to a hardcoded value instead of the data"
            )


if __name__ == "__main__":
    test_macros_in_sync_with_json()
    test_emit_is_deterministic()
    test_flagship_macros_are_auto_wired()
    print("ok — macros in sync, emit deterministic, flagship numbers wired")
