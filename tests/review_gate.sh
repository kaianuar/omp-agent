#!/usr/bin/env bash
# GATE 2 — adversarial review using a DIFFERENT model than the builder (validated 2026-08-15).
# Builder = Xiaomi mimo-v2.5-pro; Critic = OpenRouter z-ai/glm-5.2 (cheap, top validated model).
set -euo pipefail
cd "$(dirname "$0")/.."

DIFF_FILE="${1:-/tmp/review.diff}"
# Critic model on OpenRouter (validated working). Set high max_tokens — glm-5.2
# is a reasoning model and truncates/returns empty below ~4000 output tokens.
CRITIC_MODEL="${CRITIC_MODEL:-z-ai/glm-5.2}"

echo "==> GATE 2: adversarial review (critic model=${CRITIC_MODEL})"

# Build the diff to review
if [ ! -s "$DIFF_FILE" ]; then
  git add -N . 2>/dev/null || true
  git diff > "$DIFF_FILE"
  if [ ! -s "$DIFF_FILE" ]; then
    echo "!! No changes to review."
    exit 1
  fi
fi
echo "Diff: $(wc -l < "$DIFF_FILE") lines"

# Invoke omp as the critic with the OpenRouter GLM model. On concrete problems it
# exits 1 (gate fails, builder must fix). On PASS exits 0.
omp --model "${CRITIC_MODEL}" \
  "You are the adversarial code reviewer. Below is a diff produced by a builder agent.
Review it harshly for correctness, logic, security, edge cases, and whether tests cover it.
List concrete problems if any, then respond with exactly FAIL; if genuinely correct, PASS.

DIFF:
$(cat "$DIFF_FILE")" \
  | tee /tmp/review_verdict.txt

if grep -qi '^FAIL' /tmp/review_verdict.txt; then
  echo "==> GATE 2: FAIL — sending findings back to builder for iteration."
  exit 1
fi
echo "==> GATE 2: PASS."
exit 0
