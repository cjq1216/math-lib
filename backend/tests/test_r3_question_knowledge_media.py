"""R3 题库、知识点与媒体完整性回归测试与试卷快照隔离验证。"""

import base64
import io

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.paper import Paper, PaperQuestion, PaperStatus

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
TINY_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><circle cx="5" cy="5" r="4"/></svg>'


def _init_auth(client: TestClient) -> tuple[dict[str, str], dict[str, str]]:
    """初始化管理员与测试教师。"""
    res = client.post(
        "/api/v1/auth/register",
        json={"username": "admin", "password": "password123", "real_name": "系统管理员"},
    )
    assert res.status_code == 200, res.text
    admin_token = res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    res = client.post(
        "/api/v1/users/",
        headers=admin_headers,
        json={"username": "teacher1", "password": "password123", "real_name": "数学张老师", "role": "teacher"},
    )
    assert res.status_code == 201, res.text

    login_res = client.post("/api/v1/auth/login", data={"username": "teacher1", "password": "password123"})
    assert login_res.status_code == 200
    teacher_token = login_res.json()["access_token"]
    teacher_headers = {"Authorization": f"Bearer {teacher_token}"}

    return admin_headers, teacher_headers


def test_question_aggregate_creation_and_transaction_rollback(client: TestClient):
    """测试题目单事务聚合创建、失败原子回滚与 Checksum 自动生成。"""
    admin_h, teacher_h = _init_auth(client)

    # 1. 准备前置数据：创建知识点和媒体
    kp1_res = client.post(
        "/api/v1/knowledge/",
        headers=teacher_h,
        json={"code": "G7-01", "name": "有理数基础", "grade": 7},
    )
    assert kp1_res.status_code == 201
    kp1_id = kp1_res.json()["id"]

    media_res = client.post(
        "/api/v1/media/upload",
        headers=teacher_h,
        files={"file": ("test.png", io.BytesIO(TINY_PNG), "image/png")},
    )
    assert media_res.status_code == 200
    media_id = media_res.json()["id"]

    # 2. 失败原子回滚测试：传入不存在的知识点 ID
    bad_payload_kp = {
        "stem": "若 $x + 1 = 0$，求 $x$ 的值。",
        "question_type": "fill",
        "difficulty": 2,
        "total_score": 5.0,
        "knowledge_points": [{"kp_id": 99999, "is_primary": True, "weight": 1.0}],
    }
    fail_kp = client.post("/api/v1/questions/", headers=teacher_h, json=bad_payload_kp)
    assert fail_kp.status_code == 422
    # 确认题库中没有任何残留记录
    list_res = client.get("/api/v1/questions/", headers=teacher_h)
    assert list_res.json()["total"] == 0

    # 3. 失败原子回滚测试：传入不存在的媒体 ID
    bad_payload_media = {
        "stem": "若 $x + 2 = 0$，求 $x$ 的值。",
        "question_type": "fill",
        "difficulty": 2,
        "total_score": 5.0,
        "media_items": [{"media_id": 99999, "usage_type": "stem"}],
    }
    fail_media = client.post("/api/v1/questions/", headers=teacher_h, json=bad_payload_media)
    assert fail_media.status_code == 422
    assert client.get("/api/v1/questions/", headers=teacher_h).json()["total"] == 0

    # 4. 成功聚合创建：主表、小问、多空答案与规则、知识点、媒体一次性写入
    valid_payload = {
        "stem": "解方程组：(1) $x + y = 3$; (2) $x - y = 1$。",
        "options": None,
        "question_type": "solution",
        "difficulty": 3,
        "total_score": 10.0,
        "answer": "$x=2, y=1$",
        "analysis": "利用加减消元法求解。",
        "tags": ["期中", "易错"],
        "is_verified": True,
        "sub_questions": [
            {"label": "(1)", "stem": "求 $x$ 的值", "score": 5.0, "answer": "$x=2$"},
            {"label": "(2)", "stem": "求 $y$ 的值", "score": 5.0, "answer": "$y=1$"},
        ],
        "answers": [
            {
                "blank_index": 1,
                "answer_text": "2",
                "is_primary": True,
                "match_rule": {"rule_type": "exact"},
            },
            {
                "blank_index": 2,
                "answer_text": "1",
                "is_primary": True,
                "match_rule": {"rule_type": "exact"},
            },
        ],
        "knowledge_points": [
            {"kp_id": kp1_id, "is_primary": True, "weight": 1.0},
        ],
        "media_items": [
            {"media_id": media_id, "usage_type": "stem", "caption": "图1", "alt_text": "坐标示意"},
        ],
    }

    create_res = client.post("/api/v1/questions/", headers=teacher_h, json=valid_payload)
    assert create_res.status_code == 201
    qid = create_res.json()["id"]

    # 5. 校验获取详情完整性
    get_res = client.get(f"/api/v1/questions/{qid}", headers=teacher_h)
    assert get_res.status_code == 200
    q_data = get_res.json()

    assert q_data["id"] == qid
    assert q_data["is_verified"] is True
    assert q_data["checksum"] is not None and len(q_data["checksum"]) == 64
    assert len(q_data["sub_questions"]) == 2
    assert q_data["sub_questions"][0]["label"] == "(1)"
    assert len(q_data["answers"]) == 2
    assert q_data["answers"][0]["match_rule"]["rule_type"] == "exact"
    assert len(q_data["knowledge_points"]) == 1
    assert q_data["knowledge_points"][0]["kp_id"] == kp1_id
    assert len(q_data["media_items"]) == 1
    assert q_data["media_items"][0]["media_id"] == media_id
    assert q_data["media_items"][0]["access_url"] is not None

    # 6. 校验媒体引用计数已被正确累加为 1
    media_list = client.get("/api/v1/media/", headers=teacher_h).json()
    assert len(media_list) == 1
    assert media_list[0]["reference_count"] == 1


