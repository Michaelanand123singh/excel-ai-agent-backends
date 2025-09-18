from typing import Dict, Set
from fastapi import WebSocket
import json
import asyncio
import logging

logger = logging.getLogger("websocket")


class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, file_id: str):
        await websocket.accept()
        async with self._lock:
            if file_id not in self.active_connections:
                self.active_connections[file_id] = set()
            self.active_connections[file_id].add(websocket)
        logger.info(f"WebSocket connected for file {file_id}")

    async def disconnect(self, websocket: WebSocket, file_id: str):
        async with self._lock:
            if file_id in self.active_connections:
                self.active_connections[file_id].discard(websocket)
                if not self.active_connections[file_id]:
                    del self.active_connections[file_id]
        logger.info(f"WebSocket disconnected for file {file_id}")

    async def send_progress(self, file_id: str, message: dict):
        async with self._lock:
            connections = self.active_connections.get(file_id, set()).copy()
        
        if not connections:
            return
        
        message_json = json.dumps(message)
        disconnected = set()
        
        for websocket in connections:
            try:
                await websocket.send_text(message_json)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                disconnected.add(websocket)
        
        # Clean up disconnected connections
        if disconnected:
            async with self._lock:
                if file_id in self.active_connections:
                    self.active_connections[file_id] -= disconnected
                    if not self.active_connections[file_id]:
                        del self.active_connections[file_id]


# Global WebSocket manager instance
websocket_manager = WebSocketManager()
