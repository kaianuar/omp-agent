#!/usr/bin/env bash
# =============================================================================
# pipeline_self_test.sh - SELF-TEST of omp-agent's own pipeline logic.
#
# These tests run against omp-agent ONLY (no consumer project scaffold needed)
# and verify the pure, deterministic mechanics of the pipeline. They protect
# against regressions in logic that "we think works" but could fail silently
# inside an omp-driven build (phase extraction, verdict parsing, the issue
# ledger, notes extraction).
#
# Usage:  bash tests/pipeline_self_test.sh     (exit non-zero on any failure)
# =============================================================================
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$HERE/lib"
PASS=0
FAIL=0
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

note()  { printf '%s\n' "$*"; }
ok()    { PASS=$((PASS+1)); printf '  ok   - %s\n' "$*"; }
no()    { FAIL=$((FAIL+1)); printf '  FAIL - %s\n' "$*"; }

# =============================================================================
# 1. Phase extraction from plan.md (must match only "## Phase N:" headings, in
#    order, as single-word tokens PhaseN..PhaseN).
# =============================================================================
note ""
note "## 1. extract_phases"
cat > "$WORK/plan.md" <<'EOF'
# DiskScope Plan

## Phase 1: Domain Core
stuff
## Phase 2: Scan Engine
stuff, mentions Phase 3 risk row (not a heading)
| dependency | Phase 3 -> Phase 2 |   <- table row, must NOT match
## Phase 3: CLI
more
## Phase 4: GUI
## Phase 5: Sync
## Phase 6: Packaging
EOF
phases="$(grep -iE '^#+[[:space:]]+phase[[:space:]]+[0-9]+' "$WORK/plan.md" \
  | sed -E 's/^#+[[:space:]]*//I; s/[[:space:]]*:.*$//I; s/[[:space:]]+$//' \
  | tr '[:upper:]' '[:lower:]' \
  | sort -t' ' -k2 -n | sort -u -k1,1 -k2,2n \
  | while read -r line; do n="$(echo "$line" | sed -E 's/^phase[[:space:]]+//')"; [ -n "$n" ] && echo "Phase$n"; done)"
expected=$'Phase1\nPhase2\nPhase3\nPhase4\nPhase5\nPhase6'
if [ "$phases" = "$expected" ]; then
  ok "extracts exactly 6 headings as Phase1..Phase6, ignores table rows"
else
  no "extract_phases => got: [${phases//$'\n'/ }] want: [${expected//$'\n'/ }]"
fi

# =============================================================================
# 2. Verdict parsing: last bare PASS/FAIL token determines gate outcome.
# =============================================================================
note ""
note "## 2. verdict parsing"
cv() { grep -iE '(^|[^A-Za-z])(PASS|FAIL)([^A-Za-z]|$)' "$1" | tail -1 | grep -oEi 'PASS|FAIL' | tail -1 | tr '[:lower:]' '[:upper:]'; }
printf 'some notes here about a FAIL scenario\n**PASS**\n' > "$WORK/v1"            # final PASS wins
[ "$(cv "$WORK/v1")" = "PASS" ] && ok "final PASS token wins"   || no "final PASS token"
printf 'A FAIL security note\nThen discussion\nFAIL\n' > "$WORK/v2"
[ "$(cv "$WORK/v2")" = "FAIL" ] && ok "final FAIL token wins"   || no "final FAIL token"
printf 'No blockers, everything looks good.\n' > "$WORK/v3"                       # no token
[ -z "$(cv "$WORK/v3")" ] && ok "no token -> empty (undetermined)" || no "no token"

# =============================================================================
# 3. Notes extraction: [P2]/[P3]/[P4] findings captured; P0/P1 not leaked.
# =============================================================================
note ""
note "## 3. notes (P2/P3/P4) extraction"
cat > "$WORK/verdict.txt" <<'EOF'
[P1] The `test_incremental_scan` test has a correctness issue.
[P3] The `ScanConfig` struct Arc allocation cleanliness.
[P4] Minor: rename `is_match` to `matches`.
FINAL: FAIL
EOF
notes="$(grep -E '^\s*\[P[234]\]' "$WORK/verdict.txt")"
if echo "$notes" | grep -q 'P3' && echo "$notes" | grep -q 'P4' && ! echo "$notes" | grep -q 'P1'; then
  ok "P3/P4 extracted, P1 excluded"
else
  no "notes extraction wrong: [$notes]"
fi

# =============================================================================
# 4. Issue ledger transitions (tests/lib/review_ledger.py)
# =============================================================================
note ""
note "## 4. issue ledger (OPEN -> RESOLVED / BACKLOG)"
LED="$WORK/ledger.txt"
PY="$LIB/review_ledger.py"
[ -f "$PY" ] || { no "missing $PY"; exit 1; }

# Round 1: two P1 + one P3 -> both P1 OPEN, P3 BACKLOG
printf '[P1] The `test_incremental_scan` test has a correctness issue.\n[P1] The `test_parallel_scan_respects_gitignore` test is flawed.\n[P3] The `ScanConfig` struct Arc allocation cleanliness.\nFAIL\n' > "$WORK/r1.txt"
python3 "$PY" "$LED" "$WORK/r1.txt"
l1="$(grep -c 'OPEN' "$LED")"; b1="$(grep -c 'BACKLOG' "$LED")"
[ "$l1" -eq 2 ] && [ "$b1" -eq 1 ] && ok "round1: 2 OPEN P1 + 1 BACKLOG P3" || no "round1 ledger wrong: [$(cat "$LED")]"

# Round 2: gitignore re-raised (REPHRASED), incremental fixed (absent)
printf '[P1] The `test_parallel_scan_respects_gitignore` test still has a correctness issue.\nFAIL\n' > "$WORK/r2.txt"
python3 "$PY" "$LED" "$WORK/r2.txt"
if grep -q "OPEN.*gitignore" "$LED" && grep -q "RESOLVED.*incremental" "$LED"; then
  ok "round2: gitignore stays OPEN (rephrased), incremental -> RESOLVED"
else
  no "round2 ledger: [$(cat "$LED")]"
fi

# Round 3: everything fixed (verdict PASS, no findings) -> both RESOLVED
printf 'No P0 or P1 findings. All good.\nPASS\n' > "$WORK/r3.txt"
python3 "$PY" "$LED" "$WORK/r3.txt"
if [ "$(grep -c 'OPEN' "$LED")" -eq 0 ] && [ "$(grep -c 'RESOLVED' "$LED")" -eq 2 ]; then
  ok "round3: both resolved when no findings remain"
else
  no "round3 ledger: [$(cat "$LED")]"
fi

# stable-key: same symbol different wording stays one entry (no dup)
printf '[P1] the `foo` function is broken\nFAIL\n' > "$WORK/r4.txt"
python3 "$PY" "$LED" "$WORK/r4.txt"
n="$(grep -c 'foo' "$LED")"
[ "$n" -le 2 ] && ok "stable key: no duplicate explosion ($n foo refs)" || no "foo duped: [$n]"

# =============================================================================
# summary
# =============================================================================
note ""
note "======================================================"
note " RESULT: $PASS passed, $FAIL failed"
note "======================================================"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
