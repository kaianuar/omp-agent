# GUIDELINES.md — omp-agent Project Quality Constitution

> This file defines the **non-negotiable quality standards** for the omp-agent project.
> It is the single source of truth for **Gate 0 (Plan Review)**, **Gate 2 (Adversarial Code Review)**,
> and **pre-commit hooks**. The builder, critic, and pre-commit hooks all reference this file.

---

## 1. CORE PHILOSOPHY — Karpathy Principles

> **Explicit > Implicit** — No magic, no hidden behavior, no hidden state.
> **Types Everywhere** — Type hints on all functions, variables, returns. No `any`/`Any` without explicit comment.
> **Small Functions** — One thing per function, <50 lines ideal. If it does two things, split it.
> **No Cleverness** — Boring code > clever code. Readability > cleverness.
> **Explicit Error Handling** — No bare `except:` / `catch (e) { }`. Handle errors explicitly.
> **Tests as Documentation** — Test names describe behavior, not implementation. AAA pattern.
> **No Magic Numbers** — Constants with descriptive names.

---

## 2. PORTABLE RULES — Ponytail (`/.agents/rules/`)

> These rules are exported to `/.agents/rules/` so they work across **any IDE agent**:
> Cursor, OpenCode, Claude Code, Codex, Devin, Qoder, Kiro, Grok, etc.

### 2.1 Architecture & Structure
- **Hexagonal Architecture** — Domain at center, adapters at edges (Repository, API, UI).
- **Dependency Inversion** — Domain depends on abstractions (ports), not concretions.
- **Single Responsibility** — Each module/class/function has one reason to change.
- **Composition over Inheritance** — Prefer composition, interfaces, strategy pattern.

### 2.2 Type Safety
- **Strict TypeScript** — `strict: true`, `noImplicitAny: true`, `strictNullChecks: true`.
- **Python** — `mypy --strict`, type hints on ALL public functions.
- **No `any` / `Any`** without explicit `// @ts-expect-error` + comment explaining why.

### 2.3 Naming Conventions
| Construct | Convention |
|---|---|
| Files | `kebab-case.ts` / `snake_case.py` |
| Classes/Interfaces | `PascalCase` |
| Functions/Variables | `camelCase` / `snake_case` |
| Constants | `UPPER_SNAKE_CASE` |
| Types/Interfaces | `PascalCase` (prefer `interface` over `type` for objects) |
| Private | `_prefix` (or `#private` in JS) |
| Boolean predicates | `is...`, `has...`, `can...`, `should...` |

### 2.4 Error Handling
- **No bare `catch` / `except:`** — Always catch specific errors.
- **Result/Option types** — Prefer `Result<T, E>` over throwing for expected errors.
- **Fail fast** — Validate inputs early, fail fast with descriptive messages.
- **Error context** — Wrap errors with context: `throw new Error('context', { cause: original })`.

### 2.5 Testing Standards
- **TDD is mandatory** — Test written FIRST (RED), then implementation (GREEN), then refactor.
- **Test naming** — `describe('feature', () => { it('should <behavior> when <condition>', ... })`
- **AAA Pattern** — Arrange, Act, Assert — clearly separated.
- **One assertion per test** (ideally) — or logically grouped assertions.
- **Deterministic** — No flaky tests, no time-based flakiness, no external dependencies.
- **Unit tests** — Fast, isolated, no I/O. **Integration tests** — Real DB, real API, clearly separated.
- **Coverage** — Aim for >80% on domain logic. 100% on critical paths.

### 2.6 Commit & Workflow Standards

### 4.1 Conventional Commits (enforced)
| Type | When to use |
|---|---|
| `feat:` | New feature for user |
| `fix:` | Bug fix |
| `refactor:` | Code restructuring, no behavior change |
| `test:` | Adding/updating tests |
| `docs:` | Documentation only |
| `chore:` | Maintenance (deps, config, CI) |
| `perf:` | Performance improvement |

**Format:** `type(scope): imperative description`
- `feat(auth): add JWT refresh token rotation`
- `fix(api): handle 401 on expired token gracefully`
- `refactor(db): extract repository base class`
- `test(auth): add integration tests for login flow`

### 4.2 TDD Workflow (enforced)
```
1. WRITE TEST (RED)     → Write failing test for the next behavior
2. IMPLEMENT (GREEN)    → Minimal code to make test pass
3. REFACTOR             → Clean up, extract, optimize (tests stay green)
4. COMMIT               → One logical change = one commit
```
- **One TDD cycle = one commit** (or small batch of tightly related cycles).
- No "test later" — test is written BEFORE implementation.

---

## 3. PROJECT-SPECIFIC RULES

### 3.1 Technology Stack
```yaml
language: "TypeScript"
framework: "Node.js + Vite + React"
testing: "vitest + playwright"
linting: "eslint + prettier"
typecheck: "tsc --strict"
```

### 3.2 Project-Specific Patterns
```markdown
- **Agent Framework**: omp (Oh My Pi) for multi-agent orchestration
- **Providers**: OpenRouter, Xiaomi MiMo, OpenCode Go
- **Models**: deepseek-v4-flash (builder), GLM-5.2 (critic), MiMo (builder/plan)
- **Testing**: vitest (unit) + playwright (e2e)
- **CI**: run-gates.sh (Gate 0: Plan, Gate 1: Tests, Gate 2: Adversarial Review, Gate 3: Visual/E2E)
```

