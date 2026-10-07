"""R6 运维、可观测性、安全备份与灾难恢复演练测试。

覆盖：
1. 分层健康检查探针 (Liveness / Readiness) 及降级 503 场景；
2. Request ID 链路追踪与响应头耗时；
3. 敏感数据脱敏过滤器；
4. SQLite 安全热备份、清单 Manifest 校验与媒体同步归档；
5. 备份保留策略与历史文件清理；
6. 真实灾难恢复演练（数据污染后还原验证 + 恢复前快照生成）；
7. 管理端系统备份 API 角色权限控制 (RBAC) 与审计记录；
8. CLI 备份与清理命令执行。
"""

import sqlite3
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.logging_sanitizer import sanitize_sensitive_data
from app.models.audit_log import AuditLog
from app.services.backup_service import (
    cleanup_old_backups,
    create_backup,
    list_backups,
    restore_from_backup,
)


def _register_admin(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": f"admin_{uuid.uuid4().hex[:6]}",
            "password": "password123",
            "real_name": "管理员",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _auth_headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _create_teacher(client: TestClient, admin_headers: dict[str, str]) -> dict:
    uname = f"teacher_{uuid.uuid4().hex[:6]}"
    response = client.post(
        "/api/v1/users/",
        headers=admin_headers,
        json={
            "username": uname,
            "password": "password123",
            "real_name": "数学老师",
            "role": "teacher",
        },
    )
    assert response.status_code == 201, response.text
    # 登录获取 teacher token
    login_res = client.post(
        "/api/v1/auth/login",
        data={"username": uname, "password": "password123"},
    )
    assert login_res.status_code == 200
    return login_res.json()


# =========================================================================
# 1. 健康检查探针测试
# =========================================================================

def test_health_probes_liveness_and_readiness(client: TestClient):
    """测试 /health 综合探针、/health/live 存活探针和 /health/ready 就绪探针"""
    # 1. 综合 /health (向后兼容)
    res_health = client.get("/health")
    assert res_health.status_code == 200
    data_health = res_health.json()
    assert data_health["status"] == "ok"
    assert data_health["live"] is True
    assert data_health["ready"] is True

    # 2. 存活探针 /health/live
    res_live = client.get("/health/live")
    assert res_live.status_code == 200
    data_live = res_live.json()
    assert data_live["status"] == "alive"

    # 3. 就绪探针 /health/ready
    res_ready = client.get("/health/ready")
    assert res_ready.status_code == 200
    data_ready = res_ready.json()
    assert data_ready["status"] == "ready"
    assert "checks" in data_ready
    assert data_ready["checks"]["database"]["healthy"] is True
    assert data_ready["checks"]["storage_media"]["healthy"] is True
    assert data_ready["checks"]["storage_logs"]["healthy"] is True


def test_health_readiness_failure_returns_503(client: TestClient):
    """当依赖不可用时，Readiness 探针必须返回 503 Service Unavailable"""
    with patch("app.services.health_service.engine.connect") as mock_connect:
        mock_connect.side_effect = RuntimeError("Database connection refused")

        res = client.get("/health/ready")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["database"]["healthy"] is False
        assert "connection refused" in data["checks"]["database"]["message"]


# =========================================================================
# 2. 中间件与请求日志追踪
# =========================================================================

def test_request_logging_middleware_tracing(client: TestClient):
    """验证中间件生成/透传 X-Request-ID 并注入耗时响应头"""
    # 自动生成 Request-ID
    res = client.get("/health/live")
    assert res.status_code == 200
    req_id = res.headers.get("X-Request-ID")
    assert req_id is not None
    assert len(req_id) >= 16
    assert "X-Response-Time-Ms" in res.headers
    assert float(res.headers["X-Response-Time-Ms"]) >= 0

    # 透传客户端指定 Request-ID
    custom_trace = "trace-test-custom-12345"
    res_custom = client.get("/health/live", headers={"X-Request-ID": custom_trace})
    assert res_custom.status_code == 200
    assert res_custom.headers.get("X-Request-ID") == custom_trace


def test_sensitive_data_sanitizer():
    """测试敏感字段自动脱敏过滤器"""
    payload = {
        "username": "zhangsan",
        "password": "my_super_secret_password",
        "nested": {
            "token": "secret_jwt_token_here",
            "phone": "13800138000",
            "guardian_phone": "13900139000",
            "id_card": "110101199003072345",
            "math_score": 95,
        },
        "headers": ["Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", "Normal Header"],
    }

    sanitized = sanitize_sensitive_data(payload)
    assert sanitized["username"] == "zhangsan"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["nested"]["token"] == "[REDACTED]"
    assert sanitized["nested"]["phone"] == "[REDACTED]"
    assert sanitized["nested"]["guardian_phone"] == "[REDACTED]"
    assert sanitized["nested"]["id_card"] == "[REDACTED]"
    assert sanitized["nested"]["math_score"] == 95
    assert sanitized["headers"][0] == "Bearer [REDACTED]"
    assert sanitized["headers"][1] == "Normal Header"


# =========================================================================
# 3. 备份创建、清单校验与保留策略
# =========================================================================

def test_backup_creation_and_listing(tmp_path: Path):
    """测试安全热备份包生成及清单 Manifest 解析"""
    backup_dir = tmp_path / "backups"
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    # 写入测试媒体文件
    test_media = media_dir / "q1.png"
    test_media.write_bytes(b"dummy image content bytes 123456")

    # 写入测试 SQLite 数据库
    db_file = tmp_path / "test_data.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE test_tbl (id INTEGER PRIMARY KEY, content TEXT);")
    conn.execute("INSERT INTO test_tbl VALUES (1, 'initial data');")
    conn.commit()
    conn.close()

    # 创建备份
    item = create_backup(
        description="单元测试备份",
        backup_dir=backup_dir,
        media_root=media_dir,
        custom_db_path=db_file,
    )

    assert item.filename.startswith("math_bank_backup_")
    assert item.size_bytes > 0
    assert item.media_file_count == 1
    assert item.media_total_bytes == len(b"dummy image content bytes 123456")
    assert item.database_sha256 != ""
    assert item.status == "valid"

    # 查询列表
    items = list_backups(backup_dir=backup_dir)
    assert len(items) == 1
    assert items[0].backup_id == item.backup_id
    assert items[0].description == "单元测试备份"


