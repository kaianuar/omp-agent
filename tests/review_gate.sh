#!/usr/bin/env bash
# GATE 2 — INDEPENDENT adversarial review via a DIFFERENT model.
# Calls OpenRouter directly (NO nested omp), so it's not subject to omp's
# per-command 120s timeout and is fully bulletproof as a separate process.
#
# Verdict: last non-empty line that is exactly "PASS" or "FAIL".
# Run from the project root, or pass a diff path as $1.
#
# CRITIC_STANDARD controls how strict the gate is:
#   production  -> any correctness/security/UX issue = FAIL (must fix).
#                  Accepts no tradeoffs. (DEFAULT)
#   mvp         -> real correctness/security bugs = FAIL; but design/UX/tooling
#                  gaps that are out-of-scope per the requirements become
#                  highlighted NOTES, not FAIL. The gate only blocks on genuine
#                  defects, so an MVP can converge (PASS-with-notes).
# Pass CRITIC_STANDARD=mvp (and CRITIC_REQUIREMENTS=requirements.md) to let the
# critic grade an MVP build without blocking on accepted tradeoffs.
set -uo pipefail
PROJ_ROOT="$(pwd)"

DIFF_FILE="${1:-/tmp/review.diff}"
CRITIC_MODEL="${CRITIC_MODEL:-z-ai/glm-5.2}"        # OpenRouter model id
CRITIC_TIMEOUT="${CRITIC_TIMEOUT:-300}"             # seconds; large diffs need headroom
CRITIC_MAX_TOKENS="${CRITIC_MAX_TOKENS:-16000}"     # high: reasoning models burn tokens thinking and return empty if too low
CRITIC_STANDARD="${CRITIC_STANDARD:-production}"    # production | mvp
CRITIC_REQUIREMENTS="${CRITIC_REQUIREMENTS:-requirements.md}"  # acceptance/scope context
OPENROUTER_URL="https://openrouter.ai/api/v1/chat/completions"

echo "==> GATE 2: adversarial review (critic=${CRITIC_MODEL}, standard=${CRITIC_STANDARD}, timeout=${CRITIC_TIMEOUT}s, max_tokens=${CRITIC_MAX_TOKENS})"

# Load the project's .env — the ONLY env this pipeline reads (per project setup:
# keys live in the repo's .env, not in Hermes's file). This puts OPENROUTER_API_KEY
# etc. into scope whether run via run-gates.sh or directly in omp.
if [ -f "$PROJ_ROOT/.env" ]; then
  set -a; # shellcheck disable=SC1091
  . "$PROJ_ROOT/.env"
  set +a
fi

# OpenRouter key — read from the environment (which we just loaded from .env).
# Do NOT fall back to ~/.hermes/.env: a cloned repo sets up OpenRouter in the
# project's .env, not in Hermes's file.
OR_KEY="${OPENROUTER_API_KEY:-}"
if [ -z "$OR_KEY" ]; then
  echo "xx OPENROUTER_API_KEY not set. Add it to $PROJ_ROOT/.env (the project .env this pipeline reads)."
  exit 1
fi
[ "${REVIEW_DEBUG:-0}" = "1" ] && echo ">> using OPENROUTER_API_KEY from the environment"

if [ ! -s "$DIFF_FILE" ]; then
  echo "!! No diff (${DIFF_FILE} empty). Pass a path to the diff."
  exit 1
fi
echo "Diff: $(wc -l < "$DIFF_FILE") lines ($(wc -c < "$DIFF_FILE") bytes)"

# Optional: load the requirements/scope into the review context so the critic
# knows what's in/out of scope (prevents FAILing on documented MVP exclusions).
REQ_TXT=""
if [ -n "$CRITIC_REQUIREMENTS" ] && [ -f "$CRITIC_REQUIREMENTS" ]; then
  REQ_TXT="$(head -c 8000 "$CRITIC_REQUIREMENTS")"
fi

