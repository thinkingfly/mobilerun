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
    type: str = "normal"            # normal / scheduled
    parent_task: str = "0"          # "0"=无父级, 否则为父级定时任务 ID
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
    device_serials: Optional[list[str]] = None  # 多选设备
    agent_id: Optional[str] = None


class ScheduledTask(BaseModel):
    """定时任务配置。"""
    id: str
    task_id: str
    agent_id: str
    goal: str
    device_serials: list[str]
    cron_expression: str
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)


class ScheduledTaskCreate(BaseModel):
    """创建定时任务请求。"""
    goal: str
    device_serials: list[str]
    cron_expression: str
    agent_id: Optional[str] = None


class LogEntry(BaseModel):
    """日志条目。"""
    seq: Optional[int] = None
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


# ── Chat Bot Models ──


class ChatBotRequest(BaseModel):
    """聊天 Bot 触发请求。"""
    source: str                       # wechat / whatsapp
    device_id: Optional[str] = None   # 设备序列号
    target_chat: Optional[str] = None # 指定聊天对象
    monitor: bool = False             # 是否启用监控模式（持续监听新消息）
    monitor_interval: int = 30        # 监控间隔秒数（默认 30）


class ChatRecord(BaseModel):
    """聊天记录。

    单聊场景：chat_name=对方联系人名, nick_name=消息发送者
    群聊场景：chat_name=群名, nick_name=该条消息的具体发送者
    """
    id: int
    source: str = Field(description="数据源标识: wechat / whatsapp / qq 等")
    chat_type: str = Field(description="聊天类型: single(单聊) / group(群聊)")
    chat_name: str = Field(description="群名或联系人名（标识这个聊天会话）")
    nick_name: Optional[str] = Field(default=None, description="这条消息的发送者昵称")
    avatar: Optional[str] = Field(default=None, description="发送者头像URL（可选，预留字段）")
    content: str = Field(description="消息内容（文本，或[图片]/[表情]等描述）")
    is_self: bool = Field(description="是否是本设备Agent发送的消息: False=对方发的, True=自己发的")
    device_id: str = Field(description="设备序列号（标识是哪台设备读取/发送的）")
    device_user: str = Field(description="Agent在该设备上使用的昵称（默认=设备号，可在代码中配置）")
    created_at: datetime = Field(description="消息时间（ISO格式，如 2026-06-12T10:30:00）")
