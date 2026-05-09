"""
任务事件表 (Task Event / Audit Log)

设计意图：
    记录长期任务的关键历史：生成、编辑、完成、删除、派发等用户/系统动作，
    为“任务不会重复生成”和“状态可解释”提供可追溯性。

改动原因：
    仅靠 tasks 当前状态无法回答“什么时候生成的、用户做了什么操作、为何状态变更”，
    影响问题定位和复盘可信度，因此引入轻量审计表。
"""

from __future__ import annotations

import enum
import json
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin


class TaskEventType(str, enum.Enum):
    """任务事件类型。"""

    CREATED = "created"
    UPDATED = "updated"
    COMPLETED = "completed"
    DELETED = "deleted"
    REGENERATED = "regenerated"
    DISPATCHED = "dispatched"


class TaskEventSource(str, enum.Enum):
    """事件来源。"""

    MANUAL = "manual"
    AI = "ai"
    SYSTEM = "system"


class TaskEvent(Base, TimestampMixin):
    """任务事件记录表。"""

    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户",
    )

    goal_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user_goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属目标",
    )

    task_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="关联的任务 ID（删除后可能为空）",
    )

    event_type: Mapped[TaskEventType] = mapped_column(
        Enum(TaskEventType),
        nullable=False,
        index=True,
        comment="事件类型",
    )

    source: Mapped[TaskEventSource] = mapped_column(
        Enum(TaskEventSource),
        nullable=False,
        default=TaskEventSource.SYSTEM,
        comment="事件来源",
    )

    scheduled_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
        comment="任务归属日期快照（便于按天查询）",
    )

    description_snapshot: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        default="",
        comment="任务描述快照",
    )

    criteria_snapshot: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        default="",
        comment="完成标准快照",
    )

    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        comment="事件补充信息（JSON 字符串）",
    )

    @staticmethod
    def build_payload(data: dict) -> str:
        """
        构造 payload_json 字段。

        改动原因：
            统一 JSON 序列化逻辑，避免各路由重复实现且出现 ensure_ascii 等不一致。
        """
        try:
            return json.dumps(data or {}, ensure_ascii=False)
        except Exception:
            return "{}"

