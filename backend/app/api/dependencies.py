"""
依赖注入模块 (Dependencies)

设计意图：
    FastAPI 的依赖注入系统让我们可以优雅地管理请求级别的资源。
    将依赖集中管理的好处：
    1. 避免在每个路由函数中重复创建/关闭资源
    2. 便于统一替换实现（如测试时用内存数据库替换 SQLite）
    3. 符合"依赖倒置"原则，核心逻辑不依赖具体框架
"""

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.models.user import User
from app.db.session import AsyncSessionLocal

# ===== 数据库会话依赖 =====


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话的依赖注入函数。

    设计意图：
        使用 async generator 模式，确保每个请求：
        1. 开始时创建一个新的数据库会话
        2. 请求处理完毕后（无论成功或异常）自动关闭会话
        3. 异常发生时自动回滚未提交的事务
    """
    db = AsyncSessionLocal()
    try:
        yield db
    finally:
        await db.close()


# ===== JWT 认证依赖 =====

# OAuth2PasswordBearer 会从请求的 Authorization 头中提取 Bearer Token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    从 JWT Token 中解析并获取当前登录用户。

    设计意图：
        作为 FastAPI 依赖注入使用，任何需要认证的接口只需添加：
            current_user: User = Depends(get_current_user)

        流程：
        1. 从 Authorization 头中提取 Bearer Token
        2. 解码并验证 Token 签名和有效期
        3. 从 Token 中提取 user_id，查询数据库获取用户信息
        4. 返回 User ORM 对象，供路由函数使用

    Raises:
        HTTPException 401: Token 无效、过期或用户不存在
    """
    # 解码 Token
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 从 Token 中提取 user_id
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌中缺少用户标识",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 查询数据库获取用户
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
