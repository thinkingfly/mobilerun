"""对话 API 路由 — 通过 LangGraph 处理用户消息。"""

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter

from server.langgraph.dialogue_agent import process_message
from server.langgraph.tools import execute_goal_async
from server.models import ChatRequest
from server.state import state
from server.storage import storage

logger = logging.getLogger("mobilerun.server")
router = APIRouter(prefix="/chat", tags=["chat"])


def _resolve_agent_id(agent_id: str | None, device_serial: str | None) -> str:
    """解析 Agent ID，优先使用指定的，否则找可用的。"""
    if agent_id:
        return agent_id

    if device_serial:
        for a in state.list_agents():
            if a.device_serial == device_serial and a.status == "idle":
                return a.id
    for a in state.list_agents():
        if a.status == "idle":
            return a.id
    from server.api.agents import ensure_default_agent
    return ensure_default_agent().id


@router.post("")
async def chat(req: ChatRequest):
    """发送对话消息，LangGraph 解析并返回结果。

    如果用户意图是操作设备且指定了设备，LangGraph 会调用 execute_goal 工具
    创建任务记录，然后此路由负责调度异步执行。

    参数:
        agent_id: 指定执行的 Agent，不指定则使用默认 Agent
    """
    # 1. 先确定 Agent ID（需要传给 process_message 作为 thread_id）
    # 注意：此时还不知道 device_serial，先解析意图获取
    from server.langgraph.dialogue_agent import graph as dialogue_graph

    # 先轻量解析意图来获取 device_serial（不执行图，只解析）
    # 实际上我们直接调用 process_message，agent_id 后续确定
    # 方案：先找 agent_id（不依赖 device_serial 的情况下），然后调用 process_message

    # 先确定 agent_id（不依赖 device_serial 的版本）
    agent_id = _resolve_agent_id(req.agent_id, None)

    # 2. 调用 LangGraph 处理消息（含 checkpointer 持久化）
    result = process_message(req.message, agent_id=agent_id)

    # 保存用户消息
    user_msg = {
        "role": "user",
        "content": req.message,
        "timestamp": datetime.now().isoformat(),
    }
    storage.append_message(agent_id, user_msg)

    # 3. 如果工具创建了任务，调度异步执行
    task_result = result.get("task_result")
    if task_result and task_result.get("task_id"):
        task_id = task_result["task_id"]
        goal = task_result["goal"]
        device_serial = task_result["device_serial"]
        task_agent_id = task_result["agent_id"]
        vision_only = task_result.get("vision_only", False)

        # 调度异步执行
        asyncio.create_task(
            execute_goal_async(task_id, goal, device_serial, task_agent_id,
                               vision_only=vision_only)
        )

        # 保存助手回复（使用 LangGraph 生成的 response）
        assistant_msg = {
            "role": "assistant",
            "content": result.get("response") or f"任务已创建并开始执行: {goal}",
            "timestamp": datetime.now().isoformat(),
            "task_id": task_id,
        }
        storage.append_message(agent_id, assistant_msg)
        result["task_id"] = task_id
    else:
        # 保存助手回复（非任务消息）
        assistant_msg = {
            "role": "assistant",
            "content": result.get("response", "收到，正在处理..."),
            "timestamp": datetime.now().isoformat(),
        }
        storage.append_message(agent_id, assistant_msg)

    result["agent_id"] = agent_id
    result["chat_history"] = storage.load_chat(agent_id)

    return result


@router.get("/{agent_id}/history")
async def get_chat_history(agent_id: str):
    """获取指定 Agent 的对话历史。"""
    messages = storage.load_chat(agent_id)
    return {"agent_id": agent_id, "messages": messages, "total": len(messages)}


@router.delete("/{agent_id}/history")
async def clear_chat_history(agent_id: str):
    """清空指定 Agent 的对话历史。"""
    storage.clear_chat(agent_id)
    return {"message": f"Agent {agent_id} history cleared"}


@router.post("/{agent_id}/history/compress")
async def compress_chat_history(agent_id: str, keep_last: int = 10):
    """压缩指定 Agent 的对话历史。"""
    compressed = storage.compress_chat(agent_id, keep_last=keep_last)
    return {
        "agent_id": agent_id,
        "chat_count": len(compressed),
        "compressed": True,
    }
