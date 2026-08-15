# omp-agent

A fully-automated, omp-native engineering pipeline: give it a goal and it drives to
completion through a hard **test gate**, a **cross-model adversarial review**, and a
human **steer checkpoint**. Plus a **factory** (`scaffold.sh`) to replicate the setup
into any new project.

Everything runs through **Oh My Pi** (`omp`) — no Omnigent, no Munder Difflin, no
separate orchestrator to glue together. Build quality is enforced by real tests;
the adversarial review uses a *different* model than the builder so it's genuinely
independent.

---

## Quick start

```bash
# 1. Clone (already have it? just pull)
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

---

## The loop (what omp does)

```
[requirements.md]
      │
      ▼
  1. PLAN     — plan mode, breaks the goal into build/test/design work (you approve)
      │
      ▼
  2. BUILD    — builder agent implements code + tests (xiaomi mimo-v2.5-pro)
      │
      ▼
  3. GATE 1   — HARD test gate (tests/gate.sh must exit 0; red suite = halt + fix)
      │
      ▼
  4. GATE 2   — ADVERSARIAL review: a DIFFERENT model (OpenRouter z-ai/glm-5.2)
                criticizes the diff; FAIL sends feedback back to iterate (bounded)
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

## Models (validated live 2026-08-15, run-the-code verified)

| Role | Model | Provider | ~In/M |
|---|---|---|---|
| **builder** (default) | xiaomi mimo-v2.5-pro | Xiaomi MiMo | sub |
| **plan** | xiaomi mimo-v2.5 | Xiaomi MiMo | — |
| **critic** (Gate 2) | z-ai/glm-5.2 | OpenRouter | $0.49 |
| critic fallback 1 | qwen/qwen3-coder-30b-a3b-instruct | OpenRouter | $0.07 |
| critic fallback 2 | minimax/minimax-m3 | OpenRouter | $0.30 |
| critic fallback 3 | moonshotai/kimi-k2.7-code | OpenRouter | $0.71 |

> ⚠️ **kimi-k2.6 is NOT usable on OpenRouter** (returns empty output despite being
> in some local pools).

Full pricing + fallback matrix + rules in **`CONFIG.md`**.

---

## Key rules baked in (validated, don't break them)

1. **Builder ≠ critic.** The adversarial review only works if those are *different
   models*. Don't set them equal.
2. **`max_tokens >= 4000` on reasoning models** (glm-5.2, mimo, kimi). Too low and
   they spend the budget on reasoning and return **empty content**.
3. **GATE 1 runs real tests.** Never trust a model's self-reported pass — a green
   test suite is the only green.
4. **Avoid OpenCode Go for the critic** — it rate-limits (403) under load.

---

## Repository layout

```
omp-agent/
├── scaffold.sh          # FACTORY — replicate this setup into a new project
├── PIPELINE.md          # the operating loop omp follows
├── CONFIG.md            # validated models + pricing + fallback rules
├── requirements.md      # goal template (edit per project)
├── design-system/
│   └── tokens.json      # UI design tokens (screen consistency)
├── tests/
│   ├── gate.sh          # GATE 1 — hard test gate (edit RUN TESTS block)
│   └── review_gate.sh   # GATE 2 — cross-model adversarial review
└── .omp/
    └── config.yml       # modelRoles wired to real provider ids
```

---

## Setup / prerequisites

- **Oh My Pi** (`omp`) installed and configured.
- **OpenRouter API key** in your environment (e.g. `~/.hermes/.env` →
  `OPENROUTER_API_KEY="sk-or-..."`) for the critic.
- **Xiaomi MiMo** key for the builder (or swap the builder to an OpenRouter
  fallback in `.omp/config.yml`).

---

## Branch / versioning

- `main` — `git pull` on any machine to get the latest factory + config.
- Update the pipeline or models, then:
  ```bash
  git add -A && git commit -m "..." && git push
  ```
