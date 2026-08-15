# omp-agent

A fully-automated, omp-native engineering pipeline: give it a goal and it drives to
completion through a hard **test gate**, a **cross-model adversarial review**, a
**visual + functional e2e gate** (Playwright + a vision model sees the UI it builds),
and a human **steer checkpoint**. Plus a **factory** (`scaffold.sh`) to replicate the
setup into any new project.

Everything runs through **Oh My Pi** (`omp`) — no Omnigent, no Munder Difflin, no
separate orchestrator to glue together. Build quality is enforced by real tests;
the adversarial review uses a *different* model than the builder so it's genuinely
independent.

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

## The loop (what omp does)

```
[requirements.md]
      │
      ▼
  1. PLAN     — plan mode, breaks the goal into build/test/design work (you approve)
      │
      ▼
  2. BUILD    — builder agent implements code + tests, committing each logical unit
                (small, meaningful commits, not one giant blob)
      │
      ▼
  3. GATE 1   — HARD test gate (tests/gate.sh auto-detects the stack; red = halt + fix)
      │
      ▼
  4. GATE 2   — ADVERSARIAL review: a DIFFERENT model criticizes the diff;
                FAIL sends feedback back to iterate (bounded)
      │
      ▼
  5. GATE 3   — VISUAL + FUNCTIONAL E2E (if there's a UI): Playwright drives the
                app through its real flows + captures screenshots, and a vision
                model (google/gemini-3.1-flash-lite) reviews the UI actually renders
                and looks correct (tests/visual_gate.sh)
      │
      ▼
  6. STEER    — omp stops and shows the diff for your approval before committing
      │
      ▼
  7. DONE
```

The full operating instructions (roles, order, hard rules) live in **`PIPELINE.md`**
— that's the file omp loads as context on every run.

All three gates are hard and non-skippable (`run-gates.sh` runs GATE 1 + 2; GATE 3
runs when the deliverable has a UI). omp must not self-review GATE 2 — the critic and
the visual review are separate processes.

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
   review (Gate 2). The reviewer is deliberately a *different* model than the
   builder, because a builder that checks its own work misses its own assumptions
   (just like a human second-guessing their own typos).
3. **The UI has to actually render and work** — so when there's a user interface
   there's a visual + functional e2e gate (Gate 3). Playwright drives the real app
   through its flows and captures screenshots, and a vision model checks the UI
   looks correct. A diff-only review can silently bless a screen that's broken or
   bare; this gate exercises it for real.

**Why omp specifically fits this:**
- **It covers the whole loop in one tool.** omp plans, dispatches subagents, and can
  act as builder *and* reviewer. We didn't want to wire a separate orchestrator
  between two agents — omp already coordinates subagents on its own.
- **Per-role models built in.** omp routes different models to different roles
  (`modelRoles`), which is exactly what we need to keep the builder and critic on
  *different* models. No glue code.
- **Not locked to one provider.** omp talks to many providers, so you mix a builder
  from one vendor and a critic from another, and switch models as prices/quality
  change (which they do, often).
- **Programmable.** `--mode rpc` gives a JSON/stdio interface for the non-interactive
  automation path.
- **Batteries that matter here.** Real editing primitives (hashline edits, LSP/DAP,
  git-worktree isolation) and a solid agentic loop.

**What this setup is deliberately NOT:**
- **Not an always-on "agent farm"** running 24/7 in the background. This pipeline is
  *controlled, sequential, gated* single-task execution with a human steer gate at
  the end. You give it one goal, it works until the gates pass, then it stops for
  your approval. Running a fleet of agents around the clock is a different problem
  with different (heavier) machinery — not what this strives for.
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
export OPENROUTER_API_KEY="sk-or-..."      # critic (any model via OpenRouter)
export XIAOMI_API_KEY="..."                # optional: builder via Xiaomi MiMo
export XIAOMI_BASE_URL="https://api.xiaomimimo.com/v1"
# ... any others you use (DEEPSEEK_API_KEY, OPENCODE_GO_API_KEY, ...)
```

If you use Hermes and keep keys in `~/.hermes/.env`, that file is loaded into the
environment automatically.

### 3. Set your model roles

omp's model routing lives in `~/.omp/agent/config.yml` (and `~/.config/oh-my-pi/models.yml`).
Example:

```yaml
modelRoles:
  default: z-ai/glm-5.2            # your builder model
  plan: z-ai/glm-5.2
  smol: deepseek/deepseek-v4-flash
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

