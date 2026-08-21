# The Orchestrator Brain — Detailed Design

Companion to PRODUCT_SPEC.md. Drafted 2026-08-21. This is the cognitive core:
the state machine, context layer, artifacts, templates, and escalation rules
that make the orchestrator actually steer the builder well.

**Principle: the brain is a SYSTEM, not a model.** A great model with no
system flails (DS Flash did nothing for 15 min). An average model with a great
system ships PRs (MiMo shipped 4 features cleanly this week). 30% model,
70% system.

---

## 1. The Orchestrator State Machine

The orchestrator is NOT free-form chat. It is a stateful agent with explicit
phases. Each phase has: goal, inputs, outputs (artifacts), exit criteria, and
allowed tools. The user can interrupt at defined checkpoints.

```
        ┌────────────┐
        │   IDLE     │ ← waiting for user input
        └─────┬──────┘
              │ user message (feedback / idea / bug / question)
              ▼
        ┌────────────┐      need more info?
        │  INTAKE    │ ───────────────────────────────┐
        └─────┬──────┘                                │
              │ intent extracted                      │ ask user (clarify)
              ▼                                       │
        ┌────────────┐                                │
        │  RESEARCH  │ ← web search, vision, read     │
        └─────┬──────┘   code, compare approaches     │
              │                                      ▼
              ▼                              ┌──────────────┐
        ┌────────────┐                      │ (back to user│
        │   DESIGN   │ ← produce design doc  │  in IDLE)   │
        └─────┬──────┘                      └──────────────┘
              │
              ▼
     ╔══════════════════════╗
     ║ CHECKPOINT 1: DESIGN ║ ← USER approves / adjusts / rejects
     ╚══════════════════════╝    (THE design checkpoint)
              │ approved
              ▼
        ┌────────────┐
        │   RECIPE   │ ← design → builder-ready recipe
        └─────┬──────┘
              ▼
     ╔══════════════════════╗
     ║ CHECKPOINT 2: RECIPE ║ ← optional: show recipe to user
     ╚══════════════════════╝    (fast path: skip if design was clear)
              │
              ▼
        ┌────────────┐
        │  BUILD     │ ← dispatch to builder (omp) with recipe
        └─────┬──────┘    monitor for stalls / errors
              │
              ▼
        ┌────────────┐
        │  REVIEW    │ ← critic (read-only) reviews diff → P0–P4
        └─────┬──────┘
              │
              ▼
        ┌────────────┐
        │  VERIFY    │ ← orchestrator runs tests / smoke itself
        └─────┬──────┘    (writes proof to scratch if needed)
              │
              ▼
     ╔══════════════════════╗
     ║ CHECKPOINT 3: RESULT ║ ← user sees summary + PR link
     ╚══════════════════════╝    approves → merge; or requests change
              │
              ▼
        ┌────────────┐
        │  REPORT    │ ← plain-language summary + next steps
        └─────┬──────┘
              ▼
           IDLE
```

### Phase details

**IDLE**
- Goal: wait for user.
- No tools. State: project bound, context pack loaded, ready.

**INTAKE**
- Goal: extract intent from raw user message. Output: `Intent` object.
- Intent fields:
  - `kind`: `feature` | `bugfix` | `idea` | `question` | `feedback-on-existing`
  - `goal`: what the user wants to happen (one sentence)
  - `constraints`: explicit limits (platform, perf, "don't touch X")
  - `acceptance`: how we'd know it's done (if stated)
  - `urgency`: now | this session | backlog
  - `uncertainty`: what's ambiguous → list of clarifying questions
- Exit: if `uncertainty` is non-empty → ask user (clarify), loop back to
  INTAKE. Else → RESEARCH.
- Rule: NEVER skip clarify when the feature touches core behavior or delete
  semantics. Better to ask once than build the wrong thing.

**RESEARCH**
- Goal: ground the intent in reality. Output: `ResearchNotes` (scratch file).
- Actions (parallel where possible):
  - Read the relevant code (grep for the touched modules, read AGENTS.md,
    read the backlogs).
  - Web search: "how do other tools do X" (only when the design would benefit
    — not for routine changes).
  - Vision: if the user sent a screenshot/mockup, analyze it.
  - Check known limitations list ("do not fix without sign-off").
- Exit: research notes written to scratch; DESIGN.
- Rule: research is read-only. Never propose changes before understanding the
  current state. (Anti-pattern: designing against a hallucinated codebase.)

**DESIGN**
- Goal: produce the DESIGN DOC — a decision document, not an implementation
  plan. Output: `design.md` (scratch, shown to user).
- Design doc structure (TEMPLATE):
  ```
  # Design: <title>
  ## Context (2-4 sentences: what exists, what problem)
  ## Options considered (2-4, with tradeoffs)
  ## Decision (the chosen option + why, in one paragraph)
  ## Scope (what changes: files/areas touched — NOT line-level yet)
  ## Edge cases & risks (what could go wrong, how handled)
  ## Open questions (things the user must decide)
  ## Effort estimate (S/M/L + rough omp sessions)
  ```
