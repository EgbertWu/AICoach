"""
聊天会话模型 (Chat Session & Message Models)

改动原因：
    支持对话式计划生成。用户通过多轮对话描述目标，系统判断短期/长期后一键生成计划。
    ChatSession 记录会话元信息（状态、计划模式），ChatMessage 记录完整对话历史。
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin


class SessionStatus(str, enum.Enum):
    """会话状态枚举。"""
    ACTIVE = "active"       # 对话进行中
    FINALIZED = "finalized" # 已定稿生成计划


class PlanMode(str, enum.Enum):
    """计划模式枚举。"""
    UNKNOWN = "unknown"     # 尚未判断
    DAILY = "daily"         # 短期日计划
    LONG_TERM = "long_term" # 长期计划


class ChatSession(Base, TimestampMixin):
    """
    聊天会话表。

    改动原因：左侧历史对话列表需要持久化会话，支持回溯上下文和生成计划的可追踪性。

    字段说明：
    - user_id: 所属用户，实现多用户数据隔离
    - title: 会话标题（可选，可从首条消息自动生成）
    - status: 会话状态（active/finalized）
    - plan_mode: 判断出的计划模式（unknown/daily/long_term）
    - linked_goal_id: 定稿后关联的目标 ID（可空）
    """
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="会话唯一标识"
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户 ID",
    )
    title: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="会话标题（可选）",
    )
    status: Mapped[str] = mapped_column(
        Enum(SessionStatus),
        nullable=False,
        default=SessionStatus.ACTIVE,
        server_default=SessionStatus.ACTIVE.value,
        comment="会话状态：active / finalized",
    )
    plan_mode: Mapped[str] = mapped_column(
        Enum(PlanMode),
        nullable=False,
        default=PlanMode.UNKNOWN,
        server_default=PlanMode.UNKNOWN.value,
        comment="计划模式：unknown / daily / long_term",
    )
    linked_goal_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("user_goals.id", ondelete="SET NULL"),
        nullable=True,
        comment="定稿后关联的目标 ID",
    )
    # 改动原因：ChatSessionListItem schema 需要 updated_at 字段用于排序展示
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="记录更新时间",
    )

    # 关系：所属用户
    user: Mapped["User"] = relationship("User", backref="chat_sessions")  # noqa: F821

    # 关系：会话消息列表
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    # 关系：关联的目标
    linked_goal: Mapped["UserGoal | None"] = relationship("UserGoal")  # noqa: F821

    def __repr__(self) -> str:
        """调试友好的字符串表示。"""
        title_preview = (self.title or "无标题")[:30]
        return f"<ChatSession(id={self.id}, user_id={self.user_id}, status={self.status}, mode={self.plan_mode}, title='{title_preview}')>"


class ChatMessage(Base, TimestampMixin):
    """
    聊天消息表。

    改动原因：记录完整对话历史，支持上下文回溯和 LLM 多轮对话。

    字段说明：
    - session_id: 所属会话
    - role: 消息角色（user/assistant/system）
    - content: 消息内容
    """
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="消息唯一标识"
    )
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属会话 ID",
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="消息角色：user / assistant / system",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="消息内容",
    )

    # 关系：所属会话
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")

    def __repr__(self) -> str:
        """调试友好的字符串表示。"""
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<ChatMessage(id={self.id}, session_id={self.session_id}, role={self.role}, content='{preview}')>"
