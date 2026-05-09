"""
计划生成 API 端点

设计意图：
    提供计划生成和每日派发接口。

增量升级说明：
    - POST /api/plans/generate：自动识别 daily/long_term，长期目标生成 Roadmap 并派发今日任务
    - 新增 POST /api/plans/dispatch：每日自动派发（避免重复生成）
    - 所有时间窗路径加入 quiet hours 后端兜底
    改动原因：用户仍然"输入一句目标"，但系统自动升级为长期模式。
"""

import json
import logging
from datetime import date as date_type, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.dispatch_service import dispatch_daily_tasks
from app.agents.planner import PlannerAgent
from app.agents.roadmap_agent import RoadmapAgent
from app.api.dependencies import get_current_user, get_db
from app.core.long_term import ensure_daily_tasks
from app.core.goal_classifier import classify_goal
from app.core.time_prefs import normalize_planned_window
from app.db.models.task import Task
from app.db.models.user import User
from app.db.models.user_goal import GoalType, UserGoal
from app.schemas.goal import UserGoalResponse
from app.schemas.task import TaskResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plans", tags=["plans"])


class PlanGenerateResponse(BaseModel):
    """计划生成的完整响应体。"""
    goal: UserGoalResponse = Field(..., description="用户目标")
    tasks: list[TaskResponse] = Field(..., description="生成的任务列表")
    time_adjusted: bool = Field(False, description="是否有任务时间窗被自动调整")
    adjusted_reason: str = Field("", description="时间调整原因")
    model_config = {"from_attributes": True}


class DispatchRequest(BaseModel):
    """
    每日派发请求体。

    改动原因：date 和 user_feedback 都是可选字段，
    使用与项目其他 schema 一致的 X | None = Field(None) 写法。
    """
    goal_id: int = Field(..., description="目标 ID")
    date: date_type | None = Field(None, description="目标日期，默认今天")
    user_feedback: str | None = Field(None, description="用户反馈（可选）")


class DispatchResponse(BaseModel):
    """每日派发响应体。"""
    goal: UserGoalResponse = Field(..., description="用户目标")
    tasks: list[TaskResponse] = Field(..., description="当日任务列表")
    time_adjusted: bool = Field(False, description="是否有任务时间窗被自动调整")
    adjusted_reason: str = Field("", description="时间调整原因")
    model_config = {"from_attributes": True}


def _apply_quiet_hours_to_task_dict(
    task_dict: dict,
    user: User,
) -> tuple[dict, bool, str]:
    """
    对单条任务字典应用 quiet hours 兜底校验。

    改动原因：后端兜底确保 LLM 输出的时间窗不违规。

    Args:
        task_dict: 任务字典（含 planned_start_at, planned_end_at）
        user: 当前用户（含 quiet hours 偏好）

    Returns:
        (修正后的任务字典, 是否调整, 调整原因)
    """
    start_at = datetime.fromisoformat(task_dict["planned_start_at"]) if task_dict.get("planned_start_at") else None
    end_at = datetime.fromisoformat(task_dict["planned_end_at"]) if task_dict.get("planned_end_at") else None

    new_start, new_end, adjusted, reason = normalize_planned_window(
        planned_start_at=start_at,
        planned_end_at=end_at,
        quiet_hours_start=user.quiet_hours_start,
        quiet_hours_end=user.quiet_hours_end,
        allow_quiet_hours=user.allow_quiet_hours,
        timezone_str=user.timezone,
    )

    if adjusted:
        task_dict["planned_start_at"] = new_start.isoformat() if new_start else None
        task_dict["planned_end_at"] = new_end.isoformat() if new_end else None

    return task_dict, adjusted, reason