### 3.3 Domain-Specific Rules
```markdown
- All agent interactions go through omp CLI
- Model roles configured in .omp/config.yml
- OpenRouter key in ~/.hermes/.env (loaded by run-gates.sh)
- Critic uses z-ai/glm-5.2 via OpenRouter
- Builder uses xiaomi-token-plan-sgp/mimo-v2.5-pro
- Plan phase: Gate 0 (plan review) before any code
- Build phase: TDD enforced, incremental commits
- Gate 0: Plan review (adversarial)
- Gate 1: Tests (auto-detect stack)
- Gate 2: Adversarial review (critic model different from builder)
- Gate 3: Visual/E2E (Playwright + vision model)
- Pre-commit hooks: Ruff + Prettier + tsc --strict
```

---

## 4. COMMIT & WORKFLOW STANDARDS

### 4.1 Conventional Commits (enforced)
| Type | When to use |
|---|---|
| `feat:` | New feature for user |
| `fix:` | Bug fix |
| `refactor:` | Code restructuring, no behavior change |
| `test:` | Adding/updating tests |
| `docs:` | Documentation only |
| `chore:` | Maintenance (deps, config, CI) |
| `perf:` | Performance improvement |

**Format:** `type(scope): imperative description`
- `feat(gate0): add adversarial plan review gate`
- `fix(run-gates): fix diff generation for review`
- `refactor(gate2): add ponytail rules to critic prompt`
- `test(gate0): add adversarial plan review test`

### 4.2 TDD Workflow (enforced)
```
1. WRITE TEST (RED)     → Write failing test for the next behavior
2. IMPLEMENT (GREEN)    → Minimal code to make test pass
3. REFACTOR             → Clean up, extract, optimize (tests stay green)
4. COMMIT               → One logical change = one commit
```
- **One TDD cycle = one commit** (or small batch of tightly related cycles).
- No "test later" — test is written BEFORE implementation.

---

## 4. PRE-COMMIT HOOKS (enforced)

See `.pre-commit-config.yaml` for the exact hooks. Summary:
- **Ruff** (Python) / **ESLint** (JS/TS) — linting
- **Prettier** — formatting (runs on staged files)
- **tsc --strict** — type checking
- **Conventional commit message** validation

**Run on every commit.** No bypassing.

---

## 5. CRITIC REVIEW CHECKLIST (Gate 2)

> The adversarial critic uses this checklist. **Any violation = FAIL** (production) or **NOTE** (MVP).

### Code Quality
- [ ] Types on ALL public functions (no implicit `any`)
- [ ] Functions < 50 lines (or justified)
- [ ] No `any` / `Any` without `// @ts-expect-error` + comment
- [ ] No bare `catch` / `except:`
- [ ] Error messages are descriptive (not "error occurred")
- [ ] No magic numbers/strings — constants with names
- [ ] No commented-out code
- [ ] No `console.log` / `print` in production code

### Architecture
- [ ] Domain logic has NO imports from adapters (infra, UI, API)
- [ ] Adapters implement domain ports (Repository, Presenter, etc.)
- [ ] No circular dependencies
- [ ] Single responsibility per module/class

### Testing
- [ ] Tests written FIRST (TDD)
- [ ] Test names describe BEHAVIOR (`should...when...`)
- [ ] AAA pattern (Arrange, Act, Assert)
- [ ] Edge cases covered (empty, null, boundary, error paths)
- [ ] No flaky tests (no time, random, external deps in unit tests)

### Security
- [ ] No secrets in code (API keys, passwords, tokens)
- [ ] Input validation on ALL boundaries (Zod / Pydantic)
- [ ] SQL injection prevention (parameterized queries / ORM)
- [ ] XSS prevention (auto-escaping in templates, CSP headers)

### Performance
- [ ] No N+1 queries (use eager loading / batching)
- [ ] Pagination on all list endpoints
- [ ] Caching strategy for expensive reads

---

## 6. PONYTAIL RULES (Exported to `/.agents/rules/`)

> These rules are exported to `/.agents/rules/` so **any IDE agent** (Cursor, OpenCode, Claude Code, Codex, Devin, Qoder, Kiro, Grok, etc.) can enforce them.

See `/.agents/rules/karpathy-ponytail-rules.md` for the complete rule set.

Key rules enforced:
- **Karpathy**: Explicit types, small functions, no cleverness, explicit errors
- **Ponytail**: Hexagonal architecture, dependency inversion, conventional commits, TDD
- **Project**: Strict TypeScript, explicit errors, conventional commits, TDD

---

## 8. KARPATHY PRINCIPLES (Embedded)

> **Explicit > Implicit** — No magic, no hidden behavior. Every dependency is explicit.
> **Types Everywhere** — Type hints on ALL functions, variables, returns. No `any`/`Any` without comment.
> **Small Functions** — One thing per function, <50 lines. If it does two things, split it.
> **No Cleverness** — Boring code > clever code. Readability over cleverness.
> **Explicit Error Handling** — No bare `except:` / `catch (e) { }`. Handle explicitly.
> **Tests as Documentation** — Test names describe BEHAVIOR (`should <do> when <condition>`), not implementation.
> **No Magic Numbers** — Named constants with descriptive names.
> **Explicit Dependencies** — Dependencies injected, not imported globally.
> **Fail Fast** — Validate early, fail fast with descriptive messages.
> **Explicit over Implicit Returns** — Return types explicit, no implicit returns.

---

*End of GUIDELINES.md*