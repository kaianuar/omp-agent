"""Context pack assembly (L0-L3 from ORCHESTRATOR_BRAIN.md).

L0: project charter — AGENTS.md + product one-pager (static).
L1: project state — backlogs, design docs, current PR/branch state.
L2: work history — past tasks (searched on demand).
L3: user preferences — global, small.

Assembled into a single "session brief" string injected into the
orchestrator's system prompt.
"""
from __future__ import annotations

from pathlib import Path

USER_PREFERENCES = """\
- Tone: plain, concrete, no hype, no AI-slop. Short sentences.
- Style: TDD, incremental commits, evidence over opinion.
- Cost: cheapest viable model; watch spend.
- The user owns product vision; the orchestrator proposes, the user disposes.
- Never change code directly; never write into the project repo.
"""


def _read_trim(path: Path, max_chars: int = 6000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:max_chars]


def load_project_charter(repo_path: str, max_chars: int = 6000) -> str:
    """L0 — AGENTS.md + any product one-pager."""
    repo = Path(repo_path)
    parts = []
    for name in ("AGENTS.md", "README.md"):
        text = _read_trim(repo / name, max_chars)
        if text:
            parts.append(f"--- {name} ---\n{text}")
    return "\n\n".join(parts)


def load_project_state(repo_path: str, max_chars: int = 8000) -> str:
    """L1 — backlogs + design docs (gitignored working notes live in repo)."""
    repo = Path(repo_path)
    parts = []
    # Backlogs (may not exist — optional)
    for name in ("FEATURE_BACKLOG.md", "UI_BACKLOG.md", "DUPES_UI_DESIGN.md"):
        text = _read_trim(repo / name, max_chars)
        if text:
            parts.append(f"--- {name} ---\n{text}")
    return "\n\n".join(parts)


def load_work_history(task_intent: str, limit: int = 5) -> str:
    """L2 — recent past tasks matching the intent (from SQLite)."""
    from webapp.data import db

    try:
        events = db.list_recent_tasks(limit)
    except Exception:
        return ""
    if not events:
        return ""
    lines = []
    for e in events:
        lines.append(f"- [{e.get('created_at', '')}] {e.get('intent', '')[:80]} → {e.get('state', '')}")
    return "\n".join(lines)


def assemble_brief(repo_path: str, task_intent: str) -> str:
    """Assemble the full session brief for the orchestrator."""
    sections = [
        "# PROJECT CHARTER (L0)",
        load_project_charter(repo_path),
        "\n# PROJECT STATE (L1)",
        load_project_state(repo_path),
        "\n# WORK HISTORY (L2)",
        load_work_history(task_intent) or "(no prior tasks)",
        "\n# USER PREFERENCES (L3)",
        USER_PREFERENCES,
    ]
    return "\n\n".join(sections)
