"""SQLite 操作工具类 — 统一管理 SQLite 数据库连接和 CRUD 操作。"""

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mobilerun.server")

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "checkpoints.db"

# JSON 文件路径（仅用于首次迁移）
TASKS_FILE = DATA_DIR / "tasks.json"
AGENTS_FILE = DATA_DIR / "agents.json"
CHATS_DIR = DATA_DIR / "chats"

MAX_TASKS = 1000

# ── 建表语句 ──

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint BLOB,
    metadata BLOB,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    value BLOB,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    device_serial TEXT NOT NULL,
    goal TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    result TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    log_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    device_serial TEXT,
    status TEXT NOT NULL DEFAULT 'idle',
    current_task TEXT,
    total_tasks INTEGER DEFAULT 0,
    is_default INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    compressed INTEGER DEFAULT 0,
    task_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_chat_agent ON chat_messages(agent_id);
CREATE INDEX IF NOT EXISTS idx_chat_timestamp ON chat_messages(timestamp);
"""


class SQLiteStorage:
    """线程安全的 SQLite 数据库操作封装。"""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency
        self._init_db()
        self._conn.commit()
        self._migrate_from_json()
        self._conn.commit()
        logger.info(f"SQLite storage initialized: {self._db_path}")

    def _init_db(self):
        """执行建表语句。"""
        with self._lock:
            self._conn.executescript(_INIT_SQL)
            self._conn.commit()

    def _migrate_from_json(self):
        """如果 SQLite 表为空且 JSON 文件存在，自动迁移数据。"""
        # 检查是否已迁移
        task_count = self._conn.execute("SELECT count(*) FROM tasks").fetchone()[0]
        if task_count > 0:
            return  # 已有数据，跳过迁移

        import json

        # 直接读取 JSON 文件，避免循环导入
        def _load_json(path: Path) -> list:
            if not path.exists():
                return []
            try:
                return json.loads(path.read_text("utf-8"))
            except (json.JSONDecodeError, IOError):
                return []

        # 迁移 tasks
        raw_tasks = _load_json(TASKS_FILE)
        if raw_tasks:
            self._batch_insert_tasks(raw_tasks)
            logger.info(f"Migrated {len(raw_tasks)} tasks from JSON to SQLite")

        # 迁移 agents
        raw_agents = _load_json(AGENTS_FILE)
        if raw_agents:
            self._batch_insert_agents(raw_agents)
            logger.info(f"Migrated {len(raw_agents)} agents from JSON to SQLite")

        # 迁移 chats
        if CHATS_DIR.exists():
            for chat_file in CHATS_DIR.glob("*.json"):
                agent_id = chat_file.stem
                messages = _load_json(chat_file)
                if messages:
                    for msg in messages:
                        self._append_message_raw(agent_id, msg)
                    logger.info(f"Migrated {len(messages)} chat messages for {agent_id}")

        if task_count == 0:
            logger.info("No JSON data to migrate")

    # ── Tasks ──

    def load_tasks(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC"
            ).fetchall()
            tasks = []
            for r in rows:
                d = dict(r)
                if d.get("result") and isinstance(d["result"], str):
                    try:
                        d["result"] = json.loads(d["result"])
                    except json.JSONDecodeError:
                        d["result"] = None
                tasks.append(d)
            return tasks

    def _batch_insert_tasks(self, tasks: list[dict]):
        """批量插入任务（内部调用，无锁）。"""
        for t in tasks:
            for key in ("created_at", "started_at", "finished_at"):
                if key in t and isinstance(t[key], datetime):
                    t[key] = t[key].isoformat()
            if "result" in t and isinstance(t["result"], dict):
                t["result"] = json.dumps(t["result"])
        self._conn.executemany(
            """INSERT OR REPLACE INTO tasks
               (id, agent_id, device_serial, goal, status, result,
                created_at, started_at, finished_at, log_count)
               VALUES (:id, :agent_id, :device_serial, :goal, :status, :result,
                       :created_at, :started_at, :finished_at, :log_count)""",
            tasks,
        )
        self._conn.commit()

    def append_task(self, task: dict):
        with self._lock:
            # 序列化 result 和 datetime
            t = dict(task)
            for key in ("created_at", "started_at", "finished_at"):
                if key in t and isinstance(t[key], datetime):
                    t[key] = t[key].isoformat()
            if "result" in t and isinstance(t["result"], dict):
                t["result"] = json.dumps(t["result"])
            self._conn.execute(
                """INSERT OR REPLACE INTO tasks
                   (id, agent_id, device_serial, goal, status, result,
                    created_at, started_at, finished_at, log_count)
                   VALUES (:id, :agent_id, :device_serial, :goal, :status, :result,
                           :created_at, :started_at, :finished_at, :log_count)""",
                task,
            )
            self._conn.commit()

            # 清理旧任务
            count = self._conn.execute("SELECT count(*) FROM tasks").fetchone()[0]
            if count > MAX_TASKS:
                self._conn.execute(
                    "DELETE FROM tasks WHERE id IN ("
                    "SELECT id FROM tasks ORDER BY created_at DESC LIMIT -1 OFFSET ?)",
                    (MAX_TASKS,),
                )
                self._conn.commit()

    def update_task(self, task_id: str, updates: dict):
        with self._lock:
            vals = dict(updates)
            if "result" in vals and isinstance(vals["result"], dict):
                vals["result"] = json.dumps(vals["result"])
            if "finished_at" in vals and isinstance(vals["finished_at"], datetime):
                vals["finished_at"] = vals["finished_at"].isoformat()
            sets = ", ".join(f"{k} = ?" for k in vals)
            vlist = list(vals.values()) + [task_id]
            self._conn.execute(f"UPDATE tasks SET {sets} WHERE id = ?", vlist)
            self._conn.commit()

    def get_task(self, task_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            return dict(row) if row else None

    # ── Agents ──

    def load_agents(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM agents").fetchall()
            return [dict(r) for r in rows]

    def _batch_insert_agents(self, agents: list[dict]):
        for a in agents:
            if "created_at" in a and isinstance(a["created_at"], datetime):
                a["created_at"] = a["created_at"].isoformat()
            if "is_default" in a and isinstance(a["is_default"], bool):
                a["is_default"] = 1 if a["is_default"] else 0
        self._conn.executemany(
            """INSERT OR REPLACE INTO agents
               (id, name, device_serial, status, current_task,
                total_tasks, is_default, created_at)
               VALUES (:id, :name, :device_serial, :status, :current_task,
                       :total_tasks, :is_default, :created_at)""",
            agents,
        )
        self._conn.commit()

    def append_agent(self, agent: dict):
        with self._lock:
            a = dict(agent)
            if "created_at" in a and isinstance(a["created_at"], datetime):
                a["created_at"] = a["created_at"].isoformat()
            if "is_default" in a and isinstance(a["is_default"], bool):
                a["is_default"] = 1 if a["is_default"] else 0
            self._conn.execute(
                """INSERT OR REPLACE INTO agents
                   (id, name, device_serial, status, current_task,
                    total_tasks, is_default, created_at)
                   VALUES (:id, :name, :device_serial, :status, :current_task,
                           :total_tasks, :is_default, :created_at)""",
                agent,
            )
            self._conn.commit()

    def update_agent(self, agent_id: str, updates: dict):
        with self._lock:
            sets = ", ".join(f"{k} = ?" for k in updates)
            vals = list(updates.values()) + [agent_id]
            self._conn.execute(f"UPDATE agents SET {sets} WHERE id = ?", vals)
            self._conn.commit()

    def remove_agent(self, agent_id: str):
        with self._lock:
            self._conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
            self._conn.commit()

    def get_agent(self, agent_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM agents WHERE id = ?", (agent_id,)
            ).fetchone()
            return dict(row) if row else None

    # ── Chat Messages ──

    def load_chat(self, agent_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content, timestamp, compressed, task_id "
                "FROM chat_messages WHERE agent_id = ? ORDER BY timestamp",
                (agent_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def save_chat(self, agent_id: str, messages: list[dict]):
        """全量替换某个 agent 的消息（用于 compress 等操作）。"""
        with self._lock:
            self._conn.execute(
                "DELETE FROM chat_messages WHERE agent_id = ?", (agent_id,)
            )
            for msg in messages:
                self._append_message_raw(agent_id, msg)
            self._conn.commit()

    def _append_message_raw(self, agent_id: str, message: dict):
        """内部追加消息（无锁，调用者需持有锁）。"""
        self._conn.execute(
            """INSERT INTO chat_messages (agent_id, role, content, timestamp, compressed, task_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                agent_id,
                message.get("role", "user"),
                message.get("content", ""),
                message.get("timestamp", datetime.now().isoformat()),
                1 if message.get("compressed") else 0,
                message.get("task_id"),
            ),
        )

    def append_message(self, agent_id: str, message: dict):
        with self._lock:
            self._append_message_raw(agent_id, message)
            self._conn.commit()

    def clear_chat(self, agent_id: str):
        with self._lock:
            self._conn.execute(
                "DELETE FROM chat_messages WHERE agent_id = ?", (agent_id,)
            )
            self._conn.commit()

    def compress_chat(self, agent_id: str, keep_last: int = 10) -> list[dict]:
        """压缩聊天记录。"""
        messages = self.load_chat(agent_id)
        if len(messages) <= keep_last:
            return messages

        to_compress = messages[:-keep_last]
        kept = messages[-keep_last:]

        user_msgs = [m for m in to_compress if m.get("role") == "user"]
        summary_content = (
            f"[历史对话摘要：共 {len(to_compress)} 条消息，"
            f"其中 {len(user_msgs)} 条用户消息]"
        )
        key_goals = [
            m["content"]
            for m in user_msgs
            if "创建任务" not in m["content"] and "收到" not in m["content"]
        ]
        if key_goals:
            goals_preview = ", ".join(key_goals[:5])
            if len(key_goals) > 5:
                goals_preview += f"... 等 {len(key_goals)} 条指令"
            summary_content += f" - 主要指令: {goals_preview}"

        summary_msg = {
            "role": "system",
            "content": summary_content,
            "timestamp": datetime.now().isoformat(),
            "compressed": True,
        }

        compressed = [summary_msg] + kept
        self.save_chat(agent_id, compressed)
        return compressed

    def close(self):
        """关闭数据库连接。"""
        with self._lock:
            self._conn.close()


# 全局单例
db = SQLiteStorage()
