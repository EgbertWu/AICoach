"""
复盘报告 API 端点 (Review Endpoint)

设计意图：
    提供复盘相关接口：
    - POST /api/reviews/generate：单日复盘（关联 goal_id）
    - POST /api/reviews/generate-period：周期复盘（周报/月报）
    - GET /api/reviews/history：所有复盘历史
    - GET /api/reviews/period-history：周期复盘历史（周报/月报）
"""

import logging
from datetime import date as date_type, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.reviewer import ReviewerAgent
from app.api.dependencies import get_current_user, get_db
from app.db.models.review import PeriodType, ReviewReport
from app.db.models.task import Task
from app.db.models.user import User
from app.db.models.user_goal import GoalType, UserGoal
from app.schemas.review import ReviewResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


# ===== 请求/响应模型 =====

class GenerateReviewRequest(BaseModel):
    goal_id: int = Field(..., description="要复盘的目标 ID")


class GenerateReviewResponse(BaseModel):
    review: ReviewResponse = Field(..., description="复盘报告")


class GeneratePeriodReviewRequest(BaseModel):
    period_type: str = Field(..., description="复盘类型：weekly 或 monthly")
    start_date: str = Field(..., description="起始日期，格式 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期，格式 YYYY-MM-DD")


# ===== 辅助函数 =====

def _build_period_label(period_type: str, start_date: str, end_date: str) -> str:
    """生成周期标签。"""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    if period_type == "weekly":
        return f"{start.year}年{start.month}月{start.day}日-{end.month}月{end.day}日 周报"
    else:
        return f"{start.year}年{start.month}月 月报"


def _build_period_goal_content(period_type: str, start_date: str, end_date: str) -> str:
    """构造周期复盘的目标描述。"""
    label = _build_period_label(period_type, start_date, end_date)
    return f"{label}：汇总该时间段内所有任务的执行情况"

def _fmt_cn_date(d: date_type) -> str:
    return f"{d.year}年{d.month}月{d.day}日"


# ===== 接口实现 =====


