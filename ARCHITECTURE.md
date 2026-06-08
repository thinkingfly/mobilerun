# Mobilerun — 项目架构文档

## 一、项目概述

Mobilerun 是一个通过自然语言控制 Android 设备的 Agent 系统。用户可以在对话界面发送指令（如"打开微信"、"截屏"、"滑动"等），系统会解析意图、选择设备、调度 Agent 执行操作，并实时推送执行日志。

**核心能力**：
- 自然语言对话控制 Android 设备
- 5 种意图识别：设备操作、状态查询、任务管理、Agent 管理、普通聊天
- 双执行模式：FastAgent（直接执行） / Manager+Executor（推理规划）
- 纯视觉模式（vision_only）：截图 + LLM 视觉识别，可操作微信/支付宝等安全 App
- 自动 vision_only 检测：根据关键词自动切换模式
- 实时日志流（WebSocket）：前端可看到每步执行情况
- 设备自动发现（ADB 扫描）
- 持久化存储（SQLite）：任务、Agent、对话历史、LangGraph 检查点

## 二、技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.12, FastAPI, uvicorn |
| Agent 框架 | LangGraph（对话理解 + 设备管理） |
| LLM | Qwen3.6-plus（阿里云 DashScope） |
| 设备连接 | ADB + Portal（Android 无障碍服务） |
| 前端 | Next.js 14, React, Tailwind CSS |
| 实时通信 | WebSocket（日志推送） |
| 持久化 | SQLite（任务/Agent/对话/LangGraph checkpoint） |

## 三、目录结构

```
mobilerun/
├── mobilerun/                    # 核心 Agent 库
│   ├── agent/
│   │   ├── droid/               # MobileAgent — 设备操作编排
│   │   │   ├── droid_agent.py   # MobileAgent 类（核心执行引擎）
│   │   │   └── events.py        # 事件定义
│   │   ├── fast_agent/          # FastAgent（直接执行模式）
│   │   ├── manager/             # ManagerAgent（规划层）
│   │   ├── executor/            # ExecutorAgent（执行层）
│   │   └── common/              # 公共事件/工具
│   └── config_manager/          # 配置加载器
├── server/                       # FastAPI 后端
│   ├── main.py                  # 启动入口
│   ├── app.py                   # FastAPI 应用创建
│   ├── models.py                # Pydantic 数据模型
│   ├── state.py                 # 全局状态（内存 + WebSocket 订阅）
│   ├── storage.py               # 存储接口（SQLite 包装）
│   ├── db.py                    # SQLite 操作（建表 + CRUD + 迁移）
│   ├── api/                     # REST API 路由
│   │   ├── chat.py              # 对话接口 + LangGraph 处理
│   │   ├── tasks.py             # 任务 CRUD + 执行
│   │   ├── agents.py            # Agent CRUD + 记忆管理
│   │   ├── devices.py           # 设备管理 + ADB 扫描
│   │   └── ws.py                # WebSocket 日志流
│   ├── websocket/               # WebSocket 管理
│   │   ├── manager.py           # 连接管理 + 缓冲队列
│   │   └── log_handler.py       # 日志 Handler（推送到 WS）
│   └── langgraph/               # LangGraph Agent
│       ├── dialogue_agent.py    # 对话理解图（意图解析）
│       ├── device_agent.py      # 设备管理图（扫描 + 选择 + 执行）
│       ├── tools.py             # 工具函数（execute_goal + async）
│       └── utils.py             # LLM 调用工具
├── mobilerun_api.py             # 统一 API 入口（run/run_async）
├── data/                        # SQLite 数据库文件
├── web/                         # Next.js 前端
│   └── src/
│       ├── app/
│       │   ├── page.tsx         # 首页（重定向到聊天）
│       │   ├── chat/page.tsx    # 对话页面（含任务面板）
│       │   ├── tasks/page.tsx   # 任务列表
│       │   ├── tasks/[id]/page.tsx  # 任务详情（实时日志）
│       │   ├── agents/page.tsx  # Agent 管理
│       │   └── devices/page.tsx # 设备管理
│       └── lib/
│           ├── api.ts           # API 客户端
│           └── websocket.ts     # WebSocket 客户端
└── start.sh                     # 一键启动脚本
```

## 四、架构详解

### 4.1 后端请求流程

