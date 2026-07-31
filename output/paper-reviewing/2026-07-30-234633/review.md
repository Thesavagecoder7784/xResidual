# Paper Review: Cross-Venue Price Discovery in World Cup Prediction Markets: A Real, Un-Harvestable Lead

**Format:** Generic academic · **Severity:** Strict · **Date:** 2026-07-30

> **Reviewer conflict-of-interest disclosure.** This review was produced by the same assistant that
> co-authored substantial portions of the manuscript's current revision (§1–§8 were all edited in
> collaboration). It is therefore **not an independent review**. Findings below were verified against
> source artifacts rather than recalled, and severity was calibrated to strict to partially offset
> familiarity bias — but a genuinely independent reviewer remains necessary.

## Summary

The paper uses goals in the 2026 FIFA World Cup as an exogenous, repeated information shock to measure
cross-venue price discovery between Kalshi and Polymarket, then asks whether the resulting lead is
tradeable. It finds Polymarket reprices first (72% of 392 decisive events, median +600 ms; 81.0%
Gonzalo-Granger information share, leading 61 of 63 cointegrated matches) and that the lead is
un-harvestable: best-price depth collapses to 0.5% of normal at the goal, so the median match yields
no harvestable goal for a liquidity-taking follower. The study is pre-registered with eleven dated
predictions graded publicly (6 pass / 2 fail / 3 inconclusive).

## Strengths

1. **The harvestability test is a genuine contribution and is executed carefully.** Measuring a
   lead and then gating it on resting depth — with a disclosed cost model (widened goal-window
   half-spread plus taker fee) and a sensitivity analysis showing the conclusion survives relaxing
   the depth gate from 25% to 1% — is more than the literature currently does. The "both ways to
   interact lose" argument (taker finds no size; maker is the adverse-selected fill) closes the
   obvious rebuttal pre-emptively.

2. **The latency identification is handled properly.** §3 declines to assert a bound on inter-venue
   delivery asymmetry and instead tests for it, using calm play as a placebo window. The argument
   that a constant offset is regime-independent and therefore cannot produce an 86%→53% swing is
   correct and is the right way to answer the most dangerous objection to the design.

3. **Disclosure quality is unusually high, and specifically in the places that cost the authors
   something.** Reporting that 5 of 63 matches return a Gonzalo-Granger share above one (max 1.42),
   giving the in-support median alongside, and explaining why the median rather than the mean is the
   headline, is the sort of thing most authors suppress. Likewise the P1 clarification that the pass
   certifies calibration and not out-forecasting.

4. **Pre-registration with public grading, including two failures retained.** Rare in empirical
   finance and directly responsive to the field's replication problem.

5. **Sample construction is stated as a funnel table** rather than scattered across sections
   (though see Major Issue 2).

## Weaknesses

1. Two claims in the Data Availability statement are false as written (Major Issue 1).
2. The sample funnel omits the sample used for the §5.3 headline (Major Issue 2).
3. The central harvestability statistic carries no uncertainty interval (Major Issue 3).
4. A fifth of the lead-lag events sit at 3–8 s, undiscussed under a "+600 ms" headline (Major Issue 4).
5. Research question 3 (favorite-longshot bias) is effectively unanswered.
6. The canonical reference for interpreting a Hasbrouck/Gonzalo-Granger divergence is uncited.

## Major Issues

1. **The Data Availability statement makes two claims that the repository contradicts.**
   The paper states: *"Every number in this paper is machine-injected from a shipped, versioned
   artifact rather than hand-typed."* Two macros are hardcoded string literals rather than reads
   from any artifact — `scripts/emit_macros.py` lines 141–142 define `loopRawAtClose` as the
   constant `"49.95\,pp"` and `overroundKClose` as `"2300\%"`. Both appear in §5.1 as evidence. The
   claim is also strained by prose estimates such as "on the order of 200 goals" (§6.2), which is a
   rate-based approximation, not an artifact value.
   → **Suggested fix:** either wire both macros to `viz/market/_basis.js` (`avg_abs_raw`, and the
   Kalshi overround), or soften the claim to "every result in the flagship analyses is machine-
   injected." The current phrasing is the kind of absolute a referee will test, and it fails.

