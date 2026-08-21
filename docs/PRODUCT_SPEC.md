# omp-agent → Product: "Local AI Product Builder" (working title)

Product design spec. Drafted 2026-08-21. This documents the vision for turning
omp-agent (the pipeline) + an orchestrator (the "mini-Hermes" role) into a
local-first, user-facing product.

---

## 1. Vision

A local-first "AI software studio" — the user talks to an **orchestrator**
(a conversational agent with full research tools) who designs, plans, dispatches
builds, and verifies — powered by the proven **builder + critic + gates**
pipeline underneath. Think: **Lovable / Replit, but local, private, cheap, and
with an adversarial review layer that actually catches bugs.**

The pitch in one line:
> "Build me an app" — but the agent that keeps improving your product,
> with a built-in reviewer that catches mistakes before they ship.

## 2. The Three Roles (the core architecture)

```
┌────────────────────────────────────────────────────────────┐
│  WEB UI  (the conversation surface)                        │
│  User: "the dupes panel feels cluttered"                   │
│  Orchestrator: "Here's a plan → build it?" [Approve]       │
├────────────────────────────────────────────────────────────┤
│  ORCHESTRATOR  (read + reason + command; NEVER writes      │
│  to the project)                                           │
│  tools: web search, vision, read files, run tests,         │
│  author recipes/design docs (to scratch), dispatch builds, │
│  interpret critic verdicts, report in plain language       │
├────────────────────────────────────────────────────────────┤
│  BUILDER  (omp — the only writer to the project)           │
│  consumes recipes → writes code → commits → opens PRs      │
├────────────────────────────────────────────────────────────┤
│  CRITIC  (read-only adversarial reviewer)                  │
│  reviews diffs → returns P0–P4 verdicts → feeds back       │
└────────────────────────────────────────────────────────────┘
```

**The load-bearing principle: the orchestrator can never change code
directly.** It commands, designs, and verifies — it never *is* the builder.
The only writer to the project is the builder, and every builder action is
recipe-scoped and gate-reviewed.

## 3. Orchestrator Tool & Permission Model

The orchestrator has **all research tools** (web search, vision directly or
indirectly, file reads, terminal) but a **write boundary**: it may write
validation artifacts (tests, scratch, experiments) ONLY outside the project
folder (e.g. /tmp), never inside it.

### Permission table

| Tool class                  | Project folder      | Outside (scratch, e.g. /tmp) |
|-----------------------------|---------------------|------------------------------|
| Read (files, git log, tests)| ✅ allowed          | ✅ allowed                   |
| Run (build, test, scan)     | ✅ allowed          | ✅ allowed                   |
| Write (tests, scratch, docs)| ❌ **never**        | ✅ allowed                   |
| Edit / patch project code   | ❌ **never**        | ❌                           |

### Why the write boundary (not a ban)

