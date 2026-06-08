"""Task and Schedule data models."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class Task:
    """A single automation task."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    instruction: str = ""
    config_overrides: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "pending"  # pending | running | completed | failed | cancelled
    result: Optional[str] = None
    error: Optional[str] = None
    retries: int = 0
    max_retries: int = 3
    scheduled_from: Optional[str] = None  # schedule ID if triggered by scheduler

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Schedule:
    """A recurring schedule that creates tasks on a cron-like basis."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    instruction: str = ""
    cron: str = ""  # 5-field cron: minute hour dom month dow
    config_overrides: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_run: Optional[str] = None
    next_run: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Schedule":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
