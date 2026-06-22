"""聊天 Bot Agent — 专门处理微信/WhatsApp 等聊天软件的自动回复任务。"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Optional

from server.langgraph.chat_bot_config import (
    READ_MODE_ACCESSIBILITY,
    READ_MODE_SCREENSHOT,
    get_package_name,
    get_read_mode,
)
from server.langgraph.chat_bot_prompts import (
    CHAT_BOT_SYSTEM_PROMPT,
    DETECT_CHAT_TYPE_PROMPT,
    ENTER_CHAT_PROMPT,
    OPEN_APP_PROMPT,
    READ_CHAT_FULL_EXTRA,
    READ_CHAT_PROMPT,
    READ_CHAT_QUICK_EXTRA,
    SEND_REPLY_PROMPT,
)
from server.langgraph.utils import call_llm

logger = logging.getLogger("mobilerun.server.chat_bot")

# ── 设备用户名称映射 ──
# 可在代码中修改，为每个设备指定回复时使用的名字
# key: device_id (设备序列号)
# value: device_user (该设备回复时使用的名字)
DEVICE_USER_MAP: dict[str, str] = {
    # 示例：
    # "2MM0223A26010594": "小bot-01",
    # "AK3SBB5530100840": "小bot-02",
}

# 翻译缓存：避免监控模式下对相同内容重复调用 LLM
_translation_cache: dict[str, str] = {}


def _is_accessibility_mode(source: str) -> bool:
    """判断指定 source 是否使用无障碍/UI 树模式。

    WhatsApp 等支持无障碍的 App 使用 UI 树模式（vision_only=False），
    微信等屏蔽无障碍的 App 使用截图模式（vision_only=True）。

    Args:
        source: 数据源标识

    Returns:
        True 表示使用 UI 树模式，False 表示截图模式
    """
    return get_read_mode(source) == READ_MODE_ACCESSIBILITY


def _has_unreplied_messages(history: list[dict]) -> bool:
    """检查历史消息中是否有未回复的消息。

    不依赖时间排序（避免时间格式不一致导致的问题）。
    逻辑：找到最新的一条非自己消息，检查是否有任何自己消息的
    内容出现在它之后（按列表顺序）。

    Args:
        history: 按时间排序的历史消息列表（最旧在前，最新在后）

    Returns:
        True 表示有未回复的消息
    """
    if not history:
        return False

    # 找到最后一条非自己消息的位置
    last_other_idx = -1
    for i in range(len(history) - 1, -1, -1):
        if not history[i].get("is_self", False):
            last_other_idx = i
            break

    if last_other_idx == -1:
        return False  # 没有他人消息

    # 检查这条消息之后是否有自己发的消息
    for i in range(last_other_idx + 1, len(history)):
        if history[i].get("is_self", False):
            return False  # 有自己消息在之后 → 已回复

    return True  # 最后的消息来自他人 → 需要回复


def _emit_log(msg: str, log_handler=None, color: str = None):
    """输出日志到 Python logger 和 WebSocket。

    Args:
        msg: 日志消息
        log_handler: WebSocket 日志处理器（可选）
        color: 日志颜色（可选）
    """
    logger.info(msg)
    if log_handler:
        import logging as _logging
        record = _logging.LogRecord(
            name="mobilerun.server.chat_bot",
            level=_logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        record.color = color
        log_handler.emit(record)


def _log_with_translation(text: str, sender: str = "", label: str = "消息", log_handler=None):
    """打印消息日志，非中文时附带中文翻译。

    使用 _translation_cache 避免重复调用 LLM（监控模式下同一内容只翻译一次）。
    日志同时输出到 Python logger 和 WebSocket log_handler（如果提供）。

    Args:
        text: 消息文本
        sender: 发送者名称
        label: 日志标签（如 "收到消息"、"生成回复"）
        log_handler: WebSocket 日志处理器（可选）
    """
    from server.rag.language_detector import detect_language

    lang = detect_language(text)

    if lang == "zh":
        _emit_log(f"[{label}] {sender}: {text}", log_handler=log_handler)
    else:
        # 非中文 → 打印原文 + 翻译（使用缓存避免重复 LLM 调用）
        _emit_log(f"[{label}] {sender} ({lang}): {text}", log_handler=log_handler)
        if text in _translation_cache:
            translation = _translation_cache[text]
        else:
            try:
                translation = call_llm(
                    f"将以下内容翻译成中文，只返回翻译结果，不要任何解释：\n{text}",
                    max_tokens=256,
                )
                _translation_cache[text] = translation
            except Exception as e:
                logger.warning(f"翻译失败: {e}")
                translation = None
        if translation:
            _emit_log(f"[翻译] {sender}: {translation}", log_handler=log_handler, color="cyan")


def get_device_user(device_id: str) -> str:
    """获取设备用户名称，默认为设备号。

    Args:
        device_id: 设备序列号

    Returns:
        设备用户名称
    """
    return DEVICE_USER_MAP.get(device_id, device_id)


def _normalize_time(time_str: str) -> str:
    """将屏幕读取的时间字符串规范化为 ISO 格式。

    屏幕读取的时间可能是 "HH:MM"、"HH:MM:SS" 或已经是 ISO 格式。
    如果是短时间格式，用今天的日期补全。

    Args:
        time_str: 时间字符串

    Returns:
        ISO 格式时间字符串
    """
    if not time_str:
        return datetime.now().isoformat()

    # 已经是 ISO 格式（包含日期部分）
    if "T" in time_str or "-" in time_str:
        return time_str

    # 短时间格式 "HH:MM" 或 "HH:MM:SS" → 补全今天日期
    import re
    if re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', time_str):
        today = datetime.now().strftime("%Y-%m-%d")
        # 如果只有 HH:MM，补 :00
        if time_str.count(":") == 1:
            time_str += ":00"
        return f"{today}T{time_str}"

    # 无法识别，返回原值
    return time_str


def parse_chat_messages(result: dict) -> list[dict]:
    """解析 LLM 返回的聊天记录。

    从 run_async 的返回结果中提取 JSON 数组。

    Args:
        result: run_async 返回的结果字典

    Returns:
        消息列表 [{"sender": "xxx", "content": "xxx", "time": "xxx", "is_self": bool}]
    """
    if not result or not result.get("success"):
        logger.warning(f"读取聊天记录失败: {result}")
        return []

    reason = result.get("reason", "")

    # 尝试从 reason 中提取 JSON 数组
    # 匹配 [...] 格式
    json_match = re.search(r'\[[\s\S]*\]', reason)
    if json_match:
        try:
            messages = json.loads(json_match.group())
            if isinstance(messages, list):
                # 标准化字段
                normalized = []
                for msg in messages:
                    normalized.append({
                        "sender": msg.get("sender", "unknown"),
                        "content": msg.get("content", ""),
                        "time": msg.get("time", ""),
                        "is_self": bool(msg.get("is_self", False)),
                    })
                return normalized
        except json.JSONDecodeError as e:
            logger.warning(f"解析聊天记录 JSON 失败: {e}")

    logger.warning(f"未能从结果中解析出聊天记录: {reason[:200]}")
    return []


async def open_chat_app(device_id: str, source: str, log_handler=None) -> dict:
    """打开聊天软件。

    Args:
        device_id: 设备序列号
        source: 数据源标识 (wechat/whatsapp)
        log_handler: 日志处理器（可选）

    Returns:
        run_async 结果
    """
    from mobilerun_api import run_async

    # 根据 source 获取 App 名称
    app_name_map = {
        "wechat": "微信",
        "whatsapp": "WhatsApp",
    }
    app_name = app_name_map.get(source, source)

    goal = OPEN_APP_PROMPT.format(app_name=app_name)
    logger.info(f"打开聊天软件: {app_name} on {device_id}")

    vision_only = not _is_accessibility_mode(source)

    kwargs = {
        "device_serial": device_id,
        "vision_only": vision_only,
        "max_steps": 10,
    }
    if log_handler:
        kwargs["log_handler"] = log_handler

    return await run_async(goal, **kwargs)


async def enter_chat_window(device_id: str, source: str, target_chat: str, log_handler=None) -> dict:
    """进入指定聊天窗口。

    Args:
        device_id: 设备序列号
        source: 数据源标识
        target_chat: 目标聊天对象（群名或联系人名）
        log_handler: 日志处理器（可选）

    Returns:
        run_async 结果
    """
    from mobilerun_api import run_async

    app_name_map = {
        "wechat": "微信",
        "whatsapp": "WhatsApp",
    }
    app_name = app_name_map.get(source, source)

    goal = ENTER_CHAT_PROMPT.format(app_name=app_name, target_chat=target_chat)
    logger.info(f"进入聊天窗口: {target_chat} in {app_name}")

    vision_only = not _is_accessibility_mode(source)

    kwargs = {
        "device_serial": device_id,
        "vision_only": vision_only,
        "max_steps": 15,
    }
    if log_handler:
        kwargs["log_handler"] = log_handler

    return await run_async(goal, **kwargs)


async def read_chat_messages(
    device_id: str, source: str, log_handler=None, quick_read: bool = False,
) -> list[dict]:
    """读取当前聊天窗口的消息列表。

    根据 App 配置的 read_mode 选择读取方式：
    - screenshot: 纯截图 + OCR（微信等屏蔽无障碍的 App）
    - accessibility: 无障碍服务读取 UI 树（WhatsApp 等，更高效）

    Args:
        device_id: 设备序列号
        source: 数据源标识
        log_handler: 日志处理器（可选）
        quick_read: True=只读当前可见消息（不滚动），False=完整读取（含滚动）

    Returns:
        消息列表
    """
    from mobilerun_api import run_async

    device_user = get_device_user(device_id)
    read_mode = get_read_mode(source)
    vision_only = not _is_accessibility_mode(source)

    # 根据读取模式选择不同的提示词附加指令和步数
    extra = READ_CHAT_QUICK_EXTRA if quick_read else READ_CHAT_FULL_EXTRA
    goal = READ_CHAT_PROMPT.format(
        device_user=device_user, extra_instructions=extra,
    )

    # 快速读取时减少步数（不需要滚动），完整读取时需要更多步数
    max_steps = 5 if quick_read else 10

    kwargs = {
        "device_serial": device_id,
        "vision_only": vision_only,
        "max_steps": max_steps,
    }
    if log_handler:
        kwargs["log_handler"] = log_handler

    if quick_read:
        logger.info(f"快速读取聊天记录（仅可见消息）: {device_id}")
    elif read_mode == READ_MODE_ACCESSIBILITY:
        logger.info(f"使用无障碍模式完整读取聊天记录: {device_id}")
    else:
        logger.info(f"使用截图模式完整读取聊天记录: {device_id}")

    result = await run_async(goal, **kwargs)
    return parse_chat_messages(result)


async def detect_chat_type(device_id: str, source: str, log_handler=None) -> tuple[str, str]:
    """检测当前聊天窗口是单聊还是群聊。

    Args:
        device_id: 设备序列号
        source: 数据源标识（用于决定 UI 树 vs 截图模式）
        log_handler: 日志处理器（可选）

    Returns:
        (chat_type, chat_name) - "single"/"group" 和 聊天名称
    """
    from mobilerun_api import run_async

    vision_only = not _is_accessibility_mode(source)
    logger.info(f"检测聊天类型 (vision_only={vision_only}, source={source})")

    kwargs = {
        "device_serial": device_id,
        "vision_only": vision_only,
        "max_steps": 3,
    }
    if log_handler:
        kwargs["log_handler"] = log_handler

    result = await run_async(DETECT_CHAT_TYPE_PROMPT, **kwargs)

    if not result or not result.get("success"):
        return "single", "unknown"

    reason = result.get("reason", "")

    # 尝试解析 JSON
    json_match = re.search(r'\{[\s\S]*\}', reason)
    if json_match:
        try:
            data = json.loads(json_match.group())
            chat_type = data.get("chat_type", "single")
            chat_name = data.get("chat_name", "unknown")
            # 去除引号
            for ch in ['\u201c', '\u201d', '\u2018', '\u2019', '"', "'", '「', '」', '『', '』']:
                chat_name = chat_name.replace(ch, '')
            chat_name = chat_name.strip()
            return chat_type, chat_name
        except json.JSONDecodeError:
            pass

    return "single", "unknown"


async def generate_reply(
    device_id: str,
    chat_name: str,
    source: str,
    chat_type: str,
    history: list[dict],
) -> Optional[str]:
    """根据聊天历史生成回复。

    流程：
    1. 获取最后一条非自己的消息
    2. 如果消息与政策相关，且群组启用了 RAG，则优先使用 RAG 回答
    3. 否则使用普通 LLM 生成回复

    Args:
        device_id: 设备序列号
        chat_name: 聊天名称
        source: 数据源标识
        chat_type: 聊天类型 (single/group)
        history: 历史消息列表

    Returns:
        回复内容，如果不需要回复则返回 None
    """
    if not history:
        logger.info("没有历史消息，跳过回复")
        return None

    device_user = get_device_user(device_id)

    # 找到最后一条非自己的消息（需要回复的目标）
    last_other_msg = None
    for msg in reversed(history):
        is_self = msg.get("is_self", False)
        if not is_self:
            last_other_msg = msg
            break

    if not last_other_msg:
        logger.info("最后的消息都是自己发的，跳过回复")
        return None

    last_message = last_other_msg.get("content", "")

    # ── RAG 集成：优先使用政策文档回答 ──
    rag_reply = await _try_rag_reply(
        message=last_message,
        chat_name=chat_name,
        source=source,
        chat_type=chat_type,
    )
    if rag_reply is not None:
        return rag_reply

    # ── 普通 LLM 回复（非政策相关或 RAG 未启用/无结果）──
    # 构建历史消息文本
    history_text = []
    for msg in history[-100:]:  # 最多取 100 条
        # 兼容两种字段名：DB 返回 nick_name/created_at，
        # parse_chat_messages 返回 sender/time
        sender = msg.get("nick_name") or msg.get("sender", "unknown")
        content = msg.get("content", "")
        is_self = msg.get("is_self", False)
        time_str = msg.get("created_at") or msg.get("time", "")

        # 时间格式化：只取时分部分（如果太长）
        if time_str and "T" in str(time_str):
            try:
                time_str = str(time_str)[11:16]  # 提取 HH:MM
            except Exception:
                pass

        prefix = f"[{sender}]" if not is_self else f"[{device_user}]"
        if time_str:
            prefix += f" ({time_str})"
        history_text.append(f"{prefix}: {content}")

    context = "\n".join(history_text)

    # 区分单聊/群聊描述
    chat_desc = f"与「{chat_name}」的私聊" if chat_type == "single" else f"群「{chat_name}」的群聊"
    source_name = {"wechat": "微信", "whatsapp": "WhatsApp"}.get(source, source)

    # 构建完整 prompt
    system_prompt = CHAT_BOT_SYSTEM_PROMPT.format(device_user=device_user)
    user_prompt = f"""以下是你在{source_name}上{chat_desc}的最近 {len(history_text)} 条聊天记录：

