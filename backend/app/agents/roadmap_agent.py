"""
Roadmap Agent（路线图智能体）

设计意图：
    为长期目标生成结构化的学习路线图（Roadmap），
    并生成摘要供前端展示。

改动原因：
    Roadmap 稳定，避免一次性生成 60 天任务的漂移与成本。
"""

import json
import logging
from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field, ValidationError

from app.agents.prompts.roadmap_prompt import (
    ROADMAP_SUMMARY_PROMPT,
    ROADMAP_SYSTEM_PROMPT,
)
from app.core.config import settings
from app.core.llm import get_llm_client

logger = logging.getLogger(__name__)


class _WeekPlan(BaseModel):
    """单周计划。"""
    week_index: int = Field(..., ge=1, description="周索引，从1开始")
    theme: str = Field(..., min_length=1, description="本周主题")
    outcomes: str = Field(..., min_length=1, description="本周预期成果")
    focus_skills: list[str] = Field(..., min_length=1, description="重点技能列表")


class _DailyDispatchRules(BaseModel):
    """每日派发规则。"""
    tasks_per_day: int = Field(..., ge=1, le=10, description="每天建议任务数")
    time_window_hint: str = Field(..., description="时间窗建议")
    quiet_hours_note: str = Field(..., description="休息时间约束说明")


class _Roadmap(BaseModel):
    """完整的 Roadmap 结构。"""
    title: str = Field(..., min_length=1, description="路线图标题")
    duration_days: int = Field(..., ge=1, description="总天数")
    weeks: list[_WeekPlan] = Field(..., min_length=1, description="按周划分的学习计划")
    daily_dispatch_rules: _DailyDispatchRules = Field(..., description="每日派发规则")


class RoadmapAgent:
    """路线图智能体，负责生成和管理长期目标的学习路线图。"""

    @staticmethod
    async def generate_roadmap(goal_content: str, duration_days: int) -> dict:
        """
        为长期目标生成结构化 Roadmap。

        Args:
            goal_content: 用户的目标内容
            duration_days: 目标持续天数

        Returns:
            Roadmap 字典（已通过 Pydantic 校验）

        Raises:
            ValueError: LLM 返回格式不正确
            RuntimeError: LLM 服务调用失败
        """
        client = get_llm_client()
        user_message = (
            f"用户目标：{goal_content}\n\n"
            f"目标持续天数：{duration_days} 天\n\n"
            f"请为这个长期目标生成一份结构化的学习路线图。"
        )

        logger.info("RoadmapAgent: 开始生成 Roadmap，目标='%s'，天数=%d", goal_content[:50], duration_days)

        last_error = None
        for attempt in range(2):
            try:
                response = await client.chat.completions.create(
                    model=settings.llm_model,
                    messages=[
                        {"role": "system", "content": ROADMAP_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=settings.llm_temperature,
                    max_tokens=4000,
                )

                raw_content = (response.choices[0].message.content or "").strip()

                # 提取 JSON
                if raw_content.startswith("```"):
                    lines = raw_content.split("\n")
                    json_lines = [l for l in lines if not l.strip().startswith("```")]
                    raw_content = "\n".join(json_lines).strip()

                parsed = json.loads(raw_content)
                roadmap = _Roadmap.model_validate(parsed)

                logger.info("RoadmapAgent: Roadmap 生成成功，共 %d 周 (attempt %d)", len(roadmap.weeks), attempt + 1)
                return roadmap.model_dump()

            except json.JSONDecodeError as e:
                last_error = f"LLM 返回的不是有效 JSON: {e}"
                logger.warning("RoadmapAgent: 第 %d 次解析失败: %s", attempt + 1, last_error)
            except ValidationError as e:
                last_error = f"LLM 返回的 Roadmap 格式校验失败: {e}"
                logger.warning("RoadmapAgent: 第 %d 次校验失败: %s", attempt + 1, last_error)
            except Exception as e:
                logger.error("RoadmapAgent: LLM API 调用失败: %s", e)
                raise RuntimeError(f"LLM 服务调用失败: {e}") from e

        raise ValueError(f"RoadmapAgent 无法生成有效 Roadmap（已重试 1 次）。最后错误: {last_error}")

    @staticmethod
    async def generate_summary(roadmap_json: dict) -> str:
        """
        根据 Roadmap JSON 生成前端展示用的摘要。

        Args:
            roadmap_json: Roadmap 字典

        Returns:
            中文摘要文本（3-5句话）
        """
        client = get_llm_client()
        user_message = ROADMAP_SUMMARY_PROMPT.format(roadmap_json=json.dumps(roadmap_json, ensure_ascii=False, indent=2))

        try:
            response = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
                max_tokens=500,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            logger.error("RoadmapAgent: 摘要生成失败: %s", e)
            # 降级：使用标题作为摘要
            return f"长期计划：{roadmap_json.get('title', '未知')}，共 {roadmap_json.get('duration_days', 0)} 天"