def test_question_aggregate_update_and_media_reference_count(client: TestClient):
    """测试题目单事务聚合更新、Checksum 重算与媒体引用计数同步调整。"""
    admin_h, teacher_h = _init_auth(client)

    # 上传 2 个媒体资源
    m1_res = client.post("/api/v1/media/upload", headers=teacher_h, files={"file": ("m1.png", io.BytesIO(TINY_PNG), "image/png")})
    m1_id = m1_res.json()["id"]

    m2_res = client.post("/api/v1/media/upload", headers=teacher_h, files={"file": ("m2.svg", io.BytesIO(TINY_SVG), "image/svg+xml")})
    m2_id = m2_res.json()["id"]

    kp_res = client.post("/api/v1/knowledge/", headers=teacher_h, json={"code": "G7-02", "name": "方程求解", "grade": 7})
    kp_id = kp_res.json()["id"]

    # 初始创建题目，关联 m1
    init_res = client.post(
        "/api/v1/questions/",
        headers=teacher_h,
        json={
            "stem": "初版题干 $x=1$",
            "question_type": "fill",
            "difficulty": 1,
            "total_score": 5.0,
            "knowledge_points": [{"kp_id": kp_id, "is_primary": True}],
            "media_items": [{"media_id": m1_id, "usage_type": "stem"}],
        },
    )
    assert init_res.status_code == 201
    qid = init_res.json()["id"]

    old_checksum = client.get(f"/api/v1/questions/{qid}", headers=teacher_h).json()["checksum"]

    # 检查初始媒体引用计数：m1 为 1，m2 为 0
    media_dict = {m["id"]: m["reference_count"] for m in client.get("/api/v1/media/", headers=teacher_h).json()}
    assert media_dict[m1_id] == 1
    assert media_dict[m2_id] == 0

    # 执行聚合更新：修改题干、替换关联媒体（移除 m1，改为 m2）
    update_res = client.patch(
        f"/api/v1/questions/{qid}",
        headers=teacher_h,
        json={
            "stem": "更新后题干 $x=2$",
            "media_items": [{"media_id": m2_id, "usage_type": "analysis", "caption": "解析配图"}],
        },
    )
    assert update_res.status_code == 200

    # 验证更新后 Checksum 已改变
    new_q = client.get(f"/api/v1/questions/{qid}", headers=teacher_h).json()
    assert new_q["stem"] == "更新后题干 $x=2$"
    assert new_q["checksum"] != old_checksum
    assert len(new_q["media_items"]) == 1
    assert new_q["media_items"][0]["media_id"] == m2_id

    # 验证媒体引用计数：m1 降为 0，m2 升为 1
    media_dict_after = {m["id"]: m["reference_count"] for m in client.get("/api/v1/media/", headers=teacher_h).json()}
    assert media_dict_after[m1_id] == 0
    assert media_dict_after[m2_id] == 1


