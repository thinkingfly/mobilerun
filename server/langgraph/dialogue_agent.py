"""LangGraph 对话理解 Agent — 将自然语言解析为结构化设备操作请求。"""

import logging
from typing import Literal

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from server.db import DB_PATH
from server.langgraph.tools import execute_goal
from server.state import state as app_state

logger = logging.getLogger("mobilerun.server.dialogue")

# ── 系统提示词 ──
SYSTEM_PROMPT = """你是一个移动设备管理助手。用户会给你发送自然语言指令，
你需要解析用户的意图并返回结构化的操作指令。

你必须返回一个 JSON 对象，包含以下字段：
- intent: 操作意图 (operate_device / query_status / manage_task / manage_agent / chat)
- goal: 要执行的具体操作目标（自然语言描述，manage_task 意图下为 "list"/"cancel"/"status"）
- task_id_or_hint: 任务 ID 或提示（如"最新"、"第一个"等，仅 manage_task 时使用）
- device_serial: 目标设备序列号（如果用户指定了设备，如"用第一台设备"、"用AK3SBB5530100840"等；否则为 null）
- device_hint: 设备提示（如"第一台"、"第二台"、"全部"等，用于辅助选择）
- vision_only: 是否需要纯视觉模式 (bool)。目标涉及以下 App 时必须设为 true：微信、QQ、支付宝、银行类 App、钉钉、企业微信；或者需要读取屏幕上的文字/群名称/聊天内容时。普通系统操作（打开设置、计算器、浏览器等）设为 false

可用意图说明：
- operate_device: 要求在某台设备上执行具体操作（如"打开微信"、"截屏"、"点赞"、"滑动"、"输入文字"等）
- query_status: 查询设备概况和总体统计（如"设备状态"、"在线吗"、"有几个Agent"、"整体情况"等），不涉及具体任务操作
- manage_task: 任务管理操作 —— 凡是涉及任务的操作都走这个意图，包括：查看任务列表(list)、取消任务(cancel)、查询任务详情(status)
- manage_agent: 创建/删除 Agent
- chat: 普通对话聊天、问候、感谢等，不需要操作设备

重要区分：
- "有几个任务"、"任务数量" → query_status（查询统计数字）
- "查看任务列表"、"列出任务"、"任务有哪些" → manage_task with goal="list"（列出具体任务）
- "取消任务"、"取消最新任务" → manage_task with goal="cancel"
- "任务xxx的状态"、"查看任务详情" → manage_task with goal="status"

返回格式示例：
{"intent": "operate_device", "goal": "打开微信，返回群名称", "vision_only": true, "device_serial": null, "device_hint": "第一台"}
{"intent": "operate_device", "goal": "打开设置", "vision_only": false, "device_serial": null, "device_hint": null}
{"intent": "query_status", "goal": "查看整体情况", "device_serial": null, "device_hint": null}
{"intent": "manage_task", "goal": "list", "task_id_or_hint": null, "device_serial": null, "device_hint": null}
{"intent": "manage_task", "goal": "cancel", "task_id_or_hint": "最新", "device_serial": null, "device_hint": null}
{"intent": "manage_task", "goal": "status", "task_id_or_hint": "e5b12bc0", "device_serial": null, "device_hint": null}
{"intent": "chat", "goal": null, "device_serial": null, "device_hint": null}"""


# ── vision_only 自动判断 ──
def _auto_vision_only(text: str) -> bool:
    """根据关键词自动判断是否需要 vision_only 模式。"""
    security_apps = ["微信", "支付宝", "银行", "钉钉", "企业微信", "QQ", "美团", "饿了么", "淘宝", "京东"]
    if any(kw in text for kw in security_apps):
        return True
    if any(kw in text for kw in ["群名", "群名称", "聊天", "消息", "文字", "内容", "看看", "截图", "截屏"]):
        return True
    return False


class DialogueState(TypedDict):
    """对话状态。"""
    user_message: str
    parsed: dict
    response: str
    agent_id: str            # 当前对话关联的 Agent ID
    task_result: dict        # execute_goal 工具返回的任务执行结果