def test_backup_retention_policy_cleanup(tmp_path: Path):
    """测试基于最大数量和有效期的备份保留清理策略"""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE t (id INT);")
    conn.commit()
    conn.close()

    # 创建 4 个备份
    for i in range(4):
        create_backup(
            description=f"backup {i}",
            backup_dir=backup_dir,
            media_root=media_dir,
            custom_db_path=db_file,
        )

    all_before = list_backups(backup_dir=backup_dir)
    assert len(all_before) == 4

    # 清理策略：最大保留 2 个
    deleted = cleanup_old_backups(backup_dir=backup_dir, max_count=2, retention_days=30)
    assert len(deleted) == 2

    remaining = list_backups(backup_dir=backup_dir)
    assert len(remaining) == 2


# =========================================================================
# 4. 灾难恢复演练 (Disaster Recovery Drill)
# =========================================================================

def test_disaster_recovery_drill(tmp_path: Path):
    """真实灾难恢复演练：

    1. 初始化数据库并写入基准数据、生成媒体文件；
    2. 创建完整备份；
    3. 模拟数据被篡改、媒体文件被误删（模拟故障）；
    4. 执行 restore_from_backup 灾难还原；
    5. 验证数据无损还原为基线状态，媒体文件完好恢复，并自动生成恢复前快照。
    """
    backup_dir = tmp_path / "backups"
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    db_file = tmp_path / "live_math_bank.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE questions (id INTEGER PRIMARY KEY, stem TEXT);")
    conn.execute("INSERT INTO questions VALUES (101, '已知函数 f(x) = 2x + 1，求 f(3)');")
    conn.commit()
    conn.close()

    # 媒体文件
    img_file = media_dir / "diagram_101.svg"
    img_file.write_text("<svg>triangle</svg>", encoding="utf-8")

    # 1. 执行安全热备份
    backup_meta = create_backup(
        description="灾备基线快照",
        backup_dir=backup_dir,
        media_root=media_dir,
        custom_db_path=db_file,
    )
    assert backup_meta.status == "valid"

    # 2. 模拟灾难故障：数据库数据被非法修改，媒体文件被彻底删除
    conn = sqlite3.connect(str(db_file))
    conn.execute("UPDATE questions SET stem = '已被黑客恶意篡改的内容' WHERE id = 101;")
    conn.commit()
    conn.close()

    img_file.unlink()
    assert not img_file.exists()

    # 验证故障已被注入
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cur.execute("SELECT stem FROM questions WHERE id = 101;")
    assert cur.fetchone()[0] == "已被黑客恶意篡改的内容"
    conn.close()

    # 3. 执行灾难恢复
    restore_res = restore_from_backup(
        backup_dir / backup_meta.filename,
        target_db_path=db_file,
        target_media_root=media_dir,
    )

    assert restore_res.status == "success"
    assert restore_res.media_file_count == 1
    assert restore_res.pre_restore_backup is not None

    # 4. 验证数据已完全还原到基线状态
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cur.execute("SELECT stem FROM questions WHERE id = 101;")
    restored_stem = cur.fetchone()[0]
    assert restored_stem == "已知函数 f(x) = 2x + 1，求 f(3)"
    conn.close()

    # 验证媒体文件已还原
    assert img_file.exists()
    assert img_file.read_text(encoding="utf-8") == "<svg>triangle</svg>"

    # 验证恢复前快照文件存在且包含篡改态
    pre_bak_path = db_file.parent / restore_res.pre_restore_backup
    assert pre_bak_path.exists()
    conn_pre = sqlite3.connect(str(pre_bak_path))
    cur_pre = conn_pre.cursor()
    cur_pre.execute("SELECT stem FROM questions WHERE id = 101;")
    assert cur_pre.fetchone()[0] == "已被黑客恶意篡改的内容"
    conn_pre.close()


