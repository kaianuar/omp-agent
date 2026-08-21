"""Sandbox — permission checks for orchestrator actions.

The orchestrator may:
- read anywhere (files, git log, tests)
- run anywhere (build, test, scan)
- write ONLY to scratch (never the project repo)

`sandboxed_write` is the single entry point for any orchestrator write.
Every denied write is appended to the deny log (surfaced in the UI as a
trust signal).
"""
from __future__ import annotations

import os
from pathlib import Path

from webapp.pipeline.scratch import ScratchWriteDenied, scratch_write

DENY_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "deny.log"


def _log_denial(message: str) -> None:
    DENY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DENY_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def sandboxed_write(scratch_dir: str, repo_dir: str, rel_path: str, content: str) -> Path:
    """Write content under scratch_dir, denying anything resolving into repo_dir."""
    try:
        return scratch_write(scratch_dir, repo_dir, rel_path, content)
    except ScratchWriteDenied as e:
        _log_denial(f"[{os.getpid()}] {e}")
        raise


def read_deny_log() -> list[str]:
    """Return recent deny-log lines (for the UI trust surface)."""
    if not DENY_LOG_PATH.exists():
        return []
    lines = DENY_LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    return lines[-20:]
