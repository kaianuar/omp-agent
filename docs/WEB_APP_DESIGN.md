# omp-agent Web App — UI & Architecture Design (v1)

Companion to PRODUCT_SPEC.md + ORCHESTRATOR_BRAIN.md. Drafted 2026-08-21.
**Principle: clean, minimal architecture. Build the smallest thing that runs
the loop; refine incrementally. No massive changes unless required.**

---

## 1. Product shape (v1)

A local-first web app: **chat with an orchestrator** who runs the
builder+critic pipeline. The user talks, sees design docs / build progress /
critic verdicts as cards in the conversation, and approves/rejects at
checkpoints.

**Mental model:** a chat with a senior engineer who has a build pipeline.
Not a dashboard, not a terminal.

## 2. Architecture (minimal, 3 layers)

```
┌──────────────────────────────────────────────────────────┐
│  FRONTEND  (React + Vite, localhost)                     │
│  Chat + cards + approve/reject + live pipeline status    │
│  ONE websocket: JSON-RPC calls + live event push         │
├──────────────────────────────────────────────────────────┤
│  BACKEND  (FastAPI, Python)                              │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  API layer  │→ │  Orchestrator│→ │  Pipeline exec │  │
│  │  (ws RPC    │  │  (state      │  │  (dispatch omp,│  │
│  │  dispatcher,│  │  machine +   │  │  run gates,    │  │
│  │  no REST)   │  │  LLM calls)  │  │  verify)       │  │
│  └─────────────┘  └──────────────┘  └────────────────┘  │
│        │                 │                 │            │
│  ┌─────┴─────────────────┴─────────────────┴─────────┐   │
│  │  PERSISTENCE  (SQLite: sessions, tasks, events,   │   │
│  │   artifacts index; scratch dir for files)         │   │
│  └───────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

**Layer rules (the "clean" part):**
- **API layer** — one WebSocket endpoint (`/ws`), a JSON-RPC dispatcher.
  No business logic. Thin.
- **Orchestrator** — the brain (state machine from ORCHESTRATOR_BRAIN.md).
  Pure logic; no web knowledge; emits events.
- **Pipeline exec** — talks to the real world: runs omp, runs gates, runs
  verify commands, writes scratch. Everything side-effectful lives here.
- **Persistence** — SQLite via a thin data layer. Sessions/tasks/events.
- **Direction of dependency:** API → Orchestrator → Pipeline exec → (files,
  processes, DB). Never the reverse. Orchestrator knows nothing about the
  transport (WebSocket or otherwise).

**Why this stays clean & minimal:**
- 4 modules, each one job. No framework lock-in beyond FastAPI+SQLite.
- The orchestrator is testable headless (no web) — the brain spec's
  acceptance metrics run against it directly.
- Adding the web UI later to a headless engine = just the API layer on top
  (which is why this design keeps the seam clean even though we build web-first).

## 3. Data model (minimal)

```
Project      { id, name, repo_path, scratch_path, created_at }
Session      { id, project_id, started_at, status }
Task         { id, session_id, intent(json), state, current_phase,
               design_doc_path, recipe_path, pr_url, created_at }
Event        { id, task_id, ts, kind, payload(json) }
               kinds: intake, research_note, design_ready, design_approved,
               design_rejected, recipe_ready, build_started, build_commit,
               build_stalled, build_done, critic_verdict, verify_result,
               report, user_interrupt, error
```

- **Task** is the unit of work (one user request → one task through the loop).
- **Event** is the audit trail + the websocket stream source (frontend renders
  events as cards).
- No ORM needed — SQLite via a small data module (or sqlite3 stdlib for v1;
  SQLAlchemy only if it grows).

## 4. API surface (v1, minimal)

**One WebSocket** (`/ws`). JSON-RPC-style messages, correlated by id:

```
Request:   {"id": 1, "method": "projects.list", "params": {}}
Response:  {"id": 1, "result": [...]}
Error:     {"id": 1, "error": "message"}
Event:     {"type": "event", "event": {...}}   (live push, no id)
```

Methods:

```
health            → {"ok": true}
projects.list     → all bound projects
projects.create   {name, repo_path, scratch_path} → project
fs.list           {path?} → {path, dirs: [{name, path}]} (browse dialog)
sessions.create   {project_id} → session
sessions.list     {project_id} → sessions (newest first)
sessions.tasks    {session_id} → tasks
sessions.bind     {session_id} → subscribe socket to live events + replay
tasks.create      {session_id, message} → task (starts INTAKE)
tasks.get         {task_id} → task
tasks.clarify     {task_id, answers} → task
tasks.decide      {task_id, decision, note?} → task (approve|reject|adjust)
tasks.events      {task_id} → event history
deny.log          → sandbox deny-log entries
```

That's it. No auth in v1 (localhost-only; bind 127.0.0.1). No multi-user.
The frontend's `api.ts` is a thin RPC client over this one socket; the
backend pushes live events to bound sockets as the orchestrator runs.

## 5. Frontend structure (React + Vite, minimal)

```
src/
  App.tsx             — shell: layout (left rail + chat + scratch drawer)
  components/
    ChatView.tsx      — message list + input; renders cards
    DesignCard.tsx    — design doc + [Approve][Adjust][Reject]
    RecipeCard.tsx    — recipe (collapsible) + [Approve][Skip]
    BuildCard.tsx     — live build progress (branch, commits, status)
    VerdictCard.tsx   — critic P0-P4 list
    ResultCard.tsx    — summary + [View PR][Merge][Request change]
    PipelineRail.tsx  — left rail: project + live gate status
    ScratchDrawer.tsx — collapsible: orchestrator's scratch files
  hooks/
    useTaskStream.ts  — websocket → event → card state
  api.ts              — thin WS JSON-RPC client (all calls over one socket)
  types.ts            — DTOs (Task, Event, etc.)
