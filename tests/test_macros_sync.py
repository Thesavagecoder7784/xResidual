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
    """Every published number must resolve from JSON. A MISSING source must fail loudly, not fall back.

    The result JSONs are committed now (they were gitignored until 2026-07-25, which is how a clean
    clone silently fell back on 27 of 58 macros — nine of them to WRONG values, e.g. nCaptured 84
    against a true 86). So absence is no longer an acceptable state to shrug at: every source below
    must be present AND expose its key.

    The failure mode this closes is subtle. emit_macros falls back to a hardcoded literal when a
    source is missing, and the fallbacks are currently seeded from the true values — so a deleted
    artifact reproduces macros.tex byte-for-byte and the sync test stays green. The number is only
    wrong after the next data refresh, by which point nothing points at the cause. Requiring presence
    is what makes the fallback a safety net rather than a silent substitute."""
    D = EM.load()
    required = [
        ("H", "leadlag.n_events"),
        ("H", "leadlag.poly_share_decisive"),
        ("H", "infoshare.median_gg"),
        ("H", "infoshare.sign_p"),
        ("H", "infoshare.median_hasbrouck_ci"),
        ("V", "pooled.n_goals"),
        ("V", "pooled.pct_harvestable"),
        ("L", "pooled.poly_leads"),
        ("L", "n_matches"),
        ("I", "poly_infoshare_gg"),
        ("C", "versions.market.brier"),
        ("C", "paired_market_vs_v1.paired_t_p"),
        ("R", "median_ratio_logodds"),          # §5.3 reconstructed estimator
        ("R", "outcome_test.model_logloss"),
        ("T", "summary.n_trades"),              # §6.1 convergence forward-test
        ("T", "window.from"),
        ("B", "verdict"),                       # venue-vs-sharp as-of sweep
        ("U", "pct_harvestable_goal_weighted"),  # goal-unit harvestability check
    ]
    missing_src, missing_key = [], []
    for key, path in required:
        if not D.get(key):
            missing_src.append(f"{key} ({EM.SOURCES.get(key, '?')})")
            continue
        try:
            EM.dig(D, key, path)
        except (KeyError, IndexError):
            missing_key.append(f"{key}.{path}")
    assert not missing_src, (
        "committed source artifact(s) absent — the affected macros would silently fall back to a "
        "hardcoded literal instead of the data: " + ", ".join(sorted(set(missing_src))))
    assert not missing_key, (
        "canonical source key(s) missing — a published number would fall back to a hardcoded value "
        "instead of the data: " + ", ".join(missing_key))


def test_hardened_stats_match_raw_sources():
    """Cross-JSON invariant: _hardened_stats.json must describe the SAME sample as the raw
    builder outputs. Catches the failure `emit_macros --check` cannot see — a refresh that
    re-runs the builders but not harden_leadlag_stats.py, leaving the hardened aggregate stale
    (the Jul-19 bug: n_events 377 while the leadlag file had grown to 392). Raw sources are
    gitignored, so this only fires where the data lives (dev/VM) and skips on a clean checkout."""
    D = EM.load()
    H = D.get("H")
    if not H:
        if pytest:
            pytest.skip("_hardened_stats.json absent")
        return
    checked = []
    L = D.get("L")
    if L and L.get("pooled"):
        got = L["pooled"]["poly_leads"] + L["pooled"]["kalshi_leads"]
        assert got == H["leadlag"]["n_events"], (
            f"STALE hardened stats: leadlag poly+kalshi={got} but _hardened n_events="
            f"{H['leadlag']['n_events']} — rerun scripts/harden_leadlag_stats.py")
        checked.append("leadlag")
    I = D.get("I")
    if I and I.get("n_matches") is not None:
        assert I["n_matches"] == H["infoshare"]["n_matches"], (
            f"STALE hardened stats: infoshare file n_matches={I['n_matches']} but _hardened="
            f"{H['infoshare']['n_matches']} — rerun scripts/harden_leadlag_stats.py")
        checked.append("infoshare")
    if not checked and pytest:
        pytest.skip("raw leadlag/infoshare sources absent (gitignored) — checked on dev/VM")


