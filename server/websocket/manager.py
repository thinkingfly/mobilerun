"""WebSocket 连接管理器 — 按 task_id 分组推送日志。"""

import asyncio
import logging
from collections import deque

from fastapi import WebSocket

logger = logging.getLogger("mobilerun.server")

MAX_BUFFER_SIZE = 500


class ConnectionManager:
    """管理所有 WebSocket 连接，按 task_id 订阅。

    关键设计：在 WebSocket 连接建立之前产生的日志会被缓冲，
    连接建立后立即发送缓冲的日志，避免竞态条件导致日志丢失。
    """

    def __init__(self):
        self._active_connections: dict[str, list[WebSocket]] = {}
        # 在连接建立前产生的日志缓冲区: task_id -> deque of log_data
        self._log_buffer: dict[str, deque[dict]] = {}

    async def connect(self, websocket: WebSocket, task_id: str):
        await websocket.accept()
        if task_id not in self._active_connections:
            self._active_connections[task_id] = []
        self._active_connections[task_id].append(websocket)
        logger.info(
            f"WS connected: {task_id} (total: {len(self._active_connections[task_id])})"
        )
        # 发送缓冲区中的日志
        if task_id in self._log_buffer:
            buffer = self._log_buffer[task_id]
            count = 0
            while buffer:
                log_data = buffer.popleft()
                try:
                    await websocket.send_json(log_data)
                    count += 1
                except Exception as e:
                    logger.warning(f"WS buffer send failed for {task_id}: {e}")
                    break
            logger.info(
                f"WS drained {count} buffered logs for {task_id}"
            )

    async def disconnect(self, websocket: WebSocket, task_id: str):
        if task_id in self._active_connections:
            try:
                self._active_connections[task_id].remove(websocket)
            except ValueError:
                pass
            if not self._active_connections[task_id]:
                del self._active_connections[task_id]
                # 清理空缓冲区
                self._log_buffer.pop(task_id, None)
            logger.info(f"WS disconnected: {task_id}")

    async def send_log(self, task_id: str, log_data: dict):
        """向订阅了 task_id 的所有连接推送日志。
        如果没有活跃连接，将日志加入缓冲区。
        """
        if task_id in self._active_connections:
            dead = []
            for ws in self._active_connections[task_id]:
                try:
                    await ws.send_json(log_data)
                except Exception as e:
                    logger.warning(f"WS send failed for {task_id}: {e}")
                    dead.append(ws)
            for ws in dead:
                try:
                    self._active_connections[task_id].remove(ws)
                except ValueError:
                    pass
        else:
            # 没有活跃连接，加入缓冲区
            if task_id not in self._log_buffer:
                self._log_buffer[task_id] = deque(maxlen=MAX_BUFFER_SIZE)
            self._log_buffer[task_id].append(log_data)


# 全局单例
manager = ConnectionManager()
