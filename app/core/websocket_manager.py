from typing import Dict, Set, Optional
from fastapi import WebSocket
import json
import asyncio
import logging
import weakref
from contextlib import asynccontextmanager

logger = logging.getLogger("websocket")


class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._message_queue: Dict[str, asyncio.Queue] = {}
        self._cleanup_tasks: Set[asyncio.Task] = set()

    async def connect(self, websocket: WebSocket, file_id: str):
        await websocket.accept()
        async with self._lock:
            if file_id not in self.active_connections:
                self.active_connections[file_id] = set()
                self._message_queue[file_id] = asyncio.Queue()
            self.active_connections[file_id].add(websocket)
        logger.info(f"WebSocket connected for file {file_id}")

    async def disconnect(self, websocket: WebSocket, file_id: str):
        async with self._lock:
            if file_id in self.active_connections:
                self.active_connections[file_id].discard(websocket)
                if not self.active_connections[file_id]:
                    del self.active_connections[file_id]
                    # Clean up message queue
                    if file_id in self._message_queue:
                        del self._message_queue[file_id]
        logger.info(f"WebSocket disconnected for file {file_id}")

    async def send_progress(self, file_id: str, message: dict):
        """Send progress message to all connections for a file_id"""
        try:
            async with self._lock:
                connections = self.active_connections.get(file_id, set()).copy()
            
            if not connections:
                return
            
            message_json = json.dumps(message, default=str)
            disconnected = set()
            
            # Send to all connections concurrently
            tasks = []
            for websocket in connections:
                task = asyncio.create_task(self._send_to_websocket(websocket, message_json))
                tasks.append((websocket, task))
            
            # Wait for all sends to complete
            for websocket, task in tasks:
                try:
                    await task
                except Exception as e:
                    logger.warning(f"Failed to send to WebSocket: {e}")
                    disconnected.add(websocket)
            
            # Clean up disconnected connections
            if disconnected:
                await self._cleanup_disconnected(file_id, disconnected)
                
        except Exception as e:
            logger.error(f"Error in send_progress: {e}")

    async def _send_to_websocket(self, websocket: WebSocket, message: str):
        """Send message to a single websocket with timeout"""
        try:
            await asyncio.wait_for(websocket.send_text(message), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("WebSocket send timeout")
            raise
        except Exception as e:
            logger.warning(f"WebSocket send error: {e}")
            raise

    async def _cleanup_disconnected(self, file_id: str, disconnected: Set[WebSocket]):
        """Clean up disconnected websockets"""
        async with self._lock:
            if file_id in self.active_connections:
                self.active_connections[file_id] -= disconnected
                if not self.active_connections[file_id]:
                    del self.active_connections[file_id]
                    if file_id in self._message_queue:
                        del self._message_queue[file_id]

    def send_progress_sync(self, file_id: str, message: dict):
        """Synchronous wrapper for send_progress - safe to call from sync contexts"""
        try:
            # Check if we're in an async context
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context, schedule the coroutine
                asyncio.create_task(self.send_progress(file_id, message))
            except RuntimeError:
                # We're not in an async context, create a new event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.send_progress(file_id, message))
                finally:
                    loop.close()
        except Exception as e:
            logger.error(f"Error in send_progress_sync: {e}")

    async def cleanup_stale_connections(self):
        """Clean up stale connections periodically"""
        async with self._lock:
            stale_files = []
            for file_id, connections in self.active_connections.items():
                # Remove closed connections
                active_connections = set()
                for ws in connections:
                    try:
                        # Test if connection is still alive
                        await asyncio.wait_for(ws.ping(), timeout=1.0)
                        active_connections.add(ws)
                    except:
                        # Connection is dead, remove it
                        pass
                
                if active_connections:
                    self.active_connections[file_id] = active_connections
                else:
                    stale_files.append(file_id)
            
            # Remove files with no active connections
            for file_id in stale_files:
                del self.active_connections[file_id]
                if file_id in self._message_queue:
                    del self._message_queue[file_id]
                logger.info(f"Cleaned up stale connections for file {file_id}")

    def get_connection_count(self, file_id: str) -> int:
        """Get number of active connections for a file"""
        return len(self.active_connections.get(file_id, set()))

    def get_total_connections(self) -> int:
        """Get total number of active connections"""
        return sum(len(connections) for connections in self.active_connections.values())


# Global WebSocket manager instance
websocket_manager = WebSocketManager()
