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

# 注意：RAG Agent 在 server/app.py 启动时延迟注册，
# 避免循环导入（rag/agent.py → agents.base → agents/__init__.py → rag/agent.py）

__all__ = [
    "AgentContext",
    "AgentResult",
    "BaseAgent",
    "AgentRegistry",
    "registry",
]
