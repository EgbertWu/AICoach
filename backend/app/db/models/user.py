"""
用户模型 (User Model)

设计意图：
    存储用户的基本认证信息，作为所有业务数据的顶层实体。
    每个用户拥有独立的目标和任务数据，实现数据隔离。

增量升级说明：
    新增 quiet_hours_start / quiet_hours_end / allow_quiet_hours / timezone 字段。
    改动原因：作息因人而异，quiet hours 必须是用户级偏好，且跨日计算需要 timezone。
"""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """
    用户表。

    username 设置 unique=True 确保用户名不重复。
    hashed_password 存储的是 bcrypt 哈希值，长度固定为 60 字符。

    增量字段：
    - quiet_hours_start: 休息开始时间，默认 23:00
    - quiet_hours_end: 休息结束时间，默认 06:00
    - allow_quiet_hours: 是否允许在休息时间安排任务，默认 false
    - timezone: 用户时区，默认 Asia/Shanghai
    """

    __tablename__ = "users"

    # 主键：自增整数 ID
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="用户唯一标识"
    )

    # 用户名：唯一，用于登录标识
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="用户名，唯一标识",
    )

    # 密码哈希：bcrypt 哈希值，固定 60 字符
    hashed_password: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        comment="bcrypt 哈希后的密码",
    )

    # ===== Quiet Hours 偏好字段 =====
    # 改动原因：作息因人而异，quiet hours 必须是用户级偏好

    quiet_hours_start: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="23:00",
        server_default="23:00",
        comment="休息开始时间（HH:MM），默认 23:00",
    )

    quiet_hours_end: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="06:00",
        server_default="06:00",
        comment="休息结束时间（HH:MM），默认 06:00",
    )

    allow_quiet_hours: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        comment="是否允许在休息时间安排任务，默认 false",
    )

    timezone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Asia/Shanghai",
        server_default="Asia/Shanghai",
        comment="用户时区，默认 Asia/Shanghai",
    )

    # 关系：一个用户可以拥有多个目标
    goals: Mapped[list["UserGoal"]] = relationship(  # noqa: F821
        "UserGoal",
        back_populates="user",
        cascade="all, delete-orphan",
    )
