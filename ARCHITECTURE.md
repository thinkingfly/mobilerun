# Mobilerun — 项目架构文档

## 一、项目概述

Mobilerun 是一个通过自然语言控制 Android 设备的 Agent 系统。用户可以在对话界面发送指令（如"打开微信"、"截屏"、"滑动"等），系统会解析意图、选择设备、调度 Agent 执行操作，并实时推送执行日志。

**核心能力**：
- 自然语言对话控制 Android 设备
- **Supervisor 多 Agent 架构**：协调者 Agent 统一路由到专业 Agent（Device/ChatBot/Query/Schedule/RAG）
- 7 种意图识别：设备操作、状态查询、任务管理、Agent 管理、定时任务、普通聊天、**政策问答（RAG）**
- 双执行模式：FastAgent（直接执行） / Manager+Executor（推理规划）
- 纯视觉模式（vision_only）：截图 + LLM 视觉识别，可操作微信/支付宝等安全 App
- 自动 vision_only 检测：根据关键词自动切换模式
- **多设备执行**：对话时勾选多台设备，同一指令同时下发到所有选中设备
- **聊天 Bot（Chat Bot Agent）**：微信/WhatsApp 自动回复，读取聊天记录 → 生成回复 → 发送
- **RAG 智能问答（RAG Agent）**：上传政策文档 → 向量化存储 → 多语言问答 → 自动翻译，集成到群组自动回复
- **定时任务（Cron）**：自然语言创建定时任务（如"每天早上9点打开微信"），后台自动调度执行
- **任务层级关系**：定时任务不直接执行，触发时创建普通子任务执行，通过 `parent_task` 字段关联
- **定时任务生命周期**：定时任务创建后保持 running 状态，直到被取消；子任务记录每次执行历史
- **聊天验证机制**：涉及聊天/回复的指令自动追加验证步骤，确认在正确的聊天窗口后再发送
- **日志持久化**：任务执行日志同时推送到 WebSocket 和写入 JSONL 文件，支持事后查看
- 实时日志流（WebSocket）：前端可看到每步执行情况
- 设备自动发现（ADB 扫描）
- 持久化存储（SQLite）：任务、Agent、对话历史、定时任务、聊天记录、**RAG 文档/问答历史/群组配置**

