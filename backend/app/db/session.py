"""
数据库连接管理模块 (Database Session Management)

设计意图：
    集中管理 SQLAlchemy 的引擎（Engine）和会话工厂（SessionLocal），
    为整个应用提供统一的数据库访问入口。

    为什么用 async 方式？
    - FastAPI 天然支持 async，使用异步数据库驱动可以避免阻塞事件循环
    - SQLite 通过 aiosqlite 驱动实现异步操作
    - 虽然单用户场景下同步/异步差异不大，但保持 async 风格的一致性
      便于后续扩展（如接入 PostgreSQL）

    为什么把 engine 和 session 分开？
    - engine 是连接池，全局只需一个
    - session 是工作单元，每个请求应该有独立的 session
    - 这符合"请求-响应"的生命周期管理原则
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# 创建异步数据库引擎
# connect_args={"check_same_thread": False} 是 SQLite 特有的配置：
# SQLite 默认不允许跨线程共享连接，但 FastAPI 在处理请求时可能使用不同线程，
# 所以需要关闭这个检查。这在 MVP 本地单用户场景下是安全的。
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,  # debug 模式下打印 SQL 语句，方便调试
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine.sync_engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """
    为 SQLite 连接启用外键约束（含级联删除）。

    改动原因：
        SQLite 默认不启用外键约束，导致 tasks 删除后 task_uniques 等表不会级联清理，
        进而出现 “UNIQUE constraint failed: task_uniques.task_id” 这类问题。
    """
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        pass

# 创建异步会话工厂
# class_=AsyncSession 指定使用异步会话类
# expire_on_commit=False 表示 commit 后不会让已加载的对象过期，
# 这样在 commit 之后仍可访问对象的属性，避免 lazy loading 问题
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