- Exit: design doc written → CHECKPOINT 1 (user).
- Rule: the design doc is the USER'S checkpoint. They own vision. Never
  proceed to recipe without approval for anything beyond a trivial fix.

**RECIPE**
- Goal: translate approved design into a builder-ready spec. Output: `recipe.md`
  (scratch, handed to builder verbatim).
- Recipe structure (TEMPLATE — this is the proven artifact):
  ```
  # Recipe: <title>
  ## Workflow requirements (FIRST):
    - branch off main: `git checkout main && git pull && git checkout -b <branch>`
    - incremental commits (one logical change = one commit, conventional msgs)
    - finish: push + `gh pr create`
  ## Architecture context (what the builder must know: crate layout, patterns,
    serde-mirror, lint rules — condensed from AGENTS.md + design doc)
  ## Implementation (STEP 1..N):
    ### Step N (commit: <type>(<scope>): <msg>)
    - EXACT file path(s)
    - EXACT change: what to add/change (signatures, structs, function names)
    - Where to register (invoke_handler, exports, routes)
    - Test requirements (which tests to write, naming convention)
  ## Verify before pushing:
    - fmt / clippy / test commands (exact)
    - Manual verification steps (exact commands)
    - Test counts expected (so the builder knows what "pass" means)
  ```
- The recipe is the SINGLE source of truth for the builder. No ambiguity:
  if the builder has to "figure out" something, the recipe failed.
- Exit: recipe written → CHECKPOINT 2 (optional user review; fast path skips).

**BUILD**
- Goal: dispatch recipe to builder, monitor, ensure completion.
- Actions:
  - Invoke builder: `omp --model <builder> --append-system-prompt="$(cat recipe)" "<instruction>"`
  - Monitor: check process alive, check git log/status periodically.
  - Stall detection: if no file writes + no commits for N minutes (10-15),
    intervene: kill + re-dispatch with a narrowed recipe, OR finish manually.
  - Timeout handling: builder may hit the 420s terminal cap — re-check process
    survival, don't assume death.
- Exit: builder reports done (PR created) OR build failed (fix round).
- Rule: NEVER trust the builder's self-report. Always VERIFY after.

**REVIEW**
- Goal: critic reviews the diff (read-only). Output: `verdicts` (P0-P4).
- P0 = must fix, blocks merge (security, data loss, crash)
- P1 = should fix before merge (correctness, broken behavior)
- P2 = should fix, not blocking (quality, edge case)
- P3 = nice to have (style, perf)
- P4 = minor / UI nit
- P0/P1 → dispatch FIX round (loop back to RECIPE with the verdicts as
  context; "PRESERVE all existing code" in the fix prompt).
- P2+ → surface to user at CHECKPOINT 3 as non-blocking notes.
- Deletion guard: `git diff --diff-filter=D` — any deleted source files is
  auto-P0 unless the design explicitly called for the deletion.
- Exit: verdicts → VERIFY (if no P0/P1) or → RECIPE (fix round).

**VERIFY**
- Goal: orchestrator independently confirms the change works.
- Actions (never trust builder self-report):
  - Run the exact verify commands from the recipe (fmt/clippy/tests).
  - Run a behavioral smoke check if the change is user-visible (the Gate 1.5
    pattern: a deterministic check against real behavior, not the builder's
    own tests).
  - Write validation evidence to scratch if needed: a small test to /tmp that
    proves the fix, run it, attach output to the report.
  - Manual GUI check if the change is visual (or vision-analyze a screenshot
    the user takes).
- Exit: verified → CHECKPOINT 3. Failed verification → RECIPE (fix round with
  the failing evidence).

**REPORT**
- Goal: plain-language summary. Output: report (to user, and persisted).
- Report structure:
  ```
  ## What changed (2-3 sentences, no jargon)
  ## Verification (what I ran, what passed)
  ## PR link / artifacts
  ## Non-blocking notes (P2+ verdicts, flagged for later)
  ## Suggested next (what could follow, if relevant)
  ```
- Exit: → IDLE.

### Interruptions (user can break in at any point)
- During INTAKE/RESEARCH/DESIGN: user refines the request → re-enter at the
  appropriate phase.
- At CHECKPOINT 1 (design): approve / adjust (edits to design doc) / reject.
- At CHECKPOINT 3 (result): merge / request change (→ RECIPE with feedback).
- Mid-BUILD: user says "stop" → kill builder, keep partial work if committed,
  return to IDLE with a status note.

---

## 2. The Context Pack (what the brain knows)

The orchestrator needs a curated context pack per project, refreshed at
session start and updated as work completes. This is the "memory" that makes
a stateless model behave like it has worked here before.

### Layers

**L0 — Project Charter (static, hand-authored)**
- What the product is, its differentiator, target users.
- Architecture overview (crates/modules/components).
- Conventions (code style, TDD mandate, commit rules).
- Known limitations ("do not fix without sign-off").
- → This is AGENTS.md + a product one-pager. Loaded always.

