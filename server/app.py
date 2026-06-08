"""FastAPI 主应用 — Mobilerun Agent Dashboard 后端。"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.api import agents, chat, devices, tasks, ws
from server.state import state

logger = logging.getLogger("mobilerun.server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    # 启动
    logger.info("Mobilerun Agent Dashboard 启动中...")
    # 启动设备监控
    monitor_task = asyncio.create_task(device_monitor_loop())

    yield

    # 关闭
    logger.info("Mobilerun Agent Dashboard 关闭中...")
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass


async def device_monitor_loop():
    """定期扫描 ADB 设备。"""
    while True:
        try:
            await asyncio.sleep(10)
            from server.langgraph.device_agent import discover_devices

            await discover_devices({})
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"设备监控异常: {e}")


def create_app() -> FastAPI:
    """创建 FastAPI 应用。"""
    app = FastAPI(
        title="Mobilerun Agent Dashboard",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 路由
    app.include_router(devices.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")
    app.include_router(agents.router, prefix="/api")
    app.include_router(ws.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")

    # 仪表盘统计
    @app.get("/api/stats")
    async def get_stats():
        return state.get_stats()

    return app


app = create_app()
