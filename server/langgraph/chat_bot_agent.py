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
    READ_CHAT_PROMPT,
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


def get_device_user(device_id: str) -> str:
    """获取设备用户名称，默认为设备号。

    Args:
        device_id: 设备序列号

    Returns:
        设备用户名称
    """
    return DEVICE_USER_MAP.get(device_id, device_id)


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

    kwargs = {
        "device_serial": device_id,
        "vision_only": True,
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

    kwargs = {
        "device_serial": device_id,
        "vision_only": True,
        "max_steps": 15,
    }
    if log_handler:
        kwargs["log_handler"] = log_handler

    return await run_async(goal, **kwargs)


async def read_chat_messages(device_id: str, source: str, log_handler=None) -> list[dict]:
    """读取当前聊天窗口的消息列表。

    根据 App 配置的 read_mode 选择读取方式：
    - screenshot: 纯截图 + OCR（微信等屏蔽无障碍的 App）
    - accessibility: 无障碍服务读取 UI 树（WhatsApp 等，更高效）

    Args:
        device_id: 设备序列号
        source: 数据源标识
        log_handler: 日志处理器（可选）

    Returns:
        消息列表
    """
    from mobilerun_api import run_async

    device_user = get_device_user(device_id)
    read_mode = get_read_mode(source)

    goal = READ_CHAT_PROMPT.format(device_user=device_user)

    kwargs = {
        "device_serial": device_id,
        "max_steps": 5,
    }
    if log_handler:
        kwargs["log_handler"] = log_handler

    if read_mode == READ_MODE_ACCESSIBILITY:
        # 无障碍模式：使用 UI 树，不需要 vision_only
        logger.info(f"使用无障碍模式读取聊天记录: {device_id}")
        kwargs["vision_only"] = False
        result = await run_async(goal, **kwargs)
    else:
        # 截图模式：使用 vision_only + OCR
        logger.info(f"使用截图模式读取聊天记录: {device_id}")
        kwargs["vision_only"] = True
        result = await run_async(goal, **kwargs)

    return parse_chat_messages(result)


async def detect_chat_type(device_id: str, log_handler=None) -> tuple[str, str]:
    """检测当前聊天窗口是单聊还是群聊。

    Args:
        device_id: 设备序列号
        log_handler: 日志处理器（可选）

    Returns:
        (chat_type, chat_name) - "single"/"group" 和 聊天名称
    """
    from mobilerun_api import run_async

    kwargs = {
        "device_serial": device_id,
        "vision_only": True,
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


async def send_reply(device_id: str, reply: str, log_handler=None) -> dict:
    """在设备上发送回复消息。

    Args:
        device_id: 设备序列号
        reply: 回复内容
        log_handler: 日志处理器（可选）

    Returns:
        run_async 结果
    """
    from mobilerun_api import run_async

    goal = SEND_REPLY_PROMPT.format(reply=reply)
    logger.info(f"发送回复: {reply[:50]}...")

    kwargs = {
        "device_serial": device_id,
        "vision_only": True,
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
) -> dict:
    """执行完整的聊天 Bot 任务流程。

    流程：
    1. 打开聊天软件
    2. 进入指定聊天窗口（如果指定了 target_chat）
    3. 检测聊天类型（单聊/群聊）
    4. 读取当前聊天记录
    5. 存入数据库
    6. 查询历史 100 条
    7. 生成回复
    8. 发送回复

    Args:
        device_id: 设备序列号
        source: 数据源标识
        app_name: App 名称
        target_chat: 目标聊天对象（可选）
        agent_id: Agent ID（可选）
        task_id: 任务 ID（可选）
        log_handler: 日志处理器（可选，用于将日志推送到 WebSocket 和文件）

    Returns:
        任务执行结果
    """
    from server.storage import storage

    device_user = get_device_user(device_id)
    read_mode = get_read_mode(source)

    logger.info(f"=== 聊天 Bot 任务开始 ===")
    logger.info(f"设备: {device_id}, 用户: {device_user}")
    logger.info(f"App: {app_name}, Source: {source}, Read Mode: {read_mode}")

    result = {
        "success": False,
        "device_id": device_id,
        "source": source,
        "app_name": app_name,
        "target_chat": target_chat,
        "messages_read": 0,
        "reply_sent": False,
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
        chat_type, detected_chat_name = await detect_chat_type(device_id, log_handler=log_handler)
        chat_name = target_chat or detected_chat_name
        # 去除 chat_name 中可能带有的引号（中文引号、英文引号等）
        for ch in ['\u201c', '\u201d', '\u2018', '\u2019', '"', "'", '「', '」', '『', '』']:
            chat_name = chat_name.replace(ch, '')
        chat_name = chat_name.strip()
        logger.info(f"聊天类型: {chat_type}, 名称: {chat_name}")

        # 4. 读取当前聊天记录
        logger.info("步骤 4: 读取聊天记录")
        messages = await read_chat_messages(device_id, source, log_handler=log_handler)
        result["messages_read"] = len(messages)
        logger.info(f"读取到 {len(messages)} 条消息")

        if not messages:
            result["error"] = "未能读取到聊天记录"
            logger.warning(result["error"])
            return result

        # 5. 存入数据库
        logger.info("步骤 5: 存入数据库")
        now = datetime.now().isoformat()
        records = []
        for msg in messages:
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
                "created_at": msg.get("time") or now,
            })

        saved_ids = storage.save_chat_records(records)
        logger.info(f"保存了 {len(saved_ids)} 条记录")

        # 6. 查询历史 100 条
        logger.info("步骤 6: 查询历史消息")
        history = storage.get_chat_history(
            chat_name=chat_name,
            source=source,
            device_id=device_id,
            limit=100,
        )
        logger.info(f"历史记录: {len(history)} 条")

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
            logger.info("不需要回复，任务完成")
            result["success"] = True
            return result

        # 8. 发送回复
        logger.info("步骤 8: 发送回复")
        send_result = await send_reply(device_id, reply, log_handler=log_handler)

        if send_result.get("success"):
            result["success"] = True
            result["reply_sent"] = True

            # 保存自己发送的回复到数据库
            storage.save_chat_record({
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

            logger.info("回复发送成功")
        else:
            result["error"] = f"发送回复失败: {send_result.get('reason', '')}"
            logger.error(result["error"])

    except Exception as e:
        result["error"] = str(e)
        logger.exception(f"聊天 Bot 任务异常: {e}")

    logger.info(f"=== 聊天 Bot 任务结束: success={result['success']} ===")
    return result
