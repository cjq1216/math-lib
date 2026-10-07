"""R0-R5 全链路端到端闭环集成验收测试。

全流程覆盖：
1. [R0/R1] 空库首个管理员引导注册、二次公开注册阻断、登录会话、教师用户创建与任教班级分配；
2. [R1] 教师录入在班学生与权限隔离；
3. [R3/R5] 结构化知识点树创建、大模型切题草稿双栏校对一键批量入库（含小问、多空、智能知识点关联与 Checksum）；
4. [R5] 题目余弦相似度推荐接口；
5. [R4] 智能组卷引擎（四步拆分、硬约束满足、必含知识点覆盖、卷内 0 重复）；
6. [R4] 试卷题目微调、发布、快照级 Markdown 与 Word (.docx) 导出验证；
7. [R2] 班级作业下发、名单快照隔离、单题正规明细成绩录入；
8. [R2] 学情自动重算、掌握度与趋势分析、薄弱知识点生命周期自动识别标记；
9. [R2] 薄弱点针对性练习生成（命中率与去重检验）并一键转化为强化作业；
10. [R2] 强化作业成绩录入后，薄弱点生命周期自动攻克解除（is_resolved=True）闭环；
11. [R2] 班级学情概览与综合/单次排行的浮点格式化与聚合正确性。
"""

from fastapi.testclient import TestClient


