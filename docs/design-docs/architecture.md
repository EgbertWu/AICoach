# 技术架构设计 (Architecture)

本架构设计基于 Harness Engineering 中**“面向智能体可读性 (Agent Readability)”**的原则构建。优先选择清晰、主流、稳定的技术栈，避免增加 Agent 编写代码的推理成本。

## 1. 核心技术栈 (Tech Stack)

### Frontend (前端)
- **框架**: React + Vite
- **UI 组件**: (待定，建议使用 Tailwind CSS + 常见组件库如 shadcn/ui，便于 AI 生成一致的样式)
- *MVP 对齐*: 只需实现简单的对话框、任务卡片展示和打勾功能，无需复杂路由。

### Backend (后端)
- **框架**: FastAPI (Python)
- **包管理与虚拟环境**: uv (提升环境初始化速度，强制使用虚拟环境隔离依赖)
- *MVP 对齐*: Python 是处理 LLM 逻辑最成熟的语言，FastAPI 的自动 OpenAPI 文档对前端 Agent 生成接口调用非常有帮助。

### DB (数据库)
- **存储**: SQLite (替代 PostgreSQL)
- *修改原因*: 根据 `docs/concepts/mvp_scope.md`，MVP 阶段**不包含用户系统，先用本地**。因此，使用 SQLite 作为本地单文件数据库足以满足需求，极大降低了环境配置和数据库运维成本。

### LLM (大语言模型)
- **模型**: Deepseek / 本地模型 (如通过 Ollama 部署的 Llama 3)
- **交互方式**: 通过 LangChain 或直接使用官方 SDK。
- *安全约束*: 所有传入 LLM 的数据必须经过清理，符合 MVP 定义的防 Prompt 注入安全红线。

## 2. Agent Layer (智能体分层设计)
系统后端不仅是一个 CRUD 接口，而是包含了驱动业务运转的核心 Agent 层：

- **Planner (规划器)**: 将用户的自然语言长期目标拆解为当日的 3-5 个具体任务。
- **Coach (执行教练)**: (MVP 暂缓主动打扰，主要负责在用户勾选任务时给出反馈)。
- **Review (复盘器)**: 晚间对完成率进行评价，并对未完成任务给出指导。

## 3. 接口规范意图 (Harness Alignment)
- 前后端的数据交互必须遵循预先定义的结构（见后续的 `api_spec.yml`）。
- 任何通过 LLM 生成的内容必须经过 `Rule-based Linter` 验证其格式（如 JSON）后才能落库或传给前端。