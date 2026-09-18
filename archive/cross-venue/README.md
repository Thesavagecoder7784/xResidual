# Cross-venue lead-lag — withdrawn 2026-09-18

**Read [CORRECTION.md](../../CORRECTION.md) before anything in this folder.**

These documents claim that Polymarket reprices World Cup goals about 600 ms before Kalshi, with an
81% information share. That claim is withdrawn. Kalshi's price was read from a channel capped at one
message per second while Polymarket's was read from its full order book, and a market with no lead at
all, observed the same way, reproduces the published result.

The files are kept unchanged, as a record of what was claimed and how:

| File | What it is |
|---|---|
| `price_discovery_note.pdf` / `.html` | The four-page desk note |
| `cross-venue-price-discovery.md` | The full price-discovery writeup |
| `blog_post.md` | The blog version |
| `ssrn_paper.md` | The SSRN draft |
| `pre-registration.md` | The microstructure pre-registration of 2026-06-14. Byte-identical to its original commit |
| `onchain-signed-flow-spec.md` | A build spec for follow-on research that assumed the lead was real |

The code that produced these numbers stays in `scripts/` and `xresidual/`, because the tests that
overturned them run on it: [`scripts/sampling_bias_check.py`](../../scripts/sampling_bias_check.py),
[`scripts/matched_sampling_depth.py`](../../scripts/matched_sampling_depth.py) and
[`scripts/lead_deconvolution.py`](../../scripts/lead_deconvolution.py). What survives, and why, is in
[`writeups/recovery-audit.md`](../../writeups/recovery-audit.md).
