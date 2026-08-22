"""FastAPI app — WebSocket-only JSON-RPC.

Everything (projects, sessions, tasks, decide, clarify, fs browse, events)
travels over ONE websocket as JSON messages:

  Request:  {"id": 1, "method": "projects.list", "params": {}}
  Response: {"id": 1, "result": [...]}
  Error:    {"id": 1, "error": "message"}
  Event:    {"type": "event", "event": {...}}   (live push, no id)

v1: localhost only, no auth, one task at a time per session.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from webapp.data import db
from webapp.api import events as ws_events_bus
from webapp.orchestrator.machine import TaskRunner
from webapp.orchestrator import role_config
from webapp.pipeline import sandbox

app = FastAPI(title="omp-agent web")

# Localhost-only dev; the frontend (vite dev server) is a different port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5273", "http://127.0.0.1:5273"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()

# ── RPC method handlers ────────────────────────────────────────────────

def _handle(method: str, params: dict) -> dict:
    """Dispatch an RPC method to the data/orchestrator layer."""
    if method == "health":
        return {"ok": True}

    if method == "models.list":
        return {"models": role_config.list_models()}

    if method == "roles.get":
        return role_config.get_roles()

    if method == "roles.set":
        return role_config.set_roles(params.get("roles", {}))

    if method == "projects.list":
        return db.list_projects()

    if method == "projects.create":
        repo = Path(params["repo_path"]).resolve()
        if not repo.is_dir():
            return {"error": f"repo path not a directory: {repo}"}
        pid = db.create_project(params["name"], str(repo), params["scratch_path"])
        return db.get_project(pid) or {"error": "create failed"}

    if method == "fs.list":
        base = Path(params.get("path", "")).expanduser().resolve() if params.get("path") else Path.home()
        if not base.is_dir():
            return {"error": f"not a directory: {base}"}
        dirs = []
        try:
            for entry in sorted(os.scandir(base), key=lambda e: e.name.lower()):
                if entry.is_dir() and not entry.name.startswith("."):
                    dirs.append({"name": entry.name, "path": str(Path(entry.path))})
        except PermissionError:
            pass  # show what we can
        return {"path": str(base), "dirs": dirs[:200]}

    if method == "sessions.create":
        project = db.get_project(params["project_id"])
        if not project:
            return {"error": "project not found"}
        sid = db.create_session(params["project_id"])
        return db.get_session(sid) or {"error": "create failed"}

    if method == "sessions.list":
        return db.list_sessions(params["project_id"])

    if method == "sessions.tasks":
        return db.list_tasks_by_session(params["session_id"])

    if method == "tasks.create":
        sid = params["session_id"]
        session = db.get_session(sid)
        if not session:
            return {"error": "session not found"}
        project = db.get_project(session["project_id"])
        if not project:
            return {"error": "project not found"}
        task_id = db.create_task(sid, {"raw": params["message"]})
        runner = TaskRunner(task_id, project)
        runner.start(params["message"])
        return db.get_task(task_id) or {"error": "task create failed"}

    if method == "tasks.clarify":
        tid = params["task_id"]
        task = db.get_task(tid)
        if not task:
            return {"error": "task not found"}
        project = db.get_project(_session_project_id(tid))
        if not project:
            return {"error": "project not found"}
        TaskRunner(tid, project).clarify_answered(params["answers"])
        return db.get_task(tid) or {}

    if method == "tasks.decide":
        tid = params["task_id"]
        task = db.get_task(tid)
        if not task:
            return {"error": "task not found"}
        project = db.get_project(_session_project_id(tid))
        if not project:
            return {"error": "project not found"}
        runner = TaskRunner(tid, project)
        state = task["state"]
        decision = params["decision"]
        if state == "awaiting_design_approval":
            if decision == "approve":
                db.update_task_state(tid, "recipe")
                _spawn_build_chain(runner)
            else:
                runner.design_decided("reject", params.get("note", ""))
        elif state == "awaiting_recipe_approval" and decision == "approve":
            db.update_task_state(tid, "building")
            _spawn_build_chain(runner)
        return db.get_task(tid) or {}

    if method == "tasks.get":
        task = db.get_task(params["task_id"])
        return task or {"error": "task not found"}

    if method == "tasks.events":
        return db.list_events(params["task_id"])

    if method == "deny.log":
        return {"entries": sandbox.read_deny_log()}

    return {"error": f"unknown method: {method}"}


def _spawn_build_chain(runner: TaskRunner) -> None:
    """Run the recipe→build→review→fix→verify chain in a background thread."""
    import threading

    def _run() -> None:
        try:
            runner.recipe_decided("approve")
        except Exception as e:  # noqa: BLE001 — surface as an event, don't kill the thread
            db.add_event(runner.task_id, "error", {"note": str(e)})

    t = threading.Thread(target=_run, daemon=True)
    t.start()


# ── WebSocket ──────────────────────────────────────────────────────────

@app.websocket("/ws")
async def ws_rpc(ws: WebSocket):
    """Single websocket: JSON-RPC requests + live event push."""
    await ws.accept()
    # Events are pushed per-session; this socket handles the session's
    # live stream once a session is bound via sessions.bind.
    bound_session: int | None = None

    async def push_to_self(event: dict) -> None:
        try:
            await ws.send_json({"type": "event", "event": event})
        except Exception:  # noqa: BLE001
            pass

    # Subscribe the current socket to a session's live events.
    async def bind(sid: int) -> None:
        nonlocal bound_session
        if bound_session is not None:
            ws_events_bus.disconnect(bound_session, ws)
        bound_session = sid
        ws_events_bus.connect(sid, ws)
        # Replay the session's task events (latest task) for history.
        tasks = db.list_tasks_by_session(sid)
        for t in tasks[-1:]:
            for ev in db.list_events(t["id"]):
                await push_to_self(ev)

    try:
        while True:
            msg = await ws.receive_json()
            method = msg.get("method", "")
            params = msg.get("params", {}) or {}
            rid = msg.get("id")

            # sessions.bind binds this socket to a session's live stream.
            if method == "sessions.bind":
                sid = params.get("session_id")
                if sid is not None:
                    await bind(sid)
                    if rid is not None:
                        await ws.send_json({"id": rid, "result": {"bound": sid}})
                continue

            try:
                result = _handle(method, params)
            except Exception as e:  # noqa: BLE001 — never kill the socket
                result = {"error": f"internal: {e}"}

            # If it's a task method, also bind to the session for live events.
            if method == "sessions.create" and "id" in (result or {}):
                await bind(result["id"])
            if method == "tasks.create" and "id" in (result or {}):
                task = db.get_task(result["id"])
                if task:
                    await bind(task["session_id"])

            if rid is not None:
                await ws.send_json({"id": rid, "result": result})
    except WebSocketDisconnect:
        pass
    finally:
        if bound_session is not None:
            ws_events_bus.disconnect(bound_session, ws)


# ── helpers ────────────────────────────────────────────────────────────

def _session_project_id(task_id: int) -> int:
    task = db.get_task(task_id)
    if not task:
        raise ValueError("task not found")
    session = db.get_session(task["session_id"])
    if not session:
        raise ValueError("session not found")
    return session["project_id"]
