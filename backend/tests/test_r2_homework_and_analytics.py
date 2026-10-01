"""R2 成绩明细、名单快照、Excel 双版本导入与学情闭环回归测试。"""

import io

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlmodel import Session, select

from app.models.homework import (
    HomeworkQuestionResult,
    HomeworkStudent,
)
from app.models.paper import Paper, PaperQuestion, PaperStatus
from app.models.question import Question, QuestionKnowledge, QuestionType
from app.models.student import Student


def _init_admin_and_teacher(client: TestClient) -> tuple[dict[str, str], dict[str, str]]:
    """初始化管理员和测试教师，返回各自身份 Header。"""
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


def _setup_class_and_students(client: TestClient, admin_headers: dict[str, str], teacher_headers: dict[str, str]) -> tuple[int, list[int]]:
    """创建班级并关联教师，创建 2 名学生并加入班级。"""
    res = client.post(
        "/api/v1/classes/",
        headers=teacher_headers,
        json={"name": "七年级一班", "grade": 7, "semester": "fall"},
    )
    assert res.status_code == 201, res.text
    class_id = res.json()["id"]

    student_ids = []
    for no, name in [("2026001", "小明"), ("2026002", "小红")]:
        s_res = client.post(
            "/api/v1/students/",
            headers=teacher_headers,
            json={"name": name, "student_no": no, "gender": "male", "grade": 7},
        )
        assert s_res.status_code == 201
        sid = s_res.json()["id"]
        student_ids.append(sid)

        # 加入班级
        add_res = client.post(
            f"/api/v1/classes/{class_id}/students/{sid}",
            headers=teacher_headers,
        )
        assert add_res.status_code == 200

    return class_id, student_ids


def _create_kp_and_question(
    client: TestClient,
    headers: dict[str, str],
    name: str,
    code: str,
    stem: str,
    difficulty: int = 2,
) -> tuple[int, int]:
    """创建知识点并创建关联该知识点的题目。"""
    kp_res = client.post(
        "/api/v1/knowledge/",
        headers=headers,
        json={"name": name, "code": code, "grade": 7},
    )
    assert kp_res.status_code == 201, kp_res.text
    kp_id = kp_res.json()["id"]

    q_res = client.post(
        "/api/v1/questions/",
        headers=headers,
        json={
            "stem": stem,
            "question_type": QuestionType.CHOICE_SINGLE,
            "difficulty": difficulty,
        },
    )
    assert q_res.status_code == 201, q_res.text
    q_id = q_res.json()["id"]

    kp_set = client.put(
        f"/api/v1/questions/{q_id}/knowledge",
        headers=headers,
        json={"items": [{"kp_id": kp_id, "is_primary": True, "weight": 1.0}]},
    )
    assert kp_set.status_code == 200, kp_set.text

    return kp_id, q_id


def _create_paper_with_questions(
    test_engine,
    admin_headers: dict[str, str],
    title: str,
    question_ids: list[int],
    scores: list[float],
) -> int:
    """使用试卷快照创建一张试卷并添加题目。"""
    with Session(test_engine) as session:
        paper = Paper(
            title=title,
            total_score=sum(scores),
            duration_minutes=60,
            status=PaperStatus.PUBLISHED,
        )
        session.add(paper)
        session.flush()

        for idx, (qid, score) in enumerate(zip(question_ids, scores, strict=False), start=1):
            q = session.get(Question, qid)
            pq = PaperQuestion(
                paper_id=paper.id,
                question_id=qid,
                display_order=idx,
                section="单选题",
                score=score,
                stem_snapshot=q.stem if q else f"题目 {qid}",
            )
            session.add(pq)
        session.commit()
        return paper.id


