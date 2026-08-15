# USAGE — run the omp-agent pipeline yourself

This is the cheat-sheet for actually **driving the pipeline with omp**, end to end,
from your own terminal. You don't need an orchestrator or another agent — just omp.

---

## 0. Prereqs (first time on a machine)

```bash
# omp on PATH (add to ~/.bashrc then `source ~/.bashrc`)
export PATH="$HOME/.bun/bin:$PATH"

# provider keys available to omp (env or omp secrets)
export OPENROUTER_API_KEY="sk-or-..."      # critic
export XIAOMI_API_KEY="..."                # builder (or use any builder you have)
export XIAOMI_BASE_URL="https://api.xiaomimimo.com/v1"

# sanity: is omp working?
omp --version
```

---

## 1. Scaffold a new project

```bash
cd ~/code/omp-agent
./scaffold.sh ~/code/my-new-app --ui     # --ui copies design tokens; --no-git to skip git init
cd ~/code/my-new-app
```

Now edit **`requirements.md`** with your goal (what to build, for whom, acceptance
criteria). That's the only input the pipeline needs.

---

## 2. Run the PIPELINE automatically (recommended)

The **`pipeline.sh`** orchestrator closes the loop for you: it runs the builder,
runs BOTH gates (including the independent adversarial critic), and if the critic
fails, it **automatically feeds the findings back to the builder to fix and re-runs**
— so you never copy-paste the review output.

```bash
export PATH="$HOME/.bun/bin:$PATH"
BUILDER_MODEL="xiaomi-token-plan-sgp/mimo-v2.5-pro" ./pipeline.sh requirements.md
```

It loops until all gates pass (or `MAX_ROUNDS`, default 5, then stops for you).
Options:
- `MAX_ROUNDS=8 ./pipeline.sh ...`  — allow more fix rounds
- `BUILDER_MODEL="..." ./pipeline.sh ...` — set your builder model

## 2b. Run omp manually (step-by-step, if you prefer control)

The same loop but with you driving each step. Interactive — omp plans, waits for
your approval, builds, and stops at the steer checkpoint:

```bash
omp --model <builder-model> \
    --append-system-prompt=PIPELINE.md \
    --append-system-prompt=requirements.md
```
(Loading the two files as context means omp follows the PIPELINE loop against your
goal. The `--append-system-prompt=` form avoids the leading-`@` arg, which trips
zsh's auto-correct. Inside an omp session you can also just type `@PIPELINE.md` and
`@requirements.md` to load them.)

**One-shot / non-interactive** (fires and prints, no waiting):
```bash
omp --model <builder-model> --print \
    --append-system-prompt=PIPELINE.md \
    --append-system-prompt=requirements.md
```

**Builder model:** use your validated builder, e.g. `xiaomi-token-plan-sgp/mimo-v2.5-pro`,
or whatever you set in `.omp/config.yml` / your omp config.

---

## 3. What happens (the PIPELINE loop)

1. **PLAN** — omp reads the goal, proposes a plan, and **waits for your approval**
   (interactive). Approve or redirect in the session.
2. **BUILD** — the builder agent implements the code (and tests).
3. **HARD QUALITY GATE — `run-gates.sh`**:
   - **GATE 1 — TESTS.** `tests/gate.sh` auto-detects the stack(s) and runs the
     matching test command(s) — root + `client/` + `server/` for full-stack. Must pass.
   - **GATE 2 — ADVERSARIAL REVIEW.** `tests/review_gate.sh` runs an **independent**
     critic (a DIFFERENT model, e.g. GLM-5.2) that reviews the diff. Must pass.
   - The builder MUST NOT self-review; the critic is a separate process.
4. **FEEDBACK LOOP (automatic via `pipeline.sh`).** If Gate 2 fails, the critic's
   findings are saved and **fed back to the builder** to fix, then gates run again —
   repeat until green (or MAX_ROUNDS).
5. **STEER** — the built work is shown and **waits for your approval before committing**.
6. **DONE.**

You steer at the approval points by replying (e.g. "approve", "change X", "continue").

---

## 4. The critic (adversarial reviewer)

The critic lives in **`tests/review_gate.sh`** and defaults to `z-ai/glm-5.2` (OpenRouter).
Run it yourself with a different critic model via the env var:
```bash
CRITIC_MODEL="your/critic-model" ./tests/review_gate.sh     # or set the default in the script
```
It must differ from the builder (that's the whole point — independent review).

---

## 5. Common steering commands

Inside an omp session you mainly:
- **Approve a plan:** "approve, proceed"
- **Change direction:** "don't use X, use Y because ..."
- **Point out a mistake:** "that's wrong, here's why, fix it"
- **Final okay to commit:** "looks good, commit"

---

## 6. Note: it's interactive-by-design

omp does **not** run hands-free in one shot. It stops at the **plan approval** and the
**steer checkpoint** for you to sign off. That's the deliberate human-in-the-loop —
see the "why" in the README. For a fully unattended run, omp's `--print` mode will
execute and exit, but you'll want to supervise the gates.

---

## 7. Quick troubleshooting

| Symptom | Fix |
|---|---|
| `omp: command not found` | `export PATH="$HOME/.bun/bin:$PATH"` |
| zsh asks `correct '@PIPELINE.md' to 'PIPELINE.md'?` | zsh auto-correct — answer `n`, or use `--append-system-prompt=PIPELINE.md` (no leading `@`), or `unsetopt correct_all` |
| Empty model output / "finish: length" | needs higher `max_tokens` (>=4000) for reasoning models |
| Gate says "0 suites run" | put test files at the repo root / sub-dirs the gate checks (client, server) |
| Critic returns nothing | CRITIC_MODEL not set / keys missing; ensure OpenRouter key present |
| No tests detected | the gate fails-closed by design — add tests |

See `CONFIG.md` for the validated model choices + rules.
