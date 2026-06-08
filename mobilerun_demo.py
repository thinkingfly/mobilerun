"""
Mobilerun Agent Demo — 通用 Python API 调用示例

功能：
  - 通过纯 Python API 控制 Android/iOS 设备
  - 支持任意 LLM provider（OpenAILike, OpenAI, Anthropic, Ollama 等）
  - 支持 reasoning 模式（Manager 规划 + Executor 执行）
  - 支持 vision_only 纯截图模式（绕过 UI 树不可用的问题）
  - 实时展示中间处理过程

用法：
  # 打开微信
  python mobilerun_demo.py "打开微信" -d AK3SBB5530100840

  # 打开设置并找到 Android 版本号
  python mobilerun_demo.py "找到 Android 版本号" -d AK3SBB5530100840

  # 使用自定义 LLM
  python mobilerun_demo.py "发送消息给张三" -d AK3SBB5530100840 \\
      --provider OpenAILike --model gpt-4o \\
      --base-url https://api.openai.com/v1

  # 不使用 reasoning 模式（FastAgent 直执行）
  python mobilerun_demo.py "截屏" -d AK3SBB5530100840 --no-reasoning
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════════
# 1. LLM 配置 — 通过环境变量或命令行参数设置
# ═══════════════════════════════════════════════════════════════
DEFAULT_LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://coding.dashscope.aliyuncs.com/v1")
DEFAULT_LLM_API_KEY = (
    os.environ.get("LLM_API_KEY", "")
    or os.environ.get("OPENAI_API_KEY", "")
    or "sk-sp-e2a147ef4ed54e7991e184b24913f3a8"
)
DEFAULT_LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "OpenAILike")
DEFAULT_LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3.7-plus")


@dataclass
class DemoConfig:
    """Demo 运行配置。"""
    # 设备
    device_serial: str
    platform: str = "android"

    # LLM
    provider: str = DEFAULT_LLM_PROVIDER
    model: str = DEFAULT_LLM_MODEL
    base_url: str = DEFAULT_LLM_BASE_URL
    api_key: str = DEFAULT_LLM_API_KEY

    # Agent
    max_steps: int = 25
    reasoning: bool = False       # 与 mobilerun run 保持一致（FastAgent 直执行）
    vision_only: bool = False     # 与 mobilerun run 保持一致（使用 UI 树 + 截图）

    # 其他
    auto_setup: bool = False
    debug: bool = False
    disabled_tools: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# 2. 日志设置 — 展示中间处理过程
# ═══════════════════════════════════════════════════════════════

def setup_logging(debug: bool = False):
    """配置日志，与 CLI `mobilerun run` 行为一致。"""
    level = logging.DEBUG if debug else logging.INFO

    # 配置 mobilerun logger（EventHandler 使用的就是这个）
    mobilerun_logger = logging.getLogger("mobilerun")
    mobilerun_logger.setLevel(level)
    mobilerun_logger.handlers.clear()

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(logging.Formatter("%(message)s"))
    mobilerun_logger.addHandler(stream_handler)
    mobilerun_logger.propagate = False

    # 抑制 noisy third-party loggers
    for name in ["httpcore", "httpx", "openai", "llama_index", "urllib3", "websocket"]:
        logging.getLogger(name).setLevel(logging.WARNING)

    return mobilerun_logger


# ═══════════════════════════════════════════════════════════════
# 3. 核心执行逻辑
# ═══════════════════════════════════════════════════════════════

async def run_goal(
    goal: str,
    cfg: DemoConfig,
) -> dict:
    """执行一个目标指令，返回结果字典。

    执行流程与 CLI `mobilerun run` 完全一致：
      1. ConfigLoader.load() 加载默认配置
      2. 应用参数覆盖
      3. load_llm() 加载 LLM
      4. MobileAgent(goal, llms, config)
      5. EventHandler + stream_events() 实时处理
    """
    # ── Imports（延迟导入，确保日志已配置）──
    from mobilerun.agent.droid import MobileAgent
    from mobilerun.agent.utils.llm_picker import load_llm
    from mobilerun.cli.event_handler import EventHandler
    from mobilerun.config_manager.loader import ConfigLoader

    # ── Step 1: 加载配置并应用覆盖 ──
    config = ConfigLoader.load()

    config.device.serial = cfg.device_serial
    config.device.platform = cfg.platform
    config.device.auto_setup = cfg.auto_setup

    config.agent.max_steps = cfg.max_steps
    config.agent.reasoning = cfg.reasoning
    config.agent.vision_only = cfg.vision_only
    config.agent.stream = True

    config.agent.manager.vision = cfg.vision_only
    config.agent.executor.vision = cfg.vision_only
    config.agent.fast_agent.vision = cfg.vision_only

    if cfg.disabled_tools:
        config.tools.disabled_tools = cfg.disabled_tools

    # ── Step 2: 加载 LLM ──
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

    # ── Step 3: 创建 Agent ──
    droid_agent = MobileAgent(
        goal=goal,
        llms=llm,
        config=config,
        timeout=1000,
    )

    # ── Step 4: 运行 ──
    event_handler = EventHandler()

    try:
        handler = droid_agent.run()

        async for event in handler.stream_events():
            event_handler.handle(event)

        result = await handler

    except KeyboardInterrupt:
        return {"success": False, "reason": "Interrupted by user"}

    return {
        "success": getattr(result, "success", False),
        "reason": getattr(result, "reason", "N/A"),
    }


# ═══════════════════════════════════════════════════════════════
# 4. 便捷封装
# ═══════════════════════════════════════════════════════════════

async def run_single(
    goal: str,
    device_serial: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    reasoning: bool = True,
    vision_only: bool = True,
    max_steps: int = 25,
    debug: bool = False,
    disabled_tools: Optional[list[str]] = None,
) -> dict:
    """一行代码调用。

    Example:
        result = await run_single("打开微信", "AK3SBB5530100840")
    """
    setup_logging(debug)

    cfg = DemoConfig(
        device_serial=device_serial,
        provider=provider or DEFAULT_LLM_PROVIDER,
        model=model or DEFAULT_LLM_MODEL,
        base_url=base_url or DEFAULT_LLM_BASE_URL,
        api_key=api_key or DEFAULT_LLM_API_KEY,
        reasoning=reasoning,
        vision_only=vision_only,
        max_steps=max_steps,
        debug=debug,
        disabled_tools=disabled_tools or [],
    )

    return await run_goal(goal, cfg)


# ═══════════════════════════════════════════════════════════════
# 5. CLI 入口
# ═══════════════════════════════════════════════════════════════

def parse_args() -> DemoConfig:
    """简单的手动参数解析（不依赖 argparse，保持轻量）。"""
    args = sys.argv[1:]
    goal = None
    cfg = DemoConfig(device_serial="")

    i = 0
    while i < len(args):
        if args[i] == "-d" and i + 1 < len(args):
            cfg.device_serial = args[i + 1]
            i += 2
        elif args[i] == "--provider" and i + 1 < len(args):
            cfg.provider = args[i + 1]
            i += 2
        elif args[i] == "--model" and i + 1 < len(args):
            cfg.model = args[i + 1]
            i += 2
        elif args[i] == "--base-url" and i + 1 < len(args):
            cfg.base_url = args[i + 1]
            i += 2
        elif args[i] == "--api-key" and i + 1 < len(args):
            cfg.api_key = args[i + 1]
            i += 2
        elif args[i] == "--steps" and i + 1 < len(args):
            cfg.max_steps = int(args[i + 1])
            i += 2
        elif args[i] == "--no-reasoning":
            cfg.reasoning = False
            i += 1
        elif args[i] == "--ui-tree":
            cfg.vision_only = False
            i += 1
        elif args[i] == "--debug":
            cfg.debug = True
            i += 1
        elif args[i] == "--disable-tool" and i + 1 < len(args):
            cfg.disabled_tools.append(args[i + 1])
            i += 2
        elif goal is None:
            goal = args[i]
            i += 1
        else:
            i += 1

    return goal, cfg


def main():
    goal, cfg = parse_args()

    if not goal or not cfg.device_serial:
        print(__doc__)
        sys.exit(1)

    setup_logging(cfg.debug)

    print(f"\n{'=' * 60}")
    print(f"  Goal:     {goal}")
    print(f"  Device:   {cfg.device_serial}")
    print(f"  Model:    {cfg.provider}/{cfg.model}")
    print(f"  Mode:     {'reasoning' if cfg.reasoning else 'fast'} + {'vision_only' if cfg.vision_only else 'ui_tree'}")
    print(f"  Steps:    {cfg.max_steps}")
    print(f"{'=' * 60}\n")

    result = asyncio.run(run_goal(goal, cfg))

    print(f"\n{'=' * 60}")
    print(f"  Result:   {'SUCCESS' if result['success'] else 'FAILED'}")
    print(f"  Reason:   {result['reason']}")
    print(f"{'=' * 60}")

    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