def test_knowledge_tree_hierarchy_cycles_and_delete_protection(client: TestClient):
    """测试知识点树层级深度、循环引用防御、题目引用保护与迁移删除、恢复及 JSON 导入导出。"""
    admin_h, teacher_h = _init_auth(client)

    # 1. 创建节点 A -> B -> C
    a_res = client.post("/api/v1/knowledge/", headers=teacher_h, json={"code": "KP-A", "name": "代数基础", "grade": 7})
    assert a_res.status_code == 201
    id_a = a_res.json()["id"]

    b_res = client.post("/api/v1/knowledge/", headers=teacher_h, json={"code": "KP-B", "name": "整式", "parent_id": id_a, "grade": 7})
    assert b_res.status_code == 201
    id_b = b_res.json()["id"]

    c_res = client.post("/api/v1/knowledge/", headers=teacher_h, json={"code": "KP-C", "name": "单项式", "parent_id": id_b, "grade": 7})
    assert c_res.status_code == 201
    id_c = c_res.json()["id"]

    # 2. 循环引用校验：尝试将 A 的父节点设置为 C（形成 A -> B -> C -> A 闭环）
    cycle_res = client.patch(f"/api/v1/knowledge/{id_a}", headers=teacher_h, json={"parent_id": id_c})
    assert cycle_res.status_code == 422
    assert "循环引用" in cycle_res.json()["detail"]

    # 尝试将 A 的父节点设为自身
    self_res = client.patch(f"/api/v1/knowledge/{id_a}", headers=teacher_h, json={"parent_id": id_a})
    assert self_res.status_code == 422
    assert "不能以自身为父节点" in self_res.json()["detail"]

    # 3. 年级不一致校验
    grade_mismatch = client.post("/api/v1/knowledge/", headers=teacher_h, json={"code": "KP-D", "name": "几何", "parent_id": id_a, "grade": 8})
    assert grade_mismatch.status_code == 422
    assert "不一致" in grade_mismatch.json()["detail"]

    # 4. 删除保护：A 拥有活跃子节点 B，禁止删除
    del_a = client.delete(f"/api/v1/knowledge/{id_a}", headers=teacher_h)
    assert del_a.status_code == 422
    assert "仍有活跃子知识点" in del_a.json()["detail"]

    # 5. 题目引用保护：录入一道关联 C 的题目，尝试删除 C
    q_res = client.post(
        "/api/v1/questions/",
        headers=teacher_h,
        json={"stem": "单项式系数是几？", "total_score": 5.0, "knowledge_points": [{"kp_id": id_c, "is_primary": True}]},
    )
    assert q_res.status_code == 201

    del_c_blocked = client.delete(f"/api/v1/knowledge/{id_c}", headers=teacher_h)
    assert del_c_blocked.status_code == 422
    assert "题目使用，禁止删除" in del_c_blocked.json()["detail"]

    # 6. 带 target_kp_id 迁移删除：将 C 的题目引用迁移到 B，然后成功软删 C
    del_c_migrated = client.delete(f"/api/v1/knowledge/{id_c}?target_kp_id={id_b}", headers=teacher_h)
    assert del_c_migrated.status_code == 200

    # 验证题目的知识点已迁移至 B
    qid = q_res.json()["id"]
    q_data = client.get(f"/api/v1/questions/{qid}", headers=teacher_h).json()
    assert q_data["knowledge_points"][0]["kp_id"] == id_b

    # 7. 软删恢复测试
    restore_c = client.post(f"/api/v1/knowledge/{id_c}/restore", headers=teacher_h)
    assert restore_c.status_code == 200
    c_data = client.get("/api/v1/knowledge/", headers=teacher_h, params={"include_inactive": False}).json()
    assert any(k["id"] == id_c for k in c_data)

    # 8. 导出与导入验证
    export_res = client.get("/api/v1/knowledge/export", headers=teacher_h)
    assert export_res.status_code == 200
    export_items = export_res.json()
    assert len(export_items) >= 3

    # 验证导出的数据包含 parent_code
    b_export = next(k for k in export_items if k["code"] == "KP-B")
    assert b_export["parent_code"] == "KP-A"

    # 测试通过 parent_code 导入新树结构
    import_payload = {
        "items": [
            {"code": "G8-ROOT", "name": "八年级根", "grade": 8},
            {"code": "G8-SUB1", "name": "八年级第一章", "grade": 8, "parent_code": "G8-ROOT"},
        ]
    }
    import_res = client.post("/api/v1/knowledge/import", headers=teacher_h, json=import_payload)
    assert import_res.status_code == 200
    assert import_res.json()["count"] == 2

    # 查询树确认父子关系建立
    g8_tree = client.get("/api/v1/knowledge/tree", headers=teacher_h, params={"grade": 8}).json()
    assert len(g8_tree) == 1
    assert g8_tree[0]["code"] == "G8-ROOT"
    assert len(g8_tree[0]["children"]) == 1
    assert g8_tree[0]["children"][0]["code"] == "G8-SUB1"


