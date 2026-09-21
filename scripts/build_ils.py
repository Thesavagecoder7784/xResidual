#!/usr/bin/env python3
"""Putnins (2013) Information Leadership Share (ILS), per match, from the committed info-share artifact.

The ILS combines the two standard price-discovery measures. Hasbrouck's information share (IS) and the
Gonzalo-Granger component share (CS) answer different questions and diverge when the venues carry
different amounts of microstructure noise; Putnins combines them into a ranking that is meant to be
robust to that. The definition:

    IL_1  = |(IS_1 / IS_2) * (CS_2 / CS_1)|,    ILS_1 = IL_1 / (IL_1 + IL_2)

With two venues (shares summing to one) this reduces to a simple leader rule:

    ILS_1 > 0.5   <=>   IS_1 / CS_1 > IS_2 / CS_2   <=>   IS_1 > CS_1

i.e. the leader is the venue whose INFORMATION share runs above its COMPONENT share. An earlier version
of this script had the direction backwards ("leader <=> CS > IS") and therefore reported Polymarket as
the ILS leader in 44 of 63 matches. Corrected, the same inputs point the other way. The formula here
matches scripts/identification_check.py, which is the authoritative version: it evaluates the ILS across
the Hasbrouck identification band (lower bound / midpoint / upper bound) rather than at the midpoint
alone, and that sweep is what the manuscript reports.

The result is a diagnostic, not a finding. The IS it is built from comes from a Kalshi mid sampled at one
message per second against Polymarket's full book (see CORRECTION.md), so neither venue's share is
identified on this capture; and the ILS is a function of a point-identified IS, while ours is identified
only up to a Cholesky interval whose width makes the leader call flip across the band.

    python scripts/build_ils.py
"""
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "writeups" / "_infoshare_results.json"
OUT = ROOT / "writeups" / "_ils_results.json"
EPS = 1e-6


def clip(x):
    return min(1 - EPS, max(EPS, float(x)))


def ils(is1: float, cs1: float) -> float:
    """Putnins ILS for venue 1, two-venue form. >0.5 means venue 1 leads."""
    r = (is1 / (1 - is1)) / (cs1 / (1 - cs1))
    return r * r / (r * r + 1)


def main() -> int:
    d = json.loads(SRC.read_text())
    rows = []
    for m in d["per_match"]:
        is1, cs1 = clip(m["poly_hasbrouck_mid"]), clip(m["poly_gg"])
        rows.append({
            "match": m["match"], "n_coint": m.get("n_cointegrated", m.get("n_contracts")),
            "poly_is": round(is1, 4), "poly_cs": round(cs1, 4),
            "is_minus_cs": round(is1 - cs1, 4),
            "ils_poly": round(ils(is1, cs1), 4),
            "poly_leads": is1 > cs1,
        })
    n = len(rows)
    poly_leads = sum(r["poly_leads"] for r in rows)
    med = statistics.median(r["ils_poly"] for r in rows)
    IS, CS = d["poly_infoshare_hasbrouck_mid"], d["poly_infoshare_gg"]
    out = {
        "metric": "Putnins (2013) Information Leadership Share, evaluated at the Hasbrouck midpoint",
        "n_matches": n,
        "gg_leader_count": d["match_leader_counts"],
        "poly_leads_by_ils": poly_leads, "of": n, "poly_leads_frac": round(poly_leads / n, 4),
        "median_ils_poly": round(med, 4),
        "pooled": {"poly_is": IS, "poly_cs": CS, "ils_poly": round(ils(clip(IS), clip(CS)), 4)},
        "direction": "ILS_poly > 0.5 <=> IS_poly > CS_poly (Putnins 2013, IL = |(IS1/IS2)(CS2/CS1)|)",
        "supersedes": ("an earlier run of this script inverted the direction (leader <=> CS > IS) and "
                       "reported Polymarket leading in 44 of 63 matches"),
        "vs_identification_check": ("that script gates each CONTRACT on ADF p<0.10, drops shares outside "
                                    "(0,1) and takes per-contract medians, so its midpoint reads 0.392 and "
                                    "22 of 61; this one works from per-match aggregates. Both put the "
                                    "midpoint ILS below 0.5"),
        "caveat": ("diagnostic only: the underlying information share is not identified on this capture "
                   "(Kalshi sampled at 1 Hz, see CORRECTION.md), and the ILS needs a point-identified IS "
                   "while ours is a Cholesky band -- see scripts/identification_check.py for the sweep"),
        "per_match": rows,
    }
    OUT.write_text(json.dumps(out, indent=1))
    print(f"Putnins ILS over {n} cointegrated matches\n" + "=" * 52)
    print(f"  pooled Hasbrouck IS (Poly) {IS:.3f} vs GG component share {CS:.3f} -> ILS {out['pooled']['ils_poly']:.3f}")
    print(f"  Polymarket is the ILS leader in {poly_leads} of {n} matches ({poly_leads / n:.0%}); "
          f"median ILS {med:.3f}")
    print("  Diagnostic only: the information share behind it is not identified on this capture "
          "(CORRECTION.md), and the leader call flips across the Cholesky band "
          "(scripts/identification_check.py).")
    print(f"  wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