def test_homework_roster_snapshot_and_history_isolation(client: TestClient, test_engine) -> None:
    """验证作业下发时生成不可变名单快照，且转班学生仍具备历史作业录入与访问隔离。"""
    admin_headers, teacher_headers = _init_admin_and_teacher(client)
    class_id, student_ids = _setup_class_and_students(client, admin_headers, teacher_headers)
    s1, s2 = student_ids

    kp_id, q_id = _create_kp_and_question(client, teacher_headers, "有理数加法", "KP01", "1+1=?")
    paper_id = _create_paper_with_questions(test_engine, admin_headers, "第一次月考", [q_id], [10.0])

    # 1. 教师下发作业
    hw_res = client.post(
        "/api/v1/homework/",
        headers=teacher_headers,
        json={"title": "第一周作业", "paper_id": paper_id, "class_ids": [class_id]},
    )
    assert hw_res.status_code == 201, hw_res.text
    hw_id = hw_res.json()["id"]

    # 验证数据库中已持久化快照
    with Session(test_engine) as session:
        snapshots = session.exec(select(HomeworkStudent).where(HomeworkStudent.homework_id == hw_id)).all()
        assert len(snapshots) == 2
        roster_sids = {s.student_id for s in snapshots}
        assert roster_sids == {s1, s2}

    # 2. 将学生 s1 移出班级（模拟转班）
    remove_res = client.delete(f"/api/v1/classes/{class_id}/students/{s1}", headers=teacher_headers)
    assert remove_res.status_code == 200

    # 3. 新加入学生 s3 到该班级
    s3_res = client.post(
        "/api/v1/students/",
        headers=teacher_headers,
        json={"name": "小刚", "student_no": "2026003", "gender": "male", "grade": 7},
    )
    s3 = s3_res.json()["id"]
    client.post(f"/api/v1/classes/{class_id}/students/{s3}", headers=teacher_headers)

    # 4. 验证作业详情中：target_students 依然是当时快照中的 s1 和 s2，不包含后来转入的 s3
    detail_res = client.get(f"/api/v1/homework/{hw_id}", headers=teacher_headers)
    assert detail_res.status_code == 200
    target_sids = [s["student_id"] for s in detail_res.json()["target_students"]]
    assert s1 in target_sids
    assert s2 in target_sids
    assert s3 not in target_sids

    # 5. 验证仍能为已转出的 s1 录入历史作业成绩
    score_res = client.post(
        f"/api/v1/homework/{hw_id}/results",
        headers=teacher_headers,
        json={"student_id": s1, "total_score": 8.0, "max_score": 10.0},
    )
    assert score_res.status_code == 200
    assert score_res.json()["total_score"] == 8.0

    # 6. 验证不能为后转入的 s3 录入下发前的历史作业（不在快照中）
    invalid_s3_res = client.post(
        f"/api/v1/homework/{hw_id}/results",
        headers=teacher_headers,
        json={"student_id": s3, "total_score": 9.0, "max_score": 10.0},
    )
    assert invalid_s3_res.status_code == 403
    assert "不在作业目标名单中" in invalid_s3_res.json()["detail"]


