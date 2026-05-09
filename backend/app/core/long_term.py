"""
长期任务状态管理核心逻辑 (Long-Term Goal Management)

设计意图：
    为长期计划提供一致的状态追踪、幂等派发、进度汇总能力。
    该模块尽量不耦合 FastAPI 路由，便于单元测试与复用。

改动原因：
    之前长期任务主要依赖“tasks 是否存在”来推断状态，在刷新/并发/异常情况下容易出现：
    - 重复生成（竞态）
    - 状态不一致（部分写入/失败后无恢复）
"""

from __future__ import annotations

import json
import logging
from datetime import date as date_type, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.dispatch_service import dispatch_daily_tasks
from app.core.task_history import record_task_event
from app.core.task_unique import sync_task_unique
from app.db.models.goal_daily_dispatch import DispatchStatus, GoalDailyDispatch
from app.db.models.long_term_state import LongTermGoalState, LongTermGoalStatus
from app.db.models.task import Task, TaskStatus
from app.db.models.task_event import TaskEventSource, TaskEventType
from app.db.models.user import User
from app.db.models.user_goal import UserGoal

logger = logging.getLogger(__name__)


def _summarize_dispatch_error(err: Exception) -> str:
    """
    将派发过程中的异常转换为可读且可操作的提示文案。

    Args:
        err: 派发异常（可能来自 LLM 客户端、网络、格式校验等）

    Returns:
        适合直接展示给用户的错误信息（避免泄露敏感信息）
    """
    raw = str(err or "").strip()

    if "APP_LLM_API_KEY" in raw or "LLM API Key 未配置" in raw:
        return "AI 服务未配置：请在后端 .env 设置 APP_LLM_API_KEY，然后重启后端服务。"

    if "未安装 openai" in raw or "pip install openai" in raw:
        return "AI 依赖缺失：后端未安装 openai 依赖，请在 backend 环境安装 openai 后重启。"

    lowered = raw.lower()
    if "401" in lowered or "unauthorized" in lowered or "invalid api key" in lowered:
        return "AI 服务鉴权失败：请检查 APP_LLM_API_KEY 是否正确，然后重启后端服务。"

    if "timeout" in lowered or "timed out" in lowered:
        return "AI 服务超时：请稍后重试，或检查网络/代理配置。"

    if "connection" in lowered or "network" in lowered or "dns" in lowered:
        return "AI 服务网络异常：请检查网络连接或代理配置后重试。"

    return "AI 服务异常：请稍后重试。"


async def ensure_goal_state(db: AsyncSession, goal: UserGoal) -> LongTermGoalState:
    """
    确保长期目标有状态记录（缺失则创建）。

    改动原因：
        项目无数据库迁移工具，历史数据可能没有 long_term_goal_states 记录。
        通过“懒创建”保证升级后兼容已有长期目标。
    """
    result = await db.execute(select(LongTermGoalState).where(LongTermGoalState.goal_id == goal.id))
    state = result.scalar_one_or_none()
    if state:
        return state

    state = LongTermGoalState(user_id=goal.user_id, goal_id=goal.id, status=LongTermGoalStatus.ACTIVE)
    db.add(state)
    await db.commit()
    await db.refresh(state)
    return state


async def get_active_long_term_goal(db: AsyncSession, user_id: int) -> tuple[UserGoal | None, LongTermGoalState | None]:
    """
    获取用户最新的“进行中”长期目标。

    改动原因：
        页面刷新时需要快速判断是否存在进行中的长期任务，以触发引导弹窗。
    """
    state_result = await db.execute(
        select(UserGoal, LongTermGoalState)
        .join(LongTermGoalState, LongTermGoalState.goal_id == UserGoal.id)
        .where(
            LongTermGoalState.user_id == user_id,
            LongTermGoalState.status == LongTermGoalStatus.ACTIVE,
        )
        .order_by(UserGoal.created_at.desc())
        .limit(1)
    )
    row = state_result.first()
    if row:
        goal, state = row
        return goal, state

    goal_result = await db.execute(
        select(UserGoal)
        .where(UserGoal.user_id == user_id)
        .order_by(UserGoal.created_at.desc())
        .limit(10)
    )
    goals = goal_result.scalars().all()
    for g in goals:
        if getattr(g.goal_type, "value", str(g.goal_type)) != "long_term":
            continue
        state = await ensure_goal_state(db, g)
        if state.status == LongTermGoalStatus.ACTIVE:
            return g, state
    return None, None


