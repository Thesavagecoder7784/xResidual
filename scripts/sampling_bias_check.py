#!/usr/bin/env python3
"""Does the cross-venue lead survive the difference in how the two venues' prices are SAMPLED?

The published Kalshi mid (ws_events.kalshi_mid_series, stream_micro.stream_all) is read from Kalshi's
`ticker` channel. Kalshi documents it as event-driven ("sent whenever any ticker field changes"),
but it is capped at one message per second per market: in the busiest seconds of a match the book
changes 200-380 times while the ticker sends at most one message, and Kalshi's own ts_ms stamps show
the same spacing, so the cap is the publisher's, not the logger's. The Polymarket mid is reconstructed from
that venue's full book stream (~10 ms). Kalshi's `orderbook_delta` stream (~10 ms) was captured but
never used. A price observed only once a second is seen late by construction, so this script measures
how much of the published lead that asymmetry alone produces.

  1. KNOWN-TRUTH PLACEBO (lead-lag, section 5.2). Each event window's real Polymarket path is taken as
     the truth; a synthetic Kalshi is the SAME path shifted by a known true lag and observed only at that
     window's real Kalshi ticker timestamps. The published estimator + gate are run unchanged.
     Control: the same synthetic Kalshi observed at full resolution must recover the true lag.
  2. INFORMATION-SHARE PLACEBO (section 5.2, per surviving raw tape). The published pair_infoshare on:
     G1 published inputs (must reproduce the committed archive), G2 zero-lead placebo, G3 label flip
     (Kalshi's own full book as the truth, a 1 Hz copy as the stale series), G4 both venues at full
     resolution (Kalshi rebuilt from orderbook_snapshot + orderbook_delta).
     A rebuild is only trusted where it agrees with Kalshi's own ticker quote (recon_within_half_cent).

Inputs are WITHHELD (Tier B): per-tick windows in viz/market/leadlag/*.js and raw tapes. The artifact
holds aggregate statistics only. Fork-forward: imports frozen xresidual math, edits nothing there.

    python scripts/sampling_bias_check.py [--tapes ~/xResidual-vm-backup/logger-data]
"""
from __future__ import annotations
import argparse, bisect, glob, json, os, random, statistics as st, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scripts")]
from xresidual import ws_events as we  # noqa: E402
from build_leadlag import MIN_LEAD_CORR, MAX_LEAD_MS  # noqa: E402

OUT = os.path.join(ROOT, "writeups", "_sampling_bias_results.json")
WIN_DIR = os.path.join(ROOT, "viz", "market", "leadlag")
TAPE_CAPS = ["20260718T202817Z-france-vs-england", "20260719T183322Z-spain-vs-argentina"]
SEED = 20260916


def hold(src, stamps):
    """Sample-and-hold `src` onto `stamps`: what a feed publishing only at those instants shows."""
    ts = [x[0] for x in src]; out = []
    for t in stamps:
        i = bisect.bisect_right(ts, t) - 1
        if i >= 0:
            out.append((t, src[i][1]))
    return out


def load_windows():
    wins = []
    for f in sorted(glob.glob(os.path.join(WIN_DIR, "*.js"))):
        s = open(f, encoding="utf-8").read()
        try:
            d = json.loads(s[s.index("{"):].rstrip().rstrip(";"))
        except ValueError:
            continue
        p = [(int(round(t * 1000)), v) for t, v in d["data"]["poly"]]
        k = [(int(round(t * 1000)), v) for t, v in d["data"]["kalshi"]]
        if len(p) > 50 and len(k) > 10:
            wins.append((p, k))
    return wins


def gated_lag(k, p):
    ll = we.lead_lag_ms(k, p, bin_ms=200, max_lag_ms=20000)
    if not ll or ll["best_corr"] < MIN_LEAD_CORR or abs(ll["best_lag_ms"]) > MAX_LEAD_MS:
        return None
    return ll["best_lag_ms"]


def placebo(wins):
    rows = []
    for grid in ("full_resolution", "kalshi_ticker_timestamps"):
        for true_lag in (-1000, -600, -300, 0, 300, 600):
            got = []
            for p, k in wins:
                stamps = [t for t, _ in (p if grid == "full_resolution" else k)]
                r = gated_lag(hold([(t + true_lag, v) for t, v in p], stamps), p)
                if r is not None:
                    got.append(r)
            pos = sum(1 for x in got if x > 0); neg = sum(1 for x in got if x < 0)
            rows.append({"grid": grid, "true_lag_ms": true_lag, "n_gated": len(got),
                         "poly_first": pos, "kalshi_first": neg, "synchronous": len(got) - pos - neg,
                         "median_measured_ms": st.median(got) if got else None,
                         "bias_ms": (st.median(got) - true_lag) if got else None})
    return rows


