"""
加餐任务 API 端点

改动原因：
    用户当天任务很快完成时，系统主动询问是否生成新任务。
    新任务需参考旧任务的复盘报告进行调整生成，而不是随机加任务。
"""

import json
import logging
from datetime import date as date_type, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.config import settings
from app.core.llm import get_llm_client
from app.core.time_prefs import normalize_planned_window
from app.db.models.review import ReviewReport
from app.db.models.task import Task, TaskStatus
from app.db.models.user import User
from app.db.models.user_goal import GoalType, UserGoal
from app.schemas.chat import DispatchMoreResponse, DispatchMoreTaskItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plans", tags=["plans"])


_DISPATCH_MORE_PROMPT = """你是一位 AI 执行力教练。用户今天的任务已经全部完成了，现在需要你生成 2-3 条"加餐任务"。

## 要求
- 基于用户的目标和今日已完成任务，生成有针对性的增量任务
- 如果有复盘报告，参考复盘建议调整任务难度和方向
- 任务应该比原任务更有挑战性或覆盖之前未涉及的知识点
- 每条任务包含 description（做什么）和 criteria（怎么算完成）
- 生成 2-3 条即可，不要太多

## Quiet Hours 约束
{quiet_hours_constraint}

## 当前时间
今天：{today}
起始时间：{start_time}

## 用户目标
{goal_content}

## 今日已完成任务
{completed_tasks}

## 最近复盘建议
{review_suggestions}

{user_feedback_section}

请以 JSON 格式返回：
```json
{{"tasks": [{{"description": "...", "criteria": "...", "planned_start_at": "YYYY-MM-DDTHH:MM:SS", "planned_end_at": "YYYY-MM-DDTHH:MM:SS"}}]}}
```"""