2. **Table 1 claims to state the funnel "once" but omits the §5.3 primary sample.**
   §5.3 opens *"Across 54 matches and 185 goal-anchored events."* Neither 54 nor 185 appears in
   Table 1, which lists only the curated "Under-reaction subset: 8." The table's caption asserts
   that each row is "a filter required by the estimator... not a selection made after inspecting
   results" — so a results subsection running on an unlisted sample directly undercuts the table's
   stated purpose. This is the specific suspicion the table exists to defuse.
   → **Suggested fix:** add a row for the 54-match / 185-event goal-anchored sample and state its
   relationship to the 86 captures and to the 8-match curated subset.

3. **The central claim has no uncertainty interval.** "The median match yields 0% harvestable
   goals" is a median across 66 matches and is the paper's headline contribution, yet it is reported
   as a point with no bootstrap CI — while the lead-lag share, the median lead, and both information
   shares all carry bootstrap intervals. The asymmetry is conspicuous: the one number that is *not*
   given an interval is the one the title rests on.
   → **Suggested fix:** report a match-resampling bootstrap CI on the harvestable share, using the
   same machinery as `harden_leadlag_stats.py`. If the CI is degenerate (many matches at exactly
   zero), say so — that is itself informative and stronger than silence.

4. **21% of the lead-lag events lie outside the presented range and are not discussed.**
   Figure 1 is truncated at ±3 s and annotates "+83 events beyond ±3 s (gated ≤ 8 s)." So 83 of 392
   events — over a fifth — have cross-venue leads between 3 and 8 seconds. Under a headline of
   "median +600 ms," a reader is entitled to ask whether a 3–8 s cross-venue lag reflects the same
   mechanism, or events where the two venues responded to different information. The 8 s gate is
   disclosed in §4; its consequence for the sample composition is not.
   → **Suggested fix:** report the share of events by lead bucket, and show the headline share and
   median are stable when the gate is tightened to (say) 3 s. If they are, this becomes a robustness
   result rather than an unexamined tail.

5. **Research question 3 is posed and not answered.** The introduction lists "Calibration and the
   favorite-longshot bias (replication)" as one of three questions. The bias receives one sentence
   in §5.4 with no statistic, magnitude, figure, or test — "the model's advance probabilities are
   systematically more extreme than the market's at both price extremes" — and the corresponding
   pre-registered prediction (P2) is INCONCLUSIVE because prediction markets quote no draw.
   → **Suggested fix:** either quantify the descriptive claim (a decile table would suffice) or
   demote the bias from a headline research question to a secondary observation. Promising three
   questions and delivering two-and-a-half is an avoidable weakness.

6. **The Hasbrouck and Gonzalo-Granger estimates diverge and the canonical reference for
   interpreting that divergence is uncited.** §5.2 reports GG 81.0% against Hasbrouck 75.2% on the
   same per-match unit, plus a per-contract Cholesky width of 77–92%. Putniņš (2013), *"What do
   price discovery metrics really measure?"* (Journal of Empirical Finance) is the standard treatment
   of exactly when and why these measures disagree, and is absent from a 20-item bibliography. The
   project's own internal writeups reference the Putniņš information leadership share as "the natural
   refinement," so this appears to be an oversight rather than a considered omission.
   → **Suggested fix:** cite Putniņš and state in one sentence why GG is the headline and Hasbrouck
   the corroboration.

## Minor Issues

1. **OFI t-statistics of ≈115/72 are printed while simultaneously disclaimed** (§5.5) as
   overstating significance. Reporting a statistic you tell the reader not to believe invites the
   question of why it is there. Either report a match-clustered statistic or report only the sign.
2. **"22 of 22 goals whose quote moved" (§5.3)** is a perfect record on a subset from which 7 of 29
   goals were excluded for not moving. The exclusion is disclosed and argued to be conservative for
   the *ratio*, but a 22/22 count invites scrutiny the ratio argument does not address.
