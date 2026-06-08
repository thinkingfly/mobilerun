# Mobilerun 项目架构与使用指南

> 版本: 0.6.1 | 许可证: MIT | Python: >=3.11, <3.14

---

## 目录

- [项目概述](#项目概述)
- [架构图](#架构图)
- [核心模块解析](#核心模块解析)
- [CLI 用法](#cli-用法)
- [Python API 用法](#python-api-用法)
- [关键文件索引](#关键文件索引)

---

## 项目概述

Mobilerun 是一个用于通过 LLM Agent 控制 Android 和 iOS 设备的 Python 框架。支持用自然语言自动化移动设备操作——检查 UI 状态、点击、滑动、输入文本、规划多步骤工作流。

- **GitHub**: https://github.com/droidrun/mobilerun
- **核心依赖**: Llama-Index (Workflow)、Pydantic、Click CLI、Textual TUI
- **设备控制**: Android 通过 ADB + Portal APK，iOS 通过 Portal 协议

---

## 架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        用户接口层                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────┐ │
│  │   CLI (Click)│  │  TUI (Textual│  │   Python API               │ │
│  │  mobilerun   │  │   mobilerun  │  │   from mobilerun import    │ │
│  │   run/setup  │  │    tui)      │  │   MobileAgent               │ │
│  └──────┬───────┘  └──────┬───────┘  └────────────┬───────────────┘ │
│         │                 │                        │                 │
│         └─────────────────┼────────────────────────┘                 │
│                           ▼                                          │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              MobileAgent (顶层编排 / Llama-Index Workflow)    │   │
│  │                                                              │   │
│  │   ┌─────────────────────────────────────────────────────┐    │   │
│   │   │          reasoning=True (推理模式)                   │    │   │
│   │   │  ┌──────────────┐         ┌──────────────┐         │    │   │
│   │   │  │ ManagerAgent │◄───────►│ExecutorAgent │         │    │   │
│   │   │  │  (规划/推理)  │  Event  │  (动作执行)   │         │    │   │
│   │   │  └──────────────┘         └──────────────┘         │    │   │
│   │   └─────────────────────────────────────────────────────┘    │   │
│   │   ┌─────────────────────────────────────────────────────┐    │   │
│   │   │         reasoning=False (直接模式)                    │    │   │
│   │   │  ┌──────────────────────────────────────────────┐   │    │   │
│   │   │  │              FastAgent (ReAct + XML)          │   │    │   │
│   │   │  └──────────────────────────────────────────────┘   │    │   │
│   │   └─────────────────────────────────────────────────────┘    │   │
│   │                                                              │   │
│   │   ┌──────────────┐  ┌──────────────────────┐                │   │
│   │   │ AppStarter   │  │ StructuredOutputAgent│                │   │
│   │   │ (打开应用)    │  │ (结构化数据提取)      │                │   │
│   │   └──────────────┘  └──────────────────────┘                │   │
│   └───────────────────────────┬──────────────────────────────────┘   │
│                               ▼                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    ToolRegistry (工具注册中心)                 │   │
│  │   click | click_at | long_press | type_text | system_button  │   │
│  │   swipe | open_app | wait | complete | type_secret | ...     │   │
│   └───────────────────────────┬──────────────────────────────────┘   │
│                               ▼                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Device Drivers (设备驱动层)                  │   │
│   │  ┌────────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────┐   │   │
│   │  │AndroidDriver│ │IOSDriver│ │CloudDriver│ │StealthDriver │   │   │
│   │  │(ADB+Portal) │ │(Portal) │ │(云端)     │ │(拟人化操作)   │   │   │
│   │  └────────────┘ └─────────┘ └──────────┘ └──────────────┘   │   │
│   └───────────────────────────┬──────────────────────────────────┘   │
│                               ▼                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                  UI State Providers (UI 状态)                  │   │
│   │  Screenshot | XML UI Tree | iOS Provider | UI Filters      │   │
│   └───────────────────────────┬──────────────────────────────────┘   │
│                               ▼                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                  物理设备 / 云端                               │   │
│   │  Android Device (Portal APK) | iOS Device | Mobilerun Cloud │   │
│   └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘

           ┌─────────────────────────────────────────┐
           │              横切关注面                    │
           │  ConfigManager | MCP | Telemetry | Macro │
           │  CredentialManager | App Cards | Tracing │
           └─────────────────────────────────────────┘
```

---

## 核心模块解析

### 1. MobileAgent — 顶层编排器
> `mobilerun/agent/droid/droid_agent.py`

基于 Llama-Index Workflow 的顶层协调器。

**两种推理模式：**

| 模式 | 配置 | 说明 |
|------|------|------|
| 推理模式 | `reasoning=True` | ManagerAgent 负责规划和推理，ExecutorAgent 负责执行具体动作，两者通过事件循环交互直到任务完成 |
| 直接模式 | `reasoning=False` | FastAgent 使用 ReAct 循环直接生成 XML 工具调用，适合简单快速的任务 |

**生命周期：**

```
__init__()
  ├── 加载配置 (MobileConfig)
  ├── 初始化 MobileAgentState (共享状态)
  ├── 加载 LLM profiles (manager/executor/fast_agent)
  ├── 初始化 CredentialManager
  ├── 创建子 Agent (ManagerAgent + ExecutorAgent 或 FastAgent)
  └── 设置 Trajectory/Macro recorder

start_handler()  (Workflow 第一步)
  ├── 连接设备驱动 (AndroidDriver / IOSDriver)
  ├── 创建 StateProvider (AndroidStateProvider)
  ├── 构建 ToolRegistry (注册所有可用工具)
  ├── 注册用户自定义工具
  ├── 注册 MCP 工具
  ├── 创建 ActionContext
  └── 触发 FastAgentExecuteEvent 或 ManagerInputEvent

execute_task() / run_manager() / run_executor()
  ├── 根据模式分发到对应 Agent
  ├── Agent 调用工具 → ToolRegistry.execute()
  ├── 结果更新到 shared_state
  └── 直到 complete() 或达到 max_steps
```

**关键属性：**
- `shared_state` — MobileAgentState 实例，所有 Agent 共享
- `registry` — ToolRegistry 实例，所有工具注册于此
- `action_ctx` — ActionContext，工具函数接收的上下文

---

### 2. ManagerAgent — 规划智能体
> `mobilerun/agent/manager/manager_agent.py`

负责理解用户指令、制定计划、拆分子目标、跟踪进度。

```python
# 通过事件与 ExecutorAgent 通信
ManagerInputEvent  →  ManagerAgent 生成计划
ManagerPlanEvent   →  输出计划到 shared_state
ExecutorInputEvent →  下发子目标给 ExecutorAgent
ExecutorResultEvent→  接收执行结果，决定下一步
```

**Prompt 模板**: `mobilerun/config/prompts/manager/system.jinja2`

---

### 3. ExecutorAgent — 执行智能体
> `mobilerun/agent/executor/executor_agent.py`

接收 Manager 的指令，从 ToolRegistry 中选择合适的原子动作并执行。

**Prompt 模板**: `mobilerun/config/prompts/executor/system.jinja2`

---

### 4. FastAgent — 直接 XML 调用智能体
> `mobilerun/agent/fast_agent/fast_agent.py`

不需要规划器，直接通过 ReAct 循环生成 XML 格式的工具调用。

```xml
<!-- LLM 响应格式示例 -->
<think>我需要点击设置按钮</think>
<add_memory>设置按钮的索引是 5</add_memory>
<tool>
  <action>click</action>
  <index>5</index>
</tool>
```

**XML 解析器**: `mobilerun/agent/fast_agent/xml_parser.py`
**Prompt 模板**: `mobilerun/config/prompts/fast_agent/system.jinja2`

---

### 5. ToolRegistry — 工具注册中心
> `mobilerun/agent/tool_registry.py`

所有原子工具的集中注册和分发中心。

```python
class ToolRegistry:
    tools: Dict[str, ToolEntry]

    register(name, fn, params, description, deps)  # 注册工具
    register_from_dict(tools_dict)                  # 批量注册
    disable(tool_names)                             # 禁用工具
    disable_unsupported(capabilities)               # 根据设备能力禁用
    get_signatures(exclude)                         # 获取签名（用于 prompt）
    get_tool_descriptions_xml()                     # XML 格式（FastAgent）
    get_tool_descriptions_text()                    # 文本格式（ExecutorAgent）

    async execute(name, args, ctx, workflow_ctx)    # 分发调用
```

**注册流程** (`mobilerun/agent/utils/signatures.py`):
```
build_tool_registry()
  ├── click, long_press, click_at, click_area, long_press_at
  ├── type, type_text, system_button, swipe, wait
  ├── open_app (或 open_bundle_id for iOS)
  ├── complete
  └── type_secret (仅当 credential_manager 有密钥时)
```

---

### 6. Device Drivers — 设备驱动层
> `mobilerun/tools/driver/`

**DeviceDriver 基类** (`base.py`):
```python
class DeviceDriver:
    platform: str = "Android"
    supported: set[str] = set()
    supported_buttons: set[str] = set()

    async connect()
    async ensure_connected()
    async tap(x, y)
    async swipe(x1, y1, x2, y2, duration_ms)
    async input_text(text, clear, stealth, wpm)
    async press_button(button)
    async drag(x1, y1, x2, y2, duration)
    async start_app(package, activity)
    async install_app(path)
    async get_apps(include_system)
    async list_packages(include_system)
    async screenshot(hide_overlay)
    async get_ui_tree()
    async get_date()
```

**AndroidDriver** (`android.py`): 通过 `async_adbutils.AdbDevice` + `PortalClient` 实现
**IOSDriver** (`ios.py`): 通过 iOS Portal 协议实现
**CloudDriver** (`cloud.py`): 连接 Mobilerun Cloud
**StealthDriver** (`stealth.py`): 拟人化操作（随机延迟）

---

### 7. MobileAgentState — 共享状态
> `mobilerun/agent/droid/state.py`

所有 Agent 共享的 Pydantic 状态模型，核心字段：

```python
class MobileAgentState(BaseModel):
    # 任务上下文
    instruction: str           # 用户指令
    step_number: int           # 当前步骤
    platform: str              # "Android" / "iOS"

    # 设备状态
    formatted_device_state: str  # 文本描述（供 prompt 使用）
    focused_text: str           # 当前输入框焦点文本
    a11y_tree: List[Dict]       # 原始无障碍树
    screenshot: str | bytes     # 当前截图
    width: int; height: int     # 屏幕尺寸

    # 应用追踪
    app_card: str
    current_package_name: str
    visited_packages: set

    # 记忆（append-only 字符串，由 <add_memory> 标签填充）
    agent_memory: str

    # 计划（Manager 设置）
    plan: str
    current_subgoal: str
    answer: str

    # 动作历史
    action_history: List[Dict]
    summary_history: List[str]
    action_outcomes: List[bool]

    # 消息历史（LLM ChatMessage 列表）
    message_history: List[ChatMessage]

    # 完成状态
    finished: bool
    success: Optional[bool]

    # 自定义变量
    custom_variables: Dict

    # 方法
    def append_memory(text)           # 追加记忆
    async def complete(success, reason, message)  # 标记完成
    def queue_user_message(message)   # 注入外部消息
    def update_current_app(package, activity)  # 更新当前应用
```

---

### 8. ActionContext — 工具函数上下文
> `mobilerun/agent/action_context.py`

所有工具函数通过 `ctx` 参数接收的依赖注入包：

```python
class ActionContext:
    driver: DeviceDriver            # 设备驱动（tap, screenshot 等）
    ui: UIState                     # 当前 UI 状态（元素索引、坐标）
    shared_state: MobileAgentState  # 共享状态
    state_provider: StateProvider   # UI 状态提供者
    app_opener_llm: LLM             # 应用打开专用 LLM
    credential_manager: CredentialManager  # 凭据管理
    streaming: bool                 # 是否流式输出
    macro_recorder: MacroRecorder   # 宏录制器
```

---

### 9. ConfigManager — 配置系统
> `mobilerun/config_manager/config_manager.py`

基于 YAML 的数据类配置 schema (`MobileConfig`)：

```python
@dataclass
class MobileConfig:
    agent: AgentConfig               # max_steps, reasoning, streaming, 子 Agent 配置
    llm_profiles: Dict[str, LLMProfile]  # 命名 LLM profiles
    device: DeviceConfig             # serial, platform, use_tcp, auto_setup
    telemetry: TelemetryConfig       # Posthog 开关
    tracing: TracingConfig           # Phoenix / Langfuse
    logging: LoggingConfig           # debug, trajectory 保存
    tools: ToolsConfig               # disabled_tools, stealth
    credentials: CredentialsConfig   # 凭据文件路径
    external_agents: Dict            # 外部 Agent 插件
    mcp: MCPConfig                   # MCP 服务器配置
```

**加载器** (`mobilerun/config_manager/loader.py`):
```
ConfigLoader.load()
  ├── 优先级: 1. config_path 参数 → 2. MOBILERUN_CONFIG env → 3. 用户配置 → 4. 默认
  ├── 用户配置路径: ~/.config/mobilerun/config.yaml (platformdirs)
  ├── 自动迁移 (migrations/v002~v006)
  └── 保存: ConfigLoader.save(config) → 写回用户配置
```

---

### 10. 原子动作列表
> `mobilerun/agent/utils/actions.py`

| 动作 | 参数 | 说明 |
|------|------|------|
| `click` | `index: int` | 通过索引点击 UI 元素 |
| `click_at` | `x, y: int` | 坐标点击 |
| `click_area` | `x1,y1,x2,y2` | 点击区域中心 |
| `long_press` | `index: int` | 长按 UI 元素 |
| `long_press_at` | `x, y` | 坐标长按 |
| `type` | `text, index?, clear?` | 输入文本（可先点击元素） |
| `type_text` | `text, clear?` | 输入到当前焦点 |
| `system_button` | `button: str` | 系统按键 (back/home/enter) |
| `swipe` | `coordinate, coordinate2, duration` | 滑动 |
| `open_app` | `text: str` | 按名称打开应用 |
| `open_bundle_id` | `bundle_id/app_id` | 按包名打开应用 |
| `wait` | `duration: float` | 等待 |
| `complete` | `success, reason/message` | 标记任务完成 |
| `type_secret` | `secret_id, index` | 输入凭据（不暴露值） |

---

## CLI 用法

```bash
# 安装
pip install mobilerun

# 配置 LLM（交互式向导）
mobilerun configure

# 运行自然语言任务
mobilerun run "打开微信，给张三发送'你好'"

# 视觉模式
mobilerun run "..." --vision          # 发送截图给 LLM
mobilerun run "..." --vision-only     # 仅通过截图控制

# 设备管理
mobilerun setup                      # 安装 Portal APK
mobilerun devices                    # 列出设备
mobilerun ping                       # 检查设备就绪
mobilerun connect <serial>           # TCP 连接
mobilerun disconnect <serial>        # 断开 TCP

# 配置
mobilerun configure                  # LLM 配置向导
mobilerun doctor                     # 系统诊断

# TUI
mobilerun tui                        # 启动终端 UI

# 宏
mobilerun macro record               # 录制
mobilerun macro replay               # 回放

# OAuth
mobilerun openai login
mobilerun anthropic login
mobilerun gemini login
```

---

## Python API 用法

### 基础用法

```python
import asyncio
from mobilerun import MobileAgent, MobileConfig

async def main():
    # 方式一：使用配置文件
    config = MobileConfig()  # 自动加载 ~/.config/mobilerun/config.yaml

    agent = MobileAgent(
        goal="打开设置，找到 WLAN 选项",
        config=config,
    )
    result = await agent.run()
    print(result.success, result.reason)

asyncio.run(main())
```

### 直接指定 LLM

```python
import asyncio
from mobilerun import MobileAgent
from mobilerun.agent.utils.llm_loader import load_llm

async def main():
    llm = load_llm(
        provider="GoogleGenAI",
        model="gemini-3.1-flash-lite-preview",
        api_key="your-key",
    )

    agent = MobileAgent(
        goal="截屏并描述当前内容",
        llms=llm,
    )
    result = await agent.run()
    print(result.reason)

asyncio.run(main())
```

### 多 LLM Profile

```python
from mobilerun import MobileConfig, LLMProfile

config = MobileConfig()
config.llm_profiles = {
    "manager": LLMProfile(provider="OpenAI", model="gpt-4o", temperature=0.2),
    "executor": LLMProfile(provider="GoogleGenAI", model="gemini-2.5-flash", temperature=0.1),
    "fast_agent": LLMProfile(provider="GoogleGenAI", model="gemini-3.1-flash-lite-preview"),
}

agent = MobileAgent(goal="复杂任务", config=config)
```

### 直接模式（FastAgent，更快速）

```python
agent = MobileAgent(
    goal="截屏",
    config=config,
    reasoning=False,  # 直接模式
)
```

### 推理模式（Manager + Executor）

```python
agent = MobileAgent(
    goal="打开设置，找到 WLAN，开启并连接网络",
    config=config,
    reasoning=True,  # 推理模式
)
```

### Vision 模式

```python
agent = MobileAgent(
    goal="描述当前屏幕内容",
    config=config,
    vision_only=True,  # 仅截图控制
)
```

### 自定义工具

```python
def calculate_tax(amount: float, rate: float, **kwargs) -> str:
    """Calculate tax for a given amount and rate."""
    tax = amount * rate
    return f"Tax: ${tax:.2f}, Total: ${amount + tax:.2f}"

custom_tools = {
    "calculate_tax": {
        "parameters": {
            "amount": {"type": "number", "required": True},
            "rate": {"type": "number", "required": True},
        },
        "description": "Calculate tax for a given amount and rate",
        "function": calculate_tax,
    }
}

agent = MobileAgent(
    goal="Calculate tax for $100 at 8% rate",
    config=config,
    custom_tools=custom_tools,
)
```

### 带设备访问的自定义工具

```python
async def screenshot_and_count(*, ctx, **kwargs) -> str:
    """Take screenshot and count UI elements."""
    screenshot = await ctx.driver.screenshot()
    ui_state = await ctx.state_provider.get_state()
    element_count = len(ui_state.elements) if ui_state else 0
    return f"Screenshot taken. Found {element_count} UI elements"

custom_tools = {
    "screenshot_and_count": {
        "parameters": {},
        "description": "Take screenshot and count UI elements",
        "function": screenshot_and_count,
    }
}
```

**`ctx` 提供的上下文**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `ctx.driver` | `DeviceDriver` | 设备驱动（截图、tap、swipe 等） |
| `ctx.state_provider` | `StateProvider` | UI 状态获取 |
| `ctx.ui` | `UIState` | 当前 UI 状态（元素索引、坐标） |
| `ctx.shared_state` | `MobileAgentState` | 共享状态（记忆、动作历史、计划等） |
| `ctx.credential_manager` | `CredentialManager` | 凭据管理器（密钥存储） |

### 访问共享状态

```python
async def check_action_history(action_name: str, *, ctx, **kwargs) -> str:
    shared_state = ctx.shared_state

    # 最近 5 个动作
    recent = shared_state.action_history[-5:]
    already_done = any(a.get("action") == action_name for a in recent)

    # 步骤数
    if shared_state.step_number > 10:
        return "Warning: Task taking too many steps"

    # 访问记忆
    if "skip_validation" in shared_state.agent_memory:
        return "Validation skipped per memory"

    return f"Action '{action_name}' {'done' if already_done else 'not done'}"
```

### 自定义变量

```python
agent = MobileAgent(
    goal="使用特定变量执行任务",
    config=config,
    variables={"target_app": "微信", "contact": "张三"},
)
```

### 凭据管理

```python
# 方式一：直接传入字典
agent = MobileAgent(
    goal="登录应用",
    config=config,
    credentials={"MY_PASSWORD": "secret123"},
)

# 方式二：使用配置文件
# config.yaml:
# credentials:
#   enabled: true
#   file_path: "config/credentials.yaml"
#
# credentials.yaml:
# MY_PASSWORD: secret123
```

### 外部 Agent 插件

```python
# external/my_agent/__init__.py
from async_adbutils import AdbDevice

async def run(device: AdbDevice, instruction: str, config: dict, max_steps: int) -> dict:
    # 完全自定义的 Agent，拥有原始 ADB 访问
    xml = await device.dump_hierarchy()
    await device.click(500, 500)
    return {"success": True, "reason": "Done", "steps": 3}
```

配置 `config.yaml`:
```yaml
external_agents:
  my_agent:
    api_key: "sk-..."
    model: "model-name"
```

运行: `mobilerun run "task" --agent my_agent`

### 仅使用 Driver 层（不带 Agent）

```python
import asyncio
from mobilerun.tools import AndroidDriver

async def main():
    driver = AndroidDriver()
    await driver.connect()

    # 截图
    png_bytes = await driver.screenshot()

    # 获取 UI 树
    ui_tree = await driver.get_ui_tree()

    # 操作设备
    await driver.tap(500, 1000)
    await driver.swipe(500, 1500, 500, 500, duration_ms=300)
    await driver.input_text("Hello World")
    await driver.press_button("home")
    await driver.start_app("com.tencent.mm")

    apps = await driver.get_apps()

asyncio.run(main())
```

---

## 关键文件索引

| 文件 | 说明 |
|------|------|
| `mobilerun/__init__.py` | 包入口，导出 MobileAgent, MobileConfig, Drivers |
| `mobilerun/__main__.py` | CLI 入口，调用 `cli.main:cli` |
| `mobilerun/agent/droid/droid_agent.py` | **核心** MobileAgent 编排器 |
| `mobilerun/agent/droid/state.py` | MobileAgentState 共享状态模型 |
| `mobilerun/agent/droid/events.py` | 工作流事件定义 |
| `mobilerun/agent/manager/manager_agent.py` | ManagerAgent 规划智能体 |
| `mobilerun/agent/executor/executor_agent.py` | ExecutorAgent 执行智能体 |
| `mobilerun/agent/fast_agent/fast_agent.py` | FastAgent 直接模式智能体 |
| `mobilerun/agent/fast_agent/xml_parser.py` | XML 工具调用解析器 |
| `mobilerun/agent/tool_registry.py` | 工具注册中心 |
| `mobilerun/agent/action_context.py` | 工具函数上下文依赖注入 |
| `mobilerun/agent/action_result.py` | 工具执行结果数据类 |
| `mobilerun/agent/utils/actions.py` | 原子动作函数实现 |
| `mobilerun/agent/utils/signatures.py` | 标准工具注册构建器 |
| `mobilerun/tools/driver/base.py` | DeviceDriver 基类 |
| `mobilerun/tools/driver/android.py` | AndroidDriver 实现 |
| `mobilerun/tools/driver/ios.py` | IOSDriver 实现 |
| `mobilerun/tools/ui/state.py` | UIState UI 元素解析 |
| `mobilerun/tools/ui/provider.py` | StateProvider / AndroidStateProvider |
| `mobilerun/config_manager/config_manager.py` | MobileConfig 完整配置 schema |
| `mobilerun/config_manager/loader.py` | ConfigLoader YAML 加载与迁移 |
| `mobilerun/cli/main.py` | 所有 CLI 命令定义 |
| `mobilerun/cli/tui/app.py` | TUI 主界面 (Textual) |
| `mobilerun/mcp/adapter.py` | MCP 工具适配 |
| `mobilerun/macro/` | 宏录制与回放 |
| `mobilerun/credential_manager/` | 凭据存储管理 |
| `mobilerun/telemetry/` | 遥测与追踪 |
| `mobilerun/portal.py` | Portal APK 管理 |
| `mobilerun/config_example.yaml` | 完整配置示例 |
| `mobilerun/config/prompts/` | 各 Agent 的 prompt 模板 |

---

## 配置示例

完整 `config.yaml`（`~/.config/mobilerun/config.yaml`）:

```yaml
_version: 6

agent:
  name: "mobilerun"
  max_steps: 15
  reasoning: false          # true = Manager+Executor, false = FastAgent
  streaming: true
  vision_only: false
  fast_agent:
    vision: false
    parallel_tools: true
    system_prompt: "config/prompts/fast_agent/system.jinja2"
  manager:
    vision: false
    system_prompt: "config/prompts/manager/system.jinja2"
  executor:
    vision: false
    system_prompt: "config/prompts/executor/system.jinja2"

llm_profiles:
  manager:
    provider: "GoogleGenAI"
    model: "gemini-3.1-flash-lite-preview"
    temperature: 0.2
  executor:
    provider: "GoogleGenAI"
    model: "gemini-3.1-flash-lite-preview"
    temperature: 0.1
  fast_agent:
    provider: "GoogleGenAI"
    model: "gemini-3.1-flash-lite-preview"
    temperature: 0.2

device:
  serial: ""
  platform: "android"
  use_tcp: false
  auto_setup: true

tools:
  disabled_tools: ["click_at", "click_area", "long_press_at"]
  stealth: false

credentials:
  enabled: false
  file_path: "config/credentials.yaml"

mcp:
  enabled: false
  servers: {}

telemetry:
  enabled: true

tracing:
  enabled: false
  provider: "phoenix"

logging:
  debug: false
  save_trajectory: "none"
  trajectory_path: "trajectories"
```
