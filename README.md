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
