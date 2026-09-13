"""安全模块：JWT 签发/校验与密码哈希。"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
RESERVED_CLAIMS = {"sub", "exp", "iat", "type", "sid", "jti"}


def validate_password_length(password: str) -> str:
    """校验产品密码策略与 bcrypt 的 72 字节上限。"""
    if len(password) < 8:
        raise ValueError("密码至少需要 8 个字符")
    if len(password.encode("utf-8")) > 72:
        raise ValueError("密码不能超过 72 个 UTF-8 字节")
    return password


def hash_password(password: str) -> str:
    """校验并哈希密码。"""
    return pwd_context.hash(validate_password_length(password))


def verify_password(plain: str, hashed: str) -> bool:
    """校验密码；保留历史短密码登录，仅拒绝超出 bcrypt 上限的输入。"""
    if len(plain.encode("utf-8")) > 72:
        return False
    return pwd_context.verify(plain, hashed)


def create_access_token(
    subject: str | int,
    session_id: int,
    extra: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """创建短期 access token。"""
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    payload = {
        key: value for key, value in (extra or {}).items() if key not in RESERVED_CLAIMS
    }
    payload.update(
        {
            "sub": str(subject),
            "sid": session_id,
            "exp": expire,
            "iat": now,
            "type": "access",
        }
    )
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    subject: str | int,
    session_id: int,
    jti: str | None = None,
) -> tuple[str, str, datetime]:
    """创建 refresh token，并返回 token、jti 与数据库用的过期时间。"""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.jwt_refresh_token_expire_days)
    refresh_jti = jti or uuid4().hex
    payload = {
        "sub": str(subject),
        "sid": session_id,
        "jti": refresh_jti,
        "exp": expire,
        "iat": now,
        "type": "refresh",
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, refresh_jti, expire.replace(tzinfo=None)


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any] | None:
    """解码并校验 JWT；签名、过期或类型错误时返回 None。"""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        return None

    if expected_type is not None and payload.get("type") != expected_type:
        return None
    if not payload.get("sub") or payload.get("sid") is None:
        return None
    if expected_type == "refresh" and not payload.get("jti"):
        return None
    return payload
