# omp-agent

A fully-automated, omp-native engineering pipeline: give it a goal and it drives to
completion through a hard **test gate**, a **cross-model adversarial review**, and a
human **steer checkpoint**. Plus a **factory** (`scaffold.sh`) to replicate the setup
into any new project.

Everything runs through **Oh My Pi** (`omp`) — no Omnigent, no Munder Difflin, no
separate orchestrator to glue together. Build quality is enforced by real tests;
the adversarial review uses a *different* model than the builder so it's genuinely
independent.

The pipeline is **model-agnostic** — you bring your own models/providers, or use the
recommended defaults.

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
#   - edit tests/gate.sh    (the RUN TESTS block -> your real test runner)
omp
```

New machine? See [Configure your own models & providers](#configure-your-own-models--providers).

---

## The loop (what omp does)

```
[requirements.md]
      │
      ▼
  1. PLAN     — plan mode, breaks the goal into build/test/design work (you approve)
      │
      ▼
  2. BUILD    — builder agent implements code + tests
      │
      ▼
  3. GATE 1   — HARD test gate (tests/gate.sh must exit 0; red suite = halt + fix)
      │
      ▼
  4. GATE 2   — ADVERSARIAL review: a DIFFERENT model criticizes the diff;
                FAIL sends feedback back to iterate (bounded)
      │
      ▼
  5. STEER    — omp stops and shows the diff for your approval before committing
      │
      ▼
  6. DONE
```

The full operating instructions (roles, order, hard rules) live in **`PIPELINE.md`**
— that's the file omp loads as context on every run.

---

## Why omp? (instead of Claude Code / other orchestrators)

This pipeline is built around **Oh My Pi (`omp`)** rather than a different coding
agent or a separate orchestrator like Omnigent or Munder Difflin. The reasons:

**omp is the whole stack in one tool:**
- **Subagents + plan mode** — it plans, then dispatches subagents, so it can be the
  planner, the builder, and the reviewer without glue code.
- **Multi-provider** — 60+ providers through one interface, so you're not locked to
  one vendor and can mix a builder from one provider with a critic from another.
- **Per-role models** (`modelRoles`: default/plan/smol/...) — exactly what the
  pipeline needs to keep the builder and critic on **different models**.
- **`--mode rpc`** — a programmatic interface (JSON/stdio) for the non-interactive
  automation path.
- **Hashline edits, LSP/DAP, git-worktree isolation** — solid, real code editing,
  not just model wrappers.

**What we deliberately did NOT need:**
- **Omnigent / a separate orchestrator** — omp already coordinates subagents and
  per-role models, so adding Omnigent means wiring a protocol between two tools for
  no gain. Omp alone covers the loop.
- **Munder Difflin** — its strength is long-running 24/7 agent *fleets* with
  clone-to-clone messaging. This pipeline needs *controlled, sequential, gated*
  single-task execution with a human steer gate — not an always-on fleet.
- **Claude Code** — it's a fine coding agent, but omp gives the same agentic loop
  plus broader provider choice and native per-role model routing, matching how this
  repo mixes providers.

The design principle: **one tool, real test gates, and a genuinely independent
reviewer.** omp provides the "one tool" while the two gates (tests + cross-model
adversarial review) provide the quality.

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

## The two model roles (what to configure)

The pipeline needs **two models**, and they **must differ**:

1. **builder** — implements code + tests. Pick your fastest strong coder.
2. **critic** (Gate 2) — adversarially reviews the builder's diff. Pick a *different*
   model so the review is genuinely independent. Reasoning-heavy models are good here.

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

1. **Builder ≠ critic.** The adversarial review only works if those are *different
   models*. Don't set them equal.
2. **`max_tokens >= 4000` on reasoning models** (glm-5.2, mimo, kimi...). Too low and
   they spend the budget on reasoning and return **empty content**.
3. **GATE 1 runs real tests.** Never trust a model's self-reported pass — a green
   test suite is the only green.
4. **Watch provider rate limits** (some providers 403 under load).

---

## Repository layout

```
omp-agent/
├── scaffold.sh          # FACTORY — replicate this setup into a new project
├── PIPELINE.md          # the operating loop omp follows
├── CONFIG.md            # the repo-author's validated model choices + rules
├── requirements.md      # goal template (edit per project)
├── design-system/
│   └── tokens.json      # UI design tokens (screen consistency)
├── tests/
│   ├── gate.sh          # GATE 1 — hard test gate (edit RUN TESTS block)
│   └── review_gate.sh   # GATE 2 — cross-model adversarial review
└── .omp/
    └── config.yml       # modelRoles (EDIT to your models)
```

---

## Setup / prerequisites

- **Oh My Pi** (`omp`) installed and configured.
- At least one provider key (e.g. OpenRouter) for the critic, plus a builder model.
  See [Configure your own models & providers](#configure-your-own-models--providers).

---

## License

[MIT](LICENSE) © kaianuar
