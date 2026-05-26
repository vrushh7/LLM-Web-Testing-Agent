from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


class WebSocketManager:
    """Broadcasts run events and keeps a small replay buffer for late subscribers."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._recent_events: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=200))

    async def connect(self, run_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[run_id].append(websocket)
        for event in self._recent_events[run_id]:
            await websocket.send_json(event)

    def disconnect(self, run_id: str, websocket: WebSocket) -> None:
        if websocket in self._connections.get(run_id, []):
            self._connections[run_id].remove(websocket)

    async def publish(
        self,
        run_id: str,
        event_type: str,
        message: str,
        status: str | None = None,
        step_index: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event = {
            "run_id": run_id,
            "type": event_type,
            "message": message,
            "status": status,
            "step_index": step_index,
            "payload": payload or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._recent_events[run_id].append(event)

        stale: list[WebSocket] = []
        for websocket in list(self._connections.get(run_id, [])):
            try:
                await websocket.send_json(event)
            except WebSocketDisconnect:
                stale.append(websocket)
            except RuntimeError:
                stale.append(websocket)

        for websocket in stale:
            self.disconnect(run_id, websocket)


websocket_manager = WebSocketManager()

