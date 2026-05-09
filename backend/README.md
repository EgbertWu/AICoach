# AICoach Backend

AICoach MVP 后端服务 — AI 执行力教练。

## 技术栈

- **FastAPI** + **Uvicorn** (ASGI 服务器)
- **SQLite** + **SQLAlchemy** (ORM)
- **Pydantic** (数据验证)
- **uv** (包管理)

## 快速开始

```bash
# 1. 进入后端目录
cd backend

# 2. 使用 uv 初始化并安装依赖
uv sync

# 3. 启动开发服务器
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4. 访问自动生成的 API 文档
# http://localhost:8000/docs
```

## 健康检查

```bash
curl http://localhost:8000/health
```