def test_single_question_score_recording_and_auto_aggregation(client: TestClient, test_engine) -> None:
    """验证按题录入、分值合法性校验、服务端自动汇总总分与自动重算学情。"""
    admin_headers, teacher_headers = _init_admin_and_teacher(client)
    class_id, student_ids = _setup_class_and_students(client, admin_headers, teacher_headers)
    s1 = student_ids[0]

    kp1, q1 = _create_kp_and_question(client, teacher_headers, "相反数", "KP02", "3的相反数是？")
    kp2, q2 = _create_kp_and_question(client, teacher_headers, "绝对值", "KP03", "-5的绝对值是？")
    paper_id = _create_paper_with_questions(test_engine, admin_headers, "月考二", [q1, q2], [5.0, 5.0])

    hw_res = client.post(
        "/api/v1/homework/",
        headers=teacher_headers,
        json={"title": "正规小题作业", "paper_id": paper_id, "class_ids": [class_id]},
    )
    hw_id = hw_res.json()["id"]

    # 获取试卷的小题 ID
    hw_detail = client.get(f"/api/v1/homework/{hw_id}", headers=teacher_headers).json()
    pqs = hw_detail["paper_questions"]
    pq1_id = pqs[0]["id"]
    pq2_id = pqs[1]["id"]

    # 1. 提交超出题目满分的成绩，应被 422 拦截
    bad_res = client.post(
        f"/api/v1/homework/{hw_id}/results",
        headers=teacher_headers,
        json={
            "student_id": s1,
            "question_results": [
                {"paper_question_id": pq1_id, "score": 6.0},  # 满分仅5分
            ],
        },
    )
    assert bad_res.status_code == 422
    assert "得分必须在 0 到 5.0 之间" in bad_res.json()["detail"]

    # 2. 正常录入小题明细：q1 得 5 分（满分），q2 得 3 分（部分分）
    ok_res = client.post(
        f"/api/v1/homework/{hw_id}/results",
        headers=teacher_headers,
        json={
            "student_id": s1,
            "question_results": [
                {"paper_question_id": pq1_id, "score": 5.0, "is_correct": True},
                {"paper_question_id": pq2_id, "score": 3.0, "is_correct": False},
            ],
        },
    )
    assert ok_res.status_code == 200
    data = ok_res.json()
    assert data["total_score"] == 8.0
    assert data["max_score"] == 10.0
    assert data["percentage"] == 80.0
    assert len(data["question_results"]) == 2

    # 3. 验证 HomeworkQuestionResult 数据库明细表落库
    with Session(test_engine) as session:
        q_results = session.exec(
            select(HomeworkQuestionResult).where(HomeworkQuestionResult.paper_question_id == pq1_id)
        ).all()
        assert len(q_results) == 1
        assert q_results[0].score == 5.0
        assert q_results[0].is_correct is True

    # 4. 验证学生的学情统计已自动更新（无需手动点重算）
    with Session(test_engine) as session:
        st = session.get(Student, s1)
        assert st.total_homework_count == 1
        assert st.average_score == 8.0


