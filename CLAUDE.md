# Mobilerun - Claude Code 项目指令

## 项目概述

这是一个通过自然语言控制 Android 设备的 Agent 系统（Mobilerun）。

## ⚠️ 重要：进入项目时必须做的事

**每次进入此项目时，必须先读取 `ARCHITECTURE.md` 文件来了解项目架构。**

该文档包含：
- 完整的项目架构说明
- Supervisor 多 Agent 架构详解
- 目录结构和核心模块说明
- API 接口文档
- 测试方法和验证清单
- 关键文件速查表

## 技术栈

- **后端**：Python 3.12, FastAPI, LangGraph
- **前端**：Next.js 14, React, Tailwind CSS
- **LLM**：Qwen3.7-plus（阿里云 DashScope）
- **向量数据库**：ChromaDB（RAG 智能问答）
- **设备连接**：ADB + Portal（Android 无障碍服务）

## 核心功能

1. **自然语言控制 Android 设备**
2. **Supervisor 多 Agent 架构**（Device/ChatBot/Query/Schedule/RAG Agent）
3. **聊天 Bot 自动回复**（微信/WhatsApp）
4. **RAG 智能问答**（多语言政策文档问答）
5. **定时任务调度**（cron 表达式）
6. **多设备并行执行**
7. **实时日志推送**（WebSocket）

## 开发规范

- 修改代码前先阅读相关模块的架构说明
- 添加新 Agent 需实现 `BaseAgent` 接口
- 新增 API 路由放在 `server/api/` 目录
- 前端页面放在 `web/src/app/` 对应目录
- 数据模型修改需同步更新 `server/db.py` 的迁移逻辑
