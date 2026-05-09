"""
长期目标每日派发表 (Goal Daily Dispatch)

设计意图：
    为“同一长期目标在同一天只派发一次”提供数据库级幂等保障。
    用于解决：
    - 页面刷新/多标签页/重复点击导致的重复生成
    - 并发请求下的竞态条件（先查后写）导致重复插入

改动原因：
    仅依赖 tasks 表“是否存在某天任务”在并发场景下不可靠。
    使用 (goal_id, target_date) 的唯一约束可以以最小成本提供强一致的幂等语义。
"""

from __future__ import annotations

import enum
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin


class DispatchStatus(str, enum.Enum):
    """每日派发记录状态。"""

    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class GoalDailyDispatch(Base, TimestampMixin):
    """每日派发记录表。"""

    __tablename__ = "goal_daily_dispatches"
    __table_args__ = (UniqueConstraint("goal_id", "target_date", name="uq_goal_date_dispatch"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    goal_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user_goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联的长期目标 ID",
    )

    target_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="派发日期（同一 goal 每天一条）",
    )

    status: Mapped[DispatchStatus] = mapped_column(
        Enum(DispatchStatus),
        nullable=False,
        default=DispatchStatus.IN_PROGRESS,
        index=True,
        comment="派发状态：in_progress / succeeded / failed",
    )

    error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="失败原因（可为空）",
    )