def rebuild_kalshi_book(path, tickers):
    f = we._f
    yes = {t: {} for t in tickers}; no = {t: {} for t in tickers}
    have = {t: False for t in tickers}; out = {t: [] for t in tickers}

    def best(bk):
        live = [p for p, s in bk.items() if s > 1e-9]
        return max(live) if live else None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if '"kalshi"' not in line or "orderbook_" not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            ty, m, d = e.get("type"), e.get("market"), e.get("data", {})
            if m not in tickers:
                continue
            if ty == "orderbook_snapshot":
                yes[m] = {f(p): f(s) for p, s in d.get("yes_dollars_fp", []) or []}
                no[m] = {f(p): f(s) for p, s in d.get("no_dollars_fp", []) or []}
                have[m] = True
            elif ty == "orderbook_delta" and have[m]:
                p, dl = f(d.get("price_dollars")), f(d.get("delta_fp"))
                if p is None or dl is None:
                    continue
                bk = yes[m] if d.get("side") == "yes" else no[m]
                bk[p] = bk.get(p, 0.0) + dl
            else:
                continue
            bb, nb = best(yes[m]), best(no[m])       # a NO bid at q is a YES ask at 1-q
            if bb is None or nb is None or 1 - nb < bb - 1e-9:
                continue
            mid = (bb + 1 - nb) / 2; s = out[m]
            if not s or s[-1][1] != mid or e["t"] - s[-1][0] > 1000:
                s.append((e["t"], mid))
    return out


def tape_checks(tape_dir):
    import stream_micro as sm
    from build_infoshare import pair_infoshare
    keep = ("gg_a", "hasbrouck_a_lo", "hasbrouck_a_mid", "hasbrouck_a_hi", "cointegrated")
    trim = lambda r: None if r is None else {k: (round(r[k], 4) if isinstance(r.get(k), float) else r.get(k)) for k in keep}
    out = []
    for cap in TAPE_CAPS:
        path = os.path.join(tape_dir, f"ws-events-{cap}.jsonl")
        if not os.path.exists(path):
            continue
        pairs = we.load_pairs(tape_dir, cap)
        b = sm.stream_all(path, pairs)
        tickers = {pr["kalshi"] for pr in pairs if pr.get("kalshi")}
        book = rebuild_kalshi_book(path, tickers)
        slug = cap.split("-", 1)[1]
        arch = os.path.join(ROOT, "viz", "market", "infoshare", slug + ".json")
        committed = {c["label"]: c for c in json.load(open(arch))["contracts"]} if os.path.exists(arch) else {}
        for pr in pairs:
            kt, pa = pr.get("kalshi"), pr.get("poly")
            if not (kt and pa):
                continue
            tick, p, kb = b["k_mid"][kt], b["p_mid"][pa], book[kt]
            stamps = [t for t, _ in tick]
            tb = [x[0] for x in kb]; agree = n = 0
            for t, v in tick:
                i = bisect.bisect_right(tb, t) - 1
                if i >= 0:
                    n += 1; agree += abs(kb[i][1] - v) <= 0.005 + 1e-9
            recon = round(agree / n, 4) if n else None
            g1 = trim(pair_infoshare(tick, p))
            c = committed.get(pr["label"])
            out.append({
                "capture": cap, "contract": pr["label"],
                "kalshi_ticker_median_gap_ms": st.median([b2[0] - a[0] for a, b2 in zip(tick, tick[1:]) if b2[0] > a[0]]),
                "recon_within_half_cent": recon, "rebuild_trusted": bool(recon and recon >= 0.95),
                "G1_published": g1,
                "G1_reproduces_committed": bool(c and g1 and abs(c["gg_a"] - g1["gg_a"]) < 1e-3),
                "G2_zero_lead_placebo": trim(pair_infoshare(hold(p, stamps), p)),
                "G3_label_flip_kalshi_book_as_truth": trim(pair_infoshare(hold(kb, stamps), kb)),
                "G4_both_full_resolution": trim(pair_infoshare(kb, p)) if recon and recon >= 0.95 else None,
            })
            print(json.dumps(out[-1]), flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tapes", default=None, help="raw tape directory (withheld); enables information-share checks")
    a = ap.parse_args()
    random.seed(SEED)
    wins = load_windows()
    if not wins:
        print("no per-tick lead-lag windows (withheld inputs) - nothing to compute")
        return 0
    res = {"n_windows": len(wins), "lead_lag_placebo": placebo(wins),
           "estimator": "ws_events.lead_lag_ms, 200 ms bins, published gate (corr>=%s, |lag|<=%s ms)" % (MIN_LEAD_CORR, MAX_LEAD_MS)}
    for r in res["lead_lag_placebo"]:
        print(r)
    if a.tapes:
        res["infoshare_tapes"] = tape_checks(os.path.expanduser(a.tapes))
    elif os.path.exists(OUT):
        prev = json.load(open(OUT))
        if "infoshare_tapes" in prev:
            res["infoshare_tapes"] = prev["infoshare_tapes"]   # keep the tape section when tapes are absent
    json.dump(res, open(OUT, "w"), indent=1)
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