3. **Two different subsets of size 66 appear in Table 1** ("Per-match lead unit" and "Harvest
   ledger") without a note that they are different sets that coincide in size. In a single funnel
   table this reads as one subset carried forward.
4. **The abstract's phrase "the median match yields 0% harvestable goals"** is correct but strains
   under compression; a reader may take "0% harvestable goals" as a goal-level rate, which is the
   precise misreading §6.2 spends a paragraph preventing.
5. **`basisAsOf` remains a manual macro** flagged by `emit_macros.py` on every run, and the Betfair
   basis paragraph (§5.1) rests on a single date, while a nine-date replay exists in
   `_basis_asof_sweep.json` and is stronger (Polymarket closer on 9 of 9 dates).
6. One overfull hbox remains in the compiled PDF (cosmetic).

## Questions for Authors

1. What is the bootstrap confidence interval on the harvestable share, and is it degenerate?
2. Do the headline lead share and median lead survive tightening the co-movement gate from 8 s to
   3 s, i.e. excluding the 83 long-lag events?
3. Where do the 54 matches / 185 events of §5.3 sit in the Table 1 funnel, and why does that sample
   differ from the 86 captures?
4. Are `loopRawAtClose` and `overroundKClose` derivable from `_basis.js`, or is the Data Availability
   claim being relaxed?
5. Given P2 is inconclusive and §5.4's bias claim is unquantified, should the favorite-longshot bias
   remain a stated research question?

## Missing Related Work

| Paper | Key Contribution | Relevance | Cite in |
|---|---|---|---|
| Putniņš (2013), *What do price discovery metrics really measure?*, J. Empirical Finance | Establishes when Hasbrouck IS and Gonzalo-Granger CS diverge and what each measures; proposes information leadership share | The paper reports both measures diverging (81.0% vs 75.2%) without the standard interpretive frame | §2, §4, §5.2 |
| Wolfers & Zitzewitz (2004), *Prediction Markets*, J. Economic Perspectives | The canonical survey framing prediction-market efficiency | A 20-reference prediction-markets paper without it is conspicuous | §2 |
| Easley, López de Prado & O'Hara (2012), *Flow toxicity and liquidity in a high-frequency world*, RFS | Flow toxicity (VPIN) as the driver of liquidity withdrawal | Directly the mechanism claimed in §6.2; would strengthen the adverse-selection framing | §2, §6.2 |
| Menkveld (2013), *High frequency trading and the new market makers*, J. Financial Markets | Cross-venue market making and fragmentation | Supports the cross-venue framing beyond the arms-race citations | §2 |

*Note on method:* the skill's `paper_search.py` was run but returned unusable results — its arXiv
query is date-filtered to recent submissions and the Semantic Scholar endpoint rate-limited, yielding
topically irrelevant hits (Gaussian-process forecasting, 2016 dark-pool theory). The table above is
therefore compiled from domain knowledge and verified against the manuscript's bibliography, not from
the tool's output. `missing_references.json` records the failure honestly rather than padding.

## Scores

- **Overall Assessment:** Weak Accept
- **Overall Score:** 6/10
- **Confidence:** 4/5 (high on the artifacts and internal consistency; lower on field-relative novelty)
- **Novelty:** Medium — the lead direction replicates Ng et al. (2026); the harvestability gate and
  exogenous-event identification are genuinely new
- **Technical Soundness:** High — estimators verified correct against textbook definitions; VECM
  correctly lagged with no look-ahead; cluster-robust inference appropriate
- **Significance:** Medium-High — the un-harvestability result contradicts an actively-marketed
  belief and the method transfers to any venue pair
- **Clarity:** Medium-High — well-organised and unusually candid, though §5.1 carries heavy
  scaffolding around the P3 verdict
- **Reproducibility:** High — clean-clone verified, pre-registration tagged, artifacts shipped;
  reduced by non-redistributable raw captures, which is disclosed and legally constrained

## Additional Notes

The paper's disposition is its main asset. It repeatedly reports things that weaken its own
position — the out-of-support GG shares, the P1 non-significance, the detection over-firing, the
frozen-observation limits — and the cumulative effect is a document that reads as trustworthy. The
Major Issues above are almost all of one kind: places where a *stated standard* (every number
machine-injected; the funnel stated once; intervals on the headline numbers) is not quite met. That
is a comparatively good failure mode, because each is mechanically fixable without touching a result.

The single highest-value revision is Issue 3. A paper titled *A Real, Un-Harvestable Lead* should
put an interval on un-harvestability.

Sample size remains the binding limit on ambition: 63 cointegrated matches from one tournament will
not move a field, and the paper does not claim it will. Targeted at a specialist venue this is
comfortably publishable; targeted higher it is not.
