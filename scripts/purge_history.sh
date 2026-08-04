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

# Three groups, one rewrite. Deleting any of these in an ordinary commit would leave them
# reachable in history — the precise mistake this script exists to undo — so they are excised
# here instead.
#
#   leadlag / overreaction : per-event venue data (t_ms + quote levels) that the published
#                            data-availability statement says is withheld.
#   paper book backups     : three .bak copies of the paper-trading ledger. Three of its rows
#                            are Kalshi positions carrying a market ticker, entry/exit quote
#                            levels and a share count that divides straight back into the
#                            entry price — the same class of per-event venue data as leadlag.
#                            The 2026-08-04 audit missed them because it swept viz/, not
#                            paper/. The live ledger and book.md are redacted in place and
#                            re-committed clean (RESTORE_PATHS); the .bak copies have no
#                            value and are dropped outright.
#   ml_microstructure      : a gradient-boosted model trained on pooled Kalshi+Polymarket
#                            order-book features. Two documents bear on this and it is worth
#                            being exact about which one applies. Kalshi's Data Terms of Use
#                            §II prohibit use of Kalshi Data "in any manner for any machine
#                            learning and/or artificial intelligence" — but that document is
#                            scoped to content on the kalshi.com website, and these tapes came
#                            off the WebSocket API. The API is governed by the Developer
#                            Agreement, which carries no ML clause; there the operative bar is
#                            §3 ("use of Kalshi APIs is expressly limited to facilitating a
#                            member's own trading") and §3.1 (no collecting or storing except
#                            to facilitate your own trading). Either route forbids it. The
#                            result was a reported null (~52% leave-one-match-out on six
#                            matches); the code and write-up are withdrawn regardless.
PATHS=(
  "viz/market/leadlag"
  "viz/model/overreaction"
  "paper/positions.json.bak"
  "paper/positions.json.bak2"
  "paper/positions.json.bak3"
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
#
# paper/positions.json and paper/book.md are here for the same reason: the ledger is the record
# behind the paper-trading result and has to keep shipping, but every earlier revision carries
# the unredacted Kalshi rows.
RESTORE_PATHS=(
  "writeups/_leadlag_results.json"
  "paper/positions.json"
  "paper/book.md"
)
MODE="${1:---check}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

banner() { printf '\n=== %s ===\n' "$1"; }

# What counts as a dirty blob differs by file, and collapsing that into one pattern gets it
# wrong in both directions. A bare Kalshi ticker is a contract identifier, not a quote, and
# writeups/_leadlag_results.json deliberately keeps its tickers so the venue pairing stays
# auditable — a blanket ticker ban would fail a file that is already clean. The paper ledger is
# the opposite case: its redaction removes the ticker entirely, so a surviving ticker there
# means the redaction did not run. Note the limit of that check: it catches the redaction being
# reverted, not a brand-new untickered Kalshi row carrying a price. The Polymarket rows keep
# their numeric prices on purpose — those are on-chain-derived, not Kalshi Data.
danger_pattern_for() {
  case "$1" in
    paper/positions.json|paper/book.md) printf '%s' 'KXWC|KXWORLD' ;;
    *)                                  printf '%s' '"(t_ms|kalshi_reaction|poly_reaction)"' ;;
  esac
}

