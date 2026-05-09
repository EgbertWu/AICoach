"""
对话式计划智能体 (Chat Planner Agent)

改动原因：
    把"长短期判断"从关键词规则升级为"对话驱动 + 用户确认"，更符合产品体验。
    通过多轮对话收集必要参数，最终由用户确认后生成计划。
"""

import json
import logging
from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings
from app.core.llm import get_llm_client

logger = logging.getLogger(__name__)


class _ChatAgentOutput(BaseModel):
    """
    LLM 对话步骤的结构化输出。

    改动原因：所有 LLM 输出必须 Pydantic 校验后才能使用。
    """
    plan_mode: str = Field(..., description="计划模式：daily / long_term / unknown")
    confidence: float = Field(..., ge=0, le=1, description="判断置信度 0~1")
    questions: list[str] = Field(default_factory=list, description="还需要追问的问题列表")
    extracted: "ExtractedConstraints" = Field(default_factory=lambda: ExtractedConstraints(), description="已提取的约束信息")
    ready_to_finalize: bool = Field(False, description="是否准备好生成计划")
    final_prompt_to_user: str = Field("", description="引导用户确认的文案")
    response_to_user: str = Field(..., min_length=1, description="对用户的回复文本")

    # 改动原因：LLM 可能返回 null 而非空字符串，需要容错处理
    @classmethod
    def model_validate(cls, obj):
        """校验并容错处理 LLM 返回的 null 值。"""
        if isinstance(obj, dict):
            obj = {**obj}
            # 将 null 的字符串字段替换为空字符串
            for field_name in ("final_prompt_to_user", "response_to_user"):
                if obj.get(field_name) is None:
                    obj[field_name] = ""
            # 确保列表字段不为 null
            if obj.get("questions") is None:
                obj["questions"] = []
            if obj.get("extracted") is None:
                obj["extracted"] = {}
        return super().model_validate(obj)


class ExtractedConstraints(BaseModel):
    """
    从对话中提取的约束信息。

    改动原因：结构化存储用户意图，供 finalize 时直接使用。
    """
    goal_summary: str | None = Field(None, description="目标摘要")
    duration_days: int | None = Field(None, description="长期目标天数")
    start_date: str | None = Field(None, description="开始日期")
    preferred_time_windows: str | None = Field(None, description="偏好的时间窗")
    allow_quiet_hours: bool | None = Field(None, description="是否允许夜间安排")


# System Prompt for the chat planner agent
_CHAT_PLANNER_SYSTEM_PROMPT = """你是一位专业的 AI 执行力教练。你的任务是通过与用户对话，了解他们的目标，并判断这是短期目标（今天完成）还是长期目标（需要多天/多周规划）。

## 你的工作流程

1. **理解用户意图**：仔细倾听用户描述的目标
2. **判断计划类型**：
   - 如果目标可以在一天内完成 → `plan_mode: "daily"`
   - 如果目标需要多天或多周 → `plan_mode: "long_term"`
   - 如果信息不足无法判断 → `plan_mode: "unknown"`
3. **收集必要信息**：
   - 对于 daily：确认目标内容是否清晰
   - 对于 long_term：需要知道预计时长（天数/周数）、开始时间
4. **引导确认**：当信息充分时，设置 `ready_to_finalize: true` 并给出确认文案

## Quiet Hours 规则
- 用户的休息时间段在下方"当前用户偏好"中标注
- 如果当前时间正处于休息时间段内，且用户偏好不允许夜间安排（"允许夜间安排：否"）：
  - **必须拒绝生成计划**，直接告知用户当前是休息时间，建议明天再安排
  - 不要询问"你确定现在开始吗？"，不要设置 `allow_quiet_hours: true`
  - 可以正常聊天，但 `ready_to_finalize` 必须保持 `false`
- 只有当用户偏好明确允许夜间安排（"允许夜间安排：是"）时，才可以在休息时间段内安排任务

## 计划互斥原则（非常重要）
- 同一时间只能有一个进行中的计划
- 如果用户已有未完成的任务，你必须在回复中明确提醒用户
- 建议用户先完成现有任务再开始新计划，或确认要替换当前计划

## 回复风格
- 友好、专业、简洁
- 每次回复控制在 3-5 句话
- 不要重复用户已说过的内容
- 用引导性问题推进对话

## 重要约束
- 你必须输出严格的 JSON 格式
- 不要编造用户没有提到的信息
- 当 `ready_to_finalize: true` 时，`final_prompt_to_user` 必须包含目标摘要供用户确认
"""