## 二、技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.12, FastAPI, uvicorn |
| Agent 框架 | LangGraph（对话理解 + 设备管理） |
| LLM | Qwen3.7-plus（阿里云 DashScope） |
| **Embedding** | **text-embedding-v3（阿里云 Qwen，OpenAI 兼容接口）** |
| **向量数据库** | **ChromaDB（持久化，余弦相似度）** |
| **RAG** | **文档解析（python-docx/PyPDF2）+ 语义切片 + 多语言问答 + 自动翻译** |
| 设备连接 | ADB + Portal（Android 无障碍服务） |
| 前端 | Next.js 14, React, Tailwind CSS |
| 实时通信 | WebSocket（日志推送） |
| 定时调度 | croniter + asyncio（cron 表达式解析 + 调度循环） |
| 持久化 | SQLite（任务/Agent/对话/定时任务/聊天记录/**RAG 文档/问答历史/群组配置**） |

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
│   │   ├── chat.py              # 对话接口 + 多设备执行
│   │   ├── chat_bot.py          # 聊天 Bot API（触发回复/记录查询/统计）
│   │   ├── tasks.py             # 任务 CRUD + 执行 + 子任务查询 + 日志查询
│   │   ├── agents.py            # Agent CRUD + 记忆管理
│   │   ├── devices.py           # 设备管理 + ADB 扫描
│   │   ├── scheduled_tasks.py   # 定时任务 CRUD + cancel + history
│   │   ├── rag.py               # RAG API（文档管理/问答/群组配置）
│   │   └── ws.py                # WebSocket 日志流
│   ├── websocket/               # WebSocket 管理
│   │   ├── manager.py           # 连接管理 + 缓冲队列
│   │   └── log_handler.py       # 日志 Handler（推送到 WS + 持久化到 JSONL）
│   ├── scheduler.py             # 定时任务调度器（asyncio + croniter）
│   ├── rag/                     # RAG 智能问答模块
│   │   ├── __init__.py          # 模块入口
│   │   ├── document_parser.py   # 文档解析（Word/PDF/TXT）
│   │   ├── language_detector.py # 语言检测（langdetect）
│   │   ├── text_splitter.py     # 语义切片（段落分割，保持语义完整）
│   │   ├── embedding.py         # Embedding（阿里云 Qwen text-embedding-v3）
│   │   ├── vectorstore.py       # 向量存储（ChromaDB 持久化）
│   │   ├── retriever.py         # 文档检索（相似度匹配 + 过滤）
│   │   ├── chat_engine.py       # 对话引擎（多语言问答 + LLM 生成 + 翻译）
│   │   └── agent.py             # RAG Agent（Supervisor 模式，政策关键词检测）
│   └── langgraph/               # LangGraph Agent
│       ├── agents/              # 专业 Agent（Supervisor 模式）
│       │   ├── __init__.py      # Agent 包入口（触发注册，RAG 在 app.py 延迟注册）
│       │   ├── base.py          # BaseAgent 基类 + AgentResult + AgentContext
│       │   ├── registry.py      # AgentRegistry 注册表
│       │   ├── device_agent.py  # 设备操作 Agent（通用 App 操作）
│       │   ├── chat_bot_agent.py # 聊天 Bot Agent（微信/WhatsApp 自动回复，集成 RAG）
│       │   ├── query_agent.py   # 状态查询 Agent（设备/任务/Agent 查询）
│       │   └── schedule_agent.py # 定时任务 Agent（cron 调度）
│       ├── dialogue_agent.py    # Supervisor 协调者（意图解析 + Agent 路由，含 rag_question）
│       ├── device_agent.py      # 低级设备执行（ADB 操作，被 agents/device_agent 调用）
│       ├── chat_bot_agent.py    # 聊天 Bot 核心逻辑（打开App/读消息/RAG+LLM回复/发送）
│       ├── chat_bot_config.py   # 聊天 App 配置（注册表/读取模式/关键词检测）
│       ├── chat_bot_prompts.py  # 聊天 Bot 提示词模板
│       ├── tools.py             # 工具函数（execute_goal + async）
│       └── utils.py             # LLM 调用工具（全局配置：LLM_API_KEY/LLM_BASE_URL/LLM_MODEL）
├── mobilerun_api.py             # 统一 API 入口（run/run_async）
├── data/                        # SQLite 数据库文件 + 日志
│   ├── checkpoints.db           # SQLite 数据库
│   ├── chroma_db/               # ChromaDB 向量数据库（RAG）
│   ├── rag_documents/           # 上传的 RAG 原始文档
│   └── task_logs/               # 任务执行日志（JSONL 格式）
│       └── {task_id}.jsonl      # 每个任务一个日志文件
├── web/                         # Next.js 前端
│   └── src/
│       ├── app/
│       │   ├── page.tsx         # 首页（重定向到聊天）
│       │   ├── chat/page.tsx    # 对话页面（含任务面板）
│       │   ├── tasks/page.tsx   # 任务列表（定时任务面板+展开+筛选）
│       │   ├── tasks/[id]/page.tsx  # 任务详情（实时日志+子任务+定时任务详情）
│       │   ├── agents/page.tsx  # Agent 管理
│       │   ├── devices/page.tsx # 设备管理
│       │   └── rag/             # RAG 管理页面
│       │       ├── page.tsx     # 文档管理（列表/上传/删除）
│       │       ├── upload/page.tsx  # 文档上传（文件选择/语言标记/进度）
│       │       └── groups/page.tsx  # 群组配置（CRUD/语言/RAG开关）
│       └── lib/
│           ├── api.ts           # API 客户端（含 ragApi）
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
    ├── await process_message()     # LangGraph Supervisor 处理
    │   └── dialogue_agent.graph.ainvoke()
    │       ├── parse_intent        # LLM 解析意图
    │       ├── resolve_device      # 选择设备（schedule_task 跳过）
    │       ├── select_agent        # Supervisor 通过 AgentRegistry 选择 Agent
    │       └── route_to_agent      # 路由到选中的 Agent
    │           ├── device_agent     → DeviceAgent.execute() → execute_goal
    │           ├── chat_bot_agent   → ChatBotAgent.execute() → execute_chat_bot_task
    │           ├── query_agent      → QueryAgent.execute()（状态/任务查询）
    │           ├── schedule_agent   → ScheduleAgent.execute()（创建定时任务）
    │           └── chat             → handle_chat（LLM 直接回复）
    │
    ├── storage.append_message()    # 持久化用户消息
    │
    ├── 如果 should_create_task:
    │   ├── 确定目标设备列表（前端 device_serials > 解析出的 device）
    │   ├── 为每个设备创建独立任务
    │   ├── asyncio.create_task(execute_goal_async()) × N  # 多设备并行
    │   └── 返回 task_id + all_task_ids + response
    │
    └── 如果是 schedule_task:
        └── 返回确认信息（cron 表达式 + 下次执行时间）
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

### 4.4 Supervisor 多 Agent 架构 — LangGraph 图结构

```
Entry → parse_intent (LLM) → resolve_device → select_agent (AgentRegistry)
                                                      │
                              ┌───────────┬───────────┼───────────┬──────────┬──────────┐
                              ▼           ▼           ▼           ▼          ▼          ▼
                        device_agent  chat_bot    query_agent  schedule    chat      rag_agent
                              │        _agent           │        _agent       │          │
                              │           │             │          │          │          │
                              ▼           ▼             ▼          ▼          ▼          ▼
                         DeviceAgent  ChatBotAgent  QueryAgent  ScheduleAgent handle_chat RagAgent
                         .execute()   .execute()    .execute()  .execute()   (LLM)     .execute()
                              │           │             │          │          │          │
                              └───────────┴─────────────┴──────────┴──────────┴──────────┘
                                                    │
                                                    ▼
                                                   END
```

**Supervisor 路由规则**：

| 意图 | 选中 Agent | Agent 行为 |
|------|-----------|-----------|
| `operate_device`（非聊天类） | `device_agent` | 调用 execute_goal 创建设备操作任务 |
| `operate_device`（微信/WhatsApp + 回复等） | `chat_bot_agent` | 打开App → 进入聊天 → 读取消息 → **RAG 政策回复** → 生成回复 → 发送 |
| `query_status` / `manage_task` / `manage_agent` | `query_agent` | 查询设备状态、任务列表、取消任务等 |
| `schedule_task` | `schedule_agent` | 创建定时任务（解析 cron + 写入 DB） |
| `chat` | 直接处理 | LLM 生成友好回复 |
| `rag_question`（政策/薪资/规则等） | `rag_agent` | 便捷入口：内部客服在对话界面直接查询政策（**非核心场景**） |

> **RAG 核心流程**：不在上表中，而是内嵌在 `chat_bot_agent` 的 `generate_reply()` 中。
> 当群组自动回复检测到政策关键词时，直接调用 `_try_rag_reply()` 使用 RAG 回答，不走 Supervisor 路由。

**Agent 注册表（AgentRegistry）**：
- 所有 Agent 实现 `BaseAgent` 接口：`name` / `description` / `can_handle()` / `execute()`
- 各 Agent 模块导入时自动注册到全局 `registry`
- Supervisor 通过 `registry.find_agent(parsed_intent, message)` 选择第一个匹配的 Agent

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
| `tasks` | 任务记录（ID/目标/状态/类型/结果/时间） |
| `agents` | Agent 信息（名称/设备/状态） |
| `chat_messages` | 对话历史（Agent 关联） |
| `scheduled_tasks` | 定时任务配置（cron 表达式/设备/启用状态） |
| `chat_records` | 聊天记录（从微信/WhatsApp 读取的消息） |
| **`rag_documents`** | **RAG 文档（文件名/路径/解析文本/切片数/语言/状态）** |
| **`rag_chat_history`** | **RAG 问答历史（会话ID/问题/回答/语言/引用文档）** |
| **`chat_groups`** | **群组配置（群名/来源/默认语言/RAG开关）** |

**向量数据库** (`data/chroma_db/`)：

| 集合名 | 用途 | 结构 |
|--------|------|------|
| `rag_documents` | RAG 文档向量存储 | ID: `{doc_id}_{chunk_index}`, embedding, document(切片原文), metadata: {doc_id, filename, language, chunk_index} |

**tasks 表关键字段**：
- `type`: `normal`（普通任务）
- `parent_task`: `"0"`（无父级）或父级定时任务 ID（由定时任务触发创建的子任务）

**任务层级关系**：
```
ScheduledTask (定时任务规则, 存储在 scheduled_tasks 表)
  ├── status 保持 enabled/disabled（不直接有 running 状态）
  ├── 触发时创建 Task (type=normal, parent_task=st.id)
  └── 每次触发创建独立的子任务记录

Task (任务执行记录, 存储在 tasks 表)
  ├── parent_task = "0"    → 用户手动创建的普通任务
  └── parent_task = st.id  → 由定时任务 st 触发创建的子任务
```

**scheduled_tasks 表**：
- `id`: 定时任务 ID
- `goal`: 执行目标
- `device_serials`: JSON 数组（多设备）
- `cron_expression`: cron 表达式（如 `0 9 * * *`）
- `enabled`: 是否启用
- `last_run` / `next_run`: 上次/下次执行时间

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

### 4.9 多设备执行

对话界面支持勾选多台设备，同一指令同时下发到所有选中设备：

```
前端 → POST /api/chat { message, device_serials: ["dev1", "dev2"] }
  │
  ▼
chat.py → process_message() → LangGraph 创建首个任务（dev1）
  │
  ▼
为 device_serials 中的每个额外设备调用 execute_goal() 创建副本任务
  │
  ▼
asyncio.create_task(execute_goal_async()) × N 台设备并行执行
```

**前端设备选择器**（`chat/page.tsx`）：
- 自动加载在线设备列表
- Checkbox 多选，选中高亮
- 发送消息时携带 `device_serials`

### 4.10 定时任务调度

**架构**：

```
用户: "每天早上9点打开微信"
  │
  ▼
LangGraph → schedule_task 意图
  ├── LLM 解析 cron_expression: "0 9 * * *"
  ├── 正则 fallback 检测（LLM 未识别时）
  ├── _enrich_chat_goal() 追加聊天验证步骤
  ├── 获取所有在线设备
  ├── 写入 scheduled_tasks 表
  └── 返回确认（cron + 下次执行时间）

调度器 (scheduler.py):
  └── 每 60 秒检查
      └── 遍历 enabled 的 scheduled_tasks
          └── next_run <= now?
              ├── 为每个 device 创建 Task (type=normal, parent_task=st.id)
              ├── asyncio.create_task(execute_goal_async())
              └── 更新 last_run + 计算 next_run

前端任务管理:
  ├── 定时任务面板：可展开查看执行历史（子任务列表）
  ├── 取消定时任务：禁用 + 停止所有运行中的子任务
  ├── 筛选 Tab：全部 / 运行中 / 运行中定时
  └── 任务详情页：显示 parent_task 关系 + 子任务列表
```

**定时任务取消流程**：
```
POST /api/scheduled-tasks/{id}/cancel
  ├── 设置 enabled = False（停止调度）
  ├── 查找所有 parent_task = st.id 且 status = running 的子任务
  ├── 逐个调用 state.cancel_task()（设置 cancel_event + 标记 cancelled）
  └── 返回 cancelled_children 数量
```

**cron 表达式**（5 位标准格式：分 时 日 月 星期）：
- `"0 9 * * *"` → 每天 9:00
- `"*/30 * * * *"` → 每 30 分钟
- `"30 8 * * 1-5"` → 周一至周五 8:30
- `"0 * * * *"` → 每小时

