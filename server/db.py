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
    type TEXT NOT NULL DEFAULT 'normal',
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

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    goal TEXT NOT NULL,
    device_serials TEXT NOT NULL,
    cron_expression TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    last_run TEXT,
    next_run TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scheduled_enabled ON scheduled_tasks(enabled);

-- 聊天记录表：存储从聊天App（微信/WhatsApp等）读取的消息记录
-- 单聊场景：chat_name=对方联系人名, nick_name=消息发送者
-- 群聊场景：chat_name=群名, nick_name=该条消息的具体发送者
CREATE TABLE IF NOT EXISTS chat_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,              -- 数据源标识: wechat / whatsapp / qq 等
    chat_type TEXT NOT NULL,           -- 聊天类型: single(单聊) / group(群聊)
    chat_name TEXT NOT NULL,           -- 群名或联系人名（标识这个聊天会话）
    nick_name TEXT,                    -- 这条消息的发送者昵称
    avatar TEXT,                       -- 发送者头像URL（可选，预留字段）
    content TEXT NOT NULL,             -- 消息内容（文本，或[图片]/[表情]等描述）
    is_self INTEGER DEFAULT 0,         -- 是否是本设备Agent发送的消息: 0=对方发的, 1=自己发的
    device_id TEXT NOT NULL,           -- 设备序列号（标识是哪台设备读取/发送的）
    device_user TEXT NOT NULL,         -- Agent在该设备上使用的昵称（默认=设备号，可在代码中配置）
    created_at TEXT NOT NULL           -- 消息时间（ISO格式，如 2026-06-12T10:30:00）
);

CREATE INDEX IF NOT EXISTS idx_chat_records_source ON chat_records(source);
CREATE INDEX IF NOT EXISTS idx_chat_records_chat ON chat_records(chat_name, source);
CREATE INDEX IF NOT EXISTS idx_chat_records_time ON chat_records(created_at);
CREATE INDEX IF NOT EXISTS idx_chat_records_device ON chat_records(device_id);

-- RAG 文档表：存储上传的政策文档
CREATE TABLE IF NOT EXISTS rag_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    parsed_text TEXT,
    chunk_count INTEGER DEFAULT 0,
    language TEXT DEFAULT 'auto',
    uploaded_at TEXT NOT NULL,
    status TEXT DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_rag_docs_status ON rag_documents(status);

-- RAG 问答历史表
CREATE TABLE IF NOT EXISTS rag_chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    source TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    language TEXT,
    source_docs TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rag_history_session ON rag_chat_history(session_id, source);
CREATE INDEX IF NOT EXISTS idx_rag_history_time ON rag_chat_history(created_at);

-- 群组配置表
CREATE TABLE IF NOT EXISTS chat_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_name TEXT NOT NULL,
    source TEXT NOT NULL,
    device_id TEXT,
    default_language TEXT DEFAULT 'pt',
    rag_enabled INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(chat_name, source, device_id)
);

