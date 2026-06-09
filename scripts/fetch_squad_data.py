#!/usr/bin/env python3
"""Build availability candidates from the official FIFA squads + Transfermarkt values.

Two free, no-key, ToS-clean sources (verified Jun 2026):
  - FIFA official 26-man squad lists (authoritative, current): who is actually selected.
    A notable player NOT in the 26 is unavailable — injury or omission — which is the
    clean, current availability signal (no noisy/stale injury feed needed).
  - salimt/football-datasets (Transfermarkt snapshot, raw on GitHub): per-player market
    value + citizenship + national caps, to value each nation's player pool.

Pipeline: parse the FIFA squads, build each nation's Transfermarkt player pool (current
internationals by value), and diff — a high-value pool player absent from the 26 is a
*candidate* absence. Candidates are written to a REVIEW file, NOT auto-applied: name
matching across the two sources is fuzzy, so a human confirms each before it goes into
squad_values.ABSENCES and the published model.

    python scripts/fetch_squad_data.py            # fetch + write the review file
    python scripts/fetch_squad_data.py --refresh   # re-download the sources

Caches sources under data/cache/. Values are Transfermarkt's snapshot (≈ €m, Oct 2025),
comparable to SQUAD_VALUE's £m scale within FX — fine for an approximate deduction.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import pandas as pd  # noqa: E402
from xresidual import wc2026_teams  # noqa: E402
from squad_values import SQUAD_VALUE  # noqa: E402

CACHE = os.path.join(ROOT, "data", "cache")
REVIEW_MD = os.path.join(ROOT, "data", "availability_review.md")
REVIEW_JSON = os.path.join(ROOT, "data", "availability_review.json")
FIFA_PDF = "https://fdp.fifa.org/assetspublic/ce281/pdf/SquadLists-English.pdf"
TM = "https://raw.githubusercontent.com/salimt/football-datasets/main/datalake/transfermarkt"
TM_FILES = {"profiles": "player_profiles/player_profiles.csv",
            "value": "player_latest_market_value/player_latest_market_value.csv",
            "natperf": "player_national_performances/player_national_performances.csv"}

# FIFA page header "Korea Republic (KOR)" / TM citizenship -> our canonical WC names.
NATION_ALIAS = {
    "korea republic": "South Korea", "ir iran": "Iran", "iran": "Iran",
    "usa": "USA", "united states": "USA", "côte d'ivoire": "Ivory Coast",
    "cote d'ivoire": "Ivory Coast", "czechia": "Czech Republic",
    "türkiye": "Turkey", "turkiye": "Turkey", "cabo verde": "Cape Verde",
    "curacao": "Curaçao", "bosnia and herzegovina": "Bosnia & Herzegovina",
    "dr congo": "DR Congo", "congo dr": "DR Congo",
}
MIN_VALUE_M = 15.0      # floor: ignore minor-value players entirely
TOP_POOL = 26           # the nation's top-N by value form its "expected" pool
TOP_KEY = 6             # within this rank = a key/spine player (a real loss if missing)
BIG_VALUE = 45.0        # ... or any player worth at least this, regardless of rank


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _dedouble(s: str) -> str:
    """FIFA runs LAST-NAME and NAME-ON-SHIRT together ('DEMBELEDEMBELE'); halve a token
    that is an exact doubling so it matches the real surname."""
    n = len(s)
    return s[: n // 2] if n >= 4 and n % 2 == 0 and s[: n // 2] == s[n // 2:] else s


def _name_keys(name: str) -> set:
    """Surname keys for a Transfermarkt name: the last token, and the last two/three
    joined (so multi-word surnames like 'Hadj Moussa' / 'Aït-Nouri' still match FIFA's
    concatenated NAME-ON-SHIRT)."""
    toks = [t for t in re.sub(r"\s*\(\d+\)\s*$", "", str(name)).split() if t]
    keys = set()
    for k in (1, 2, 3):
        if len(toks) >= k:
            j = _norm("".join(toks[-k:]))
            if len(j) >= 3:
                keys.add(j)
    return keys


def _in_squad(name: str, squad_keys: set) -> bool:
    """A TM player is in the squad if any of their surname keys matches a FIFA key
    exactly or by containment (>=5 chars, to absorb the doubling/extra-name noise)."""
    for k in _name_keys(name):
        if k in squad_keys:
            return True
        if len(k) >= 5 and any(k in s or s in k for s in squad_keys if len(s) >= 5):
            return True
    return False


def _canon_nation(raw: str) -> str | None:
    n = re.sub(r"\s*\([A-Z]{3}\)\s*$", "", str(raw)).strip()      # drop "(ALG)"
    key = n.lower()
    if key in NATION_ALIAS:
        return NATION_ALIAS[key]
    c = wc2026_teams.canonical(n)
    return c if c in SQUAD_VALUE else (n if n in SQUAD_VALUE else None)


def download(url: str, path: str, refresh: bool) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if refresh or not os.path.exists(path):
        print(f"  downloading {os.path.basename(path)} ...")
        r = requests.get(url, headers={"User-Agent": "xResidual/1.0"}, timeout=120)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
    return path


def parse_fifa_squads(pdf_path: str) -> dict[str, set]:
    """{canonical nation -> set of normalized surnames in the official 26}."""
    from pypdf import PdfReader
    squads: dict[str, set] = {}
    for page in PdfReader(pdf_path).pages:
        lines = [l for l in (page.extract_text() or "").splitlines() if l.strip()]
        if not lines:
            continue
        nation = _canon_nation(lines[0])
        if nation is None:
            continue
        names = set()
        for l in lines[1:]:
            if not l[:2] in ("GK", "DF", "MF", "FW"):
                continue
            m = re.search(r"\d{2}/\d{2}/\d{4}", l)        # DOB anchors the end of the name
            if not m:
                continue
            blob = l[2:m.start()]
            caps = re.findall(r"[A-ZÀ-Ÿ][A-ZÀ-Ÿ'\- ]+", blob)   # trailing all-caps = surname/shirt
            if caps:
                grp = caps[-1]                              # "LASTNAME(S) NAME-ON-SHIRT"
                names.add(_dedouble(_norm(grp)))            # whole, de-spaced + de-doubled
                for tok in grp.split():                     # and each de-doubled token
                    if len(tok) > 1:
                        names.add(_dedouble(_norm(tok)))
        names.discard("")
        if names:
            squads[nation] = squads.get(nation, set()) | names
    return squads


def build_pool(refresh: bool) -> pd.DataFrame:
    """Per-nation Transfermarkt pool: current internationals with value + caps."""
    prof = pd.read_csv(download(f"{TM}/{TM_FILES['profiles']}",
                                os.path.join(CACHE, "tm_profiles.csv"), refresh),
                       usecols=["player_id", "player_name", "citizenship",
                                "main_position", "current_club_name"])
    val = pd.read_csv(download(f"{TM}/{TM_FILES['value']}",
                               os.path.join(CACHE, "tm_value.csv"), refresh))
    nat = pd.read_csv(download(f"{TM}/{TM_FILES['natperf']}",
                               os.path.join(CACHE, "tm_natperf.csv"), refresh),
                      usecols=["player_id", "matches", "career_state"])
    # latest value per player; infer units (EUR -> millions)
    val = val.sort_values("date_unix").groupby("player_id")["value"].last().reset_index()
    if val["value"].max() > 1e5:
        val["value"] = val["value"] / 1e6
    # current internationals only (drop former), most caps per player
    nat = nat[~nat["career_state"].astype(str).str.contains("FORMER", case=False, na=False)]
    nat = nat.sort_values("matches", ascending=False).groupby("player_id").first().reset_index()
    df = prof.merge(val, on="player_id", how="inner").merge(nat, on="player_id", how="inner")
    df["nation"] = df["citizenship"].map(lambda c: next(
        (_canon_nation(p) for p in str(c).split("/") if _canon_nation(p)), None))
    df = df[df["nation"].notna() & (df["value"] > 0)]
    return df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download sources")
    a = ap.parse_args()

    print("fetching official FIFA squads + Transfermarkt pool ...")
    squads = parse_fifa_squads(download(FIFA_PDF, os.path.join(CACHE, "fifa_squads.pdf"), a.refresh))
    pool = build_pool(a.refresh)
    print(f"  FIFA squads parsed: {len(squads)} nations · TM pool: {len(pool):,} players")

    review = {}
    for nation in sorted(SQUAD_VALUE):
        if nation not in squads:
            continue
        cand = pool[pool["nation"] == nation].nlargest(TOP_POOL, "value").reset_index(drop=True)
        absent = []
        for rank, r in enumerate(cand.itertuples()):
            # only a *key* player missing is a real strength loss: top of the nation's
            # value ranking, or any genuinely big value. Depth omissions (a deep squad
            # leaving out its 18th-best) don't lower effective strength, so skip them.
            key_player = rank < TOP_KEY or r.value >= BIG_VALUE
            if not key_player or r.value < MIN_VALUE_M:
                continue
            if not _in_squad(r.player_name, squads[nation]):         # not in the official 26
                absent.append({"player": re.sub(r"\s*\(\d+\)\s*$", "", str(r.player_name)),
                               "value": round(float(r.value), 1), "caps": int(r.matches),
                               "club": r.current_club_name, "position": r.main_position,
                               "status": "out", "rank_in_nation": rank + 1})
        if absent:
            review[nation] = sorted(absent, key=lambda x: -x["value"])

    with open(REVIEW_JSON, "w", encoding="utf-8") as f:
        json.dump(review, f, indent=2, ensure_ascii=False)
    lines = ["# Availability review — candidate absences (CONFIRM before use)\n",
             "Auto-surfaced: a top-value current international (Transfermarkt) whose surname",
             "was **not matched** in the official FIFA 26-man squad. Fuzzy name-matching means",
             "some are **false positives** (spelling/accents) — verify each against the squad",
             "list and squad news, then paste the real ones into `squad_values.ABSENCES` with a",
             "source. Values are Transfermarkt's snapshot (≈€m, Oct 2025).\n",
             f"_{sum(len(v) for v in review.values())} candidates across {len(review)} nations._\n"]
    for nation, players in sorted(review.items(), key=lambda kv: -max(p["value"] for p in kv[1])):
        lines.append(f"\n## {nation}")
        for p in players:
            lines.append(f"- **{p['player']}** ({p['position']}, {p['caps']} caps) "
                         f"~{p['value']}m · {p['club']}")
    with open(REVIEW_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nwrote {os.path.relpath(REVIEW_MD, ROOT)} and .json "
          f"({sum(len(v) for v in review.values())} candidates, {len(review)} nations)")
    print("Review it, then add confirmed absences to squad_values.ABSENCES.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
