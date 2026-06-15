"""Query Agent — 处理状态查询和任务管理操作。

此 Agent 处理以下意图：
- query_status: 查询设备/系统状态
- manage_task: 任务管理（列表、取消、状态查询）
- manage_agent: Agent 管理（当前提示使用界面操作）
"""

import logging

from server.langgraph.agents.base import AgentContext, AgentResult, BaseAgent
from server.langgraph.agents.registry import registry
from server.state import state as app_state

logger = logging.getLogger("mobilerun.server.agents.query")


class QueryAgent(BaseAgent):
    """状态查询和任务管理 Agent。"""

    @property
    def name(self) -> str:
        return "query_agent"

    @property
    def description(self) -> str:
        return "查询设备状态、任务列表、任务详情、取消任务等"

    def can_handle(self, parsed_intent: dict, user_message: str) -> bool:
        """判断是否能处理此请求。

        处理 query_status、manage_task、manage_agent 意图。
        """
        intent = parsed_intent.get("intent")
        return intent in ("query_status", "manage_task", "manage_agent")

    async def execute(self, context: AgentContext) -> AgentResult:
        """执行查询或管理操作。"""
        intent = context.parsed_intent.get("intent")

        if intent == "query_status":
            return self._handle_query_status()
        elif intent == "manage_task":
            return self._handle_manage_task(context.parsed_intent)
        elif intent == "manage_agent":
            return self._handle_manage_agent()
        else:
            return AgentResult(
                success=False,
                response=f"未知的查询意图: {intent}",
            )

    def _handle_query_status(self) -> AgentResult:
        """处理状态查询。"""
        devices = app_state.list_devices()
        tasks = app_state.list_tasks()
        agents = app_state.list_agents()

        parts = []
        parts.append(f"设备总数: {len(devices)}")
        parts.append(f"   在线: {sum(1 for d in devices if d.state == 'online')}")
        parts.append(f"   忙碌: {sum(1 for d in devices if d.state == 'busy')}")
        parts.append(f"Agent: {len(agents)}")
        parts.append(
            f"任务: {len(tasks)} (运行中: {sum(1 for t in tasks if t.status == 'running')})"
        )

        return AgentResult(
            success=True,
            response="\n".join(parts),
        )

    def _handle_manage_task(self, parsed: dict) -> AgentResult:
        """处理任务管理操作。"""
        goal = parsed.get("goal", "")
        task_hint = parsed.get("task_id_or_hint", "")

        if goal == "list":
            return self._list_tasks()
        elif goal == "cancel":
            return self._cancel_task(task_hint)
        elif goal == "status":
            return self._task_status(task_hint)
        else:
            return AgentResult(
                success=False,
                response="请指定任务操作：查看任务列表(list)、取消任务(cancel)、或查询任务状态(status)。",
            )

    def _list_tasks(self) -> AgentResult:
        """列出任务。"""
        tasks = app_state.list_tasks()
        if not tasks:
            return AgentResult(success=True, response="当前没有任务。")

        parts = [f"任务列表（共 {len(tasks)} 个）:"]
        for t in tasks[:10]:
            status_icon = {
                "running": "🔄",
                "completed": "✅",
                "cancelled": "⏹",
                "failed": "❌",
            }.get(t.status, "⏳")
            type_tag = " [定时]" if t.type == "scheduled" else ""
            parts.append(f"  {status_icon} [{t.status}]{type_tag} {t.id}: {t.goal[:30]}")

        if len(tasks) > 10:
            parts.append(f"  ... 还有 {len(tasks) - 10} 个任务")

        return AgentResult(success=True, response="\n".join(parts))

    def _cancel_task(self, task_hint: str) -> AgentResult:
        """取消任务。"""
        running = [t for t in app_state.list_tasks() if t.status in ("running", "pending")]
        if not running:
            return AgentResult(success=True, response="当前没有运行中的任务。")

        task_id = None
        if task_hint and task_hint != "最新":
            # 尝试匹配任务 ID
            for t in running:
                if task_hint.lower() in t.id.lower():
                    task_id = t.id
                    break

        if not task_id:
            # 取消最新运行中的任务
            task_id = running[0].id

        app_state.cancel_task(task_id)
        if running:
            app_state.set_device_busy(running[0].device_serial, None)

        return AgentResult(success=True, response=f"已取消任务：{task_id}")

    def _task_status(self, task_hint: str) -> AgentResult:
        """查询任务状态。"""
        if task_hint:
            task = app_state.get_task(task_hint)
            if not task:
                # 尝试模糊匹配
                for t in app_state.list_tasks():
                    if task_hint.lower() in t.id.lower():
                        task = t
                        break

            if task:
                result_preview = ""
                if task.result:
                    reason = task.result.get("reason", "")[:100]
                    result_preview = f"\n结果: {reason}" if reason else ""

                response = (
                    f"任务 {task.id}\n"
                    f"目标: {task.goal}\n"
                    f"状态: {task.status}\n"
                    f"设备: {task.device_serial}\n"
                    f"创建时间: {task.created_at.isoformat()}"
                    f"{result_preview}"
                )
                return AgentResult(success=True, response=response)
            else:
                return AgentResult(success=True, response=f"未找到任务：{task_hint}")
        else:
            running = [t for t in app_state.list_tasks() if t.status == "running"]
            if not running:
                return AgentResult(success=True, response="当前没有运行中的任务。")
            else:
                parts = [f"运行中的任务（{len(running)} 个）:"]
                for t in running:
                    parts.append(
                        f"  🔄 [{t.id}] {t.goal[:40]} (设备: {t.device_serial})"
                    )
                return AgentResult(success=True, response="\n".join(parts))

    def _handle_manage_agent(self) -> AgentResult:
        """处理 Agent 管理。"""
        return AgentResult(
            success=True,
            response="请使用界面上的 Agent 管理功能来创建或删除 Agent。",
        )


# 注册 Agent
registry.register(QueryAgent())
