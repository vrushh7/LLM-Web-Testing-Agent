from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.services.websocket_manager import websocket_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/runs/{run_id}")
async def run_socket(websocket: WebSocket, run_id: str) -> None:
    await websocket_manager.connect(run_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_manager.disconnect(run_id, websocket)