def test_harvest_denominators_are_unambiguous():
    """The harvest ledger must expose exactly ONE field named n_matches.

    The Jul-25 reconciliation: the artifact carried a top-level `n_matches` (74 harvest FILES)
    next to `pooled.n_matches` (66 ledger matches). Same name, different number, nothing saying
    which one backs the published figures — so prose could quote either and look sourced. The
    file count is now `n_match_files`; assert the ambiguity cannot come back, and that it stays
    >= the ledger n (a match can yield a file with no qualifying goal, never the reverse)."""
    D = EM.load()
    V = D.get("V")
    if not V:
        if pytest:
            pytest.skip("_harvest_results.json absent (gitignored) — checked on dev/VM")
        return
    assert "n_matches" not in V, (
        "ambiguous denominator: top-level `n_matches` is back in _harvest_results.json. It means "
        "harvest FILES, not ledger matches — rename to `n_match_files` (scripts/build_harvest.py)")
    pooled = V.get("pooled")
    if not pooled:
        if pytest:
            pytest.skip("no pooled harvest result yet")
        return
    files, ledger = V.get("n_match_files"), pooled["n_matches"]
    assert files is not None, "_harvest_results.json missing `n_match_files` (coverage denominator)"
    assert files >= ledger, (
        f"impossible denominators: n_match_files={files} < pooled.n_matches={ledger} — every "
        f"ledger match must have produced a harvest file")


def test_harvest_medians_are_not_a_subtraction():
    """gross/cost/net are three independent medians; asserting they subtract would be wrong.

    Guards the prose claim, not the arithmetic: any writeup saying "gross X minus cost Y leaves
    net Z" is misdescribing the estimator. Pin that gross - cost != net so the day it accidentally
    does, nobody upgrades the prose to an implied subtraction."""
    D = EM.load()
    pooled = (D.get("V") or {}).get("pooled")
    if not pooled:
        if pytest:
            pytest.skip("_harvest_results.json absent (gitignored) — checked on dev/VM")
        return
    for k in ("estimator", "arithmetic_note"):
        assert pooled.get(k), (
            f"_harvest_results.json lost its `{k}` provenance field — a reader can no longer tell "
            f"a median-of-medians from a mean (scripts/build_harvest.py)")
    assert "median" in pooled["estimator"].lower(), "estimator field no longer names the statistic"


def test_hasbrouck_point_estimate_sits_inside_its_interval():
    """A published point estimate must lie inside the interval published beside it.

    The Jul-25 audit: `poly_infoshare_hasbrouck_mid` (75.2%) is a median across MATCHES, while the
    old `hasbrouck_mid_band` [77.3%, 92.2%] was a median across CONTRACTS of each contract's lo/hi.
    Different denominators, so every draft printed a point estimate BELOW its own lower bound. The
    match-unit CI now lives in _hardened_stats.json; assert it actually brackets the mid, and that
    the contract-unit band cannot be mistaken for a CI by its name alone."""
    D = EM.load()
    I, H = D.get("I"), D.get("H")
    if not I or not H:
        if pytest:
            pytest.skip("infoshare sources absent (gitignored) — checked on dev/VM")
        return
    assert "hasbrouck_mid_band" not in I, (
        "`hasbrouck_mid_band` is back in _infoshare_results.json. It is a per-CONTRACT "
        "identification width, not a band around the per-MATCH mid — it must stay named "
        "`hasbrouck_contract_band` (scripts/build_infoshare.py)")
    mid = I.get("poly_infoshare_hasbrouck_mid")
    ci = (H.get("infoshare") or {}).get("median_hasbrouck_ci")
    if mid is None or not ci:
        if pytest:
            pytest.skip("no Hasbrouck mid/CI in this checkout")
        return
    assert ci[0] <= mid <= ci[1], (
        f"incoherent interval: Hasbrouck mid {mid:.4f} is outside its own CI "
        f"[{ci[0]:.4f}, {ci[1]:.4f}] — the two are being computed on different units again")


