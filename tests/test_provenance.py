"""Tests for the provenance + staleness helper. No network.

Run:  python tests/test_provenance.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xresidual import provenance as P  # noqa: E402


def test_stamp_has_expected_shape():
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "in.csv")
        open(f, "w").write("a,b\n1,2\n")
        s = P.stamp(d, params={"w": 0.4}, inputs={"in": f, "missing": os.path.join(d, "nope")})
        assert set(s) == {"generated_utc", "git", "params", "inputs"}
        assert s["params"]["w"] == 0.4
        assert s["inputs"]["in"]["sha8"] and s["inputs"]["in"]["bytes"] > 0
        assert s["inputs"]["missing"] is None          # absent input -> None, not a crash


def test_inputs_changed_detects_content_change_not_touch():
    with tempfile.TemporaryDirectory() as d:
        viz = os.path.join(d, "viz")
        os.makedirs(viz)
        inp = os.path.join(d, "squad_values.py")
        open(inp, "w").write("X = 1\n")
        # record a build against the current content
        P.write_provenance(viz, P.stamp(d, inputs={"squad_values": inp}))
        # a touch (mtime bump, same bytes) must NOT flag — content-hash, not mtime
        os.utime(inp, (1_700_000_000, 1_700_000_000))
        assert P.inputs_changed_since(viz, {"squad_values": inp}) == []
        # a real content change MUST flag
        open(inp, "w").write("X = 2\n")
        changed = P.inputs_changed_since(viz, {"squad_values": inp})
        assert len(changed) == 1 and changed[0]["input"] == "squad_values"
        assert changed[0]["was"] != changed[0]["now"]


def test_inputs_changed_empty_without_prior_provenance():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "viz"))
        inp = os.path.join(d, "in.csv"); open(inp, "w").write("a\n")
        assert P.inputs_changed_since(os.path.join(d, "viz"), {"in": inp}) == []


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