### 4.11 日志持久化

任务执行日志同时推送到 WebSocket（实时）和写入 JSONL 文件（持久化）：

```
WebSocketLogHandler(task_id)
  ├── emit() 每次被调用时：
  │   ├── 写入 data/task_logs/{task_id}.jsonl（追加模式）
  │   ├── 输出到服务器 logger（方便 tail 查看）
  │   └── 推送到 WebSocket 连接
  └── 日志文件格式：
      {"seq": 1, "msg": "...", "color": "green", "level": 20, "timestamp": "..."}
```

**API 查询**：`GET /api/tasks/{id}/logs` 读取 JSONL 文件返回日志列表。

### 4.12 聊天验证机制

`_enrich_chat_goal(goal)` 对涉及聊天/消息的 goal 自动追加验证步骤：

**触发关键词**：回复、发消息、聊天、发送消息、自动回复、群名、群名称、聊天记录、消息、告诉他、告诉她

**追加内容**：
```
在执行回复操作之前，必须先确认当前所在的聊天窗口是正确的。
请查看屏幕顶部的群名或联系人名称，确认与目标一致后再输入和发送消息。
如果发现不在正确的聊天窗口，不要发送任何消息，直接报告错误。
```

### 4.13 定时任务正则 Fallback

当 LLM 未能正确识别 `schedule_task` 意图时，`_detect_schedule_pattern()` 提供正则 fallback：

```python
_SCHEDULE_PATTERNS = [
    (re.compile(r'每\s*(\d+)\s*分钟'), lambda m: f'*/{m.group(1)} * * * *'),
    (re.compile(r'每\s*(\d+)\s*小时'), lambda m: f'0 */{m.group(1)} * * *'),
    (re.compile(r'每天\s*(\d+)\s*[点时:]'), ...),
    (re.compile(r'每(周|星期)([一二三四五六日天\d])', ...),
    ...
]
```

当 `parse_intent()` 返回 `operate_device` 但消息包含定时模式时，自动修正为 `schedule_task`。

### 4.14 服务重启清理

`AppState._load_from_storage()` 启动时将所有 `status=running` 的 Task 标记为 `failed`：
- 原因：服务重启后 asyncio 协程已丢失，running 状态的任务无法继续
- 定时任务（scheduled_tasks 表）不受影响，仍保持 enabled 状态
- 下次 cron 触发时会自动创建新的子任务

