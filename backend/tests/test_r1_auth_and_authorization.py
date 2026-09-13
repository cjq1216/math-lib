"""R1 认证、授权、可信审计字段与 OpenAPI 回归。"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import create_access_token, decode_token
from app.models.audit_log import AuditLog
from app.models.class_ import ClassTeacher
from app.models.homework import HomeworkResult
from app.models.question import Question


def _register_admin(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "admin",
            "password": "password123",
            "real_name": "管理员",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _auth_headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _create_user(
    client: TestClient,
    admin_headers: dict[str, str],
    username: str,
    role: str = "teacher",
) -> dict:
    response = client.post(
        "/api/v1/users/",
        headers=admin_headers,
        json={
            "username": username,
            "password": "password123",
            "real_name": username,
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _login(client: TestClient, username: str) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/users/",
        "/api/v1/questions/",
        "/api/v1/knowledge/",
        "/api/v1/media/",
        "/api/v1/papers/",
        "/api/v1/classes/",
        "/api/v1/students/",
        "/api/v1/homework/",
        "/api/v1/analytics/students/1/overview",
        "/api/v1/llm/tasks",
    ],
)
def test_all_business_modules_require_authentication(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_auth_bootstrap_me_refresh_rotation_and_invalid_tokens(client: TestClient) -> None:
    unauthenticated = client.get("/api/v1/questions/")
    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["www-authenticate"] == "Bearer"

    auth = _register_admin(client)
    headers = _auth_headers(auth)
    assert auth["user"]["role"] == "admin"

    second_registration = client.post(
        "/api/v1/auth/register",
        json={
            "username": "anonymous",
            "password": "password123",
            "real_name": "匿名教师",
        },
    )
    assert second_registration.status_code == 403

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["username"] == "admin"

    refresh_cookie = client.cookies.get(settings.auth_refresh_cookie_name)
    assert refresh_cookie
    refresh_as_access = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {refresh_cookie}"},
    )
    assert refresh_as_access.status_code == 401

    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    rotated_cookie = client.cookies.get(settings.auth_refresh_cookie_name)
    assert rotated_cookie and rotated_cookie != refresh_cookie
    assert client.get(
        "/api/v1/auth/me", headers=_auth_headers(refreshed.json())
    ).status_code == 200

    claims = decode_token(refreshed.json()["access_token"], expected_type="access")
    expired_access = create_access_token(
        subject=claims["sub"],
        session_id=claims["sid"],
        expires_delta=timedelta(seconds=-1),
    )
    assert client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_access}"},
    ).status_code == 401

    client.cookies.set(
        settings.auth_refresh_cookie_name,
        refresh_cookie,
        path="/api/v1/auth",
    )
    replay = client.post("/api/v1/auth/refresh")
    assert replay.status_code == 401
    assert client.get(
        "/api/v1/auth/me", headers=_auth_headers(refreshed.json())
    ).status_code == 401


def test_admin_only_users_and_disabled_user_session(client: TestClient) -> None:
    admin_auth = _register_admin(client)
    admin_headers = _auth_headers(admin_auth)
    teacher = _create_user(client, admin_headers, "teacher-a")
    teacher_auth = _login(client, "teacher-a")
    teacher_headers = _auth_headers(teacher_auth)

    assert client.get("/api/v1/users/", headers=teacher_headers).status_code == 403

    forged_claims = decode_token(teacher_auth["access_token"], expected_type="access")
    forged_role_token = create_access_token(
        subject=teacher["id"],
        session_id=forged_claims["sid"],
        extra={"role": "admin"},
    )
    assert client.get(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {forged_role_token}"},
    ).status_code == 403

    disabled = client.post(
        f"/api/v1/users/{teacher['id']}/disable",
        headers=admin_headers,
    )
    assert disabled.status_code == 200, disabled.text
    assert client.get("/api/v1/auth/me", headers=teacher_headers).status_code == 401

    short_password = client.post(
        "/api/v1/users/",
        headers=admin_headers,
        json={
            "username": "short",
            "password": "1234567",
            "real_name": "短密码",
        },
    )
    assert short_password.status_code == 422


def test_class_student_object_isolation_and_membership_lifecycle(client: TestClient) -> None:
    admin_auth = _register_admin(client)
    admin_headers = _auth_headers(admin_auth)
    teacher_a = _create_user(client, admin_headers, "teacher-a")
    teacher_b = _create_user(client, admin_headers, "teacher-b")
    headers_a = _auth_headers(_login(client, "teacher-a"))
    headers_b = _auth_headers(_login(client, "teacher-b"))

    created_class = client.post(
        "/api/v1/classes/",
        headers=headers_a,
        json={"name": "七年级一班", "grade": 7, "semester": "2026-Fall"},
    )
    assert created_class.status_code == 201, created_class.text
    class_id = created_class.json()["id"]

    created_student = client.post(
        "/api/v1/students/",
        headers=headers_a,
        json={
            "student_no": "S001",
            "name": "学生甲",
            "grade": 7,
            "class_id": class_id,
        },
    )
    assert created_student.status_code == 201, created_student.text
    student_id = created_student.json()["id"]

    assert client.get(
        f"/api/v1/classes/{class_id}", headers=headers_b
    ).status_code == 403
    assert client.get(
        f"/api/v1/students/{student_id}", headers=headers_b
    ).status_code == 403
    assert client.get(
        f"/api/v1/analytics/students/{student_id}/overview", headers=headers_b
    ).status_code == 403

    assign_b = client.put(
        f"/api/v1/classes/{class_id}/teachers",
        headers=admin_headers,
        json={"teacher_ids": [teacher_a["id"], teacher_b["id"]]},
    )
    assert assign_b.status_code == 200, assign_b.text
    assert client.get(
        f"/api/v1/classes/{class_id}", headers=headers_b
    ).status_code == 200
    assert client.get(
        f"/api/v1/students/{student_id}", headers=headers_b
    ).status_code == 200

    unassign_b = client.put(
        f"/api/v1/classes/{class_id}/teachers",
        headers=admin_headers,
        json={"teacher_ids": [teacher_a["id"]]},
    )
    assert unassign_b.status_code == 200
    assert client.get(
        f"/api/v1/classes/{class_id}", headers=headers_b
    ).status_code == 403

    removed = client.delete(
        f"/api/v1/classes/{class_id}/students/{student_id}", headers=headers_a
    )
    assert removed.status_code == 200
    assert client.get(
        f"/api/v1/students/{student_id}", headers=headers_a
    ).status_code == 403
    assert client.get(
        f"/api/v1/classes/{class_id}/students", headers=headers_a
    ).json() == []

    rejoined = client.post(
        f"/api/v1/classes/{class_id}/students/{student_id}", headers=headers_a
    )
    assert rejoined.status_code == 200
    assert client.get(
        f"/api/v1/students/{student_id}", headers=headers_a
    ).status_code == 200


def test_trusted_actor_fields_homework_scope_and_audit(client: TestClient, test_engine) -> None:
    admin_auth = _register_admin(client)
    admin_headers = _auth_headers(admin_auth)
    teacher = _create_user(client, admin_headers, "teacher-a")
    teacher_headers = _auth_headers(_login(client, "teacher-a"))

    forged_question = client.post(
        "/api/v1/questions/",
        headers=teacher_headers,
        json={
            "stem": "伪造创建者",
            "question_type": "solution",
            "created_by": 999,
        },
    )
    assert forged_question.status_code == 422

    question = client.post(
        "/api/v1/questions/",
        headers=teacher_headers,
        json={"stem": "1+1=?", "question_type": "solution"},
    )
    assert question.status_code == 201, question.text
    question_id = question.json()["id"]

    class_response = client.post(
        "/api/v1/classes/",
        headers=teacher_headers,
        json={"name": "七年级一班", "grade": 7, "semester": "2026-Fall"},
    )
    class_id = class_response.json()["id"]
    student_response = client.post(
        "/api/v1/students/",
        headers=teacher_headers,
        json={
            "student_no": "S001",
            "name": "学生甲",
            "grade": 7,
            "class_id": class_id,
        },
    )
    student_id = student_response.json()["id"]
    paper = client.post(
        "/api/v1/papers/",
        headers=teacher_headers,
        json={"title": "测试卷"},
    )
    assert paper.status_code == 201, paper.text
    homework = client.post(
        "/api/v1/homework/",
        headers=teacher_headers,
        json={
            "title": "测试作业",
            "paper_id": paper.json()["id"],
            "class_ids": [class_id],
        },
    )
    assert homework.status_code == 201, homework.text
    homework_id = homework.json()["id"]

    forged_result = client.post(
        f"/api/v1/homework/{homework_id}/results",
        headers=teacher_headers,
        json={
            "student_id": student_id,
            "total_score": 80,
            "max_score": 100,
            "recorded_by": 999,
        },
    )
    assert forged_result.status_code == 422
    result = client.post(
        f"/api/v1/homework/{homework_id}/results",
        headers=teacher_headers,
        json={"student_id": student_id, "total_score": 80, "max_score": 100},
    )
    assert result.status_code == 200, result.text

    with Session(test_engine) as session:
        assert session.get(Question, question_id).created_by == teacher["id"]
        homework_result = session.exec(
            select(HomeworkResult).where(HomeworkResult.homework_id == homework_id)
        ).one()
        assert homework_result.recorded_by == teacher["id"]
        actions = set(session.exec(select(AuditLog.action)).all())
        assert {"bootstrap_admin", "login_success", "create", "create_result"} <= actions
        assert session.exec(select(ClassTeacher)).all()


def test_openapi_exposes_bearer_and_explicit_contracts(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    schemes = schema["components"]["securitySchemes"]
    assert schemes["OAuth2PasswordBearer"]["flows"]["password"]["tokenUrl"] == "/api/v1/auth/login"
    assert schema["paths"]["/api/v1/questions/"]["post"]["security"]
    request_schema = schema["paths"]["/api/v1/questions/"]["post"]["requestBody"]
    assert "QuestionCreate" in str(request_schema)
    question_properties = schema["components"]["schemas"]["QuestionCreate"]["properties"]
    assert "created_by" not in question_properties
    assert "recorded_by" not in schema["components"]["schemas"]["HomeworkResultCreate"]["properties"]
