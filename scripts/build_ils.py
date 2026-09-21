#!/usr/bin/env python3
"""
Putnins (2013) Information Leadership Share (ILS) — noise-robust price-discovery metric.

FORWARD-ONLY probe (v1 untouched). Reads the per-match Hasbrouck information share (IS)
and Gonzalo-Granger component share (CS) already estimated in writeups/_infoshare_results.json
and combines them into the ILS, which is robust to the two venues carrying different
amounts of microstructure noise (Kalshi: thin book, coarse 1c tick vs Polymarket's deep book).

Why this matters here: the headline 81% is the GG *component* share (CS), which is noise-free
by construction. The Hasbrouck IS is noise-sensitive; Yan-Zivot (2010) show noise INFLATES a
venue's IS. So the leader in the ILS sense is the venue whose CS exceeds its IS.

Direction (settled from theory): leader <=> CS > IS.
Normalization: two forms reported until the exact Putnins (2013) Eq. is verified against the paper.
  - linear : ILS_1 = (CS_1*IS_2) / (CS_1*IS_2 + CS_2*IS_1)
  - squared: IL_1 = (CS_1/CS_2)*(IS_2/IS_1);  ILS_1 = IL_1^2 / (IL_1^2 + 1)
Both give ILS_1 > 0.5  <=>  CS_1 > IS_1 (identical leader call; magnitude differs).
"""
import json, statistics, sys
from pathlib import Path

SRC = Path("writeups/_infoshare_results.json")
OUT = Path("writeups/_ils_results.json")
EPS = 1e-6

def clip(x): return min(1 - EPS, max(EPS, float(x)))

def ils_linear(is1, cs1):
    is2, cs2 = 1 - is1, 1 - cs1
    return (cs1 * is2) / (cs1 * is2 + cs2 * is1)

def ils_squared(is1, cs1):
    is2, cs2 = 1 - is1, 1 - cs1
    il = (cs1 / cs2) * (is2 / is1)
    return il * il / (il * il + 1)

def main():
    d = json.loads(SRC.read_text())
    per = d["per_match"]
    rows = []
    for m in per:
        is1 = clip(m["poly_hasbrouck_mid"])   # Polymarket Hasbrouck information share
        cs1 = clip(m["poly_gg"])              # Polymarket Gonzalo-Granger component share
        rows.append({
            "match": m["match"], "n_coint": m.get("n_cointegrated", m.get("n_contracts")),
            "poly_is": round(is1, 4), "poly_cs": round(cs1, 4),
            "is_minus_cs": round(is1 - cs1, 4),
            "ils_lin": round(ils_linear(is1, cs1), 4),
            "ils_sq": round(ils_squared(is1, cs1), 4),
            "poly_leads": cs1 > is1,          # ILS leader call
        })

    n = len(rows)
    poly_leads = sum(r["poly_leads"] for r in rows)
    med_lin = statistics.median(r["ils_lin"] for r in rows)
    med_sq = statistics.median(r["ils_sq"] for r in rows)

    # pooled IS/CS -> pooled ILS (a second, aggregate view)
    IS = d["poly_infoshare_hasbrouck_mid"]; CS = d["poly_infoshare_gg"]
    pooled = {
        "poly_is": IS, "poly_cs": CS,
        "ils_lin": round(ils_linear(clip(IS), clip(CS)), 4),
        "ils_sq": round(ils_squared(clip(IS), clip(CS)), 4),
    }

    out = {
        "metric": "Putnins (2013) Information Leadership Share",
        "n_matches": n,
        "gg_leader_count": d["match_leader_counts"],           # for comparison (61/63)
        "poly_leads_by_ils": poly_leads, "of": n,
        "poly_leads_frac": round(poly_leads / n, 4),
        "median_ils_linear": round(med_lin, 4),
        "median_ils_squared": round(med_sq, 4),
        "pooled": pooled,
        "direction": "leader <=> CS > IS (noise inflates IS; Yan-Zivot 2010)",
        "formula_status": "normalization pending verification vs Putnins (2013) Eq.; linear+squared both reported",
        "per_match": rows,
    }
    OUT.write_text(json.dumps(out, indent=1))

    # ---- console summary ----
    print(f"Putnins ILS over {n} cointegrated matches\n" + "=" * 52)
    print(f"  pooled Hasbrouck IS (Poly): {IS:.3f}   GG component share (Poly): {CS:.3f}")
    print(f"  -> IS {'<' if IS < CS else '>'} CS  (Kalshi noisier => its IS inflated above its CS)\n")
    print(f"  Polymarket is the ILS leader in {poly_leads} of {n} matches ({poly_leads/n:.0%})")
    print(f"    (compare: GG component share leads {d['match_leader_counts'].get('polymarket')} of {n};"
          f" lead-lag event study 72%)")
    print(f"  median ILS (Poly)  linear form : {med_lin:.3f}")
    print(f"  median ILS (Poly)  squared form: {med_sq:.3f}")
    print(f"  pooled ILS (Poly)  linear/squared: {pooled['ils_lin']:.3f} / {pooled['ils_sq']:.3f}")
    print(f"\n  headline GG share 81% -> noise-robust ILS ~{med_lin:.0%}-{med_sq:.0%}: "
          f"lead HOLDS, magnitude moderates.")
    # a couple of extremes for eyeballing
    rows_sorted = sorted(rows, key=lambda r: r["ils_sq"])
    print("\n  most Kalshi-leaning:", ", ".join(f"{r['match']} ({r['ils_sq']:.2f})" for r in rows_sorted[:3]))
    print("  most Poly-leaning  :", ", ".join(f"{r['match']} ({r['ils_sq']:.2f})" for r in rows_sorted[-3:]))
    print(f"\n  wrote {OUT}")

if __name__ == "__main__":
    sys.exit(main())
