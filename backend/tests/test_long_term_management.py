"""
长期任务状态管理测试

改动原因：
    任务状态管理机制涉及“幂等派发 + 取消清理 + 刷新检测”，必须有可回归的测试来保障一致性。
"""

from __future__ import annotations

import json
from datetime import date as date_type

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

from app.api.dependencies import get_current_user, get_db
from app.db.models import Base, GoalType, User, UserGoal
from app.db.models.goal_daily_dispatch import DispatchStatus, GoalDailyDispatch
from app.main import create_app


@pytest_asyncio.fixture()  # type: ignore[union-attr]
async def test_client(monkeypatch: pytest.MonkeyPatch):
    """
    创建带依赖覆盖的测试客户端。

    改动原因：
        端到端验证 FastAPI 路由行为，并使用内存数据库隔离测试数据。
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

    async with SessionLocal() as db:
        user = User(username="test", hashed_password="x" * 60)
        db.add(user)
        await db.commit()
        await db.refresh(user)

        goal = UserGoal(
            user_id=user.id,
            content="软考复习",
            goal_type=GoalType.LONG_TERM,
            roadmap_json=json.dumps({"title": "软考复习", "weeks": [], "start_date": date_type.today().isoformat()}, ensure_ascii=False),
            roadmap_summary="测试路线图",
            target_duration_days=30,
            start_date=date_type.today(),
        )
        db.add(goal)
        await db.commit()
        await db.refresh(goal)

    async def _get_current_user_override():
        async with SessionLocal() as db:
            u = (await db.get(User, 1))
            assert u is not None
            return u

    app = create_app()
    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_current_user] = _get_current_user_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client._test_user_id = 1  # type: ignore[attr-defined]
        client._test_goal_id = 1  # type: ignore[attr-defined]
        client._SessionLocal = SessionLocal  # type: ignore[attr-defined]
        yield client

    await engine.dispose()


@pytest.mark.asyncio
async def test_active_long_term_detects_goal(test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """
    刷新检测：存在长期目标时应返回目标与进度。

    改动原因：
        前端刷新弹窗依赖该接口，必须稳定可用。
    """
    resp = await test_client.get("/api/long-term/active")
    assert resp.status_code == 200
    data = resp.json()
    assert data["goal"]["content"] == "软考复习"
    assert data["progress"]["total"] >= 0
    assert "today_tasks" in data


@pytest.mark.asyncio
async def test_continue_long_term_is_idempotent(test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """
    继续任务：同一天重复调用不会重复生成任务。

    改动原因：
        解决重复生成与状态不一致的关键保障点。
    """
    async def _fake_dispatch_daily_tasks(**_kwargs):
        today = date_type.today().isoformat()
        return [
            {"description": "任务A", "criteria": "完成A", "planned_start_at": f"{today}T09:00:00", "planned_end_at": f"{today}T10:00:00"},
            {"description": "任务B", "criteria": "完成B", "planned_start_at": f"{today}T10:30:00", "planned_end_at": f"{today}T11:30:00"},
            {"description": "任务C", "criteria": "完成C", "planned_start_at": f"{today}T14:00:00", "planned_end_at": f"{today}T15:00:00"},
        ]

    import app.core.long_term as long_term_module

    monkeypatch.setattr(long_term_module, "dispatch_daily_tasks", _fake_dispatch_daily_tasks)

    goal_id = 1
    r1 = await test_client.post(f"/api/long-term/{goal_id}/continue", json={})
    assert r1.status_code == 200
    tasks1 = r1.json()["tasks"]
    assert len(tasks1) == 3

    r2 = await test_client.post(f"/api/long-term/{goal_id}/continue", json={})
    assert r2.status_code == 200
    tasks2 = r2.json()["tasks"]
    assert [t["id"] for t in tasks2] == [t["id"] for t in tasks1]


@pytest.mark.asyncio
async def test_cancel_long_term_clears_pending_tasks(test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """
    取消任务：应清理未完成任务，并使 active 检测变为 404。

    改动原因：
        取消必须是可持久化的状态变化，避免刷新后仍被识别为进行中。
    """
    async def _fake_dispatch_daily_tasks(**_kwargs):
        today = date_type.today().isoformat()
        return [
            {"description": "任务X", "criteria": "完成X", "planned_start_at": f"{today}T09:00:00", "planned_end_at": f"{today}T10:00:00"},
        ]

    import app.core.long_term as long_term_module

    monkeypatch.setattr(long_term_module, "dispatch_daily_tasks", _fake_dispatch_daily_tasks)

    goal_id = 1
    r1 = await test_client.post(f"/api/long-term/{goal_id}/continue", json={})
    assert r1.status_code == 200

    r2 = await test_client.post(f"/api/long-term/{goal_id}/cancel")
    assert r2.status_code == 200
    assert r2.json()["deleted_pending_tasks"] >= 1

    r3 = await test_client.get("/api/long-term/active")
    assert r3.status_code == 404


@pytest.mark.asyncio
async def test_continue_long_term_dispatch_failure_can_retry(test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """
    异常场景：派发失败时应返回清晰错误，并允许用户再次点击“继续任务”重试成功。

    改动原因：
        真实环境下 LLM/网络会失败，系统必须可恢复，避免 dispatch 幂等记录卡死导致永久无法继续。
    """
    async def _fail_dispatch_daily_tasks(**_kwargs):
        raise RuntimeError("LLM down")

    import app.core.long_term as long_term_module

    monkeypatch.setattr(long_term_module, "dispatch_daily_tasks", _fail_dispatch_daily_tasks)

    goal_id = 1
    r1 = await test_client.post(f"/api/long-term/{goal_id}/continue", json={})
    assert r1.status_code == 502
    assert "AI 派发任务失败" in r1.json()["detail"]

    async def _ok_dispatch_daily_tasks(**_kwargs):
        today = date_type.today().isoformat()
        return [
            {"description": "任务A", "criteria": "完成A", "planned_start_at": f"{today}T09:00:00", "planned_end_at": f"{today}T10:00:00"},
        ]

    monkeypatch.setattr(long_term_module, "dispatch_daily_tasks", _ok_dispatch_daily_tasks)

    r2 = await test_client.post(f"/api/long-term/{goal_id}/continue", json={})
    assert r2.status_code == 200
    data = r2.json()
    assert len(data["tasks"]) == 1
    assert data["generated_new"] is True
    assert data["created_count"] == 1


@pytest.mark.asyncio
async def test_continue_long_term_in_progress_returns_clear_message(test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """
    边缘场景：同一天派发记录处于 in_progress 且 tasks 为空时，接口应提示“正在生成中”而不是返回空白。

    改动原因：
        多标签页/重复点击会触发竞态；需要对用户给出明确反馈，避免“无响应/空白”体验。
    """
    SessionLocal = test_client._SessionLocal  # type: ignore[attr-defined]
    goal_id = 1
    today = date_type.today()
    async with SessionLocal() as db:
        row = GoalDailyDispatch(goal_id=goal_id, target_date=today, status=DispatchStatus.IN_PROGRESS)
        db.add(row)
        await db.commit()

    async def _noop_dispatch_daily_tasks(**_kwargs):
        today_str = date_type.today().isoformat()
        return [
            {"description": "任务A", "criteria": "完成A", "planned_start_at": f"{today_str}T09:00:00", "planned_end_at": f"{today_str}T10:00:00"},
        ]

    import app.core.long_term as long_term_module

    monkeypatch.setattr(long_term_module, "dispatch_daily_tasks", _noop_dispatch_daily_tasks)

    r = await test_client.post(f"/api/long-term/{goal_id}/continue", json={})
    assert r.status_code == 502
    assert "正在生成中" in r.json()["detail"]


@pytest.mark.asyncio
async def test_continue_long_term_can_regenerate_if_tasks_deleted_but_dispatch_succeeded(test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """
    边缘场景：如果用户把“今天任务”手动删光，但派发记录已是 succeeded，
    系统应能自修复并允许重新生成，而不是卡在“正在生成中”。

    改动原因：
        用户侧确实存在“清空今天任务后重新生成”的需求，需要保证一致性与可恢复。
    """
    SessionLocal = test_client._SessionLocal  # type: ignore[attr-defined]
    goal_id = 1
    today = date_type.today()
    async with SessionLocal() as db:
        row = GoalDailyDispatch(goal_id=goal_id, target_date=today, status=DispatchStatus.SUCCEEDED)
        db.add(row)
        await db.commit()

    async def _ok_dispatch_daily_tasks(**_kwargs):
        today_str = date_type.today().isoformat()
        return [
            {"description": "任务R", "criteria": "完成R", "planned_start_at": f"{today_str}T09:00:00", "planned_end_at": f"{today_str}T10:00:00"},
        ]

    import app.core.long_term as long_term_module

    monkeypatch.setattr(long_term_module, "dispatch_daily_tasks", _ok_dispatch_daily_tasks)

    r = await test_client.post(f"/api/long-term/{goal_id}/continue", json={})
    assert r.status_code == 200
    data = r.json()
    assert len(data["tasks"]) == 1
    assert data["generated_new"] is True


@pytest.mark.asyncio
async def test_complete_and_uncomplete_persists_after_refresh(test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    async def _fake_dispatch_daily_tasks(**_kwargs):
        today = date_type.today().isoformat()
        return [
            {"description": "任务A", "criteria": "完成A", "planned_start_at": f"{today}T09:00:00", "planned_end_at": f"{today}T10:00:00"},
        ]

    import app.core.long_term as long_term_module

    monkeypatch.setattr(long_term_module, "dispatch_daily_tasks", _fake_dispatch_daily_tasks)

    goal_id = 1
    r1 = await test_client.post(f"/api/long-term/{goal_id}/continue", json={})
    assert r1.status_code == 200
    task_id = r1.json()["tasks"][0]["id"]

    r2 = await test_client.post(f"/api/tasks/{task_id}/complete", json={})
    assert r2.status_code == 200
    assert r2.json()["task"]["status"] == "completed"

    r3 = await test_client.post(f"/api/tasks/{task_id}/uncomplete", json={})
    assert r3.status_code == 200
    assert r3.json()["status"] == "pending"

    r4 = await test_client.get("/api/plans/latest")
    assert r4.status_code == 200
    tasks = r4.json()["tasks"]
    t = next(x for x in tasks if x["id"] == task_id)
    assert t["status"] == "pending"