@router.post("/dispatch-more", response_model=DispatchMoreResponse)
async def dispatch_more_tasks(
    body: "DispatchMoreRequest",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    生成加餐任务（基于复盘调整）。

    改动原因：让"完成太快"成为可触发的教练式加餐，新任务依据复盘，而不是随机加任务。
    生成时必须遵守 quiet hours 与时间窗兜底。
    """
    target_date_str = body.date or date_type.today().isoformat()
    try:
        target_date = date_type.fromisoformat(target_date_str)
    except ValueError:
        target_date = date_type.today()

    # 1. 查询目标
    result = await db.execute(
        select(UserGoal).where(
            UserGoal.id == body.goal_id,
            UserGoal.user_id == current_user.id,
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在或无权访问")

    # 2. 查询今日已完成任务
    tasks_result = await db.execute(
        select(Task).where(
            Task.goal_id == goal.id,
            Task.scheduled_date == target_date,
        )
    )
    today_tasks = tasks_result.scalars().all()
    completed_tasks = [t for t in today_tasks if t.status == TaskStatus.COMPLETED]

    if not completed_tasks:
        raise HTTPException(status_code=400, detail="今天还没有已完成的任务")

    # 3. 查询最近一次复盘报告
    review_result = await db.execute(
        select(ReviewReport)
        .where(ReviewReport.goal_id == goal.id)
        .order_by(ReviewReport.created_at.desc())
        .limit(1)
    )
    latest_review = review_result.scalar_one_or_none()

    # 4. 构造 quiet hours 约束
    if current_user.allow_quiet_hours:
        quiet_constraint = "用户允许在任意时间安排任务，无休息时间限制。"
    else:
        quiet_constraint = (
            f"严禁在 {current_user.quiet_hours_start} 到 {current_user.quiet_hours_end} 之间安排任务。"
            f"所有任务的 planned_start_at 和 planned_end_at 必须在 {current_user.quiet_hours_end} 到 {current_user.quiet_hours_start} 之间。"
        )

    # 5. 构造上下文
    completed_text = "\n".join(
        f"- {t.description}（完成标准：{t.criteria}）"
        for t in completed_tasks
    )

    review_text = "无"
    if latest_review:
        review_text = f"完成率：{latest_review.completion_rate}%\n分析：{latest_review.analysis}\n建议：{latest_review.suggestions}"

    feedback_section = ""
    if body.user_feedback:
        feedback_section = f"## 用户额外反馈\n{body.user_feedback}"

    now = datetime.now()
    start_dt = now.replace(minute=0, second=0, microsecond=0)
    if now.minute >= 30:
        start_dt = start_dt.replace(hour=start_dt.hour + 1)
    start_dt = start_dt + timedelta(minutes=30)
    start_time_str = start_dt.strftime("%H:%M")

    system_prompt = (
        _DISPATCH_MORE_PROMPT
        .replace("{quiet_hours_constraint}", quiet_constraint)
        .replace("{today}", target_date.isoformat())
        .replace("{start_time}", start_time_str)
        .replace("{goal_content}", goal.content)
        .replace("{completed_tasks}", completed_text)
        .replace("{review_suggestions}", review_text)
        .replace("{user_feedback_section}", feedback_section)
    )

    # 6. 调用 LLM
    logger.info("生成加餐任务: goal_id=%d, date=%s", goal.id, target_date)

    client = get_llm_client()
    last_error = None

    for attempt in range(2):
        try:
            response = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "请生成加餐任务。"},
                ],
                temperature=settings.llm_temperature,
                max_tokens=1500,
            )

            raw_content = (response.choices[0].message.content or "").strip()
            if "```" in raw_content:
                lines = raw_content.split("\n")
                json_lines = [l for l in lines if not l.strip().startswith("```")]
                raw_content = "\n".join(json_lines).strip()

            parsed = json.loads(raw_content)
            tasks_data = parsed.get("tasks", [])

            if not tasks_data:
                raise ValueError("LLM 未返回任何任务")

            # 7. 保存任务（应用 quiet hours 兜底）
            any_adjusted = False
            all_reasons: list[str] = []
            saved_items: list[DispatchMoreTaskItem] = []

            for t in tasks_data:
                start_at = datetime.fromisoformat(t["planned_start_at"]) if t.get("planned_start_at") else None
                end_at = datetime.fromisoformat(t["planned_end_at"]) if t.get("planned_end_at") else None

                new_start, new_end, adjusted, reason = normalize_planned_window(
                    planned_start_at=start_at,
                    planned_end_at=end_at,
                    quiet_hours_start=current_user.quiet_hours_start,
                    quiet_hours_end=current_user.quiet_hours_end,
                    allow_quiet_hours=current_user.allow_quiet_hours,
                    timezone_str=current_user.timezone,
                )

                if adjusted:
                    any_adjusted = True
                    all_reasons.append(reason)

                task = Task(
                    goal_id=goal.id,
                    description=t["description"],
                    criteria=t["criteria"],
                    planned_start_at=new_start,
                    planned_end_at=new_end,
                    scheduled_date=target_date,
                )
                db.add(task)
                await db.flush()
                await db.refresh(task)

                saved_items.append(DispatchMoreTaskItem(
                    id=task.id,
                    description=task.description,
                    criteria=task.criteria,
                    planned_start_at=new_start.isoformat() if new_start else None,
                    planned_end_at=new_end.isoformat() if new_end else None,
                    status="pending",
                ))

            await db.commit()

            logger.info("加餐任务生成成功: goal_id=%d, tasks=%d", goal.id, len(saved_items))

            return DispatchMoreResponse(
                tasks=saved_items,
                time_adjusted=any_adjusted,
                adjusted_reason="；".join(all_reasons) if all_reasons else "",
            )

        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            logger.warning("加餐任务第 %d 次生成失败: %s", attempt + 1, e)
        except Exception as e:
            logger.error("加餐任务 LLM 调用失败: %s", e)
            raise HTTPException(status_code=502, detail=f"AI 服务暂时不可用: {e}") from e

    raise HTTPException(
        status_code=500,
        detail=f"AI 生成加餐任务失败（已重试 1 次）：{last_error}",
    )


# 请求体定义（放在文件底部避免循环导入）
class DispatchMoreRequest(BaseModel):
    """加餐任务请求体。"""
    goal_id: int = Field(..., description="目标 ID")
    date: str | None = Field(None, description="目标日期（YYYY-MM-DD），默认今天")
    user_feedback: str | None = Field(None, description="用户反馈（可选）")