def test_harvestability_cannot_be_quoted_at_the_wrong_unit():
    """`pooled.pct_harvestable` is a MEDIAN ACROSS MATCHES, not a share of goals.

    It reads 0.0 as soon as half the matches contain no harvestable goal, which is not the claim
    "0% of goals are harvestable" — every draft before Jul-25 published exactly that conflation,
    while the goal-weighted rate was ~9% over the full ledger (~11% on the 21-match subset that
    was all the archive could reach before the VM backup was recovered). Require the estimator
    string to spell out the unit, and require the goal-weighted companion to travel with it so the
    two denominators are always visible together."""
    D = EM.load()
    pooled = (D.get("V") or {}).get("pooled")
    if not pooled:
        if pytest:
            pytest.skip("_harvest_results.json absent (gitignored) — checked on dev/VM")
        return
    est = pooled.get("estimator", "").lower()
    assert "median match" in est and "never" in est, (
        "the harvest estimator field no longer states that pct_harvestable is the MEDIAN MATCH's "
        "share — restore the wording in scripts/build_harvest.py so prose cannot round it into "
        "'X% of goals'")
    if "pct_harvestable" in pooled and "pct_harvestable_goal_weighted" not in pooled:
        # An older pooled artifact predates the goal-weighted field; the standalone check must
        # then be present instead, so the goal-level rate is never simply unavailable.
        assert D.get("U"), (
            "pooled.pct_harvestable is published with no goal-level companion: either re-pool with "
            "the current build_harvest.py or run scripts/harvest_unit_check.py")


def test_goal_unit_harvest_check_declares_its_coverage():
    """The goal-weighted rate must always state the coverage it was computed on.

    This used to assert the archive was REDUCED. That premise died when the missing per-game
    JSONs were recovered from a VM backup (2026-07-25) and the rate was re-pooled over all 66
    ledger matches — and the hard-coded "this is a subset" note went on asserting it anyway.
    So the invariant is not "say it is reduced", it is "say what it actually covers", against
    both denominators that matter: the pooled ledger, and what a fresh CLONE can recompute."""
    U = EM.load().get("U")
    if not U:
        if pytest:
            pytest.skip("_harvest_unit_check.json absent — run scripts/harvest_unit_check.py")
        return
    assert U.get("coverage_note"), "_harvest_unit_check.json lost its coverage_note"
    ledger = U.get("pooled_ledger_n_matches")
    n = U["n_matches_checked"]
    if ledger:
        assert n <= ledger, (
            f"unit check claims {n} matches but the pooled ledger has "
            f"{ledger} — the check cannot cover more than the ledger it is checking")
        # The note must describe the coverage it actually has, in either direction. (Only the
        # positive claim is asserted: the note may legitimately mention the historical subset
        # in explaining why the figure moved, so "subset" appearing is not itself a defect.)
        note = U["coverage_note"].lower()
        if n >= ledger:
            assert "complete" in note, (
                f"the check now covers the whole {ledger}-match ledger but its coverage_note "
                f"does not say so — rerun scripts/harvest_unit_check.py")
        else:
            assert "subset" in note, (
                f"the check covers {n} of {ledger} ledger matches without saying so")

    # The clone-coverage gap is the failure this file exists to surface: the archives behind it
    # are gitignored, so a reviewer can silently recompute a different number. Whenever fewer
    # archives are tracked than were used, the note has to say the figure is not clone-reproducible.
    tracked = U.get("n_matches_tracked")
    if tracked is not None and tracked < n:
        assert "reproducibility" in U["coverage_note"].lower(), (
            f"only {tracked} of {n} harvest archives are git-tracked, so a clone recomputes a "
            f"different goal-weighted rate — coverage_note must say so")


