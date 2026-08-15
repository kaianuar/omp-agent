#!/usr/bin/env bash
# GATE 2 — adversarial review using a DIFFERENT model than the builder.
# Builder != critic: critic defaults to OpenRouter z-ai/glm-5.2.
#
# Run from the PROJECT ROOT (or give a diff path as $1). Do NOT inline the diff as
# an argv — a large diff exceeds OS arg limits. Instead we write the review prompt
# (with the diff) to a temp file and let omp read it via `@file` (streams from disk).
set -uo pipefail
PROJ_ROOT="$(pwd)"

DIFF_FILE="${1:-/tmp/review.diff}"

# TOKEN / COST NOTES
#  - max_tokens is only a CEILING; the model self-terminates when done, so a higher
#    value does NOT waste tokens on normal short answers. Set it generously (>=4000)
#    so reasoning never starves the answer.
#  - Optional: some reasoning models accept low-thinking to cut tokens; varies by
#    model/provider, user choice (see CONFIG.md).
CRITIC_MODEL="${CRITIC_MODEL:-z-ai/glm-5.2}"

echo "==> GATE 2: adversarial review (critic model=${CRITIC_MODEL})"

if [ ! -s "$DIFF_FILE" ]; then
  echo "!! No diff provided (${DIFF_FILE} empty or missing). Provide it or pass a path."
  exit 1
fi
echo "Diff: $(wc -l < "$DIFF_FILE") lines"

# Build the prompt file (diff streamed from disk, not argv).
PROMPT_FILE="${DIFF_FILE}.prompt.txt"
{
  echo "You are the adversarial code reviewer. A builder agent produced the diff below."
  echo "Review it harshly for correctness, logic, security, edge cases, and test coverage."
  echo "List concrete problems if any, then end with exactly: FAIL"
  echo "If it is genuinely correct with no substantive issues, end with exactly: PASS"
  echo ""
  echo "DIFF:"
  cat "$DIFF_FILE"
} > "$PROMPT_FILE"

echo "Prompt: $(wc -c < "$PROMPT_FILE") bytes -> $PROMPT_FILE"

# Run the critic non-interactively (--print is REQUIRED: without it omp expects a
# TTY and exits/hangs when run from a script). Stream the prompt file.
if ! omp --print --model "${CRITIC_MODEL}" "@${PROMPT_FILE}" 2>&1 | tee /tmp/review_verdict.txt; then
  echo "xx GATE 2 — critic invocation failed."
  exit 1
fi

if grep -qi '^FAIL' /tmp/review_verdict.txt; then
  echo "==> GATE 2: FAIL — sending findings back to builder for iteration."
  exit 1
fi
echo "==> GATE 2: PASS."
exit 0
