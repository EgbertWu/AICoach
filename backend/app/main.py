"""
FastAPI 应用入口 (Application Entry Point)

增量升级说明：
    - 新增注册 chat 和 dispatch_more 路由
    改动原因：聊天式计划生成和加餐任务功能需要注册到应用中。
"""

from contextlib import asynccontextmanager
import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.api.endpoints import auth, chat, dispatch_more, health, long_term, plans, preferences, reviews, tasks
from app.core.config import settings
from app.core.maintenance import maintenance_loop
from app.db.models import Base
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理器 (Lifespan Manager)。

    启动时自动创建数据库表（含新增字段），关闭时释放资源。
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print(f"✅ 数据库表已创建/验证完毕 (database: {settings.database_url})")

    import asyncio

    stop_event = asyncio.Event()
    maintenance_task = asyncio.create_task(maintenance_loop(stop_event))

    yield

    stop_event.set()
    try:
        await maintenance_task
    except Exception:
        pass

    await engine.dispose()
    print("🔌 数据库连接已关闭")


def create_app() -> FastAPI:
    """
    应用工厂函数 (Application Factory)。
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    logger = logging.getLogger(__name__)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        兜底异常处理：把未捕获异常统一转换为 JSON，避免前端拿到空白/HTML 导致“只有 500 没提示”。

        改动原因：
            用户反馈“请求失败 500 但没有提示”，多数情况下是后端返回非 JSON 或无 detail，
            前端无法稳定解析并展示。这里保证任何 500 都返回带错误 ID 的 JSON，便于定位。
        """
        error_id = uuid4().hex[:10]
        logger.exception("UnhandledException: error_id=%s path=%s", error_id, request.url.path)
        return JSONResponse(status_code=500, content={"detail": f"服务端内部错误（错误ID: {error_id}）"})

    origins = [o.strip() for o in (settings.cors_allow_origins or "").split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        """
        安全响应头中间件。

        改动原因：
            提升对点击劫持、MIME 嗅探等常见风险的默认防护强度。
        """
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        return response

    # 注册路由
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(plans.router)
    app.include_router(tasks.router)
    app.include_router(reviews.router)
    app.include_router(preferences.router)
    app.include_router(long_term.router)
    # 增量：注册聊天会话路由
    # 改动原因：ChatGPT 风格的对话式计划生成需要独立的路由模块
    app.include_router(chat.router)
    # 增量：注册加餐任务路由
    # 改动原因：dispatch-more 端点挂在 /api/plans 前缀下，但独立模块便于维护
    app.include_router(dispatch_more.router)

    return app


app = create_app()
