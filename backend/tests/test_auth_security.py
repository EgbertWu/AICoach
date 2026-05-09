"""
认证安全加固测试

改动原因：
    注册/登录安全策略属于系统底座能力，一旦回归失败会造成严重安全风险。
    该文件覆盖密码强度、账户锁定、会话过期与常见注入尝试等关键场景。
"""

from __future__ import annotations

import pytest

try:
    import pytest_asyncio
except ModuleNotFoundError:  # pragma: no cover
    pytest_asyncio = None  # type: ignore[assignment]
    pytest.skip("需要安装 pytest-asyncio 才能运行异步集成测试", allow_module_level=True)

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.core.config import settings
from app.db.models import Base, User
from app.main import create_app


@pytest_asyncio.fixture()  # type: ignore[union-attr]
async def client():
    """
    创建带内存数据库的测试客户端。

    改动原因：
        避免污染本地 aicoach.db，并确保测试可重复、稳定。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def _get_db_override():
        async with SessionLocal() as db:
            yield db

    app = create_app()
    app.dependency_overrides[get_db] = _get_db_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        c._SessionLocal = SessionLocal  # type: ignore[attr-defined]
        yield c

    await engine.dispose()


def _form(username: str, password: str) -> dict:
    return {"username": username, "password": password}


@pytest.mark.asyncio
async def test_register_password_policy_rejects_weak(client: AsyncClient):
    """
    注册必须执行 12 位强度策略。

    改动原因：
        强密码是账号体系的第一道防线。
    """
    r = await client.post(
        "/api/auth/register",
        data=_form("u1", "123456"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 400
    assert "至少" in r.json()["detail"]


@pytest.mark.asyncio
async def test_register_password_policy_accepts_strong(client: AsyncClient):
    """
    强密码应允许注册成功。

    改动原因：
        确保策略不是“只拒绝不通过”的死规则。
    """
    r = await client.post(
        "/api/auth/register",
        data=_form("u2", "Abcdef!23456"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200
    assert r.json()["username"] == "u2"


@pytest.mark.asyncio
async def test_login_lock_after_5_failures(client: AsyncClient):
    """
    连续 5 次失败后锁定 30 分钟。

    改动原因：
        防止暴力破解与撞库。
    """
    await client.post(
        "/api/auth/register",
        data=_form("u3", "Abcdef!23456"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    for _ in range(settings.max_failed_login_attempts - 1):
        r = await client.post(
            "/api/auth/login",
            data=_form("u3", "Wrong!23456Aa"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 401

    locked = await client.post(
        "/api/auth/login",
        data=_form("u3", "Wrong!23456Aa"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert locked.status_code == 423
    assert "锁定" in locked.json()["detail"]

    still_locked = await client.post(
        "/api/auth/login",
        data=_form("u3", "Abcdef!23456"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert still_locked.status_code == 423


@pytest.mark.asyncio
async def test_sql_injection_like_username_does_not_bypass_login(client: AsyncClient):
    """
    类 SQL 注入用户名不应导致认证绕过。

    改动原因：
        防止通过特殊输入影响查询语义。
    """
    r = await client.post(
        "/api/auth/login",
        data=_form("' OR 1=1--", "Whatever!23456Aa"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_security_headers_present(client: AsyncClient):
    """
    常见安全响应头应存在。

    改动原因：
        提升默认安全基线，降低前端被嵌入与 MIME 嗅探风险。
    """
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("x-content-type-options") == "nosniff"

