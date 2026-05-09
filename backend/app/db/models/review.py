"""
复盘报告模型 (ReviewReport Model)

设计意图：
    记录 Reviewer Agent 基于用户任务执行情况生成的复盘分析。
    支持两种复盘类型：
    - 单日复盘：关联单个 goal_id（原逻辑）
    - 周期复盘：周报/月报，关联时间段内所有任务，goal_id 为空

    字段设计考量：
    - completion_rate: 百分比（0.0-100.0），便于前端展示进度条
    - analysis: AI 对执行情况的分析文本
    - suggestions: AI 给出的改进建议
    - period_type: "daily" | "weekly" | "monthly"
    - period_label: 如 "2026年5月1日-5月7日 周报" 或 "2026年5月月报"
"""

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin

import enum


class PeriodType(str, enum.Enum):
    """复盘周期类型。"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ReviewReport(Base, TimestampMixin):
    """
    复盘报告表。

    每条记录代表一次 AI 生成的复盘分析。
    - daily: 关联单个 goal_id
    - weekly / monthly: 关联时间段，goal_id 为空
    """
    __tablename__ = "review_reports"

    # 主键
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="复盘报告唯一标识"
    )

    # 外键：关联到 user_goals 表（周期复盘时可为空）
    goal_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("user_goals.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="关联的目标 ID（周期复盘时为空）",
    )

    # 复盘周期类型
    period_type: Mapped[PeriodType] = mapped_column(
        Enum(PeriodType),
        nullable=False,
        default=PeriodType.DAILY,
        comment="复盘类型：daily / weekly / monthly",
    )

    # 周期标签（展示用）
    period_label: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        comment="周期标签，如 '2026年5月1日-5月7日 周报'",
    )

    # 完成率：浮点数，范围 0.0 - 100.0
    completion_rate: Mapped[float] = mapped_column(
        Float, nullable=False, comment="任务完成率（0.0-100.0）"
    )

    # 分析文本：AI 对用户执行情况的深度分析
    analysis: Mapped[str] = mapped_column(
        Text, nullable=False, comment="AI 执行分析"
    )

    # 建议文本：AI 给出的具体改进建议
    suggestions: Mapped[str] = mapped_column(
        Text, nullable=False, comment="AI 改进建议"
    )

    # 反向关系：复盘所属的目标
    goal: Mapped["UserGoal | None"] = relationship("UserGoal", back_populates="reviews")

    def __repr__(self) -> str:
        return (
            f"<ReviewReport(id={self.id}, goal_id={self.goal_id}, "
            f"type={self.period_type.value}, rate={self.completion_rate}%)>"
        )