### 4.15 Chat Bot Agent — 聊天软件自动回复

**架构**：

```
用户: "打开微信瞎聊群，查看聊天记录，自动回复"
  │
  ▼
Supervisor → select_agent → chat_bot_agent
  │
  ▼
ChatBotAgent.execute()
  ├── should_use_chat_bot(goal)     # 检测是否匹配聊天App关键词
  ├── parse_target_chat(goal)       # 解析目标聊天对象（"瞎聊群"）
  ├── 创建 Task (type=chat_bot)
  ├── WebSocketLogHandler(task_id)  # 日志处理器
  └── asyncio.create_task(execute_chat_bot_task())
      │
      ├── 步骤1: open_chat_app()           # 打开微信/WhatsApp
      ├── 步骤2: enter_chat_window()       # 进入指定聊天窗口（滑动列表/搜索）
      ├── 步骤3: detect_chat_type()        # 检测单聊/群聊
      ├── 步骤4: read_chat_messages()      # 读取聊天记录（截图OCR/无障碍）
      ├── 步骤5: storage.save_chat_records() # 存入 chat_records 表
      ├── 步骤6: storage.get_chat_history() # 查询历史100条
      ├── 步骤7: generate_reply()          # LLM 生成回复
      └── 步骤8: send_reply()              # 在设备上发送回复
```

**支持的聊天 App**（`chat_bot_config.py`）：

| App | source | 包名 | 读取模式 | 触发关键词 |
|-----|--------|------|---------|-----------|
| 微信 | wechat | com.tencent.mm | screenshot（截图OCR） | 微信/WeChat |
| WhatsApp | whatsapp | com.whatsapp | accessibility（无障碍） | WhatsApp/WA |

**读取模式**：
- `screenshot`：截图 + LLM 视觉识别（适用于微信等屏蔽无障碍的 App）
- `accessibility`：无障碍服务读取 UI 树（更高效，适用于 WhatsApp 等）

**聊天记录表 `chat_records`**：

| 字段 | 类型 | 含义 | 单聊示例 | 群聊示例 |
|------|------|------|----------|----------|
| `source` | TEXT | 数据源标识 | "wechat" | "wechat" |
| `chat_type` | TEXT | 聊天类型 | "single" | "group" |
| `chat_name` | TEXT | **群名或联系人名**（标识这个聊天会话） | "张三" | "瞎聊群" |
| `nick_name` | TEXT | **这条消息的发送者昵称** | "张三" | "李四" |
| `content` | TEXT | 消息内容 | "你好" | "大家好" |
| `is_self` | INTEGER | 是否是本设备 Agent 发送的 | 0/1 | 0/1 |
| `device_id` | TEXT | 设备序列号 | "2MM..." | "2MM..." |
| `device_user` | TEXT | Agent 在该设备上的昵称（默认=设备号） | "小bot-01" | "小bot-01" |
| `created_at` | TEXT | 消息时间 | "2026-06-12T10:30:00" | "2026-06-12T10:30:00" |

**设备用户配置**（`chat_bot_agent.py`）：
```python
DEVICE_USER_MAP = {
    "2MM0223A26010594": "小bot-01",
    "AK3SBB5530100840": "小bot-02",
}
```

### 4.16 Supervisor Agent 接口设计

**BaseAgent 抽象基类**：

```python
class BaseAgent(ABC):
    name: str                    # Agent 唯一标识
    description: str             # 能力描述（供 Supervisor 参考）

    def can_handle(parsed_intent, user_message) -> bool   # 判断能否处理
    async def execute(context: AgentContext) -> AgentResult # 执行任务
```

**AgentContext**：包含 user_message / parsed_intent / device_serial / agent_id / log_handler

**AgentResult**：包含 success / response / task_id / data

### 4.17 RAG 智能问答系统

**整体架构**：

```
用户上传文档（Word/PDF/TXT）
    │
    ▼
document_parser.py         # 解析文档文本
    │
    ▼
language_detector.py       # 检测文档语言（langdetect）
    │
    ▼
text_splitter.py           # 语义切片（~400字/片，50字重叠）
    │
    ▼
embedding.py               # 阿里云 Qwen Embedding（text-embedding-v3）
    │
    ▼
vectorstore.py             # ChromaDB 持久化存储（余弦相似度）
    │
    ▼
用户提问（中/葡/英等）
    │
    ▼
language_detector.py       # 检测问题语言
    │
    ▼
retriever.py               # 相似度检索 top_k=5 相关切片
    │
    ▼
chat_engine.py             # 构建 Prompt → LLM 生成回答（用问题语言）
    │
    ├── 如果回答语言≠中文 → translate_text() 翻译为中文
    │
    ▼
返回 {answer, language, source_docs, translation}
```

**多语言问答语言优先级**：
1. 用户提问语言（自动检测：字符集优先，再 langdetect 辅助）
2. 后台配置的群组默认语言（`chat_groups.default_language`）
3. 文档原文语言

> **支持任意语言**：系统不硬编码语言列表，LLM 能理解 ISO 639-1 语言代码。
> 常用语言（中/英/葡/西/法/德/日/韩等 30+）有预定义名称，其他语言代码直接透传。

**RAG 集成到 Chat Bot Agent**（私聊 + 群聊自动回复）：

```
generate_reply() 收到聊天历史
    │
    ├── 找到最后一条非自己的消息
    │
    ├── _try_rag_reply(message, chat_name, source, chat_type)
    │   ├── is_policy_related(message)    # 检查政策关键词（中/葡/英）
    │   │   └── 不相关 → return None，走普通 LLM 回复
    │   │
    │   ├── 私聊（chat_type="single"）
    │   │   └── rag_enabled 默认 True → 直接调用 RAG
    │   │
    │   ├── 群聊（chat_type="group"）
    │   │   ├── 查询 chat_groups 配置
    │   │   ├── rag_enabled=False → 跳过 RAG
    │   │   └── rag_enabled=True → 继续
    │   │
    │   ├── RagChatEngine.chat(question, session_id=chat_name, ...)
    │   │   ├── 检索相关文档切片
    │   │   ├── LLM 生成回答（问题语言）
    │   │   └── 可选：翻译为中文
    │   │
    │   └── 返回回答（含翻译）或 None（无结果则回退普通 LLM）
    │
    └── 普通 LLM 回复（非政策相关或 RAG 无结果时）
```

