"""SQLite thin data layer for the omp-agent web app.

Minimal by design: no ORM. Tables: projects, sessions, tasks, events.
One connection per operation (v1 simplicity; SQLite handles this fine
for a localhost single-user app).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "omp_web.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables if missing. Idempotent."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                repo_path   TEXT NOT NULL,
                scratch_path TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL REFERENCES projects(id),
                status      TEXT NOT NULL DEFAULT 'active',
                started_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   INTEGER NOT NULL REFERENCES sessions(id),
                intent       TEXT,           -- JSON (Intent object)
                state        TEXT NOT NULL,  -- current phase
                design_path  TEXT,
                recipe_path  TEXT,
                pr_url       TEXT,
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS events (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id  INTEGER NOT NULL REFERENCES tasks(id),
                kind     TEXT NOT NULL,
                payload  TEXT NOT NULL,      -- JSON
                ts       TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )


def _lastrowid(cur: sqlite3.Cursor) -> int:
    """lastrowid is Optional in typing; it is always set after INSERT here."""
    rid = cur.lastrowid
    if rid is None:
        raise RuntimeError("INSERT did not return a row id")
    return rid


# ── Projects ────────────────────────────────────────────────────────────

def create_project(name: str, repo_path: str, scratch_path: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO projects (name, repo_path, scratch_path) VALUES (?, ?, ?)",
            (name, repo_path, scratch_path),
        )
        return _lastrowid(cur)


def list_projects() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def get_project(project_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return dict(row) if row else None


# ── Sessions ────────────────────────────────────────────────────────────

def create_session(project_id: int) -> int:
    with _connect() as conn:
        cur = conn.execute("INSERT INTO sessions (project_id) VALUES (?)", (project_id,))
        return _lastrowid(cur)


def list_sessions(project_id: int) -> list[dict[str, Any]]:
    """All sessions for a project, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE project_id = ? ORDER BY id DESC",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_session(session_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None


# ── Tasks ───────────────────────────────────────────────────────────────

def create_task(session_id: int, intent: dict[str, Any]) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (session_id, intent, state) VALUES (?, ?, 'intake')",
            (session_id, json.dumps(intent)),
        )
        return _lastrowid(cur)


def get_task(task_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def update_task_state(task_id: int, state: str, **fields: Any) -> None:
    """Update task state + any extra columns (design_path, recipe_path, pr_url)."""
    allowed = {"design_path", "recipe_path", "pr_url", "state"}
    sets = ["state = ?"]
    vals: list[Any] = [state]
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k} = ?")
            vals.append(v)
    vals.append(task_id)
    with _connect() as conn:
        conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", vals)


# ── Events ──────────────────────────────────────────────────────────────

def add_event(task_id: int, kind: str, payload: dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO events (task_id, kind, payload) VALUES (?, ?, ?)",
            (task_id, kind, json.dumps(payload)),
        )
        # Resolve the event's session for the WS push (best-effort).
        row = conn.execute(
            "SELECT session_id FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        sid = row["session_id"] if row else None
    if sid is not None:
        _publish_ws(sid, {
            "id": _last_event_id(task_id),
            "task_id": task_id,
            "kind": kind,
            "payload": payload,
            "ts": _timestamp(),
        })


def _last_event_id(task_id: int) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM events WHERE task_id = ? ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        return row["id"] if row else 0


def _publish_ws(sid: int, event: dict[str, Any]) -> None:
    """Push an event to the session's websocket clients (async fire-and-forget)."""
    try:
        from webapp.api import events as ws_events
        import asyncio

        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(ws_events.publish(sid, event))
        else:
            asyncio.run(ws_events.publish(sid, event))
    except Exception:  # noqa: BLE001 — ws push must never break event persistence
        pass


def list_events(task_id: int) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE task_id = ? ORDER BY id", (task_id,)
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d["payload"])
            out.append(d)
        return out


def list_recent_tasks(limit: int = 5) -> list[dict[str, Any]]:
    """Recent tasks across all sessions (for L2 work-history context)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def list_tasks_by_session(session_id: int) -> list[dict[str, Any]]:
    """All tasks in a session, oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE session_id = ? ORDER BY id", (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]