# Build the JSON request with the review prompt + requirements + diff (max_tokens
# generous for reasoning models; not streamed).
node - "$DIFF_FILE" "$CRITIC_MODEL" "$CRITIC_STANDARD" "$CRITIC_REQUIREMENTS" "$CRITIC_MAX_TOKENS" <<'NODE' > /tmp/review_request.json
const fs=require('fs');
const [ , , diffFile, model, standard, reqFile, maxTokens ]=process.argv;
const diff=fs.readFileSync(diffFile,'utf8');
let req='';
try { req=fs.readFileSync(reqFile,'utf8').slice(0,8000); } catch(e){}
// scope-aware severity instruction
const scope = standard==='mvp'
  ? `GRADING (MVP standard): Use strict judgement. A real correctness or security defect MUST be FAIL.
     Design/UX/tooling issues that the PROJECT REQUIREMENTS explicitly list as out-of-scope are acceptable:
     list them under "NOTES (non-blocking)" and do NOT fail the gate for them.
     If there are no correctness/security defects worth blocking on, your final verdict is PASS (notes may follow).`
  : `GRADING (PRODUCTION standard): This is a production build. Any correctness, security, or UX defect is FAIL.
     No tradeoffs are accepted. Be strict.`;
const prompt=`You are an adversarial code reviewer. A builder produced the diff below.
${scope}

PROJECT REQUIREMENTS / SCOPE (in/out-of-scope context):
${req}

Review the diff harshly for correctness, logic, security, edge cases, and test coverage.
List concrete BLOCKING problems first (each with severity), then any NON-BLOCKING notes.
End your reply with a SINGLE final line that is exactly PASS or FAIL.

DIFF:
${diff}`;
process.stdout.write(JSON.stringify({
  model,
  messages:[{role:'user',content:prompt}],
  max_tokens:Number(maxTokens||16000),
  temperature:0.2
}));
NODE

echo "Request bytes: $(wc -c < /tmp/review_request.json)"

# POST to OpenRouter with an explicit generous timeout.
curl -sS --max-time "${CRITIC_TIMEOUT}" \
  -X POST "$OPENROUTER_URL" \
  -H "Authorization: Bearer ${OR_KEY}" \
  -H "Content-Type: application/json" \
  -H "HTTP-Referer: http://localhost" \
  -H "X-Title: omp-agent" \
  --data @/tmp/review_request.json > /tmp/review_response.json
CURL_EC=$?

if [ "$CURL_EC" -ne 0 ]; then
  echo "xx Critic request failed/aborted (curl exit ${CURL_EC}). Increase CRITIC_TIMEOUT if it timed out."
  exit 1
fi

# Extract the assistant content and print it (for the log + verdict).
node - <<'NODE' > /tmp/review_verdict.txt
const fs=require('fs');
let d;
try { d=JSON.parse(fs.readFileSync('/tmp/review_response.json','utf8')); }
catch(e){ console.log('RESPONSE-ERROR: '+e.message); process.exit(1); }
if(d.error){ console.log('API-ERROR: '+JSON.stringify(d.error)); process.exit(1); }
const content=(d.choices?.[0]?.message?.content)||'(empty)';
console.log(content);
NODE
RC=$?

if [ "$RC" -ne 0 ]; then
  echo "xx Could not parse critic response (see /tmp/review_response.json)."
  exit 1
fi

# Verdict: scan the LAST occurrence of a line containing a bare PASS/FAIL token.
# Loosen so `PASS`, `PASS.`, `**PASS**`, "PASS (see notes)" all match — but anchor on
# the final line(s) so a mid-text "FAIL" mention doesn't override a final PASS.
# Only a token that is PASS or FAIL (case-insensitive) counts; nothing else.
VERDICT="$(grep -iE '(^|[^A-Za-z])(PASS|FAIL)([^A-Za-z]|$)' /tmp/review_verdict.txt | tail -1 | grep -oEi 'PASS|FAIL' | tail -1 | tr '[:lower:]' '[:upper:]')"

echo "---- critic verdict ----"
echo "(last verdict token: ${VERDICT:-<none>})"
echo "------------------------"

if [ "$VERDICT" = "FAIL" ]; then
  echo "==> GATE 2: FAIL — blocking findings fed back to builder (see /tmp/review_verdict.txt)."
  exit 1
fi
if [ "$VERDICT" = "PASS" ]; then
  echo "==> GATE 2: PASS${CRITIC_STANDARD:+, standard=${CRITIC_STANDARD}}. Non-blocking notes, if any, are in /tmp/review_verdict.txt."
  exit 0
fi
echo "xx No clear PASS/FAIL verdict found in critic output."
exit 1