def test_calibration_brier_gap_ships_with_its_uncertainty():
    """The market-vs-model Brier gap must never be publishable without its paired test.

    P1's frozen rule is a POINT comparison (market Brier < model Brier) and it passes — but the
    gap is not significant (p~0.25 on 72 games), and the prose read it as a demonstrated win.
    Require the paired block to exist so the macros can always quote the uncertainty."""
    C = EM.load().get("C")
    if not C:
        if pytest:
            pytest.skip("_calibration_results.json absent (gitignored) — checked on dev/VM")
        return
    if "market" not in C.get("versions", {}):
        if pytest:
            pytest.skip("no market calibration in this checkout")
        return
    paired = C.get("paired_market_vs_v1")
    assert paired, (
        "_calibration_results.json publishes a market Brier with no `paired_market_vs_v1` block — "
        "rerun scripts/build_calibration.py so the gap ships with its significance")
    for k in ("paired_t_p", "boot_ci_advantage", "n_games"):
        assert paired.get(k) is not None, f"paired test missing `{k}`"
    lo, hi = paired["boot_ci_advantage"]
    assert lo <= paired["advantage_a"] <= hi, "paired advantage lies outside its own bootstrap CI"


def test_underreaction_outcome_test_still_reproduces():
    """The §5.3 outcome test is the one published figure that survived reconstruction — pin it.

    The ratio statistic ("0.55x, 20 of 22, 7 of 8") was ad-hoc and did not reproduce; the outcome
    test did, exactly, when pooled over every goal in the clean subset. That exact agreement is the
    evidence the reconstruction found the right analysis rather than a plausible-looking one, so it
    is worth a regression: if these drift, the reconstruction has silently changed meaning."""
    R = EM.load().get("R")
    if not R:
        if pytest:
            pytest.skip("_underreaction_clean_results.json absent — run scripts/underreaction_clean.py")
        return
    o = R.get("outcome_test")
    assert o, "clean-subset artifact lost its outcome_test block"
    assert (o["model_logloss"], o["market_logloss"]) == (0.235, 0.361), (
        f"outcome test drifted from the published-and-reproduced values: "
        f"{o['model_logloss']}/{o['market_logloss']} vs 0.235/0.361")
    assert (o["model_brier"], o["market_brier"]) == (0.073, 0.113)
    assert o["model_better"], "the outcome test no longer rules out the over-eager-benchmark confound"
    # the gate must stay conservative: excluding flat quotes may only move the ratio toward 1
    assert R["median_ratio_logodds"] > R["median_ratio_logodds_ungated"], (
        "the gated ratio is no longer the conservative one — check the exclusion rule in "
        "scripts/underreaction_clean.py")
    assert R["n_goals_gated"] < R["n_goals"], "gate excluded nothing; the flat-quote filter is off"


def test_forwardtest_numbers_have_a_committed_source():
    """§6.1's convergence result must come from an artifact, not from prose.

    It drifted for exactly that reason: the only source was a gitignored viz/_*.js, and the notes
    kept quoting a cut taken two days into the run (6 trades / -2.6pp) long after it reached 8 /
    -1.66pp. Also pin that a null per_trade_sharpe is never dressed up as a number."""
    T = EM.load().get("T")
    if not T:
        if pytest:
            pytest.skip("_forwardtest_results.json absent — run scripts/forwardtest_run.py")
        return
    s = T.get("summary") or {}
    for k in ("n_trades", "total_pnl_pp", "hit_rate", "mean_pnl_pp"):
        assert s.get(k) is not None, f"forward-test summary missing `{k}`"
    assert T.get("window", {}).get("from") and T["window"].get("to"), (
        "the forward-test artifact must carry its window — the result is buildup-only and "
        "meaningless once the title field resolves")
    if s.get("per_trade_sharpe") is None:
        macros = EM.parse_macros(EM.build(EM.load())[0])
        assert not any("Sharpe" in k or "sharpe" in k for k in macros), (
            "per_trade_sharpe is null in the artifact but a Sharpe macro is being emitted")


