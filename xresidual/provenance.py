"""Provenance + staleness for the card pipeline.

Two jobs, both aimed at the staleness bug-class we kept hitting (a card or a writeup
citing numbers an input has since moved past):

  - stamp() captures what produced a render batch — generation time, git commit, model
    params, and fingerprints of the input data — so a card set self-documents and a
    reviewer can tell when (and from what) it was built.
  - inputs_changed_since() compares the current inputs' CONTENT HASHES to the hashes
    recorded in the last build's _provenance.js, and flags any whose content actually
    changed — the "you edited the model/data but the committed cards were built from an
    older version" detector. Content-hash, not mtime, so a touch/checkout that bumps a
    timestamp without changing bytes doesn't cry wolf.

The continuously-updating market snapshots are deliberately NOT part of the baseline
(they refresh every 30 min, which is the daily-refresh's job, not a "forgot to rebuild"
signal)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time

_ISO = "%Y-%m-%dT%H:%M:%SZ"


def _sha8(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()[:8]


def _git_sha(root: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or None
    except Exception:
        return None


def fingerprint(path: str) -> dict | None:
    """{mtime, bytes, sha8} for an input file, or None if missing."""
    if not os.path.exists(path):
        return None
    st = os.stat(path)
    return {"mtime_utc": time.strftime(_ISO, time.gmtime(st.st_mtime)),
            "bytes": st.st_size, "sha8": _sha8(path)}


def stamp(root: str, params: dict | None = None, inputs: dict | None = None) -> dict:
    """A provenance record: when, which commit, which params, and input fingerprints."""
    return {"generated_utc": time.strftime(_ISO, time.gmtime()),
            "git": _git_sha(root),
            "params": params or {},
            "inputs": {k: fingerprint(p) for k, p in (inputs or {}).items()}}


def write_provenance(viz_dir: str, prov: dict) -> str:
    """Write the batch provenance to viz/_provenance.js (window.PROV) for the record."""
    path = os.path.join(viz_dir, "_provenance.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write("window.PROV = " + json.dumps(prov) + ";\n")
    return path


def _read_provenance(viz_dir: str) -> dict | None:
    path = os.path.join(viz_dir, "_provenance.js")
    if not os.path.exists(path):
        return None
    try:
        return json.loads(open(path, encoding="utf-8").read().split("=", 1)[1].rstrip().rstrip(";"))
    except Exception:
        return None


def inputs_changed_since(viz_dir: str, input_paths: dict) -> list[dict]:
    """Inputs whose CONTENT (sha8) differs from what the last build recorded in
    _provenance.js — i.e. the committed cards were built from an older version of that
    input. Returns [{input, was, now}]; empty = cards are built from the current inputs.
    Returns [] if there is no prior provenance to compare against (first build)."""
    prev = _read_provenance(viz_dir)
    if not prev:
        return []
    prev_in = prev.get("inputs", {})
    changed = []
    for name, p in input_paths.items():
        cur = fingerprint(p)
        was = (prev_in.get(name) or {}).get("sha8")
        now = (cur or {}).get("sha8")
        if was is not None and now is not None and was != now:
            changed.append({"input": name, "was": was, "now": now})
    return changed
