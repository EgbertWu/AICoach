# AICoach（AI 执行力教练）

中文

AI 驱动的个人执行力教练：把“模糊目标”落到“今天就做这几件”的可执行任务上，并基于执行结果生成复盘建议与后续调整。

## 从这里开始

- MVP 范围与成功标准：docs/concepts/mvp_scope.md
- 架构设计：docs/design-docs/architecture.md
- 后端设计：docs/design-docs/backend_design.md
- 前端设计：docs/design-docs/frontend_design.md

## 你能用它做什么

- 生成计划：输入目标（短期/长期），生成带“完成标准”的任务卡片与建议时间窗（可手动调整）
- 看板管理：待办 / 进行中 / 已完成三列，支持拖拽排序与状态切换
- 可控修正：任务支持编辑、AI 重新生成（可带反馈）、超时原因补填
- 复盘闭环：单日复盘 + 周报/月报（按时间范围聚合任务）
- Quiet Hours：默认 23:00–次日 06:00 不建议分配任务时间窗（可作为用户偏好配置）

## 快速开始（3 步跑起来，macOS）

1. 安装并启动后端（需要 Python 3.12+ 与 uv）

```bash
cd backend
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端 OpenAPI：

- <http://localhost:8000/docs>

2. 启动前端

```bash
cd ../frontend
npm install
npm run dev
```

3. 打开 Web UI

- Vite 启动后终端会输出本地地址（通常是 <http://localhost:5173>）

## 配置 LLM

- 后端通过 `backend/.env` 配置 LLM
- 必填：`APP_LLM_API_KEY`
- 可选：`APP_LLM_BASE_URL` / `APP_LLM_MODEL` / `APP_LLM_TEMPERATURE`

## Web UI 截图

- Dashboard：.tmp_dashboard.png

## 运行测试

```bash
cd backend
uv run pytest -q
```

## 配置文件与安全

- 不要把真实 API Key 提交到 Git：`backend/.env` 已加入忽略规则
- 不要提交数据库与虚拟环境：`*.db`、`.venv/`、`node_modules/` 已加入忽略规则

## 架构（极简）

- 前端：React + TypeScript + Vite + Tailwind CSS
- 后端：FastAPI + SQLAlchemy（Async）+ SQLite（aiosqlite）
- AI：DeepSeek（OpenAI SDK 兼容），Agent（Planner / Reviewer / TaskRewriter）
- 包管理：后端 uv；前端 npm
