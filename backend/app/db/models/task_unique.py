"""
任务唯一性约束表 (Task Uniqueness)

设计意图：
    通过数据库唯一索引在“同一目标 + 同一天”维度防止重复任务出现。
    这是对 GoalDailyDispatch 幂等表的补强：
    - GoalDailyDispatch 保证一天只派发一次
    - TaskUnique 防止单次派发内部的重复、或“手动新增”与“派发生成”冲突

改动原因：
    任务重复生成与状态不一致，往往来自多个入口（自动派发/手动新增/加餐/重生成）。
    仅靠前端或 LLM 约束不足以保证一致性，需要数据库级防线。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin


class TaskUnique(Base, TimestampMixin):
    """任务唯一性记录表。"""

    __tablename__ = "task_uniques"
    __table_args__ = (UniqueConstraint("goal_id", "scheduled_date", "fingerprint", name="uq_goal_date_fingerprint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    goal_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user_goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属目标 ID",
    )

    scheduled_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
        comment="任务归属日期（长期计划按天派发；每日计划可为空）",
    )

    task_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="关联的任务 ID（保证 1:1）",
    )

    fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="任务指纹（sha256 hex）",
    )

