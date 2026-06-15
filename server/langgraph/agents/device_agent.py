"""Device Agent — 处理设备通用操作（打开App、截屏、点击等）。

此 Agent 是 Supervisor 模式下的路由包装器，负责处理 operate_device 意图。
实际设备执行逻辑由 server.langgraph.device_agent 和 tools.execute_goal() 提供。
"""

import logging

from server.langgraph.agents.base import AgentContext, AgentResult, BaseAgent
from server.langgraph.agents.registry import registry
from server.langgraph.tools import execute_goal

logger = logging.getLogger("mobilerun.server.agents.device")


def _enrich_chat_goal(goal: str) -> str:
    """对涉及聊天/消息的 goal，自动追加验证步骤。

    确保 Agent 在回复前先确认当前聊天窗口是正确的对象（群名/联系人名）。
    """
    chat_keywords = [
        "回复", "发消息", "聊天", " reply", "发送消息", "自动回复",
        "群名", "群名称", "聊天记录", "消息", "告诉他", "告诉她",
    ]
    if any(kw in goal for kw in chat_keywords):
        verification = (
            "\n\n重要：在执行回复操作之前，必须先确认当前所在的聊天窗口是正确的。"
            "请查看屏幕顶部的群名或联系人名称，确认与目标一致后再输入和发送消息。"
            "如果发现不在正确的聊天窗口，不要发送任何消息，直接报告错误。"
        )
        return goal + verification
    return goal


class DeviceAgent(BaseAgent):
    """设备操作 Agent。

    处理通用的设备操作任务，如打开App、截屏、点击、滑动等。
    排除聊天App自动回复任务（由 ChatBotAgent 处理）。
    """

    @property
    def name(self) -> str:
        return "device_agent"

    @property
    def description(self) -> str:
        return "处理通用设备操作：打开App、截屏、点击、滑动、输入文字等"

    def can_handle(self, parsed_intent: dict, user_message: str) -> bool:
        """判断是否能处理此请求。

        处理 operate_device 意图，但排除聊天App自动回复（由 ChatBotAgent 处理）。
        """
        if parsed_intent.get("intent") != "operate_device":
            return False

        # 排除聊天 App 相关操作（由 ChatBotAgent 处理）
        from server.langgraph.chat_bot_config import should_use_chat_bot

        goal = parsed_intent.get("goal", "")
        use_chat_bot, _, _ = should_use_chat_bot(goal)
        return not use_chat_bot

    async def execute(self, context: AgentContext) -> AgentResult:
        """执行设备操作任务。"""
        parsed = context.parsed_intent
        goal = parsed.get("goal", "")
        device = context.device_serial
        vision_only = parsed.get("vision_only", False)

        if not goal:
            return AgentResult(
                success=False,
                response="请告诉我您想执行什么操作。",
            )

        if not device:
            return AgentResult(
                success=False,
                response="当前没有可用的设备，请先连接设备。",
            )

        # 对聊天类 goal 追加验证步骤
        enriched_goal = _enrich_chat_goal(goal)

        # 调用工具创建任务
        tool_result = execute_goal(
            enriched_goal,
            device,
            context.agent_id,
            vision_only=vision_only,
        )

        mode_str = "（纯视觉模式）" if vision_only else ""
        return AgentResult(
            success=True,
            response=f"已为您在设备 {device} 上创建任务：{goal}{mode_str}",
            task_id=tool_result.get("task_id"),
            data=tool_result,
        )


# 注册 Agent
registry.register(DeviceAgent())