> **私聊 vs 群聊**：
> - 私聊：只要消息包含政策关键词，自动触发 RAG（无需额外配置）
> - 群聊：需先在后台配置群组并启用 `rag_enabled`，才触发 RAG

**政策关键词检测**（`server/rag/agent.py`）：
```python
POLICY_KEYWORDS = [
    # 中文：政策/规则/薪资/工资/提现/佣金/奖励/钻石/任务/主播/招聘/培训/级别/等级
    # 葡萄牙语（无重音）：politica/salario/regra/comissao/diamante/saque/bonus/nivel...
    # 葡萄牙语（有重音）：política/salário/regras/comissão/diamantes/bônus/nível...
    # 英语：policy/salary/commission/withdrawal/rule/diamond/bonus/level...
]
```

**RAG Agent（Supervisor 模式，便捷入口）**：
- `name = "rag_agent"`
- `can_handle()`: 意图为 `rag_question`（在对话界面直接问政策问题时触发）
- `execute()`: 调用 `RagChatEngine.chat()` → 返回回答 + 引用来源日志

> **注意**：RAG 的**核心使用场景不是**独立意图，而是集成在 `chat_bot_agent` 的 `generate_reply()` 中。
> 群组自动回复时，检测到政策关键词 → 直接调用 `_try_rag_reply()` → RAG 回答。
> `RagAgent` 只是为内部客服在对话界面直接查询政策提供便捷入口。

**全局 LLM 配置共享**：
RAG 模块与主系统共用同一套 LLM 配置，来自 `server/langgraph/utils.py`：
```python
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://coding.dashscope.aliyuncs.com/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "") or "sk-sp-..."
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3.7-plus")
EMBEDDING_MODEL = "text-embedding-v3"  # Embedding 固定模型
```

**循环导入处理**：
`server/rag/agent.py` 依赖 `server.langgraph.agents.base`，但注册时需要 `registry`。
为避免循环导入，RAG Agent 在 `server/app.py` lifespan 中延迟注册：
```python
# app.py lifespan
from server.rag.agent import RagAgent
from server.langgraph.agents.registry import registry
if "rag_agent" not in registry._agents:
    registry.register(RagAgent())
```

### 4.18 RAG 群组配置

**群组配置表 `chat_groups`**：

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `chat_name` | TEXT | 群名（唯一标识） | "巴西主播群" |
| `source` | TEXT | 来源（wechat/whatsapp） | "wechat" |
| `device_id` | TEXT | 绑定设备（可选） | "2MM..." |
| `default_language` | TEXT | 默认回答语言 | "pt"（葡萄牙语） |
| `rag_enabled` | INTEGER | RAG 是否启用 | 1/0 |

**用途**：
- Agent 监控群组时，根据配置决定是否使用 RAG 回答政策相关问题
- 每个群组可设置默认回答语言，RAG 优先使用该语言生成回答
- 未配置的群组默认启用 RAG，使用自动检测语言

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
| GET | `/api/tasks/{id}/children` | 获取子任务列表 |
| GET | `/api/tasks/{id}/logs` | 获取持久化日志（JSONL） |
| GET | `/api/agents` | Agent 列表 |
| POST | `/api/agents` | 创建 Agent |
| DELETE | `/api/agents/{id}` | 删除 Agent |
| GET | `/api/agents/{id}/memory` | 获取 Agent 记忆 |
| DELETE | `/api/agents/{id}/memory` | 清空记忆 |
| POST | `/api/agents/{id}/memory/compress` | 压缩记忆 |
| POST | `/api/chat` | 发送对话消息（支持多设备） |
| GET | `/api/chat/{agent_id}/history` | 对话历史 |
| DELETE | `/api/chat/{agent_id}/history` | 清空对话 |
| POST | `/api/chat/{agent_id}/history/compress` | 压缩对话 |
| GET | `/api/scheduled-tasks` | 定时任务列表 |
| GET | `/api/scheduled-tasks/{id}` | 定时任务详情 |
| POST | `/api/scheduled-tasks` | 创建定时任务 |
| DELETE | `/api/scheduled-tasks/{id}` | 删除定时任务 |
| POST | `/api/scheduled-tasks/{id}/toggle` | 启用/禁用定时任务 |
| POST | `/api/scheduled-tasks/{id}/cancel` | 取消定时任务（禁用+停止子任务） |
| GET | `/api/scheduled-tasks/{id}/history` | 获取执行历史（子任务列表） |
| GET | `/api/stats` | 仪表盘统计 |
| POST | `/api/chat-bot/reply` | 触发聊天 Bot 回复任务 |
| GET | `/api/chat-bot/records` | 获取聊天记录（支持 source/chat_name/device_id 筛选） |
| GET | `/api/chat-bot/chats` | 获取聊天列表（按聊天名称分组） |
| GET | `/api/chat-bot/stats` | 聊天记录统计 |
| **GET** | **`/api/rag/documents`** | **RAG 文档列表（支持 status 过滤）** |
| **POST** | **`/api/rag/documents/upload`** | **上传文档（multipart：file + language）** |
| **DELETE** | **`/api/rag/documents/{id}`** | **删除文档（从向量库+DB 移除）** |
| **POST** | **`/api/rag/chat`** | **RAG 问答（question/session_id/source/language）** |
| **GET** | **`/api/rag/history`** | **RAG 问答历史（支持 session_id/source 过滤）** |
| **GET** | **`/api/rag/groups`** | **群组配置列表** |
| **POST** | **`/api/rag/groups`** | **添加群组配置** |
| **PUT** | **`/api/rag/groups/{name}`** | **更新群组配置（语言/RAG开关）** |
| **DELETE** | **`/api/rag/groups/{name}`** | **删除群组配置** |

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

