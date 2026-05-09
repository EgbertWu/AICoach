# 后端详细设计文档 (Backend Design)

本节基于 `architecture.md` 进一步细化后端技术栈、目录结构及核心逻辑，以支撑 MVP 阶段的 AI Coach 系统。

## 1. 技术栈选型细化

* **核心框架**: FastAPI (利用其依赖注入和自动 OpenAPI 文档生成特性)
* **语言**: Python 3.12 (提供强大的类型提示)
* **包管理与虚拟环境**: uv (极速的 Python 包管理器，替代 pip/poetry。推荐使用 `uv venv` 和 `uv pip`，或直接使用 `uv run` 以确保依赖隔离)
* **数据验证**: Pydantic (定义严格的数据模式，这是 Harness 中“机械化执行”的基础)
* **数据库**: SQLite (本地单文件存储)
* **ORM**: SQLAlchemy (用于对象关系映射，避免手写 SQL)
* **LLM 交互**: LangChain 或官方 SDK (推荐直接使用 SDK，保持代码透明度，避免过度封装)

## 2. 核心模块与工作流 (Modules & Workflows)

### 2.1 API 层 (Routes)
* `POST /api/plans/generate`: 接收用户当日目标，调用 Planner Agent 生成任务列表。
* `GET /api/tasks/today`: 获取今日已生成的任务列表。
* `PUT /api/tasks/{task_id}/status`: 更新特定任务的完成状态，可能触发 Coach Agent 的微反馈。
* `POST /api/reviews/generate`: 在一天结束时触发，调用 Review Agent 生成复盘报告。

### 2.2 Agent 层 (Agents)
实现业务逻辑的“大脑”，通过精心设计的 Prompt 与 LLM 交互。
* **Planner**: 负责将模糊目标转化为具体的、可执行的、带完成标准的任务。
* **Coach**: 负责在任务状态改变时提供鼓励或建议。
* **Reviewer**: 负责分析任务完成率，提供改进建议。

### 2.3 核心数据模型 (Data Models)
* **UserGoal**: 记录用户的长期目标和每日意图。
* **Task**: 记录单条任务，包含描述、完成标准、状态 (未开始/进行中/已完成)。
  - *新增字段*: `start_time` (计划/实际开始时间), `end_time` (计划/实际结束时间), `duration_seconds` (实际花费秒数，配合前端计时器)。这是实现 Coach 智能干预（如“长时间未执行”、“卡住”）的数据基础。
* **ReviewReport**: 记录每日的复盘结果。

## 3. 目录结构设计 (Directory Structure)

```text
backend/
├── app/
│   ├── api/            # API 路由定义 (FastAPI routers)
│   │   ├── endpoints/  # 具体接口实现
│   │   └── dependencies.py # 依赖注入 (如数据库会话)
│   ├── core/           # 核心配置 (Config, Security, LLM Client 初始化)
│   ├── db/             # 数据库相关
│   │   ├── models/     # SQLAlchemy 模型 (Data layer)
│   │   └── session.py  # 数据库连接管理
│   ├── schemas/        # Pydantic 模型 (Data validation, 与 frontend types 对齐)
│   ├── agents/         # AI 智能体逻辑层
│   │   ├── planner.py  # 规划器逻辑
│   │   ├── coach.py    # 教练逻辑
│   │   ├── reviewer.py # 复盘器逻辑
│   │   └── prompts/    # 具体的 Prompt 模板 (可从 docs/prompts 同步)
│   └── main.py         # FastAPI 应用入口
├── tests/              # 自动化测试用例
└── pyproject.toml      # uv 包管理配置与依赖清单 (替代 requirements.txt)
```

## 4. 关键设计原则 (Design Principles)

* **依赖倒置**: 核心逻辑应尽量减少对具体框架的依赖，便于测试。
* **输入清理 (Security)**: 在 API 层必须对用户输入进行基本校验，防范简单的 Prompt 注入。
* **强类型约束**: 所有从 LLM 返回的数据，必须通过 Pydantic 模型进行强制校验。如果解析失败，抛出特定的异常交由上层处理（自我纠正重试或返回默认信息）。