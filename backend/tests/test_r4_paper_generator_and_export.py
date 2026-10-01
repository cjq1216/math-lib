"""R4 智能组卷与试卷导出端到端集成测试。"""

import io
from urllib.parse import unquote

import docx
from fastapi.testclient import TestClient


def _init_auth(client: TestClient) -> tuple[dict[str, str], dict[str, str]]:
    """初始化管理员与测试教师。"""
    res = client.post(
        "/api/v1/auth/register",
        json={"username": "admin", "password": "password123", "real_name": "系统管理员"},
    )
    assert res.status_code == 200
    admin_token = res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    res = client.post(
        "/api/v1/users/",
        headers=admin_headers,
        json={"username": "teacher1", "password": "password123", "real_name": "数学张老师", "role": "teacher"},
    )
    assert res.status_code == 201

    login_res = client.post("/api/v1/auth/login", data={"username": "teacher1", "password": "password123"})
    assert login_res.status_code == 200
    teacher_token = login_res.json()["access_token"]
    teacher_headers = {"Authorization": f"Bearer {teacher_token}"}

    return admin_headers, teacher_headers


def _seed_bank(client: TestClient, teacher_headers: dict[str, str]) -> dict[str, list[int]]:
    """通过 API 快速建立测试题库。"""
    # 建立知识点
    kp1 = client.post("/api/v1/knowledge/", headers=teacher_headers, json={"code": "K-01", "name": "代数", "grade": 7}).json()["id"]
    kp2 = client.post("/api/v1/knowledge/", headers=teacher_headers, json={"code": "K-02", "name": "几何", "grade": 7}).json()["id"]

    q_ids: dict[str, list[int]] = {"choice_single": [], "fill": [], "solution": []}

    # 5 道单选
    for i in range(5):
        r = client.post(
            "/api/v1/questions/",
            headers=teacher_headers,
            json={
                "stem": f"单选题 #{i + 1}：已知 $x+{i}=10$，求 $x$。",
                "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
                "question_type": "choice_single",
                "difficulty": (i % 3) + 1,
                "total_score": 3.0,
                "answer": "A",
                "analysis": f"解一元一次方程，将常数项移到右侧得 $x=10-{i}$。",
                "knowledge_points": [{"kp_id": kp1 if i < 3 else kp2, "is_primary": True}],
            },
        )
        assert r.status_code == 201
        q_ids["choice_single"].append(r.json()["id"])

    # 4 道填空
    for i in range(4):
        r = client.post(
            "/api/v1/questions/",
            headers=teacher_headers,
            json={
                "stem": f"填空题 #{i + 1}：计算 $2^{i + 1}$ 的值。",
                "question_type": "fill",
                "difficulty": (i % 3) + 2,
                "total_score": 4.0,
                "answer": str(2 ** (i + 1)),
                "analysis": "根据幂运算规则展开计算即可。",
                "knowledge_points": [{"kp_id": kp1, "is_primary": True}],
            },
        )
        assert r.status_code == 201
        q_ids["fill"].append(r.json()["id"])

    # 3 道解答
    for i in range(3):
        r = client.post(
            "/api/v1/questions/",
            headers=teacher_headers,
            json={
                "stem": f"解答题 #{i + 1}：已知三角形三边长，求面积。",
                "question_type": "solution",
                "difficulty": i + 3,
                "total_score": 10.0,
                "answer": "根据海伦公式计算面积。",
                "analysis": "半周长 $p=(a+b+c)/2$，代入面积公式即可求解。",
                "knowledge_points": [{"kp_id": kp2, "is_primary": True}],
            },
        )
        assert r.status_code == 201
        q_ids["solution"].append(r.json()["id"])

    return q_ids


def test_generate_paper_api_flow_and_structured_error(client: TestClient):
    """测试通过 API 触发智能组卷、硬约束不足报错及发布流程。"""
    _, teacher_h = _init_auth(client)
    _seed_bank(client, teacher_h)

    # 1. 约束不可满足：请求 20 道单选题（题库仅有 5 道）
    bad_req = {
        "title": "超量单选题试卷",
        "constraint": {
            "type_distribution": {"choice_single": 20, "fill": 2},
            "difficulty_ratio": {"1": 0.5, "2": 0.5},
            "total_score": 100,
        },
    }
    fail_res = client.post("/api/v1/papers/generate", headers=teacher_h, json=bad_req)
    assert fail_res.status_code == 422
    err_body = fail_res.json()["detail"]
    assert err_body["error"] == "constraint_unsatisfiable"
    assert "choice_single" in err_body["missing_types"]
    assert err_body["missing_types"]["choice_single"]["shortage"] == 15

    # 2. 正常组卷请求：单选 3 道，填空 2 道，解答 1 道，总分 50 分
    good_req = {
        "title": "七年级数学期中练习卷",
        "constraint": {
            "type_distribution": {"choice_single": 3, "fill": 2, "solution": 1},
            "difficulty_ratio": {"1": 0.3, "2": 0.4, "3": 0.3},
            "total_score": 50.0,
            "seed": 42,
        },
    }
    gen_res = client.post("/api/v1/papers/generate", headers=teacher_h, json=good_req)
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    paper_id = gen_data["paper_id"]
    assert gen_data["question_count"] == 6
    assert gen_data["total_score"] == 50.0

    # 3. 查看试卷详情状态为 draft
    paper_detail = client.get(f"/api/v1/papers/{paper_id}", headers=teacher_h).json()
    assert paper_detail["status"] == "draft"
    assert len(paper_detail["questions"]) == 6

    # 4. 发布试卷
    pub_res = client.post(f"/api/v1/papers/{paper_id}/publish", headers=teacher_h)
    assert pub_res.status_code == 200
    paper_pub = client.get(f"/api/v1/papers/{paper_id}", headers=teacher_h).json()
    assert paper_pub["status"] == "published"


