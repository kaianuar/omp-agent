#!/usr/bin/env bash
# ----------------------------------------
# omp-agent factory — scaffold a new project
# Usage: ./scaffold.sh <new-project-dir> [--ui] [--no-git]
#   <new-project-dir>  destination (absolute or relative)
#   --ui               also copy design-system/ tokens (Req 3 UI consistency)
#   --no-git           skip `git init`
# ----------------------------------------
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-}"
FLAG_UI=false
FLAG_GIT=true

for a in "$@"; do
  case "$a" in
    --ui) FLAG_UI=true ;;
    --no-git) FLAG_GIT=false ;;
  esac
done

if [ -z "$DEST" ]; then
  echo "Usage: $0 <new-project-dir> [--ui] [--no-git]"
  exit 1
fi
if [ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
  echo "!! Destination not empty: $DEST"
  exit 1
fi

mkdir -p "$DEST"
cd "$DEST"

echo "==> Scaffolding into $DEST"

# --- Copy reusable pipeline files ---
cp "$SRC/PIPELINE.md" .
cp "$SRC/README.md" .
cp "$SRC/CONFIG.md" .
cp "$SRC/.gitignore" .

# --- Project-specific: requirements template + tests + hard-gate runner ---
cp "$SRC/requirements.md" .
mkdir -p tests
cp "$SRC/tests/gate.sh" tests/
cp "$SRC/tests/review_gate.sh" tests/
cp "$SRC/tests/visual_gate.sh" tests/
chmod +x tests/*.sh
# Playwright e2e template + config (for GATE 3 visual/functional e2e)
mkdir -p tests/e2e
cp "$SRC/tests/e2e/_example.spec.ts" tests/e2e/
cp "$SRC/tests/e2e/playwright.config.ts" tests/e2e/
# The hard, non-skippable dual-gate runner (GATE 1 tests + GATE 2 adversarial review)
cp "$SRC/run-gates.sh" .
chmod +x run-gates.sh
# The fully-automated orchestrator (build -> gates -> feed findings back -> loop)
cp "$SRC/pipeline.sh" .
chmod +x pipeline.sh

# --- omp project config (wired to the user's REAL modelRoles) ---
mkdir -p .omp
cp "$SRC/.omp/config.yml" .omp/

# --- UI tokens (only with --ui) ---
if $FLAG_UI; then
  mkdir -p design-system
  cp "$SRC/design-system/tokens.json" design-system/
  echo "   (design-system/ included)"
else
  echo "   (no design-system/ — re-run with --ui to include UI tokens)"
fi

# --- git init ---
if $FLAG_GIT; then
  git init -q && echo "   git initialized"
  echo "   next: edit requirements.md, then run: omp"
fi

echo ""
echo "==> Done. Structure:"
find . -type f | sort
echo ""
echo "Next steps:"
echo "  1. Edit requirements.md with your goal"
echo "  2. Run: omp   (in $DEST) — PIPELINE.md drives the loop (tests auto-detect your stack)"