```
前端 HTTP POST /api/chat
    │
    ▼
chat.py::chat()
    ├── _resolve_agent_id()         # 确定 Agent ID
    ├── process_message()           # LangGraph 对话理解
    │   └── dialogue_agent.graph.invoke()
    │       ├── parse_intent        # LLM 解析意图
    │       ├── resolve_device      # 选择设备
    │       └── route_intent        # 路由到处理节点
    │           ├── operate_device  → handle_operate → execute_goal 工具
    │           ├── query_status    → handle_query
    │           ├── manage_task     → handle_manage_task（list/cancel/status）
    │           ├── manage_agent    → handle_manage
    │           └── chat            → handle_chat
    │
    ├── storage.append_message()    # 持久化用户消息
    │
    └── 如果 should_create_task:
        ├── asyncio.create_task(execute_goal_async())  # 异步执行
        └── 返回 task_id + response
```

### 4.2 任务执行流程

```
execute_goal_async()
    │
    ├── WebSocketLogHandler(task_id)     # 创建日志处理器
    ├── state.get_cancel_event(task_id)  # 获取取消事件
    │
    ├── run_async()                      # mobilerun_api.py
    │   ├── ConfigLoader.load()          # 加载配置
    │   ├── config.agent.reasoning = cfg.reasoning      # False = FastAgent
    │   ├── config.agent.vision_only = cfg.vision_only  # True = 纯视觉
    │   ├── config.agent.manager.vision = cfg.vision_only
    │   ├── config.agent.executor.vision = cfg.vision_only
    │   ├── config.agent.fast_agent.vision = cfg.vision_only
    │   │
    │   └── droid_agent.run().stream_events()
    │       │
    │       ├── reasoning=False → FastAgent 直接执行
    │       ├── reasoning=True  → ManagerAgent 规划 + ExecutorAgent 执行
    │       │
    │       └── 每个事件 → _extract_log_entry() → log_handler.emit()
    │
    ├── 更新任务状态（completed/failed/cancelled）
    └── 清理状态（device busy, agent status）
```

### 4.3 日志流架构

```
mobilerun events → _extract_log_entry() → WebSocketLogHandler.emit()
                                               │
                                               ▼
                                    ws_manager.send_log(task_id, entry)
                                               │
                                    ┌──────────┴──────────┐
                                    ▼                     ▼
                              活跃 WS 连接          缓冲队列
                            (实时推送)          (连接后发送)
                                    │                     │
                                    ▼                     ▼
                              前端 websocket.ts → React state → 渲染
```

**日志格式**（自定义）：
```
🚀 Starting: {goal}
🤖 Agent mode: direct execution / reasoning (Manager + Executor)
👁️ Vision settings: Manager={bool}, Executor={bool}, FastAgent={bool}
🚀 Running MobileAgent to achieve goal: {goal}
🔄 Step {N}/{max_steps}        # 每轮执行计数
FastAgent response：
📸 Taking screenshot...
🧠 Thinking: {preview}
💻 Executing action code
⚡ Executing tool calls...
⚡ Action result: {preview}
🎉 Goal achieved: {reason} / ❌ Goal failed: {reason}
```

### 4.4 对话理解 — LangGraph 图结构

```
Entry → parse_intent (LLM) → resolve_device → route_intent (conditional)
                                                   │
                     ┌──────────┬─────────┬───────┼───────┐
                     ▼          ▼         ▼       ▼       ▼
                  operate    query    manage  manage_task  chat
                     │          │         │       │         │
                     ▼          ▼         ▼       ▼         ▼
                  handle_    handle_   handle_ handle_     handle_
                  operate    query     manage  manage_task chat
                     │          │         │       │         │
                     └──────────┴─────────┴───────┴─────────┘
                                          │
                                          ▼
                                         END
```

**意图类型**：

| 意图 | 触发场景 | 处理节点 |
|------|---------|---------|
| `operate_device` | 要求在某台设备上执行操作 | handle_operate → execute_goal |
| `query_status` | 查询设备/任务统计 | handle_query |
| `manage_task` | 任务管理（列表/取消/状态） | handle_manage_task |
| `manage_agent` | 创建/删除 Agent | handle_manage |
| `chat` | 普通对话聊天 | handle_chat（LLM 回复） |

### 4.5 自动 vision_only 检测

`_auto_vision_only(text)` 函数根据关键词自动判断是否需要纯视觉模式：

**自动设为 True 的关键词**：
- 安全类 App：微信、支付宝、银行、钉钉、企业微信、QQ、美团、饿了么、淘宝、京东
- 屏幕读取：群名、群名称、聊天、消息、文字、内容、看看、截图、截屏

