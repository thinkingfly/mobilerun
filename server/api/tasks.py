"""任务管理 API 路由。"""

import asyncio
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from server.langgraph.tools import execute_goal_async
from server.models import Task, TaskCreate
from server.state import state

logger = logging.getLogger("mobilerun.server")
router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
async def list_tasks(
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    """获取任务列表（支持分页）。"""
    all_tasks = state.list_tasks(status=status)
    total = len(all_tasks)
    start = (page - 1) * page_size
    end = start + page_size
    tasks = all_tasks[start:end]
    return {
        "items": [t.model_dump(mode="json") for t in tasks],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
    }


@router.get("/{task_id}")
async def get_task(task_id: str):
    """获取任务详情。"""
    task = state.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("")
async def create_task(req: TaskCreate):
    """创建任务（立即开始执行）。"""
    device_serial = req.device_serial
    if not device_serial:
        for d in state.list_devices():
            if d.state in ("online", "busy"):
                device_serial = d.serial
                break

    if not device_serial:
        raise HTTPException(status_code=400, detail="No available devices")

    task_id = str(uuid.uuid4())[:8]

    # 确定使用的 Agent
    agent_id = req.agent_id
    if agent_id:
        agent = state.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    else:
        # 优先找绑定该设备的 Agent
        for a in state.list_agents():
            if a.device_serial == device_serial and a.status == "idle":
                agent_id = a.id
                break
        # 如果没有，找任意一个 idle Agent
        if not agent_id:
            for a in state.list_agents():
                if a.status == "idle":
                    agent_id = a.id
                    break
        # 如果都没有，创建默认 Agent
        if not agent_id:
            from server.api.agents import ensure_default_agent
            agent = ensure_default_agent()
            agent_id = agent.id

    task = Task(
        id=task_id,
        agent_id=agent_id,
        device_serial=device_serial,
        goal=req.goal,
        status="running",
        started_at=datetime.now(),
    )
    state.create_task(task)
    state.set_device_busy(device_serial, task_id)
    state.update_agent(agent_id, status="working", current_task=task_id)

    # 调度异步执行
    asyncio.create_task(execute_goal_async(task_id, req.goal, device_serial, agent_id))

    return task


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消运行中的任务。"""
    task = state.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status not in ("running", "pending"):
        raise HTTPException(status_code=400, detail=f"Task is {task.status}, cannot cancel")

    state.cancel_task(task_id)
    state.set_device_busy(task.device_serial, None)

    if task.agent_id:
        state.update_agent(task.agent_id, status="idle", current_task=None)

    return {"message": f"Task {task_id} cancelled"}
