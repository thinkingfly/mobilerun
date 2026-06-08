"""LangGraph 设备管理 Agent — 协调多设备任务分发。"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from mobilerun_api import run_async
from server.models import Agent, Task
from server.state import state as app_state

logger = logging.getLogger("mobilerun.server.device")


class DeviceAgentState(TypedDict):
    """设备管理 Agent 状态。"""
    goal: str
    device_serial: Optional[str]
    task_id: Optional[str]
    agent_id: Optional[str]
    result: dict
    error: Optional[str]


async def discover_devices(state: DeviceAgentState) -> DeviceAgentState:
    """扫描 ADB 设备并更新状态。"""
    try:
        from async_adbutils import adb

        devices = await adb.list()
        for d in devices:
            serial = d.serial
            adb_state = getattr(d, "state", "unknown")
            if adb_state == "device":
                existing = app_state.get_device(serial)
                if not existing or existing.state == "offline":
                    app_state.upsert_device(serial, state="online", platform="android", portal_connected=False)
                else:
                    app_state.upsert_device(serial, state=existing.state, portal_connected=existing.portal_connected)

        known = {d.serial for d in devices}
        for d in app_state.list_devices():
            if d.serial not in known:
                app_state.upsert_device(d.serial, state="offline")

        logger.info(f"设备扫描完成: {len(devices)} 台")
    except Exception as e:
        logger.error(f"设备扫描失败: {e}")

    return state


async def select_device(state: DeviceAgentState) -> DeviceAgentState:
    """选择目标设备。"""
    serial = state["device_serial"]
    if not serial:
        for d in app_state.list_devices():
            if d.state in ("online", "busy"):
                state["device_serial"] = d.serial
                break

    if not state["device_serial"]:
        state["error"] = "没有可用的设备"
        state["result"] = {"success": False, "reason": "No devices available"}

    return state


async def create_task(state: DeviceAgentState) -> DeviceAgentState:
    """创建任务记录。"""
    task_id = str(uuid.uuid4())[:8]

    agent_id = None
    agent = None
    for a in app_state.list_agents():
        if a.device_serial == state["device_serial"]:
            agent_id = a.id
            agent = a
            break

    if not agent_id:
        agent_id = str(uuid.uuid4())[:8]
        agent = Agent(id=agent_id, name=f"Agent-{agent_id}", device_serial=state["device_serial"])
        app_state.create_agent(agent)

    serial = state["device_serial"]
    goal = state["goal"]

    task = Task(
        id=task_id,
        agent_id=agent_id,
        device_serial=serial,
        goal=goal,
        status="pending",
    )
    app_state.create_task(task)

    app_state.set_device_busy(serial, task_id)
    app_state.update_agent(agent_id, status="working", current_task=task_id, total_tasks=(agent.total_tasks + 1) if agent else 1)

    state["task_id"] = task_id
    state["agent_id"] = agent_id
    logger.info(f"任务创建: {task_id} on {serial}")

    return state


async def execute_task(state: DeviceAgentState) -> DeviceAgentState:
    """执行任务。"""
    task_id = state["task_id"]
    goal = state["goal"]
    serial = state["device_serial"]
    agent_id = state["agent_id"]

    cancel_event = app_state.get_cancel_event(task_id)

    async def _run():
        try:
            return await run_async(
                goal,
                device_serial=serial,
                cancel_event=cancel_event,
                max_steps=25,
                reasoning=False,
                vision_only=False,
                debug=False,
            )
        except Exception as e:
            return {"success": False, "reason": str(e)}

    runner = asyncio.create_task(_run())
    app_state.register_runner(task_id, runner)
    app_state.update_task_status(task_id, "running")

    result = await runner

    app_state.clear_runner(task_id)

    if result.get("success"):
        app_state.update_task_status(task_id, "completed", result=result)
        if agent_id:
            app_state.update_agent(agent_id, status="idle", current_task=None)
    else:
        app_state.update_task_status(task_id, "failed", result=result)
        if agent_id:
            app_state.update_agent(agent_id, status="idle", current_task=None)

    app_state.set_device_busy(serial, None)
    state["result"] = result
    return state


def build_graph():
    """构建设备管理 LangGraph。"""
    graph = StateGraph(DeviceAgentState)

    graph.add_node("discover", discover_devices)
    graph.add_node("select", select_device)
    graph.add_node("create", create_task)
    graph.add_node("execute", execute_task)

    graph.add_edge("discover", "select")
    graph.add_edge("select", "create")
    graph.add_edge("create", "execute")
    graph.add_edge("execute", END)

    graph.set_entry_point("discover")
    return graph.compile()


# 全局图实例
graph = build_graph()


async def execute_on_device(goal: str, device_serial: Optional[str] = None) -> dict:
    """通过设备管理 Agent 执行任务。

    Returns:
        {"task_id": str, "status": str, "result": dict | None}
    """
    initial_state: DeviceAgentState = {
        "goal": goal,
        "device_serial": device_serial,
        "task_id": None,
        "agent_id": None,
        "result": {},
        "error": None,
    }

    result = await graph.ainvoke(initial_state)
    return {
        "task_id": result.get("task_id"),
        "status": "completed" if result.get("result", {}).get("success") else "failed",
        "result": result.get("result"),
        "error": result.get("error"),
    }