CREATE INDEX IF NOT EXISTS idx_chat_groups_source ON chat_groups(source);
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
            self._migrate_add_type_column()
            self._migrate_add_parent_task_column()
            self._conn.commit()

    def _migrate_add_type_column(self):
        """为已有 tasks 表增加 type 列（如果不存在）。"""
        try:
            self._conn.execute("SELECT type FROM tasks LIMIT 1")
        except sqlite3.OperationalError:
            # 列不存在，添加
            self._conn.execute("ALTER TABLE tasks ADD COLUMN type TEXT DEFAULT 'normal'")
            logger.info("Migrated: added 'type' column to tasks table")
        # 确保索引存在
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(type)")

    def _migrate_add_parent_task_column(self):
        """为已有 tasks 表增加 parent_task 列（如果不存在）。"""
        try:
            self._conn.execute("SELECT parent_task FROM tasks LIMIT 1")
        except sqlite3.OperationalError:
            self._conn.execute("ALTER TABLE tasks ADD COLUMN parent_task TEXT DEFAULT '0'")
            logger.info("Migrated: added 'parent_task' column to tasks table")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_task)")

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
            t.setdefault("type", "normal")
            t.setdefault("parent_task", "0")
        self._conn.executemany(
            """INSERT OR REPLACE INTO tasks
               (id, agent_id, device_serial, goal, status, result,
                created_at, started_at, finished_at, log_count, type, parent_task)
               VALUES (:id, :agent_id, :device_serial, :goal, :status, :result,
                       :created_at, :started_at, :finished_at, :log_count, :type, :parent_task)""",
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
            t.setdefault("type", "normal")
            t.setdefault("parent_task", "0")
            self._conn.execute(
                """INSERT OR REPLACE INTO tasks
                   (id, agent_id, device_serial, goal, status, result,
                    created_at, started_at, finished_at, log_count, type, parent_task)
                   VALUES (:id, :agent_id, :device_serial, :goal, :status, :result,
                           :created_at, :started_at, :finished_at, :log_count, :type, :parent_task)""",
                t,
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

    def load_child_tasks(self, parent_task_id: str) -> list[dict]:
        """加载某个父任务的所有子任务。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tasks WHERE parent_task = ? ORDER BY created_at DESC",
                (parent_task_id,),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if d.get("result") and isinstance(d["result"], str):
                    try:
                        d["result"] = json.loads(d["result"])
                    except json.JSONDecodeError:
                        d["result"] = None
                result.append(d)
            return result

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

    # ── Scheduled Tasks ──

    def load_scheduled_tasks(self, enabled_only: bool = False) -> list[dict]:
        with self._lock:
            sql = "SELECT * FROM scheduled_tasks"
            if enabled_only:
                sql += " WHERE enabled = 1"
            sql += " ORDER BY created_at DESC"
            rows = self._conn.execute(sql).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if d.get("device_serials") and isinstance(d["device_serials"], str):
                    try:
                        d["device_serials"] = json.loads(d["device_serials"])
                    except json.JSONDecodeError:
                        d["device_serials"] = []
                d["enabled"] = bool(d.get("enabled", 1))
                result.append(d)
            return result

    def append_scheduled_task(self, task: dict):
        with self._lock:
            t = dict(task)
            for key in ("created_at", "last_run", "next_run"):
                if key in t and isinstance(t[key], datetime):
                    t[key] = t[key].isoformat()
            if "device_serials" in t and isinstance(t["device_serials"], list):
                t["device_serials"] = json.dumps(t["device_serials"])
            if "enabled" in t and isinstance(t["enabled"], bool):
                t["enabled"] = 1 if t["enabled"] else 0
            self._conn.execute(
                """INSERT OR REPLACE INTO scheduled_tasks
                   (id, task_id, agent_id, goal, device_serials, cron_expression,
                    enabled, last_run, next_run, created_at)
                   VALUES (:id, :task_id, :agent_id, :goal, :device_serials, :cron_expression,
                           :enabled, :last_run, :next_run, :created_at)""",
                t,
            )
            self._conn.commit()

    def update_scheduled_task(self, task_id: str, updates: dict):
        with self._lock:
            vals = dict(updates)
            if "device_serials" in vals and isinstance(vals["device_serials"], list):
                vals["device_serials"] = json.dumps(vals["device_serials"])
            for key in ("last_run", "next_run"):
                if key in vals and isinstance(vals[key], datetime):
                    vals[key] = vals[key].isoformat()
            if "enabled" in vals and isinstance(vals["enabled"], bool):
                vals["enabled"] = 1 if vals["enabled"] else 0
            sets = ", ".join(f"{k} = ?" for k in vals)
            vlist = list(vals.values()) + [task_id]
            self._conn.execute(f"UPDATE scheduled_tasks SET {sets} WHERE id = ?", vlist)
            self._conn.commit()

    def get_scheduled_task(self, task_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("device_serials") and isinstance(d["device_serials"], str):
                try:
                    d["device_serials"] = json.loads(d["device_serials"])
                except json.JSONDecodeError:
                    d["device_serials"] = []
            d["enabled"] = bool(d.get("enabled", 1))
            return d

    def remove_scheduled_task(self, task_id: str):
        with self._lock:
            self._conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
            self._conn.commit()

    # ── Chat Records (聊天 Bot 专用) ──

    def save_chat_record(self, record: dict) -> int:
        """保存单条聊天记录（自动去重）。返回新记录的 id，重复则返回 -1。"""
        with self._lock:
            r = dict(record)
            now = datetime.now().isoformat()
            if "created_at" in r and isinstance(r["created_at"], datetime):
                r["created_at"] = r["created_at"].isoformat()
            r.setdefault("created_at", now)
            if "is_self" in r and isinstance(r["is_self"], bool):
                r["is_self"] = 1 if r["is_self"] else 0
            r.setdefault("nick_name", None)
            r.setdefault("avatar", None)
            r.setdefault("is_self", 0)

            # 去重检查
            dup = self._conn.execute(
                "SELECT id FROM chat_records "
                "WHERE source = ? AND chat_name = ? AND device_id = ? "
                "AND nick_name = ? AND content = ? LIMIT 1",
                (r.get("source", ""), r.get("chat_name", ""),
                 r.get("device_id", ""), r.get("nick_name"),
                 r.get("content", "")),
            ).fetchone()
            if dup:
                return -1

            cursor = self._conn.execute(
                """INSERT INTO chat_records
                   (source, chat_type, chat_name, nick_name, avatar, content,
                    is_self, device_id, device_user, created_at)
                   VALUES (:source, :chat_type, :chat_name, :nick_name, :avatar, :content,
                           :is_self, :device_id, :device_user, :created_at)""",
                r,
            )
            self._conn.commit()
            return cursor.lastrowid

    def save_chat_records(self, records: list[dict]) -> list[int]:
        """批量保存聊天记录（自动去重）。返回新记录的 id 列表。

        去重逻辑：同一聊天会话（source + chat_name + device_id）中，
        如果 nick_name + content 完全相同的记录已存在，则跳过。
        """
        ids = []
        now = datetime.now().isoformat()

        with self._lock:
            # 加载此聊天会话已有的消息，用于去重
            if records:
                sample = records[0]
                existing_rows = self._conn.execute(
                    "SELECT nick_name, content FROM chat_records "
                    "WHERE source = ? AND chat_name = ? AND device_id = ?",
                    (sample.get("source", ""), sample.get("chat_name", ""),
                     sample.get("device_id", "")),
                ).fetchall()
                existing = {
                    (r["nick_name"], r["content"]) for r in existing_rows
                }
            else:
                existing = set()

            for record in records:
                r = dict(record)
                if "created_at" in r and isinstance(r["created_at"], datetime):
                    r["created_at"] = r["created_at"].isoformat()
                r.setdefault("created_at", now)
                if "is_self" in r and isinstance(r["is_self"], bool):
                    r["is_self"] = 1 if r["is_self"] else 0
                r.setdefault("nick_name", None)
                r.setdefault("avatar", None)
                r.setdefault("is_self", 0)

                # 去重：nick_name + content 相同则跳过
                dedup_key = (r.get("nick_name"), r.get("content", ""))
                if dedup_key in existing:
                    continue
                existing.add(dedup_key)

                cursor = self._conn.execute(
                    """INSERT INTO chat_records
                       (source, chat_type, chat_name, nick_name, avatar, content,
                        is_self, device_id, device_user, created_at)
                       VALUES (:source, :chat_type, :chat_name, :nick_name, :avatar, :content,
                               :is_self, :device_id, :device_user, :created_at)""",
                    r,
                )
                ids.append(cursor.lastrowid)
            self._conn.commit()
        return ids

    def get_chat_history(
        self, chat_name: str = None, source: str = None, device_id: str = None, limit: int = 100
    ) -> list[dict]:
        """获取指定聊天的最近 N 条消息（按时间正序）。

        chat_name 和 source 均为可选，不传时返回全局最近消息。
        """
        with self._lock:
            conditions = []
            params = []
            if chat_name:
                conditions.append("chat_name = ?")
                params.append(chat_name)
            if source:
                conditions.append("source = ?")
                params.append(source)
            if device_id:
                conditions.append("device_id = ?")
                params.append(device_id)

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            params.append(limit)

            rows = self._conn.execute(
                f"""SELECT * FROM chat_records
                    {where}
                    ORDER BY created_at DESC LIMIT ?""",
                params,
            ).fetchall()
            result = [dict(r) for r in rows]
            result.reverse()  # 按时间正序
            for r in result:
                r["is_self"] = bool(r.get("is_self", 0))
            return result

    def get_recent_chats(self, source: str = None, device_id: str = None, limit: int = 10) -> list[dict]:
        """获取最近的聊天列表（按 chat_name 分组，返回每个聊天的最新消息）。"""
        with self._lock:
            conditions = []
            params = []
            if source:
                conditions.append("source = ?")
                params.append(source)
            if device_id:
                conditions.append("device_id = ?")
                params.append(device_id)

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            rows = self._conn.execute(
                f"""SELECT chat_name, source, chat_type, device_id, device_user,
                           MAX(created_at) as last_message_time,
                           COUNT(*) as message_count
                    FROM chat_records
                    {where}
                    GROUP BY chat_name, source, device_id
                    ORDER BY last_message_time DESC
                    LIMIT ?""",
                params + [limit],
            ).fetchall()
            return [dict(r) for r in rows]

    def get_chat_record_count(self, chat_name: str = None, source: str = None, device_id: str = None) -> int:
        """获取聊天记录数量。"""
        with self._lock:
            conditions = []
            params = []
            if chat_name:
                conditions.append("chat_name = ?")
                params.append(chat_name)
            if source:
                conditions.append("source = ?")
                params.append(source)
            if device_id:
                conditions.append("device_id = ?")
                params.append(device_id)

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            count = self._conn.execute(
                f"SELECT COUNT(*) FROM chat_records {where}", params
            ).fetchone()[0]
            return count

    # ── RAG 文档 ──

    def append_rag_document(self, doc: dict) -> int:
        """添加 RAG 文档。返回文档 ID。"""
        with self._lock:
            d = dict(doc)
            if "uploaded_at" in d and isinstance(d["uploaded_at"], datetime):
                d["uploaded_at"] = d["uploaded_at"].isoformat()
            cursor = self._conn.execute(
                """INSERT INTO rag_documents
                   (filename, file_path, parsed_text, chunk_count, language, uploaded_at, status)
                   VALUES (:filename, :file_path, :parsed_text, :chunk_count, :language, :uploaded_at, :status)""",
                d,
            )
            self._conn.commit()
            return cursor.lastrowid

    def load_rag_documents(self, status: str = None) -> list[dict]:
        """加载 RAG 文档列表。"""
        with self._lock:
            sql = "SELECT * FROM rag_documents"
            params = []
            if status:
                sql += " WHERE status = ?"
                params.append(status)
            sql += " ORDER BY uploaded_at DESC"
            rows = self._conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def get_rag_document(self, doc_id: int) -> Optional[dict]:
        """获取单个 RAG 文档。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM rag_documents WHERE id = ?", (doc_id,)
            ).fetchone()
            return dict(row) if row else None

    def delete_rag_document(self, doc_id: int):
        """删除 RAG 文档（标记为 archived）。"""
        with self._lock:
            self._conn.execute(
                "UPDATE rag_documents SET status = 'archived' WHERE id = ?",
                (doc_id,),
            )
            self._conn.commit()

    def update_rag_document(self, doc_id: int, updates: dict):
        """更新 RAG 文档信息。"""
        with self._lock:
            sets = ", ".join(f"{k} = ?" for k in updates)
            vals = list(updates.values()) + [doc_id]
            self._conn.execute(
                f"UPDATE rag_documents SET {sets} WHERE id = ?", vals
            )
            self._conn.commit()

    # ── RAG 问答历史 ──

    def append_rag_chat_history(self, record: dict) -> int:
        """添加 RAG 问答历史。返回记录 ID。"""
        with self._lock:
            r = dict(record)
            if "created_at" in r and isinstance(r["created_at"], datetime):
                r["created_at"] = r["created_at"].isoformat()
            if "source_docs" in r and isinstance(r["source_docs"], list):
                r["source_docs"] = json.dumps(r["source_docs"])
            cursor = self._conn.execute(
                """INSERT INTO rag_chat_history
                   (session_id, source, question, answer, language, source_docs, created_at)
                   VALUES (:session_id, :source, :question, :answer, :language, :source_docs, :created_at)""",
                r,
            )
            self._conn.commit()
            return cursor.lastrowid

    def get_rag_chat_history(
        self, session_id: str = None, source: str = None, limit: int = 50
    ) -> list[dict]:
        """获取 RAG 问答历史。"""
        with self._lock:
            conditions = []
            params = []
            if session_id:
                conditions.append("session_id = ?")
                params.append(session_id)
            if source:
                conditions.append("source = ?")
                params.append(source)

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            params.append(limit)

            rows = self._conn.execute(
                f"""SELECT * FROM rag_chat_history
                    {where}
                    ORDER BY created_at DESC LIMIT ?""",
                params,
            ).fetchall()

            result = [dict(r) for r in rows]
            for r in result:
                if r.get("source_docs") and isinstance(r["source_docs"], str):
                    try:
                        r["source_docs"] = json.loads(r["source_docs"])
                    except json.JSONDecodeError:
                        r["source_docs"] = []
            result.reverse()
            return result

    # ── 群组配置 ──

    def append_chat_group(self, group: dict) -> int:
        """添加群组配置。返回配置 ID。"""
        with self._lock:
            g = dict(group)
            if "created_at" in g and isinstance(g["created_at"], datetime):
                g["created_at"] = g["created_at"].isoformat()
            if "rag_enabled" in g and isinstance(g["rag_enabled"], bool):
                g["rag_enabled"] = 1 if g["rag_enabled"] else 0
            cursor = self._conn.execute(
                """INSERT OR IGNORE INTO chat_groups
                   (chat_name, source, device_id, default_language, rag_enabled, created_at)
                   VALUES (:chat_name, :source, :device_id, :default_language, :rag_enabled, :created_at)""",
                g,
            )
            self._conn.commit()
            return cursor.lastrowid

    def load_chat_groups(self, source: str = None) -> list[dict]:
        """加载群组配置列表。"""
        with self._lock:
            sql = "SELECT * FROM chat_groups"
            params = []
            if source:
                sql += " WHERE source = ?"
                params.append(source)
            sql += " ORDER BY created_at DESC"
            rows = self._conn.execute(sql, params).fetchall()
            result = [dict(r) for r in rows]
            for r in result:
                r["rag_enabled"] = bool(r.get("rag_enabled", 1))
            return result

    def get_chat_group(self, chat_name: str, source: str) -> Optional[dict]:
        """获取单个群组配置。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM chat_groups WHERE chat_name = ? AND source = ?",
                (chat_name, source),
            ).fetchone()
            if row:
                d = dict(row)
                d["rag_enabled"] = bool(d.get("rag_enabled", 1))
                return d
            return None

    def update_chat_group(self, chat_name: str, source: str, updates: dict):
        """更新群组配置。"""
        with self._lock:
            sets = ", ".join(f"{k} = ?" for k in updates)
            vals = list(updates.values()) + [chat_name, source]
            self._conn.execute(
                f"UPDATE chat_groups SET {sets} WHERE chat_name = ? AND source = ?",
                vals,
            )
            self._conn.commit()

    def delete_chat_group(self, chat_name: str, source: str):
        """删除群组配置。"""
        with self._lock:
            self._conn.execute(
                "DELETE FROM chat_groups WHERE chat_name = ? AND source = ?",
                (chat_name, source),
            )
            self._conn.commit()

    def close(self):
        """关闭数据库连接。"""
        with self._lock:
            self._conn.close()


# 全局单例
db = SQLiteStorage()
