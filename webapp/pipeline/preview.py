"""Preview server — starts a repo's dev/static server so the web UI can
iframe the built app.

Stack detection (v1):
  - Vite (vite.config.* + package.json "vite" dep)  → `npm run dev` / vite
  - Next.js (next.config.*)                         → `npm run dev`
  - Static (index.html)                             → `python3 -m http.server`
  - Otherwise                                       → unsupported

Only one preview server per repo path is kept alive (keyed by path).
"""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Any

_ACTIVE: dict[str, "subprocess.Popen"] = {}
_LOCK = threading.Lock()

PREVIEW_PORTS = {"vite": 5173, "next": 3000, "static": 8000}


def _has(p: Path, *names: str) -> bool:
    return any((p / n).exists() for n in names)


def detect_stack(repo_path: str) -> tuple[str | None, str]:
    """Return (stack, app_dir) for a repo. stack is None if no web app.

    Checks the repo root AND common web-app subdirectories (gui/web, web,
    frontend, webapp/web, client) since Vite apps often live nested.
    """
    root = Path(repo_path)
    if not root.is_dir():
        return None, repo_path
    # Candidate dirs: root + common nested web-app locations.
    candidates = [root]
    for sub in ("gui/web", "web", "frontend", "client", "webapp/web", "app"):
        p = root / sub
        if p.is_dir():
            candidates.append(p)
    for c in candidates:
        pkg = c / "package.json"
        has_pkg = pkg.exists()
        if has_pkg:
            try:
                import json

                data = json.loads(pkg.read_text())
                deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
            except Exception:  # noqa: BLE001
                deps = {}
        else:
            deps = {}
        if "vite" in deps or _has(c, "vite.config.ts", "vite.config.js", "vite.config.mjs"):
            return "vite", str(c)
        if _has(c, "next.config.ts", "next.config.js", "next.config.mjs") or "next" in deps:
            return "next", str(c)
        if _has(c, "index.html"):
            return "static", str(c)
    return None, repo_path


def _cmd_for(stack: str, app_dir: str) -> list[str] | None:
    root = Path(app_dir)
    if stack == "vite":
        # Prefer the local vite binary if present.
        if (root / "node_modules" / ".bin" / "vite").exists():
            return [str(root / "node_modules" / ".bin" / "vite"), "--port", "5173", "--strictPort"]
        return ["npm", "run", "dev", "--", "--port", "5173", "--strictPort"]
    if stack == "next":
        return ["npm", "run", "dev", "--", "-p", "3000"]
    if stack == "static":
        return ["python3", "-m", "http.server", "8000", "--directory", app_dir]
    return None


def start_preview(repo_path: str) -> dict[str, Any]:
    """Start a preview server for a repo. Returns {url, stack} or {error}."""
    with _LOCK:
        existing = _ACTIVE.get(repo_path)
        if existing and existing.poll() is None:
            stack, _app = detect_stack(repo_path)
            stack = stack or "vite"
            port = PREVIEW_PORTS.get(stack, 5173)
            return {"url": f"http://127.0.0.1:{port}", "stack": stack, "already": True}
    stack, app_dir = detect_stack(repo_path)
    if not stack:
        return {"error": f"no previewable web app detected in {repo_path}"}
    cmd = _cmd_for(stack, app_dir)
    if not cmd:
        return {"error": f"unsupported stack: {stack}"}
    try:
        env = dict(os.environ)
        # Headless-friendly: vite/next don't need a browser; keep stdout quiet.
        proc = subprocess.Popen(
            cmd, cwd=app_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env
        )
    except FileNotFoundError:
        return {"error": f"command not found: {cmd[0]} — is the stack installed?"}
    with _LOCK:
        # Replace any prior dead handle for this path.
        old = _ACTIVE.pop(repo_path, None)
        if old and old.poll() is None:
            old.terminate()
        _ACTIVE[repo_path] = proc
    port = PREVIEW_PORTS.get(stack, 5173)
    return {"url": f"http://127.0.0.1:{port}", "stack": stack, "pid": proc.pid}


def stop_preview(repo_path: str) -> dict[str, Any]:
    """Stop a repo's preview server if running."""
    with _LOCK:
        proc = _ACTIVE.pop(repo_path, None)
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            return {"stopped": True}
        except Exception:  # noqa: BLE001
            pass
    return {"stopped": False}


def list_previews() -> dict[str, Any]:
    """For diagnostics: currently running preview servers."""
    out: dict[str, dict[str, Any]] = {}
    with _LOCK:
        for path, proc in _ACTIVE.items():
            out[path] = {
                "running": proc.poll() is None,
                "pid": proc.pid,
            }
    return {"previews": out}