def test_media_safety_validation_deduplication_and_lifecycle(client: TestClient):
    """测试媒体格式白名单、真实图片解码、孤儿文件清理与无引用物理删除。"""
    admin_h, teacher_h = _init_auth(client)

    # 1. 非法格式与篡改校验：虚假后缀图片（文本伪造为 png）
    fake_png = b"THIS IS NOT A VALID PNG FILE AT ALL"
    bad_upload = client.post(
        "/api/v1/media/upload",
        headers=teacher_h,
        files={"file": ("fake.png", io.BytesIO(fake_png), "image/png")},
    )
    assert bad_upload.status_code == 422
    assert "无效或已损坏" in bad_upload.json()["detail"]

    # 2. 不支持的扩展名
    bad_ext = client.post(
        "/api/v1/media/upload",
        headers=teacher_h,
        files={"file": ("script.exe", io.BytesIO(TINY_PNG), "application/octet-stream")},
    )
    assert bad_ext.status_code == 422
    assert "不支持的文件扩展名" in bad_ext.json()["detail"]

    # 3. 正常上传 PNG 与 SVG，初始引用计数均为 0
    png_res = client.post(
        "/api/v1/media/upload",
        headers=teacher_h,
        files={"file": ("real.png", io.BytesIO(TINY_PNG), "image/png")},
    )
    assert png_res.status_code == 200
    p_data = png_res.json()
    assert p_data["deduplicated"] is False
    assert p_data["reference_count"] == 0
    assert p_data["width"] == 1
    assert p_data["height"] == 1
    png_id = p_data["id"]

    svg_res = client.post(
        "/api/v1/media/upload",
        headers=teacher_h,
        files={"file": ("real.svg", io.BytesIO(TINY_SVG), "image/svg+xml")},
    )
    assert svg_res.status_code == 200
    assert svg_res.json()["reference_count"] == 0
    svg_id = svg_res.json()["id"]

    # 4. MD5 重复上传去重测试
    dup_res = client.post(
        "/api/v1/media/upload",
        headers=teacher_h,
        files={"file": ("another_name.png", io.BytesIO(TINY_PNG), "image/png")},
    )
    assert dup_res.status_code == 200
    assert dup_res.json()["deduplicated"] is True
    assert dup_res.json()["id"] == png_id
    assert dup_res.json()["reference_count"] == 0

    # 5. 独立关联与解除接口测试
    q_res = client.post(
        "/api/v1/questions/",
        headers=teacher_h,
        json={"stem": "配图题目", "total_score": 5.0},
    )
    qid = q_res.json()["id"]

    # 关联 svg_id
    assoc_res = client.post(
        f"/api/v1/questions/{qid}/media",
        headers=teacher_h,
        json={"media_id": svg_id, "usage_type": "stem", "caption": "几何图形"},
    )
    assert assoc_res.status_code == 200

    # 验证引用计数变 1，此时尝试删除媒体应被拦截
    m_info = next(m for m in client.get("/api/v1/media/", headers=teacher_h).json() if m["id"] == svg_id)
    assert m_info["reference_count"] == 1

    del_blocked = client.delete(f"/api/v1/media/{svg_id}", headers=teacher_h)
    assert del_blocked.status_code == 400
    assert "仍被题目引用" in del_blocked.json()["detail"]

    # 解除关联
    disassoc_res = client.delete(f"/api/v1/questions/{qid}/media/{svg_id}", headers=teacher_h)
    assert disassoc_res.status_code == 200

    # 此时引用计数回降为 0，允许物理删除
    del_ok = client.delete(f"/api/v1/media/{svg_id}", headers=teacher_h)
    assert del_ok.status_code == 200


