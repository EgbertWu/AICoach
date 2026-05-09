"""
长期目标状态表 (Long-Term Goal State)

设计意图：
    以“附加表”的方式为长期目标提供可演进的状态机能力，而不强依赖对 user_goals 表做迁移。
    用于解决：
    - 页面刷新时快速判断是否存在进行中的长期任务
    - 长期任务取消/完成等状态持久化
    - 后续扩展：暂停、归档、异常恢复等

改动原因：
    仅依赖 tasks 表的 pending/completed 状态，无法可靠表达“目标是否仍进行中/是否已取消”。
    同时项目当前无迁移工具，新增表比 ALTER TABLE 更安全、可控。
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin


class LongTermGoalStatus(str, enum.Enum):
    """长期目标状态。"""

    ACTIVE = "active"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class LongTermGoalState(Base, TimestampMixin):
    """
    长期目标状态记录。

    约束：
        - goal_id 唯一：一个 goal 对应一条状态记录
    """

    __tablename__ = "long_term_goal_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户（用于快速查询活跃目标）",
    )

    goal_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user_goals.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="关联的长期目标 ID",
    )

    status: Mapped[LongTermGoalStatus] = mapped_column(
        Enum(LongTermGoalStatus),
        nullable=False,
        default=LongTermGoalStatus.ACTIVE,
        index=True,
        comment="长期目标状态：active / cancelled / completed",
    )

    last_dispatch_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
        comment="最后一次成功派发的日期",
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="取消时间（可为空）",
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="完成时间（可为空）",
    )

