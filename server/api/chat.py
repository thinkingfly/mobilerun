"""对话 API 路由 — 通过 LangGraph 处理用户消息。"""

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter

from server.langgraph.dialogue_agent import process_message
from server.langgraph.tools import execute_goal, execute_goal_async
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

    支持多设备执行：当 device_serials 包含多个设备时，为每个设备创建独立任务。
    """
    agent_id = _resolve_agent_id(req.agent_id, None)

    # 调用 LangGraph 处理消息（含 checkpointer 持久化）
    result = await process_message(req.message, agent_id=agent_id)

    # 保存用户消息
    user_msg = {
        "role": "user",
        "content": req.message,
        "timestamp": datetime.now().isoformat(),
    }
    storage.append_message(agent_id, user_msg)

    # 确定目标设备列表（优先前端传入的 device_serials）
    target_devices = list(req.device_serials or [])
    if not target_devices and req.device_serial:
        target_devices = [req.device_serial]

    # 如果工具创建了任务，调度异步执行
    task_result = result.get("task_result")
    if task_result and task_result.get("task_id"):
        task_id = task_result["task_id"]
        goal = task_result["goal"]
        orig_device = task_result["device_serial"]
        task_agent_id = task_result["agent_id"]
        vision_only = task_result.get("vision_only", False)

        # 如果前端指定了设备且与 LangGraph 解析的不同，需要重新分配
        first_device = target_devices[0] if target_devices else orig_device

        # 如果第一个设备和 LangGraph 创建的不同，需要创建新任务
        tasks_to_schedule = []  # list of (task_id, device_serial)

        if first_device != orig_device:
            # 前端指定的第一个设备和 LangGraph 的不同 — 创建新任务
            new_task = execute_goal(goal, first_device, task_agent_id, vision_only=vision_only)
            tasks_to_schedule.append((new_task["task_id"], first_device))
        else:
            tasks_to_schedule.append((task_id, orig_device))

        # 为额外设备创建任务
        for dev in target_devices[1:]:
            extra = execute_goal(goal, dev, task_agent_id, vision_only=vision_only)
            tasks_to_schedule.append((extra["task_id"], dev))

        # 调度所有任务异步执行
        for tid, dev in tasks_to_schedule:
            asyncio.create_task(
                execute_goal_async(tid, goal, dev, task_agent_id,
                                   vision_only=vision_only)
            )

        # 保存助手回复
        device_info = ""
        if len(tasks_to_schedule) > 1:
            device_info = f"（{len(tasks_to_schedule)} 台设备）"
        assistant_msg = {
            "role": "assistant",
            "content": result.get("response") or f"任务已创建并开始执行{device_info}: {goal}",
            "timestamp": datetime.now().isoformat(),
            "task_id": tasks_to_schedule[0][0],
        }
        storage.append_message(agent_id, assistant_msg)
        result["task_id"] = tasks_to_schedule[0][0]
        result["all_task_ids"] = [t[0] for t in tasks_to_schedule]
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
