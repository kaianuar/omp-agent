#!/usr/bin/env bash
# pipeline.sh — the FULLY-AUTOMATED loop: build -> gates -> act-on-findings -> repeat.
#
# This is what makes Gate 2 (adversarial review) genuinely automatic: the critic's
# findings are fed back to the builder automatically, so you never copy-paste.
#
# Loop:
#   round 1 : builder writes code+tests  ->  run-gates.sh (Gate1 tests + Gate2 critic)
#   round 2+: builder gets the critic's FAILING findings + "fix these, re-run gates"
#             ->  run-gates.sh again
#   ... until gates PASS, or MAX_ROUNDS reached (then stop and ask you).
#
# NOTE: omp must be on PATH (e.g. export PATH="$HOME/.bun/bin:$PATH").
set -euo pipefail

BUILDER_MODEL="${BUILDER_MODEL:-xiaomi-token-plan-sgp/mimo-v2.5-pro}"
MAX_ROUNDS="${MAX_ROUNDS:-5}"
FINDINGS_FILE="${FINDINGS_FILE:-/tmp/review_verdict.txt}"

if [ "$#" -ge 1 ]; then
  REQUIREMENTS="$1"   # path to requirements.md
else
  REQUIREMENTS="requirements.md"
fi

echo "==> pipeline.sh: automated loop (builder=${BUILDER_MODEL}, max ${MAX_ROUNDS} rounds)"
echo "    requirements: ${REQUIREMENTS}"

for round in $(seq 1 "$MAX_ROUNDS"); do
  echo ""
  echo "=================================================================="
  echo " ROUND ${round} / ${MAX_ROUNDS}"
  echo "=================================================================="

  # ---- BUILD ----
  echo "==> [build] running builder (omp)..."
  # Round 1: no prior findings. Later rounds: append the critic's findings as the task.
  if [ "$round" -eq 1 ]; then
    omp --print --model "$BUILDER_MODEL" \
        --append-system-prompt=PIPELINE.md \
        --append-system-prompt="$REQUIREMENTS"
  else
    if [ -s "$FINDINGS_FILE" ] && grep -qi 'FAIL' "$FINDINGS_FILE"; then
      echo "==> [build] feeding critic findings to builder ..."
      # Build a consolidated "fix these findings" prompt from the last verdict.
      omp --print --model "$BUILDER_MODEL" \
          --append-system-prompt=PIPELINE.md \
          --append-system-prompt="$REQUIREMENTS" \
          "The adversarial review found the following issues in the last build. Fix each one and re-run ./run-gates.sh. Do not skip any. Findings:
$(cat "$FINDINGS_FILE")"
    else
      echo "==> [build] no prior FAIL findings; continuing build..."
      omp --print --model "$BUILDER_MODEL" \
          --append-system-prompt=PIPELINE.md \
          --append-system-prompt="$REQUIREMENTS"
    fi
  fi

  # ---- GATES (independent critic is a separate process) ----
  echo ""
  echo "==> [gates] run-gates.sh (Gate 1 tests + Gate 2 adversarial review)..."
  set +e
  ./run-gates.sh
  GATE_EC=$?
  set -e

  if [ "$GATE_EC" -eq 0 ]; then
    echo ""
    echo "=================================================================="
    echo " ALL GATES PASSED after ${round} round(s). Proceed to steer/commit."
    echo "=================================================================="
    exit 0
  fi

  echo ""
  echo ">>> Gates failed (round ${round}). See ${FINDINGS_FILE} for the critic's findings."
  echo ">>> Feeding them back to the builder for round $((round+1))."
done

echo ""
echo "!! Reached ${MAX_ROUNDS} rounds without all gates passing. STOPPING for you to review."
echo "   Critic's latest findings are in: ${FINDINGS_FILE}"
echo "   Fix manually or bump MAX_ROUNDS."
exit 1