@router.post("/generate", response_model=PlanGenerateResponse)
async def generate_plan(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    生成计划（自动识别 daily / long_term）。

    daily：保持原有逻辑，直接调用 PlannerAgent。
    long_term：
    1) 创建 goal（goal_type=long_term）
    2) 生成 Roadmap 并保存
    3) 派发今日任务
    """
    content = body.get("content", "") if isinstance(body, dict) else ""
    if not content or not isinstance(content, str) or len(content.strip()) == 0:
        raise HTTPException(status_code=422, detail="目标内容不能为空")

    # 1. 识别目标类型
    goal_type, duration_days = classify_goal(content)
    logger.info("目标类型识别: type=%s, duration=%s, content='%s'", goal_type, duration_days, content[:50])

    if goal_type == GoalType.LONG_TERM:
        return await _generate_long_term_plan(content, duration_days, current_user, db)
    else:
        return await _generate_daily_plan(content, current_user, db)


async def _generate_daily_plan(
    content: str,
    current_user: User,
    db: AsyncSession,
) -> PlanGenerateResponse:
    """生成每日计划（原有逻辑 + quiet hours 兜底）。"""
    planner = PlannerAgent()
    try:
        task_dicts = await planner.generate_tasks_from_goal(content)
    except RuntimeError as e:
        logger.error("计划生成失败: LLM 服务错误 - %s", e)
        raise HTTPException(status_code=502, detail=f"AI 服务暂时不可用: {e}") from e
    except ValueError as e:
        logger.error("计划生成失败: LLM 返回格式错误 - %s", e)
        raise HTTPException(status_code=500, detail=f"AI 返回了无法解析的内容: {e}") from e

    # 保存 UserGoal
    user_goal = UserGoal(content=content, user_id=current_user.id, goal_type=GoalType.DAILY)
    db.add(user_goal)
    await db.flush()

    # 保存所有 Task（应用 quiet hours 兜底）
    any_adjusted = False
    all_reasons = []
    saved_tasks: list[Task] = []

    for task_dict in task_dicts:
        task_dict, adjusted, reason = _apply_quiet_hours_to_task_dict(task_dict, current_user)
        if adjusted:
            any_adjusted = True
            all_reasons.append(reason)

        task = Task(
            goal_id=user_goal.id,
            description=task_dict["description"],
            criteria=task_dict["criteria"],
            planned_start_at=datetime.fromisoformat(task_dict["planned_start_at"]) if task_dict.get("planned_start_at") else None,
            planned_end_at=datetime.fromisoformat(task_dict["planned_end_at"]) if task_dict.get("planned_end_at") else None,
        )
        db.add(task)
        saved_tasks.append(task)

    await db.commit()
    await db.refresh(user_goal)
    for task in saved_tasks:
        await db.refresh(task)

    logger.info("每日计划生成成功: goal_id=%d, tasks_count=%d", user_goal.id, len(saved_tasks))

    return PlanGenerateResponse(
        goal=UserGoalResponse.model_validate(user_goal),
        tasks=[TaskResponse.model_validate(t) for t in saved_tasks],
        time_adjusted=any_adjusted,
        adjusted_reason="；".join(all_reasons) if all_reasons else "",
    )


async def _generate_long_term_plan(
    content: str,
    duration_days: int | None,
    current_user: User,
    db: AsyncSession,
) -> PlanGenerateResponse:
    """生成长期计划（Roadmap + 今日派发）。"""
    if not duration_days:
        duration_days = 30

    today = date_type.today()

    # 1. 生成 Roadmap
    try:
        roadmap_data = await RoadmapAgent.generate_roadmap(content, duration_days)
    except (ValueError, RuntimeError) as e:
        logger.error("Roadmap 生成失败: %s", e)
        raise HTTPException(status_code=502, detail=f"AI 生成路线图失败: {e}") from e

    # 设置 start_date
    roadmap_data["start_date"] = today.isoformat()

    # 2. 生成摘要
    try:
        summary = await RoadmapAgent.generate_summary(roadmap_data)
    except Exception as e:
        logger.warning("摘要生成失败，使用降级方案: %s", e)
        summary = f"长期计划：{roadmap_data.get('title', '未知')}，共 {duration_days} 天"

    # 3. 保存 UserGoal
    user_goal = UserGoal(
        content=content,
        user_id=current_user.id,
        goal_type=GoalType.LONG_TERM,
        target_duration_days=duration_days,
        start_date=today,
        roadmap_json=json.dumps(roadmap_data, ensure_ascii=False),
        roadmap_summary=summary,
    )
    db.add(user_goal)
    await db.flush()

    # 4. 先提交目标本身，再幂等派发今日任务
    # 改动原因：项目当前无迁移工具且需要稳定的“可重试”派发语义；
    # 即使派发失败，也保留长期目标与路线图，用户可通过“继续任务”重试。
    await db.commit()
    await db.refresh(user_goal)

    try:
        saved_tasks, any_adjusted, adjusted_reason, _generated_new, _created_count = await ensure_daily_tasks(
            db=db,
            goal=user_goal,
            user=current_user,
            target_date=today,
        )
    except Exception as e:
        logger.error("每日派发失败: %s", e)
        raise HTTPException(status_code=502, detail=f"AI 派发今日任务失败: {e}") from e

    goal_for_response = await db.get(UserGoal, user_goal.id)
    if not goal_for_response:
        raise HTTPException(status_code=404, detail="目标不存在或无权访问")

    logger.info("长期计划生成成功: goal_id=%d, roadmap_title=%s, tasks_count=%d", user_goal.id, roadmap_data.get("title"), len(saved_tasks))

    return PlanGenerateResponse(
        goal=UserGoalResponse.model_validate(goal_for_response),
        tasks=[TaskResponse.model_validate(t) for t in saved_tasks],
        time_adjusted=any_adjusted,
        adjusted_reason=adjusted_reason,
    )


@router.post("/dispatch", response_model=DispatchResponse)
async def dispatch_daily(
    body: DispatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    每日派发接口。

    - 若当日已有 scheduled_date=date 的 tasks，则直接返回（避免重复生成）
    - 否则 dispatch_daily_tasks 生成并返回
    """
    target_date = body.date or date_type.today()

    # 查询目标
    result = await db.execute(
        select(UserGoal).where(
            UserGoal.id == body.goal_id,
            UserGoal.user_id == current_user.id,
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在或无权访问")

    if goal.goal_type != GoalType.LONG_TERM or not goal.roadmap_json:
        raise HTTPException(status_code=400, detail="该目标不是长期目标或没有路线图")

    try:
        saved_tasks, any_adjusted, adjusted_reason, _generated_new, _created_count = await ensure_daily_tasks(
            db=db,
            goal=goal,
            user=current_user,
            target_date=target_date,
            user_feedback=body.user_feedback,
        )
    except Exception as e:
        logger.error("每日派发失败: %s", e)
        raise HTTPException(status_code=502, detail=f"AI 派发今日任务失败: {e}") from e

    logger.info("每日派发成功: goal_id=%d, date=%s, tasks_count=%d", goal.id, target_date, len(saved_tasks))

    goal_for_response = await db.get(UserGoal, goal.id)
    if not goal_for_response:
        raise HTTPException(status_code=404, detail="目标不存在或无权访问")

    return DispatchResponse(
        goal=UserGoalResponse.model_validate(goal_for_response),
        tasks=[TaskResponse.model_validate(t) for t in saved_tasks],
        time_adjusted=any_adjusted,
        adjusted_reason=adjusted_reason,
    )
