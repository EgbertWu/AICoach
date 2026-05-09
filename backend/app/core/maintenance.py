"""
后台维护任务 (Maintenance Jobs)

设计意图：
    提供轻量的“定时检查/清理”机制，避免异常/过期数据长期累积导致：
    - 刷新检测误判（卡在 in_progress）
    - 幂等表膨胀影响性能

改动原因：
    MVP 阶段没有引入独立的定时任务系统（如 Celery / APScheduler），
    先采用 FastAPI lifespan 内的后台协程实现最小可用的周期清理。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from app.db.models.goal_daily_dispatch import DispatchStatus, GoalDailyDispatch
from app.db.models.task import Task
from app.db.models.task_unique import TaskUnique
from app.db.session import AsyncSessionLocal


async def cleanup_stale_dispatches() -> int:
    """
    清理异常/过期的派发记录。

    改动原因：
        若派发过程中异常中断，GoalDailyDispatch 可能长期停留在 in_progress/failed，
        影响后续“继续任务”的幂等判断与用户体验。
    """
    now = datetime.now()
    stale_in_progress_before = now - timedelta(minutes=30)
    old_failed_before = now - timedelta(days=7)

    async with AsyncSessionLocal() as db:
        stale_rows = await db.execute(
            select(GoalDailyDispatch).where(
                (
                    ((GoalDailyDispatch.status == DispatchStatus.IN_PROGRESS) & (GoalDailyDispatch.created_at < stale_in_progress_before))
                    | ((GoalDailyDispatch.status == DispatchStatus.FAILED) & (GoalDailyDispatch.created_at < old_failed_before))
                )
            )
        )
        rows = stale_rows.scalars().all()
        if not rows:
            return 0

        await db.execute(
            delete(GoalDailyDispatch).where(GoalDailyDispatch.id.in_([r.id for r in rows]))
        )
        await db.commit()
        return len(rows)


async def maintenance_loop(stop_event: asyncio.Event) -> None:
    """
    后台维护循环。

    改动原因：
        提供“定时检查机制”的最小实现：周期清理派发幂等表中的异常记录。
    """
    while not stop_event.is_set():
        try:
            await cleanup_stale_dispatches()
        except Exception:
            pass

        try:
            await cleanup_orphan_task_uniques()
        except Exception:
            pass

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=6 * 60 * 60)
        except asyncio.TimeoutError:
            continue


async def cleanup_orphan_task_uniques() -> int:
    """
    清理孤儿 task_uniques（其 task_id 在 tasks 表中已不存在）。

    改动原因：
        SQLite 在外键未启用或历史数据遗留情况下，可能出现 task_uniques 残留，
        从而触发 “UNIQUE constraint failed: task_uniques.task_id” 等错误。
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TaskUnique.id).where(~TaskUnique.task_id.in_(select(Task.id)))
        )
        ids = [int(x) for x in result.scalars().all()]
        if not ids:
            return 0
        await db.execute(delete(TaskUnique).where(TaskUnique.id.in_(ids)))
        await db.commit()
        return len(ids)