def test_excel_import_points_and_tick_cross_versions(client: TestClient, test_engine) -> None:
    """验证 Excel 得分版（数值）与对错版（√ / ×）批量导入、幂等更新与行列级错误报告。"""
    admin_headers, teacher_headers = _init_admin_and_teacher(client)
    class_id, student_ids = _setup_class_and_students(client, admin_headers, teacher_headers)
    s1, s2 = student_ids

    _, q1 = _create_kp_and_question(client, teacher_headers, "乘方", "KP04", "2^3=?")
    _, q2 = _create_kp_and_question(client, teacher_headers, "科学记数法", "KP05", "1000用科学记数法表示")
    paper_id = _create_paper_with_questions(test_engine, admin_headers, "综合测验", [q1, q2], [5.0, 5.0])

    hw_res = client.post(
        "/api/v1/homework/",
        headers=teacher_headers,
        json={"title": "导入测试作业", "paper_id": paper_id, "class_ids": [class_id]},
    )
    hw_id = hw_res.json()["id"]

    # 1. 构造 Excel 文件（同时包含数值版与对错符号版，以及一行错误数据）
    wb = Workbook()
    ws = wb.active
    ws.append(["学号", "姓名", "班级", "第1题(5分)", "第2题(5分)", "总分", "用时"])
    ws.append(["2026001", "小明", "七年级一班", 5, 4, 9, 45])             # 小明：数值 5分 + 4分
    ws.append(["2026002", "小红", "七年级一班", "√", "×", 5, 40])          # 小红：对错版 √ (5分) + × (0分)
    ws.append(["9999999", "不存在", "七年级一班", 5, 5, 10, 30])           # 错误行：学号不存在
    ws.append(["2026001", "名字不对", "七年级一班", 5, 5, 10, 30])         # 错误行：姓名不匹配

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    # 2. 执行导入
    files = {"file": ("scores.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    res = client.post(f"/api/v1/homework/{hw_id}/import-results", headers=teacher_headers, files=files)
    assert res.status_code == 200, res.text
    summary = res.json()

    assert summary["created"] == 2
    assert summary["updated"] == 0
    assert len(summary["errors"]) == 2
    err_codes = [e["code"] for e in summary["errors"]]
    assert "student_not_found" in err_codes
    assert "student_name_mismatch" in err_codes

    # 3. 验证导入结果数据
    detail = client.get(f"/api/v1/homework/{hw_id}", headers=teacher_headers).json()
    r1 = next(r for r in detail["results"] if r["student_id"] == s1)
    r2 = next(r for r in detail["results"] if r["student_id"] == s2)
    assert r1["total_score"] == 9.0
    assert r2["total_score"] == 5.0
    assert r2["percentage"] == 50.0

    # 4. 幂等更新测试：再次导入相同文件，只做更新不重复插入
    buf.seek(0)
    res_repeat = client.post(f"/api/v1/homework/{hw_id}/import-results", headers=teacher_headers, files=files)
    assert res_repeat.status_code == 200
    repeat_summary = res_repeat.json()
    assert repeat_summary["created"] == 0
    assert repeat_summary["updated"] == 2


def test_student_learning_analytics_trend_weak_point_lifecycle(client: TestClient, test_engine) -> None:
    """
    验收核心场景：构造 1 名学生、3 个知识点、5 次作业：
    - 前 3 次作业在 KP1 上连续做错 -> 触发薄弱知识点标记（WeakPoint severity=high, accuracy=0.0）；
    - 后续第 4、第 5 次在 KP1 上做对 -> 知识点正确率上升，趋势显示 up，薄弱知识点自动解除（is_resolved=True）。
    """
    admin_headers, teacher_headers = _init_admin_and_teacher(client)
    class_id, student_ids = _setup_class_and_students(client, admin_headers, teacher_headers)
    s1 = student_ids[0]

    # 创建 3 个知识点与题目
    kp1, q1 = _create_kp_and_question(client, teacher_headers, "一次方程", "KP10", "2x=4, x=?")
    kp2, q2 = _create_kp_and_question(client, teacher_headers, "去括号", "KP11", "-(a-b)=?")
    kp3, q3 = _create_kp_and_question(client, teacher_headers, "去分母", "KP12", "x/2=1, x=?")

    paper_id = _create_paper_with_questions(test_engine, admin_headers, "月考系列卷", [q1, q2, q3], [10.0, 10.0, 10.0])

    with Session(test_engine) as session:
        pqs = session.exec(select(PaperQuestion).where(PaperQuestion.paper_id == paper_id).order_by(PaperQuestion.display_order)).all()
        pq1_id, pq2_id, pq3_id = pqs[0].id, pqs[1].id, pqs[2].id

    # 1. 前 3 次作业：KP1 每次做错 (0分)，KP2 做对 (10分)，KP3 做对 (10分)
    for hw_idx in range(1, 4):
        hw_res = client.post(
            "/api/v1/homework/",
            headers=teacher_headers,
            json={"title": f"第{hw_idx}次练习", "paper_id": paper_id, "class_ids": [class_id]},
        )
        hw_id = hw_res.json()["id"]

        client.post(
            f"/api/v1/homework/{hw_id}/results",
            headers=teacher_headers,
            json={
                "student_id": s1,
                "question_results": [
                    {"paper_question_id": pq1_id, "score": 0.0, "is_correct": False},
                    {"paper_question_id": pq2_id, "score": 10.0, "is_correct": True},
                    {"paper_question_id": pq3_id, "score": 10.0, "is_correct": True},
                ],
            },
        )

    # 检查薄弱点：KP1 累计 3 次作答全部错误，必须产生未解除的薄弱点
    overview = client.get(f"/api/v1/analytics/students/{s1}/overview", headers=teacher_headers).json()
    weak_points = overview["weak_points"]
    assert len(weak_points) == 1
    wp = weak_points[0]
    assert wp["kp_id"] == kp1
    assert wp["accuracy"] == 0.0
    assert wp["severity"] == "high"

    # 2. 第 4 次与第 5 次作业：KP1 连续做对 (10分)，KP2、KP3 也做对
    for hw_idx in range(4, 6):
        hw_res = client.post(
            "/api/v1/homework/",
            headers=teacher_headers,
            json={"title": f"第{hw_idx}次练习", "paper_id": paper_id, "class_ids": [class_id]},
        )
        hw_id = hw_res.json()["id"]

        client.post(
            f"/api/v1/homework/{hw_id}/results",
            headers=teacher_headers,
            json={
                "student_id": s1,
                "question_results": [
                    {"paper_question_id": pq1_id, "score": 10.0, "is_correct": True},
                    {"paper_question_id": pq2_id, "score": 10.0, "is_correct": True},
                    {"paper_question_id": pq3_id, "score": 10.0, "is_correct": True},
                ],
            },
        )

    # 3. 验证薄弱点闭环：KP1 正确率回升，活跃薄弱点自动解除
    overview_after = client.get(f"/api/v1/analytics/students/{s1}/overview", headers=teacher_headers).json()
    assert len(overview_after["weak_points"]) == 0  # 活跃薄弱点为 0

    # 检查 weak_points 列表（包含已攻克标记）
    wp_list = client.get(f"/api/v1/analytics/students/{s1}/weak-points", headers=teacher_headers).json()
    assert len(wp_list) == 1
    resolved_wp = wp_list[0]
    assert resolved_wp["kp_id"] == kp1
    assert resolved_wp["is_resolved"] is True
    assert resolved_wp["resolved_at"] is not None
    assert resolved_wp["trend"] == "up"  # 最近表现明显高于历史基线
    assert resolved_wp["recent_5_accuracy"] == 0.4  # 5 次中对 2 次


def test_targeted_practice_deduplication_and_hit_rate(client: TestClient, test_engine) -> None:
    """验证针对性出题：排除已做过的题目，命中薄弱知识点比例 >= 80%。"""
    admin_headers, teacher_headers = _init_admin_and_teacher(client)
    class_id, student_ids = _setup_class_and_students(client, admin_headers, teacher_headers)
    s1 = student_ids[0]

    # 创建薄弱知识点 KP20
    kp_id, q_done = _create_kp_and_question(client, teacher_headers, "几何初步", "KP20", "线段的定义")

    # 在该知识点下再录入 5 道新题目
    new_qids = []
    for i in range(1, 6):
        res = client.post(
            "/api/v1/questions/",
            headers=teacher_headers,
            json={
                "stem": f"几何练习题 #{i}",
                "question_type": QuestionType.CHOICE_SINGLE,
                "difficulty": 2,
            },
        )
        assert res.status_code == 201, res.text
        new_qid = res.json()["id"]
        client.put(
            f"/api/v1/questions/{new_qid}/knowledge",
            headers=teacher_headers,
            json={"items": [{"kp_id": kp_id, "is_primary": True, "weight": 1.0}]},
        )
        new_qids.append(new_qid)

    # 模拟让学生在 q_done 上连续做错 3 次，形成活跃薄弱点
    paper_id = _create_paper_with_questions(test_engine, admin_headers, "几何前测", [q_done], [10.0])
    with Session(test_engine) as session:
        pq_id = session.exec(select(PaperQuestion.id).where(PaperQuestion.paper_id == paper_id)).first()

    for idx in range(3):
        hw_res = client.post(
            "/api/v1/homework/",
            headers=teacher_headers,
            json={"title": f"几何测试{idx+1}", "paper_id": paper_id, "class_ids": [class_id]},
        )
        client.post(
            f"/api/v1/homework/{hw_res.json()['id']}/results",
            headers=teacher_headers,
            json={"student_id": s1, "question_results": [{"paper_question_id": pq_id, "score": 0.0, "is_correct": False}]},
        )

    # 调用针对性出题接口
    practice_res = client.post(
        f"/api/v1/analytics/students/{s1}/targeted-practice",
        headers=teacher_headers,
        json={"count": 5, "difficulty_min": 1, "difficulty_max": 3},
    )
    assert practice_res.status_code == 200, practice_res.text
    practice = practice_res.json()

    assert practice["total"] == 5
    returned_qids = [q["id"] for q in practice["questions"]]

    # 严格验证：已做过的 q_done 绝对不出现（去重）
    assert q_done not in returned_qids

    # 严格验证：命中薄弱知识点的题目比例 >= 80% (5题中至少4题命中)
    with Session(test_engine) as session:
        matching_count = session.exec(
            select(QuestionKnowledge.question_id)
            .where(QuestionKnowledge.question_id.in_(returned_qids))
            .where(QuestionKnowledge.knowledge_point_id == kp_id)
        ).all()
        hit_rate = len(matching_count) / len(returned_qids)
        assert hit_rate >= 0.8


def test_convert_targeted_practice_to_homework(client: TestClient, test_engine) -> None:
    """验证一键将针对性练习转换为专属试卷并直接下发作业。"""
    admin_headers, teacher_headers = _init_admin_and_teacher(client)
    class_id, student_ids = _setup_class_and_students(client, admin_headers, teacher_headers)
    s1 = student_ids[0]

    _, q1 = _create_kp_and_question(client, teacher_headers, "因式分解", "KP30", "x^2-1=?")
    _, q2 = _create_kp_and_question(client, teacher_headers, "十字相乘", "KP31", "x^2+3x+2=?")

    # 一键生成作业
    res = client.post(
        f"/api/v1/analytics/students/{s1}/create-targeted-homework",
        headers=teacher_headers,
        json={
            "title": "小明专属巩固作业",
            "question_ids": [q1, q2],
            "score_per_question": 10.0,
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    new_hw_id = data["homework_id"]
    new_paper_id = data["paper_id"]

    # 验证新生成的作业与试卷
    hw_detail = client.get(f"/api/v1/homework/{new_hw_id}", headers=teacher_headers).json()
    assert hw_detail["paper_id"] == new_paper_id
    assert len(hw_detail["paper_questions"]) == 2
    assert len(hw_detail["target_students"]) == 1
    assert hw_detail["target_students"][0]["student_id"] == s1


def test_class_ranking_and_overview(client: TestClient, test_engine) -> None:
    """验证班级成绩排行与班级学情统计。"""
    admin_headers, teacher_headers = _init_admin_and_teacher(client)
    class_id, student_ids = _setup_class_and_students(client, admin_headers, teacher_headers)
    s1, s2 = student_ids

    _, q = _create_kp_and_question(client, teacher_headers, "整式", "KP40", "单项式的次数")
    paper_id = _create_paper_with_questions(test_engine, admin_headers, "班级统考", [q], [100.0])

    hw_res = client.post(
        "/api/v1/homework/",
        headers=teacher_headers,
        json={"title": "班级测验", "paper_id": paper_id, "class_ids": [class_id]},
    )
    hw_id = hw_res.json()["id"]

    # s1 考 90 分，s2 考 60 分
    client.post(f"/api/v1/homework/{hw_id}/results", headers=teacher_headers, json={"student_id": s1, "total_score": 90.0, "max_score": 100.0})
    client.post(f"/api/v1/homework/{hw_id}/results", headers=teacher_headers, json={"student_id": s2, "total_score": 60.0, "max_score": 100.0})

    # 1. 验证按指定作业排行
    rankings = client.get(f"/api/v1/analytics/classes/{class_id}/ranking?homework_id={hw_id}", headers=teacher_headers).json()
    assert len(rankings) == 2
    assert rankings[0]["student_id"] == s1
    assert rankings[0]["rank"] == 1
    assert rankings[0]["total_score"] == 90.0
    assert rankings[1]["student_id"] == s2
    assert rankings[1]["rank"] == 2
    assert rankings[1]["total_score"] == 60.0

    # 2. 验证班级综合排行（一人一行）
    overall_rankings = client.get(f"/api/v1/analytics/classes/{class_id}/ranking", headers=teacher_headers).json()
    assert len(overall_rankings) == 2
    assert overall_rankings[0]["student_id"] == s1
    assert overall_rankings[1]["student_id"] == s2

    # 3. 验证班级整体概览
    overview = client.get(f"/api/v1/analytics/classes/{class_id}/overview", headers=teacher_headers).json()
    assert overview["student_count"] == 2
    assert overview["total_homework"] == 2
    assert overview["avg_score"] == 75.0
    assert overview["max_score"] == 90.0
    assert overview["min_score"] == 60.0
