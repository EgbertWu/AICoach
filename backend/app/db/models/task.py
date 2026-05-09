"""
任务模型 (Task Model)

设计意图：
    记录 Planner Agent 将用户目标拆解后的具体任务卡片。
    这是 MVP 的核心数据实体——用户每天与之交互的主要对象。

    Phase 10 字段设计：
    - description / criteria: 任务内容（不变）
    - planned_start_at / planned_end_at: DateTime 类型，计划时间窗口
    - completed_at: DateTime，用户勾选完成时由后端写入 now()
    - completion_reason: Text，超时完成时用户填写的原因
    - 移除 duration_seconds：不做秒表计时

增量升级说明：
    新增 scheduled_date 字段。
    改动原因：长期计划必须落到"每天"，周/月复盘也应以 scheduled_date 聚合。
"""

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin


class TaskStatus(str, enum.Enum):
    """
    任务状态枚举。

    状态流转规则：
        pending → completed（简化：去掉 in_progress，因为没有计时器了）
    """
    PENDING = "pending"           # 未开始
    COMPLETED = "completed"       # 已完成


class Task(Base, TimestampMixin):
    """
    任务表。

    每条记录代表 Planner Agent 从用户目标中拆解出的一条具体任务。

    增量字段：
    - scheduled_date: 该任务归属哪一天（长期计划按天派发专用）
    """
    __tablename__ = "tasks"

    # 主键
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="任务唯一标识"
    )

    # 外键：关联到 user_goals 表
    goal_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user_goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联的目标 ID",
    )

    # 任务描述：用户可读的任务内容
    description: Mapped[str] = mapped_column(
        Text, nullable=False, comment="任务描述（做什么）"
    )

    # 完成标准：明确的"完成"定义
    criteria: Mapped[str] = mapped_column(
        Text, nullable=False, comment="完成标准（怎么算做完）"
    )

    # 计划开始时间：DateTime 类型，由 LLM 生成或用户手动编辑
    planned_start_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="计划开始时间（DateTime）",
    )

    # 计划结束/截止时间：用于判断是否超时
    planned_end_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="计划截止时间（DateTime），用于超时判定",
    )

    # 实际完成时间：由后端写入 now()，确保时间可信
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="用户勾选完成的实际时间（后端写入）",
    )

    # 超时完成原因：用户在超时弹窗中填写（可选）
    completion_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="超时完成时用户填写的原因（可选）",
    )

    # 任务状态：使用 Enum 类型存储
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus),
        nullable=False,
        default=TaskStatus.PENDING,
        comment="任务状态：pending / completed",
    )

    # ===== 按天派发归属字段 =====
    # 改动原因：长期计划必须落到"每天"，周/月复盘也应以 scheduled_date 聚合
    scheduled_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
        comment="该任务归属哪一天（长期计划按天派发专用）",
    )

    # 反向关系：任务所属的目标
    goal: Mapped["UserGoal"] = relationship("UserGoal", back_populates="tasks")

    def __repr__(self) -> str:
        """调试友好的字符串表示。"""
        preview = self.description[:30] + "..." if len(self.description) > 30 else self.description
        return f"<Task(id={self.id}, status='{self.status.value}', scheduled='{self.scheduled_date}', desc='{preview}')>"