def parse_intent(state: DialogueState) -> DialogueState:
    """解析用户意图（使用 LLM）。"""
    import json

    from server.langgraph.utils import call_llm

    message = state["user_message"]
    prompt = f"{SYSTEM_PROMPT}\n\n用户指令: {message}\n\n返回 JSON:"

    try:
        result = call_llm(prompt)
        parsed = json.loads(result)
        if not isinstance(parsed, dict):
            parsed = {"intent": "chat", "goal": None, "device_serial": None, "device_hint": None, "vision_only": False}
        parsed.setdefault("intent", "chat")
        parsed.setdefault("goal", None)
        parsed.setdefault("device_serial", None)
        parsed.setdefault("device_hint", None)
        parsed.setdefault("vision_only", False)
        if not isinstance(parsed["vision_only"], bool):
            parsed["vision_only"] = bool(parsed["vision_only"])

        # LLM 可能不返回 vision_only，用关键词自动判断
        if _auto_vision_only((parsed.get("goal") or "") + " " + message):
            parsed["vision_only"] = True

        state["parsed"] = parsed
        logger.info(f"解析意图: {parsed}")
    except Exception as e:
        logger.warning(f"解析意图失败: {e}，默认使用 operate_device")
        state["parsed"] = {
            "intent": "operate_device",
            "goal": message,
            "device_serial": None,
            "device_hint": None,
            "vision_only": _auto_vision_only(message),
        }

    return state


def resolve_device(state: DialogueState) -> DialogueState:
    """解析设备选择。manage_task 意图跳过设备解析。"""
    intent = state["parsed"].get("intent", "chat")
    if intent == "manage_task":
        return state

    parsed = state["parsed"]
    hint = parsed.get("device_hint")

    if parsed.get("device_serial"):
        return state

    devices = app_state.list_devices()
    if not devices:
        parsed["device_serial"] = None
        return state

    if hint and "全部" in hint:
        for d in devices:
            if d.state in ("online", "busy"):
                parsed["device_serial"] = d.serial
                return state
    elif hint and ("第二" in hint or "2" in hint):
        online = [d for d in devices if d.state in ("online", "busy")]
        if len(online) >= 2:
            parsed["device_serial"] = online[1].serial
        elif online:
            parsed["device_serial"] = online[0].serial
    else:
        for d in devices:
            if d.state in ("online", "busy"):
                parsed["device_serial"] = d.serial
                return state
        if devices:
            parsed["device_serial"] = devices[0].serial

    return state


def route_intent(state: DialogueState) -> Literal["operate", "query", "manage", "manage_task", "chat"]:
    """根据意图路由。"""
    intent = state["parsed"].get("intent", "chat")
    if intent == "operate_device":
        return "operate"
    elif intent == "query_status":
        return "query"
    elif intent == "manage_agent":
        return "manage"
    elif intent == "manage_task":
        return "manage_task"
    return "chat"


def handle_operate(state: DialogueState) -> DialogueState:
    """处理设备操作意图 — 调用 execute_goal 工具创建任务。"""
    parsed = state["parsed"]
    goal = parsed.get("goal", "")
    device = parsed.get("device_serial")
    agent_id = state.get("agent_id", "")

    if not goal:
        state["response"] = "请告诉我您想执行什么操作。"
        return state

    if not device:
        state["response"] = "当前没有可用的设备，请先连接设备。"
        return state

    # 调用工具创建任务记录
    vision_only = parsed.get("vision_only", False)
    tool_result = execute_goal(goal, device, agent_id, vision_only=vision_only)
    state["task_result"] = tool_result
    mode_str = "纯视觉模式" if vision_only else ""
    state["response"] = f"已为您在设备 {device} 上创建任务：{goal}{mode_str}"
    return state


def handle_query(state: DialogueState) -> DialogueState:
    """处理查询意图。"""
    devices = app_state.list_devices()
    tasks = app_state.list_tasks()
    agents = app_state.list_agents()

    parts = []
    parts.append(f"设备总数: {len(devices)}")
    parts.append(f"   在线: {sum(1 for d in devices if d.state == 'online')}")
    parts.append(f"   忙碌: {sum(1 for d in devices if d.state == 'busy')}")
    parts.append(f"Agent: {len(agents)}")
    parts.append(f"任务: {len(tasks)} (运行中: {sum(1 for t in tasks if t.status == 'running')})")

    state["response"] = "\n".join(parts)
    return state


def handle_manage(state: DialogueState) -> DialogueState:
    """处理 Agent 管理意图。"""
    state["response"] = "请使用界面上的 Agent 管理功能来创建或删除 Agent。"
    return state


