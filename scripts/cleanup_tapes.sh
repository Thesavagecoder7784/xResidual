#!/usr/bin/env bash
# Delete capture tapes (ws-events-*.jsonl) ONCE THEY'VE BEEN PROCESSED into the lead-lag pool
# (writeups/_leadlag_results.json), keeping the VM's disk in check over a 72-game tournament
# (~0.5-1.2 GB/game would otherwise fill the 62 GB box).
#
# Safe by construction (the point of this version):
#   - a tape is removed only if its match is present in the pool — i.e. it has been folded in.
#     The OLD version deleted purely by age (>48h), which silently lost tapes the memory guard
#     had deferred past the cutoff (spain-cape-verde, iran-new-zealand were lost this way).
#   - a tape younger than TAPE_KEEP_DAYS is always kept (an in-progress capture has a fresh mtime,
#     so it can never be matched; the floor also leaves time to pull/process).
#   - an aged-but-UNprocessed tape is KEPT and warned, not deleted — until TAPE_HARD_KEEP_DAYS,
#     after which it's force-removed with a loud log line (presumed a low-event game, e.g. a 0-0,
#     that produced no shock pairs and so will never enter the pool). 14 days is ample time to
#     notice the warning and process it by hand if it actually mattered.
#   - if the pool can't be read, the run ABORTS and deletes nothing (never delete blind).
#   - only ws-events-*.jsonl tapes are touched; the tiny ws-pairs-*.jsonl records stay.
#
# Tunables (env): TAPE_DIR, LEADLAG_POOL, TAPE_KEEP_DAYS (floor, default 2),
#                 TAPE_HARD_KEEP_DAYS (backstop, default 14), TAPE_CLEANUP_DRYRUN (set = no deletes).
set -u
PY="${XRES_PY:-/home/azureuser/xResidual/.venv/bin/python}"
exec "$PY" - <<'PYEOF'
import os, re, json, glob, time, subprocess, sys

DIR  = os.environ.get("TAPE_DIR", "/home/azureuser/xResidual/logger/data")
POOL = os.environ.get("LEADLAG_POOL", "/home/azureuser/xResidual/writeups/_leadlag_results.json")
KEEP_DAYS      = float(os.environ.get("TAPE_KEEP_DAYS", "2"))
HARD_KEEP_DAYS = float(os.environ.get("TAPE_HARD_KEEP_DAYS", "14"))
DRY  = bool(os.environ.get("TAPE_CLEANUP_DRYRUN"))
LOG  = os.path.join(DIR, "tape_cleanup.log")

# canonical slug: lowercase, every run of non-alphanumerics (incl. spaces, "&", "vs" separators)
# collapses to a single "-". The Latin range À-ſ keeps accented names (e.g. Curaçao) intact, so
# the pool's "Germany vs Curaçao" and the tape's "...-germany-vs-curaçao.jsonl" both -> the same key.
def canon(s):
    return re.sub(r"-+", "-", re.sub(r"[^0-9a-zÀ-ſ]+", "-", s.lower())).strip("-")

def ts():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def avail():
    try:
        return int(subprocess.check_output(["df", "-BG", "--output=avail", DIR]).split()[-1].decode().rstrip("G"))
    except Exception:
        return -1

def log(*lines):
    with open(LOG, "a") as fh:
        for ln in lines:
            fh.write(ln + "\n")

tag = "tape-cleanup (DRYRUN)" if DRY else "tape-cleanup"

# processed set from the pool; if unreadable or empty, abort — never delete blind.
try:
    d = json.load(open(POOL))
    processed = {canon(p["match"]) for p in d.get("pairs", []) if p.get("match")}
except Exception as e:
    log("%s %s: ABORTED — could not read pool (%s); kept all tapes" % (ts(), tag, e))
    sys.exit(0)
if not processed:
    log("%s %s: ABORTED — pool lists 0 processed matches; kept all tapes" % (ts(), tag))
    sys.exit(0)

now   = time.time()
floor = KEEP_DAYS * 86400
hard  = HARD_KEEP_DAYS * 86400
removed, forced, kept = [], [], []
before = avail()

for f in glob.glob(os.path.join(DIR, "ws-events-*.jsonl")):
    base = os.path.basename(f)
    if (now - os.path.getmtime(f)) < floor:      # too fresh (covers in-progress captures)
        continue
    m = re.match(r"ws-events-[0-9T]+Z-(.*)\.jsonl$", base)
    slug = canon(m.group(1)) if m else ""
    if slug in processed:                        # done with it -> safe to remove
        if not DRY:
            os.remove(f)
        removed.append(base)
    elif (now - os.path.getmtime(f)) > hard:     # unprocessed but ancient -> force, loudly
        if not DRY:
            os.remove(f)
        forced.append(base)
    else:                                        # unprocessed -> KEEP and warn
        kept.append(base)

after = avail()
log("%s %s: removed %d processed, force-removed %d unprocessed(>%gd), kept %d unprocessed; avail %dG -> %dG"
    % (ts(), tag, len(removed), len(forced), HARD_KEEP_DAYS, len(kept), before, after))
for b in removed:
    log("  - " + b)
for b in forced:
    log("  ! FORCED (unprocessed >%gd, presumed low-event): %s" % (HARD_KEEP_DAYS, b))
for b in kept:
    log("  ~ kept (unprocessed, aged past floor — run build_micro_all.py): " + b)
PYEOF
