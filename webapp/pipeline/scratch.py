"""Scratch — the ONLY write path for the orchestrator.

Enforces the permission model from PRODUCT_SPEC.md:
- Writes are allowed ONLY under the project's scratch dir (e.g. /tmp/...).
- Any write whose realpath resolves inside the project repo is DENIED.
- Every denial is logged (the deny-log surfaces in the UI).

realpath resolution defeats symlink tricks (`ln -s /project /tmp/link`).
"""
from __future__ import annotations

import os
from pathlib import Path


class ScratchWriteDenied(Exception):
    """Raised when a write targets the project repo (or anything outside scratch)."""


def _real(path: Path) -> Path:
    return Path(os.path.realpath(path))


def scratch_write(scratch_dir: str, repo_dir: str, rel_path: str, content: str) -> Path:
    """Write `content` to scratch_dir/rel_path, refusing anything that
    resolves into repo_dir. Returns the written absolute path.

    `rel_path` must be relative and must not escape scratch (no '..').
    """
    scratch = _real(Path(scratch_dir))
    repo = _real(Path(repo_dir))

    target = _real(scratch / rel_path)
    # Guard 1: target must stay under scratch.
    if not target.is_relative_to(scratch):
        raise ScratchWriteDenied(f"write outside scratch dir: {target}")
    # Guard 2: target must NOT be under the project repo.
    if target.is_relative_to(repo):
        raise ScratchWriteDenied(f"write into project folder blocked — use scratch: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def scratch_read(scratch_dir: str, rel_path: str) -> str | None:
    """Read a scratch file (None if missing). Read-only, no guard needed
    but still resolve realpath for consistency."""
    scratch = _real(Path(scratch_dir))
    target = _real(scratch / rel_path)
    if not target.is_relative_to(scratch):
        return None
    if not target.exists():
        return None
    return target.read_text(encoding="utf-8")


def list_scratch(scratch_dir: str) -> list[str]:
    """List relative paths of files under scratch (for the Scratch drawer)."""
    scratch = _real(Path(scratch_dir))
    if not scratch.exists():
        return []
    return [
        str(p.relative_to(scratch))
        for p in scratch.rglob("*")
        if p.is_file()
    ]
