"""
安全工具模块 (Security)

设计意图：
    集中处理密码哈希和 JWT 令牌的签发/验证逻辑。

安全策略：
    - 密码：直接使用 bcrypt 库（passlib 已停止维护，与新版 bcrypt 不兼容）
    - JWT：使用 HS256 对称签名，包含 user_id 和 username
    - Token 有效期：通过配置文件管理，默认 8 小时（可通过环境变量覆盖）
"""

from datetime import datetime, timedelta, timezone
import re

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# ===== 密码哈希 =====
# 直接使用 bcrypt 库而非 passlib，避免 passlib 与 bcrypt>=4.1 的兼容性问题。

_PASSWORD_MIN_LENGTH = 8
_BCRYPT_COST = 12


def validate_password_strength(password: str) -> list[str]:
    """
    校验密码强度策略。

    策略要求（可用于注册/改密）：
        - 至少 8 位
        - 必须同时包含：小写字母、数字、特殊符号

    Args:
        password: 用户输入的明文密码

    Returns:
        list[str]: 不满足的规则描述列表；若为空表示通过校验
    """
    issues: list[str] = []
    if len(password) < _PASSWORD_MIN_LENGTH:
        issues.append(f"密码长度至少 {_PASSWORD_MIN_LENGTH} 位")
    if not re.search(r"[a-z]", password):
        issues.append("密码必须包含小写字母")
    if not re.search(r"[0-9]", password):
        issues.append("密码必须包含数字")
    if not re.search(r"[^A-Za-z0-9]", password):
        issues.append("密码必须包含特殊符号")
    return issues


def hash_password(password: str) -> str:
    """
    对明文密码进行 bcrypt 哈希。

    Args:
        password: 用户输入的明文密码

    Returns:
        bcrypt 哈希后的密码字符串
    """
    # bcrypt 要求输入为 bytes
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=_BCRYPT_COST)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码是否与哈希值匹配。

    Args:
        plain_password: 用户输入的明文密码
        hashed_password: 数据库中存储的哈希值

    Returns:
        密码匹配返回 True，否则返回 False
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


# ===== JWT 令牌配置 =====


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """
    创建 JWT 访问令牌。

    Args:
        data: 要编码到 Token 中的数据（通常包含 sub=user_id, username=xxx）
        expires_delta: Token 有效时长，默认使用配置中的值

    Returns:
        编码后的 JWT 字符串
    """
    to_encode = data.copy()

    # 设置过期时间
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    to_encode.update({"exp": expire})

    # 使用 HS256 算法签名
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict | None:
    """
    解码并验证 JWT 令牌。

    Args:
        token: 客户端发送的 JWT 字符串

    Returns:
        解码成功返回 Token 中的数据字典，失败返回 None
    """
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        return payload
    except JWTError:
        return None
