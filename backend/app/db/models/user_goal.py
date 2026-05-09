"""
用户目标模型 (UserGoal Model)

设计意图：
    记录用户输入的长期目标或每日意图。这是整个系统的"起点"——
    用户先设定目标，Planner Agent 再基于目标生成具体的任务列表。

    关联关系：
    - user_id: 外键关联 User 表，实现多用户数据隔离
    - tasks: 一对多关联 Task 表
    - reviews: 一对多关联 ReviewReport 表

增量升级说明：
    新增 goal_type / target_duration_days / start_date / roadmap_json / roadmap_summary 字段。
    改动原因：不新增表也能承载长期计划，并能用于每日派发。
"""

import enum
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin


class GoalType(str, enum.Enum):
    """
    目标类型枚举。

    - daily: 每日目标（原有逻辑）
    - long_term: 长期目标（新增，需要生成 Roadmap 并按天派发）
    """
    DAILY = "daily"
    LONG_TERM = "long_term"


class UserGoal(Base, TimestampMixin):
    """
    用户目标表。

    每条记录代表用户设定的一条目标（长期目标或当日意图）。
    与 User 是多对一关系（多个目标属于一个用户），
    与 Task 是一对多关系（一个目标可以拆解为多个任务）。

    增量字段：
    - goal_type: 目标类型（daily / long_term）
    - target_duration_days: 长期目标的天数
    - start_date: 长期目标的开始日期
    - roadmap_json: 结构化 Roadmap JSON
    - roadmap_summary: Roadmap 摘要（供前端展示）
    """
    __tablename__ = "user_goals"

    # 主键：自增整数 ID
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="目标唯一标识"
    )

    # 外键：关联到 users 表
    # 实现多用户数据隔离，每个用户只能看到自己的目标
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户 ID",
    )

    # 目标内容：使用 Text 类型而非 String
    # 因为用户输入的目标可能是长段落，Text 没有长度限制更安全。
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="用户输入的目标内容（自然语言）"
    )

    # ===== 长期计划元数据 =====
    # 改动原因：不新增表也能承载长期计划，并能用于每日派发

    goal_type: Mapped[str] = mapped_column(
        Enum(GoalType),
        nullable=False,
        default=GoalType.DAILY,
        server_default=GoalType.DAILY.value,
        comment="目标类型：daily（每日）/ long_term（长期）",
    )

    target_duration_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="长期目标的天数（如 30/56/60），仅 long_term 有效",
    )

    start_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="长期目标的开始日期，默认今天",
    )

    roadmap_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="结构化 Roadmap JSON（长期目标专用）",
    )

    roadmap_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Roadmap 摘要（供前端展示，避免传超长 JSON）",
    )

    # 关系定义：所属用户
    user: Mapped["User"] = relationship("User", back_populates="goals")  # noqa: F821

    # 关系定义：一个目标对应多个任务
    tasks: Mapped[list["Task"]] = relationship(
        "Task", back_populates="goal", cascade="all, delete-orphan"
    )

    # 关系定义：一个目标可以有多个复盘报告
    reviews: Mapped[list["ReviewReport"]] = relationship(
        "ReviewReport", back_populates="goal", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """调试友好的字符串表示，截断过长的内容。"""
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<UserGoal(id={self.id}, user_id={self.user_id}, type={self.goal_type}, content='{preview}')>"
