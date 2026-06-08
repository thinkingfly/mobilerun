"""自定义日志处理器 — 将 mobilerun 日志实时推送到 WebSocket。"""

import asyncio
import logging
from datetime import datetime

from server.models import LogEntry
from server.websocket.manager import manager as ws_manager

logger = logging.getLogger("mobilerun.server.log_handler")


class WebSocketLogHandler(logging.Handler):
    """将日志实时推送到 WebSocket。

    用法：
        handler = WebSocketLogHandler(task_id)
        result = await run_async(..., log_handler=handler)
    """

    def __init__(self, task_id: str):
        super().__init__(logging.DEBUG)
        self.task_id = task_id
        self._loop: asyncio.AbstractEventLoop | None = None
        self._count = 0

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """设置事件循环（在异步上下文中调用）。"""
        self._loop = loop
        logger.info(f"WS log handler initialized for task {self.task_id}")

    def emit(self, record: logging.LogRecord):
        """将日志推送到 WebSocket。"""
        try:
            self._count += 1
            msg = self.format(record)
            color = getattr(record, "color", None)
            levelno = getattr(record, "levelno", 0) or 0
            entry = LogEntry(
                msg=msg,
                color=color,
                level=levelno,
                timestamp=datetime.now(),
            )
            if self._loop and self._loop.is_running():
                self._loop.create_task(
                    ws_manager.send_log(self.task_id, entry.model_dump(mode="json"))
                )
        except Exception:
            self.handleError(record)
