# PIPELINE — the operating loop omp follows

This file defines HOW you work in this repo. Load it as context on every run.
There is one overall goal (in `requirements.md`). You drive it to completion
following this exact loop. If anything is ambiguous, stop and ask.

## Roles (use omp subagents, different models via modelRoles)

- **builder** — implements code + tests. The default model (e.g. deepseek-v4-flash).
  Works in an isolated git worktree. Owns producing a working, test-passing diff.
- **critic** — adversarially reviews the builder's diff. Use a DIFFERENT model
  than builder via omp's `modelRoles` / `--model` override (e.g. deepseek-v4-pro
  or kimi / GLM). Fresh context. Harsh, concrete, never lenient. Returns PASS or
  a list of specific problems.
- **you (me)** — the human. Final approval at the steer checkpoint.

## omp configuration reference (verified)

- Global settings: `~/.omp/agent/config.yml` (`modelRoles: {smol, slow, plan, commit}`).
- Project-local overrides: `<cwd>/.omp/config.yml` (loaded when `.omp/` exists).
- CLI model flags: `--model <default>`, `--smol`, `--slow`, `--plan`.
- Critic with a different model: launch with `--model <model B>` (or set a
  dedicated role in `modelRoles` and invoke via that role).
- Non-interactive automation: `omp --mode rpc` (JSONL protocol over stdio).
- Plan/steer gate: `--plan` mode forces a planning step before code.


## The loop (in order, no skipping)

1. **PLAN (plan mode).** Read `requirements.md`. Break the goal into concrete
   work: build / test / design. Show me the plan BEFORE any code is written.
   Do not start implementing without my OK on the plan.

2. **BUILD.** builder implements the feature + tests, following the UI rules in
   `design-system/` (consistency gate).

3. **HARD QUALITY GATE — `run-gates.sh` (non-skippable).** After BUILD, run
   `./run-gates.sh`. It runs BOTH gates in sequence:
   - **GATE 1 — TESTS:** `tests/gate.sh` auto-detects the stack(s) and runs the
     matching test command(s) — including BOTH frontend and backend for a full-stack
     project (e.g. `client/` + `server/`). Must exit 0 (all suites green).
   - **GATE 2 — ADVERSARIAL REVIEW:** `tests/review_gate.sh` has a DIFFERENT model
     (the critic) review the diff. Must pass.
   - **MANDATORY:** `run-gates.sh` MUST exit 0 before ANY steer/commit. If it fails,
     the pipeline HALTS and the builder must fix, then re-run `run-gates.sh`.
   - Never proceed past a red gate. Never edit a test to make it pass unless the
     test itself is wrong AND you can justify it. Do NOT skip Gate 2 — a self-review
     by the builder is NOT a substitute; it must be a different model.
   - **Do NOT review the code yourself.** The adversarial review must be done by the
     SEPARATE critic process that `tests/review_gate.sh` launches (`omp --print
     --model z-ai/glm-5.2`). Your own analysis of your own code is not the gate. Run
     `./run-gates.sh` and let the independent critic do the review; do not improvise
     a self-review.
   - Do not hand-edit a test command into `tests/gate.sh` — let it auto-detect. If a
     suite isn't detected, tell me rather than forcing one.

4. **STEER CHECKPOINT.** Stop. Show me the complete diff + a 2-line summary of
   what changed and why. I approve (then you commit) or redirect you. Do NOT
   commit or merge before this approval.

## UI rules (loaded from design-system/)

- Every screen/component MUST consume tokens from `design-system/tokens.json`.
- No hard-coded colors/spacing/typography outside the token file.
- Do not invent a visual style — follow the seeded design direction. If the goal
  needs unique assets, source them via the configured image-gen path and wire them
  in (do not fabricate a unique look from scratch).

## Hard rules
- Never trust the model's self-reported pass. GATE 1 runs real tests; only a
  green `gate.sh` counts as green.
- One logical change per commit. Commit incrementally.
- If you're unsure or blocked > threshold, stop and ask me rather than guessing.
- Keep the diff minimal and readable.
