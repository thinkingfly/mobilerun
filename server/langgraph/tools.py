"""LangGraph 工具函数 — 设备操作执行工具。"""

import asyncio
import logging
import uuid
from datetime import datetime

from server.models import Task as TaskModel
from server.state import state

logger = logging.getLogger("mobilerun.server")


def execute_goal(goal: str, device_serial: str, agent_id: str, vision_only: bool = False) -> dict:
    """准备执行设备操作工具。

    创建任务记录、设置日志处理器，并返回任务配置供调用者调度执行。

    Args:
        goal: 要执行的目标指令（自然语言）
        device_serial: 目标设备序列号
        agent_id: 执行 Agent 的 ID
        vision_only: 是否使用纯视觉模式（不依赖无障碍服务）

    Returns:
        {"task_id": str, "agent_id": str, "goal": str, "device_serial": str, "vision_only": bool}
    """
    task_id = str(uuid.uuid4())[:8]
    now = datetime.now()

    task = TaskModel(
        id=task_id,
        agent_id=agent_id,
        device_serial=device_serial,
        goal=goal,
        status="running",
        created_at=now,
        started_at=now,
    )
    state.create_task(task)
    state.set_device_busy(device_serial, task_id)
    state.update_agent(agent_id, status="working", current_task=task_id)

    mode = "vision_only" if vision_only else "normal"
    logger.info(f"Tool execute_goal: created task {task_id} goal={goal[:50]} mode={mode}")

    return {
        "task_id": task_id,
        "agent_id": agent_id,
        "goal": goal,
        "device_serial": device_serial,
        "vision_only": vision_only,
    }


async def execute_goal_async(task_id: str, goal: str, device_serial: str, agent_id: str, vision_only: bool = False) -> dict:
    """异步执行任务。由调用者在创建任务后调度执行。"""
    from mobilerun_api import run_async
    from server.storage import storage
    from server.websocket.log_handler import WebSocketLogHandler

    ws_handler = WebSocketLogHandler(task_id)
    ws_handler.set_loop(asyncio.get_running_loop())

    cancel_event = state.get_cancel_event(task_id)

    try:
        mode_str = "vision_only" if vision_only else "normal"
        logger.info(f"Task {task_id} starting with {mode_str} mode")
        result = await run_async(
            goal,
            device_serial=device_serial,
            cancel_event=cancel_event,
            max_steps=25,
            reasoning=False,
            vision_only=vision_only,
            debug=False,
            log_handler=ws_handler,
        )
        logger.info(f"Task {task_id} completed: {result}")

        if result.get("success"):
            state.update_task_status(task_id, "completed", result=result)
            # 将执行结果追加到对话历史
            storage.append_message(agent_id, {
                "role": "assistant",
                "content": f"✅ 任务完成: {goal}\n结果: {result.get('reason', '')}",
                "timestamp": datetime.now().isoformat(),
                "task_id": task_id,
            })
        else:
            state.update_task_status(task_id, "failed", result=result)
            # 将失败结果追加到对话历史
            storage.append_message(agent_id, {
                "role": "assistant",
                "content": f"❌ 任务失败: {goal}\n原因: {result.get('reason', '未知错误')}",
                "timestamp": datetime.now().isoformat(),
                "task_id": task_id,
            })
    except asyncio.CancelledError:
        state.update_task_status(task_id, "cancelled")
        storage.append_message(agent_id, {
            "role": "assistant",
            "content": f"⏹ 任务已取消: {goal}",
            "timestamp": datetime.now().isoformat(),
            "task_id": task_id,
        })
    except Exception as e:
        logger.error(f"任务执行异常 {task_id}: {e}")
        state.update_task_status(task_id, "failed", result={"success": False, "reason": str(e)})
        storage.append_message(agent_id, {
            "role": "assistant",
            "content": f"❌ 任务异常: {goal}\n原因: {str(e)}",
            "timestamp": datetime.now().isoformat(),
            "task_id": task_id,
        })
    finally:
        state.clear_runner(task_id)
        state.set_device_busy(device_serial, None)
        if agent_id:
            state.update_agent(agent_id, status="idle", current_task=None)

    return result