# The two groups have DIFFERENT success criteria and an earlier version of this script summed
# them into one "TOTAL" it told you to expect at 0. That total can never be 0 after a correct
# run: each RESTORE_PATH is deliberately re-committed as one clean blob, so a perfect rewrite
# scores 0 for PATHS and exactly 1 for each restored file. Reporting a single number meant the
# documented success condition was unreachable, and a reader who followed it would have read a
# correct purge as a failed one. PURGED_TOTAL / RESTORED_TOTAL are set here for the caller to
# assert on.
PURGED_TOTAL=0
RESTORED_TOTAL=0
count_exposure() {
  # PATHS holds both directories and single files, so the pattern must match "<path>/..." AND
  # "<path>" exactly. An earlier version anchored on a trailing slash only and silently
  # reported 0 for every file entry -- a broken check reading as a clean one.
  local objects n
  objects=$(git rev-list --objects --all 2>/dev/null || true)
  PURGED_TOTAL=0
  RESTORED_TOTAL=0
  echo "  purged outright (must reach 0):"
  for p in "${PATHS[@]}"; do
    n=$(printf '%s\n' "$objects" | grep -cE " ${p//./\\.}(/|\$)" || true)
    printf '    %-38s %4s blob(s) reachable in history\n' "$p" "$n"
    PURGED_TOTAL=$(( PURGED_TOTAL + n ))
  done
  echo "  purged then re-committed redacted (must reach 1 each):"
  for p in "${RESTORE_PATHS[@]}"; do
    n=$(printf '%s\n' "$objects" | grep -cE " ${p//./\\.}(/|\$)" || true)
    printf '    %-38s %4s blob(s) reachable in history\n' "$p" "$n"
    RESTORED_TOTAL=$(( RESTORED_TOTAL + n ))
  done
  echo "  PURGED_TOTAL: $PURGED_TOTAL   (target 0)"
  echo "  RESTORED_TOTAL: $RESTORED_TOTAL   (target ${#RESTORE_PATHS[@]})"
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
    if grep -qE "$(danger_pattern_for "$p")" "$STASH/$p"; then
      echo "  FAIL: current $p still contains per-event venue fields; redact it before purging" >&2
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

banner "POST-REWRITE EXPOSURE"
count_exposure
# Assert, do not merely print. The previous version reported these numbers and then carried on
# to the success banner regardless of what they said -- so a rewrite that silently purged
# nothing would still have ended with "CLEAN" on screen.
if (( PURGED_TOTAL != 0 )); then
  echo "  FAIL: $PURGED_TOTAL blob(s) of purged paths still reachable" >&2
  exit 1
fi
if (( RESTORED_TOTAL != ${#RESTORE_PATHS[@]} )); then
  echo "  FAIL: expected ${#RESTORE_PATHS[@]} restored blob(s), found $RESTORED_TOTAL" >&2
  echo "        (fewer means a Tier A artifact the paper depends on was dropped;" >&2
  echo "         more means an old revision survived the rewrite)" >&2
  exit 1
fi
echo "  ok: purged paths gone, ${#RESTORE_PATHS[@]} redacted blob(s) restored"

banner "DEEP VERIFY — scan every surviving blob for quote-level / timestamp fields"
python3 - <<'PY'
import subprocess, collections
raw = subprocess.run(['git','rev-list','--objects','--all'],
                     capture_output=True, text=True).stdout
DANGER = [b'"t_ms"', b'"kalshi_reaction"', b'"poly_reaction"']
# Scoped to paper/ on purpose: a Kalshi ticker is fine in _leadlag_results.json and in the
# infoshare archives, where it identifies a contract and nothing else. In the paper ledger it
# travels next to an entry price, which is why the ledger is redacted rather than kept.
PAPER_DANGER = [b'KXWC', b'KXWORLD']
hits = collections.Counter()
checked = 0
want = []
for line in raw.splitlines():
    part = line.split(' ', 1)
    if len(part) != 2:
        continue
    sha, path = part
    # paper/watchlist.md is the deliberate exception: it lists tickers for markets the venue
    # had not quoted yet ("no bid/ask/last"), so it carries model views and no venue data.
    paper = path.startswith('paper/') and not path.startswith('paper/watchlist')
    if not (path.endswith('.json') or path.endswith('.js') or paper):
        continue
    want.append((sha, path, paper))

# One long-lived `cat-file --batch` rather than one subprocess per blob. The per-blob version
# took 5-10 minutes on this repo's ~9k text blobs -- long enough to look hung, and a verify
# people interrupt is a verify that never runs.
proc = subprocess.Popen(['git', 'cat-file', '--batch'],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE)
for sha, path, paper in want:
    proc.stdin.write((sha + '\n').encode())
    proc.stdin.flush()
    header = proc.stdout.readline().split()
    if len(header) < 3:
        continue
    blob = proc.stdout.read(int(header[2]))
    proc.stdout.read(1)          # trailing newline after the object payload
    if header[1] != b'blob':
        continue
    checked += 1
    for d in (DANGER + PAPER_DANGER if paper else DANGER):
        if d in blob:
            hits[path] += 1
proc.stdin.close()
proc.wait()
print(f"  scanned {checked} JSON/JS and paper/ blobs across all history")
if hits:
    print("  !! RESIDUAL EXPOSURE:")
    for p, n in hits.most_common(20):
        print(f"     {p}  ({n})")
    raise SystemExit(1)
print("  CLEAN — no t_ms / kalshi_reaction / poly_reaction in any reachable blob,")
print("          and no Kalshi ticker under paper/")
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
        bash scripts/purge_history.sh --check
    A correct rewrite reports PURGED_TOTAL: 0 and RESTORED_TOTAL equal to the number of
    RESTORE_PATHS (one clean blob each). RESTORED_TOTAL of 0 is NOT a better result -- it
    means an artifact the paper reproduces from is missing.

Open pull requests created before the rewrite still reference the old commits and will
show as broken. Close and reopen them from freshly-branched work.
EOF