```

**Card-in-chat model:** every Event kind maps to a card component. The chat
is the timeline. Approve/reject buttons live on the cards. Streaming events
append/update cards in place (build progress ticks).

## 6. The orchestrator engine (behind the API — from BRAIN doc)

- State machine: IDLE→INTAKE→RESEARCH→DESIGN→[checkpoint]→RECIPE→
  [checkpoint]→BUILD→REVIEW→VERIFY→[checkpoint]→REPORT→IDLE.
- Each phase = a function in `orchestrator/phases.py` (pure: task state in,
  events + next-state out).
- LLM calls via a thin `llm.py` (any OpenAI-compatible endpoint — the
  CommandCode/Xiaomi stack, or a local model).
- Context pack assembly in `orchestrator/context.py` (AGENTS.md + backlogs +
  design docs + preferences).
- Templates in `templates/` (design.md, recipe.md, clarify, verify) —
  parameterized per task.
- Scratch writes go through `pipeline/scratch.py` — the ONLY write path,
  realpath-guarded to the project's scratch dir (never the project itself).
- Dispatch in `pipeline/exec.py` — runs omp with the recipe, monitors for
  stalls, runs gates + verify.

```
orchestrator/
  __init__.py
  machine.py       — state machine transitions + event emission
  phases.py        — one function per phase (intake, design, recipe, ...)
  context.py       — context pack assembly (L0-L3)
  llm.py           — OpenAI-compatible client (model routing)
  prompts.py       — prompt builders (uses templates/)
  templates/       — design.md, recipe.md, clarify.md, verify.md
pipeline/
  __init__.py
  exec.py          — dispatch omp, monitor, gates, verify commands
  scratch.py       — the ONLY write path (realpath-guarded to scratch dir)
  sandbox.py       — permission checks (deny project writes, deny-log)
api/
  __init__.py
  main.py          — FastAPI app, ONE websocket (/ws), RPC dispatcher
  events.py        — event bus: per-session websocket fan-out
data/
  db.py            — SQLite thin layer
main.py            — entrypoint: uvicorn
```

**The clean seam:** `orchestrator` + `pipeline` are 100% web-free — they'd
run headless too. `api` is a thin adapter. That's the "no massive changes"
insurance: if the UI direction shifts, the engine survives.

## 7. Streaming & events (the live feel)

- `db.add_event` persists every event (SQLite) AND publishes it to the
  session's websocket clients via `api/events.py` (per-session fan-out).
- The socket bound to a session (`sessions.bind`) replays its recent task
  events on connect, then receives live events as the orchestrator runs.
- Frontend: `api.onEvent` maps kind → card, appends/updates. No polling.

## 8. v1 scope (what we build now)

**In:**
- Project binding (repo path + scratch dir) — open any existing folder
  via typed path OR a browse dialog (fs.list).
- Multiple sessions per project; session picker restores full history
  (tasks, events, checkpoint state).
- The full loop: intake → design card → approve → recipe → build (omp) →
  critic → verify → result card → merge button (gh pr merge).
- Scratch drawer (design/recipe/test files).
- Localhost only, no auth.

**Deliberately OUT (refine later):**
- Multi-user, auth, cloud.
- Parallel tasks / multi-project concurrency.
- Template editing UI.
- Cost dashboard.
- Anything beyond the loop that works.

## 9. Build steps (incremental, clean)

1. **Scaffold** — FastAPI + React/Vite skeleton, SQLite schema, ws echo.
2. **Pipeline exec** — dispatch omp with a recipe, capture events (test with
   a real recipe on diskscope). No brain yet — hardcode a phase script.
3. **Orchestrator phases** — INTAKE→DESIGN→RECIPE as LLM calls producing
   artifacts; BUILD→REVIEW→VERIFY wired to exec; checkpoints emit events.
4. **API + ws** — routes above, event stream.
5. **Frontend** — chat + cards + rail + drawer; approve/reject wired.
6. **Dogfood** — run the diskscope backlog through it; measure against the
   brain's acceptance metrics; refine.

Each step is independently testable. No big-bang.
