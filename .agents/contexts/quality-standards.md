# Ponytail Context — Quality Standards

## Quality Standards for All Agents

This context file defines the quality standards that ALL agents (Claude Code, Cursor, OpenCode, Codex, Devin, Qoder, Kiro, Grok, etc.) must follow when working on this project.

## Quality Standards

### Karpathy Principles (Mandatory)
1. **Explicit > Implicit** — No magic, no hidden behavior, no hidden state
2. **Types Everywhere** — Type hints on ALL functions, variables, returns. No `any`/`Any` without explicit comment
3. **Small Functions** — One thing per function, <50 lines ideal
4. **No Cleverness** — Boring code > clever code. Readability > cleverness
5. **Explicit Error Handling** — No bare `catch` / `except:`. Handle errors explicitly with context
6. **Tests as Documentation** — Test names describe BEHAVIOR (`should <do> when <condition>`), not implementation
7. **No Magic Numbers** — Named constants with descriptive names
8. **Explicit Dependencies** — Dependencies injected, not imported globally
9. **Fail Fast** — Validate early, fail fast with descriptive messages
10. **Explicit Returns** — Return types explicit, no implicit returns

### Ponytail Rules (Mandatory)
1. **Hexagonal Architecture** — Domain at center, adapters at edges
2. **Dependency Inversion** — Domain depends on abstractions, not concretions
3. **Strict TypeScript** — `strict: true`, `noImplicitAny: true`, `strictNullChecks: true`
4. **Conventional Commits** — `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, `perf:`
5. **TDD Mandatory** — Test first, then implement, then refactor
6. **One Change Per Commit** — One logical change per commit
6. **Strict TypeScript** — `strict: true`, `noImplicitAny: true`, `strictNullChecks: true`
7. **No `any` / `Any`** without explicit comment
8. **No Bare Catch** — No bare `catch` / `except:`
9. **Explicit Errors** — Explicit error handling with context
9. **No Magic Numbers** — Named constants with descriptive names
10. **Explicit Errors** — Explicit error handling with context

---

## Project-Specific Rules

### Architecture
- **Hexagonal Architecture** — Domain at center, adapters at edges
- **Domain** — Zero external dependencies, pure business logic
- **Adapters** — Implement domain ports (Repository, API, UI, etc.)

### Technology Stack
- **Language**: TypeScript
- **Framework**: Node.js + Vite + React
- **Testing**: vitest + playwright
- **Linting**: eslint + prettier
- **Typecheck**: tsc --strict

### Quality Gates
- **Gate 0**: Plan Review (adversarial plan review)
- **Gate 1**: Tests (auto-detect stack, run all suites)
- **Gate 2**: Adversarial Review (different model critic)
- **Gate 3**: Visual + Functional E2E (Playwright + Vision)

### Commit Standards
- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, `perf:`
- One logical change per commit
- Imperative mood: "add feature" not "added feature"

### TDD Workflow
1. WRITE TEST (RED) → Write failing test
2. IMPLEMENT (GREEN) → Minimal code to pass
3. REFACTOR → Clean up, extract, optimize
4. COMMIT → One logical change = one commit