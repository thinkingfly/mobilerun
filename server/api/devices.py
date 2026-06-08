"""设备管理 API 路由。"""

import asyncio
import logging

from fastapi import APIRouter

from server.models import Device, DeviceCreate
from server.state import state

logger = logging.getLogger("mobilerun.server")
router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[Device])
async def list_devices():
    """获取设备列表（实时扫描 ADB）。"""
    # 触发设备扫描
    from server.langgraph.device_agent import discover_devices

    await discover_devices({})
    return state.list_devices()


@router.get("/{serial}")
async def get_device(serial: str):
    """获取单个设备信息。"""
    device = state.get_device(serial)
    if not device:
        return {"error": "Device not found"}
    return device


@router.post("/{serial}/refresh")
async def refresh_device(serial: str):
    """刷新设备状态。"""
    try:
        from async_adbutils import adb

        devices = await adb.list()
        for d in devices:
            if d.serial == serial:
                adb_state = getattr(d, "state", "unknown")
                state.upsert_device(serial, state="online" if adb_state == "device" else "offline")
                return {"serial": serial, "state": "online" if adb_state == "device" else "offline"}

        state.upsert_device(serial, state="offline")
        return {"serial": serial, "state": "offline"}
    except Exception as e:
        logger.error(f"刷新设备失败: {e}")
        return {"error": str(e)}


@router.post("")
async def add_device(req: DeviceCreate):
    """手动添加设备。"""
    device = state.upsert_device(req.serial, platform=req.platform, state="online")
    return device


@router.delete("/{serial}")
async def remove_device(serial: str):
    """移除设备。"""
    state.remove_device(serial)
    return {"message": f"Device {serial} removed"}
