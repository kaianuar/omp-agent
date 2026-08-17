# omp-agent

A fully-automated, omp-native engineering pipeline: give it a goal and it drives to
completion through a hard **test gate**, an **adversarial review**, a
**visual + functional e2e gate** (Playwright + a vision model sees the UI it builds),
and a human **steer checkpoint**. Plus a **factory** (`scaffold.sh`) to replicate the
setup into any new project.

Everything runs through **Oh My Pi** (`omp`) as the agent, with a thin
`pipeline.sh` orchestrator that drives a **plan-only phase** then a **phased build**
(each phase: implement → test gate → adversarial review → commit → next), so a
large project is reviewed in small, bounded slices instead of one giant wall.
Build quality is enforced by real tests; the adversarial review uses the same
model as the builder (Xiaomi MiMo) with strict severity discipline to ensure
genuine independence through prompt-enforced rules.

The pipeline is **model-agnostic** — you bring your own models/providers, or use the
recommended defaults.

🌍 **See it in action:** apps built with omp-agent → **[PROJECTS.md](PROJECTS.md)**.

---

## Quick start (you have models configured)

```bash
# 1. Clone
git clone https://github.com/kaianuar/omp-agent
cd omp-agent

# 2. Scaffold a new project from the factory
./scaffold.sh ~/code/my-app --ui        # --ui also copies the UI design tokens

# 3. Edit the goal, then let omp run the loop (see PIPELINE.md)
cd ~/code/my-app
#   - edit requirements.md  (what to build)
omp
```

