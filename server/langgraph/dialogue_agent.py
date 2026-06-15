"""LangGraph Supervisor — 多 Agent 协调者。

使用 Supervisor 模式进行多 Agent 路由：
1. parse_intent: 解析用户意图（LLM）
2. resolve_device: 解析设备选择
3. select_agent: 通过 AgentRegistry 选择合适的 Agent
4. route_to_agent: 路由到选中的 Agent 执行

各专业 Agent 实现在 server/langgraph/agents/ 目录下。
"""

import logging
import re
from typing import Literal

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from server.langgraph.agents.base import AgentContext
from server.langgraph.agents.registry import registry
from server.state import state as app_state

# 导入各 Agent 模块以触发注册
from server.langgraph.agents import (  # noqa: F401
    chat_bot_agent,
    device_agent,
    query_agent,
    schedule_agent,
)

logger = logging.getLogger("mobilerun.server.supervisor")

# ── 系统提示词 ──
SYSTEM_PROMPT = """你是一个移动设备管理助手。用户会给你发送自然语言指令，
你需要解析用户的意图并返回结构化的操作指令。

你必须返回一个 JSON 对象，包含以下字段：
- intent: 操作意图 (operate_device / query_status / manage_task / manage_agent / schedule_task / chat)
- goal: 要执行的具体操作目标（自然语言描述）。注意：如果是定时任务，goal 只包含操作内容，去掉时间描述。例如"每5分钟打开微信"的 goal 是"打开微信"，不是"每5分钟打开微信"
- task_id_or_hint: 任务 ID 或提示（如"最新"、"第一个"等，仅 manage_task 时使用）
- device_serial: 目标设备序列号（如果用户指定了设备，如"用第一台设备"、"用AK3SBB5530100840"等；否则为 null）
- device_hint: 设备提示（如"第一台"、"第二台"、"全部"等，用于辅助选择）
- vision_only: 是否需要纯视觉模式 (bool)。目标涉及以下 App 时必须设为 true：微信、QQ、支付宝、银行类 App、钉钉、企业微信；或者需要读取屏幕上的文字/群名称/聊天内容时。普通系统操作（打开设置、计算器、浏览器等）设为 false
- cron_expression: cron 表达式（仅 schedule_task 意图时使用，如 "0 9 * * *" 表示每天9点，"*/5 * * * *" 表示每5分钟）

可用意图说明：
- operate_device: 要求在某台设备上立即执行具体操作（如"打开微信"、"截屏"、"点赞"等）。注意：不包含任何时间/频率描述
- query_status: 查询设备概况和总体统计（如"设备状态"、"在线吗"等），不涉及具体任务操作
- manage_task: 任务管理操作 —— 查看任务列表(list)、取消任务(cancel)、查询任务详情(status)
- manage_agent: 创建/删除 Agent
- schedule_task: 创建定时/周期性任务。★★★ 关键判断规则：只要用户消息中包含以下任何时间模式，必须使用 schedule_task：
  * "每N分钟"、"每N小时"（如"每5分钟"、"每30分钟"、"每小时"）
  * "每天"、"每日"（如"每天早上9点"、"每天晚上"）
  * "每隔"、"每隔N"（如"每隔10分钟"）
  * "定时"、"定期"（如"定时执行"、"定期检查"）
  * "每周"、"每月"、"每年"
  * "星期X"、"周一"到"周日"
  * "X点"、"X:XX"（如"9点"、"下午3:30"）
  当识别为 schedule_task 时，goal 字段只写操作内容（去掉时间描述），cron_expression 字段填写对应的 cron 表达式
- chat: 普通对话聊天、问候、感谢等，不需要操作设备

★★★ 重要区分（务必注意）★★★：
- "每5分钟打开微信" → schedule_task（有"每5分钟"时间模式）, goal="打开微信", cron="*/5 * * * *"
- "每5分钟打开微信瞎聊群，查看聊天记录，自动回复" → schedule_task, goal="打开微信瞎聊群，查看最近的聊天记录，自动回复相关内容", cron="*/5 * * * *"
- "每小时截屏一次" → schedule_task, goal="截屏", cron="0 * * * *"
- "每天早上9点打开微信" → schedule_task, goal="打开微信", cron="0 9 * * *"
- "打开微信" → operate_device（没有时间描述，立即执行）
- "打开微信查看聊天记录" → operate_device（没有时间描述，立即执行）
- "取消最新任务" → manage_task with goal="cancel"
- "查看任务列表" → manage_task with goal="list"

cron 表达式说明（5位：分 时 日 月 星期）：
- "每5分钟" → "*/5 * * * *"
- "每10分钟" → "*/10 * * * *"
- "每30分钟" → "*/30 * * * *"
- "每小时" → "0 * * * *"
- "每天9点" → "0 9 * * *"
- "每天上午10点" → "0 10 * * *"
- "每周一到周五上午8:30" → "30 8 * * 1-5"
- "每周一下午2点" → "0 14 * * 1"

返回格式示例：
{"intent": "schedule_task", "goal": "打开微信瞎聊群，查看最近的聊天记录，自动回复相关内容", "cron_expression": "*/5 * * * *", "vision_only": true, "device_serial": null, "device_hint": null}
{"intent": "operate_device", "goal": "打开微信，返回群名称", "vision_only": true, "device_serial": null, "device_hint": null}
{"intent": "operate_device", "goal": "打开设置", "vision_only": false, "device_serial": null, "device_hint": null}
{"intent": "schedule_task", "goal": "打开微信查看消息", "cron_expression": "0 9 * * *", "vision_only": true, "device_serial": null, "device_hint": null}
{"intent": "query_status", "goal": "查看整体情况", "device_serial": null, "device_hint": null}
{"intent": "manage_task", "goal": "list", "task_id_or_hint": null, "device_serial": null, "device_hint": null}
{"intent": "manage_task", "goal": "cancel", "task_id_or_hint": "最新", "device_serial": null, "device_hint": null}
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


# ── 定时任务模式匹配（兜底） ──

_SCHEDULE_PATTERNS = [
    # 每N分钟/小时
    (re.compile(r'每\s*(\d+)\s*分钟'), lambda m: f'*/{m.group(1)} * * * *'),
    (re.compile(r'每\s*(\d+)\s*小时'), lambda m: f'0 */{m.group(1)} * * *'),
    (re.compile(r'每隔\s*(\d+)\s*分钟'), lambda m: f'*/{m.group(1)} * * * *'),
    (re.compile(r'每隔\s*(\d+)\s*小时'), lambda m: f'0 */{m.group(1)} * * *'),
    # 每小时/每分钟
    (re.compile(r'每小时'), lambda m: '0 * * * *'),
    (re.compile(r'每半小时'), lambda m: '*/30 * * * *'),
    # 每天X点
    (re.compile(r'每天\s*(?:早上|上午)?\s*(\d{1,2})\s*[点时:：]\s*(?:(\d{1,2})\s*分?)?'), lambda m: f'{m.group(2) or "0"} {m.group(1)} * * *'),
    (re.compile(r'每天\s*(?:下午|晚上)\s*(\d{1,2})\s*[点时:：]\s*(?:(\d{1,2})\s*分?)?'), lambda m: f'{m.group(2) or "0"} {int(m.group(1)) + 12} * * *'),
    (re.compile(r'每日'), lambda m: '0 9 * * *'),
    # 定时/定期
    (re.compile(r'定时|定期'), lambda m: '0 * * * *'),
]


def _detect_schedule_pattern(text: str) -> str | None:
    """检测文本中的定时模式，返回 cron 表达式或 None。"""
    for pattern, cron_fn in _SCHEDULE_PATTERNS:
        m = pattern.search(text)
        if m:
            try:
                return cron_fn(m)
            except Exception:
                continue
    return None


def _extract_goal_without_schedule(text: str) -> str:
    """从用户消息中去掉时间前缀，提取纯操作目标。"""
    # 去掉开头的时间描述
    cleaned = re.sub(
        r'^(每\s*\d+\s*(?:分钟|小时)|每隔\s*\d+\s*(?:分钟|小时)|每小时|每半小时|每天\s*(?:早上|上午|下午|晚上)?\s*\d{1,2}\s*[点时:：]\s*(?:\d{1,2}\s*分?)?|定时|定期)\s*',
        '', text.strip()
    )
    # 去掉末尾的频率描述
    cleaned = re.sub(r'[，,]\s*(一次|一回).*$', '', cleaned)
    return cleaned.strip() or text.strip()


class SupervisorState(TypedDict):
    """Supervisor 状态。"""
    user_message: str
    parsed: dict
    selected_agent: str          # 选中的 Agent 名称
    response: str
    agent_id: str                # 当前对话关联的 Agent ID
    task_result: dict            # execute_goal 工具返回的任务执行结果


# ── 节点函数 ──

def parse_intent(state: SupervisorState) -> SupervisorState:
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
        parsed.setdefault("cron_expression", None)
        if not isinstance(parsed["vision_only"], bool):
            parsed["vision_only"] = bool(parsed["vision_only"])

        # LLM 可能不返回 vision_only，用关键词自动判断
        if _auto_vision_only((parsed.get("goal") or "") + " " + message):
            parsed["vision_only"] = True

        # ★ 兜底1：LLM 识别为 schedule_task 但缺少 cron_expression，用正则补全
        if parsed["intent"] == "schedule_task" and not parsed.get("cron_expression"):
            cron = _detect_schedule_pattern(message)
            if cron:
                parsed["cron_expression"] = cron
                raw_goal = parsed.get("goal") or message
                parsed["goal"] = _extract_goal_without_schedule(raw_goal)
                logger.info(f"兜底补全 cron: {cron}, goal={parsed['goal'][:50]}")

        # ★ 兜底2：只要消息包含定时模式，且 LLM 未识别为 schedule_task，强制纠正
        if parsed["intent"] != "schedule_task" and not parsed.get("cron_expression"):
            cron = _detect_schedule_pattern(message)
            if cron:
                old_intent = parsed["intent"]
                parsed["intent"] = "schedule_task"
                parsed["cron_expression"] = cron
                raw_goal = parsed.get("goal") or message
                parsed["goal"] = _extract_goal_without_schedule(raw_goal)
                logger.info(f"兜底纠正: {old_intent} → schedule_task, cron={cron}, goal={parsed['goal'][:50]}")

        state["parsed"] = parsed
        logger.info(f"解析意图: {parsed}")
    except Exception as e:
        logger.warning(f"解析意图失败: {e}，默认使用 operate_device")
        parsed = {
            "intent": "operate_device",
            "goal": message,
            "device_serial": None,
            "device_hint": None,
            "vision_only": _auto_vision_only(message),
            "cron_expression": None,
        }
        # ★ LLM 失败时也要执行正则兜底检测定时任务
        cron = _detect_schedule_pattern(message)
        if cron:
            parsed["intent"] = "schedule_task"
            parsed["cron_expression"] = cron
            parsed["goal"] = _extract_goal_without_schedule(message)
            logger.info(f"兜底纠正(LLM失败): schedule_task, cron={cron}, goal={parsed['goal'][:50]}")
        state["parsed"] = parsed

    return state


def resolve_device(state: SupervisorState) -> SupervisorState:
    """解析设备选择。manage_task 和 schedule_task 意图跳过设备解析。"""
    intent = state["parsed"].get("intent", "chat")
    if intent in ("manage_task", "schedule_task"):
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


def select_agent(state: SupervisorState) -> SupervisorState:
    """通过 AgentRegistry 选择合适的 Agent。"""
    parsed = state["parsed"]
    message = state["user_message"]
    intent = parsed.get("intent", "chat")

    # 普通聊天直接处理，不走 Agent
    if intent == "chat":
        state["selected_agent"] = "chat"
        return state

    # 使用注册表查找合适的 Agent
    agent = registry.find_agent(parsed, message)
    if agent:
        state["selected_agent"] = agent.name
        logger.info(f"Supervisor 选择 Agent: {agent.name}")
    else:
        # 默认使用 device_agent
        state["selected_agent"] = "device_agent"
        logger.info("Supervisor 使用默认 Agent: device_agent")

    return state


def route_to_agent(state: SupervisorState) -> str:
    """路由到选中的 Agent。"""
    return state.get("selected_agent", "chat")


# ── Agent 执行节点 ──

async def execute_device_agent(state: SupervisorState) -> SupervisorState:
    """执行 Device Agent。"""
    agent = registry.get_agent("device_agent")
    context = AgentContext(
        user_message=state["user_message"],
        parsed_intent=state["parsed"],
        device_serial=state["parsed"].get("device_serial"),
        agent_id=state.get("agent_id", ""),
    )
    result = await agent.execute(context)
    state["response"] = result.response
    state["task_result"] = result.data or {}
    return state


async def execute_chat_bot_agent(state: SupervisorState) -> SupervisorState:
    """执行 ChatBot Agent。"""
    agent = registry.get_agent("chat_bot_agent")
    context = AgentContext(
        user_message=state["user_message"],
        parsed_intent=state["parsed"],
        device_serial=state["parsed"].get("device_serial"),
        agent_id=state.get("agent_id", ""),
    )
    result = await agent.execute(context)
    state["response"] = result.response
    return state


async def execute_query_agent(state: SupervisorState) -> SupervisorState:
    """执行 Query Agent。"""
    agent = registry.get_agent("query_agent")
    context = AgentContext(
        user_message=state["user_message"],
        parsed_intent=state["parsed"],
        device_serial=state["parsed"].get("device_serial"),
        agent_id=state.get("agent_id", ""),
    )
    result = await agent.execute(context)
    state["response"] = result.response
    return state


async def execute_schedule_agent(state: SupervisorState) -> SupervisorState:
    """执行 Schedule Agent。"""
    agent = registry.get_agent("schedule_agent")
    context = AgentContext(
        user_message=state["user_message"],
        parsed_intent=state["parsed"],
        device_serial=state["parsed"].get("device_serial"),
        agent_id=state.get("agent_id", ""),
    )
    result = await agent.execute(context)
    state["response"] = result.response
    return state


def handle_chat(state: SupervisorState) -> SupervisorState:
    """处理普通对话。"""
    from server.langgraph.utils import call_llm

    message = state["user_message"]
    prompt = f"你是一个移动设备管理助手。用户说：{message}\n请友好地回复，告诉用户你可以帮他们控制手机设备。"

    try:
        state["response"] = call_llm(prompt)
    except Exception:
        state["response"] = "你好！我可以帮你控制 Android 设备。请告诉我你想执行什么操作。"

    return state


def _build_graph(checkpointer=None):
    """构建 Supervisor LangGraph。"""
    g = StateGraph(SupervisorState)

    # 添加节点
    g.add_node("parse", parse_intent)
    g.add_node("resolve_device", resolve_device)
    g.add_node("select_agent", select_agent)
    g.add_node("device_agent", execute_device_agent)
    g.add_node("chat_bot_agent", execute_chat_bot_agent)
    g.add_node("query_agent", execute_query_agent)
    g.add_node("schedule_agent", execute_schedule_agent)
    g.add_node("chat", handle_chat)

    # 固定边
    g.add_edge("parse", "resolve_device")
    g.add_edge("resolve_device", "select_agent")

    # Supervisor 路由
    g.add_conditional_edges(
        "select_agent",
        route_to_agent,
        {
            "device_agent": "device_agent",
            "chat_bot_agent": "chat_bot_agent",
            "query_agent": "query_agent",
            "schedule_agent": "schedule_agent",
            "chat": "chat",
        },
    )

    # 所有 Agent 执行完后结束
    g.add_edge("device_agent", END)
    g.add_edge("chat_bot_agent", END)
    g.add_edge("query_agent", END)
    g.add_edge("schedule_agent", END)
    g.add_edge("chat", END)

    g.set_entry_point("parse")

    return g.compile(checkpointer=checkpointer)


# 全局图实例（不使用 checkpointer，对话历史通过 storage.append_message 管理）
graph = _build_graph()
logger.info(f"已注册 Agent: {registry.agent_names}")
logger.info(f"已注册 Agent: {registry.agent_names}")


async def process_message(message: str, agent_id: str = "default") -> dict:
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
            "task_result": dict | None,
        }
    """
    config = {"configurable": {"thread_id": agent_id}}
    result = await graph.ainvoke(
        {
            "user_message": message,
            "parsed": {},
            "selected_agent": "",
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
