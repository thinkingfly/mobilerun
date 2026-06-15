"""专业 Agent 模块 — Supervisor 模式下的各 Agent 实现。"""

from server.langgraph.agents.base import AgentContext, AgentResult, BaseAgent
from server.langgraph.agents.registry import AgentRegistry, registry

# 导入各 Agent 模块以触发注册（顺序重要）
from server.langgraph.agents import (  # noqa: F401
    device_agent,
    chat_bot_agent,
    query_agent,
    schedule_agent,
)

__all__ = [
    "AgentContext",
    "AgentResult",
    "BaseAgent",
    "AgentRegistry",
    "registry",
]
