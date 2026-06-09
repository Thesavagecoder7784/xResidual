"""Tests for the P6 (information share) and P8 (sigma) metrics on synthetic data
where the right answer is known."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xresidual import microstructure as ms      # noqa: E402
from xresidual import ws_events as we            # noqa: E402


def _lead_follow(rng, n=800, obs=0.002, su=0.01):
    """Classic Hasbrouck DGP: an efficient price m, observed by the leader immediately
    (+ obs noise) and by the follower one step behind (+ obs noise). The observation
    noise makes the error-correction term identifiable (not collinear with lagged
    returns), which is the realistic case."""
    m = np.cumsum(rng.normal(0, su, n))
    leader = m + rng.normal(0, obs, n)
    follower = np.concatenate([[m[0]], m[:-1]]) + rng.normal(0, obs, n)
    return leader, follower


def test_information_share_detects_the_leader():
    rng = np.random.default_rng(0)
    leader, follower = _lead_follow(rng)
    res = ms.information_share(leader, follower, label_a="poly", label_b="kalshi")
    assert res is not None
    assert res["leader"] == "poly"          # the venue we fed as the leader
    assert res["gg_a"] > 0.65               # most price discovery on the leader
    # Hasbrouck bounds should also favour a
    if res["hasbrouck_a_mid"] is not None:
        assert res["hasbrouck_a_mid"] > 0.5


def test_information_share_is_symmetric():
    rng = np.random.default_rng(1)
    leader, follower = _lead_follow(rng)
    # now pass the follower first: leader should be label_b
    res = ms.information_share(follower, leader, label_a="poly", label_b="kalshi")
    assert res["leader"] == "kalshi"


def test_information_share_too_short():
    assert ms.information_share([0.1, 0.2, 0.3], [0.1, 0.2, 0.3]) is None


def test_max_move_sigma_flags_a_big_jump():
    # 200 calm bins (vol ~0.001), then a 0.05 jump = tens of sigma
    rng = np.random.default_rng(2)
    mids = list(np.cumsum(rng.normal(0, 0.001, 200)) + 0.5)
    mids.append(mids[-1] + 0.05)            # the shock
    series = [(i * 1000, float(m)) for i, m in enumerate(mids)]
    res = we.max_move_sigma(series, bin_ms=1000, window_bins=1800, min_prior=30)
    assert res is not None
    assert res["max_sigma"] > 8             # a real shock is many sigma above calm vol
    assert abs(res["ret_at_max"] - 0.05) < 0.02


def test_max_move_sigma_too_short():
    assert we.max_move_sigma([(0, 0.5), (1000, 0.5)]) is None