#### B. 意图识别测试（Supervisor 路由验证）
```bash
# 查询状态 → query_agent
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "设备状态", "agent_id": "default"}'
# 预期: intent = query_status, 回复包含设备/任务统计

# 任务列表 → query_agent
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "查看任务列表", "agent_id": "default"}'
# 预期: intent = manage_task, goal = list

# 取消任务 → query_agent
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "取消最新任务", "agent_id": "default"}'
# 预期: intent = manage_task, goal = cancel

# 普通聊天 → 直接 LLM 回复
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "agent_id": "default"}'
# 预期: intent = chat

# 设备操作 → device_agent
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "打开设置", "agent_id": "default"}'
# 预期: intent = operate_device, 创建任务

# 微信聊天 Bot → chat_bot_agent
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "打开微信瞎聊群，查看聊天记录，自动回复", "agent_id": "default"}'
# 预期: intent = operate_device, 回复"已启动 微信 聊天 Bot（瞎聊群）..."

# 定时任务 → schedule_agent
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "每5分钟截屏一次", "agent_id": "default"}'
# 预期: intent = schedule_task, 回复包含 cron 和下次执行时间
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

#### F. 多设备执行测试
```bash
# 对话时指定多设备（前端勾选或 API 传入）
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "打开设置",
    "agent_id": "default",
    "device_serials": ["AK3SBB5530100840", "2MM0223A26010594"]
  }'
# 预期: 返回 all_task_ids 包含 2 个任务 ID，两台设备同时执行

# 任务列表确认
curl "http://localhost:8080/api/tasks?page_size=5"
# 预期: 出现两个相同 goal 的任务，device_serial 不同
```

#### G. 定时任务测试
```bash
# 通过对话创建定时任务
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "每天早上9点打开微信", "agent_id": "default"}'
# 预期: intent = schedule_task, 返回 cron 表达式和下次执行时间

# 通过对话创建定时任务（正则 fallback）
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "每5分钟打开微信瞎聊群，查看最近的聊天记录，自动回复相关内容", "agent_id": "default"}'
# 预期: intent = schedule_task（即使 LLM 误判，正则 fallback 也能正确识别）

# 直接 API 创建定时任务
curl -X POST http://localhost:8080/api/scheduled-tasks \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "打开设置",
    "device_serials": ["AK3SBB5530100840"],
    "cron_expression": "*/5 * * * *"
  }'
# 预期: 返回定时任务详情，5 分钟后首次执行

# 查看定时任务列表
curl http://localhost:8080/api/scheduled-tasks

# 启用/禁用定时任务
curl -X POST http://localhost:8080/api/scheduled-tasks/{id}/toggle

# 删除定时任务
curl -X DELETE http://localhost:8080/api/scheduled-tasks/{id}
```

#### H. 任务层级关系测试
```bash
# 等待定时任务触发后，查看子任务
curl "http://localhost:8080/api/scheduled-tasks/{st_id}/history"
# 预期: 返回子任务列表，每个子任务 type=normal, parent_task={st_id}

# 查看子任务详情
curl "http://localhost:8080/api/tasks/{child_task_id}"
# 预期: parent_task 字段为定时任务 ID

# 查看任务的子任务列表
curl "http://localhost:8080/api/tasks/{task_id}/children"
# 预期: 如果该任务有子任务则返回列表，否则返回空

# 取消定时任务（禁用 + 停止所有运行中的子任务）
curl -X POST http://localhost:8080/api/scheduled-tasks/{id}/cancel
# 预期: enabled=false, 所有 running 子任务被取消
```

#### I. 日志持久化测试
```bash
# 任务执行完成后查看持久化日志
curl "http://localhost:8080/api/tasks/{task_id}/logs"
# 预期: 返回日志列表，包含执行过程的所有日志条目

# 日志文件格式验证
# 每条日志包含: seq, msg, color, level, timestamp
```

#### J. Chat Bot 聊天自动回复测试
```bash
# 通过对话触发聊天 Bot（完整流程）
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "打开微信瞎聊群，查看聊天记录，自动回复", "agent_id": "default"}'
# 预期:
# - intent = operate_device
# - response 包含"已启动 微信 聊天 Bot（瞎聊群）"
# - 后台异步执行: 打开微信 → 进入瞎聊群 → 读取消息 → 生成回复 → 发送

# 等待任务完成后查看对话历史
curl http://localhost:8080/api/chat/default/history
# 预期: 包含"✅ 微信自动回复完成：读取了 N 条消息并已发送回复"

# 直接 API 触发聊天 Bot
curl -X POST http://localhost:8080/api/chat-bot/reply \
  -H "Content-Type: application/json" \
  -d '{"source": "wechat", "target_chat": "瞎聊群"}'
# 预期: 返回 task_id + status=running

# 查看聊天记录
curl "http://localhost:8080/api/chat-bot/records?source=wechat&limit=10"
# 预期: 返回聊天记录列表，包含 sender/content/time/is_self

# 查看聊天列表（按聊天名称分组）
curl "http://localhost:8080/api/chat-bot/chats?source=wechat"
# 预期: 返回聊天列表，每个聊天包含 chat_name + message_count

# 查看聊天记录统计
curl "http://localhost:8080/api/chat-bot/stats"
# 预期: 返回 total_records 总数
```

#### K. RAG 智能问答测试
```bash
# ── 文档管理 ──

# 获取文档列表
curl http://localhost:8080/api/rag/documents
# 预期: 返回文档列表，包含 id/filename/language/chunk_count/status

# 上传文档（Word/PDF/TXT）
curl -X POST http://localhost:8080/api/rag/documents/upload \
  -F "file=@policy.pdf" -F "language=auto"
# 预期: 返回 {id, filename, language, chunk_count, message:"文档上传成功"}
# - 文档被解析为文本
# - 文本被语义切片（~400字/片）
# - 每个切片被 Embedding 并存入 ChromaDB
# - 文档元信息存入 rag_documents 表

# 上传文档（手动标记语言）
curl -X POST http://localhost:8080/api/rag/documents/upload \
  -F "file=@policy.docx" -F "language=pt"
