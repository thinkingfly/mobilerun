"""Agent 基类 — 所有专业 Agent 的统一接口。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResult:
    """Agent 执行结果。"""

    success: bool
    response: str                         # 给用户的响应文本
    task_id: str | None = None            # 关联的任务 ID（如果有）
    data: dict | None = field(default_factory=dict)  # 额外数据


@dataclass
class AgentContext:
    """Agent 执行上下文。"""

    user_message: str                     # 原始用户消息
    parsed_intent: dict                   # 解析后的意图
    device_serial: str | None             # 目标设备
    agent_id: str                         # 关联的 Agent ID
    log_handler: Any = None               # 日志处理器（可选）


class BaseAgent(ABC):
    """Agent 基类。

    所有专业 Agent 都必须实现此接口，并通过 AgentRegistry 注册。
    Supervisor 通过 can_handle() 判断是否能处理请求，
    然后调用 execute() 执行具体任务。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent 名称（唯一标识）。"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Agent 能力描述（供 Supervisor 选择参考）。"""
        ...

    @abstractmethod
    def can_handle(self, parsed_intent: dict, user_message: str) -> bool:
        """判断此 Agent 是否能处理该请求。

        Args:
            parsed_intent: 解析后的意图字典
            user_message: 原始用户消息

        Returns:
            是否能处理
        """
        ...

    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResult:
        """执行任务。

        Args:
            context: Agent 执行上下文

        Returns:
            执行结果
        """
        ...
