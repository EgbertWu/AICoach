"""
用户认证状态模型 (User Auth State Model)

设计意图：
    为登录安全策略提供可持久化的状态存储（无需修改 users 表）。

改动原因：
    MVP 阶段仓库没有数据库迁移机制，直接给 users 表加字段会导致已有数据库不生效。
    因此用独立表承载“失败次数/锁定时间”等安全状态，避免破坏现有数据。
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin


class UserAuthState(Base, TimestampMixin):
    """
    用户认证状态表。

    字段说明：
        - user_id: 关联 users.id（一对一，unique）
        - failed_attempts: 当前连续失败次数
        - locked_until: 锁定截止时间（UTC），为空表示未锁定
        - last_failed_at: 最近一次失败时间（UTC）
    """

    __tablename__ = "user_auth_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    failed_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    locked_until: Mapped[datetime.datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        default=None,
    )

    last_failed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        default=None,
    )

