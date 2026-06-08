"""全局状态管理 — 设备、任务、Agent 和 WebSocket 订阅。"""

import asyncio
import json
import logging
import threading
import time
from datetime import datetime
from typing import Optional

from server.models import Agent, DashboardStats, Device, LogEntry, Task
from server.storage import storage

logger = logging.getLogger("mobilerun.server")


class AppState:
    """线程安全的全局状态存储。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._devices: dict[str, Device] = {}
        self._tasks: dict[str, Task] = {}
        self._agents: dict[str, Agent] = {}
        # task_id -> set of WebSocket send queues
        self._ws_subscribers: dict[str, set] = {}
        # task_id -> asyncio.Event for cancellation
        self._cancel_events: dict[str, asyncio.Event] = {}
        # task_id -> asyncio.Task reference
        self._task_runners: dict[str, asyncio.Task] = {}

        # 从持久化存储加载
        self._load_from_storage()

    def _load_from_storage(self):
        """从 JSON 文件加载任务和 Agent。"""
        try:
            # 加载任务
            raw_tasks = storage.load_tasks()
            for td in raw_tasks:
                try:
                    # 处理 datetime 字符串
                    for key in ("created_at", "started_at", "finished_at"):
                        if key in td and isinstance(td[key], str):
                            td[key] = datetime.fromisoformat(td[key])
                    task = Task(**td)
                    self._tasks[task.id] = task
                    self._ws_subscribers[task.id] = set()
                except Exception as e:
                    logger.warning(f"Failed to load task {td.get('id')}: {e}")
            logger.info(f"Loaded {len(self._tasks)} tasks from storage")

            # 加载 Agent
            raw_agents = storage.load_agents()
            for ad in raw_agents:
                try:
                    if "created_at" in ad and isinstance(ad["created_at"], str):
                        ad["created_at"] = datetime.fromisoformat(ad["created_at"])
                    agent = Agent(**ad)
                    self._agents[agent.id] = agent
                except Exception as e:
                    logger.warning(f"Failed to load agent {ad.get('id')}: {e}")
            logger.info(f"Loaded {len(self._agents)} agents from storage")
        except Exception as e:
            logger.error(f"Failed to load from storage: {e}")

    # ── 设备管理 ──

    def list_devices(self) -> list[Device]:
        with self._lock:
            return list(self._devices.values())

    def get_device(self, serial: str) -> Optional[Device]:
        with self._lock:
            return self._devices.get(serial)

    def upsert_device(self, serial: str, **kwargs) -> Device:
        with self._lock:
            if serial in self._devices:
                device = self._devices[serial]
                for k, v in kwargs.items():
                    setattr(device, k, v)
                device.last_seen = datetime.now()
            else:
                device = Device(serial=serial, **kwargs)
                self._devices[serial] = device
            return device

    def remove_device(self, serial: str):
        with self._lock:
            self._devices.pop(serial, None)

    def set_device_busy(self, serial: str, task_id: Optional[str]):
        with self._lock:
            if serial in self._devices:
                self._devices[serial].state = "busy" if task_id else "online"
                self._devices[serial].current_task = task_id

    # ── 任务管理 ──

    def list_tasks(self, status: Optional[str] = None) -> list[Task]:
        with self._lock:
            tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)

    def create_task(self, task: Task):
        with self._lock:
            self._tasks[task.id] = task
        self._ws_subscribers[task.id] = set()
        # 持久化
        storage.append_task(task.model_dump(mode="json"))

    def update_task_status(self, task_id: str, status: str, result: Optional[dict] = None):
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = status
                if result:
                    task.result = result
                if status == "running" and not task.started_at:
                    task.started_at = datetime.now()
                if status in ("completed", "cancelled", "failed"):
                    task.finished_at = datetime.now()
        # 持久化
        updates = {"status": status}
        if result:
            updates["result"] = result
        if status in ("completed", "cancelled", "failed"):
            updates["finished_at"] = datetime.now().isoformat()
        storage.update_task(task_id, updates)

    def increment_task_logs(self, task_id: str):
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.log_count += 1

    # ── Agent 管理 ──

    def list_agents(self) -> list[Agent]:
        with self._lock:
            return list(self._agents.values())

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        with self._lock:
            return self._agents.get(agent_id)

    def create_agent(self, agent: Agent):
        with self._lock:
            self._agents[agent.id] = agent
        # 持久化
        storage.append_agent(agent.model_dump(mode="json"))

    def remove_agent(self, agent_id: str):
        with self._lock:
            self._agents.pop(agent_id, None)
        # 持久化
        storage.remove_agent(agent_id)

    def update_agent(self, agent_id: str, **kwargs):
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent:
                for k, v in kwargs.items():
                    setattr(agent, k, v)
        # 持久化
        storage.update_agent(agent_id, kwargs)

    # ── 取消机制 ──

    def get_cancel_event(self, task_id: str) -> asyncio.Event:
        if task_id not in self._cancel_events:
            self._cancel_events[task_id] = asyncio.Event()
        return self._cancel_events[task_id]

    def cancel_task(self, task_id: str):
        if task_id in self._cancel_events:
            self._cancel_events[task_id].set()
        self.update_task_status(task_id, "cancelled")

    def register_runner(self, task_id: str, task: asyncio.Task):
        self._task_runners[task_id] = task

    def clear_runner(self, task_id: str):
        self._task_runners.pop(task_id, None)
        self._cancel_events.pop(task_id, None)

    # ── WebSocket 订阅 ──

    def subscribe(self, task_id: str, queue: asyncio.Queue):
        if task_id not in self._ws_subscribers:
            self._ws_subscribers[task_id] = set()
        self._ws_subscribers[task_id].add(queue)

    def unsubscribe(self, task_id: str, queue: asyncio.Queue):
        if task_id in self._ws_subscribers:
            self._ws_subscribers[task_id].discard(queue)

    async def broadcast_log(self, task_id: str, log_entry: LogEntry):
        if task_id in self._ws_subscribers:
            dead = set()
            for q in self._ws_subscribers[task_id]:
                try:
                    await q.put(log_entry.model_dump(mode="json"))
                except Exception:
                    dead.add(q)
            for q in dead:
                self._ws_subscribers[task_id].discard(q)

    # ── 统计 ──

    def get_stats(self) -> DashboardStats:
        with self._lock:
            devices = list(self._devices.values())
            tasks = list(self._tasks.values())
            agents = list(self._agents.values())

        return DashboardStats(
            total_devices=len(devices),
            online_devices=sum(1 for d in devices if d.state == "online"),
            busy_devices=sum(1 for d in devices if d.state == "busy"),
            total_agents=len(agents),
            active_agents=sum(1 for a in agents if a.status == "working"),
            total_tasks=len(tasks),
            running_tasks=sum(1 for t in tasks if t.status == "running"),
            completed_tasks=sum(1 for t in tasks if t.status == "completed"),
        )


# 全局单例
state = AppState()
