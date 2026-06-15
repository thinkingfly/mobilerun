"""Agent 注册表 — 管理所有可用的专业 Agent。"""

import logging

from server.langgraph.agents.base import BaseAgent

logger = logging.getLogger("mobilerun.server.agents")


class AgentRegistry:
    """Agent 注册表。

    管理所有注册的专业 Agent，提供查询和路由功能。
    Supervisor 使用此注册表找到合适的 Agent 来处理用户请求。
    """

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent):
        """注册一个 Agent。

        Args:
            agent: 要注册的 Agent 实例
        """
        if agent.name in self._agents:
            logger.warning(f"Agent '{agent.name}' 已存在，将被覆盖")
        self._agents[agent.name] = agent
        logger.info(f"注册 Agent: {agent.name} - {agent.description}")

    def get_agent(self, name: str) -> BaseAgent | None:
        """获取指定名称的 Agent。

        Args:
            name: Agent 名称

        Returns:
            Agent 实例或 None
        """
        return self._agents.get(name)

    def find_agent(self, parsed_intent: dict, user_message: str) -> BaseAgent | None:
        """根据意图和消息找到合适的 Agent。

        按注册顺序遍历所有 Agent，返回第一个能处理的。

        Args:
            parsed_intent: 解析后的意图字典
            user_message: 原始用户消息

        Returns:
            合适的 Agent 实例或 None
        """
        for agent in self._agents.values():
            if agent.can_handle(parsed_intent, user_message):
                logger.debug(f"Agent '{agent.name}' 可以处理此请求")
                return agent
        logger.debug("没有匹配的 Agent，将使用默认 Agent")
        return None

    def list_agents(self) -> list[dict]:
        """列出所有注册的 Agent。

        Returns:
            Agent 信息列表 [{"name": str, "description": str}]
        """
        return [
            {"name": a.name, "description": a.description}
            for a in self._agents.values()
        ]

    @property
    def agent_names(self) -> list[str]:
        """获取所有 Agent 名称。"""
        return list(self._agents.keys())


# 全局注册表实例
registry = AgentRegistry()
