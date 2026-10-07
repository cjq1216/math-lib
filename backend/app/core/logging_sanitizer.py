"""日志与审计敏感数据脱敏工具。

严格禁止在日志和审计中打印密码、令牌、Cookie 以及学生敏感隐私字段。
"""

from typing import Any

SENSITIVE_FIELD_NAMES = {
    "password",
    "password_hash",
    "old_password",
    "new_password",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "secret",
    "secret_key",
    "id_card",
    "phone",
    "phone_number",
    "guardian_phone",
}


def sanitize_sensitive_data(value: Any) -> Any:
    """递归脱敏数据结构中的敏感信息。"""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for k, v in value.items():
            if str(k).lower() in SENSITIVE_FIELD_NAMES:
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_sensitive_data(v)
        return sanitized
    elif isinstance(value, (list, tuple, set)):
        sanitized_list = [sanitize_sensitive_data(item) for item in value]
        return type(value)(sanitized_list) if isinstance(value, (list, tuple)) else sanitized_list
    elif isinstance(value, str):
        # 简单防御 Bearer token 字符串模式泄漏
        if value.lower().startswith("bearer ") and len(value) > 15:
            return "Bearer [REDACTED]"
    return value