Edit `.omp/config.yml` (per project) for builder/plan, and `tests/review_gate.sh`
or the `CRITIC_MODEL` env var for the critic. See
[Configure your own models & providers](#configure-your-own-models--providers).

---

## The model roles (what to configure)

The pipeline needs **two core models**, and they **must differ**:

1. **builder** — implements code + tests. Pick your fastest strong coder.
2. **critic** (Gate 2) — adversarially reviews the builder's diff. Pick a *different*
   model so the review is genuinely independent. Reasoning-heavy models are good here.

There's also an optional **vision reviewer** for Gate 3: it checks screenshots of the
running UI. A cheap multimodal model works (e.g. `google/gemini-3.1-flash-lite`);
it's used by `tests/visual_gate.sh`, not by the builder/critic roles.

> **Rule:** if builder and critic are the same model, Gate 2 degenerates into
> self-review. Keep them distinct.

### Recommended default (used in `.omp/config.yml`)

| Role | Model | Provider |
|---|---|---|
| builder | mimo-v2.5-pro | Xiaomi MiMo |
| plan | mimo-v2.5 | Xiaomi MiMo |
| critic | z-ai/glm-5.2 | OpenRouter |

These are just the repo author's defaults. Swap them for whatever you actually use
(see below).

---

## Configure your own models & providers

omp resolves models and credentials through **its own config** — the pipeline only
says *which role uses which model id*. So you configure providers once in your omp
setup, then point the pipeline at them.

### 1. Tell omp about your providers + keys

Providers and API keys live in your **omp environment** (not in this repo):
- omp reads API keys from your shell environment / omp's secrets store. Common vars:
  `OPENROUTER_API_KEY`, `XIAOMI_API_KEY`/`XIAOMI_BASE_URL`, `OPENCODE_GO_API_KEY`,
  `DEEPSEEK_API_KEY`, etc.
- Set any provider's credentials you plan to use. See omp's own docs for the exact
  key names and config file (`~/.omp/agent/config.yml`, `~/.config/oh-my-pi/models.yml`).

### 2. Pick model ids that exist in your setup

Each model is addressed as `<provider>/<model>` (e.g. `z-ai/glm-5.2` on OpenRouter,
`xiaomi-token-plan-sgp/mimo-v2.5-pro`, `deepseek/deepseek-v4-flash`). To know what
you have, list models from your providers (e.g. `curl https://openrouter.ai/api/v1/models`),
or run omp and pick from its model menu.

### 3. Point the pipeline at them

Edit **`.omp/config.yml`** (per project) to set your builder/plan/critic ids:

```yaml
modelRoles:
  default: <provider>/<builder-model>     # builder
  plan: <provider>/<plan-model>
# critic is set separately (see tests/review_gate.sh or CRITIC_MODEL env)
```

The critic is invoked by `tests/review_gate.sh`; it defaults to a model and can be
overridden at runtime:

```bash
CRITIC_MODEL="myorg/my-critic-model" omp
# or edit the default in tests/review_gate.sh
```

### 4. Validate before trusting

Never trust a model's self-report. Run a quick coding probe (e.g. the dedupe test)
against any candidate and confirm it produces correct, runnable code before wiring it
into the pipeline. See `CONFIG.md` for the full rule set.

---

## Key rules baked in (validated, don't break them)

1. **Builder ≠ critic ≠ vision reviewer.** The adversarial review (Gate 2) only works
   if the critic is a *different* model than the builder. And GATE 3's visual review
   runs as a separate vision-model process too (no self-reviewing the UI).
2. **Use a generous `max_tokens` (>= 4000) for reasoning models.** `max_tokens` is a
   CEILING — the model self-terminates when done, so a higher value doesn't waste
   tokens on short answers. It just gives reasoning enough room so the answer isn't
   truncated empty. (GATE 3's vision review also needs enough tokens.)
3. **Optional: low-thinking to cut cost.** Some reasoning models accept a low
   `thinking`/`reasoning_effort` setting that sharply cuts completion tokens. Support
   and value vary by model/provider, so it's a user choice (see CONFIG.md) — verify
   it on your own model before relying on it.
4. **GATE 1 runs real tests.** Never trust a model's self-reported pass — a green
   test suite is the only green.
5. **GATE 3 runs real flows + a real vision check.** Never trust "the code compiles"
   as proof a screen works — Playwright exercises it and a vision model checks it.
6. **Watch provider rate limits** (some providers 403 under load).

---

## Repository layout

```
omp-agent/
├── scaffold.sh          # FACTORY — replicate this setup into a new project
├── run-gates.sh         # HARD dual-gate runner (GATE 1 + GATE 2, sources project .env)
├── pipeline.sh          # fully-automated loop (build → gates → feed findings back)
├── PIPELINE.md          # the operating loop omp follows
├── CONFIG.md            # the repo-author's validated model choices + rules
├── USAGE.md            # how to drive the whole thing yourself
├── PROJECTS.md          # apps built with omp-agent (live showcase)
├── requirements.md      # goal template (edit per project)
├── design-system/
│   └── tokens.json      # UI design tokens (screen consistency)
├── tests/
│   ├── gate.sh          # GATE 1 — hard test gate (auto-detects stack(s), runs tests)
│   ├── review_gate.sh   # GATE 2 — cross-model adversarial review (OpenRouter direct)
│   ├── visual_gate.sh   # GATE 3 — Playwright functional e2e + vision screenshot review
│   └── e2e/             # Playwright spec templates + config for GATE 3
└── .omp/
    └── config.yml       # modelRoles (EDIT to your models)
```

---

## Setup / prerequisites

- **Oh My Pi** (`omp`) installed and configured.
- At least one provider key (e.g. OpenRouter) for the critic, plus a builder model.
  See [Configure your own models & providers](#configure-your-own-models--providers).
- **GATE 3 (visual/e2e) needs a browser + a cheap vision model.** `tests/visual_gate.sh`
  installs `@playwright/test` + Chromium on first run and uses a vision model
  (`VISION_MODEL`, default `google/gemini-3.1-flash-lite`) to review screenshots.
  Only needed if the deliverable has a UI.

---

## License

[MIT](LICENSE) © kaianuar
