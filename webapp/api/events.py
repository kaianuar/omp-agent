"""WebSocket event bus — pushes orchestrator events to connected clients.

The orchestrator's EventSink writes events to the DB (source of truth) AND
publishes them here so connected web clients get live updates instead of
polling. One connection set per session id.
"""

from __future__ import annotations

from typing import Any

from fastapi import WebSocket

# sid -> set of active WebSocket connections
_SESSIONS: dict[int, set[WebSocket]] = {}


def connect(sid: int, ws: WebSocket) -> None:
    _SESSIONS.setdefault(sid, set()).add(ws)


def disconnect(sid: int, ws: WebSocket) -> None:
    conns = _SESSIONS.get(sid)
    if conns:
        conns.discard(ws)
        if not conns:
            _SESSIONS.pop(sid, None)


async def publish(sid: int, event: dict[str, Any]) -> None:
    """Send an event to every connected client for the session.

    A failing/dead connection is dropped (the client reconnects and replays
    from the DB on connect).
    """
    conns = _SESSIONS.get(sid)
    if not conns:
        return
    dead: list[WebSocket] = []
    for ws in conns:
        try:
            await ws.send_json(event)
        except Exception:  # noqa: BLE001 — dead connection, drop it
            dead.append(ws)
    for ws in dead:
        disconnect(sid, ws)


def session_connections(sid: int) -> int:
    return len(_SESSIONS.get(sid, set()))