{context}

请根据以上聊天记录，理解上下文语境，针对最后一条消息生成合适的回复。
注意：
- 你的身份是 {device_user}
- 如果最后一条消息不需要回复（如表情、简短回应、已结束的对话），请返回 [NO_REPLY]
- 避免重复你已经回复过的内容"""

    full_prompt = f"{system_prompt}\n\n{user_prompt}\n\n回复："

    try:
        reply = call_llm(full_prompt, max_tokens=256)
        reply = reply.strip()

        # 检查是否不需要回复
        if "[NO_REPLY]" in reply:
            logger.info("LLM 判断不需要回复")
            return None

        # 清理回复内容
        reply = reply.strip('"').strip("'")
        if not reply:
            return None

        logger.info(f"生成回复: {reply[:50]}...")
        return reply

    except Exception as e:
        logger.error(f"生成回复失败: {e}")
        return None


async def _try_rag_reply(
    message: str,
    chat_name: str,
    source: str,
    chat_type: str,
) -> Optional[str]:
    """尝试使用 RAG 回答政策相关问题。

    如果消息包含政策关键词，且群组启用了 RAG，则使用 RAG 引擎回答。

    Args:
        message: 用户消息
        chat_name: 聊天名称
        source: 数据源标识
        chat_type: 聊天类型 (single/group)

    Returns:
        RAG 回答，如果不满足条件或回答失败则返回 None
    """
    from server.db import db
    from server.rag.agent import is_policy_related

    logger.info(f"_try_rag_reply: message={message[:60]}..., chat_type={chat_type}")

    # 1. 检查消息是否与政策相关
    if not is_policy_related(message):
        logger.info(f"_try_rag_reply: 消息与政策无关，跳过 RAG")
        return None

    logger.info(f"检测到政策相关问题: {message[:50]}...")

    # 2. 查询群组配置（群聊才检查，私聊直接用 RAG）
    group_config = None
    rag_enabled = True  # 默认启用

    if chat_type == "group":
        group_config = db.get_chat_group(chat_name, source)
        if group_config:
            rag_enabled = group_config.get("rag_enabled", True)
            logger.info(
                f"群组配置: {chat_name}, RAG 启用={rag_enabled}, "
                f"默认语言={group_config.get('default_language', 'auto')}"
            )
        else:
            logger.info(f"群组 {chat_name} 未配置，使用默认设置")

    if not rag_enabled:
        logger.info(f"群组 {chat_name} 未启用 RAG，跳过")
        return None

    # 3. 获取群组默认语言（如果已配置）
    default_language = None
    if group_config:
        default_language = group_config.get("default_language")

    # 4. 调用 RAG 引擎
    try:
        from server.rag.chat_engine import RagChatEngine

        result = await RagChatEngine.chat(
            question=message,
            session_id=chat_name,
            source=source,
            language=default_language,
            include_translation=True,
        )

        answer = result.get("answer", "")

        # 如果 RAG 没有找到相关信息，返回 None 让普通 LLM 处理
        # 检查语言无关的 [NO_INFO] 标记 + 多语言的"未找到"模式
        no_info_markers = [
            "[NO_INFO]",
            "没有找到相关信息", "没有找到相关", "没有相关信息",
            "não encontrei", "não há informação", "sem informação",
            "no relevant information", "no information found",
            "no se encontró", "sin información",
        ]
        answer_lower = answer.lower().strip() if answer else ""
        is_no_info = not answer or any(marker in answer_lower for marker in no_info_markers)

        if is_no_info:
            logger.info(f"RAG 未找到相关信息（answer={answer[:60] if answer else 'empty'}），回退到普通 LLM")
            return None

        # 翻译只记录到日志，不附加到回复中（回复保持原语言发给对方）
        translation = result.get("translation", "")
        if translation:
            logger.info(f"RAG 回答中文翻译: {translation[:80]}...")

        # 日志打印引用来源
        source_docs = result.get("source_docs", [])
        if source_docs:
            logger.info(f"RAG 引用来源：{len(source_docs)} 个文档片段")
            for doc in source_docs[:3]:
                logger.info(
                    f"  - {doc.get('filename')}: "
                    f"{doc.get('chunk_text', '')[:100]}..."
                )

        logger.info(f"使用 RAG 回答政策问题: {answer[:80]}...")
        return answer

    except Exception as e:
        logger.error(f"RAG 回答失败：{e}，回退到普通 LLM")
        return None


async def send_reply(device_id: str, reply: str, source: str = "", log_handler=None) -> dict:
    """在设备上发送回复消息。

    Args:
        device_id: 设备序列号
        reply: 回复内容
        source: 数据源标识（用于决定 UI 树 vs 截图模式）
        log_handler: 日志处理器（可选）

    Returns:
        run_async 结果
    """
    from mobilerun_api import run_async

    vision_only = not _is_accessibility_mode(source) if source else True
    logger.info(f"发送回复 (vision_only={vision_only}, source={source}): {reply[:50]}...")

    goal = SEND_REPLY_PROMPT.format(reply=reply)

    kwargs = {
        "device_serial": device_id,
        "vision_only": vision_only,
        "max_steps": 10,
    }
    if log_handler:
        kwargs["log_handler"] = log_handler

    return await run_async(goal, **kwargs)


async def execute_chat_bot_task(
    device_id: str,
    source: str,
    app_name: str,
    target_chat: Optional[str] = None,
    agent_id: Optional[str] = None,
    task_id: Optional[str] = None,
    log_handler=None,
    monitor: bool = False,
    monitor_interval: int = 30,
) -> dict:
    """执行完整的聊天 Bot 任务流程。

    流程：
    1. 打开聊天软件
    2. 进入指定聊天窗口（如果指定了 target_chat）
    3. 检测聊天类型（单聊/群聊）
    4. 读取当前聊天记录
    5. 存入数据库
    6. 查询历史 100 条
    6.5 检查是否有未回复的消息（去重）
    7. 生成回复
    8. 发送回复

    监控模式（monitor=True）：
    - 步骤 1-3 只执行一次
    - 步骤 4-8 循环执行，每次间隔 monitor_interval 秒
    - 支持通过 cancel_event 取消

    Args:
        device_id: 设备序列号
        source: 数据源标识
        app_name: App 名称
        target_chat: 目标聊天对象（可选）
        agent_id: Agent ID（可选）
        task_id: 任务 ID（可选）
        log_handler: 日志处理器（可选，用于将日志推送到 WebSocket 和文件）
        monitor: 是否启用监控模式（持续监听新消息）
        monitor_interval: 监控间隔秒数（默认 30）

    Returns:
        任务执行结果
    """
    from server.storage import storage

    device_user = get_device_user(device_id)
    read_mode = get_read_mode(source)

    logger.info(f"=== 聊天 Bot 任务开始 ===")
    logger.info(f"设备: {device_id}, 用户: {device_user}")
    logger.info(f"App: {app_name}, Source: {source}, Read Mode: {read_mode}")
    if monitor:
        logger.info(f"监控模式: 启用, 间隔: {monitor_interval} 秒")

    result = {
        "success": False,
        "device_id": device_id,
        "source": source,
        "app_name": app_name,
        "target_chat": target_chat,
        "messages_read": 0,
        "reply_sent": False,
        "monitor": monitor,
        "monitor_loops": 0,
        "error": None,
    }

    try:
        # 1. 打开聊天软件
        logger.info("步骤 1: 打开聊天软件")
        open_result = await open_chat_app(device_id, source, log_handler=log_handler)
        if not open_result.get("success"):
            result["error"] = f"打开 {app_name} 失败: {open_result.get('reason', '')}"
            logger.error(result["error"])
            return result

        # 等待应用完全加载
        await asyncio.sleep(2)

        # 2. 进入指定聊天窗口
        if target_chat:
            logger.info(f"步骤 2: 进入聊天窗口 - {target_chat}")
            enter_result = await enter_chat_window(device_id, source, target_chat, log_handler=log_handler)
            if not enter_result.get("success"):
                result["error"] = f"进入 {target_chat} 失败: {enter_result.get('reason', '')}"
                logger.error(result["error"])
                return result
            await asyncio.sleep(1)
        else:
            logger.info("步骤 2: 跳过（未指定聊天对象，使用当前窗口）")

        # 3. 检测聊天类型
        logger.info("步骤 3: 检测聊天类型")
        chat_type, detected_chat_name = await detect_chat_type(device_id, source, log_handler=log_handler)
        chat_name = target_chat or detected_chat_name
        # 去除 chat_name 中可能带有的引号（中文引号、英文引号等）
        for ch in ['\u201c', '\u201d', '\u2018', '\u2019', '"', "'", '「', '」', '『', '』']:
            chat_name = chat_name.replace(ch, '')
        chat_name = chat_name.strip()
        logger.info(f"聊天类型: {chat_type}, 名称: {chat_name}")

        # ── 步骤 4-8: 读取 → 去重 → 回复（监控模式下循环执行）──
        loop_count = 0

        while True:
            loop_count += 1

            if monitor:
                # 监控模式：检查取消信号
                if task_id:
                    from server.state import state
                    cancel_event = state.get_cancel_event(task_id)
                    if cancel_event and cancel_event.is_set():
                        logger.info("监控任务被取消")
                        break
                logger.info(f"--- 监控循环 #{loop_count} ---")

            # 4. 读取当前聊天记录
            # 优化：先查 DB，如果已有历史记录则只快速读取可见消息（不滚动）
            logger.info("步骤 4: 读取聊天记录")
            existing_count = storage.get_chat_record_count(
                chat_name=chat_name, source=source, device_id=device_id,
            )
            quick_read = existing_count > 0
            if quick_read:
                _emit_log(
                    f"📋 DB 已有 {existing_count} 条记录，快速读取当前可见消息（不滚动）",
                    log_handler=log_handler, color="blue",
                )
            else:
                _emit_log(
                    "📋 DB 无历史记录，完整读取聊天历史（含滚动）",
                    log_handler=log_handler, color="blue",
                )

            messages = await read_chat_messages(
                device_id, source, log_handler=log_handler, quick_read=quick_read,
            )
            result["messages_read"] = len(messages)
            logger.info(f"读取到 {len(messages)} 条消息")

            if not messages:
                if monitor:
                    logger.warning("未能读取到聊天记录，等待下次重试")
                    await asyncio.sleep(monitor_interval)
                    continue
                result["error"] = "未能读取到聊天记录"
                logger.warning(result["error"])
                return result

            # 4.1 修正 is_self：WhatsApp UI 树可能将自己发的消息标记为来自聊天对象名
            # 始终查询 DB（不限于 quick_read），确保即使 DB 记录较少也能识别自己发的消息
            for msg in messages:
                sender = msg.get("sender", "")
                if sender == device_user:
                    msg["is_self"] = True

            # 用 DB 已有的 self 消息内容修正被误标的消息
            existing_history_for_fix = storage.get_chat_history(
                chat_name=chat_name, source=source, device_id=device_id, limit=200,
            )
            self_contents = {
                h.get("content") for h in existing_history_for_fix
                if h.get("is_self")
            }
            if self_contents:
                for msg in messages:
                    if not msg.get("is_self") and msg.get("content") in self_contents:
                        msg["is_self"] = True
                        logger.info(
                            f"修正 is_self: sender={msg.get('sender')} → True "
                            f"(content={msg.get('content', '')[:40]}...)"
                        )

            # 4.5 识别新消息：与 DB 已有记录对比，找出未记录的消息
            # 去重只比较 content（不比较 sender），防止旧消息被错误地重新保存
            if quick_read:
                # 获取 DB 已有的 content 集合，用于去重
                existing_history = storage.get_chat_history(
                    chat_name=chat_name, source=source, device_id=device_id,
                    limit=500,
                )
                existing_contents = {h.get("content") for h in existing_history}
                # 找出屏幕读取到的消息中内容不在 DB 里的（真正的新消息）
                new_messages = [
                    m for m in messages
                    if m.get("content") not in existing_contents
                ]
                if len(new_messages) < len(messages):
                    _emit_log(
                        f"  其中 {len(new_messages)} 条新消息，"
                        f"{len(messages) - len(new_messages)} 条已记录",
                        log_handler=log_handler, color="gray",
                    )
            else:
                new_messages = messages  # 首次读取，全部为新消息

            # 4.6 翻译日志：为新的他人消息（不在 DB 中的）打印中文翻译
            non_self_new = [m for m in new_messages if not m.get("is_self", False)]
            translate_msgs = non_self_new[-10:] if len(non_self_new) > 10 else non_self_new
            for msg in translate_msgs:
                content = msg.get("content", "")
                if content:
                    _log_with_translation(
                        content,
                        sender=msg.get("sender", ""),
                        label="收到消息",
                        log_handler=log_handler,
                    )

            # 5. 存入数据库（只保存新消息，save_chat_records 内置去重兜底）
            logger.info("步骤 5: 存入数据库")
            now = datetime.now().isoformat()
            records = []
            for msg in new_messages:
                records.append({
                    "source": source,
                    "chat_type": chat_type,
                    "chat_name": chat_name,
                    "nick_name": msg.get("sender"),
                    "avatar": None,
                    "content": msg.get("content", ""),
                    "is_self": msg.get("is_self", False),
                    "device_id": device_id,
                    "device_user": device_user,
                    "created_at": _normalize_time(msg.get("time", "")),
                })

            if records:
                try:
                    saved_ids = storage.save_chat_records(records)
                    logger.info(
                        f"保存了 {len(saved_ids)} 条新记录 "
                        f"(chat_name={chat_name}, device_id={device_id})"
                    )
                except Exception as e:
                    logger.error(f"批量保存聊天记录失败: {e}", exc_info=True)
            else:
                logger.info("没有新消息需要保存")

            # 5.5 基于屏幕消息的去重检查（确定性逻辑）
            # 规则：如果屏幕上的消息没有新的他人消息，则不需要回复
            screen_non_self = [m for m in messages if not m.get("is_self", False)]
            screen_new_non_self = [m for m in new_messages if not m.get("is_self", False)]

            logger.info(
                f"去重诊断: messages={len(messages)}, new_messages={len(new_messages)}, "
                f"screen_non_self={len(screen_non_self)}, screen_new_non_self={len(screen_new_non_self)}, "
                f"self_contents_in_db={len(self_contents)}"
            )

            if not screen_new_non_self:
                # 屏幕没有新的他人消息 → 不需要回复
                _emit_log(
                    "✅ 屏幕无新消息（他人），跳过回复",
                    log_handler=log_handler, color="green",
                )
                result["success"] = True
                result["reply_sent"] = False
                if monitor:
                    await asyncio.sleep(monitor_interval)
                    continue
                return result

            # 6. 查询历史 100 条（用于生成回复的上下文）
            logger.info("步骤 6: 查询历史消息")
            history = storage.get_chat_history(
                chat_name=chat_name,
                source=source,
                device_id=device_id,
                limit=100,
            )
            logger.info(f"历史记录: {len(history)} 条")

            # 6.5 去重检查：是否已有未回复的消息
            if not _has_unreplied_messages(history):
                _emit_log("✅ 所有消息已回复，无需重复回复", log_handler=log_handler, color="green")
                result["success"] = True
                result["reply_sent"] = False
                if monitor:
                    await asyncio.sleep(monitor_interval)
                    continue
                return result

            # 7. 生成回复
            logger.info("步骤 7: 生成回复")
            reply = await generate_reply(
                device_id=device_id,
                chat_name=chat_name,
                source=source,
                chat_type=chat_type,
                history=history,
            )

            if not reply:
                logger.info("不需要回复（LLM 判断无需回复）")
                result["success"] = True
                result["reply_sent"] = False
                if monitor:
                    await asyncio.sleep(monitor_interval)
                    continue
                return result

            # 翻译日志：回复内容
            _log_with_translation(reply, sender=device_user, label="生成回复", log_handler=log_handler)

            # 8. 发送回复
            logger.info("步骤 8: 发送回复")
            send_result = await send_reply(device_id, reply, source=source, log_handler=log_handler)

            if send_result.get("success"):
                result["success"] = True
                result["reply_sent"] = True

                # 保存自己发送的回复到数据库（用于后续去重识别自己的消息）
                try:
                    saved_id = storage.save_chat_record({
                        "source": source,
                        "chat_type": chat_type,
                        "chat_name": chat_name,
                        "nick_name": device_user,
                        "avatar": None,
                        "content": reply,
                        "is_self": True,
                        "device_id": device_id,
                        "device_user": device_user,
                        "created_at": datetime.now().isoformat(),
                    })
                    if saved_id == -1:
                        logger.warning(
                            f"回复已在 DB 中（去重跳过），content 前 60 字：{reply[:60]}"
                        )
                    else:
                        logger.info(
                            f"回复已保存到 DB (id={saved_id}, chat_name={chat_name}, device_id={device_id})"
                        )
                except Exception as e:
                    logger.error(f"保存回复到 DB 失败: {e}", exc_info=True)

                logger.info("回复发送成功")
            else:
                result["error"] = f"发送回复失败: {send_result.get('reason', '')}"
                logger.error(result["error"])

            # 监控模式：等待后继续循环
            if monitor:
                result["monitor_loops"] = loop_count
                logger.info(f"等待 {monitor_interval} 秒后重新检查...")
                await asyncio.sleep(monitor_interval)
            else:
                break

    except Exception as e:
        result["error"] = str(e)
        logger.exception(f"聊天 Bot 任务异常: {e}")

    logger.info(
        f"=== 聊天 Bot 任务结束: success={result['success']}, "
        f"reply_sent={result['reply_sent']}, "
        f"monitor_loops={result.get('monitor_loops', 0)} ==="
    )
    return result
