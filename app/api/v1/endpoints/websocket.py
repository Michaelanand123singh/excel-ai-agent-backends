from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import logging

from app.core.websocket_manager import websocket_manager

router = APIRouter()
logger = logging.getLogger("websocket")


@router.websocket("/{file_id}")
async def websocket_handler(websocket: WebSocket, file_id: str) -> None:
    await websocket_manager.connect(websocket, file_id)
    try:
        # Send initial connection message
        await websocket.send_text('{"type": "connected", "file_id": "' + file_id + '"}')
        
        # Keep connection alive and handle any incoming messages
        while True:
            try:
                data = await websocket.receive_text()
                # Echo back for now, could handle commands later
                await websocket.send_text(f'{{"type": "echo", "data": "{data}"}}')
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    finally:
        await websocket_manager.disconnect(websocket, file_id)


