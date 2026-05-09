"""
认证接口 (Auth Endpoints)

设计意图：
    提供用户注册和登录的 RESTful API。
    使用 OAuth2PasswordRequestForm 作为登录表单格式（FastAPI 标准做法），
    返回 JWT Token 供前端存储和使用。

接口列表：
    - POST /api/auth/register: 用户注册
    - POST /api/auth/login: 用户登录，返回 JWT Token
    - POST /api/auth/change-password: 修改密码（需要登录）
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.config import settings
from app.core.security import (
    create_access_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.db.models.user_auth_state import UserAuthState
from app.db.models.user import User

router = APIRouter(prefix="/api/auth", tags=["认证"])


async def _get_or_create_auth_state(db: AsyncSession, user_id: int) -> UserAuthState:
    """
    获取或创建用户认证状态行。

    改动原因：
        登录锁定机制需要可持久化状态，但不改动 users 表结构。
    """
    result = await db.execute(select(UserAuthState).where(UserAuthState.user_id == user_id))
    state = result.scalar_one_or_none()
    if state:
        return state
    state = UserAuthState(user_id=user_id, failed_attempts=0)
    db.add(state)
    await db.flush()
    return state


@router.post("/register", summary="用户注册")
async def register(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    用户注册接口。

    使用 OAuth2PasswordRequestForm 格式接收数据（username + password），
    与登录接口保持一致的表单格式，前端可以使用 FormData 提交。

    流程：
    1. 检查用户名是否已存在
    2. 对密码进行 bcrypt 哈希
    3. 创建用户记录
    4. 返回成功信息
    """
    # 检查用户名是否已被注册
    result = await db.execute(select(User).where(User.username == form_data.username))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )

    issues = validate_password_strength(form_data.password)
    if issues:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="；".join(issues),
        )

    # 创建新用户
    user = User(
        username=form_data.username,
        hashed_password=hash_password(form_data.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    await _get_or_create_auth_state(db, user.id)
    await db.commit()

    return {"message": "注册成功", "user_id": user.id, "username": user.username}


@router.post("/login", summary="用户登录")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    用户登录接口。

    验证用户名和密码后，签发 JWT Token 返回给前端。
    前端应将 Token 存储在 localStorage 中，并在后续请求的
    Authorization 头中携带：Bearer <token>
    """
    # 查找用户
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    state = await _get_or_create_auth_state(db, user.id)
    if state.locked_until and now < state.locked_until:
        remaining = int((state.locked_until - now).total_seconds())
        minutes = max(1, (remaining + 59) // 60)
        raise HTTPException(
            status_code=423,
            detail=f"账号已锁定，请 {minutes} 分钟后再试",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(form_data.password, user.hashed_password):
        state.failed_attempts = int(state.failed_attempts or 0) + 1
        state.last_failed_at = now
        if state.failed_attempts >= settings.max_failed_login_attempts:
            state.locked_until = now + timedelta(minutes=settings.account_lock_minutes)
            await db.commit()
            raise HTTPException(
                status_code=423,
                detail=f"账号已锁定，请 {settings.account_lock_minutes} 分钟后再试",
                headers={"WWW-Authenticate": "Bearer"},
            )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    state.failed_attempts = 0
    state.locked_until = None
    state.last_failed_at = None
    await db.commit()

    # 签发 JWT Token
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
    }


@router.post("/change-password", summary="修改密码")
async def change_password(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    修改当前用户密码。

    请求体：
        - old_password: 原密码
        - new_password: 新密码（需满足强度策略）

    改动原因：
        密码策略强化不仅影响注册，也需要提供安全的改密入口，便于存量账号升级。
    """
    old_password = str(body.get("old_password") or "")
    new_password = str(body.get("new_password") or "")
    if not old_password or not new_password:
        raise HTTPException(status_code=400, detail="old_password 与 new_password 均不能为空")

    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if not verify_password(old_password, user.hashed_password):
        raise HTTPException(status_code=401, detail="原密码错误")

    issues = validate_password_strength(new_password)
    if issues:
        raise HTTPException(status_code=400, detail="；".join(issues))

    user.hashed_password = hash_password(new_password)
    state = await _get_or_create_auth_state(db, user.id)
    state.failed_attempts = 0
    state.locked_until = None
    state.last_failed_at = None
    await db.commit()

    return {"message": "密码已更新"}


@router.get("/me", summary="获取当前用户信息")
async def get_me(current_user: User = Depends(get_current_user)):
    """
    获取当前登录用户的信息。
    用于前端验证 Token 是否有效，以及获取用户基本信息。
    """
    return {
        "user_id": current_user.id,
        "username": current_user.username,
        "created_at": current_user.created_at.isoformat(),
    }
