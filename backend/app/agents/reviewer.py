"""
Reviewer Agent (复盘智能体)

Phase 10 更新说明：
- _build_user_message 包含每个任务的超时上下文（is_late、completion_reason）
- 为 Review Agent 提供高质量上下文，支持"超时原因归因"
"""

import json
import logging

from pydantic import BaseModel, Field, ValidationError

from app.agents.prompts.reviewer_prompt import REVIEWER_SYSTEM_PROMPT
from app.core.config import settings
from app.core.llm import get_llm_client
from app.db.models.task import Task

logger = logging.getLogger(__name__)


class _ReviewOutput(BaseModel):
    """LLM 返回的复盘格式。"""
    completion_rate: float = Field(..., ge=0, le=100)
    analysis: str = Field(..., min_length=10, max_length=2000)
    suggestions: str = Field(..., min_length=10, max_length=2000)


class ReviewerAgent:
    """复盘智能体。"""

    @staticmethod
    def _build_user_message(goal_content: str, tasks: list[Task]) -> str:
        """
        构造复盘的用户消息。

        Phase 10 改动原因：
        包含每个任务的 planned_end_at、completed_at、is_late、completion_reason，
        为 AI 提供超时上下文，即使 completion_reason 为空也能分析。
        """
        from datetime import datetime

        now = datetime.now()
        per_day: dict[str, dict[str, int]] = {}
        task_lines = []

        for i, task in enumerate(tasks, 1):
            date_key = task.scheduled_date.isoformat() if getattr(task, "scheduled_date", None) else "未设置日期"
            day_row = per_day.get(date_key) or {"total": 0, "completed": 0, "late": 0}
            day_row["total"] += 1

            # 判断是否超时
            is_late = False
            if task.planned_end_at:
                if task.status.value == "completed" and task.completed_at:
                    is_late = task.completed_at > task.planned_end_at
                elif task.status.value == "pending":
                    is_late = now > task.planned_end_at

            if task.status.value == "completed":
                day_row["completed"] += 1
            if is_late:
                day_row["late"] += 1
            per_day[date_key] = day_row

            line = (
                f"### 任务 {i}: {task.description}\n"
                f"- 完成标准：{task.criteria}\n"
                f"- 状态：{task.status.value}\n"
                f"- 归属日期：{date_key}\n"
            )

            if task.planned_start_at:
                line += f"- 计划开始：{task.planned_start_at.strftime('%H:%M')}\n"
            if task.planned_end_at:
                line += f"- 计划截止：{task.planned_end_at.strftime('%H:%M')}\n"
            if task.completed_at:
                line += f"- 实际完成：{task.completed_at.strftime('%H:%M')}\n"
            line += f"- 是否超时：{'是' if is_late else '否'}\n"
            line += f"- 超时原因：{task.completion_reason if task.completion_reason else '（用户未填写）'}\n"

            task_lines.append(line)

        summary_lines = []
        for k in sorted(per_day.keys()):
            row = per_day[k]
            total = row["total"]
            completed = row["completed"]
            rate = int(round((completed / total) * 100)) if total > 0 else 0
            summary_lines.append(f"- {k}：完成 {completed}/{total}（{rate}%），超时 {row['late']}")

        tasks_text = "\n".join(task_lines)
        summary_text = "\n".join(summary_lines) if summary_lines else "（无）"

        return (
            f"## 用户目标\n{goal_content}\n\n"
            f"## 按日期汇总\n{summary_text}\n\n"
            f"## 任务执行情况\n{tasks_text}\n\n"
            f"请按日期分别总结（优劣势/原因），最后给出综合结论与下一步建议。"
        )

    @staticmethod
    def _parse_llm_response(raw_content: str) -> dict:
        """解析 LLM 的复盘响应。"""
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            json_lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(json_lines).strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM 返回的不是有效 JSON: {e}") from e

        try:
            review = _ReviewOutput.model_validate(parsed)
            return {
                "completion_rate": review.completion_rate,
                "analysis": review.analysis,
                "suggestions": review.suggestions,
            }
        except ValidationError as e:
            raise ValueError(f"LLM 返回的复盘格式校验失败: {e}") from e

    async def generate_review(self, goal_content: str, tasks: list[Task]) -> dict:
        """生成复盘分析。"""
        user_message = self._build_user_message(goal_content, tasks)

        logger.info("ReviewerAgent: 开始生成复盘，tasks_count=%d", len(tasks))

        last_error = None
        for attempt in range(2):
            try:
                client = get_llm_client()
                response = await client.chat.completions.create(
                    model=settings.llm_model,
                    messages=[
                        {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=settings.llm_temperature,
                    max_tokens=settings.llm_max_tokens,
                )

                raw_content = response.choices[0].message.content or ""
                result = self._parse_llm_response(raw_content)

                logger.info("ReviewerAgent: 复盘生成成功 (attempt %d)", attempt + 1)
                return result

            except ValueError as e:
                last_error = e
                logger.warning("ReviewerAgent: 第 %d 次解析失败: %s", attempt + 1, e)
            except Exception as e:
                logger.error("ReviewerAgent: LLM API 调用失败: %s", e)
                raise RuntimeError(f"LLM 服务调用失败: {e}") from e

        raise ValueError(f"ReviewerAgent 无法生成复盘（已重试 1 次）。最后错误: {last_error}")