def test_paper_question_adjustment_endpoints(client: TestClient):
    """测试试卷题目的单题微调：改分自动重算总分、题目替换、题目删除及批量重排。"""
    _, teacher_h = _init_auth(client)
    _seed_bank(client, teacher_h)

    # 生成初始试卷
    gen_res = client.post(
        "/api/v1/papers/generate",
        headers=teacher_h,
        json={
            "title": "微调试卷",
            "constraint": {
                "type_distribution": {"choice_single": 2, "fill": 2},
                "total_score": 20.0,
            },
        },
    ).json()
    paper_id = gen_res["paper_id"]

    detail = client.get(f"/api/v1/papers/{paper_id}", headers=teacher_h).json()
    questions = detail["questions"]
    assert len(questions) == 4
    pq1 = questions[0]
    pq2 = questions[1]

    # 1. 修改单题分值：将第 1 题分值从 5 分改为 10 分
    update_res = client.put(
        f"/api/v1/papers/{paper_id}/questions/{pq1['id']}",
        headers=teacher_h,
        json={"score": 10.0},
    )
    assert update_res.status_code == 200
    assert update_res.json()["score"] == 10.0

    # 验证试卷总分从 20 分自动重算并更新为 25 分
    fresh_paper = client.get(f"/api/v1/papers/{paper_id}", headers=teacher_h).json()
    assert fresh_paper["total_score"] == 25.0

    # 2. 题目替换：替换第 2 题
    old_stem = pq2["stem"]
    replace_res = client.post(
        f"/api/v1/papers/{paper_id}/questions/{pq2['id']}/replace",
        headers=teacher_h,
        json={},
    )
    assert replace_res.status_code == 200
    replaced_pq = replace_res.json()
    assert replaced_pq["stem"] != old_stem

    # 3. 题目重排
    reorder_res = client.put(
        f"/api/v1/papers/{paper_id}/questions/reorder",
        headers=teacher_h,
        json={
            "items": [
                {"paper_question_id": pq1["id"], "display_order": 2},
                {"paper_question_id": pq2["id"], "display_order": 1},
            ]
        },
    )
    assert reorder_res.status_code == 200

    # 4. 删除单题：删除第 1 题
    del_res = client.delete(
        f"/api/v1/papers/{paper_id}/questions/{pq1['id']}",
        headers=teacher_h,
    )
    assert del_res.status_code == 200

    # 验证题目总数由 4 变 3，题号连续
    after_del = client.get(f"/api/v1/papers/{paper_id}", headers=teacher_h).json()
    assert len(after_del["questions"]) == 3
    orders = [q["display_order"] for q in after_del["questions"]]
    assert orders == [1, 2, 3]


def test_export_markdown_stream(client: TestClient):
    """测试真实 Markdown 导出文件流及排版内容。"""
    _, teacher_h = _init_auth(client)
    _seed_bank(client, teacher_h)

    gen_res = client.post(
        "/api/v1/papers/generate",
        headers=teacher_h,
        json={
            "title": "初一数学随堂达标卷",
            "constraint": {
                "type_distribution": {"choice_single": 2, "fill": 1},
                "total_score": 30.0,
            },
        },
    ).json()
    paper_id = gen_res["paper_id"]

    # 调用 Markdown 导出
    export_res = client.get(f"/api/v1/papers/{paper_id}/export?format=markdown", headers=teacher_h)
    assert export_res.status_code == 200
    assert "text/markdown" in export_res.headers["Content-Type"]
    assert "attachment" in export_res.headers["Content-Disposition"]
    assert ".md" in unquote(export_res.headers["Content-Disposition"])

    md_text = export_res.content.decode("utf-8")
    assert "# 初一数学随堂达标卷" in md_text
    assert "满分" in md_text
    assert "考试时间" in md_text
    assert "班级：" in md_text
    assert "参考答案与解析" in md_text
    assert "参考答案速查" in md_text
    assert "试题详细解析" in md_text


def test_export_word_docx_stream(client: TestClient):
    """测试真实 Word (.docx) 导出文件流与文档结构解析。"""
    _, teacher_h = _init_auth(client)
    _seed_bank(client, teacher_h)

    gen_res = client.post(
        "/api/v1/papers/generate",
        headers=teacher_h,
        json={
            "title": "期中模拟检测标准试卷",
            "constraint": {
                "type_distribution": {"choice_single": 2, "fill": 1, "solution": 1},
                "total_score": 40.0,
            },
        },
    ).json()
    paper_id = gen_res["paper_id"]

    # 调用 Word 导出
    export_res = client.get(f"/api/v1/papers/{paper_id}/export?format=word", headers=teacher_h)
    assert export_res.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in export_res.headers["Content-Type"]
    assert ".docx" in unquote(export_res.headers["Content-Disposition"])

    # 用 python-docx 解析二进制文件流
    doc = docx.Document(io.BytesIO(export_res.content))
    full_text = "\n".join(p.text for p in doc.paragraphs)

    assert "期中模拟检测标准试卷" in full_text
    assert "考试时长" in full_text
    assert "参考答案与解析" in full_text
    assert "试题详细解析与步骤" in full_text

    # 验证答案表格存在且有效
    assert len(doc.tables) >= 1
    table = doc.tables[0]
    headers = [cell.text for cell in table.rows[0].cells]
    assert "题号" in headers
    assert "参考答案" in headers
    assert len(table.rows) == 5  # 1 表头 + 4 道题
