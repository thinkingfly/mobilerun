"""本地持久化存储 — 基于 SQLite。

保持与旧 FileStorage 相同的接口，内部使用 SQLite 存储。
"""

import logging
from datetime import datetime
from typing import Optional

from server.db import db as sqlite_db

logger = logging.getLogger("mobilerun.server")


class Storage:
    """兼容旧接口的存储包装器，内部使用 SQLite。"""

    # ── Tasks ──

    def load_tasks(self) -> list[dict]:
        return sqlite_db.load_tasks()

    def save_tasks(self, tasks: list[dict]):
        """SQLite 不需要全量保存，每条单独写入。"""
        pass

    def append_task(self, task: dict):
        sqlite_db.append_task(task)

    def update_task(self, task_id: str, updates: dict):
        sqlite_db.update_task(task_id, updates)

    def get_task(self, task_id: str) -> Optional[dict]:
        return sqlite_db.get_task(task_id)

    # ── Agents ──

    def load_agents(self) -> list[dict]:
        return sqlite_db.load_agents()

    def save_agents(self, agents: list[dict]):
        """SQLite 不需要全量保存。"""
        pass

    def append_agent(self, agent: dict):
        sqlite_db.append_agent(agent)

    def update_agent(self, agent_id: str, updates: dict):
        sqlite_db.update_agent(agent_id, updates)

    def remove_agent(self, agent_id: str):
        sqlite_db.remove_agent(agent_id)

    def get_agent(self, agent_id: str) -> Optional[dict]:
        return sqlite_db.get_agent(agent_id)

    # ── Chat History ──

    def load_chat(self, agent_id: str) -> list[dict]:
        return sqlite_db.load_chat(agent_id)

    def save_chat(self, agent_id: str, messages: list[dict]):
        sqlite_db.save_chat(agent_id, messages)

    def append_message(self, agent_id: str, message: dict):
        sqlite_db.append_message(agent_id, message)

    def clear_chat(self, agent_id: str):
        sqlite_db.clear_chat(agent_id)

    def compress_chat(self, agent_id: str, keep_last: int = 10) -> list[dict]:
        return sqlite_db.compress_chat(agent_id, keep_last)


storage = Storage()
