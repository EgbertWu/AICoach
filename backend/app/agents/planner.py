"""
Planner Agent (规划器智能体)

设计意图：
    将用户的模糊目标拆解为具体、可执行、带时间窗口的任务列表。

    Phase 10 更新说明：
    - _LLMTaskItem 使用 planned_start_at / planned_end_at (datetime)
    - Prompt 注入当天日期，确保 LLM 生成的时间窗口合理
    - 移除 start_time / end_time (String)
"""

import json
import logging
import re
from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field, ValidationError

from app.agents.prompts.planner_prompt import PLANNER_SYSTEM_PROMPT
from app.core.config import settings
from app.core.llm import get_llm_client

logger = logging.getLogger(__name__)


class _LLMTaskItem(BaseModel):
    """LLM 返回的单条任务格式。"""
    description: str = Field(..., min_length=1, max_length=1000)
    criteria: str = Field(..., min_length=1, max_length=1000)
    planned_start_at: datetime | None = Field(None, description="计划开始时间")
    planned_end_at: datetime | None = Field(None, description="计划截止时间")


class _LLMTaskList(BaseModel):
    """LLM 返回的任务列表格式。"""
    tasks: list[_LLMTaskItem] = Field(..., min_length=1, max_length=5)


_INJECTION_PATTERNS = re.compile(
    r"(?i)"
    r"(忽略|ignore)\s*(之前|previous|all)\s*(的|the)?\s*(指令|instructions?|rules?|prompt)"
    r"|(你|you)\s*(现在|are)\s*(是|a)\s*(写代码|code|evil|hacker)"
    r"|system\s*prompt"
    r"|forget\s*(everything|all)"
    r"|pretend\s*(you|to\s*be)"
    r"|act\s*as\s*if",
)


class PlannerAgent:
    """规划器智能体。"""

    @staticmethod
    def _sanitize_input(goal_content: str) -> str:
        """对用户输入进行安全清理（Prompt 注入防御）。"""
        if len(goal_content) > 2000:
            logger.warning("用户目标内容过长 (%d 字符)，已截断", len(goal_content))
            goal_content = goal_content[:2000]

        if _INJECTION_PATTERNS.search(goal_content):
            logger.warning("检测到可能的 Prompt 注入尝试: %s", goal_content[:100])

        return goal_content.strip()

    @staticmethod
    def _parse_llm_response(raw_content: str) -> list[dict]:
        """
        解析 LLM 的原始响应文本为结构化任务列表。

        改动原因：支持两种 LLM 输出格式：
        1. ISO datetime（如 "2026-05-02T09:00:00"）→ 直接解析
        2. HH:MM 字符串（如 "09:00"）→ 转换为当天 datetime
        """
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
            if isinstance(parsed, list):
                task_list = _LLMTaskList(tasks=parsed)
            elif isinstance(parsed, dict) and "tasks" in parsed:
                task_list = _LLMTaskList(tasks=parsed["tasks"])
            else:
                raise ValueError(f"LLM 返回的 JSON 格式不符合预期: {type(parsed)}")

            today = date.today()

            return [
                {
                    "description": t.description,
                    "criteria": t.criteria,
                    "planned_start_at": t.planned_start_at.isoformat() if t.planned_start_at else None,
                    "planned_end_at": t.planned_end_at.isoformat() if t.planned_end_at else None,
                }
                for t in task_list.tasks
            ]
        except ValidationError as e:
            raise ValueError(f"LLM 返回的任务格式校验失败: {e}") from e

    async def generate_tasks_from_goal(
        self,
        goal_content: str,
        context: str | None = None,
        quiet_hours_start: str = "23:00",
        quiet_hours_end: str = "06:00",
    ) -> list[dict]:
        """
        将用户的自然语言目标拆解为结构化任务列表。

        改动原因：Prompt 中注入当天日期、当前时间、对话上下文，确保时间窗口合理且任务贴合用户意图。
        
        Args:
            goal_content: 用户目标描述
            context: 对话上下文（从聊天历史中提取的关键信息），可选
        """
        sanitized = self._sanitize_input(goal_content)
        if not sanitized:
            raise ValueError("目标内容不能为空")

        # 注入当天日期和起始时间到 Prompt
        # 改动原因：起始时间动态化为当前时间 +30 分钟，
        # 避免生成已过期的任务（如当前 9:53 还生成 9:00 的计划）
        now = datetime.now()
        today_str = now.date().isoformat()
        current_time_str = now.strftime("%H:%M")
        # 向上取整到下一个整点，再加 30 分钟作为起始时间
        start_dt = now.replace(minute=0, second=0, microsecond=0)
        if now.minute >= 30:
            start_dt = start_dt.replace(hour=start_dt.hour + 1)
        start_dt = start_dt + timedelta(minutes=30)
        start_time_str = start_dt.strftime("%H:%M")

        system_prompt = (
            PLANNER_SYSTEM_PROMPT
            .replace("{{today}}", today_str)
            .replace("{{start_time}}", start_time_str)
            .replace("{{current_time}}", current_time_str)
            .replace("{{quiet_hours_start}}", quiet_hours_start)
            .replace("{{quiet_hours_end}}", quiet_hours_end)
        )

        # 改动原因：如果有对话上下文，注入到 prompt 中让 LLM 参考用户的具体需求
        if context and context.strip():
            context_section = (
                f"## 用户对话上下文（请务必参考这些信息来生成任务）\n\n{context.strip()}\n\n"
                "请根据以上对话中用户提到的具体安排和偏好来生成任务，"
                "不要忽略用户已经明确说明的计划。"
            )
            system_prompt = system_prompt.replace("{{context_section}}", context_section)
        else:
            system_prompt = system_prompt.replace("{{context_section}}", "")

        client = get_llm_client()
        user_message = f"用户目标：{sanitized}\n\n请为这个目标生成 3-5 个具体任务。"

        logger.info("PlannerAgent: 开始生成任务，目标='%s'", sanitized[:50])

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
                    max_tokens=settings.llm_max_tokens,
                )

                raw_content = response.choices[0].message.content or ""

                tasks = self._parse_llm_response(raw_content)

                logger.info("PlannerAgent: 成功生成 %d 个任务 (attempt %d)", len(tasks), attempt + 1)
                return tasks

            except ValueError as e:
                last_error = e
                logger.warning("PlannerAgent: 第 %d 次尝试解析失败: %s", attempt + 1, e)
            except Exception as e:
                logger.error("PlannerAgent: LLM API 调用失败: %s", e)
                raise RuntimeError(f"LLM 服务调用失败: {e}") from e

        raise ValueError(f"PlannerAgent 无法生成有效任务（已重试 1 次）。最后错误: {last_error}")
