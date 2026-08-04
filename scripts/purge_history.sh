#!/usr/bin/env bash
# Excise the per-event venue-data paths from the ENTIRE git history.
#
# WHY THIS EXISTS
# ---------------
# `viz/market/leadlag/` and `viz/model/overreaction/` were committed before the .gitignore
# rules covering them existed. They were removed from tracking on 2026-07-28, and a note in
# REPRODUCING.md concluded the data-availability statement was "now true as written".
#
# That conclusion was wrong. Untracking a file removes it from the working tree, not from the
# repository: the blobs stay reachable from earlier commits, so `git clone` still delivers
# them. Audited 2026-08-04 on a fresh clone of the public remote:
#
#     viz/market/leadlag/       27 JSON blobs · 27 matches · 690 per-event records carrying
#                               absolute `t_ms` and `kalshi_reaction`/`poly_reaction` quote
#                               levels · 54 distinct Kalshi tickers · ~834 KB
#     viz/model/overreaction/   24 blobs · per-trade `t_ms` with pre/entry/exit price levels
#
# Both are ancestors of origin/main, so every clone receives them. That is precisely the
# material REPRODUCING.md promises is withheld, and precisely what Kalshi's Developer
# Agreement §3.1 forbids sharing with third parties absent written authorization.
#
# Rewriting history is the only fix. This script does the rewrite and the verification; it
# deliberately does NOT push. Read the whole file before running it.
#
#     bash scripts/purge_history.sh --check     # audit only, changes nothing (default)
#     bash scripts/purge_history.sh --run       # rewrite local history, still does not push
set -euo pipefail

# Two groups, one rewrite. Deleting the ML files in an ordinary commit would leave them
# reachable in history — the precise mistake this script exists to undo — so they are excised
# here instead.
#
#   leadlag / overreaction : per-event venue data (t_ms + quote levels) that the published
#                            data-availability statement says is withheld.
#   ml_microstructure      : a gradient-boosted model trained on pooled Kalshi+Polymarket
#                            order-book features. Kalshi's Data Terms expressly prohibit use
#                            of Kalshi Data for machine learning, including for training. The
#                            result was a reported null (~52% leave-one-match-out on six
#                            matches); the code and write-up are withdrawn regardless.
PATHS=(
  "viz/market/leadlag"
  "viz/model/overreaction"
  "scripts/ml_microstructure.py"
  "writeups/ml-microstructure-note.md"
  "writeups/_ml_micro_results.json"
)

# RESTORE_PATHS are different, and the difference matters. These files must KEEP shipping --
# writeups/_leadlag_results.json is the Tier A artifact every published lead-lag number
# regenerates from -- but their EARLIER revisions predate the redaction in build_leadlag.py and
# still carry per-event t_ms and kalshi_reaction / poly_reaction levels. Audited 2026-08-04:
# 26 revisions of that file exist, ~24 of them unredacted (587 KB vs the current, clean 127 KB).
#
# So a plain --invert-paths is wrong here (it would delete a file the paper depends on) and
# leaving it alone is also wrong (the old revisions leak). The fix is to drop the path from all
# history and then re-commit the current, redacted content as a single new blob.
RESTORE_PATHS=(
  "writeups/_leadlag_results.json"
)
MODE="${1:---check}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

banner() { printf '\n=== %s ===\n' "$1"; }

count_exposure() {
  # PATHS holds both directories and single files, so the pattern must match "<path>/..." AND
  # "<path>" exactly. An earlier version anchored on a trailing slash only and silently
  # reported 0 for every file entry -- a broken check reading as a clean one.
  local total=0 objects
  objects=$(git rev-list --objects --all 2>/dev/null || true)
  for p in "${PATHS[@]}" "${RESTORE_PATHS[@]}"; do
    local n
    n=$(printf '%s\n' "$objects" | grep -cE " ${p//./\\.}(/|\$)" || true)
    printf '  %-38s %4s blob(s) reachable in history\n' "$p" "$n"
    total=$(( total + n ))
  done
  echo "  TOTAL: $total"
  return 0
}

banner "CURRENT EXPOSURE"
count_exposure

if [[ "$MODE" == "--check" ]]; then
  cat <<'EOF'

Check-only mode; nothing was modified. Re-run with --run to rewrite history.

BEFORE YOU RUN IT, IN THIS ORDER — the ordering is not optional:

  1. QUIT every editor and IDE with this repo open, on every machine.
     A previous history rewrite on this repo was silently UNDONE when an editor's
     auto-fetch/auto-pull restored the old objects from its own copy. An editor that
     is open during the rewrite can re-push what you just removed.

  2. Confirm there are no forks. A fork keeps its own copy of every object and GitHub
     cannot purge it for you; if one exists, the rewrite cannot be made complete.
         gh api repos/<owner>/<repo> --jq .forks_count      # must be 0

  3. Make a full backup you can restore from:
         git clone --mirror <remote-url> ../xResidual-backup.git

  4. Install git-filter-repo (do NOT use filter-branch — it is slow, error-prone, and
     leaves replace-refs behind):
         brew install git-filter-repo     # or: pip install git-filter-repo

  5. Run this script with --run, then follow the push instructions it prints.

  6. AFTER pushing, ask GitHub Support to purge cached views. The rewrite removes the
     objects from the repository, but GitHub can still serve an unreferenced blob by its
     SHA through the web UI and API until support runs a server-side gc. Nothing you can
     run locally clears that.

  7. Every existing local clone is now poisoned — it still holds the old objects and will
     happily push them back. Delete and re-clone each one. Do not merge or pull from them.