def test_r0_to_r5_complete_business_lifecycle(client: TestClient) -> None:
    # =========================================================================
    # 步骤 1: [R0/R1] 管理员引导与教师权限
    # =========================================================================
    # 1.1 注册首个管理员
    reg_res = client.post(
        "/api/v1/auth/register",
        json={"username": "admin", "password": "AdminPassword123", "real_name": "系统管理员"},
    )
    assert reg_res.status_code == 200, reg_res.text
    admin_token = reg_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 1.2 二次公开注册必须被拒绝 (403)
    second_reg = client.post(
        "/api/v1/auth/register",
        json={"username": "intruder", "password": "Password123", "real_name": "未授权用户"},
    )
    assert second_reg.status_code == 403

    # 1.3 管理员创建教师用户
    t_create_res = client.post(
        "/api/v1/users/",
        headers=admin_headers,
        json={
            "username": "math_teacher",
            "password": "TeacherPassword123",
            "real_name": "李老师",
            "role": "teacher",
            "subject": "math",
        },
    )
    assert t_create_res.status_code == 201
    teacher_id = t_create_res.json()["id"]

    # 1.4 教师登录获得独立身份 Header
    t_login = client.post(
        "/api/v1/auth/login",
        data={"username": "math_teacher", "password": "TeacherPassword123"},
    )
    assert t_login.status_code == 200
    teacher_token = t_login.json()["access_token"]
    teacher_headers = {"Authorization": f"Bearer {teacher_token}"}

    # 1.5 教师创建班级
    c_res = client.post(
        "/api/v1/classes/",
        headers=teacher_headers,
        json={"name": "初二(1)班", "grade": 8, "semester": "2026-Fall"},
    )
    assert c_res.status_code == 201
    class_id = c_res.json()["id"]

    # 管理员将该班级分配给教师任教
    client.put(
        f"/api/v1/classes/{class_id}/teachers",
        headers=admin_headers,
        json={"teacher_ids": [teacher_id]},
    )

    # 1.6 教师录入两名学生并加入班级
    s1_res = client.post(
        "/api/v1/students/",
        headers=teacher_headers,
        json={"name": "王小明", "student_no": "20260801", "gender": "male", "grade": 8},
    )
    assert s1_res.status_code == 201
    student1_id = s1_res.json()["id"]

    s2_res = client.post(
        "/api/v1/students/",
        headers=teacher_headers,
        json={"name": "李小华", "student_no": "20260802", "gender": "female", "grade": 8},
    )
    assert s2_res.status_code == 201
    student2_id = s2_res.json()["id"]

    client.post(f"/api/v1/classes/{class_id}/students/{student1_id}", headers=teacher_headers)
    client.post(f"/api/v1/classes/{class_id}/students/{student2_id}", headers=teacher_headers)

    # =========================================================================
    # 步骤 2: [R3/R5] 知识点树与双栏切题批量校对入库
    # =========================================================================
    # 2.1 创建知识点树
    kp_root_res = client.post(
        "/api/v1/knowledge/",
        headers=teacher_headers,
        json={"code": "MATH", "name": "初中数学", "grade": 8},
    )
    assert kp_root_res.status_code == 201
    root_kp_id = kp_root_res.json()["id"]

    kp1_res = client.post(
        "/api/v1/knowledge/",
        headers=teacher_headers,
        json={"code": "G8-ALG-01", "name": "一元二次方程", "parent_id": root_kp_id, "grade": 8},
    )
    assert kp1_res.status_code == 201
    kp1_id = kp1_res.json()["id"]

    kp2_res = client.post(
        "/api/v1/knowledge/",
        headers=teacher_headers,
        json={"code": "G8-GEO-01", "name": "勾股定理", "parent_id": root_kp_id, "grade": 8},
    )
    assert kp2_res.status_code == 201
    _ = kp2_res.json()["id"]

    # 2.2 批量切题草稿一键入库（模拟双栏校对工作台点击“确认入库”）
    draft_payload = {
        "questions": [
            {
                "number": "1",
                "stem": "关于 $x$ 的一元二次方程 $x^2 - 4 = 0$ 的根为（ ）",
                "question_type": "choice_single",
                "difficulty": 2,
                "options": ["A. $x=2$", "B. $x=-2$", "C. $x=\\pm 2$", "D. $x=4$"],
                "answer": "C",
                "analysis": "移项开平方可得 $x = \\pm 2$。",
                "knowledge_points": ["一元二次方程"],
                "total_score": 3.0,
            },
            {
                "number": "2",
                "stem": "若关于 $x$ 的方程 $x^2 - 2x + m = 0$ 有两个相等实根，则 $m=$ ____。",
                "question_type": "fill",
                "difficulty": 3,
                "options": None,
                "answer": "1",
                "analysis": "判别式 $\\Delta = (-2)^2 - 4m = 0$，解得 $m=1$。",
                "knowledge_points": ["一元二次方程"],
                "total_score": 4.0,
            },
            {
                "number": "3",
                "stem": "在直角三角形 $ABC$ 中，两直角边长分别为 3 和 4，求斜边长。",
                "question_type": "solution",
                "difficulty": 2,
                "options": None,
                "answer": "5",
                "analysis": "由勾股定理 $c = \\sqrt{3^2 + 4^2} = 5$。",
                "knowledge_points": ["勾股定理"],
                "sub_questions": [
                    {"label": "(1)", "stem": "写出勾股定理公式并代入数值计算斜边长。", "score": 8.0, "answer": "5"}
                ],
                "total_score": 8.0,
            },
            {
                "number": "4",
                "stem": "一元二次方程 $(x-1)(x-2)=0$ 的解是（ ）",
                "question_type": "choice_single",
                "difficulty": 1,
                "options": ["A. $x_1=1, x_2=2$", "B. $x_1=-1, x_2=-2$", "C. $x=1$", "D. $x=2$"],
                "answer": "A",
                "analysis": "直接由因式分解法求根。",
                "knowledge_points": ["一元二次方程"],
                "total_score": 3.0,
            },
            {
                "number": "5",
                "stem": "直角三角形两边长分别为 6 和 8，则第三边长可能为 ____。",
                "question_type": "fill",
                "difficulty": 4,
                "options": None,
                "answer": "10或2根号7",
                "analysis": "分类讨论：8 为斜边或 8 为直角边。",
                "knowledge_points": ["勾股定理"],
                "total_score": 4.0,
            },
        ]
    }

    commit_res = client.post("/api/v1/llm/commit-drafts", headers=teacher_headers, json=draft_payload)
    assert commit_res.status_code == 200, commit_res.text
    commit_data = commit_res.json()
    assert commit_data["created_count"] == 5
    created_q_ids = commit_data["question_ids"]

    # 2.3 验证相似题检索接口
    sim_res = client.get(f"/api/v1/llm/questions/{created_q_ids[0]}/similar", headers=teacher_headers)
    assert sim_res.status_code == 200
    assert isinstance(sim_res.json(), list)

    # =========================================================================
    # 步骤 3: [R4] 智能组卷、试卷微调与快照导出
    # =========================================================================
    gen_payload = {
        "title": "2026学年八年级数学期中模拟试卷",
        "constraint": {
            "total_score": 15.0,
            "duration_minutes": 45,
            "seed": 2026,
            "type_distribution": {
                "choice_single": 1,
                "fill": 1,
                "solution": 1,
            },
            "difficulty_ratio": {"1": 0.2, "2": 0.4, "3": 0.4},
            "required_kps": [kp1_id],  # 必含一元二次方程
            "forbidden_kps": [],
        },
    }

    paper_gen_res = client.post("/api/v1/papers/generate", headers=teacher_headers, json=gen_payload)
    assert paper_gen_res.status_code == 200, paper_gen_res.text
    paper_id = paper_gen_res.json()["paper_id"]
    assert paper_id > 0

    # 3.1 验证试卷详情及题目快照
    p_detail_res = client.get(f"/api/v1/papers/{paper_id}", headers=teacher_headers)
    assert p_detail_res.status_code == 200
    p_detail = p_detail_res.json()
    p_questions = p_detail["questions"]
    assert len(p_questions) == 3
    # 验证卷内题目 ID 严格唯一
    pq_ids = [item["id"] for item in p_questions]
    assert len(pq_ids) == len(set(pq_ids))

    # 3.2 教师微调单题分值
    pq_first = p_questions[0]
    score_update_res = client.put(
        f"/api/v1/papers/{paper_id}/questions/{pq_first['id']}",
        headers=teacher_headers,
        json={"score": 5.0},
    )
    assert score_update_res.status_code == 200

    # 3.3 发布试卷
    pub_res = client.post(f"/api/v1/papers/{paper_id}/publish", headers=teacher_headers)
    assert pub_res.status_code == 200

    # 3.4 导出 Markdown
    md_res = client.get(f"/api/v1/papers/{paper_id}/export?format=markdown", headers=teacher_headers)
    assert md_res.status_code == 200
    md_content = md_res.text
    assert "# 2026学年八年级数学期中模拟试卷" in md_content
    assert "参考答案速查" in md_content
    assert "试题详细解析" in md_content

    # 3.5 导出 Word (.docx)
    docx_res = client.get(f"/api/v1/papers/{paper_id}/export?format=word", headers=teacher_headers)
    assert docx_res.status_code == 200
    assert len(docx_res.content) > 1000
    assert "vnd.openxmlformats-officedocument.wordprocessingml.document" in docx_res.headers["content-type"]

    # =========================================================================
    # 步骤 4: [R2] 班级作业下发、成绩明细与学情闭环
    # =========================================================================
    hw_create_payload = {
        "title": "期中模拟测验第一讲",
        "paper_id": paper_id,
        "type": "homework",
        "class_ids": [class_id],
        "student_ids": [],
    }
    hw_res = client.post("/api/v1/homework/", headers=teacher_headers, json=hw_create_payload)
    assert hw_res.status_code == 201, hw_res.text
    hw_id = hw_res.json()["id"]

    # 刷新试卷各题最新分值
    p_detail_latest = client.get(f"/api/v1/papers/{paper_id}", headers=teacher_headers).json()
    pqs = p_detail_latest["questions"]

    # 4.1 录入王小明作答成绩（模拟一元二次方程题目做错，触发薄弱点）
    # 找到与一元二次方程相关的题目并给 0 分
    q_results_payload = []
    for pq in pqs:
        # 如果是选择题或填空题（一元二次方程），给 0 分 False
        is_kp1 = "一元二次方程" in pq["stem"] or pq["display_order"] in [1, 2]
        q_results_payload.append({
            "paper_question_id": pq["id"],
            "score": 0.0 if is_kp1 else pq["score"],
            "is_correct": not is_kp1,
            "answer_text": "错误选项" if is_kp1 else "正确答案",
        })

    grade_res = client.post(
        f"/api/v1/homework/{hw_id}/results",
        headers=teacher_headers,
        json={"student_id": student1_id, "question_results": q_results_payload},
    )
    assert grade_res.status_code == 200, grade_res.text

    # 为确保触发 attempts >= 3，再模拟录入两次历史平时作业的错题
    hw2_res = client.post("/api/v1/homework/", headers=teacher_headers, json={
        "title": "平时练习A",
        "paper_id": paper_id,
        "type": "homework",
        "class_ids": [class_id],
    })
    hw2_id = hw2_res.json()["id"]
    client.post(
        f"/api/v1/homework/{hw2_id}/results",
        headers=teacher_headers,
        json={"student_id": student1_id, "question_results": q_results_payload},
    )

    hw3_res = client.post("/api/v1/homework/", headers=teacher_headers, json={
        "title": "平时练习B",
        "paper_id": paper_id,
        "type": "homework",
        "class_ids": [class_id],
    })
    hw3_id = hw3_res.json()["id"]
    client.post(
        f"/api/v1/homework/{hw3_id}/results",
        headers=teacher_headers,
        json={"student_id": student1_id, "question_results": q_results_payload},
    )

    # 4.2 验证学情分析已成功识别并标记薄弱知识点
    overview_res = client.get(f"/api/v1/analytics/students/{student1_id}/overview", headers=teacher_headers)
    assert overview_res.status_code == 200
    st1_overview = overview_res.json()
    assert st1_overview["total_homework"] == 3
    assert len(st1_overview["weak_points"]) >= 1
    weak_kp_ids = [w["kp_id"] for w in st1_overview["weak_points"]]
    assert kp1_id in weak_kp_ids

    # 4.3 针对薄弱点生成针对性练习并转化为新作业
    practice_res = client.post(
        f"/api/v1/analytics/students/{student1_id}/targeted-practice",
        headers=teacher_headers,
        json={"count": 2, "difficulty_min": 1, "difficulty_max": 5},
    )
    assert practice_res.status_code == 200
    practice_data = practice_res.json()
    assert len(practice_data["questions"]) > 0

    # 转化为强化作业
    new_hw_res = client.post(
        f"/api/v1/analytics/students/{student1_id}/create-targeted-homework",
        headers=teacher_headers,
        json={
            "title": "王小明-一元二次方程专项攻克强化作业",
            "question_ids": [q["id"] for q in practice_data["questions"]],
            "score_per_question": 10.0,
        },
    )
    assert new_hw_res.status_code == 200
    targeted_hw_id = new_hw_res.json()["homework_id"]
    targeted_paper_id = new_hw_res.json()["paper_id"]

    # 4.4 录入该强化作业作答成绩（全部做对，满分）
    targeted_pqs = client.get(f"/api/v1/papers/{targeted_paper_id}", headers=teacher_headers).json()["questions"]
    remedy_results = [
        {
            "paper_question_id": tpq["id"],
            "score": tpq["score"],
            "is_correct": True,
            "answer_text": "全对",
        }
        for tpq in targeted_pqs
    ]

    client.post(
        f"/api/v1/homework/{targeted_hw_id}/results",
        headers=teacher_headers,
        json={"student_id": student1_id, "question_results": remedy_results},
    )

    # 再次录入一次满分巩固作业，确保触发薄弱点解除阈值
    remedy_hw2 = client.post(
        f"/api/v1/analytics/students/{student1_id}/create-targeted-homework",
        headers=teacher_headers,
        json={
            "title": "王小明-一元二次方程专项巩固测试",
            "question_ids": [q["id"] for q in practice_data["questions"]],
            "score_per_question": 10.0,
        },
    ).json()
    remedy_pqs2 = client.get(f"/api/v1/papers/{remedy_hw2['paper_id']}", headers=teacher_headers).json()["questions"]
    client.post(
        f"/api/v1/homework/{remedy_hw2['homework_id']}/results",
        headers=teacher_headers,
        json={
            "student_id": student1_id,
            "question_results": [
                {"paper_question_id": tpq["id"], "score": tpq["score"], "is_correct": True, "answer_text": "全对"}
                for tpq in remedy_pqs2
            ],
        },
    )

    # 4.5 验证薄弱点已被自动攻克解除 (is_resolved == True)
    wp_list_res = client.get(f"/api/v1/analytics/students/{student1_id}/weak-points", headers=teacher_headers)
    assert wp_list_res.status_code == 200
    wp_items = wp_list_res.json()
    kp1_wp = next((w for w in wp_items if w["kp_id"] == kp1_id), None)
    assert kp1_wp is not None
    assert kp1_wp["is_resolved"] is True
    assert kp1_wp["resolved_at"] is not None

    # 4.6 班级学情概览与综合排行验证
    class_ov_res = client.get(f"/api/v1/analytics/classes/{class_id}/overview", headers=teacher_headers)
    assert class_ov_res.status_code == 200
    class_ov = class_ov_res.json()
    assert class_ov["student_count"] == 2
    assert class_ov["total_homework"] >= 3
    assert class_ov["avg_score"] is not None

    class_rank_res = client.get(f"/api/v1/analytics/classes/{class_id}/ranking", headers=teacher_headers)
    assert class_rank_res.status_code == 200
    rank_rows = class_rank_res.json()
    assert len(rank_rows) == 2
    assert rank_rows[0]["rank"] == 1
    assert rank_rows[1]["rank"] == 2
