"""
长期任务状态管理 API 端点 (Long-Term Goal Management Endpoint)

设计意图：
    提供“刷新检测 + 引导弹窗”所需的轻量接口：
    - GET /api/long-term/active：检测是否存在进行中的长期计划，并返回进度汇总
    - POST /api/long-term/{goal_id}/continue：幂等派发今天任务（继续任务）
    - POST /api/long-term/{goal_id}/cancel：取消长期计划并清理未完成任务

改动原因：
    之前前端刷新只会加载最新计划，缺少“状态机 + 幂等派发”的后端支撑，导致重复生成与状态不一致。
"""

from __future__ import annotations

import logging
from datetime import date as date_type
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.long_term import cancel_long_term_goal, compute_goal_progress, ensure_daily_tasks, get_active_long_term_goal
from app.db.models.user import User
from app.db.models.user_goal import UserGoal
from app.schemas.goal import UserGoalResponse
from app.schemas.task import TaskResponse


router = APIRouter(prefix="/api/long-term", tags=["long-term"])
logger = logging.getLogger(__name__)


class ActiveLongTermResponse(BaseModel):
    """活跃长期目标信息（用于刷新检测）。"""

    goal: UserGoalResponse = Field(..., description="活跃的长期目标")
    progress: dict = Field(..., description="进度汇总：total/completed/completion_rate")
    today_tasks: list[TaskResponse] = Field(..., description="今天的任务列表（可能为空）")

    model_config = {"from_attributes": True}


class ContinueRequest(BaseModel):
    """继续长期任务的请求体。"""

    user_feedback: str | None = Field(None, description="用户反馈（可选，用于滚动调整）")


class ContinueResponse(BaseModel):
    """继续长期任务的响应体。"""

    goal: UserGoalResponse = Field(..., description="目标信息")
    tasks: list[TaskResponse] = Field(..., description="今天任务列表")
    time_adjusted: bool = Field(False, description="是否有任务时间窗被自动调整")
    adjusted_reason: str = Field("", description="时间调整原因")
    generated_new: bool = Field(False, description="本次是否新生成了任务（否则为幂等返回已有任务）")
    created_count: int = Field(0, description="本次新创建的任务数量（幂等返回时为 0）")

    model_config = {"from_attributes": True}


class CancelResponse(BaseModel):
    """取消长期任务的响应体。"""

    goal_id: int = Field(..., description="目标 ID")
    deleted_pending_tasks: int = Field(..., description="被清理的未完成任务数量")
    message: str = Field(..., description="提示信息")


@router.get("/active", response_model=ActiveLongTermResponse)
async def get_active_long_term(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    检测当前用户是否存在进行中的长期任务。

    改动原因：
        页面刷新触发机制需要一个轻量接口，在 500ms 内完成检测并返回必要信息。
    """
    user_id = current_user.id
    goal, _state = await get_active_long_term_goal(db, user_id)
    if not goal:
        raise HTTPException(status_code=404, detail="没有进行中的长期任务")

    progress = await compute_goal_progress(db, goal.id)

    today = date_type.today()

    # 直接查询 tasks 表，避免额外的 relationship 载入
    from app.db.models.task import Task

    today_task_rows = await db.execute(
        select(Task).where(Task.goal_id == goal.id, Task.scheduled_date == today).order_by(Task.id)
    )
    today_tasks = today_task_rows.scalars().all()

    logger.info(
        "LongTerm.active: 命中 user_id=%d goal_id=%d today_tasks=%d progress=%s",
        user_id,
        goal.id,
        len(today_tasks),
        progress,
    )

    return ActiveLongTermResponse(
        goal=UserGoalResponse.model_validate(goal),
        progress=progress,
        today_tasks=[TaskResponse.model_validate(t) for t in today_tasks],
    )


@router.post("/{goal_id}/continue", response_model=ContinueResponse)
async def continue_long_term(
    goal_id: int,
    body: ContinueRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    继续长期任务：幂等生成今天的子任务（若已存在则直接返回）。

    改动原因：
        “继续任务”需要在刷新后基于之前进度生成/补齐今天任务，并避免重复生成。
    """
    user_id = current_user.id
    goal_result = await db.execute(
        select(UserGoal).where(UserGoal.id == goal_id, UserGoal.user_id == user_id)
    )
    goal = goal_result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在或无权访问")

    today = date_type.today()
    try:
        tasks, adjusted, reason, generated_new, created_count = await ensure_daily_tasks(
            db=db,
            goal=goal,
            user=current_user,
            target_date=today,
            user_feedback=(body.user_feedback if body else None),
        )
    except RuntimeError as e:
        error_id = uuid4().hex[:10]
        logger.exception(
            "LongTerm.continue: 继续任务失败 (runtime) error_id=%s user_id=%d goal_id=%d",
            error_id,
            user_id,
            goal_id,
        )
        raise HTTPException(status_code=502, detail=f"{e}（错误ID: {error_id}）") from e
    except Exception as e:
        error_id = uuid4().hex[:10]
        logger.exception(
            "LongTerm.continue: 继续任务失败 (unexpected) error_id=%s user_id=%d goal_id=%d",
            error_id,
            user_id,
            goal_id,
        )
        raise HTTPException(status_code=500, detail=f"继续任务失败，请稍后重试（错误ID: {error_id}）") from e

    logger.info(
        "LongTerm.continue: 成功 user_id=%d goal_id=%d date=%s tasks=%d generated_new=%s created=%d",
        user_id,
        goal_id,
        today.isoformat(),
        len(tasks),
        generated_new,
        created_count,
    )

    goal_for_response = await db.get(UserGoal, goal_id)
    if not goal_for_response:
        raise HTTPException(status_code=404, detail="目标不存在或无权访问")

    return ContinueResponse(
        goal=UserGoalResponse.model_validate(goal_for_response),
        tasks=[TaskResponse.model_validate(t) for t in tasks],
        time_adjusted=adjusted,
        adjusted_reason=reason,
        generated_new=generated_new,
        created_count=created_count,
    )


@router.post("/{goal_id}/cancel", response_model=CancelResponse)
async def cancel_long_term(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    取消长期任务并清理未完成任务。

    改动原因：
        “取消任务”必须终止后续刷新检测，并清理未完成任务，避免数据污染和状态不一致。
    """
    user_id = current_user.id
    goal_result = await db.execute(
        select(UserGoal).where(UserGoal.id == goal_id, UserGoal.user_id == user_id)
    )
    goal = goal_result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在或无权访问")

    deleted = await cancel_long_term_goal(db, goal, current_user)
    logger.info(
        "LongTerm.cancel: 成功 user_id=%d goal_id=%d deleted_pending=%d",
        user_id,
        goal.id,
        deleted,
    )
    return CancelResponse(goal_id=goal.id, deleted_pending_tasks=deleted, message="长期任务已取消")
