"""WebSocket API 路由 — 实时日志推送。"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.websocket.manager import manager as ws_manager

logger = logging.getLogger("mobilerun.server")
router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/logs/{task_id}")
async def websocket_logs(websocket: WebSocket, task_id: str):
    """订阅任务实时日志。

    客户端连接后，会收到该任务的所有日志推送。
    断开连接后自动取消订阅。
    """
    await ws_manager.connect(websocket, task_id)
    try:
        while True:
            # 接收客户端消息（可选：客户端可发送心跳或取消请求）
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                # 处理客户端消息（如心跳）
                logger.debug(f"WS received from {task_id}: {data}")
            except asyncio.TimeoutError:
                # 心跳超时，发送 ping
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        logger.info(f"WS disconnected: {task_id}")
    except Exception as e:
        logger.warning(f"WS error for {task_id}: {e}")
    finally:
        await ws_manager.disconnect(websocket, task_id)


@router.websocket("/logs/{task_id}/stream")
async def websocket_stream(websocket: WebSocket, task_id: str):
    """简化版日志流（只推送，不接收）。"""
    await ws_manager.connect(websocket, task_id)
    try:
        # 保持连接直到客户端断开
        while True:
            await asyncio.sleep(10)
            try:
                await websocket.send_json({"type": "ping"})
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(websocket, task_id)
