"""自定义日志处理器 — 将 mobilerun 日志实时推送到 WebSocket + 持久化到文件。"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from server.models import LogEntry
from server.websocket.manager import manager as ws_manager

logger = logging.getLogger("mobilerun.server.log_handler")

# 日志持久化目录
LOG_DIR = Path(__file__).parent.parent.parent / "data" / "task_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


class WebSocketLogHandler(logging.Handler):
    """将日志实时推送到 WebSocket，同时持久化到文件。

    用法：
        handler = WebSocketLogHandler(task_id)
        result = await run_async(..., log_handler=handler)
    """

    def __init__(self, task_id: str):
        super().__init__(logging.DEBUG)
        self.task_id = task_id
        self._loop: asyncio.AbstractEventLoop | None = None
        self._count = 0
        self._log_file = LOG_DIR / f"{task_id}.jsonl"
        # 清空旧日志文件
        if self._log_file.exists():
            self._log_file.unlink()

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """设置事件循环（在异步上下文中调用）。"""
        self._loop = loop
        logger.info(f"WS log handler initialized for task {self.task_id}")

    def emit(self, record: logging.LogRecord):
        """将日志推送到 WebSocket + 写入文件。"""
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

            # 持久化到 JSONL 文件
            try:
                log_data = {
                    "seq": self._count,
                    "msg": msg,
                    "color": color,
                    "level": levelno,
                    "timestamp": datetime.now().isoformat(),
                }
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_data, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.warning(f"Failed to persist log for task {self.task_id}: {e}")

            # 同时输出到服务器日志（方便 tail 查看）
            logger.info(f"[{self.task_id}] {msg}")

            # 推送到 WebSocket
            if self._loop and self._loop.is_running():
                self._loop.create_task(
                    ws_manager.send_log(self.task_id, entry.model_dump(mode="json"))
                )
        except Exception:
            self.handleError(record)