### 4.6 执行模式详解

| 模式 | reasoning | vision_only | 说明 |
|------|-----------|-------------|------|
| **直接执行** | False | False | FastAgent 直接使用 ADB UI 树（无障碍服务），速度快 |
| **纯视觉** | False | True | FastAgent 使用截图 + LLM 视觉识别，可操作安全 App，慢 |
| **推理规划** | True | False | ManagerAgent 规划步骤 + ExecutorAgent 执行，复杂任务适用 |
| **推理+视觉** | True | True | 规划 + 截图视觉识别，最慢但能力最强 |

**关键参数控制**（`mobilerun_api.py`）：
- `reasoning`: 决定是否使用 Manager+Executor 规划层
- `vision_only`: 决定 Agent 使用截图还是 UI 树
- `max_steps`: 最大执行步数（默认 25）
- `config.agent.manager.vision` / `executor.vision` / `fast_agent.vision`: 各 Agent 的视觉模式

### 4.7 持久化存储

**SQLite 数据库** (`data/checkpoints.db`)：

| 表名 | 用途 |
|------|------|
| `checkpoints` | LangGraph 对话检查点（多轮对话状态） |
| `writes` | LangGraph 写入记录 |
| `tasks` | 任务记录（ID/目标/状态/结果/时间） |
| `agents` | Agent 信息（名称/设备/状态） |
| `chat_messages` | 对话历史（Agent 关联） |

**特点**：
- WAL 模式（Write-Ahead Logging）支持并发
- 启动时自动从旧 JSON 文件迁移
- 任务上限 1000 条（自动清理旧的）
- 对话历史支持压缩（compress_chat）

### 4.8 WebSocket 日志流

**连接管理器** (`ConnectionManager`)：
- 按 task_id 分组管理 WebSocket 连接
- **缓冲队列**：连接建立前的日志会被缓冲，连接后自动发送，避免竞态丢失
- 自动清理断开的连接和空缓冲区

**前端 WebSocket 客户端** (`websocket.ts`)：
- 单例 `logWs` 全局实例
- 支持自动重连（3 秒间隔）
- 心跳 ping/pong 机制

## 五、核心 API 接口

### REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/devices` | 获取设备列表（触发 ADB 扫描） |
| GET | `/api/devices/{serial}` | 获取单个设备 |
| POST | `/api/devices` | 手动添加设备 |
| DELETE | `/api/devices/{serial}` | 移除设备 |
| POST | `/api/devices/{serial}/refresh` | 刷新设备状态 |
| GET | `/api/tasks` | 任务列表（支持分页+状态过滤） |
| GET | `/api/tasks/{id}` | 任务详情 |
| POST | `/api/tasks` | 创建并执行任务 |
| POST | `/api/tasks/{id}/cancel` | 取消任务 |
| GET | `/api/agents` | Agent 列表 |
| POST | `/api/agents` | 创建 Agent |
| DELETE | `/api/agents/{id}` | 删除 Agent |
| GET | `/api/agents/{id}/memory` | 获取 Agent 记忆 |
| DELETE | `/api/agents/{id}/memory` | 清空记忆 |
| POST | `/api/agents/{id}/memory/compress` | 压缩记忆 |
| POST | `/api/chat` | 发送对话消息 |
| GET | `/api/chat/{agent_id}/history` | 对话历史 |
| DELETE | `/api/chat/{agent_id}/history` | 清空对话 |
| POST | `/api/chat/{agent_id}/history/compress` | 压缩对话 |
| GET | `/api/stats` | 仪表盘统计 |

### WebSocket

| 路径 | 说明 |
|------|------|
| `/api/ws/logs/{task_id}` | 订阅任务实时日志 |
| `/api/ws/logs/{task_id}/stream` | 简化版日志流（只推送） |

## 六、测试方法

### 6.1 启动服务

```bash
# 一键启动（前端 + 后端）
./start.sh

# 指定端口
./start.sh --port 9000

# 只启动后端
./start.sh --no-web

# 开发模式（debug）
./start.sh --debug
```

### 6.2 功能测试

#### A. 对话功能测试
```bash
# 发送对话消息
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "打开微信，返回群名称", "agent_id": "default"}'

# 预期返回：
# {
#   "response": "已创建任务...",
#   "intent": "operate_device",
#   "goal": "打开微信，返回群名称",
#   "device_serial": "...",
#   "vision_only": true,
#   "task_id": "...",
#   ...
# }
```

