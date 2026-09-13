"""显式业务审计日志辅助函数。"""

from typing import Any

from fastapi import Request
from sqlmodel import Session

from app.models.audit_log import AuditLog
from app.models.user import User

SENSITIVE_KEYS = {
    "authorization",
    "password",
    "password_hash",
    "access_token",
    "refresh_token",
    "token",
}


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else _sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def add_audit_event(
    session: Session,
    *,
    action: str,
    resource_type: str,
    actor: User | None = None,
    resource_id: int | None = None,
    changes: dict[str, Any] | None = None,
    request: Request | None = None,
    actor_username: str | None = None,
) -> AuditLog:
    """向当前事务添加审计事件，不在此处提交事务。"""
    ip_address = request.client.host if request and request.client else None
    user_agent = request.headers.get("user-agent") if request else None
    event = AuditLog(
        user_id=actor.id if actor else None,
        username=actor.username if actor else actor_username,
        action=action[:32],
        resource_type=resource_type[:32],
        resource_id=resource_id,
        changes=_sanitize(changes) if changes else None,
        ip_address=ip_address[:64] if ip_address else None,
        user_agent=user_agent[:512] if user_agent else None,
    )
    session.add(event)
    return event