def handle_manage_task(state: DialogueState) -> DialogueState:
    """处理任务管理意图（列表、取消、状态查询）。"""
    parsed = state["parsed"]
    goal = parsed.get("goal", "")
    task_hint = parsed.get("task_id_or_hint", "")

    if goal == "list":
        tasks = app_state.list_tasks()
        if not tasks:
            state["response"] = "当前没有任务。"
            return state
        parts = [f"任务列表（共 {len(tasks)} 个）:"]
        for t in tasks[:10]:
            status_icon = {"running": "🔄", "completed": "✅", "cancelled": "⏹", "failed": "❌"}.get(t.status, "⏳")
            parts.append(f"  {status_icon} [{t.status}] {t.id}: {t.goal[:30]}")
        if len(tasks) > 10:
            parts.append(f"  ... 还有 {len(tasks) - 10} 个任务")
        state["response"] = "\n".join(parts)

    elif goal == "cancel":
        running = [t for t in app_state.list_tasks() if t.status in ("running", "pending")]
        if not running:
            state["response"] = "当前没有运行中的任务。"
            return state

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
        app_state.set_device_busy(running[0].device_serial if running else None, None)
        state["response"] = f"已取消任务：{task_id}"

    elif goal == "status":
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
                state["response"] = (
                    f"任务 {task.id}\n"
                    f"目标: {task.goal}\n"
                    f"状态: {task.status}\n"
                    f"设备: {task.device_serial}\n"
                    f"创建时间: {task.created_at.isoformat()}"
                    f"{result_preview}"
                )
            else:
                state["response"] = f"未找到任务：{task_hint}"
        else:
            running = [t for t in app_state.list_tasks() if t.status == "running"]
            if not running:
                state["response"] = "当前没有运行中的任务。"
            else:
                parts = [f"运行中的任务（{len(running)} 个）:"]
                for t in running:
                    parts.append(f"  🔄 [{t.id}] {t.goal[:40]} (设备: {t.device_serial})")
                state["response"] = "\n".join(parts)

    else:
        state["response"] = "请指定任务操作：查看任务列表(list)、取消任务(cancel)、或查询任务状态(status)。"

    return state


def handle_chat(state: DialogueState) -> DialogueState:
    """处理普通对话。"""
    from server.langgraph.utils import call_llm

    message = state["user_message"]
    prompt = f"你是一个移动设备管理助手。用户说：{message}\n请友好地回复，告诉用户你可以帮他们控制手机设备。"

    try:
        state["response"] = call_llm(prompt)
    except Exception:
        state["response"] = "你好！我可以帮你控制 Android 设备。请告诉我你想执行什么操作。"

    return state


def _build_graph():
    """构建对话理解 LangGraph（含 SQLite 永久持久化）。"""
    from langgraph.checkpoint.sqlite import SqliteSaver

    graph = StateGraph(DialogueState)

    graph.add_node("parse", parse_intent)
    graph.add_node("resolve_device", resolve_device)
    graph.add_node("operate", handle_operate)
    graph.add_node("query", handle_query)
    graph.add_node("manage", handle_manage)
    graph.add_node("manage_task", handle_manage_task)
    graph.add_node("chat", handle_chat)

    graph.add_edge("parse", "resolve_device")
    graph.add_conditional_edges(
        "resolve_device",
        route_intent,
        {
            "operate": "operate",
            "query": "query",
            "manage": "manage",
            "manage_task": "manage_task",
            "chat": "chat",
        },
    )
    graph.add_edge("operate", END)
    graph.add_edge("query", END)
    graph.add_edge("manage", END)
    graph.add_edge("manage_task", END)
    graph.add_edge("chat", END)

    graph.set_entry_point("parse")

    # 独立 SQLite 连接（与 server/db.py 共用同一数据库文件）
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    checkpointer = SqliteSaver(conn)

    return graph.compile(checkpointer=checkpointer)


# 全局图实例（含 SQLite 永久持久化）
graph = _build_graph()
logger.info(f"LangGraph checkpointer: {DB_PATH}")


def process_message(message: str, agent_id: str = "default") -> dict:
    """处理用户消息，返回结构化结果。

    Args:
        message: 用户消息
        agent_id: 当前对话关联的 Agent ID，用作 checkpointer 的 thread_id

    Returns:
        {
            "response": str,
            "intent": str,
            "goal": str | None,
            "device_serial": str | None,
            "should_create_task": bool,
            "task_result": dict | None,  # execute_goal 工具返回的任务信息
        }
    """
    config = {"configurable": {"thread_id": agent_id}}
    result = graph.invoke(
        {
            "user_message": message,
            "parsed": {},
            "response": "",
            "agent_id": agent_id,
            "task_result": {},
        },
        config=config,
    )

    parsed = result.get("parsed", {})
    response = result.get("response", "")
    task_result = result.get("task_result") or {}

    should_create_task = (
        parsed.get("intent") == "operate_device"
        and bool(parsed.get("goal"))
        and bool(parsed.get("device_serial"))
    )

    return {
        "response": response,
        "intent": parsed.get("intent", "chat"),
        "goal": parsed.get("goal"),
        "device_serial": parsed.get("device_serial"),
        "vision_only": parsed.get("vision_only", False),
        "should_create_task": should_create_task,
        "task_result": task_result if task_result else None,
    }
