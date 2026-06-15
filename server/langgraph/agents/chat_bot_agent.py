"""ChatBot Agent — 专门处理微信/WhatsApp 等聊天软件的自动回复任务。

此 Agent 处理涉及聊天App的自动回复任务，包括：
- 打开聊天App
- 进入指定聊天窗口
- 读取聊天记录
- 生成并发送回复
- 存储聊天记录到数据库
"""

import asyncio
import logging
import uuid
from datetime import datetime

from server.langgraph.agents.base import AgentContext, AgentResult, BaseAgent
from server.langgraph.agents.registry import registry
from server.state import state as app_state
from server.storage import storage

logger = logging.getLogger("mobilerun.server.agents.chatbot")


class ChatBotAgent(BaseAgent):
    """聊天 Bot Agent。

    处理聊天App（微信/WhatsApp）的自动回复任务。
    """

    @property
    def name(self) -> str:
        return "chat_bot_agent"

    @property
    def description(self) -> str:
        return "处理聊天App（微信/WhatsApp）的自动回复任务，包括读取聊天记录和生成回复"

    def can_handle(self, parsed_intent: dict, user_message: str) -> bool:
        """判断是否能处理此请求。

        只处理 operate_device 意图且涉及聊天App的情况。
        """
        if parsed_intent.get("intent") != "operate_device":
            return False

        from server.langgraph.chat_bot_config import should_use_chat_bot

        goal = parsed_intent.get("goal", "")
        use_chat_bot, _, _ = should_use_chat_bot(goal)
        return use_chat_bot

    async def execute(self, context: AgentContext) -> AgentResult:
        """执行聊天 Bot 任务。"""
        from server.langgraph.chat_bot_agent import execute_chat_bot_task
        from server.langgraph.chat_bot_config import parse_target_chat, should_use_chat_bot
        from server.models import Task as TaskModel
        from server.websocket.log_handler import WebSocketLogHandler

        goal = context.parsed_intent.get("goal", "")
        device = context.device_serial

        if not device:
            return AgentResult(
                success=False,
                response="当前没有可用的设备，请先连接设备。",
            )

        # 解析聊天 App 信息
        use_chat_bot, app_name, app_config = should_use_chat_bot(goal)
        if not use_chat_bot:
            return AgentResult(
                success=False,
                response="无法识别聊天App",
            )

        # 解析目标聊天对象
        target_chat = parse_target_chat(goal, app_name)
        target_desc = f"（{target_chat}）" if target_chat else ""

        # 创建任务记录
        task_id = str(uuid.uuid4())[:8]
        now = datetime.now()

        task = TaskModel(
            id=task_id,
            agent_id=context.agent_id,
            device_serial=device,
            goal=goal,
            status="running",
            type="chat_bot",
            created_at=now,
            started_at=now,
        )
        app_state.create_task(task)
        app_state.set_device_busy(device, task_id)
        app_state.update_agent(context.agent_id, status="working", current_task=task_id)

        # 创建日志处理器
        ws_handler = WebSocketLogHandler(task_id)
        ws_handler.set_loop(asyncio.get_running_loop())

        # 异步执行 chat_bot 任务
        async def _run():
            try:
                result = await execute_chat_bot_task(
                    device_id=device,
                    source=app_config["source"],
                    app_name=app_name,
                    target_chat=target_chat,
                    agent_id=context.agent_id,
                    task_id=task_id,
                    log_handler=ws_handler,
                )

                if result.get("success"):
                    app_state.update_task_status(task_id, "completed", result=result)
                    self._append_result_message(
                        context.agent_id, task_id, app_name, result
                    )
                else:
                    app_state.update_task_status(task_id, "failed", result=result)
                    storage.append_message(context.agent_id, {
                        "role": "assistant",
                        "content": f"❌ {app_name}任务失败: {result.get('error', '未知错误')}",
                        "timestamp": datetime.now().isoformat(),
                        "task_id": task_id,
                    })

            except Exception as e:
                logger.error(f"Chat bot task error: {e}")
                app_state.update_task_status(
                    task_id, "failed", result={"success": False, "reason": str(e)}
                )
                storage.append_message(context.agent_id, {
                    "role": "assistant",
                    "content": f"❌ {app_name}任务异常: {str(e)}",
                    "timestamp": datetime.now().isoformat(),
                    "task_id": task_id,
                })
            finally:
                app_state.clear_runner(task_id)
                app_state.set_device_busy(device, None)
                app_state.update_agent(
                    context.agent_id, status="idle", current_task=None
                )

        asyncio.create_task(_run())

        return AgentResult(
            success=True,
            response=f"已启动 {app_name} 聊天 Bot{target_desc}，正在处理自动回复任务...",
            task_id=task_id,
        )

    def _append_result_message(
        self, agent_id: str, task_id: str, app_name: str, result: dict
    ):
        """将执行结果追加到对话历史。"""
        reply_sent = result.get("reply_sent", False)
        messages_read = result.get("messages_read", 0)

        if reply_sent:
            content = (
                f"✅ {app_name}自动回复完成：读取了 {messages_read} 条消息并已发送回复"
            )
        else:
            content = (
                f"✅ {app_name}聊天记录读取完成：共 {messages_read} 条消息（无需回复）"
            )

        storage.append_message(agent_id, {
            "role": "assistant",
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "task_id": task_id,
        })


# 注册 Agent
registry.register(ChatBotAgent())
