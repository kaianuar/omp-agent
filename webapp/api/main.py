"""FastAPI app — routes + websocket event stream.

Thin layer: no business logic. Maps HTTP/ws to the orchestrator + data layer.
v1: localhost only, no auth, one task at a time per session.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from webapp.data import db
from webapp.api import events as ws_events_bus
from webapp.orchestrator.machine import TaskRunner
from webapp.pipeline import sandbox

app = FastAPI(title="omp-agent web")

# Localhost-only dev; the frontend (vite dev server) is a different port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()


# ── DTOs ───────────────────────────────────────────────────────────────

class ProjectIn(BaseModel):
    name: str
    repo_path: str
    scratch_path: str


class TaskIn(BaseModel):
    message: str


class DecideIn(BaseModel):
    decision: str  # approve | reject | adjust
    note: str = ""


class ClarifyIn(BaseModel):
    answers: str


# ── REST ───────────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/projects")
def projects() -> list[dict]:
    return db.list_projects()


@app.post("/api/projects")
def create_project(body: ProjectIn) -> dict:
    repo = Path(body.repo_path).resolve()
    if not repo.is_dir():
        return {"error": f"repo path not a directory: {repo}"}
    pid = db.create_project(body.name, str(repo), body.scratch_path)
    return db.get_project(pid) or {"error": "create failed"}


@app.post("/api/projects/{pid}/sessions")
def start_session(pid: int) -> dict:
    project = db.get_project(pid)
    if not project:
        return {"error": "project not found"}
    sid = db.create_session(pid)
    return db.get_session(sid) or {"error": "create failed"}


@app.post("/api/sessions/{sid}/tasks")
def new_task(sid: int, body: TaskIn) -> dict:
    """Create a task and start the intake phase (blocking up to LLM call)."""
    session = db.get_session(sid)
    if not session:
        return {"error": "session not found"}
    project = db.get_project(session["project_id"])
    if not project:
        return {"error": "project not found"}
    # v1: a fresh intent placeholder; run_intake fills it.
    task_id = db.create_task(sid, {"raw": body.message})
    runner = TaskRunner(task_id, project)
    runner.start(body.message)
    return db.get_task(task_id) or {"error": "task create failed"}


@app.post("/api/tasks/{tid}/clarify")
def clarify(tid: int, body: ClarifyIn) -> dict:
    task = db.get_task(tid)
    if not task:
        return {"error": "task not found"}
    project = db.get_project(_session_project_id(tid))
    if not project:
        return {"error": "project not found"}
    TaskRunner(tid, project).clarify_answered(body.answers)
    return db.get_task(tid) or {}


@app.post("/api/tasks/{tid}/decide")
def decide(tid: int, body: DecideIn) -> dict:
    """CHECKPOINT decisions: design approve/reject, recipe approve, etc.

    Returns immediately; the build chain (recipe → build → review → fix →
    verify) runs in a background thread so the UI gets instant feedback and
    polls /events for progress.
    """
    task = db.get_task(tid)
    if not task:
        return {"error": "task not found"}
    project = db.get_project(_session_project_id(tid))
    if not project:
        return {"error": "project not found"}
    runner = TaskRunner(tid, project)
    state = task["state"]
    if state == "awaiting_design_approval":
        if body.decision == "approve":
            db.update_task_state(tid, "recipe")
            _spawn_build_chain(runner)
        else:
            runner.design_decided("reject", body.note)
    elif state == "awaiting_recipe_approval" and body.decision == "approve":
        db.update_task_state(tid, "building")
        _spawn_build_chain(runner)
    return db.get_task(tid) or {}


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


@app.get("/api/tasks/{tid}/events")
def task_events(tid: int) -> list[dict]:
    return db.list_events(tid)


@app.get("/api/tasks/{tid}")
def get_task(tid: int) -> dict:
    task = db.get_task(tid)
    if not task:
        return {"error": "task not found"}
    return task


@app.get("/api/tasks/{tid}/artifacts")
def task_artifacts(tid: int) -> dict:
    task = db.get_task(tid)
    if not task:
        return {"error": "task not found"}
    return {
        "design_path": task.get("design_path"),
        "recipe_path": task.get("recipe_path"),
    }


@app.get("/api/deny-log")
def deny_log() -> dict:
    return {"entries": sandbox.read_deny_log()}


# ── WebSocket ──────────────────────────────────────────────────────────

@app.websocket("/ws/sessions/{sid}")
async def ws_events(ws: WebSocket, sid: int):
    """Push Event stream for a session. Replays recent events, then live-pushes."""
    await ws.accept()
    session = db.get_session(sid)
    if not session:
        await ws.send_json({"error": "session not found"})
        await ws.close()
        return
    ws_events_bus.connect(sid, ws)
    try:
        # Replay the session's task events (latest task) so a reconnecting
        # client gets history; then live events arrive via the bus.
        tasks = db.list_tasks_by_session(sid)
        for t in tasks[-1:]:
            for ev in db.list_events(t["id"]):
                await ws.send_json(ev)
        # Keep the connection open; the bus pushes new events to us.
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_events_bus.disconnect(sid, ws)


# ── helpers ────────────────────────────────────────────────────────────

def _session_project_id(task_id: int) -> int:
    task = db.get_task(task_id)
    if not task:
        raise ValueError("task not found")
    session = db.get_session(task["session_id"])
    if not session:
        raise ValueError("session not found")
    return session["project_id"]