EOF
  exit 0
fi

if [[ "$MODE" != "--run" ]]; then
  echo "unknown mode: $MODE (expected --check or --run)" >&2
  exit 2
fi

banner "PRECONDITIONS"
command -v git-filter-repo >/dev/null 2>&1 || {
  echo "  FAIL: git-filter-repo not installed (brew install git-filter-repo)" >&2; exit 1; }
echo "  ok: git-filter-repo present"

[[ -z "$(git status --porcelain)" ]] || {
  echo "  FAIL: working tree is dirty — commit or stash first" >&2; exit 1; }
echo "  ok: working tree clean"

echo
read -r -p "Rewrite ALL history in $ROOT, removing ${PATHS[*]}? Type REWRITE to confirm: " ans
[[ "$ans" == "REWRITE" ]] || { echo "aborted."; exit 1; }

banner "PRESERVING CURRENT CONTENT OF RESTORE_PATHS"
STASH="$(mktemp -d)"
for p in "${RESTORE_PATHS[@]}"; do
  if git cat-file -e "HEAD:$p" 2>/dev/null; then
    mkdir -p "$STASH/$(dirname "$p")"
    git show "HEAD:$p" > "$STASH/$p"
    # Refuse to carry a dirty blob across the rewrite -- that would defeat the whole exercise.
    if grep -qE '"(t_ms|kalshi_reaction|poly_reaction)"' "$STASH/$p"; then
      echo "  FAIL: current $p still contains per-event fields; redact it before purging" >&2
      exit 1
    fi
    echo "  saved $p ($(wc -c < "$STASH/$p" | tr -d ' ') bytes, verified clean)"
  fi
done

banner "REWRITING"
ARGS=()
for p in "${PATHS[@]}" "${RESTORE_PATHS[@]}"; do ARGS+=(--path "$p"); done
# --invert-paths: keep everything EXCEPT these. --force: proceed on a non-fresh clone.
git filter-repo "${ARGS[@]}" --invert-paths --force

banner "RESTORING CURRENT CONTENT AS A SINGLE CLEAN BLOB"
for p in "${RESTORE_PATHS[@]}"; do
  [[ -f "$STASH/$p" ]] || continue
  mkdir -p "$(dirname "$p")"
  cp "$STASH/$p" "$p"
  git add -- "$p"
  echo "  restored $p"
done
if ! git diff --cached --quiet; then
  git commit -q -m "Restore redacted Tier A artifacts after history purge

Their pre-redaction revisions carried per-event t_ms and venue quote levels and were
excised with the rest of the per-event data. The current, redacted content is re-committed
here as a single blob so Tier A still reproduces."
  echo "  committed"
fi
rm -rf "$STASH"

banner "POST-REWRITE EXPOSURE (expect 0)"
count_exposure

banner "DEEP VERIFY — scan every surviving blob for quote-level / timestamp fields"
python3 - <<'PY'
import subprocess, collections
raw = subprocess.run(['git','rev-list','--objects','--all'],
                     capture_output=True, text=True).stdout
DANGER = [b'"t_ms"', b'"kalshi_reaction"', b'"poly_reaction"']
hits = collections.Counter()
checked = 0
for line in raw.splitlines():
    part = line.split(' ', 1)
    if len(part) != 2:
        continue
    sha, path = part
    if not (path.endswith('.json') or path.endswith('.js')):
        continue
    blob = subprocess.run(['git','cat-file','-p',sha], capture_output=True).stdout
    checked += 1
    for d in DANGER:
        if d in blob:
            hits[path] += 1
print(f"  scanned {checked} JSON/JS blobs across all history")
if hits:
    print("  !! RESIDUAL EXPOSURE:")
    for p, n in hits.most_common(20):
        print(f"     {p}  ({n})")
    raise SystemExit(1)
print("  CLEAN — no t_ms / kalshi_reaction / poly_reaction in any reachable blob")
PY

cat <<'EOF'

=== NOT YET PUSHED ===

History has been rewritten LOCALLY only. filter-repo also removed the 'origin' remote on
purpose, so you cannot push by reflex. To publish the rewrite:

    git remote add origin <remote-url>
    git push --force --all origin
    git push --force --tags origin

Then, and only then:
  - ask GitHub Support to purge cached views and unreachable objects (step 6 above);
  - delete every other local clone and re-clone;
  - re-verify from a FRESH clone:
        git clone <remote-url> /tmp/verify && cd /tmp/verify
        bash scripts/purge_history.sh --check      # must report TOTAL: 0

Open pull requests created before the rewrite still reference the old commits and will
show as broken. Close and reopen them from freshly-branched work.
EOF