async def compute_goal_progress(db: AsyncSession, goal_id: int) -> dict:
    """
    计算长期目标进度汇总。

    改动原因：
        前端需要可视化展示“整体完成情况”，并在刷新弹窗中让用户一眼理解当前进度。
    """
    total_result = await db.execute(select(func.count(Task.id)).where(Task.goal_id == goal_id))
    total = int(total_result.scalar() or 0)
    completed_result = await db.execute(
        select(func.count(Task.id)).where(Task.goal_id == goal_id, Task.status == TaskStatus.COMPLETED)
    )
    completed = int(completed_result.scalar() or 0)
    rate = int(round((completed / total) * 100)) if total > 0 else 0
    return {"total": total, "completed": completed, "completion_rate": rate}


async def _compute_recent_completion_rate(
    db: AsyncSession,
    goal_id: int,
    target_date: date_type,
    days: int = 7,
) -> float:
    """
    计算近期完成率（0-100）。

    改动原因：
        “继续任务”需要基于用户最近完成情况滚动调整派发任务难度/数量。
        该数值用于注入到 Dispatch prompt，提升稳定性。
    """
    start_date = target_date - timedelta(days=days - 1)
    total_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.goal_id == goal_id,
            Task.scheduled_date.is_not(None),
            Task.scheduled_date >= start_date,
            Task.scheduled_date <= target_date,
        )
    )
    total = float(total_result.scalar() or 0)
    if total <= 0:
        return 0.0
    done_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.goal_id == goal_id,
            Task.scheduled_date.is_not(None),
            Task.scheduled_date >= start_date,
            Task.scheduled_date <= target_date,
            Task.status == TaskStatus.COMPLETED,
        )
    )
    done = float(done_result.scalar() or 0)
    return max(0.0, min(100.0, (done / total) * 100.0))


