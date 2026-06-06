"""Smoke tests for the plotting layer: each function writes a non-empty PNG.

Run:  python tests/test_plots.py
"""

import os
import sys
import tempfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xresidual import plots  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="xr_plots_")


def _exists_nonempty(path):
    return os.path.exists(path) and os.path.getsize(path) > 1000


def test_reliability_diagram_writes_png():
    rng = np.random.default_rng(0)
    p = rng.uniform(0.05, 0.95, 3000)
    y = (rng.uniform(size=3000) < p).astype(float)
    out = plots.reliability_diagram(p, y, os.path.join(_TMP, "rel.png"))
    assert _exists_nonempty(out)


def test_devig_comparison_writes_png():
    out = plots.devig_comparison([1.5, 4.0, 7.0], ["home", "draw", "away"],
                                 os.path.join(_TMP, "devig.png"))
    assert _exists_nonempty(out)


def test_trajectory_and_velocity_write_png():
    rows = []
    for ts in ("2026-06-10T00:00:00+00:00", "2026-06-12T00:00:00+00:00"):
        for team, p in [("Brazil", 0.1 if "10" in ts else 0.2), ("Spain", 0.18)]:
            rows.append({"ts": pd.Timestamp(ts), "team": team, "prob": p})
    long = pd.DataFrame(rows)
    out1 = plots.trajectory_chart(long, os.path.join(_TMP, "traj.png"))
    assert _exists_nonempty(out1)

    from xresidual import trajectory
    vel = trajectory.belief_velocity(long)
    out2 = plots.velocity_chart(vel, os.path.join(_TMP, "vel.png"))
    assert _exists_nonempty(out2)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