#### B. 意图识别测试
```bash
# 查询状态
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "设备状态", "agent_id": "default"}'
# 预期: intent = query_status, 不涉及设备操作

# 任务列表
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "查看任务列表", "agent_id": "default"}'
# 预期: intent = manage_task, goal = list

# 取消任务
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "取消最新任务", "agent_id": "default"}'
# 预期: intent = manage_task, goal = cancel

# 普通聊天
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "agent_id": "default"}'
# 预期: intent = chat
```

#### C. 任务执行测试
```bash
# 直接创建任务（不经过对话）
curl -X POST http://localhost:8080/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"goal": "打开设置", "device_serial": "AK3SBB5530100840"}'

# 查询任务状态
curl http://localhost:8080/api/tasks/{task_id}

# 取消任务
curl -X POST http://localhost:8080/api/tasks/{task_id}/cancel
```

#### D. WebSocket 日志测试
```python
import asyncio, websockets, json

async def test_logs():
    # 1. 先创建任务获取 task_id
    import requests
    resp = requests.post('http://127.0.0.1:8080/api/chat',
        json={'message': '打开设置', 'agent_id': 'default'})
    result = resp.json()
    task_id = result.get('task_id')

    # 2. 连接 WebSocket 获取日志
    uri = f'ws://127.0.0.1:8080/api/ws/logs/{task_id}'
    async with websockets.connect(uri) as ws:
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=30)
                data = json.loads(msg)
                if data.get('type') != 'ping':
                    print(data.get('msg', data))
            except asyncio.TimeoutError:
                break

asyncio.run(test_logs())
```

#### E. 设备管理测试
```bash
# 设备列表
curl http://localhost:8080/api/devices

# 刷新设备
curl -X POST http://localhost:8080/api/devices/{serial}/refresh

# 统计信息
curl http://localhost:8080/api/stats
```

### 6.3 模式对比测试

| 测试场景 | 参数 | 预期 |
|---------|------|------|
| 打开设置（普通系统操作） | `reasoning=False, vision_only=False` | 快速完成，使用 UI 树 |
| 打开微信（安全 App） | `vision_only=True` | 可完成，使用截图 |
| 打开微信（无 vision_only） | `vision_only=False` | 可能失败（无障碍被禁用） |
| 复杂多步骤任务 | `reasoning=True` | 先规划步骤再执行 |

### 6.4 验证清单

每次迭代后验证以下功能：

- [ ] 对话页面可以发送消息并收到回复
- [ ] 操作设备指令正确创建任务
- [ ] 任务管理意图（list/cancel/status）不操作设备
- [ ] 安全 App 相关指令自动设置 vision_only=true
- [ ] WebSocket 日志实时推送到前端
- [ ] 日志格式正确显示（启动信息、步骤计数、颜色标记）
- [ ] 任务完成后状态正确更新
- [ ] 设备状态正确更新（online/busy/offline）
- [ ] Agent 状态正确更新（idle/working）
- [ ] 对话历史正确保存和加载
- [ ] LangGraph 检查点正确持久化（重启后保留上下文）

## 七、已知限制

1. **max_steps=25**：复杂多步骤任务可能不足（如打开微信→找群→读取聊天记录）
2. **纯视觉模式较慢**：每步都需要截图 + LLM 视觉分析
3. **无法运行时切换模式**：当前不支持 normal ↔ vision 动态切换
4. **安全 App 无障碍限制**：微信等 App 会禁用 Android Accessibility Service
5. **图片截取问题**：部分设备在 vision 模式下截图传输可能截断
6. **LLM 解析不稳定**：意图解析依赖 LLM 返回 JSON，偶有解析失败（有 fallback）

## 八、关键文件速查

| 需求 | 修改文件 |
|------|---------|
| 修改意图识别规则 | `server/langgraph/dialogue_agent.py`（SYSTEM_PROMPT） |
| 添加新意图 | `server/langgraph/dialogue_agent.py`（新增 handle_xxx + 路由） |
| 修改日志格式 | `mobilerun_api.py`（_extract_log_entry + _run_goal_internal） |
| 修改执行参数 | `server/langgraph/tools.py`（execute_goal_async） |
| 修改设备选择逻辑 | `server/langgraph/dialogue_agent.py`（resolve_device） |
| 添加新 API | `server/api/` 新增路由文件 |
| 修改前端页面 | `web/src/app/` 对应页面 |
| 修改数据模型 | `server/models.py` |
| 修改存储逻辑 | `server/db.py` |