async def ensure_daily_tasks(
    db: AsyncSession,
    goal: UserGoal,
    user: User,
    target_date: date_type,
    user_feedback: str | None = None,
) -> tuple[list[Task], bool, str, bool, int]:
    """
    确保某个长期目标在某一天的任务已生成（幂等）。

    返回：
        (tasks, time_adjusted, adjusted_reason, generated_new, created_count)

    改动原因：
        将“派发 + 落库 + 幂等”封装为一处可复用能力，供刷新弹窗的“继续任务”与自动派发调用。
    """
    started_at = datetime.now()
    goal_id = goal.id
    user_id = user.id
    roadmap_json_text = goal.roadmap_json
    quiet_hours_start = user.quiet_hours_start
    quiet_hours_end = user.quiet_hours_end
    allow_quiet_hours = user.allow_quiet_hours
    state = await ensure_goal_state(db, goal)
    await db.refresh(state)
    if state.status != LongTermGoalStatus.ACTIVE:
        return [], False, "", False, 0
    last_dispatch_date_str = state.last_dispatch_date.isoformat() if state.last_dispatch_date else None

    existing_result = await db.execute(
        select(Task).where(Task.goal_id == goal_id, Task.scheduled_date == target_date).order_by(Task.id)
    )
    existing_tasks = existing_result.scalars().all()
    if existing_tasks:
        logger.info(
            "LongTerm.ensure_daily_tasks: 已存在当天任务，直接返回 goal_id=%d date=%s tasks=%d cost_ms=%d",
            goal_id,
            target_date.isoformat(),
            len(existing_tasks),
            int((datetime.now() - started_at).total_seconds() * 1000),
        )
        return existing_tasks, False, "", False, 0

    dispatch_row: GoalDailyDispatch | None = None
    for attempt in range(2):
        try:
            dispatch_row = GoalDailyDispatch(goal_id=goal_id, target_date=target_date, status=DispatchStatus.IN_PROGRESS)
            db.add(dispatch_row)
            await db.commit()
            await db.refresh(dispatch_row)
            break
        except IntegrityError:
            await db.rollback()
            existing_dispatch_result = await db.execute(
                select(GoalDailyDispatch).where(
                    GoalDailyDispatch.goal_id == goal_id,
                    GoalDailyDispatch.target_date == target_date,
                )
            )
            existing_dispatch = existing_dispatch_result.scalar_one_or_none()
            retry_tasks_result = await db.execute(
                select(Task).where(Task.goal_id == goal_id, Task.scheduled_date == target_date).order_by(Task.id)
            )
            retry_tasks = retry_tasks_result.scalars().all()
            if retry_tasks:
                return retry_tasks, False, "", False, 0

            if attempt == 0 and existing_dispatch and existing_dispatch.status in (
                DispatchStatus.FAILED,
                DispatchStatus.SUCCEEDED,
            ):
                await db.delete(existing_dispatch)
                await db.commit()
                continue

            logger.info(
                "LongTerm.ensure_daily_tasks: 并发派发中 goal_id=%d date=%s",
                goal_id,
                target_date.isoformat(),
            )
            raise RuntimeError("当天任务正在生成中，请稍后重试")

    roadmap_data = json.loads(roadmap_json_text) if roadmap_json_text else {}
    recent_rate = await _compute_recent_completion_rate(db, goal_id, target_date=target_date, days=7)

    completed_result = await db.execute(
        select(Task)
        .where(Task.goal_id == goal_id, Task.status == TaskStatus.COMPLETED)
        .order_by(Task.completed_at.desc(), Task.id.desc())
        .limit(20)
    )
    completed_rows = completed_result.scalars().all()
    completed_context = [
        {
            "description": t.description,
            "scheduled_date": t.scheduled_date.isoformat() if t.scheduled_date else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        }
        for t in completed_rows
    ]

    try:
        task_dicts = await dispatch_daily_tasks(
            roadmap_json=roadmap_data,
            target_date=target_date,
            quiet_hours_start=quiet_hours_start,
            quiet_hours_end=quiet_hours_end,
            allow_quiet_hours=allow_quiet_hours,
            user_feedback=user_feedback,
            recent_completion_rate=recent_rate,
            completed_tasks=completed_context,
            last_dispatch_date=last_dispatch_date_str,
        )
    except Exception as e:
        await db.rollback()
        user_msg = _summarize_dispatch_error(e)
        if dispatch_row:
            dispatch_row.status = DispatchStatus.FAILED
            dispatch_row.error_message = user_msg[:500]
            db.add(dispatch_row)
            await db.commit()
        logger.exception(
            "LongTerm.ensure_daily_tasks: 派发生成失败 goal_id=%d date=%s",
            goal_id,
            target_date.isoformat(),
        )
        raise RuntimeError(f"AI 派发任务失败：{user_msg}") from e

    any_adjusted = False
    reasons: list[str] = []
    saved: list[Task] = []

    try:
        for task_dict in task_dicts:
            planned_start = datetime.fromisoformat(task_dict["planned_start_at"]) if task_dict.get("planned_start_at") else None
            planned_end = datetime.fromisoformat(task_dict["planned_end_at"]) if task_dict.get("planned_end_at") else None

            task = Task(
                goal_id=goal_id,
                description=task_dict["description"],
                criteria=task_dict["criteria"],
                planned_start_at=planned_start,
                planned_end_at=planned_end,
                scheduled_date=target_date,
                status=TaskStatus.PENDING,
            )
            db.add(task)
            await db.flush()

            await sync_task_unique(db, task)

            await record_task_event(
                db=db,
                user_id=user_id,
                goal_id=goal_id,
                task=task,
                event_type=TaskEventType.DISPATCHED,
                source=TaskEventSource.AI,
                payload={"target_date": target_date.isoformat()},
            )

            saved.append(task)

            if task_dict.get("time_adjusted"):
                any_adjusted = True
                if task_dict.get("adjusted_reason"):
                    reasons.append(task_dict["adjusted_reason"])

        if dispatch_row:
            dispatch_row.status = DispatchStatus.SUCCEEDED
            dispatch_row.error_message = None

        state.last_dispatch_date = target_date
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if dispatch_row:
            dispatch_row.status = DispatchStatus.FAILED
            dispatch_row.error_message = "任务去重约束冲突"
            db.add(dispatch_row)
            await db.commit()

        conflict_tasks_result = await db.execute(
            select(Task).where(Task.goal_id == goal_id, Task.scheduled_date == target_date).order_by(Task.id)
        )
        conflict_tasks = conflict_tasks_result.scalars().all()
        if conflict_tasks:
            return conflict_tasks, False, "", False, 0
        raise

    for t in saved:
        await db.refresh(t)

    logger.info(
        "LongTerm.ensure_daily_tasks: 生成成功 goal_id=%d date=%s created=%d adjusted=%s cost_ms=%d",
        goal_id,
        target_date.isoformat(),
        len(saved),
        any_adjusted,
        int((datetime.now() - started_at).total_seconds() * 1000),
    )

    return saved, any_adjusted, "；".join(reasons) if reasons else "", True, len(saved)


async def cancel_long_term_goal(db: AsyncSession, goal: UserGoal, user: User) -> int:
    """
    取消长期目标并清理未完成任务。

    返回：
        清理的 pending 任务数量。

    改动原因：
        “取消任务”必须可持久化，避免刷新后又被识别为进行中，并提供清理能力避免数据污染。
    """
    state = await ensure_goal_state(db, goal)
    state.status = LongTermGoalStatus.CANCELLED
    state.cancelled_at = datetime.now()

    tasks_result = await db.execute(select(Task).where(Task.goal_id == goal.id, Task.status == TaskStatus.PENDING))
    tasks = tasks_result.scalars().all()
    deleted = 0
    for t in tasks:
        await record_task_event(
            db=db,
            user_id=user.id,
            goal_id=goal.id,
            task=t,
            event_type=TaskEventType.DELETED,
            source=TaskEventSource.SYSTEM,
            payload={"reason": "cancel_long_term_goal"},
        )
        await db.delete(t)
        deleted += 1

    await db.commit()
    return deleted