_CHAT_PLANNER_FINALIZE_PROMPT = """基于以下对话历史，请提取最终的计划生成参数。

要求：
1. goal_summary：用一句话概括用户的目标
2. duration_days：如果是长期目标，提取预计天数（没有则默认 30）
3. start_date：开始日期（默认今天 {today}）
4. allow_quiet_hours：用户是否明确要求夜间安排

只输出 JSON，不要其他内容。"""


class ChatPlannerAgent:
    """
    对话式计划智能体。

    改动原因：通过多轮对话判断短期/长期并收集参数，替代原有的表单式输入。
    """

    @staticmethod
    def _build_messages(
        session_messages: list[dict],
        user_prefs: dict | None = None,
    ) -> list[dict]:
        """
        构造发送给 LLM 的消息列表。

        Args:
            session_messages: 会话历史消息 [{role, content}, ...]
            user_prefs: 用户偏好 {quiet_hours_start, quiet_hours_end, allow_quiet_hours, timezone}

        Returns:
            完整的消息列表（含 system prompt）
        """
        messages = [{"role": "system", "content": _CHAT_PLANNER_SYSTEM_PROMPT}]

        # 注入用户偏好作为 system 上下文
        if user_prefs:
            prefs_text = (
                f"\n\n## 当前用户偏好\n"
                f"- 休息时间：{user_prefs.get('quiet_hours_start', '23:00')} - {user_prefs.get('quiet_hours_end', '06:00')}\n"
                f"- 允许夜间安排：{'是' if user_prefs.get('allow_quiet_hours') else '否'}\n"
                f"- 时区：{user_prefs.get('timezone', 'Asia/Shanghai')}\n"
                f"- 当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            )
            # 改动原因：将冲突信息注入 prompt，让 LLM 在对话中主动提醒用户
            if user_prefs.get("conflict_warning"):
                prefs_text += f"\n## ⚠️ 计划冲突警告\n{user_prefs['conflict_warning']}\n"
            messages[0]["content"] += prefs_text

        # 添加对话历史
        for msg in session_messages:
            if msg["role"] in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"]})

        return messages

    @staticmethod
    def _parse_response(raw_content: str) -> dict:
        """
        解析 LLM 的结构化 JSON 响应。

        改动原因：确保 LLM 输出经过 Pydantic 校验后才能使用。

        Args:
            raw_content: LLM 原始响应文本

        Returns:
            校验后的字典

        Raises:
            ValueError: 解析或校验失败
        """
        cleaned = raw_content.strip()
        # 提取 JSON（可能被 markdown 代码块包裹）
        if "```" in cleaned:
            lines = cleaned.split("\n")
            json_lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(json_lines).strip()
            # 如果有多余文本，尝试提取 JSON 部分
            json_start = cleaned.find("{")
            json_end = cleaned.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                cleaned = cleaned[json_start:json_end]

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM 返回的不是有效 JSON: {e}") from e

        try:
            output = _ChatAgentOutput.model_validate(parsed)
            return output.model_dump()
        except ValidationError as e:
            raise ValueError(f"LLM 输出格式校验失败: {e}") from e

    async def step(
        self,
        session_messages: list[dict],
        user_prefs: dict | None = None,
    ) -> dict:
        """
        执行一步对话推理。

        改动原因：每次用户发送消息后调用，返回助手回复和会话状态。

        Args:
            session_messages: 会话历史消息 [{role, content}, ...]
            user_prefs: 用户偏好

        Returns:
            {
                assistant_text: str,        # 助手回复文本
                plan_mode: str,             # 当前计划模式
                ready_to_finalize: bool,    # 是否准备好生成
                extracted: dict,            # 提取的约束
                next_questions: list[str],  # 还需要追问的问题
                final_prompt_to_user: str,  # 确认文案
            }

        Raises:
            ValueError: LLM 返回格式不正确
            RuntimeError: LLM 服务调用失败
        """
        messages = self._build_messages(session_messages, user_prefs)

        # 在最后一条用户消息后追加 JSON 输出指令
        messages.append({
            "role": "user",
            "content": (
                "\n\n---\n请以上面的 JSON 格式回复（包含 plan_mode, confidence, questions, extracted, "
                "ready_to_finalize, final_prompt_to_user, response_to_user 字段）。"
                "注意：response_to_user 是你给用户的自然语言回复，其他字段是结构化数据。"
            ),
        })

        logger.info("ChatPlannerAgent: 开始对话推理，消息数=%d", len(session_messages))

        client = get_llm_client()
        last_error = None

        for attempt in range(2):
            try:
                response = await client.chat.completions.create(
                    model=settings.llm_model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=1500,
                )

                raw_content = response.choices[0].message.content or ""
                result = self._parse_response(raw_content)

                logger.info(
                    "ChatPlannerAgent: 推理完成 (attempt %d), mode=%s, ready=%s",
                    attempt + 1,
                    result.get("plan_mode"),
                    result.get("ready_to_finalize"),
                )

                return {
                    "assistant_text": result.get("response_to_user", ""),
                    "plan_mode": result.get("plan_mode", "unknown"),
                    "ready_to_finalize": result.get("ready_to_finalize", False),
                    "extracted": result.get("extracted", {}),
                    "next_questions": result.get("questions", []),
                    "final_prompt_to_user": result.get("final_prompt_to_user", ""),
                }

            except ValueError as e:
                last_error = e
                logger.warning("ChatPlannerAgent: 第 %d 次解析失败: %s", attempt + 1, e)
            except Exception as e:
                logger.error("ChatPlannerAgent: LLM API 调用失败: %s", e)
                raise RuntimeError(f"LLM 服务调用失败: {e}") from e

        raise ValueError(f"ChatPlannerAgent 对话推理失败（已重试 1 次）。最后错误: {last_error}")

    async def extract_final_constraints(
        self,
        session_messages: list[dict],
    ) -> dict:
        """
        从对话历史中提取最终的计划生成参数。

        改动原因：finalize 时需要结构化的参数来调用现有的计划生成逻辑。

        Args:
            session_messages: 完整的对话历史

        Returns:
            {
                goal_summary: str,
                duration_days: int | None,
                start_date: str,
                allow_quiet_hours: bool,
            }
        """
        messages = [
            {"role": "system", "content": _CHAT_PLANNER_FINALIZE_PROMPT.replace("{today}", date.today().isoformat())},
        ]

        # 添加对话历史作为上下文
        conversation_text = "\n".join(
            f"[{m['role']}]: {m['content']}" for m in session_messages
        )
        messages.append({"role": "user", "content": f"## 对话历史\n{conversation_text}"})

        logger.info("ChatPlannerAgent: 提取最终约束参数")

        client = get_llm_client()
        last_error = None

        for attempt in range(2):
            try:
                response = await client.chat.completions.create(
                    model=settings.llm_model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=500,
                )

                raw_content = (response.choices[0].message.content or "").strip()
                if "```" in raw_content:
                    lines = raw_content.split("\n")
                    json_lines = [l for l in lines if not l.strip().startswith("```")]
                    raw_content = "\n".join(json_lines).strip()
                    json_start = raw_content.find("{")
                    json_end = raw_content.rfind("}") + 1
                    if json_start >= 0 and json_end > json_start:
                        raw_content = raw_content[json_start:json_end]

                parsed = json.loads(raw_content)

                # 使用 ExtractedConstraints 校验
                constraints = ExtractedConstraints.model_validate(parsed)

                result = constraints.model_dump()
                # 确保有默认值
                result.setdefault("goal_summary", "用户目标")
                result.setdefault("duration_days", None)
                result.setdefault("start_date", date.today().isoformat())
                result.setdefault("allow_quiet_hours", False)

                logger.info("ChatPlannerAgent: 约束提取成功: %s", result)
                return result

            except (json.JSONDecodeError, ValidationError) as e:
                last_error = e
                logger.warning("ChatPlannerAgent: 第 %d 次提取失败: %s", attempt + 1, e)
            except Exception as e:
                logger.error("ChatPlannerAgent: LLM API 调用失败: %s", e)
                raise RuntimeError(f"LLM 服务调用失败: {e}") from e

        # 降级：从对话历史中简单提取
        logger.warning("ChatPlannerAgent: 约束提取失败，使用降级方案")
        user_messages = [m["content"] for m in session_messages if m["role"] == "user"]
        goal_summary = user_messages[0] if user_messages else "用户目标"
        return {
            "goal_summary": goal_summary[:500],
            "duration_days": None,
            "start_date": date.today().isoformat(),
            "allow_quiet_hours": False,
        }
