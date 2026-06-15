"""定时任务管理 API 路由。"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

from server.models import ScheduledTask, ScheduledTaskCreate
from server.scheduler import scheduler
from server.state import state
from server.storage import storage
logger = logging.getLogger("mobilerun.server")
router = APIRouter(prefix="/scheduled-tasks", tags=["scheduled-tasks"])


@router.get("")
async def list_scheduled_tasks():
    """获取所有定时任务。"""
    tasks = storage.load_scheduled_tasks()
    return {"items": tasks, "total": len(tasks)}


@router.get("/{task_id}")
async def get_scheduled_task(task_id: str):
    """获取定时任务详情。"""
    task = storage.get_scheduled_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return task


@router.post("")
async def create_scheduled_task(req: ScheduledTaskCreate):
    """创建定时任务。"""
    # 验证 cron 表达式
    try:
        next_run = scheduler.compute_next_run(req.cron_expression)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid cron expression: {e}")

    # 确定 agent_id
    agent_id = req.agent_id
    if not agent_id:
        agents = state.list_agents()
        idle = [a for a in agents if a.status == "idle"]
        if idle:
            agent_id = idle[0].id
        elif agents:
            agent_id = agents[0].id
        else:
            from server.api.agents import ensure_default_agent
            agent_id = ensure_default_agent().id

    # 验证设备
    if not req.device_serials:
        raise HTTPException(status_code=400, detail="At least one device is required")

    st_id = str(uuid.uuid4())[:8]
    now = datetime.now()

    scheduled_task = {
        "id": st_id,
        "task_id": st_id,  # 关联自身的 ID
        "agent_id": agent_id,
        "goal": req.goal,
        "device_serials": req.device_serials,
        "cron_expression": req.cron_expression,
        "enabled": True,
        "last_run": None,
        "next_run": next_run.isoformat(),
        "created_at": now.isoformat(),
    }
    storage.append_scheduled_task(scheduled_task)

    logger.info(f"Created scheduled task {st_id}: {req.goal[:50]} cron={req.cron_expression}")

    return {
        **scheduled_task,
        "device_serials": req.device_serials,
        "enabled": True,
        "message": f"定时任务已创建：{req.cron_expression} 执行 '{req.goal}'",
    }


@router.delete("/{task_id}")
async def delete_scheduled_task(task_id: str):
    """删除定时任务。"""
    task = storage.get_scheduled_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    storage.remove_scheduled_task(task_id)
    return {"message": f"Scheduled task {task_id} deleted"}


@router.post("/{task_id}/toggle")
async def toggle_scheduled_task(task_id: str):
    """启用/禁用定时任务。"""
    task = storage.get_scheduled_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    new_enabled = not task["enabled"]
    storage.update_scheduled_task(task_id, {"enabled": new_enabled})

    # 如果启用，重新计算 next_run
    if new_enabled:
        try:
            base = datetime.fromisoformat(task["last_run"]) if task.get("last_run") else None
            next_run = scheduler.compute_next_run(task["cron_expression"], base)
            storage.update_scheduled_task(task_id, {"next_run": next_run.isoformat()})
        except Exception:
            pass

    status_str = "启用" if new_enabled else "禁用"
    return {"message": f"Scheduled task {task_id} {status_str}", "enabled": new_enabled}


@router.post("/{task_id}/cancel")
async def cancel_scheduled_task(task_id: str):
    """取消定时任务：禁用 + 停止所有运行中的子任务。"""
    st = storage.get_scheduled_task(task_id)
    if not st:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    # 禁用定时任务
    storage.update_scheduled_task(task_id, {"enabled": False})

    # 取消所有运行中的子任务
    children = storage.load_child_tasks(task_id)
    cancelled_count = 0
    for child in children:
        if child.get("status") == "running":
            state.cancel_task(child["id"])
            cancelled_count += 1

    logger.info(f"Cancelled scheduled task {task_id}, {cancelled_count} children cancelled")
    return {
        "message": f"Scheduled task {task_id} cancelled",
        "cancelled_children": cancelled_count,
    }


@router.get("/{task_id}/history")
async def get_scheduled_task_history(task_id: str):
    """获取定时任务的执行历史（子任务列表）。"""
    st = storage.get_scheduled_task(task_id)
    if not st:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    children = storage.load_child_tasks(task_id)
    return {"items": children, "total": len(children)}