@router.post("/generate", response_model=GenerateReviewResponse)
async def generate_review(
    body: GenerateReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    生成单日复盘报告（需要登录）。
    """
    user_id = current_user.id
    result = await db.execute(
        select(UserGoal)
        .where(UserGoal.id == body.goal_id, UserGoal.user_id == user_id)
    )
    goal = result.scalar_one_or_none()

    if not goal:
        raise HTTPException(status_code=404, detail=f"目标不存在或无权访问 (id={body.goal_id})")

    goal_type_value = goal.goal_type.value if isinstance(goal.goal_type, GoalType) else str(goal.goal_type)

    tasks: list[Task]
    period_label: str
    if goal_type_value == GoalType.LONG_TERM.value:
        dates_result = await db.execute(
            select(Task.scheduled_date)
            .where(Task.goal_id == goal.id, Task.scheduled_date.is_not(None))
            .distinct()
            .order_by(Task.scheduled_date.desc())
            .limit(7)
        )
        dates = [d for d in dates_result.scalars().all() if d is not None]
        if not dates:
            raise HTTPException(status_code=400, detail="该长期目标还没有任何按天任务，无法生成复盘")

        start_date = min(dates)
        end_date = max(dates)

        tasks_result = await db.execute(
            select(Task)
            .where(Task.goal_id == goal.id, Task.scheduled_date.in_(dates))
            .order_by(Task.scheduled_date.asc(), Task.id.asc())
        )
        tasks = tasks_result.scalars().all()
        if not tasks:
            raise HTTPException(status_code=400, detail="该目标下没有任何任务，无法生成复盘")

        if start_date == end_date:
            period_label = f"{_fmt_cn_date(end_date)} 日复盘"
        else:
            period_label = f"{_fmt_cn_date(start_date)}-{_fmt_cn_date(end_date)} 日复盘"
    else:
        goal_with_tasks_result = await db.execute(
            select(UserGoal)
            .options(selectinload(UserGoal.tasks))
            .where(UserGoal.id == body.goal_id, UserGoal.user_id == user_id)
        )
        goal_with_tasks = goal_with_tasks_result.scalar_one_or_none()
        if not goal_with_tasks or not goal_with_tasks.tasks:
            raise HTTPException(status_code=400, detail="该目标下没有任何任务，无法生成复盘")
        tasks = sorted(goal_with_tasks.tasks, key=lambda t: t.id)
        period_label = f"{_fmt_cn_date(date_type.today())} 日复盘"

    reviewer = ReviewerAgent()
    try:
        review_data = await reviewer.generate_review(goal.content, tasks)
    except RuntimeError as e:
        logger.error("复盘生成失败: LLM 服务错误 - %s", e)
        raise HTTPException(status_code=502, detail=f"AI 服务暂时不可用: {e}") from e
    except ValueError as e:
        logger.error("复盘生成失败: LLM 返回格式错误 - %s", e)
        raise HTTPException(status_code=500, detail=f"AI 返回了无法解析的内容: {e}") from e

    report = ReviewReport(
        goal_id=goal.id,
        period_type=PeriodType.DAILY,
        period_label=period_label,
        completion_rate=review_data["completion_rate"],
        analysis=review_data["analysis"],
        suggestions=review_data["suggestions"],
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    logger.info("单日复盘已保存: report_id=%d, goal_id=%d", report.id, goal.id)

    return GenerateReviewResponse(review=ReviewResponse.model_validate(report))


@router.post("/generate-period", response_model=GenerateReviewResponse)
async def generate_period_review(
    body: GeneratePeriodReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    生成周期复盘报告（周报/月报）。

    根据时间范围查询该用户所有任务，汇总后调用 AI 生成复盘。
    """
    if body.period_type not in ("weekly", "monthly"):
        raise HTTPException(status_code=400, detail="period_type 必须为 weekly 或 monthly")

    try:
        start_dt = datetime.strptime(body.start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(body.end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式错误，请使用 YYYY-MM-DD")

    start_d = start_dt.date()
    end_d = end_dt.date()

    # 查询该用户在时间范围内的所有任务
    result = await db.execute(
        select(Task)
        .join(UserGoal, Task.goal_id == UserGoal.id)
        .where(
            UserGoal.user_id == current_user.id,
            or_(
                and_(
                    Task.scheduled_date.is_not(None),
                    Task.scheduled_date >= start_d,
                    Task.scheduled_date <= end_d,
                ),
                and_(
                    Task.scheduled_date.is_(None),
                    Task.created_at >= start_dt,
                    Task.created_at <= end_dt,
                ),
            ),
        )
        .order_by(Task.scheduled_date.asc().nulls_last(), Task.created_at.asc(), Task.id.asc())
    )
    tasks = result.scalars().all()

    if not tasks:
        raise HTTPException(
            status_code=400,
            detail=f"{body.start_date} ~ {body.end_date} 期间没有任务记录",
        )

    # 构造周期目标内容
    goal_content = _build_period_goal_content(body.period_type, body.start_date, body.end_date)

    # 调用 ReviewerAgent
    reviewer = ReviewerAgent()
    try:
        review_data = await reviewer.generate_review(goal_content, tasks)
    except RuntimeError as e:
        logger.error("周期复盘生成失败: LLM 服务错误 - %s", e)
        raise HTTPException(status_code=502, detail=f"AI 服务暂时不可用: {e}") from e
    except ValueError as e:
        logger.error("周期复盘生成失败: LLM 返回格式错误 - %s", e)
        raise HTTPException(status_code=500, detail=f"AI 返回了无法解析的内容: {e}") from e

    period_type_enum = PeriodType.WEEKLY if body.period_type == "weekly" else PeriodType.MONTHLY
    period_label = _build_period_label(body.period_type, body.start_date, body.end_date)

    report = ReviewReport(
        goal_id=None,
        period_type=period_type_enum,
        period_label=period_label,
        completion_rate=review_data["completion_rate"],
        analysis=review_data["analysis"],
        suggestions=review_data["suggestions"],
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    logger.info(
        "周期复盘已保存: report_id=%d, type=%s, label=%s, user_id=%d",
        report.id, body.period_type, period_label, current_user.id,
    )

    return GenerateReviewResponse(review=ReviewResponse.model_validate(report))


@router.get("/history", response_model=list[ReviewResponse])
async def get_review_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前用户所有复盘报告历史（按创建时间倒序）。
    """
    result = await db.execute(
        select(ReviewReport)
        .join(UserGoal, ReviewReport.goal_id == UserGoal.id, isouter=True)
        .where(
            (UserGoal.user_id == current_user.id) | (ReviewReport.goal_id.is_(None))
        )
        .order_by(ReviewReport.created_at.desc())
    )
    reviews = result.scalars().all()
    return [ReviewResponse.model_validate(r) for r in reviews]


@router.get("/period-history", response_model=list[ReviewResponse])
async def get_period_review_history(
    period_type: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前用户的周期复盘历史（周报/月报）。

    可选参数 period_type: "weekly" 或 "monthly" 进行筛选。
    """
    conditions = [
        ReviewReport.goal_id.is_(None),
        ReviewReport.period_type.in_([PeriodType.WEEKLY, PeriodType.MONTHLY]),
    ]

    if period_type and period_type in ("weekly", "monthly"):
        pt = PeriodType.WEEKLY if period_type == "weekly" else PeriodType.MONTHLY
        conditions.append(ReviewReport.period_type == pt)

    result = await db.execute(
        select(ReviewReport)
        .join(UserGoal, ReviewReport.goal_id == UserGoal.id, isouter=True)
        .where(and_(*conditions))
        .order_by(ReviewReport.created_at.desc())
    )
    reviews = result.scalars().all()
    return [ReviewResponse.model_validate(r) for r in reviews]
