"""Agent 管理 API 路由。"""

import uuid

from fastapi import APIRouter, HTTPException

from server.models import Agent, AgentCreate
from server.state import state
from server.storage import storage

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
async def list_agents():
    """获取 Agent 列表（确保至少有一个默认 Agent）。"""
    ensure_default_agent()
    return state.list_agents()


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    """获取 Agent 详情。"""
    agent = state.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("")
async def create_agent(req: AgentCreate):
    """创建新 Agent。"""
    agent_id = str(uuid.uuid4())[:8]
    agent = Agent(
        id=agent_id,
        name=req.name,
        device_serial=req.device_serial,
    )
    state.create_agent(agent)
    return agent


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str):
    """删除 Agent。"""
    agent = state.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.is_default:
        raise HTTPException(
            status_code=400,
            detail="默认 Agent 无法删除",
        )

    if agent.status == "working":
        raise HTTPException(
            status_code=400,
            detail="该 Agent 正在执行任务，无法删除",
        )

    state.remove_agent(agent_id)
    # 同时清理聊天记录
    storage.clear_chat(agent_id)
    return {"message": f"Agent {agent_id} deleted"}


@router.get("/{agent_id}/memory")
async def get_agent_memory(agent_id: str):
    """获取 Agent 对话记忆。"""
    agent = state.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    messages = storage.load_chat(agent_id)
    return {
        "agent_id": agent_id,
        "chat_count": len(messages),
        "messages": messages,
    }


@router.delete("/{agent_id}/memory")
async def clear_agent_memory(agent_id: str):
    """清空 Agent 对话记忆。"""
    agent = state.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    storage.clear_chat(agent_id)
    return {"message": f"Agent {agent_id} memory cleared"}


@router.post("/{agent_id}/memory/compress")
async def compress_agent_memory(agent_id: str, keep_last: int = 10):
    """压缩 Agent 对话记忆：保留最近 N 条，其余压缩为摘要。"""
    agent = state.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    compressed = storage.compress_chat(agent_id, keep_last=keep_last)
    return {
        "agent_id": agent_id,
        "chat_count": len(compressed),
        "compressed": True,
    }


def ensure_default_agent() -> Agent:
    """确保存在默认 Agent，没有则创建。"""
    agents = state.list_agents()
    if agents:
        return agents[0]

    agent_id = str(uuid.uuid4())[:8]
    agent = Agent(id=agent_id, name=f"Agent-{agent_id}", status="idle", is_default=True)
    state.create_agent(agent)
    return agent
