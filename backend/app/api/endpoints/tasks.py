"""
任务管理 API 端点 (Task Management Endpoint)

设计意图：
    提供任务编辑、完成、重新生成和历史计划查询接口。

增量升级说明：
    - PATCH /api/tasks/{task_id}：加入 quiet hours 后端兜底
    - POST /api/tasks/{task_id}/regenerate：加入 quiet hours 后端兜底
    - GET /api/plans/latest：适配新字段 goal_type / roadmap_summary
    - GET /api/plans/history：适配新字段
    改动原因：所有"会产生/修改 planned 时间窗"的路径必须加入兜底。
"""

import json
import logging
from datetime import date as date_type, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError as PydanticValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.prompts.task_rewriter_prompt import TASK_REWRITER_SYSTEM_PROMPT
from app.api.dependencies import get_current_user, get_db
from app.core.config import settings
from app.core.llm import get_llm_client
from app.core.task_history import record_task_event
from app.core.task_unique import sync_task_unique
from app.core.time_prefs import normalize_planned_window
from app.db.models.task import Task, TaskStatus
from app.db.models.task_event import TaskEventSource, TaskEventType
from app.db.models.task_unique import TaskUnique
from app.db.models.user import User
from app.db.models.user_goal import GoalType, UserGoal
from app.schemas.goal import UserGoalResponse, UserGoalWithTasksResponse
from app.schemas.task import (
    CompleteTaskResponse,
    RegenerateTaskRequest,
    TaskCreate,
    TaskCompleteRequest,
    TaskResponse,
    TaskUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tasks"])


class PlanResponse(BaseModel):
    """计划响应体（目标 + 任务列表）。"""
    goal: UserGoalResponse = Field(..., description="用户目标")
    tasks: list[TaskResponse] = Field(..., description="关联的任务列表")
    model_config = {"from_attributes": True}


# ===== LLM 响应的内部 Pydantic 模型 =====

class _RewrittenTaskItem(BaseModel):
    """LLM 返回的单条改写任务格式。"""
    description: str = Field(..., min_length=1, max_length=1000)
    criteria: str = Field(..., min_length=1, max_length=1000)
    planned_start_at: datetime | None = Field(None, description="计划开始时间")
    planned_end_at: datetime | None = Field(None, description="计划截止时间")

class DeleteTaskResponse(BaseModel):
    """删除任务的响应体。"""
    message: str = Field(..., description="删除结果提示")
    task_id: int = Field(..., description="被删除的任务 ID")


# ===== 接口实现 =====

@router.post("/tasks", response_model=TaskResponse)
async def create_task(
    body: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    手动新增任务（需要登录）。

    改动原因：
    - 看板不仅支持 AI 自动生成，也需要支持用户在「待办」中手动新增任务。
    - 所有“会产生/修改 planned 时间窗”的路径都必须应用 quiet hours 兜底。
    """
    goal_result = await db.execute(
        select(UserGoal).where(UserGoal.id == body.goal_id, UserGoal.user_id == current_user.id)
    )
    goal = goal_result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail=f"目标不存在或无权访问 (goal_id={body.goal_id})")

    new_start, new_end, adjusted, reason = normalize_planned_window(
        planned_start_at=body.planned_start_at,
        planned_end_at=body.planned_end_at,
        quiet_hours_start=current_user.quiet_hours_start,
        quiet_hours_end=current_user.quiet_hours_end,
        allow_quiet_hours=current_user.allow_quiet_hours,
        timezone_str=current_user.timezone,
    )
    if adjusted:
        logger.info("任务新增时间窗已修正: goal_id=%d, reason=%s", body.goal_id, reason)

    scheduled_date = body.scheduled_date
    if scheduled_date is None and goal.goal_type == GoalType.LONG_TERM:
        scheduled_date = date_type.today()

    task = Task(
        goal_id=body.goal_id,
        description=body.description.strip(),
        criteria=body.criteria.strip(),
        planned_start_at=new_start,
        planned_end_at=new_end,
        scheduled_date=scheduled_date,
        status=TaskStatus.PENDING,
    )
    db.add(task)
    try:
        await db.flush()
        await sync_task_unique(db, task)
        await record_task_event(
            db=db,
            user_id=current_user.id,
            goal_id=goal.id,
            task=task,
            event_type=TaskEventType.CREATED,
            source=TaskEventSource.MANUAL,
            payload={"entry": "create_task"},
        )
        await db.commit()
        await db.refresh(task)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="相同任务已存在，已阻止重复创建")
    return TaskResponse.model_validate(task)


@router.delete("/tasks/{task_id}", response_model=DeleteTaskResponse)
async def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    删除任务（需要登录）。

    改动原因：
    - 支持用户在看板的「待办」中清理任务（例如错误生成/不再需要）。
    - 限制：已完成任务不允许删除，避免破坏复盘/历史统计。
    """
    result = await db.execute(
        select(Task)
        .join(UserGoal, Task.goal_id == UserGoal.id)
        .where(Task.id == task_id, UserGoal.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在或无权访问 (id={task_id})")

    if task.status == TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="已完成任务不允许删除")

    await record_task_event(
        db=db,
        user_id=current_user.id,
        goal_id=task.goal_id,
        task=task,
        event_type=TaskEventType.DELETED,
        source=TaskEventSource.MANUAL,
        payload={"entry": "delete_task"},
    )
    await db.execute(delete(TaskUnique).where(TaskUnique.task_id == task_id))
    await db.delete(task)
    await db.commit()

    return DeleteTaskResponse(message="任务已删除", task_id=task_id)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    body: TaskUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    手动编辑任务（需要登录）。

    增量改动：加入 quiet hours 后端兜底。
    改动原因：用户手动编辑也可能设置违规时间窗。
    """
    result = await db.execute(
        select(Task)
        .join(UserGoal, Task.goal_id == UserGoal.id)
        .where(Task.id == task_id, UserGoal.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在或无权访问 (id={task_id})")

    update_fields = body.model_dump(exclude_unset=True)

    if "description" in update_fields:
        task.description = update_fields["description"]
    if "criteria" in update_fields:
        task.criteria = update_fields["criteria"]

    # 对时间窗应用 quiet hours 兜底
    new_start = update_fields.get("planned_start_at", task.planned_start_at)
    new_end = update_fields.get("planned_end_at", task.planned_end_at)

    if "planned_start_at" in update_fields or "planned_end_at" in update_fields:
        adjusted_start, adjusted_end, adjusted, reason = normalize_planned_window(
            planned_start_at=new_start,
            planned_end_at=new_end,
            quiet_hours_start=current_user.quiet_hours_start,
            quiet_hours_end=current_user.quiet_hours_end,
            allow_quiet_hours=current_user.allow_quiet_hours,
            timezone_str=current_user.timezone,
        )
        task.planned_start_at = adjusted_start
        task.planned_end_at = adjusted_end
        if adjusted:
            logger.info("任务编辑时间窗已修正: task_id=%d, reason=%s", task_id, reason)

    payload: dict = {"entry": "update_task", "changed_fields": sorted(list(update_fields.keys()))}
    if "planned_start_at" in update_fields and task.planned_start_at:
        payload["planned_start_at"] = task.planned_start_at.isoformat()
    if "planned_end_at" in update_fields and task.planned_end_at:
        payload["planned_end_at"] = task.planned_end_at.isoformat()

    try:
        await sync_task_unique(db, task)
        await record_task_event(
            db=db,
            user_id=current_user.id,
            goal_id=task.goal_id,
            task=task,
            event_type=TaskEventType.UPDATED,
            source=TaskEventSource.MANUAL,
            payload=payload,
        )
        await db.commit()
        await db.refresh(task)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="该修改会导致与已有任务重复，已阻止保存")

    return TaskResponse.model_validate(task)


@router.post("/tasks/{task_id}/complete", response_model=CompleteTaskResponse)
async def complete_task(
    task_id: int,
    body: TaskCompleteRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """完成任务（需要登录）。保持原有逻辑不变。"""
    result = await db.execute(
        select(Task)
        .join(UserGoal, Task.goal_id == UserGoal.id)
        .where(Task.id == task_id, UserGoal.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在或无权访问 (id={task_id})")

    if task.status == TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="任务已经完成")

    now = datetime.now()
    task.status = TaskStatus.COMPLETED
    task.completed_at = now

    is_late = False
    if task.planned_end_at and now > task.planned_end_at:
        is_late = True

    reason_required = False
    if is_late:
        user_reason = body.completion_reason if body else None
        if user_reason:
            task.completion_reason = user_reason
            reason_required = False
        else:
            reason_required = True

    await record_task_event(
        db=db,
        user_id=current_user.id,
        goal_id=task.goal_id,
        task=task,
        event_type=TaskEventType.COMPLETED,
        source=TaskEventSource.MANUAL,
        payload={"entry": "complete_task", "is_late": is_late, "reason_required": reason_required},
    )
    await db.commit()
    await db.refresh(task)

    logger.info(
        "任务完成: task_id=%d, is_late=%s, reason_required=%s",
        task_id, is_late, reason_required,
    )

    return CompleteTaskResponse(
        task=TaskResponse.model_validate(task),
        is_late=is_late,
        reason_required=reason_required,
    )


@router.post("/tasks/{task_id}/uncomplete", response_model=TaskResponse)
async def uncomplete_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Task)
        .join(UserGoal, Task.goal_id == UserGoal.id)
        .where(Task.id == task_id, UserGoal.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在或无权访问 (id={task_id})")

    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="任务尚未完成，无需取消完成")

    task.status = TaskStatus.PENDING
    task.completed_at = None
    task.completion_reason = None

    await record_task_event(
        db=db,
        user_id=current_user.id,
        goal_id=task.goal_id,
        task=task,
        event_type=TaskEventType.UPDATED,
        source=TaskEventSource.MANUAL,
        payload={"entry": "uncomplete_task"},
    )
    await db.commit()
    await db.refresh(task)

    logger.info("任务取消完成: task_id=%d", task_id)

    return TaskResponse.model_validate(task)


@router.patch("/tasks/{task_id}/completion-reason", response_model=TaskResponse)
async def update_completion_reason(
    task_id: int,
    body: TaskCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """补填超时完成原因（需要登录）。保持原有逻辑不变。"""
    result = await db.execute(
        select(Task)
        .join(UserGoal, Task.goal_id == UserGoal.id)
        .where(Task.id == task_id, UserGoal.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在或无权访问 (id={task_id})")

    if body.completion_reason:
        task.completion_reason = body.completion_reason

    await record_task_event(
        db=db,
        user_id=current_user.id,
        goal_id=task.goal_id,
        task=task,
        event_type=TaskEventType.UPDATED,
        source=TaskEventSource.MANUAL,
        payload={"entry": "update_completion_reason"},
    )
    await db.commit()
    await db.refresh(task)

    return TaskResponse.model_validate(task)


@router.post("/tasks/{task_id}/regenerate", response_model=TaskResponse)
async def regenerate_task(
    task_id: int,
    body: RegenerateTaskRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    重新生成单条任务（需要登录）。

    增量改动：加入 quiet hours 后端兜底。
    改动原因：LLM 重生成也可能输出违规时间窗。
    """
    result = await db.execute(
        select(Task)
        .join(UserGoal, Task.goal_id == UserGoal.id)
        .where(Task.id == task_id, UserGoal.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在或无权访问 (id={task_id})")

    goal_result = await db.execute(select(UserGoal).where(UserGoal.id == task.goal_id))
    goal = goal_result.scalar_one_or_none()

    if not goal:
        raise HTTPException(status_code=404, detail="关联的目标不存在")

    user_feedback = body.user_feedback if body else None

    start_str = task.planned_start_at.strftime("%H:%M") if task.planned_start_at else "未设定"
    end_str = task.planned_end_at.strftime("%H:%M") if task.planned_end_at else "未设定"

    feedback_part = f"\n\n用户反馈：{user_feedback}" if user_feedback else ""
    user_message = (
        f"## 所属目标\n{goal.content}\n\n"
        f"## 原始任务\n"
        f"- 描述：{task.description}\n"
        f"- 完成标准：{task.criteria}\n"
        f"- 时间窗口：{start_str} ~ {end_str}"
        f"{feedback_part}\n\n"
        f"请根据以上信息改写这条任务，输出一个 JSON 对象。"
    )

    logger.info("TaskRewriter: 开始改写任务 task_id=%d", task_id)

    last_error = None
    for attempt in range(2):
        try:
            client = get_llm_client()
            response = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": TASK_REWRITER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )

            raw_content = (response.choices[0].message.content or "").strip()

            if raw_content.startswith("```"):
                lines = raw_content.split("\n")
                json_lines = [l for l in lines if not l.strip().startswith("```")]
                raw_content = "\n".join(json_lines).strip()

            parsed = json.loads(raw_content)

            if "start_time" in parsed or "end_time" in parsed:
                from datetime import date as date_type
                today = date_type.today()
                start_at = None
                end_at = None
                if parsed.get("start_time"):
                    h, m = map(int, str(parsed["start_time"]).split(":"))
                    start_at = datetime.combine(today, datetime.min.time().replace(hour=h, minute=m))
                if parsed.get("end_time"):
                    h, m = map(int, str(parsed["end_time"]).split(":"))
                    end_at = datetime.combine(today, datetime.min.time().replace(hour=h, minute=m))

                rewritten = _RewrittenTaskItem(
                    description=parsed["description"],
                    criteria=parsed["criteria"],
                    planned_start_at=start_at,
                    planned_end_at=end_at,
                )
            else:
                rewritten = _RewrittenTaskItem.model_validate(parsed)

            # ===== quiet hours 兜底 =====
            # 改动原因：LLM 重生成也可能输出违规时间窗
            new_start, new_end, adjusted, reason = normalize_planned_window(
                planned_start_at=rewritten.planned_start_at,
                planned_end_at=rewritten.planned_end_at,
                quiet_hours_start=current_user.quiet_hours_start,
                quiet_hours_end=current_user.quiet_hours_end,
                allow_quiet_hours=current_user.allow_quiet_hours,
                timezone_str=current_user.timezone,
            )
            if adjusted:
                logger.info("TaskRewriter: 时间窗已修正: task_id=%d, reason=%s", task_id, reason)

            task.description = rewritten.description
            task.criteria = rewritten.criteria
            task.planned_start_at = new_start
            task.planned_end_at = new_end
            try:
                await sync_task_unique(db, task)
                await record_task_event(
                    db=db,
                    user_id=current_user.id,
                    goal_id=task.goal_id,
                    task=task,
                    event_type=TaskEventType.REGENERATED,
                    source=TaskEventSource.AI,
                    payload={"entry": "regenerate_task", "time_adjusted": adjusted, "adjusted_reason": reason},
                )
                await db.commit()
                await db.refresh(task)
            except IntegrityError:
                await db.rollback()
                raise HTTPException(status_code=409, detail="重生成结果与已有任务冲突，已阻止保存")

            logger.info("TaskRewriter: 任务改写成功 task_id=%d (attempt %d)", task_id, attempt + 1)
            return TaskResponse.model_validate(task)

        except json.JSONDecodeError as e:
            last_error = f"LLM 返回的不是有效 JSON: {e}"
            logger.warning("TaskRewriter: 第 %d 次解析失败: %s", attempt + 1, last_error)
        except PydanticValidationError as e:
            last_error = f"LLM 返回的任务格式校验失败: {e}"
            logger.warning("TaskRewriter: 第 %d 次校验失败: %s", attempt + 1, last_error)
        except Exception as e:
            logger.error("TaskRewriter: LLM API 调用失败: %s", e)
            raise HTTPException(status_code=502, detail=f"AI 服务暂时不可用: {e}") from e

    raise HTTPException(status_code=500, detail=f"AI 无法改写任务（已重试 1 次）。最后错误: {last_error}")


@router.get("/plans/latest", response_model=PlanResponse)
async def get_latest_plan(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户最近一次生成的计划。适配新字段 goal_type / roadmap_summary。"""
    result = await db.execute(
        select(UserGoal)
        .options(selectinload(UserGoal.tasks))
        .where(UserGoal.user_id == current_user.id)
        .order_by(UserGoal.created_at.desc())
        .limit(1)
    )
    latest_goal = result.scalar_one_or_none()

    if not latest_goal:
        raise HTTPException(status_code=404, detail="还没有生成过任何计划")

    sorted_tasks = sorted(latest_goal.tasks, key=lambda t: t.id)

    return PlanResponse(
        goal=UserGoalResponse.model_validate(latest_goal),
        tasks=[TaskResponse.model_validate(t) for t in sorted_tasks],
    )


@router.get("/plans/history", response_model=list[UserGoalWithTasksResponse])
async def get_plan_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的所有历史计划。适配新字段。"""
    result = await db.execute(
        select(UserGoal)
        .options(selectinload(UserGoal.tasks))
        .where(UserGoal.user_id == current_user.id)
        .order_by(UserGoal.created_at.desc())
    )
    goals = result.scalars().all()

    return [
        UserGoalWithTasksResponse(
            id=g.id,
            user_id=g.user_id,
            content=g.content,
            created_at=g.created_at,
            goal_type=g.goal_type.value if hasattr(g.goal_type, 'value') else str(g.goal_type),
            roadmap_summary=g.roadmap_summary,
            target_duration_days=g.target_duration_days,
            start_date=g.start_date,
            tasks=sorted([TaskResponse.model_validate(t) for t in g.tasks], key=lambda t: t.id),
        )
        for g in goals
    ]


@router.get("/plans/{goal_id}", response_model=PlanResponse)
async def get_plan_by_id(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取指定 ID 的计划及其任务列表。"""
    result = await db.execute(
        select(UserGoal)
        .options(selectinload(UserGoal.tasks))
        .where(UserGoal.id == goal_id, UserGoal.user_id == current_user.id)
    )
    goal = result.scalar_one_or_none()

    if not goal:
        raise HTTPException(status_code=404, detail="计划不存在或无权访问")

    sorted_tasks = sorted(goal.tasks, key=lambda t: t.id)

    return PlanResponse(
        goal=UserGoalResponse.model_validate(goal),
        tasks=[TaskResponse.model_validate(t) for t in sorted_tasks],
    )
