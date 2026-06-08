"""Pydantic data models for the Mobilerun Agent Dashboard."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Device(BaseModel):
    """设备信息。"""
    serial: str
    platform: str = "android"
    state: str = "offline"          # online / offline / busy
    portal_connected: bool = False
    current_task: Optional[str] = None
    last_seen: Optional[datetime] = None


class DeviceCreate(BaseModel):
    """添加设备请求。"""
    serial: str
    platform: str = "android"


class Task(BaseModel):
    """任务信息。"""
    id: str
    agent_id: str
    device_serial: str
    goal: str
    status: str = "pending"         # pending / running / completed / cancelled / failed
    result: Optional[dict] = None
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    log_count: int = 0


class TaskCreate(BaseModel):
    """创建任务请求。"""
    goal: str
    device_serial: Optional[str] = None
    agent_id: Optional[str] = None
    max_steps: int = 25
    reasoning: bool = False
    vision_only: bool = False


class Agent(BaseModel):
    """Agent 信息。"""
    id: str
    name: str
    device_serial: Optional[str] = None
    status: str = "idle"            # idle / working / error
    current_task: Optional[str] = None
    total_tasks: int = 0
    is_default: bool = False
    created_at: datetime = Field(default_factory=datetime.now)


class AgentCreate(BaseModel):
    """创建 Agent 请求。"""
    name: str
    device_serial: Optional[str] = None


class ChatMessage(BaseModel):
    """聊天消息。"""
    role: str                       # user / assistant / system
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    compressed: bool = False


class ChatHistoryResponse(BaseModel):
    """聊天历史响应（含统计）。"""
    messages: list[ChatMessage]
    total: int
    compressed: bool = False


class AgentMemory(BaseModel):
    """Agent 记忆管理。"""
    agent_id: str
    memory_summary: Optional[str] = None
    chat_count: int = 0


class ChatRequest(BaseModel):
    """对话请求。"""
    message: str
    device_serial: Optional[str] = None
    agent_id: Optional[str] = None


class LogEntry(BaseModel):
    """日志条目。"""
    msg: str
    color: Optional[str] = None
    stream: bool = False
    stream_end: bool = False
    level: int = 20
    timestamp: datetime = Field(default_factory=datetime.now)


class DashboardStats(BaseModel):
    """仪表盘统计。"""
    total_devices: int = 0
    online_devices: int = 0
    busy_devices: int = 0
    total_agents: int = 0
    active_agents: int = 0
    total_tasks: int = 0
    running_tasks: int = 0
    completed_tasks: int = 0