def test_paper_snapshot_isolation(client: TestClient, test_engine):
    """验证历史试卷快照隔离（ADR-002）：原题修改或软删除绝对不污染已有试卷。"""
    admin_h, teacher_h = _init_auth(client)

    # 1. 创建原题（包含题干、选项、答案与解析）
    original_stem = "已知 $x^2 - 5x + 6 = 0$，求方程的解。"
    original_options = ["A. $x_1=2, x_2=3$", "B. $x_1=-2, x_2=-3$", "C. $x=1$", "D. 无解"]
    original_answer = "A"
    original_analysis = "因式分解 $(x-2)(x-3)=0$，故 $x_1=2, x_2=3$。"

    q_res = client.post(
        "/api/v1/questions/",
        headers=teacher_h,
        json={
            "stem": original_stem,
            "options": original_options,
            "question_type": "choice_single",
            "difficulty": 2,
            "total_score": 10.0,
            "answer": original_answer,
            "analysis": original_analysis,
        },
    )
    assert q_res.status_code == 201
    qid = q_res.json()["id"]

    # 2. 创建试卷并将该题加入试卷（写入快照字段）
    with Session(test_engine) as session:
        paper = Paper(
            title="2026学年七年级期中数学测试",
            total_score=100.0,
            duration_minutes=90,
            status=PaperStatus.PUBLISHED,
            question_count=1,
            created_by=1,
        )
        session.add(paper)
        session.flush()

        paper_q = PaperQuestion(
            paper_id=paper.id,
            question_id=qid,
            section="一、选择题",
            display_order=1,
            score=10.0,
            stem_snapshot=original_stem,
            answer_snapshot=original_answer,
            analysis_snapshot=original_analysis,
            options_snapshot=original_options,
        )
        session.add(paper_q)
        session.commit()
        paper_id = paper.id

    # 3. 校验试卷详情正确返回历史快照
    paper_res = client.get(f"/api/v1/papers/{paper_id}", headers=teacher_h)
    assert paper_res.status_code == 200
    paper_data = paper_res.json()
    assert len(paper_data["questions"]) == 1
    snapshot = paper_data["questions"][0]
    assert snapshot["stem"] == original_stem
    assert snapshot["answer"] == original_answer
    assert snapshot["analysis"] == original_analysis
    assert snapshot["options"] == original_options

    # 4. 大幅度篡改题库原题：变更题干、选项、答案与解析
    tampered_stem = "【已修改】完全不同的全新题面：求 $\\sqrt{16}$ 的值。"
    tampered_options = ["A. 4", "B. -4", "C. $\\pm 4$", "D. 16"]
    tampered_answer = "A"
    tampered_analysis = "算术平方根非负，故为 4。"

    patch_res = client.patch(
        f"/api/v1/questions/{qid}",
        headers=teacher_h,
        json={
            "stem": tampered_stem,
            "options": tampered_options,
            "answer": tampered_answer,
            "analysis": tampered_analysis,
            "difficulty": 1,
        },
    )
    assert patch_res.status_code == 200

    # 软删除原题
    del_res = client.delete(f"/api/v1/questions/{qid}", headers=teacher_h)
    assert del_res.status_code == 200

    # 验证题库中原题已被修改且停用
    q_after = client.get(f"/api/v1/questions/{qid}", headers=teacher_h).json()
    assert q_after["stem"] == tampered_stem
    # 活跃题库列表不再返回该题
    active_list = client.get("/api/v1/questions/", headers=teacher_h, params={"is_active": True}).json()
    assert not any(q["id"] == qid for q in active_list["items"])

    # 5. 核心断言：重新读取已发布试卷详情，验证快照 100% 保持原样，原题的篡改和删除对历史试卷零影响！
    paper_res_again = client.get(f"/api/v1/papers/{paper_id}", headers=teacher_h)
    assert paper_res_again.status_code == 200
    paper_data_again = paper_res_again.json()
    assert len(paper_data_again["questions"]) == 1
    frozen_snapshot = paper_data_again["questions"][0]

    assert frozen_snapshot["stem"] == original_stem
    assert frozen_snapshot["answer"] == original_answer
    assert frozen_snapshot["analysis"] == original_analysis
    assert frozen_snapshot["options"] == original_options
    assert frozen_snapshot["stem"] != tampered_stem