- Without write access the orchestrator is a *tattletale* ("I think X is
  broken"). With scratch write access it becomes a *tester*: it can write a
  small validation unit test to /tmp, run it against the project's build,
  and attach the failing output to a recipe as **evidence**. This is the
  proven Gate-1.5 pattern — deterministic behavioral proof catches bugs the
  critic alone misses (e.g. the total_size double-count).
- It keeps the trust boundary: the orchestrator structurally cannot corrupt
  the project, inject code, or bypass the gates.
- It's honest to the workflow: read + run anywhere, write only to scratch,
  never touch the project.

### Enforcement (structural, not a promise)

- **Sandbox rule:** every write operation's target path is resolved with
  `realpath` and checked against the project root. A write inside the project
  is DENIED with an error ("write to project folder blocked — use /tmp").
- **realpath resolution** is mandatory (defeats symlink tricks like
  `ln -s /project /tmp/link`).
- **Project scope:** repo root + everything under it, no exceptions
  (predictable > clever). Build artifacts (target/, node_modules) still count
  as project — the rule is "nothing under the repo root, period."
- **Deny log:** every blocked write is logged and surfaced in the UI
  ("orchestrator attempted to write to the project — blocked") — a visible
  trust signal.
- **Two sandboxes:** the orchestrator process (read+run, write-to-scratch-only)
  and the builder process (full write, recipe-scoped) are separate. The guard
  applies to the orchestrator only.

### Orchestrator toolbelt (concrete)

1. **Web search / extract** — research features, compare approaches, check APIs.
2. **Vision** — analyze user-sent screenshots, mockups, icons (directly if the
   model has vision, else via a vision-model fallback).
3. **File read** — inspect codebase, read AGENTS.md / backlogs / design docs.
4. **Terminal (read-only + scratch-write)** — run tests/builds/git status/log;
   write scratch files to the allowed scratch dir.
5. **Design-doc + recipe authoring** — its primary output artifact (to scratch,
   then handed to the builder).
6. **Dispatch** — hand recipes to the builder; collect critic verdicts; decide
   iterate/approve.
7. **PR / report** — open PRs, summarize in plain language.

## 4. The Loop (how a user request becomes shipped code)

```
1. USER: feedback / idea / bug report (in the web UI chat)
2. ORCHESTRATOR: research (web/vision/files) → design doc → recipe
   (exact file/line, root cause, fix structure, verification steps)
3. USER: approve / adjust / reject (the design doc is the checkpoint)
4. ORCHESTRATOR: dispatch recipe → BUILDER (omp) writes code in the repo
   → commits incrementally → opens a PR
5. CRITIC: read-only review of the diff → P0–P4 verdicts
6. ORCHESTRATOR: interprets verdicts → P0/P1 → dispatch fix round;
   P2+ → surface to user for decision
7. ORCHESTRATOR: verifies (runs tests / smoke checks — writes proof to
   scratch if needed) → reports result in plain language → next iteration
```

Proven equivalents in our workflow: the HTML export (PR #4), theme toggle
(#5), dupes engine (#6), dupes UI (#7) — all followed exactly this loop,
with the orchestrator role played manually (design docs, recipes, verification).

## 5. Product Surface (Web UI)

- **Chat panel** — the conversation (user ↔ orchestrator), like a mini-Hermes.
- **Pipeline view** — live status of gates, critic verdicts, diffs, PRs
  (SSE/websocket stream from the engine).
- **Approve / Adjust / Reject affordances** — the user is the final gate.
- **Project binding** — "point me at a repo + API keys → I learn the codebase
  (AGENTS.md, structure) → you give feedback."
- **Scratch browser** — show what the orchestrator wrote to scratch (tests,
  recipes) so the user can see its reasoning artifacts.

## 6. Build Order (phased) — REVISED 2026-08-21: web-first

Pivot: build the **web UI first**, with the engine running behind it. The
web app IS the product; the CLI/headless engine is an internal detail.
Less use for standalone CLI commands.

1. **Web app shell (frontend)** — chat panel + pipeline view + approve/
   adjust/reject controls. The conversation surface (the product).
2. **Engine behind it** — the orchestrator loop (state machine + context
   pack + templates) as the web app's backend: receive feedback → design
   doc → recipe → dispatch builder → critic → verify → report.
3. **Sandbox/permission layer** — orchestrator writes only to scratch,
   never the project (realpath-guarded).
4. **Project binding + onboarding** — repo binding, API keys, AGENTS.md
   ingestion.
5. **Multi-project + persistence** — sessions, history, scratch retention.

The brain (ORCHESTRATOR_BRAIN.md) drives the engine regardless of surface.
Web-first just changes what we build first: the conversation + pipeline UI,
with the loop wired behind it.

## 7. Open Questions

1. Orchestrator model: which model? (cheap + capable; the current stack has
   MiMo Pro as builder, Muse as critic — orchestrator could be a different,
   more conversational model.)
2. Scratch dir default: `/tmp/omp-orchestrator/` — configurable per project?
3. How much of the recipe/design-doc authoring should be template-driven vs
   free-form LLM? (We have strong templates from the working recipes.)
4. Multi-user / sharing — local-only v1, or later? (Local-only is the v1
   differentiator; sharing = later.)
5. Where does the orchestrator's "product judgment" come from — pure LLM, or
   a growing corpus of design docs / lessons (the backlogs we've built)?

## 8. The Differentiators (marketing truths)

- **Local-first + private** — your code, your models, your machine.
- **Cheap** — Xiaomi $50/38B tokens ≈ pennies per build vs Lovable's $25-100/mo.
- **Review-gated** — the adversarial critic layer that catches bugs before
  they ship (nobody in the AI-builder space does this well).
- **Continuous improvement** — not "generate once," but "the agent that keeps
  improving your product" — feedback → re-design → re-build as the native loop.