# 预期: language="pt"，跳过自动检测

# 删除文档
curl -X DELETE http://localhost:8080/api/rag/documents/{id}
# 预期: 从 ChromaDB 删除对应切片，DB 中标记 status=archived

# ── RAG 问答 ──

# 中文提问（回答用中文）
curl -X POST http://localhost:8080/api/rag/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "薪资怎么算？", "session_id": "test", "source": "web"}'
# 预期:
# - language: "zh"（自动检测为中文）
# - answer: 中文回答（基于检索到的葡萄牙语文档翻译/生成）
# - source_docs: 引用文档列表
# - translation: ""（回答已是中文，无需翻译）

# 葡萄牙语提问（回答用葡萄牙语 + 附中文翻译）
curl -X POST http://localhost:8080/api/rag/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Como funciona o salário?", "session_id": "test", "source": "web", "include_translation": true}'
# 预期:
# - language: "pt"
# - answer: 葡萄牙语回答
# - translation: 对应的中文翻译

# 指定回答语言
curl -X POST http://localhost:8080/api/rag/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "薪资怎么算？", "session_id": "test", "source": "web", "language": "pt"}'
# 预期: language="pt"，强制用葡萄牙语回答

# 查看问答历史
curl "http://localhost:8080/api/rag/history?limit=10"
# 预期: 返回问答历史列表，包含 question/answer/language/source_docs

# ── 群组配置 ──

# 获取群组列表
curl http://localhost:8080/api/rag/groups
# 预期: 返回群组配置列表

# 添加群组配置
curl -X POST http://localhost:8080/api/rag/groups \
  -H "Content-Type: application/json" \
  -d '{"chat_name": "巴西主播群", "source": "wechat", "default_language": "pt", "rag_enabled": true}'
# 预期: 返回 {id, message:"群组配置已添加"}

# 更新群组配置（关闭 RAG）
curl -X PUT "http://localhost:8080/api/rag/groups/巴西主播群?source=wechat" \
  -H "Content-Type: application/json" \
  -d '{"rag_enabled": false}'
# 预期: 该群组自动回复将不再使用 RAG

# 更新群组配置（修改默认语言）
curl -X PUT "http://localhost:8080/api/rag/groups/巴西主播群?source=wechat" \
  -H "Content-Type: application/json" \
  -d '{"default_language": "zh"}'
# 预期: 该群组 RAG 回答将使用中文

# 删除群组配置
curl -X DELETE "http://localhost:8080/api/rag/groups/巴西主播群?source=wechat"
# 预期: 删除配置，未配置的群组默认启用 RAG

# ── RAG 集成到聊天 Bot 测试 ──

# 模拟：群组中有人问政策问题 → chat_bot_agent.generate_reply() 调用 _try_rag_reply()
# 注意：需要群组已配置且 rag_enabled=True

# 通过聊天 Bot 触发（需要设备在线）
curl -X POST http://localhost:8080/api/chat-bot/reply \
  -H "Content-Type: application/json" \
  -d '{"source": "wechat", "target_chat": "巴西主播群"}'
# 预期流程:
# 1. 读取群聊记录
# 2. 最后一条消息是政策相关（如 "薪资怎么算？"）
# 3. _try_rag_reply() 被调用
# 4. 查询 chat_groups 配置 → rag_enabled=True
# 5. RagChatEngine.chat() 生成回答
# 6. 回答包含葡萄牙语原文 + 中文翻译
# 7. 发送到群聊

# 直接调用 _try_rag_reply 验证（单元测试）
# 见 tests/test_rag.py
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

**基础功能**：
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

**Supervisor 多 Agent 路由**：
- [ ] "打开设置" → device_agent
- [ ] "打开微信瞎聊群自动回复" → chat_bot_agent
- [ ] "查看设备状态" / "查看任务列表" → query_agent
- [ ] "每5分钟截屏" → schedule_agent
- [ ] "你好" → chat（LLM 直接回复）
- [ ] AgentRegistry 正确注册所有 Agent
- [ ] process_message 使用 async（graph.ainvoke）

**Chat Bot 聊天自动回复**：
- [ ] 微信聊天记录正确存入 chat_records 表
- [ ] chat_name 正确标识聊天会话（群名/联系人名）
- [ ] nick_name 正确记录每条消息的发送者
- [ ] device_user 正确标识 Agent 身份
- [ ] is_self 正确标记 Agent 发送的消息
- [ ] 聊天 Bot API（records/chats/stats）正常返回
- [ ] 任务完成后对话历史追加结果消息
- [ ] 聊天验证机制在发送前确认窗口正确

**多设备执行**：
- [ ] 对话页面显示设备 checkbox 列表
- [ ] 勾选多台设备发送指令，每台设备创建独立任务
- [ ] 返回结果包含 all_task_ids
- [ ] 任务列表显示多台设备的任务

**定时任务**：
- [ ] 对话"每天早上9点打开微信"创建定时任务成功
- [ ] 对话"每5分钟打开微信..."通过正则 fallback 正确识别为 schedule_task
- [ ] 定时任务列表 API 返回正确数据
- [ ] 启用/禁用定时任务正常切换
- [ ] 删除定时任务正常
- [ ] 调度器到期触发 → 创建 type=normal + parent_task=st.id 的子任务
- [ ] 子任务执行完成后状态正确更新（completed/failed）
- [ ] 取消定时任务：enabled=false + 运行中的子任务被取消
- [ ] 定时任务执行历史 API 返回子任务列表
- [ ] 服务重启后定时任务仍 enabled，子任务被标记 failed

**任务层级关系**：
- [ ] 任务列表页定时任务卡片可展开查看执行历史
- [ ] 任务详情页显示 parent_task 链接（子任务→定时任务）
- [ ] 任务详情页显示子任务列表（父任务→子任务们）
- [ ] 筛选"运行中定时"只显示有运行中子任务的定时任务
- [ ] 定时任务卡片显示"已执行 N 次"和"运行中 M 个"

**日志持久化**：
- [ ] 任务执行日志写入 data/task_logs/{task_id}.jsonl
- [ ] GET /api/tasks/{id}/logs 返回正确的日志列表
- [ ] WebSocket 和文件同时收到日志