That's it — fill in `requirements.md`, and omp handles the rest (including
auto-detecting your stack's test command(s)). New machine? See
[Configure your own models & providers](#configure-your-own-models--providers).

Or view the full **[USAGE.md](USAGE.md)** cheat-sheet — how to run the pipeline
yourself end to end (scaffold, omp commands, steering, troubleshooting).

---

## The loop (what the pipeline does)

```
[requirements.md]
      │
      ▼
  A. PLAN-ONLY  — builder writes plan.md (phases identified, NO code). Critic
                  (Gate 0) approves the plan before any code exists. Rejections
                  only revise the plan, never touch source.
      │  plan approved
      ▼
  B. PHASED BUILD — for each phase (Phase 1: domain → Phase 2: adapters → ...):
      │   ┌───────────────────────────────────────────┐
      │   │  builder implements deliverables           │  (no plan edits)
      │   │  (sub-chunked: ≤5 focused omp calls,      │
      │   │   or batched if more)                      │
      │   ▼                                           │
      │  GATE 1 — HARD test gate (tests/gate.sh; red = halt)   │
      │   ▼                                           │
      │  GATE 2 — ADVERSARIAL review: MiMo criticizes │
      │           that phase's diff;                  │
      │           FAIL → feed findings back → retry   │── loop (bounded)
      │   ▼                                           │
      │  PASS → commit that phase → next phase ───────┘
      ▼
  C. GATE 3  — VISUAL + FUNCTIONAL E2E (if there's a UI): Playwright drives the
                app through its real flows + captures screenshots, and a vision
                model (mimo-v2.5) reviews the UI actually renders and looks
                correct (tests/visual_gate.sh)
      │
      ▼
  D. STEER   — shows the diff for your approval before finalizing
      │
      ▼
  E. DONE
```

The full operating instructions (roles, order, hard rules) live in **`PIPELINE.md`**
— that's the file omp loads as context on every run.

`pipeline.sh` orchestrates the whole thing (plan-only → per-phase build/gates).
All gates are hard and non-skippable. omp must not self-review GATE 2 — the critic
and the visual review are separate processes.

### Interaction log

Every run writes a structured interaction log to `/tmp/omp_interaction.log`:
- Plan phase: builder task, plan content-hash, critic verdict with P1 count
- Build phases: Gate 1 test results, Gate 2 critic verdict, per-deliverable progress
- Content-hashes make stale-content bugs immediately visible

### Issue ledger

Gate 2 maintains a structured issue ledger (`/tmp/review_ledger.txt`) per phase:
- Each finding is tagged `[P0]`–`[P4]` and tracked with `OPEN`/`RESOLVED`/`BACKLOG` status
- The critic re-flags only `OPEN` items; `RESOLVED` items stay closed
- Prevents the "re-raise same issue forever" deadlock that plagued earlier versions

### Docker preflight

For projects needing native build dependencies (Tauri, GTK, etc.):
- `pipeline.sh` auto-detects the runtime (Rust/Node/Python/PHP/Go) from project manifests
- Generates a Dockerfile with the appropriate base image + system libs
- Builds a cached Docker image (`omp-env:<project>`)
- Gates run tests inside the container, eliminating host-lib blockers

---

## Why omp? (the thinking behind this setup)

The goal here is a local agent that takes a goal and drives it to completion
**reliably** — not a demo that mostly works and occasionally ships something broken.
That goal shapes every choice:

**Three things have to be hard:**
1. **The build has to actually work** — so there's a hard test gate in front of
   everything (Gate 1). Code isn't "done" because the agent says so; it's done when
   the tests pass.
2. **Someone independent has to review it** — so there's a cross-model adversarial
   review (Gate 2). The reviewer applies strict severity discipline (P0–P4 taxonomy,
   actionable `-> FIX:` remediation, respect-own-FIX contract) so it can't inflate
   severity or re-raise resolved issues.
3. **The UI has to actually render and work** — so when there's a user interface
   there's a visual + functional e2e gate (Gate 3). Playwright drives the real app
   through its flows and captures screenshots, and a vision model checks the UI
   looks correct. A diff-only review can silently bless a screen that's broken or
   bare; this gate exercises it for real.

**Why omp specifically fits this:**
- **It covers the whole loop in one tool.** omp plans, dispatches subagents, and can
  act as builder *and* reviewer. `pipeline.sh` is a thin orchestrator on top that
  splits the work into a plan-only phase and per-phase build/review — omp provides
  the agentic editing and model routing; the orchestrator just sequences the phases
  and gates.
- **Programmable.** `--mode rpc` gives a JSON/stdio interface for the non-interactive
  automation path.
- **Batteries that matter here.** Real editing primitives (hashline edits, LSP/DAP,
  git-worktree isolation) and a solid agentic loop.

**What this setup is deliberately NOT:**
- **Not an always-on "agent farm"** running 24/7 in the background. This pipeline is
  *controlled, sequential, gated* single-task execution with a human steer gate at
  the end. You give it one goal, it works until the gates pass, then it stops for
  your approval.
- **Not tied to any specific model or vendor.** Swap builder/critic freely; the
  gates and the loop are what guarantee quality.

---

## Installing & setting up omp

### 1. Install

Oh My Pi ships as a CLI. From its GitHub (`can1357/oh-my-pi`, also `omp.sh`):

```bash
# npm
npm install -g @oh-my-pi/cli

# or curl (Linux/macOS)
curl -fsSL https://omp.sh/install.sh | bash
```

Confirm it works: `omp --version`.

> Check the omp repo / omp.sh for the current, supported install command for your
> platform — it ships by shell script, npm, Bun, or PowerShell.

### 2. Point omp at your providers (API keys)

omp reads provider keys from your shell environment and its own secrets store.
At minimum set the keys for the providers you'll use:

```bash
export XIAOMI_API_KEY="..."                # builder + critic via Xiaomi MiMo
export XIAOMI_BASE_URL="https://token-plan-sgp.xiaomimimo.com/v1"
# ... any others you use (DEEPSEEK_API_KEY, OPENCODE_GO_API_KEY, ...)
```

If you use Hermes and keep keys in `~/.hermes/.env`, that file is loaded into the
environment automatically.

### 3. Set your model roles

omp's model routing lives in `~/.omp/agent/config.yml` (and `~/.config/oh-my-pi/models.yml`).
Example:

```yaml
modelRoles:
  default: xiaomi-token-plan-sgp/mimo-v2.5-pro   # your builder model
  plan: xiaomi-token-plan-sgp/mimo-v2.5
```

You don't have to match this exactly — set the roles to models you have access to.

### 4. Sanity-check with a coding probe

Before trusting a model, run a tiny coding task and confirm it produces runnable
code (never trust a model's self-report). Example probe (2026-08-15):

> *"Write a Python function `dedupe_events(events)` that keeps the earliest
> timestamp per id, output ordered by first appearance in the input, and returns
> `[]` for empty input. Return only runnable code."*

If it returns correct code, the model is usable in the pipeline (see CONFIG.md rules).

### 5. Point the pipeline at your models

Edit `.omp/config.yml` (per project) for builder/plan, and the `PIPELINE_CRITIC_MODEL`
or `CRITIC_MODEL` env var for the critic. See
[Configure your own models & providers](#configure-your-own-models--providers).

---

## The model roles (what to configure)

The pipeline needs **two core models**:

1. **builder** — implements code + tests. Pick your fastest strong coder.
2. **critic** (Gate 2) — adversarially reviews the builder's diff. Uses the same
   model as the builder by default (Xiaomi MiMo), with strict severity discipline
   enforced through prompt rules (P0–P4 taxonomy, actionable `-> FIX:` lines,
   respect-own-FIX contract).

There's also an optional **vision reviewer** for Gate 3: it checks screenshots of the
running UI. A multimodal model works (e.g. `mimo-v2.5`); it's used by
`tests/visual_gate.sh`, not by the builder/critic roles.

### Recommended default

| Role | Model | Provider |
|---|---|---|
| builder | mimo-v2.5-pro | Xiaomi MiMo |
| plan | mimo-v2.5 | Xiaomi MiMo |
| critic | mimo-v2.5-pro | Xiaomi MiMo |
| vision | mimo-v2.5 | Xiaomi MiMo |

These are the repo author's defaults. Swap them for whatever you actually use
(see below).

---

## Configure your own models & providers

omp resolves models and credentials through **its own config** — the pipeline only
says *which role uses which model id*. So you configure providers once in your omp
setup, then point the pipeline at them.

### 1. Tell omp about your providers + keys

Providers and API keys live in your **omp environment** (not in this repo):
- omp reads API keys from your shell environment / omp's secrets store. Common vars:
  `XIAOMI_API_KEY`, `OPENCODE_GO_API_KEY`, `DEEPSEEK_API_KEY`, etc.
- Set any provider's credentials you plan to use. See omp's own docs for the exact
  key names and config file (`~/.omp/agent/config.yml`, `~/.config/oh-my-pi/models.yml`).

### 2. Pick model ids that exist in your setup

Each model is addressed as `<provider>/<model>` (e.g. `xiaomi-token-plan-sgp/mimo-v2.5-pro`).
To know what you have, list models from your providers, or run omp and pick from its model menu.

### 3. Point the pipeline at them

Edit **`.omp/config.yml`** (per project) to set your builder/plan ids:

```yaml
modelRoles:
  default: <provider>/<builder-model>     # builder
  plan: <provider>/<plan-model>
```

The critic is invoked by `tests/review_gate.sh`; it defaults to a model and can be
overridden at runtime:

```bash
PIPELINE_CRITIC_MODEL="myorg/my-critic-model" omp
# or edit the default in tests/review_gate.sh
```

### 4. Validate before trusting

Never trust a model's self-report. Run a quick coding probe (e.g. the dedupe test)
against any candidate and confirm it produces correct, runnable code before wiring it
into the pipeline. See `CONFIG.md` for the full rule set.

---

## Key rules baked in (validated, don't break them)

1. **Use a generous `max_tokens` (>= 4000) for reasoning models.** `max_tokens` is a
   CEILING — the model self-terminates when done, so a higher value doesn't waste
   tokens on short answers. It just gives reasoning enough room so the answer isn't
   truncated empty. (GATE 3's vision review also needs enough tokens.)
2. **GATE 1 runs real tests.** Never trust a model's self-reported pass — a green
   test suite is the only green.
3. **GATE 3 runs real flows + a real vision check.** Never trust "the code compiles"
   as proof a screen works — Playwright exercises it and a vision model checks it.
4. **Watch provider rate limits** (some providers 403 under load).
5. **Builder scaffold must be minimal.** Never pre-scaffold application code or
   design decisions — the builder writes everything from `requirements.md`.
   Only pipeline infrastructure is scaffolded.
6. **Respect the severity discipline.** P0/P1 = concrete build/requirement defects.
   Documentation/completeness nits are P2/P3, never block. A `-> FIX:` line is a
   contract — if satisfied, the finding is RESOLVED and must not be re-raised.

---

## Repository layout

```
omp-agent/
├── scaffold.sh          # FACTORY — replicate this setup into a new project
├── run-gates.sh         # HARD dual-gate runner (GATE 1 + GATE 2, sources project .env)
├── pipeline.sh          # fully-automated loop (plan → sub-chunked phases → gates)
├── PIPELINE.md          # the operating loop omp follows
├── PIPELINE_AUDIT.md    # full data-flow audit, handoffs, and risks
├── CONFIG.md            # the repo-author's validated model choices + rules
├── USAGE.md             # how to drive the whole thing yourself
├── PROJECTS.md          # apps built with omp-agent (live showcase)
├── requirements.md      # goal template (edit per project)
├── design-system/
│   └── tokens.json      # UI design tokens (screen consistency)
├── tests/
│   ├── gate.sh          # GATE 1 — hard test gate (auto-detects stack(s), runs tests)
│   ├── review_gate.sh   # GATE 2 — adversarial review (P0–P4, issue ledger, -> FIX)
│   ├── visual_gate.sh   # GATE 3 — Playwright functional e2e + vision screenshot review
│   ├── gate0_plan_review.sh  # GATE 0 — plan review (before any code exists)
│   ├── pipeline_self_test.sh # 19 self-tests for pipeline logic
│   ├── lib/
│   │   └── review_ledger.py  # issue ledger logic (OPEN/RESOLVED/BACKLOG)
│   └── e2e/             # Playwright spec templates + config for GATE 3
└── .omp/
    └── config.yml       # modelRoles (EDIT to your models)
```

---

## Setup / prerequisites

- **Oh My Pi** (`omp`) installed and configured.
- At least one provider key (e.g. `XIAOMI_API_KEY`) for the critic, plus a builder model.
  See [Configure your own models & providers](#configure-your-own-models--providers).
- **Docker** (optional but recommended) for projects needing native build dependencies
  (Tauri, GTK, etc.). The pipeline auto-detects the runtime and builds a container.
- **GATE 3 (visual/e2e) needs a browser + a vision model.** `tests/visual_gate.sh`
  installs `@playwright/test` + Chromium on first run and uses a vision model
  (`VISION_MODEL`, default `mimo-v2.5`) to review screenshots.
  Only needed if the deliverable has a UI.

---

## License

[MIT](LICENSE) © kaianuar
