"""
每日派发服务 (Daily Dispatch Service)

设计意图：
    根据长期目标的 Roadmap 和当日上下文，生成当天可执行的任务列表。
    支持根据近期完成率和用户反馈滚动调整。

改动原因：
    长期目标要"每天生成当天可执行任务"，并能根据反馈滚动调整。
    先在 prompt 中约束 quiet hours，再走后端 normalize 校验兜底。
"""

import json
import logging
from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field, ValidationError

from app.agents.prompts.dispatch_prompt import DAILY_DISPATCH_SYSTEM_PROMPT
from app.core.config import settings
from app.core.llm import get_llm_client
from app.core.time_prefs import normalize_planned_window

logger = logging.getLogger(__name__)


class _DispatchTaskItem(BaseModel):
    """LLM 返回的单条派发任务格式。"""
    description: str = Field(..., min_length=1, max_length=1000)
    criteria: str = Field(..., min_length=1, max_length=1000)
    planned_start_at: datetime | None = Field(None, description="计划开始时间")
    planned_end_at: datetime | None = Field(None, description="计划截止时间")


class _DispatchTaskList(BaseModel):
    """LLM 返回的派发任务列表格式。"""
    tasks: list[_DispatchTaskItem] = Field(..., min_length=1, max_length=5)


async def dispatch_daily_tasks(
    roadmap_json: dict,
    target_date: date,
    quiet_hours_start: str = "23:00",
    quiet_hours_end: str = "06:00",
    allow_quiet_hours: bool = False,
    user_feedback: str | None = None,
    recent_completion_rate: float | None = None,
    completed_tasks: list[dict] | None = None,
    last_dispatch_date: str | None = None,
) -> list[dict]:
    """
    根据长期目标的 Roadmap 为指定日期生成当日任务。

    流程：
    1. 确定当前所在周的主题和目标
    2. 构造包含上下文的 Prompt（含 quiet hours 约束）
    3. 调用 LLM 生成任务
    4. Pydantic 校验
    5. 后端兜底：normalize_planned_window 确保时间窗合规

    Args:
        roadmap_json: Roadmap 字典
        target_date: 目标日期
        quiet_hours_start: 休息开始时间
        quiet_hours_end: 休息结束时间
        allow_quiet_hours: 是否允许在休息时间安排任务
        user_feedback: 用户反馈（可选）
        recent_completion_rate: 近期完成率（可选，0-100）

    Returns:
        任务字典列表，每项包含 description, criteria, planned_start_at, planned_end_at
        所有时间窗已经过后端兜底校验

    Raises:
        ValueError: LLM 返回格式不正确
        RuntimeError: LLM 服务调用失败
    """
    # 1. 确定当前所在周
    start_date_str = roadmap_json.get("start_date")
    if start_date_str:
        start_date = date.fromisoformat(start_date_str)
    else:
        start_date = target_date

    days_elapsed = (target_date - start_date).days
    current_week_index = max(1, days_elapsed // 7 + 1)

    weeks = roadmap_json.get("weeks", [])
    current_week = None
    for week in weeks:
        if week.get("week_index") == current_week_index:
            current_week = week
            break
    # 如果找不到精确匹配，取最近的周
    if not current_week and weeks:
        current_week = weeks[-1]

    # 2. 构造 quiet hours 约束
    if allow_quiet_hours:
        quiet_constraint = "用户允许在任意时间安排任务，无休息时间限制。"
    else:
        quiet_constraint = (
            f"严禁在 {quiet_hours_start} 到 {quiet_hours_end} 之间安排任务。"
            f"所有任务的 planned_start_at 和 planned_end_at 必须在 {quiet_hours_end} 到 {quiet_hours_start} 之间。"
        )

    # 3. 构造 Prompt
    today_str = target_date.isoformat()
    now = datetime.now()
    start_dt = now.replace(minute=0, second=0, microsecond=0)
    if now.minute >= 30:
        start_dt = start_dt.replace(hour=start_dt.hour + 1)
    start_dt = start_dt + timedelta(minutes=30)
    start_time_str = start_dt.strftime("%H:%M")

    system_prompt = (
        DAILY_DISPATCH_SYSTEM_PROMPT
        .replace("{{today}}", today_str)
        .replace("{{start_time}}", start_time_str)
        .replace("{{quiet_hours_constraint}}", quiet_constraint)
    )

    # 构造用户消息
    context_parts = [
        f"## 长期目标\n{roadmap_json.get('title', '未知')}",
        f"## 当前进度\n第 {current_week_index} 周",
    ]

    if current_week:
        context_parts.append(f"## 本周主题\n{current_week.get('theme', '未知')}")
        context_parts.append(f"## 本周目标\n{current_week.get('outcomes', '未知')}")
        skills = current_week.get("focus_skills", [])
        if skills:
            context_parts.append(f"## 重点技能\n{', '.join(skills)}")

    if recent_completion_rate is not None:
        context_parts.append(f"## 近期完成率\n{recent_completion_rate:.0f}%")

    if last_dispatch_date:
        context_parts.append(f"## 上次派发日期\n{last_dispatch_date}")

    if completed_tasks:
        lines = []
        for item in completed_tasks[:20]:
            d = item.get("scheduled_date") or item.get("completed_at") or ""
            desc = (item.get("description") or "").strip()
            if not desc:
                continue
            lines.append(f"- {d} {desc}")
        if lines:
            context_parts.append("## 已完成内容（避免重复，推进下一步）\n" + "\n".join(lines))

    if user_feedback:
        context_parts.append(f"## 用户反馈\n{user_feedback}")

    user_message = (
        "\n\n".join(context_parts)
        + "\n\n请为今天生成具体的可执行任务。"
        + "\n\n要求：优先推进未完成的新内容，避免重复已完成内容；如果需要复习巩固，请控制在少量且明确写明“巩固原因”。"
    )

    logger.info("DispatchService: 开始派发每日任务，日期=%s，周=%d", target_date, current_week_index)

    # 4. 调用 LLM
    client = get_llm_client()
    last_error = None
    for attempt in range(2):
        try:
            response = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=settings.llm_temperature,
                max_tokens=2000,
            )

            raw_content = (response.choices[0].message.content or "").strip()

            # 提取 JSON
            if raw_content.startswith("```"):
                lines = raw_content.split("\n")
                json_lines = [l for l in lines if not l.strip().startswith("```")]
                raw_content = "\n".join(json_lines).strip()

            parsed = json.loads(raw_content)

            if isinstance(parsed, list):
                task_list = _DispatchTaskList(tasks=parsed)
            elif isinstance(parsed, dict) and "tasks" in parsed:
                task_list = _DispatchTaskList(tasks=parsed["tasks"])
            else:
                raise ValueError(f"LLM 返回的 JSON 格式不符合预期: {type(parsed)}")

            # 5. 后端兜底：normalize 时间窗
            result_tasks = []
            for t in task_list.tasks:
                new_start, new_end, adjusted, reason = normalize_planned_window(
                    planned_start_at=t.planned_start_at,
                    planned_end_at=t.planned_end_at,
                    quiet_hours_start=quiet_hours_start,
                    quiet_hours_end=quiet_hours_end,
                    allow_quiet_hours=allow_quiet_hours,
                )
                if adjusted:
                    logger.info("DispatchService: 时间窗已修正 - %s", reason)

                result_tasks.append({
                    "description": t.description,
                    "criteria": t.criteria,
                    "planned_start_at": new_start.isoformat() if new_start else None,
                    "planned_end_at": new_end.isoformat() if new_end else None,
                    "time_adjusted": adjusted,
                    "adjusted_reason": reason,
                })

            logger.info("DispatchService: 成功派发 %d 个任务 (attempt %d)", len(result_tasks), attempt + 1)
            return result_tasks

        except json.JSONDecodeError as e:
            last_error = f"LLM 返回的不是有效 JSON: {e}"
            logger.warning("DispatchService: 第 %d 次解析失败: %s", attempt + 1, last_error)
        except ValidationError as e:
            last_error = f"LLM 返回的任务格式校验失败: {e}"
            logger.warning("DispatchService: 第 %d 次校验失败: %s", attempt + 1, last_error)
        except Exception as e:
            logger.error("DispatchService: LLM API 调用失败: %s", e)
            raise RuntimeError(f"LLM 服务调用失败: {e}") from e

    raise ValueError(f"DispatchService 无法生成有效任务（已重试 1 次）。最后错误: {last_error}")
