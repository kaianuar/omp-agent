"""Orchestrator phases — one function per phase (ORCHESTRATOR_BRAIN.md).

Each phase: takes (task state, project config, event sink) and returns
the next state + emitted events. Pure-ish: LLM calls via llm.chat, writes
via sandbox.sandboxed_write. No web knowledge.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from webapp.orchestrator import context as ctx
from webapp.orchestrator import llm, prompts
from webapp.pipeline import sandbox

# Event sink: (task_id, kind, payload) -> None
EventSink = Callable[[int, str, dict[str, Any]], None]


def _emit(sink: EventSink, task_id: int, kind: str, payload: dict[str, Any]) -> None:
    sink(task_id, kind, payload)


def run_intake(
    task_id: int, user_message: str, brief: str, sink: EventSink
) -> dict[str, Any]:
    """INTAKE — extract the Intent object from the raw message."""
    system, user = prompts.intake_prompt(user_message)
    raw = llm.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
    )
    try:
        intent = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: wrap in a best-effort parse (strip code fences).
        cleaned = raw.strip().strip("`").removeprefix("json").strip()
        intent = json.loads(cleaned)

    _emit(sink, task_id, "intake", {"intent": intent})
    return intent


def run_design(
    task_id: int,
    intent: dict[str, Any],
    repo_path: str,
    scratch_dir: str,
    brief: str,
    sink: EventSink,
) -> str:
    """DESIGN — write design.md to scratch, emit design_ready."""
    # Research = context (AGENTS.md, backlogs, code hints). For v1 this is
    # the brief + a note; deeper code research comes later.
    research = brief
    system, user = prompts.design_prompt(brief, intent, research)
    design = llm.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.4,
        max_tokens=4000,
    )
    path = sandbox.sandboxed_write(scratch_dir, repo_path, "design.md", design)
    _emit(sink, task_id, "design_ready", {"path": str(path), "content": design})
    return str(path)


def run_recipe(
    task_id: int,
    intent: dict[str, Any],
    design_doc: str,
    repo_path: str,
    scratch_dir: str,
    brief: str,
    sink: EventSink,
) -> str:
    """RECIPE — convert approved design into builder-ready recipe.md."""
    # Recipe generation is output-heavy; the recipe prompt already carries
    # architecture context + the design doc. Injecting the full L0-L3 brief
    # (34KB) makes MiMo return empty content — skip it entirely.
    system, user = prompts.recipe_prompt("", design_doc, intent)
    recipe = llm.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
        max_tokens=6000,
        model=llm.RECIPE_MODEL,
    )
    path = sandbox.sandboxed_write(scratch_dir, repo_path, "recipe.md", recipe)
    _emit(sink, task_id, "recipe_ready", {"path": str(path), "content": recipe})
    return str(path)


def _trim_brief(brief: str, max_chars: int = 8000) -> str:
    """Keep the head of the brief (charter + prefs), drop the deep backlog."""
    if len(brief) <= max_chars:
        return brief
    # Keep the first (charter) and last (preferences) sections.
    return brief[:max_chars] + "\n\n...[truncated for recipe generation]"


def run_review(
    task_id: int,
    pr_url: str,
    diff: str,
    sink: EventSink,
    model: str | None = None,
) -> dict[str, Any]:
    """REVIEW — critic (read-only) reviews the PR diff → P0-P4 verdicts.

    Emits critic_verdict with the raw text + PASS/FAIL. The machine decides
    whether to fix-round (P0/P1) or surface to the user (P2+).
    """
    system, user = prompts.review_prompt(pr_url, diff)
    verdict_text = llm.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.1,
        max_tokens=3000,
        model=model or llm.CRITIC_MODEL,
    )
    passed = "VERDICT: PASS" in verdict_text.upper()
    _emit(sink, task_id, "critic_verdict", {"passed": passed, "text": verdict_text})
    return {"passed": passed, "text": verdict_text}
