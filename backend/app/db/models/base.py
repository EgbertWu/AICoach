"""
SQLAlchemy ORM 基础模块 (Base Model)

设计意图：
    定义所有 ORM 模型共享的基类和公共 Mixin。
    将基类集中管理的好处：
    1. 所有模型自动获得 id、created_at 等公共字段，避免重复定义
    2. 便于统一修改公共行为（如修改时间戳格式、添加软删除等）
    3. 新增模型时只需继承基类，降低 Agent 编写模型的推理成本
"""

import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    所有 ORM 模型的抽象基类。

    使用 SQLAlchemy 2.0 推荐的 DeclarativeBase 方式（而非旧版的 declarative_base()），
    配合 Mapped/mapped_column 类型注解，提供完整的 IDE 类型提示支持。
    """
    pass


class TimestampMixin:
    """
    时间戳混入类 (Timestamp Mixin)。

    为模型自动提供 created_at 字段。
    使用 Mixin 而非直接写在 Base 中，是因为未来可能有不需要时间戳的表（如关联表），
    Mixin 模式让这种选择性继承变得自然。

    为什么用 func.now() 而非 datetime.now？
    - func.now() 生成的是 SQL 的 CURRENT_TIMESTAMP，由数据库服务器计算时间
    - 这样即使应用服务器和数据库服务器时间不一致，也能保证时间戳的准确性
    - 对于 SQLite（本地单文件），两者等价，但保持良好习惯便于后续迁移
    """
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="记录创建时间",
    )
