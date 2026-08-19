# Project Context — omp-agent Architecture

## Overview
omp-agent is an automated AI agent orchestration pipeline built on Oh My Pi (omp).
It drives development from requirements to deployed code through a series of quality gates.

## Core Concept
```
requirements.md → Gate 0 (Plan Review) → Build (TDD) → Gate 1 (Tests) 
  → Gate 2 (Adversarial Review) → Gate 3 (Visual/E2E) → Steer → Deploy
```

## Core Components

### 1. Builder (MiMo Pro via Xiaomi)
- Implements code + tests
- Works in isolated git worktree
- Owns producing working, test-passing diff
- Model: `xiaomi-token-plan-sgp/mimo-v2.5-pro`

### 2. Critic (GLM-5.2 via OpenRouter)
- Adversarially reviews builder's diff
- Different model than builder (independence)
- Returns PASS or specific problems
- Model: `z-ai/glm-5.2` via OpenRouter

### 3. Gates
- **Gate 0**: Plan Review (adversarial plan review)
- **Gate 1**: Tests (auto-detects stack, runs all suites)
- **Gate 2**: Adversarial Review (critic model reviews diff)
- **Gate 3**: Visual + Functional E2E (Playwright + Vision)

### 4. Quality Standards
- **Karpathy Principles**: Explicit > Implicit, Types everywhere, Small functions, No cleverness
- **Ponytail Rules**: Hexagonal architecture, Dependency inversion, Strict TS, TDD
- **Project Rules**: Strict TypeScript, explicit errors, conventional commits, TDD

## Project Structure
```
omp-agent/
├── .agents/                 # Ponytail agent instructions
│   ├── rules/               # Karpathy + Ponytail rules
│   ├── skills/              # Reusable skills (write-test, refactor, write-docs)
│   ├── contexts/            # Project context files
│   ├── templates/           # Prompt templates
│   └── ponytail.yaml        # Ponytail config
├── .omp/                    # omp configuration
├── tests/                   # Gate scripts
│   ├── gate.sh              # Gate 1: Tests
│   ├── gate0_plan_review.sh # Gate 0: Plan Review
│   ├── review_gate.sh       # Gate 2: Adversarial Review
│   ├── visual_gate.sh       # Gate 3: Visual/E2E
│   └── e2e/                 # Playwright specs
├── tests/e2e/               # Playwright specs
├── .agents/                 # Ponytail agent instructions
├── .omp/                    # omp configuration
├── design-system/           # Design tokens (optional)
├── tests/e2e/               # Playwright E2E specs
├── GUIDELINES.md            # Quality constitution
├── PLANNING.md              # Plan template
├── PLAN.md                  # Current plan (Gate 0 artifact)
├── requirements.md          # Project requirements
├── PIPELINE.md              # Pipeline documentation
├── CONFIG.md                # Model configuration
├── run-gates.sh             # Gate runner
├── pipeline.sh              # Automated orchestrator
├── scaffold.sh              # Factory script
├── .pre-commit-config.yaml  # Pre-commit hooks
├── ponytail.yaml            # Ponytail config
└── .agents/                 # Ponytail agent instructions
```

## Model Roles
| Role | Model | Provider |
|------|-------|----------|
| builder | mimo-v2.5-pro | Xiaomi MiMo |
| plan | mimo-v2.5 | Xiaomi MiMo |
| critic (Gate 2) | z-ai/glm-5.2 | OpenRouter |
| vision (Gate 3) | google/gemini-3.1-flash-lite | OpenRouter |

## Quality Gates
1. **Gate 0 (Plan Review)** — Adversarial plan review before any code
2. **Gate 1 (Tests)** — Auto-detect stack, run all test suites
3. **Gate 2 (Adversarial Review)** — Different model critiques diff
3. **Gate 3 (Visual/E2E)** — Playwright + Vision review

## Key Principles
- **Karpathy Principles**: Explicit > Implicit, Types everywhere, Small functions, No cleverness
- **Ponytail**: Hexagonal architecture, Dependency inversion, Strict TS, TDD
- **TDD**: Test first, implement, refactor, commit (one cycle = one commit)
- **Ponytail**: Portable agent instructions across IDEs

## Key Files
- `GUIDELINES.md` — Quality constitution
- `PLANNING.md` — Plan template
- `plan.md` — Current plan (Gate 0 artifact)
- `requirements.md` — Project requirements
- `PIPELINE.md` — Pipeline documentation
- `CONFIG.md` — Model configuration
- `run-gates.sh` — Gate runner
- `pipeline.sh` — Automated orchestrator
- `scaffold.sh` — Factory script
- `ponytail.yaml` — Ponytail config