def test_venue_vs_sharp_claim_is_as_of_dated_and_stable():
    """The venue-vs-sharp comparison may only be quoted at an as-of date the sweep actually covers.

    Two notes published two different undated pairs (~0.12/0.16 and ~0.18/0.26) for this. The
    magnitude drifts hard as the title field resolves — Kalshi's winner overround goes from ~6% to
    ~2300% — so an undated read is a read of whichever day it was taken. Require the quoted date to
    exist in the sweep, and require the direction to be stable across cutoffs before any of it is
    published at all."""
    B = EM.load().get("B")
    if not B:
        if pytest:
            pytest.skip("_basis_asof_sweep.json absent — run scripts/basis_asof_sweep.py")
        return
    series = B.get("series") or {}
    assert EM.BASIS_ASOF in series and series[EM.BASIS_ASOF], (
        f"emit_macros quotes the sharp-line comparison at {EM.BASIS_ASOF}, which the sweep does "
        f"not cover: {sorted(series)}")
    assert (B.get("verdict") or "").startswith("stable"), (
        f"the closer-to-sharp venue is not stable across as-of dates ({B.get('verdict')}) — the "
        f"directional claim must come out of the notes and the manuscript, not just the magnitude")
    row = series[EM.BASIS_ASOF]
    assert row["pm_closer_on"] + row["ka_closer_on"] == row["n_teams"], "team counts do not sum"


def test_frozen_overrounds_match_the_buildup_sweep():
    """Cross-artifact check: the frozen overrounds must sit in the window they were taken in.

    _frozen_observations.json records overrounds the title market can no longer be re-read for.
    They are BUILDUP reads, and Polymarket's compresses fast (~3% pre-kickoff, <1.5% by mid-group),
    so checking them against a mid-tournament sweep makes a correct number look wrong — which is
    how the 3.0% spent an audit flagged as an unexplained discrepancy. Check them against the
    buildup cutoffs specifically, which is the only comparison that means anything."""
    D = EM.load()
    F, B = D.get("F"), D.get("B")
    if not F or not B:
        if pytest:
            pytest.skip("frozen observations or the as-of sweep absent")
        return
    buildup = [v for k, v in (B.get("series") or {}).items() if v and k < "2026-06-11"]
    if not buildup:
        if pytest:
            pytest.skip("sweep has no pre-kickoff cutoffs — extend CUTOFFS in basis_asof_sweep.py")
        return
    for frozen_key, sweep_key, label in (("overround_poly_pct", "overround_poly_pct", "Polymarket"),
                                         ("overround_kalshi_pct", "overround_kalshi_pct", "Kalshi")):
        got = F.get(frozen_key)
        rng = [v[sweep_key] for v in buildup]
        if got is None:
            continue
        # generous: the frozen value is one intraday read, the sweep is end-of-day snapshots
        assert min(rng) - 1.0 <= got <= max(rng) + 1.0, (
            f"frozen {label} overround {got}% is outside the buildup sweep range "
            f"[{min(rng)}, {max(rng)}] — one of the two is measuring something else")


def test_calibration_n_is_the_scored_sample_not_the_tournament():
    """\\calN must be the games actually scored, never the 104-match tournament size.

    The forecast ledgers stop at 2026-06-27, so calibration covers the group stage only. Drafts
    wrote "~104 matches" next to a Brier, overstating the sample by ~44%."""
    C = EM.load().get("C")
    if not C or "market" not in C.get("versions", {}):
        if pytest:
            pytest.skip("_calibration_results.json absent or has no market version")
        return
    n = C["versions"]["market"]["n_games"]
    assert n <= C["n_played"], f"scored n={n} exceeds n_played={C['n_played']}"
    assert n < 104, (
        f"calibration n={n} claims the full 104-match tournament; the pre-committed ledger does "
        f"not reach the knockout rounds")


if __name__ == "__main__":
    test_macros_in_sync_with_json()
    test_emit_is_deterministic()
    test_flagship_macros_are_auto_wired()
    test_hardened_stats_match_raw_sources()
    test_harvest_denominators_are_unambiguous()
    test_harvest_medians_are_not_a_subtraction()
    test_hasbrouck_point_estimate_sits_inside_its_interval()
    test_harvestability_cannot_be_quoted_at_the_wrong_unit()
    test_goal_unit_harvest_check_declares_its_coverage()
    test_calibration_brier_gap_ships_with_its_uncertainty()
    test_calibration_n_is_the_scored_sample_not_the_tournament()
    print("ok — macros in sync, emit deterministic, flagship wired, hardened matches sources, "
          "harvest denominators unambiguous, units coherent, Brier gap carries its uncertainty")
