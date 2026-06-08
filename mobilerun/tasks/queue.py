"""Task queue — manages pending tasks with JSON persistence."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from mobilerun.tasks.models import Task

logger = logging.getLogger("mobilerun")

DEFAULT_DIR = Path.home() / ".local" / "share" / "mobilerun" / "tasks"


class TaskQueue:
    """In-memory task queue with JSON file persistence."""

    def __init__(self, storage_dir: str | Path | None = None):
        self._storage_dir = Path(storage_dir) if storage_dir else DEFAULT_DIR
        self._tasks: Dict[str, Task] = {}
        self._load()

    def enqueue(self, task: Task) -> str:
        """Add a task to the queue. Returns task ID."""
        self._tasks[task.id] = task
        self._save()
        return task.id

    def dequeue(self) -> Optional[Task]:
        """Get the next pending task and mark it as running."""
        for task in self._tasks.values():
            if task.status == "pending":
                task.status = "running"
                task.updated_at = task.updated_at  # update timestamp
                self._save()
                return task
        return None

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def list_tasks(self, status: str | None = None) -> list[Task]:
        """List tasks, optionally filtered by status."""
        if status is None:
            return list(self._tasks.values())
        return [t for t in self._tasks.values() if t.status == status]

    def update_task(self, task_id: str, status: str, result: str | None = None, error: str | None = None) -> bool:
        """Update task status and optional result/error."""
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.status = status
        if result is not None:
            task.result = result
        if error is not None:
            task.error = error
        task.updated_at = task.updated_at
        self._save()
        return True

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending or running task."""
        task = self._tasks.get(task_id)
        if task and task.status in ("pending", "running"):
            task.status = "cancelled"
            self._save()
            return True
        return False

    def retry(self, task_id: str) -> bool:
        """Retry a failed task if retries remain."""
        task = self._tasks.get(task_id)
        if task and task.status == "failed" and task.retries < task.max_retries:
            task.status = "pending"
            task.retries += 1
            task.error = None
            self._save()
            return True
        return False

    def clear_completed(self, older_than_hours: int = 24) -> int:
        """Remove completed/failed/cancelled tasks older than N hours."""
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
        to_remove = []
        for tid, task in self._tasks.items():
            if task.status in ("completed", "failed", "cancelled"):
                try:
                    created = datetime.fromisoformat(task.created_at)
                    if created < cutoff:
                        to_remove.append(tid)
                except ValueError:
                    to_remove.append(tid)
        for tid in to_remove:
            del self._tasks[tid]
        if to_remove:
            self._save()
        return len(to_remove)

    def pending_count(self) -> int:
        return sum(1 for t in self._tasks.values() if t.status == "pending")

    # -- persistence ---------------------------------------------------------

    def _load(self) -> None:
        path = self._storage_dir / "queue.json"
        if not path.exists():
            self._tasks = {}
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._tasks = {tid: Task.from_dict(d) for tid, d in data.get("tasks", {}).items()}
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load task queue: {e}")
            self._tasks = {}

    def _save(self) -> None:
        path = self._storage_dir / "queue.json"
        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            data = {"tasks": {tid: t.to_dict() for tid, t in self._tasks.items()}}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error(f"Failed to save task queue: {e}")
