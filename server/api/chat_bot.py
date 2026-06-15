"""聊天 Bot API 路由。"""

import asyncio
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from server.models import ChatBotRequest, Task
from server.state import state
from server.storage import storage

logger = logging.getLogger("mobilerun.server.chat_bot")
router = APIRouter(prefix="/chat-bot", tags=["chat-bot"])


@router.post("/reply")
async def trigger_chat_bot_reply(req: ChatBotRequest):
    """触发聊天 Bot 回复任务。

    流程：
    1. 根据 source 获取 App 名称
    2. 查找或指定设备
    3. 创建任务记录
    4. 异步执行 chat_bot_agent
    """
    from server.langgraph.chat_bot_agent import execute_chat_bot_task
    from server.langgraph.chat_bot_config import CHAT_APP_REGISTRY

    # 根据 source 查找 App 名称
    app_name = None
    for name, config in CHAT_APP_REGISTRY.items():
        if config["source"] == req.source:
            app_name = name
            break

    if not app_name:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的聊天源: {req.source}，支持的源: {[c['source'] for c in CHAT_APP_REGISTRY.values()]}",
        )

    # 查找设备
    device_id = req.device_id
    if not device_id:
        # 自动查找空闲设备
        for d in state.list_devices():
            if d.state in ("online", "busy"):
                device_id = d.serial
                break

    if not device_id:
        raise HTTPException(status_code=400, detail="当前没有可用的设备")

    # 查找 Agent
    agent_id = None
    for a in state.list_agents():
        if a.device_serial == device_id and a.status == "idle":
            agent_id = a.id
            break
    if not agent_id:
        for a in state.list_agents():
            if a.status == "idle":
                agent_id = a.id
                break
    if not agent_id:
        from server.api.agents import ensure_default_agent
        agent = ensure_default_agent()
        agent_id = agent.id

    # 创建任务记录
    task_id = str(uuid.uuid4())[:8]
    goal = f"自动回复{app_name}消息"
    if req.target_chat:
        goal += f"（{req.target_chat}）"

    task = Task(
        id=task_id,
        agent_id=agent_id,
        device_serial=device_id,
        goal=goal,
        status="running",
        type="chat_bot",
        started_at=datetime.now(),
    )
    state.create_task(task)
    state.set_device_busy(device_id, task_id)
    state.update_agent(agent_id, status="working", current_task=task_id)

    # 创建日志处理器
    from server.websocket.log_handler import WebSocketLogHandler
    ws_handler = WebSocketLogHandler(task_id)
    ws_handler.set_loop(asyncio.get_running_loop())

    # 异步执行 chat_bot 任务
    async def _run_chat_bot():
        try:
            result = await execute_chat_bot_task(
                device_id=device_id,
                source=req.source,
                app_name=app_name,
                target_chat=req.target_chat,
                agent_id=agent_id,
                task_id=task_id,
                log_handler=ws_handler,
            )
            # 更新任务状态
            t = state.get_task(task_id)
            if t:
                t.status = "completed" if result.get("success") else "failed"
                t.result = result
                t.finished_at = datetime.now()
        except Exception as e:
            logger.exception(f"Chat bot task failed: {e}")
            t = state.get_task(task_id)
            if t:
                t.status = "failed"
                t.result = {"error": str(e)}
                t.finished_at = datetime.now()
        finally:
            state.set_device_busy(device_id, None)
            state.update_agent(agent_id, status="idle", current_task=None)

    asyncio.create_task(_run_chat_bot())

    return {
        "task_id": task_id,
        "device_id": device_id,
        "agent_id": agent_id,
        "source": req.source,
        "app_name": app_name,
        "target_chat": req.target_chat,
        "status": "running",
    }


@router.get("/records")
async def get_chat_records(
    source: str = Query(None, description="数据源 (wechat/whatsapp)"),
    chat_name: str = Query(None, description="聊天名称（群名或联系人名）"),
    device_id: str = Query(None, description="设备序列号"),
    limit: int = Query(100, ge=1, le=500, description="返回数量"),
):
    """获取聊天记录。

    支持按 source、chat_name、device_id 筛选。
    """
    if chat_name and source:
        records = storage.get_chat_history(
            chat_name=chat_name,
            source=source,
            device_id=device_id,
            limit=limit,
        )
    else:
        # 没有指定 chat_name，获取最近的记录
        records = storage.get_chat_history(
            chat_name=None,
            source=source,
            device_id=device_id,
            limit=limit,
        )

    return {
        "items": records,
        "total": len(records),
    }


@router.get("/chats")
async def get_chat_list(
    source: str = Query(None, description="数据源 (wechat/whatsapp)"),
    device_id: str = Query(None, description="设备序列号"),
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
):
    """获取聊天列表（按聊天名称分组）。

    返回最近的聊天列表，包含每个聊天的最后一条消息和时间。
    """
    chats = storage.get_recent_chats(
        source=source,
        device_id=device_id,
        limit=limit,
    )

    # 为每个聊天补充统计信息
    result = []
    for chat in chats:
        count = storage.get_chat_record_count(
            chat_name=chat.get("chat_name"),
            source=source,
            device_id=device_id,
        )
        result.append({
            **chat,
            "message_count": count,
        })

    return {
        "items": result,
        "total": len(result),
    }


@router.get("/stats")
async def get_chat_stats(
    source: str = Query(None),
    device_id: str = Query(None),
):
    """获取聊天记录统计信息。"""
    total = storage.get_chat_record_count(
        source=source,
        device_id=device_id,
    )
    return {
        "total_records": total,
        "source": source,
        "device_id": device_id,
    }
