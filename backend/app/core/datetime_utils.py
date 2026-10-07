"""UTC 时间工具模块，兼容 Python 3.11-3.14+ 并消除 datetime.utcnow() 弃用警告。"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """返回当前 UTC 时间对应的 naive datetime 对象（与 SQLite/SQLModel 存储保持完全兼容）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)