# =========================================================================
# 5. 管理端 API 权限与审计测试 (RBAC)
# =========================================================================

def test_system_backup_api_rbac_and_audit(client: TestClient, test_engine):
    """测试备份管理 API 仅允许管理员访问，且记录审计日志"""
    admin_auth = _register_admin(client)
    admin_headers = _auth_headers(admin_auth)
    teacher_auth = _create_teacher(client, admin_headers)
    teacher_headers = _auth_headers(teacher_auth)

    # 1. 未认证访问返回 401
    assert client.get("/api/v1/system/backups").status_code == 401
    assert client.post("/api/v1/system/backup").status_code == 401

    # 2. 教师访问返回 403 Forbidden
    res_teacher = client.get("/api/v1/system/backups", headers=teacher_headers)
    assert res_teacher.status_code == 403

    res_teacher_post = client.post("/api/v1/system/backup", headers=teacher_headers, json={})
    assert res_teacher_post.status_code == 403

    # 3. 管理员成功创建备份
    res_admin_create = client.post(
        "/api/v1/system/backup",
        headers=admin_headers,
        json={"description": "API 审计验证备份"},
    )
    assert res_admin_create.status_code == 201
    backup_data = res_admin_create.json()
    filename = backup_data["filename"]
    assert filename.startswith("math_bank_backup_")

    # 4. 管理员查看列表
    res_list = client.get("/api/v1/system/backups", headers=admin_headers)
    assert res_list.status_code == 200
    filenames = [item["filename"] for item in res_list.json()]
    assert filename in filenames

    # 5. 管理员下载备份
    res_down = client.get(f"/api/v1/system/backups/{filename}/download", headers=admin_headers)
    assert res_down.status_code == 200
    assert res_down.headers["content-type"] == "application/zip"

    # 6. 管理员恢复测试（未确认 confirm=True 返回 400）
    res_restore_noconfirm = client.post(
        "/api/v1/system/restore",
        headers=admin_headers,
        json={"filename": filename, "confirm": False},
    )
    assert res_restore_noconfirm.status_code == 400

    # 7. 管理员删除备份
    res_del = client.delete(f"/api/v1/system/backups/{filename}", headers=admin_headers)
    assert res_del.status_code == 200
    assert res_del.json()["ok"] is True

    # 8. 验证 AuditLog 中记录了审计事件
    with Session(test_engine) as session:
        events = session.exec(
            select(AuditLog).where(AuditLog.resource_type == "system_backup")
        ).all()
        actions = [ev.action for ev in events]
        assert "create_backup" in actions
        assert "delete_backup" in actions


def test_backup_cli_execution(monkeypatch, capsys):
    """测试 CLI 备份、列表与清理指令正常调用"""
    from app.cli.backup import main

    # 1. 执行 list
    monkeypatch.setattr("sys.argv", ["backup.py", "list"])
    main()
    captured = capsys.readouterr()
    assert "备份" in captured.out

    # 2. 执行 cleanup
    monkeypatch.setattr("sys.argv", ["backup.py", "cleanup"])
    main()
    captured_cleanup = capsys.readouterr()
    assert "清理" in captured_cleanup.out
