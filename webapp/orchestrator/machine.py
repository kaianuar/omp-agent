"""Orchestrator state machine — drives phases + checkpoints.

Phases: idle → intake → research → design → (checkpoint) → recipe →
(checkpoint) → build → review → verify → (checkpoint) → report → idle.

The machine is driven by explicit method calls (the API layer triggers
transitions; user decisions at checkpoints arrive as `decide`).
"""
from __future__ import annotations

import json
from typing import Any

from webapp.data import db
from webapp.orchestrator import context as ctx
from webapp.orchestrator import phases
from webapp.pipeline import exec as pexec


class TaskRunner:
    """One task's lifecycle. Holds project config + task id."""

    def __init__(self, task_id: int, project: dict[str, Any]):
        self.task_id = task_id
        self.project = project
        self.repo_path = project["repo_path"]
        self.scratch_dir = project["scratch_path"]

    # ── event sink ─────────────────────────────────────────────────────
    def _sink(self, task_id: int, kind: str, payload: dict[str, Any]) -> None:
        db.add_event(task_id, kind, payload)

    # ── transitions ────────────────────────────────────────────────────

    def start(self, user_message: str) -> None:
        """From IDLE: create task (intake) — called by API on new task."""
        intent = phases.run_intake(
            self.task_id, user_message, self._brief(), self._sink
        )
        db.update_task_state(self.task_id, "intake")
        # Persist the intent JSON onto the task row.
        db.add_event(self.task_id, "intake_done", {"intent": intent})
        if intent.get("uncertainty"):
            db.update_task_state(self.task_id, "awaiting_clarify")
            # The API surfaces the questions to the user.
            db.add_event(
                self.task_id,
                "clarify_needed",
                {"questions": intent["uncertainty"]},
            )
        else:
            self._to_design(intent)

    def clarify_answered(self, answers: str) -> None:
        """User answered the clarifying questions → re-run intake."""
        task = self._task()
        intent = json.loads(task["intent"] or "{}")
        intent["answers"] = answers
        db.update_task_state(self.task_id, "intake")
        self._to_design(intent)

    def _to_design(self, intent: dict[str, Any]) -> None:
        db.update_task_state(self.task_id, "design")
        design_path = phases.run_design(
            self.task_id,
            intent,
            self.repo_path,
            self.scratch_dir,
            self._brief(),
            self._sink,
        )
        db.update_task_state(self.task_id, "awaiting_design_approval", design_path=design_path)

    def design_decided(self, decision: str, note: str = "") -> None:
        """CHECKPOINT 1 — approve → recipe; reject/adjust → design again.

        Reject carries the user's feedback in `note`; it's merged into the
        intent so the regenerated design addresses it (the adjust path).
        """
        if decision == "approve":
            self._to_recipe()
        else:
            db.update_task_state(self.task_id, "design")
            self._sink(self.task_id, "design_rejected", {"note": note})
            intent = self._last_intent()
            if intent:
                if note.strip():
                    intent["feedback"] = note.strip()
                self._to_design(intent)

    def _to_recipe(self) -> None:
        task = self._task()
        design = _read_file(task.get("design_path")) if task.get("design_path") else ""
        db.update_task_state(self.task_id, "recipe")
        recipe_path = phases.run_recipe(
            self.task_id,
            self._last_intent(),
            design,
            self.repo_path,
            self.scratch_dir,
            self._brief(),
            self._sink,
        )
        db.update_task_state(self.task_id, "awaiting_recipe_approval", recipe_path=recipe_path)

    def recipe_decided(self, decision: str) -> None:
        """CHECKPOINT 2 — approve (or skip) → build."""
        if decision == "approve":
            self._to_build()

    def _to_build(self) -> None:
        task = self._task()
        recipe = _read_file(task.get("recipe_path")) if task.get("recipe_path") else ""
        db.update_task_state(self.task_id, "building")
        # Dispatch builder; v1: blocking call (runs omp), emits events.
        build = pexec.dispatch_build(
            self.task_id, self.repo_path, self.scratch_dir, recipe, self._sink
        )
        # Build failed (non-zero / timeout / missing) → surface an error.
        if build.get("exit_code", 0) != 0:
            self._sink(self.task_id, "error", {
                "note": f"build failed (exit {build.get('exit_code')}): {build.get('output', '')[-400:]}",
            })
            db.update_task_state(self.task_id, "error")
            return
        # REVIEW → auto-fix loop: critic FAIL (P0/P1) → re-dispatch builder
        # with verdicts as context → re-review, up to MAX_FIX_ROUNDS.
        db.update_task_state(self.task_id, "reviewing")
        for round_no in range(1, pexec.MAX_FIX_ROUNDS + 1):
            pr_url, diff = pexec.get_pr_diff(self.repo_path)
            if not pr_url:
                self._sink(self.task_id, "no_pr", {"note": "no open PR found for review"})
                break
            self._sink(self.task_id, "pr_ready", {"url": pr_url, "diff": diff[-4000:]})
            db.update_task_state(self.task_id, "reviewing", pr_url=pr_url)
            verdict = phases.run_review(self.task_id, pr_url, diff, self._sink)
            if verdict["passed"]:
                self._sink(self.task_id, "critic_passed", {"round": round_no})
                break
            if round_no >= pexec.MAX_FIX_ROUNDS:
                # Escalate to user after max rounds (don't loop forever).
                db.update_task_state(self.task_id, "awaiting_fix_decision")
                self._sink(self.task_id, "fix_exhausted", {"verdict": verdict["text"]})
                return
            # Fix round: re-dispatch builder with the critic's verdicts.
            self._sink(self.task_id, "fix_round_started", {"round": round_no})
            db.update_task_state(self.task_id, "fixing")
            pexec.dispatch_fix_round(
                self.task_id, self.repo_path, self.scratch_dir,
                recipe, verdict["text"], self._sink,
            )
        # VERIFY: run the recipe's verification commands.
        db.update_task_state(self.task_id, "verifying")
        pexec.run_verify(
            self.task_id, self.repo_path, recipe, self._sink
        )
        db.update_task_state(self.task_id, "awaiting_result")

    # ── helpers ────────────────────────────────────────────────────────

    def _task(self) -> dict[str, Any]:
        task = db.get_task(self.task_id)
        if task is None:
            raise RuntimeError(f"task {self.task_id} not found")
        return task

    def _brief(self) -> str:
        return ctx.assemble_brief(self.repo_path, self._last_intent_raw())

    def _last_intent_raw(self) -> str:
        task = self._task()
        return task.get("intent") or ""

    def _last_intent(self) -> dict[str, Any]:
        task = self._task()
        try:
            return json.loads(task.get("intent") or "{}")
        except json.JSONDecodeError:
            return {}


def _read_file(path: str | None) -> str:
    if not path:
        return ""
    from pathlib import Path

    p = Path(path)
    return p.read_text(encoding="utf-8") if p.exists() else ""
