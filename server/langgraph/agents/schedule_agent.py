"""Schedule Agent — 处理定时/周期性任务创建。

此 Agent 处理 schedule_task 意图，创建定时任务。
"""

import logging
import uuid
from datetime import datetime

from server.langgraph.agents.base import AgentContext, AgentResult, BaseAgent
from server.langgraph.agents.registry import registry
from server.state import state as app_state
from server.storage import storage

logger = logging.getLogger("mobilerun.server.agents.schedule")


def _describe_cron(cron_expr: str) -> str:
    """将 cron 表达式转为人类可读描述。"""
    parts = cron_expr.split()
    if len(parts) != 5:
        return cron_expr
    minute, hour, dom, month, dow = parts

    if dom == "*" and month == "*" and dow == "*":
        if hour == "*" and minute.startswith("*/"):
            return f"每 {minute[2:]} 分钟"
        if hour == "*":
            return f"每小时第 {minute} 分"
        if minute == "0":
            return f"每天 {hour}:00"
        return f"每天 {hour}:{minute.zfill(2)}"
    if dow != "*" and dom == "*":
        day_map = {
            "1": "周一", "2": "周二", "3": "周三", "4": "周四",
            "5": "周五", "6": "周六", "0": "周日", "7": "周日",
        }
        if "-" in dow:
            days = dow.split("-")
            day_str = f"{day_map.get(days[0], dow)}至{day_map.get(days[-1], dow)}"
        else:
            day_str = day_map.get(dow, f"星期{dow}")
        return f"每{day_str} {hour}:{minute.zfill(2)}"
    return cron_expr


def _enrich_chat_goal(goal: str) -> str:
    """对涉及聊天/消息的 goal，自动追加验证步骤。"""
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


class ScheduleAgent(BaseAgent):
    """定时任务 Agent。"""

    @property
    def name(self) -> str:
        return "schedule_agent"

    @property
    def description(self) -> str:
        return "创建定时/周期性任务，如'每5分钟打开微信'、'每天早上9点截屏'"

    def can_handle(self, parsed_intent: dict, user_message: str) -> bool:
        """判断是否能处理此请求。"""
        return parsed_intent.get("intent") == "schedule_task"

    async def execute(self, context: AgentContext) -> AgentResult:
        """执行定时任务创建。"""
        from server.scheduler import scheduler

        parsed = context.parsed_intent
        goal = parsed.get("goal", "")
        cron_expr = parsed.get("cron_expression", "")
        agent_id = context.agent_id

        if not goal:
            return AgentResult(
                success=False,
                response="请告诉我您想定时执行什么操作。",
            )

        if not cron_expr:
            return AgentResult(
                success=False,
                response="无法解析定时规则，请使用明确的时间描述，如'每天早上9点打开微信'。",
            )

        # 验证 cron 表达式
        try:
            next_run = scheduler.compute_next_run(cron_expr)
        except Exception as e:
            return AgentResult(
                success=False,
                response=f"cron 表达式无效：{cron_expr}（{e}）",
            )

        # 获取设备列表
        devices = app_state.list_devices()
        device_serials = [d.serial for d in devices if d.state in ("online", "busy")]
        if not device_serials:
            return AgentResult(
                success=False,
                response="当前没有可用的设备，请先连接设备。",
            )

        st_id = str(uuid.uuid4())[:8]
        now = datetime.now()

        # 对聊天类任务追加验证步骤
        enriched_goal = _enrich_chat_goal(goal)

        scheduled_task = {
            "id": st_id,
            "task_id": st_id,
            "agent_id": agent_id,
            "goal": enriched_goal,
            "device_serials": device_serials,
            "cron_expression": cron_expr,
            "enabled": True,
            "last_run": None,
            "next_run": next_run.isoformat(),
            "created_at": now.isoformat(),
        }
        storage.append_scheduled_task(scheduled_task)

        logger.info(
            f"Created scheduled task: {st_id} cron={cron_expr} goal={goal[:50]}"
        )

        # 生成人类可读的时间描述
        cron_desc = _describe_cron(cron_expr)
        devs = "、".join(device_serials[:2])
        if len(device_serials) > 2:
            devs += f" 等 {len(device_serials)} 台"

        response = (
            f"✅ 定时任务已创建！\n"
            f"  目标：{goal}\n"
            f"  频率：{cron_desc}（{cron_expr}）\n"
            f"  设备：{devs}\n"
            f"  下次执行：{next_run.strftime('%Y-%m-%d %H:%M')}"
        )

        return AgentResult(success=True, response=response)


# 注册 Agent
registry.register(ScheduleAgent())