**RAG 智能问答**：
- [ ] 上传 Word/PDF/TXT 文档成功，解析+切片+向量化正常
- [ ] 文档列表 API 返回正确数据
- [ ] 删除文档从向量库和 DB 同时清除
- [ ] 中文提问 → 中文回答
- [ ] 葡萄牙语提问 → 葡萄牙语回答 + 中文翻译
- [ ] 指定回答语言参数生效
- [ ] 问答历史正确记录
- [ ] 群组配置 CRUD 正常（添加/更新/删除）
- [ ] 群组 `rag_enabled=False` 时不触发 RAG
- [ ] 私聊政策问题自动触发 RAG（无需配置）
- [ ] 群聊政策问题触发 RAG（需配置 rag_enabled=True）
- [ ] 非政策问题不走 RAG，走普通 LLM 回复
- [ ] RAG 无结果时回退到普通 LLM 回复
- [ ] 政策关键词检测支持中文/葡萄牙语（含重音）/英语
- [ ] RagAgent 在 Supervisor 中正确注册（app.py lifespan）
- [ ] 无循环导入问题

## 七、已知限制

1. **max_steps=25**：复杂多步骤任务可能不足（如打开微信→找群→读取聊天记录）
2. **纯视觉模式较慢**：每步都需要截图 + LLM 视觉分析
3. **无法运行时切换模式**：当前不支持 normal ↔ vision 动态切换
4. **安全 App 无障碍限制**：微信等 App 会禁用 Android Accessibility Service，需要手动重新开启 Portal 权限
5. **图片截取问题**：部分设备在 vision 模式下截图传输可能截断
6. **LLM 解析不稳定**：意图解析依赖 LLM 返回 JSON，偶有解析失败（有正则 fallback）
7. **Event Loop 阻塞**：任务执行（`run_async`）在主事件循环中运行，执行期间 HTTP API 可能无法响应

## 八、关键文件速查

| 需求 | 修改文件 |
|------|---------|
| 修改意图识别规则 | `server/langgraph/dialogue_agent.py`（SYSTEM_PROMPT） |
| 添加新的专业 Agent | `server/langgraph/agents/` 新建文件 + 实现 BaseAgent 接口 |
| 修改 Agent 路由规则 | `server/langgraph/agents/registry.py`（AgentRegistry） |
| 修改设备操作逻辑 | `server/langgraph/agents/device_agent.py`（DeviceAgent） |
| 修改聊天 Bot 逻辑 | `server/langgraph/agents/chat_bot_agent.py`（ChatBotAgent） |
| 修改聊天 App 配置 | `server/langgraph/chat_bot_config.py`（CHAT_APP_REGISTRY） |
| 修改聊天 Bot 提示词 | `server/langgraph/chat_bot_prompts.py` |
| 修改聊天 Bot 核心流程 | `server/langgraph/chat_bot_agent.py`（execute_chat_bot_task） |
| 修改日志格式 | `mobilerun_api.py`（_extract_log_entry + _run_goal_internal） |
| 修改执行参数 | `server/langgraph/tools.py`（execute_goal_async） |
| 修改设备选择逻辑 | `server/langgraph/dialogue_agent.py`（resolve_device） |
| 修改多设备执行 | `server/api/chat.py`（chat 端点） |
| 修改定时调度 | `server/scheduler.py`（TaskScheduler._check_and_run） |
| 修改定时任务 CRUD | `server/api/scheduled_tasks.py`（含 cancel + history） |
| 修改 cron 意图解析 | `server/langgraph/agents/schedule_agent.py`（ScheduleAgent） |
| 修改聊天验证逻辑 | `server/langgraph/agents/device_agent.py`（_enrich_chat_goal） |
| 修改任务层级关系 | `server/models.py`（Task.parent_task）+ `server/db.py`（迁移） |
| 修改子任务查询 | `server/api/tasks.py`（GET /{id}/children）+ `server/storage.py` |
| 修改日志持久化 | `server/websocket/log_handler.py`（WebSocketLogHandler.emit） |
| 修改聊天记录存储 | `server/db.py`（chat_records 表）+ `server/models.py`（ChatRecord） |
| 修改聊天 Bot API | `server/api/chat_bot.py`（reply/records/chats/stats） |
| 修改启动清理逻辑 | `server/state.py`（_load_from_storage） |
| **修改 RAG 文档解析** | **`server/rag/document_parser.py`（parse_word/parse_pdf/parse_txt）** |
| **修改 RAG 文本切片** | **`server/rag/text_splitter.py`（semantic_split）** |
| **修改 RAG Embedding** | **`server/rag/embedding.py`（get_embedding/get_embeddings）** |
| **修改 RAG 向量存储** | **`server/rag/vectorstore.py`（RagVectorStore + ChromaDB）** |
| **修改 RAG 检索逻辑** | **`server/rag/retriever.py`（RagRetriever.retrieve）** |
| **修改 RAG 对话引擎** | **`server/rag/chat_engine.py`（RagChatEngine.chat + translate_text）** |
| **修改 RAG 政策关键词** | **`server/rag/agent.py`（POLICY_KEYWORDS + is_policy_related）** |
| **修改 RAG API** | **`server/api/rag.py`（文档管理/问答/群组配置路由）** |
| **修改聊天 Bot RAG 集成** | **`server/langgraph/chat_bot_agent.py`（_try_rag_reply + generate_reply）** |
| **修改 RAG Agent 注册** | **`server/app.py`（lifespan 延迟注册）** |
| **修改 RAG 意图识别** | **`server/langgraph/dialogue_agent.py`（SYSTEM_PROMPT 增加 rag_question）** |
| **修改 RAG 前端页面** | **`web/src/app/rag/`（文档管理/上传/群组配置页面）** |
| 添加新 API | `server/api/` 新增路由文件 |
| 修改前端页面 | `web/src/app/` 对应页面 |
| 修改数据模型 | `server/models.py` |
| 修改存储逻辑 | `server/db.py` + `server/storage.py` |
