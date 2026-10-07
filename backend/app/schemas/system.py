"""系统运维、健康诊断与备份恢复相关的请求/响应 Schema。"""

from pydantic import Field

from app.schemas.common import StrictSchema


class HealthProbeDetail(StrictSchema):
    """单个健康检查指标详情"""

    healthy: bool
    message: str | None = None
    latency_ms: float | None = None
    details: dict[str, object] | None = None


class HealthCheckResponse(StrictSchema):
    """综合健康检查响应"""

    status: str
    app: str
    version: str = "0.1.0"
    environment: str
    timestamp: str
    checks: dict[str, HealthProbeDetail] = Field(default_factory=dict)


class BackupItem(StrictSchema):
    """备份文件摘要信息"""

    backup_id: str
    filename: str
    size_bytes: int
    created_at: str
    database_sha256: str
    database_size_bytes: int
    media_file_count: int
    media_total_bytes: int
    status: str = "valid"
    description: str | None = None


class BackupCreateRequest(StrictSchema):
    """手动创建备份请求"""

    description: str | None = Field(default=None, max_length=200)


class RestoreRequest(StrictSchema):
    """执行备份恢复请求"""

    filename: str = Field(description="待恢复的备份文件名，如 math_bank_backup_xxx.zip")
    confirm: bool = Field(default=False, description="必须为 True 方可执行覆盖恢复")


class RestoreResponse(StrictSchema):
    """恢复执行结果响应"""

    status: str
    message: str
    restored_at: str
    backup_filename: str
    pre_restore_backup: str | None = None
    database_sha256: str
    media_file_count: int
