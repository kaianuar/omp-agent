"""Pipeline exec — talks to the real world.

- dispatch_build: runs omp (the builder) with the recipe, monitors, emits
  build events.
- run_verify: runs the recipe's verification commands (fmt/clippy/tests),
  emits verify_result.

All side effects (subprocess, scratch writes) live here — never in the
orchestrator phases. The orchestrator stays pure.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any, Callable

EventSink = Callable[[int, str, dict[str, Any]], None]

BUILD_TIMEOUT_S = int(os.environ.get("OMP_BUILD_TIMEOUT_S", "1500"))
VERIFY_TIMEOUT_S = int(os.environ.get("OMP_VERIFY_TIMEOUT_S", "600"))

# Max critic fix rounds before escalating to the user (don't loop forever).
MAX_FIX_ROUNDS = int(os.environ.get("OMP_MAX_FIX_ROUNDS", "3"))


def _run(cmd: list[str], cwd: str, timeout: int) -> tuple[int, str]:
    """Run a command, return (exit_code, combined_output)."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out[-4000:]
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s"
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"


def _builder_cmd(recipe_path: str, repo_path: str) -> list[str]:
    """Build the omp invocation from the recipe file.

    The recipe text is INLINED into --append-system-prompt (omp takes the
    prompt text, not a file reference).
    """
    from pathlib import Path

    recipe = Path(recipe_path).read_text(encoding="utf-8") if Path(recipe_path).exists() else ""
    env = dict(os.environ)
    env["PATH"] = os.path.expanduser("~/.bun/bin") + os.pathsep + env.get("PATH", "")
    model = os.environ.get("OMP_BUILDER_MODEL", "commandcode/xiaomi/mimo-v2.5-pro")
    return [
        "omp",
        "--print",
        "--model",
        model,
        "--append-system-prompt",
        recipe,
        "Apply this recipe exactly. Follow the workflow requirements (branch off main, incremental commits, PR). Run the verification steps. Report when done.",
    ]


def _run_streaming(
    cmd: list[str], cwd: str, timeout: int, task_id: int, sink: EventSink
) -> tuple[int, str]:
    """Run a command, reading output line-by-line and emitting progress events.

    Emits `build_progress` for lines that look like omp milestones (commits,
    phase transitions, PR creation) so the UI shows live build progress
    instead of a silent wait.
    """
    import subprocess

    proc = subprocess.Popen(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    lines: list[str] = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            lines.append(line)
            _maybe_emit_progress(task_id, sink, line)
        proc.wait(timeout=timeout)
        return proc.returncode, "\n".join(lines)[-4000:]
    except subprocess.TimeoutExpired:
        proc.kill()
        return 124, "TIMEOUT after %ss" % timeout
    except FileNotFoundError:
        return 127, "command not found: %s" % cmd[0]


def _maybe_emit_progress(task_id: int, sink: EventSink, line: str) -> None:
    """Emit a build_progress event for omp milestone lines."""
    low = line.lower()
    if any(m in low for m in ("commit", "branch", "pr:", "working", "done.", "feat(", "fix(")):
        sink(task_id, "build_progress", {"line": line[:300]})


def dispatch_build(
    task_id: int, repo_path: str, scratch_dir: str, recipe: str, sink: EventSink
) -> dict[str, Any]:
    """Run the builder (omp) with the recipe. Emits build events.

    The recipe is written to the project's scratch dir first (the only file
    the builder needs to read) — but the builder writes code into the repo,
    which is its job. Output streams line-by-line → build_progress events.
    """
    # Write recipe to scratch so the builder has a stable path to read.
    from webapp.pipeline import sandbox

    recipe_path = sandbox.sandboxed_write(scratch_dir, repo_path, "recipe.md", recipe)
    sink(task_id, "build_started", {"recipe_path": str(recipe_path)})
    cmd = _builder_cmd(str(recipe_path), repo_path)
    code, output = _run_streaming(cmd, repo_path, BUILD_TIMEOUT_S, task_id, sink)
    sink(task_id, "build_done", {"exit_code": code, "output": output})
    return {"exit_code": code, "output": output}


def run_verify(task_id: int, repo_path: str, recipe: str, sink: EventSink) -> dict[str, Any]:
    """Run the recipe's verification commands (heuristic for v1).

    v1: extracts ```-fenced shell blocks from the recipe and runs them.
    This is crude but works for the recipes we author (they contain exact
    verify commands). Refine later (structured verify steps in the recipe).
    """
    import re

    results = []
    for block in re.findall(r"```(?:sh|bash)?\n(.*?)```", recipe, re.S):
        for line in block.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            code, output = _run(["bash", "-lc", line], repo_path, VERIFY_TIMEOUT_S)
            results.append({"cmd": line, "exit_code": code, "output": output[-800:]})
            sink(task_id, "verify_step", {"cmd": line, "exit_code": code})
    sink(task_id, "verify_result", {"results": results})
    return {"results": results}


def get_pr_diff(repo_path: str) -> tuple[str | None, str]:
    """Get the current branch's PR diff via gh.

    Returns (pr_url, diff). pr_url is None if no PR/open branch.
    """
    code, out = _run(["gh", "pr", "view", "--json", "url,number", "--jq", ".url"], repo_path, 30)
    pr_url = out.strip() if code == 0 and out.strip() else None
    if not pr_url:
        return None, ""
    code2, diff = _run(["gh", "pr", "diff"], repo_path, 60)
    if code2 != 0:
        return pr_url, f"(could not fetch diff: {diff[:200]})"
    return pr_url, diff[-40000:]


def dispatch_fix_round(
    task_id: int, repo_path: str, scratch_dir: str,
    recipe: str, verdicts: str, sink: EventSink,
) -> dict[str, Any]:
    """Fix round: re-dispatch the builder with the critic's verdicts.

    The recipe + verdicts are inlined; the builder fixes the PR's issues.
    "PRESERVE all existing code" is enforced (the deletion-guard lesson).
    """
    from webapp.pipeline import sandbox

    fix_prompt = (
        "The critic found blocking issues in your PR. Fix ALL of them.\n\n"
        "=== ORIGINAL RECIPE ===\n"
        f"{recipe}\n\n"
        "=== CRITIC VERDICTS (P0/P1 = must fix; also address P2 where easy) ===\n"
        f"{verdicts}\n\n"
        "RULES:\n"
        "- PRESERVE all existing code. Do NOT delete or rewrite unrelated code.\n"
        "- STAY ON the current branch — do NOT create or switch branches. "
        "Amend/extend the existing PR with new commits on THIS branch.\n"
        "- Run the verification steps after fixing; ensure all tests pass.\n"
        "- Report what you fixed."
    )
    fix_path = sandbox.sandboxed_write(scratch_dir, repo_path, "fix_round.md", fix_prompt)
    sink(task_id, "fix_round_started", {"round_path": str(fix_path)})
    cmd = _builder_cmd(str(fix_path), repo_path)
    code, output = _run(cmd, repo_path, BUILD_TIMEOUT_S)
    sink(task_id, "fix_round_done", {"exit_code": code, "output": output[-2000:]})
    return {"exit_code": code, "output": output}
