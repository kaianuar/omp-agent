"""Prompt builders for the orchestrator phases.

Each returns a (system, user) message pair. Templates are inline strings
for v1 (parameterized); they move to templates/ files when they stabilize.
"""
from __future__ import annotations

import json

ORCH_SYSTEM = (
    "You are the orchestrator for a local AI product builder. You design, "
    "plan, dispatch builds, and verify — you NEVER write code into the "
    "project yourself. You are a calm senior engineer briefing a colleague. "
    "Plain language, no hype, no AI-slop. The user owns product vision; "
    "you propose, they dispose.\n\n"
    "{brief}"
)


def intake_prompt(user_message: str) -> tuple[str, str]:
    system = (
        "Extract the user's intent as JSON with EXACTLY these keys: "
        "kind (feature|bugfix|idea|question|feedback-on-existing), "
        "goal (one sentence), constraints (array of strings, empty if none), "
        "acceptance (how we'd know it's done, or null), "
        "urgency (now|this-session|backlog), "
        "uncertainty (array of clarifying questions, empty if clear). "
        "Reply with ONLY the JSON object."
    )
    return system, user_message


def design_prompt(
    brief: str, intent: dict, research: str
) -> tuple[str, str]:
    system = ORCH_SYSTEM.format(brief=brief)
    user = (
        "Design a solution for this intent (JSON):\n"
        f"{json.dumps(intent, indent=2)}\n\n"
        "Research notes:\n"
        f"{research}\n\n"
        "Produce a design doc with this EXACT structure:\n"
        "# Design: <title>\n"
        "## Context (2-4 sentences)\n"
        "## Options considered (2-4 with tradeoffs)\n"
        "## Decision (chosen option + why, one paragraph)\n"
        "## Scope (files/areas touched — NOT line-level)\n"
        "## Edge cases & risks\n"
        "## Open questions (things the user must decide)\n"
        "## Effort estimate (S/M/L + omp sessions)\n"
    )
    return system, user


def recipe_prompt(
    brief: str, design_doc: str, intent: dict
) -> tuple[str, str]:
    system = ORCH_SYSTEM.format(brief=brief)
    user = (
        "Convert this approved design into a builder-ready recipe.\n\n"
        "DESIGN DOC:\n"
        f"{design_doc}\n\n"
        "RECIPE FORMAT (follow exactly):\n"
        "# Recipe: <title>\n"
        "## Workflow requirements (FIRST):\n"
        "  - branch off main: git checkout main && git pull && git checkout -b <branch>\n"
        "  - incremental commits (one logical change = one commit, conventional msgs)\n"
        "  - finish: push + gh pr create\n"
        "## Architecture context (what the builder must know)\n"
        "## Implementation (STEP 1..N):\n"
        "  ### Step N (commit: <type>(<scope>): <msg>)\n"
        "  - EXACT file paths, EXACT changes (signatures, structs, names)\n"
        "  - Where to register (invoke_handler, exports, routes)\n"
        "  - Test requirements (which tests, naming convention)\n"
        "## Verify before pushing:\n"
        "  - fmt / clippy / test commands (exact)\n"
        "  - Manual verification steps (exact commands)\n"
        "  - Expected test counts (what 'pass' means)\n\n"
        "The builder must NEVER need to 'figure something out' — if it's "
        "ambiguous, the recipe failed. Be exhaustive."
    )
    return system, user


def clarify_prompt(intent: dict, questions: list[str]) -> tuple[str, str]:
    system = (
        "You are the orchestrator. The user's request is ambiguous. Ask the "
        "clarifying questions in a friendly, plain way. Keep it short — "
        "one message, the questions as a numbered list. No preamble."
    )
    user = (
        f"Intent so far: {json.dumps(intent, indent=2)}\n"
        f"Questions to ask:\n" + "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
    )
    return system, user