**L1 — Project State (semi-static, updated per session)**
- Backlogs: UI_BACKLOG.md, FEATURE_BACKLOG.md (what's planned, priorities).
- Design docs: DUPES_UI_DESIGN.md etc (decisions made, why).
- Current branch/PR state: what's merged, what's in flight.
- → Refreshed at session start. Loaded always (condensed).

**L2 — Work History (dynamic, appended per task)**
- Every task: intent → design → recipe → verdicts → outcome.
- Kept as a running log (or per-task files in a `sessions/` dir).
- Used for: not re-litigating settled decisions, learning what the user
  prefers, catching regressions ("we fixed this before").
- → Loaded on-demand (searchable), recent N entries always in context.

**L3 — User Preferences (cross-project)**
- Tone: plain, concrete, no hype (the user's voice rules).
- Style: incremental commits, TDD, evidence over opinion.
- Cost: cheapest viable model, watch spend.
- → Global, always loaded (small).

### Context pack assembly (per session)
```
1. Load L0 (AGENTS.md + product one-pager)
2. Load L1 (backlogs + design docs — condensed to relevant sections)
3. Load L3 (preferences)
4. L2: search for anything related to the incoming request; if found, load.
5. Assemble into a single "session brief" injected into the orchestrator
   prompt (or retrieved on-demand via a memory tool).
```

---

## 3. Templates (the accumulated craft)

The recipes that worked weren't magic — they followed a repeatable pattern.
The brain uses templates, not improvisation. Templates live in
`omp-agent/templates/` and are parameterized per task.

### Recipe template (full) — see RECIPE phase above.
### Design doc template — see DESIGN phase above.
### Clarify questions template
- "When you say X, do you mean A or B?"
- "Is this for all platforms or Linux-first?"
- "Should it be undoable / go to trash?"
- "Is this P1 (build now) or backlog?"
### Verification checklist template
- [ ] tsc / build / tests pass (exact commands)
- [ ] behavioral smoke check passed (what it proved)
- [ ] clippy/fmt/lint clean
- [ ] manual GUI check (if visual)
- [ ] no deleted source files (deletion guard)
- [ ] branch + PR created, CI green

---

## 4. Escalation Rules (when to stop and ask the human)

The brain must know when NOT to be autonomous:

1. **New feature with design tradeoffs** → always CHECKPOINT 1 (design approval).
2. **Anything touching "known limitations, do not fix without sign-off"** →
   ask before touching.
3. **Delete / destructive semantics** → design must state the delete path
   (trash? permanent?) and get approval.
4. **Breaking changes / API changes** → design checkpoint.
5. **Cost decisions** → large builds, expensive models, long sessions →
   inform user before spending.
6. **Ambiguity in intent** → clarify (never guess on core behavior).
7. **Builder stalls repeatedly** → stop, reassess approach, tell user
   (don't burn tokens looping).
8. **Critic P0/P1 with unclear fix** → ask user whether to fix-round or defer.

---

## 5. Failure Handling

| Failure | Detection | Response |
|---|---|---|
| Builder stalls (no writes) | periodic git status/process check | kill, narrow recipe, re-dispatch; if 2nd stall → tell user |
| Builder self-report false | VERIFY always runs | fix round with evidence |
| Critic deadlock (P1 re-flagged forever) | same verdict >2 rounds | escalate to user with both sides |
| Recipe rejected by builder (API error) | error code | SKIP_BUILD_ROUND, rewrite recipe |
| Tests flaky | rerun | isolate, mark, don't chase |
| User changes mind mid-build | interrupt | keep committed work, return to IDLE |

---

## 6. Model Choice (the open question, refined)

The orchestrator does the HARDER cognition than the builder:
- Long context (design docs + recipes are long)
- Multi-step reasoning (design tradeoffs, P1-vs-P3 calls)
- Tool-calling reliability (web, vision, read, run — constant)
- Conversational quality (talks to the user)

Recommendation: **orchestrator model ≥ builder model in reasoning**, even if
slower/more expensive — it runs once per task, the builder runs many times.
Candidate: a strong general model (e.g. the best available on CommandCode /
whatever wins the next model bake-off). Builder stays cheap+fast (MiMo Pro).
Critic stays a different model (Muse) to avoid self-review bias.

---

## 7. What "Done" Looks Like (acceptance for the brain itself)

The brain is done when:
1. A user request flows through the state machine without human babysitting
   beyond the 3 checkpoints.
2. The design doc is genuinely useful (user can veto meaningfully).
3. The recipe is unambiguous (builder never asks "what do you mean").
4. Verification catches at least the Gate-1.5-class bugs (behavioral, not
   just the builder's own tests).
5. The report is plain-language and the user trusts it.

Measured by: run the loop on real tasks (the diskscope backlog) and count
(design rejections, fix rounds, stalls, user corrections). Target: <2 fix
rounds per task, <10% stall rate, user approves >80% of designs.
