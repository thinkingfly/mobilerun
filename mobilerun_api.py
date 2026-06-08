"""
Mobilerun Agent API — 纯函数调用，支持任务取消

用法：
    from mobilerun_api import run, run_async, run_with_cancel

    # 同步调用
    result = run("打开微信", device_serial="AK3SBB5530100840")

    # 异步调用
    result = await run_async("打开微信", device_serial="AK3SBB5530100840")

    # 可取消的异步调用
    cancel_event, task, result_future = run_with_cancel("打开微信", device_serial="...")
    # 需要取消时：
    cancel_event.set()
    result = await result_future
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Optional, Tuple

# ── 默认配置（可通过环境变量或参数覆盖）──
DEFAULT_LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://coding.dashscope.aliyuncs.com/v1")
DEFAULT_LLM_API_KEY = (
    os.environ.get("LLM_API_KEY", "")
    or os.environ.get("OPENAI_API_KEY", "")
    or "sk-sp-e2a147ef4ed54e7991e184b24913f3a8"
)
DEFAULT_LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "OpenAILike")
DEFAULT_LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3.7-plus")


@dataclass
class Config:
    """运行配置。"""
    device_serial: str
    platform: str = "android"
    provider: str = DEFAULT_LLM_PROVIDER
    model: str = DEFAULT_LLM_MODEL
    base_url: str = DEFAULT_LLM_BASE_URL
    api_key: str = DEFAULT_LLM_API_KEY
    max_steps: int = 25
    reasoning: bool = False
    vision_only: bool = False
    auto_setup: bool = False
    debug: bool = False
    disabled_tools: list[str] = field(default_factory=list)


def _setup_logging(debug: bool = False):
    """配置日志（幂等，只设置一次）。"""
    if logging.getLogger("mobilerun").handlers:
        return
    level = logging.DEBUG if debug else logging.INFO
    logger = logging.getLogger("mobilerun")
    logger.setLevel(level)
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    for name in ["httpcore", "httpx", "openai", "llama_index", "urllib3", "websocket"]:
        logging.getLogger(name).setLevel(logging.WARNING)


def _build_config(**overrides) -> Config:
    """从关键字参数构建 Config。"""
    defaults = {
        "device_serial": "",
        "platform": "android",
        "provider": DEFAULT_LLM_PROVIDER,
        "model": DEFAULT_LLM_MODEL,
        "base_url": DEFAULT_LLM_BASE_URL,
        "api_key": DEFAULT_LLM_API_KEY,
        "max_steps": 25,
        "reasoning": False,
        "vision_only": False,
        "auto_setup": False,
        "debug": False,
        "disabled_tools": [],
    }
    for k, v in overrides.items():
        if v is not None:
            defaults[k] = v
    return Config(**defaults)


def _extract_log_entry(event, step: int = 0, max_steps: int = 25) -> Optional[logging.LogRecord]:
    """从 mobilerun 事件中提取日志记录（带 color 信息）。"""
    from mobilerun.agent.common.events import ScreenshotEvent, RecordUIStateEvent
    from mobilerun.agent.droid.events import (
        ExecutorResultEvent, FastAgentExecuteEvent, FastAgentResultEvent, FinalizeEvent,
    )
    from mobilerun.agent.executor.events import ExecutorActionEvent, ExecutorActionResultEvent
    from mobilerun.agent.fast_agent.events import (
        FastAgentEndEvent, FastAgentInputEvent, FastAgentOutputEvent,
        FastAgentResponseEvent, FastAgentToolCallEvent,
    )
    from mobilerun.agent.manager.events import (
        ManagerContextEvent, ManagerPlanDetailsEvent, ManagerResponseEvent,
    )

    record = None

    if isinstance(event, ScreenshotEvent):
        record = logging.makeLogRecord({"msg": "📸 Taking screenshot...", "levelno": logging.DEBUG})
    elif isinstance(event, RecordUIStateEvent):
        record = logging.makeLogRecord({"msg": "✏️ Recording UI state", "levelno": logging.DEBUG})
    elif isinstance(event, ManagerContextEvent):
        record = logging.makeLogRecord({"msg": "🧠 Manager preparing context...", "levelno": logging.DEBUG})
    elif isinstance(event, ManagerResponseEvent):
        record = logging.makeLogRecord({"msg": "📥 Manager received LLM response", "levelno": logging.DEBUG})
    elif isinstance(event, ManagerPlanDetailsEvent):
        if event.thought:
            preview = event.thought[:120] + "..." if len(event.thought) > 120 else event.thought
            record = logging.makeLogRecord({"msg": f"💭 Thought: {preview}", "levelno": logging.DEBUG, "color": "cyan"})
        elif event.subgoal:
            preview = event.subgoal[:150] + "..." if len(event.subgoal) > 150 else event.subgoal
            record = logging.makeLogRecord({"msg": f"📋 Next step: {preview}", "levelno": logging.DEBUG, "color": "yellow"})
        elif event.answer:
            preview = event.answer[:200] + "..." if len(event.answer) > 200 else event.answer
            record = logging.makeLogRecord({"msg": f"💬 Answer: {preview}", "levelno": logging.DEBUG, "color": "green"})
        elif event.plan:
            record = logging.makeLogRecord({"msg": f"▸ {event.plan}", "levelno": logging.DEBUG, "color": "yellow"})
        elif event.memory_update:
            record = logging.makeLogRecord({"msg": f"🧠 Memory: {event.memory_update[:100]}...", "levelno": logging.DEBUG, "color": "cyan"})
    elif isinstance(event, ExecutorActionEvent):
        if event.description:
            record = logging.makeLogRecord({"msg": f"🎯 Action: {event.description}", "levelno": logging.DEBUG, "color": "yellow"})
        elif event.thought:
            preview = event.thought[:120] + "..." if len(event.thought) > 120 else event.thought
            record = logging.makeLogRecord({"msg": f"💭 Reasoning: {preview}", "levelno": logging.DEBUG, "color": "cyan"})
    elif isinstance(event, ExecutorActionResultEvent):
        if event.success:
            record = logging.makeLogRecord({"msg": f"✅ {event.summary}", "levelno": logging.DEBUG, "color": "green"})
        else:
            error_msg = event.error or "Unknown error"
            record = logging.makeLogRecord({"msg": f"❌ {event.summary} ({error_msg})", "levelno": logging.DEBUG, "color": "red"})
    elif isinstance(event, ExecutorResultEvent):
        record = logging.makeLogRecord({"msg": "Step complete", "levelno": logging.DEBUG, "color": "magenta"})
    elif isinstance(event, FastAgentInputEvent):
        record = logging.makeLogRecord({"msg": "💬 Task input received...", "levelno": logging.DEBUG})
    elif isinstance(event, FastAgentResponseEvent):
        record = logging.makeLogRecord({"msg": "FastAgent response：", "levelno": logging.DEBUG, "color": "magenta"})
        if event.thought:
            preview = event.thought[:150] + "..." if len(event.thought) > 150 else event.thought
            record = logging.makeLogRecord({"msg": f"🧠 Thinking: {preview}", "levelno": logging.DEBUG, "color": "cyan"})
        elif event.code:
            record = logging.makeLogRecord({"msg": "💻 Executing action code", "levelno": logging.DEBUG, "color": "blue"})
    elif isinstance(event, FastAgentToolCallEvent):
        record = logging.makeLogRecord({"msg": "⚡ Executing tool calls...", "levelno": logging.DEBUG, "color": "yellow"})
    elif isinstance(event, FastAgentOutputEvent):
        if event.output:
            output = str(event.output)
            preview = output[:100] + "..." if len(output) > 100 else output
            if "Error" in output or "Exception" in output:
                record = logging.makeLogRecord({"msg": f"❌ Action error: {preview}", "levelno": logging.DEBUG, "color": "red"})
            else:
                record = logging.makeLogRecord({"msg": f"⚡ Action result: {preview}", "levelno": logging.DEBUG, "color": "green"})
    elif isinstance(event, FastAgentEndEvent):
        status = "done" if event.success else "failed"
        color = "green" if event.success else "red"
        record = logging.makeLogRecord({"msg": f"■ {status}: {event.reason} ({event.tool_call_count} runs)", "levelno": logging.DEBUG, "color": color})
    elif isinstance(event, FastAgentExecuteEvent):
        record = logging.makeLogRecord({"msg": f"🔄 Step {step}/{max_steps}", "levelno": logging.DEBUG, "color": "magenta"})
    elif isinstance(event, FastAgentResultEvent):
        if event.success:
            record = logging.makeLogRecord({"msg": f"Task result: {event.reason}", "levelno": logging.DEBUG, "color": "green"})
        else:
            record = logging.makeLogRecord({"msg": f"Task failed: {event.reason}", "levelno": logging.DEBUG, "color": "red"})
    elif isinstance(event, FinalizeEvent):
        if event.success:
            record = logging.makeLogRecord({"msg": f"🎉 Goal achieved: {event.reason}", "levelno": logging.INFO, "color": "green"})
        else:
            record = logging.makeLogRecord({"msg": f"❌ Goal failed: {event.reason}", "levelno": logging.INFO, "color": "red"})

    return record


async def _run_goal_internal(goal: str, cfg: Config, cancel_event: Optional[asyncio.Event] = None, log_handler=None) -> dict:
    """内部执行逻辑，支持取消事件和自定义日志处理器。"""
    from mobilerun.agent.droid import MobileAgent
    from mobilerun.agent.utils.llm_picker import load_llm
    from mobilerun.cli.event_handler import EventHandler
    from mobilerun.config_manager.loader import ConfigLoader

    config = ConfigLoader.load()
    config.device.serial = cfg.device_serial
    config.device.platform = cfg.platform
    config.device.auto_setup = cfg.auto_setup
    config.agent.max_steps = cfg.max_steps
    config.agent.reasoning = cfg.reasoning
    config.agent.vision_only = cfg.vision_only    # 由 _auto_vision_only 自动判断
    config.agent.stream = True
    # 子 Agent 的 vision 跟随 vision_only：开启时 FastAgent 才能截图
    config.agent.manager.vision = cfg.vision_only
    config.agent.executor.vision = cfg.vision_only
    config.agent.fast_agent.vision = cfg.vision_only
    if cfg.disabled_tools:
        config.tools.disabled_tools = cfg.disabled_tools

    if cfg.api_key:
        os.environ["OPENAI_API_KEY"] = cfg.api_key

    llm_kwargs = {
        "provider_name": cfg.provider,
        "model": cfg.model,
        "is_chat_model": True,
    }
    if cfg.base_url:
        llm_kwargs["base_url"] = cfg.base_url

    llm = load_llm(**llm_kwargs)

    droid_agent = MobileAgent(goal=goal, llms=llm, config=config, timeout=1000)
    event_handler = EventHandler()

    try:
        # 输出任务启动信息
        if log_handler:
            mode_text = "direct execution" if not cfg.reasoning else "reasoning (Manager + Executor)"
            log_handler.emit(logging.makeLogRecord({
                "msg": f"🚀 Starting: {goal}",
                "levelno": logging.INFO,
                "color": "magenta",
            }))
            log_handler.emit(logging.makeLogRecord({
                "msg": f"🤖 Agent mode: {mode_text}",
                "levelno": logging.INFO,
                "color": "cyan",
            }))
            log_handler.emit(logging.makeLogRecord({
                "msg": f"👁️ Vision mode: reasoning={config.agent.reasoning}, vision_only={config.agent.vision_only}, Manager.vision={config.agent.manager.vision}, Executor.vision={config.agent.executor.vision}, FastAgent.vision={config.agent.fast_agent.vision}",
                "levelno": logging.INFO,
                "color": "cyan",
            }))
            log_handler.emit(logging.makeLogRecord({
                "msg": f"🚀 Running MobileAgent to achieve goal: {goal}",
                "levelno": logging.INFO,
                "color": "magenta",
            }))

        handler = droid_agent.run()

        step = 0
        async for event in handler.stream_events():
            if cancel_event and cancel_event.is_set():
                return {"success": False, "reason": "Task cancelled by user"}
            event_handler.handle(event)
            # 如果提供了日志处理器，提取事件信息并推送
            if log_handler:
                # 跟踪步骤数（FastAgentExecuteEvent 表示新的一轮执行）
                from mobilerun.agent.droid.events import FastAgentExecuteEvent as _FAEE
                if isinstance(event, _FAEE):
                    step += 1
                log_entry = _extract_log_entry(event, step=step, max_steps=cfg.max_steps)
                if log_entry:
                    log_handler.emit(log_entry)

        if cancel_event and cancel_event.is_set():
            return {"success": False, "reason": "Task cancelled by user"}

        result = await handler
    except KeyboardInterrupt:
        return {"success": False, "reason": "Interrupted by user"}

    return {
        "success": getattr(result, "success", False),
        "reason": getattr(result, "reason", "N/A"),
    }


async def run_async(
    goal: str,
    *,
    device_serial: str = "",
    platform: str = "android",
    provider: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    max_steps: int = 25,
    reasoning: bool = False,
    vision_only: bool = False,
    auto_setup: bool = False,
    debug: bool = False,
    disabled_tools: Optional[list[str]] = None,
    cancel_event: Optional[asyncio.Event] = None,
    log_handler=None,
) -> dict:
    """异步执行目标指令。

    Args:
        goal: 要执行的目标指令（自然语言）
        device_serial: 设备序列号
        platform: 平台类型，"android" 或 "ios"
        provider: LLM provider 名称
        model: LLM 模型名称
        base_url: LLM API base URL
        api_key: LLM API Key
        max_steps: 最大执行步数
        reasoning: 是否使用推理模式（Manager + Executor）
        vision_only: 是否仅使用截图模式（不使用 UI 树）
        auto_setup: 是否自动安装设备端组件
        debug: 是否开启调试日志
        disabled_tools: 禁用的工具列表
        cancel_event: 可选的取消事件，设置后将提前终止
        log_handler: 可选的日志处理器，用于捕获实时日志

    Returns:
        {"success": bool, "reason": str}
    """
    _setup_logging(debug)

    cfg = _build_config(
        device_serial=device_serial,
        platform=platform,
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        max_steps=max_steps,
        reasoning=reasoning,
        vision_only=vision_only,
        auto_setup=auto_setup,
        debug=debug,
        disabled_tools=disabled_tools,
    )

    return await _run_goal_internal(goal, cfg, cancel_event, log_handler)


def run(
    goal: str,
    *,
    device_serial: str = "",
    platform: str = "android",
    provider: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    max_steps: int = 25,
    reasoning: bool = False,
    vision_only: bool = False,
    auto_setup: bool = False,
    debug: bool = False,
    disabled_tools: Optional[list[str]] = None,
) -> dict:
    """同步执行目标指令（阻塞直到完成）。

    参数与 run_async 相同，返回 dict。

    Example:
        result = run("打开微信", device_serial="AK3SBB5530100840")
        print(result["success"], result["reason"])
    """
    return asyncio.run(run_async(
        goal=goal,
        device_serial=device_serial,
        platform=platform,
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        max_steps=max_steps,
        reasoning=reasoning,
        vision_only=vision_only,
        auto_setup=auto_setup,
        debug=debug,
        disabled_tools=disabled_tools,
    ))


def run_with_cancel(
    goal: str,
    *,
    device_serial: str = "",
    **kwargs,
) -> Tuple[asyncio.Event, asyncio.Task, asyncio.Future]:
    """启动一个可取消的任务。

    Returns:
        (cancel_event, task, result_future)
        - cancel_event: 调用 .set() 取消任务
        - task: asyncio.Task 对象
        - result_future: await 获取最终结果

    Example:
        cancel_event, task, future = run_with_cancel("打开微信", device_serial="...")
        # 需要取消时:
        cancel_event.set()
        result = await future
    """
    cancel_event = asyncio.Event()

    async def _wrapper():
        return await run_async(goal, device_serial=device_serial, cancel_event=cancel_event, **kwargs)

    loop = asyncio.get_event_loop()
    task = loop.create_task(_wrapper())
    return cancel_event, task, task


# ═══════════════════════════════════════════════════════════════
# CLI 入口（保留命令行用法）
# ═══════════════════════════════════════════════════════════════

def main():
    import sys

    args = sys.argv[1:]
    goal = None
    device_serial = ""
    kwargs = {}

    i = 0
    while i < len(args):
        if args[i] == "-d" and i + 1 < len(args):
            device_serial = args[i + 1]
            i += 2
        elif args[i] == "--provider" and i + 1 < len(args):
            kwargs["provider"] = args[i + 1]
            i += 2
        elif args[i] == "--model" and i + 1 < len(args):
            kwargs["model"] = args[i + 1]
            i += 2
        elif args[i] == "--base-url" and i + 1 < len(args):
            kwargs["base_url"] = args[i + 1]
            i += 2
        elif args[i] == "--api-key" and i + 1 < len(args):
            kwargs["api_key"] = args[i + 1]
            i += 2
        elif args[i] == "--steps" and i + 1 < len(args):
            kwargs["max_steps"] = int(args[i + 1])
            i += 2
        elif args[i] == "--reasoning":
            kwargs["reasoning"] = True
            i += 1
        elif args[i] == "--vision-only":
            kwargs["vision_only"] = True
            i += 1
        elif args[i] == "--debug":
            kwargs["debug"] = True
            i += 1
        elif goal is None:
            goal = args[i]
            i += 1
        else:
            i += 1

    if not goal or not device_serial:
        print(__doc__)
        sys.exit(1)

    result = run(goal, device_serial=device_serial, **kwargs)
    print(f"\nResult: {'SUCCESS' if result['success'] else 'FAILED'}")
    print(f"Reason: {result['reason']}")
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
