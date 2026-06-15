"""定时任务调度器 — 基于 asyncio 的 cron 调度。"""

import asyncio
import logging
import uuid
from datetime import datetime

from croniter import croniter

from server.storage import storage

logger = logging.getLogger("mobilerun.server.scheduler")


class TaskScheduler:
    """定时任务调度器 — 每分钟检查一次到期任务。"""

    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        """启动调度器。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Task scheduler started")

    async def stop(self):
        """停止调度器。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Task scheduler stopped")

    async def _loop(self):
        """主循环 — 每分钟检查一次。"""
        # 启动时先更新所有任务的 next_run
        self._update_all_next_runs()

        while self._running:
            try:
                await asyncio.sleep(60)
                await self._check_and_run()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")

    def _update_all_next_runs(self):
        """启动时更新所有定时任务的 next_run。"""
        scheduled = storage.load_scheduled_tasks(enabled_only=True)
        now = datetime.now()
        for st in scheduled:
            try:
                base_time = datetime.fromisoformat(st["last_run"]) if st.get("last_run") else now
                cron = croniter(st["cron_expression"], base_time)
                next_run = cron.get_next(datetime)
                storage.update_scheduled_task(st["id"], {"next_run": next_run.isoformat()})
            except Exception as e:
                logger.warning(f"Failed to compute next_run for {st['id']}: {e}")

    async def _check_and_run(self):
        """检查并触发到期任务。"""
        from server.langgraph.tools import execute_goal_async

        now = datetime.now()
        scheduled = storage.load_scheduled_tasks(enabled_only=True)

        for st in scheduled:
            try:
                next_run_str = st.get("next_run")
                if not next_run_str:
                    # 计算 next_run
                    base_time = datetime.fromisoformat(st["last_run"]) if st.get("last_run") else now
                    cron = croniter(st["cron_expression"], base_time)
                    next_run = cron.get_next(datetime)
                    storage.update_scheduled_task(st["id"], {"next_run": next_run.isoformat()})
                    continue

                next_run = datetime.fromisoformat(next_run_str)
                if next_run > now:
                    continue

                # 触发执行
                goal = st["goal"]
                agent_id = st["agent_id"]
                device_serials = st.get("device_serials", [])

                # 检测是否为聊天 Bot 任务
                from server.langgraph.chat_bot_config import should_use_chat_bot, parse_target_chat
                use_chat_bot, app_name, app_config = should_use_chat_bot(goal)

                logger.info(
                    f"Scheduled task {st['id']} triggered: {goal[:50]} "
                    f"use_chat_bot={use_chat_bot}"
                )

                for dev in device_serials:
                    task_id = str(uuid.uuid4())[:8]
                    from server.models import Task
                    from server.state import state

                    if use_chat_bot:
                        # ── Chat Bot 任务：走 chat_bot_agent 完整流程 ──
                        from server.langgraph.chat_bot_agent import execute_chat_bot_task
                        from server.websocket.log_handler import WebSocketLogHandler

                        source = app_config["source"]
                        target_chat = parse_target_chat(goal, app_name)

                        task = Task(
                            id=task_id,
                            agent_id=agent_id,
                            device_serial=dev,
                            goal=goal,
                            status="running",
                            type="chat_bot",
                            parent_task=st["id"],
                            started_at=now,
                        )
                        state.create_task(task)
                        state.set_device_busy(dev, task_id)
                        state.update_agent(agent_id, status="working", current_task=task_id)

                        ws_handler = WebSocketLogHandler(task_id)
                        ws_handler.set_loop(asyncio.get_running_loop())

                        async def _run_chat_bot(tid=task_id, d=dev, s=source, an=app_name, tc=target_chat, aid=agent_id, wh=ws_handler):
                            try:
                                r = await execute_chat_bot_task(
                                    device_id=d, source=s, app_name=an,
                                    target_chat=tc, agent_id=aid, task_id=tid,
                                    log_handler=wh,
                                )
                                if r.get("success"):
                                    state.update_task_status(tid, "completed", result=r)
                                else:
                                    state.update_task_status(tid, "failed", result=r)
                            except Exception as e:
                                logger.error(f"Chat bot scheduled task error {tid}: {e}")
                                state.update_task_status(tid, "failed", result={"success": False, "error": str(e)})
                            finally:
                                state.clear_runner(tid)
                                state.set_device_busy(d, None)
                                state.update_agent(aid, status="idle", current_task=None)

                        asyncio.create_task(_run_chat_bot())
                    else:
                        # ── 普通设备任务 ──
                        from server.langgraph.dialogue_agent import _auto_vision_only
                        vision_only = _auto_vision_only(goal)

                        task = Task(
                            id=task_id,
                            agent_id=agent_id,
                            device_serial=dev,
                            goal=goal,
                            status="running",
                            type="normal",
                            parent_task=st["id"],
                            started_at=now,
                        )
                        state.create_task(task)
                        state.set_device_busy(dev, task_id)
                        state.update_agent(agent_id, status="working", current_task=task_id)

                        asyncio.create_task(
                            execute_goal_async(task_id, goal, dev, agent_id,
                                               vision_only=vision_only)
                        )

                # 更新 last_run 和 next_run
                cron = croniter(st["cron_expression"], now)
                new_next = cron.get_next(datetime)
                storage.update_scheduled_task(st["id"], {
                    "last_run": now.isoformat(),
                    "next_run": new_next.isoformat(),
                })

            except Exception as e:
                logger.error(f"Error running scheduled task {st.get('id')}: {e}")

    def compute_next_run(self, cron_expression: str, base_time: datetime | None = None) -> datetime:
        """计算下一次运行时间。"""
        if base_time is None:
            base_time = datetime.now()
        cron = croniter(cron_expression, base_time)
        return cron.get_next(datetime)


# 全局单例
scheduler = TaskScheduler()
