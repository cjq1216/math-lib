"""作业下发、名单快照、成绩录入（支持每题明细与对错版）、Excel 导入与自动学情重算。"""

import io
import re
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.dependencies import (
    can_access_class,
    can_access_homework,
    can_access_student,
    get_current_user,
    require_homework_access,
)
from app.models.class_ import Class, ClassStudent
from app.models.homework import (
    Homework,
    HomeworkClass,
    HomeworkQuestionResult,
    HomeworkResult,
    HomeworkStatus,
    HomeworkStudent,
)
from app.models.paper import Paper, PaperQuestion
from app.models.student import Student
from app.models.user import User, UserRole
from app.schemas.common import ImportErrorItem, ImportSummary
from app.schemas.homework import (
    HomeworkCreate,
    HomeworkRead,
    HomeworkResultCreate,
    HomeworkResultRead,
    HomeworkSummary,
)
from app.services.analytics_service import recompute_student_stats
from app.services.audit_service import add_audit_event

router = APIRouter()


def _ensure_target_access(
    session: Session,
    current_user: User,
    class_ids: list[int],
    student_ids: list[int],
) -> None:
    forbidden_classes = [
        class_id
        for class_id in class_ids
        if not can_access_class(session, current_user, class_id)
    ]
    forbidden_students = [
        student_id
        for student_id in student_ids
        if not can_access_student(session, current_user, student_id)
    ]
    if forbidden_classes or forbidden_students:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "作业目标包含无权访问的对象",
                "class_ids": forbidden_classes,
                "student_ids": forbidden_students,
            },
        )


def _student_is_targeted(session: Session, homework: Homework, student_id: int) -> bool:
    """判断学生是否在作业目标名单中（优先使用名单快照）。"""
    snapshot_exists = session.exec(
        select(HomeworkStudent.id).where(
            HomeworkStudent.homework_id == homework.id,
            HomeworkStudent.student_id == student_id,
        )
    ).first() is not None
    if snapshot_exists:
        return True

    has_any_snapshot = session.exec(
        select(HomeworkStudent.id).where(HomeworkStudent.homework_id == homework.id)
    ).first() is not None
    if has_any_snapshot:
        return False

    # 回退兼容尚未生成快照的历史记录
    if student_id in (homework.student_ids or []):
        return True
    if not homework.class_ids:
        return False
    return session.exec(
        select(ClassStudent.id).where(
            ClassStudent.class_id.in_(homework.class_ids),
            ClassStudent.student_id == student_id,
            ClassStudent.left_at.is_(None),
        )
    ).first() is not None


def _homework_summary(homework: Homework) -> dict:
    return {
        "id": homework.id,
        "title": homework.title,
        "type": homework.type,
        "status": homework.status,
        "paper_id": homework.paper_id,
        "due_at": homework.due_at,
        "created_at": homework.created_at,
    }


def _result_to_dict(result: HomeworkResult, q_results: list[HomeworkQuestionResult] | None = None) -> dict:
    detail_items = []
    if q_results:
        detail_items = [
            {
                "id": qr.id,
                "paper_question_id": qr.paper_question_id,
                "question_id": qr.question_id,
                "score": qr.score,
                "max_score": qr.max_score,
                "is_correct": qr.is_correct,
                "answer_text": qr.answer_text,
                "time_spent_seconds": qr.time_spent_seconds,
            }
            for qr in q_results
        ]
    return {
        "id": result.id,
        "student_id": result.student_id,
        "total_score": result.total_score,
        "max_score": result.max_score,
        "percentage": result.percentage,
        "time_spent_minutes": result.time_spent_minutes,
        "question_results": detail_items,
    }


@router.post("/", response_model=HomeworkSummary, status_code=status.HTTP_201_CREATED)
def create_homework(
    payload: HomeworkCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """向有权访问的班级/学生下发作业并建立不可变名单快照。"""
    paper = session.get(Paper, payload.paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")
    class_ids = list(dict.fromkeys(payload.class_ids))
    student_ids = list(dict.fromkeys(payload.student_ids))
    if not class_ids and not student_ids:
        raise HTTPException(status_code=422, detail="至少选择一个班级或学生")
    _ensure_target_access(session, current_user, class_ids, student_ids)

    homework = Homework(
        title=payload.title,
        type=payload.type,
        status=HomeworkStatus.ASSIGNED,
        paper_id=payload.paper_id,
        class_ids=class_ids,
        student_ids=student_ids,
        assigned_at=datetime.utcnow(),
        due_at=payload.due_at,
        time_limit_minutes=payload.time_limit_minutes,
        allow_retake=payload.allow_retake,
        notes=payload.notes,
        created_by=current_user.id,
    )
    session.add(homework)
    session.flush()

    # 1. 保存关联班级快照
    for cid in class_ids:
        session.add(HomeworkClass(homework_id=homework.id, class_id=cid))

    # 2. 收集并保存目标学生快照（记录学生下发时所在的班级）
    target_roster: dict[int, int | None] = {}
    if class_ids:
        class_students = session.exec(
            select(ClassStudent.class_id, ClassStudent.student_id).where(
                ClassStudent.class_id.in_(class_ids),
                ClassStudent.left_at.is_(None),
            )
        ).all()
        for cid, sid in class_students:
            if sid not in target_roster:
                target_roster[sid] = cid
    for sid in student_ids:
        if sid not in target_roster:
            target_roster[sid] = None

    for sid, cid in target_roster.items():
        session.add(
            HomeworkStudent(
                homework_id=homework.id,
                student_id=sid,
                class_id=cid,
            )
        )
    session.flush()

    add_audit_event(
        session,
        action="create",
        resource_type="homework",
        actor=current_user,
        resource_id=homework.id,
        changes={
            "class_ids": class_ids,
            "student_ids": student_ids,
            "total_students_targeted": len(target_roster),
        },
        request=request,
    )
    session.commit()
    return _homework_summary(homework)


@router.get("/", response_model=list[HomeworkSummary])
def list_homework(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict]:
    """按当前用户对象权限列出作业。"""
    statement = select(Homework).order_by(Homework.created_at.desc())
    if current_user.role == UserRole.ADMIN:
        items = session.exec(statement.offset(skip).limit(limit)).all()
    else:
        accessible = [
            homework
            for homework in session.exec(statement).all()
            if can_access_homework(session, current_user, homework)
        ]
        items = accessible[skip : skip + limit]
    return [_homework_summary(item) for item in items]


@router.get("/{homework_id}", response_model=HomeworkRead)
def get_homework(
    homework: Annotated[Homework, Depends(require_homework_access)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    """读取有权访问的作业、名单快照、试卷题目与已录入成绩。"""
    # 1. 目标学生快照
    hw_students = session.exec(
        select(HomeworkStudent).where(HomeworkStudent.homework_id == homework.id)
    ).all()
    target_students: list[dict] = []
    if hw_students:
        sids = [hs.student_id for hs in hw_students]
        cids = [hs.class_id for hs in hw_students if hs.class_id is not None]
        students_map = {
            s.id: s
            for s in session.exec(select(Student).where(Student.id.in_(sids))).all()
        }
        classes_map = (
            {
                c.id: c
                for c in session.exec(select(Class).where(Class.id.in_(cids))).all()
            }
            if cids
            else {}
        )
        for hs in hw_students:
            st = students_map.get(hs.student_id)
            if st:
                cls = classes_map.get(hs.class_id) if hs.class_id else None
                target_students.append(
                    {
                        "student_id": st.id,
                        "student_no": st.student_no,
                        "name": st.name,
                        "class_id": hs.class_id,
                        "class_name": cls.name if cls else None,
                    }
                )
    else:
        # 回退兼容
        cids = homework.class_ids or []
        sids = homework.student_ids or []
        roster_map: dict[int, int | None] = {}
        if cids:
            active_students = session.exec(
                select(ClassStudent.class_id, ClassStudent.student_id).where(
                    ClassStudent.class_id.in_(cids),
                    ClassStudent.left_at.is_(None),
                )
            ).all()
            for cid, sid in active_students:
                if sid not in roster_map:
                    roster_map[sid] = cid
        for sid in sids:
            if sid not in roster_map:
                roster_map[sid] = None
        if roster_map:
            st_list = session.exec(select(Student).where(Student.id.in_(list(roster_map.keys())))).all()
            cls_list = session.exec(select(Class).where(Class.id.in_(cids))).all() if cids else []
            cls_dict = {c.id: c for c in cls_list}
            for st in st_list:
                cid = roster_map.get(st.id)
                cls = cls_dict.get(cid) if cid else None
                target_students.append(
                    {
                        "student_id": st.id,
                        "student_no": st.student_no,
                        "name": st.name,
                        "class_id": cid,
                        "class_name": cls.name if cls else None,
                    }
                )

    # 2. 试卷题目列表
    paper_questions = session.exec(
        select(PaperQuestion)
        .where(PaperQuestion.paper_id == homework.paper_id)
        .order_by(PaperQuestion.display_order)
    ).all()
    pq_list = [
        {
            "id": pq.id,
            "question_id": pq.question_id,
            "display_order": pq.display_order,
            "score": pq.score,
            "stem_snapshot": pq.stem_snapshot,
            "question_type": None,
        }
        for pq in paper_questions
    ]

    # 3. 成绩汇总与每题明细
    results = session.exec(
        select(HomeworkResult).where(HomeworkResult.homework_id == homework.id)
    ).all()
    res_ids = [r.id for r in results if r.id is not None]
    q_res_by_result_id: dict[int, list[HomeworkQuestionResult]] = {}
    if res_ids:
        all_q_results = session.exec(
            select(HomeworkQuestionResult).where(
                HomeworkQuestionResult.homework_result_id.in_(res_ids)
            )
        ).all()
        for qr in all_q_results:
            q_res_by_result_id.setdefault(qr.homework_result_id, []).append(qr)

    return {
        "id": homework.id,
        "title": homework.title,
        "type": homework.type,
        "status": homework.status,
        "paper_id": homework.paper_id,
        "class_ids": homework.class_ids,
        "student_ids": homework.student_ids,
        "due_at": homework.due_at,
        "results": [
            _result_to_dict(result, q_res_by_result_id.get(result.id, []))
            for result in results
        ],
        "target_students": target_students,
        "paper_questions": pq_list,
    }


@router.post("/{homework_id}/results", response_model=HomeworkResultRead)
def record_result(
    payload: HomeworkResultCreate,
    request: Request,
    homework: Annotated[Homework, Depends(require_homework_access)],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """录入作业成绩（支持按题录入与自动汇总），并自动重算学情。"""
    student = session.get(Student, payload.student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    if not _student_is_targeted(session, homework, student.id):
        raise HTTPException(status_code=403, detail="该学生不在作业目标名单中")

    paper_questions = session.exec(
        select(PaperQuestion).where(PaperQuestion.paper_id == homework.paper_id)
    ).all()
    pq_map = {pq.id: pq for pq in paper_questions}

    saved_q_results: list[HomeworkQuestionResult] = []

    # 1. 查找或创建 HomeworkResult 汇总记录
    result = session.exec(
        select(HomeworkResult).where(
            HomeworkResult.homework_id == homework.id,
            HomeworkResult.student_id == student.id,
        )
    ).first()
    action = "update_result" if result else "create_result"
    if result is None:
        result = HomeworkResult(homework_id=homework.id, student_id=student.id)
        session.add(result)
        session.flush()

    # 2. 如果提供了每题明细 question_results，由服务端严格聚合总分与满分
    if payload.question_results is not None:
        total_score = 0.0
        max_score = 0.0
        detail_json = []

        # 检查是否重复传入同一道试卷题目
        seen_pqs = set()
        for qr in payload.question_results:
            if qr.paper_question_id in seen_pqs:
                raise HTTPException(status_code=422, detail=f"试卷题目 ID {qr.paper_question_id} 重复传入")
            seen_pqs.add(qr.paper_question_id)

            pq = pq_map.get(qr.paper_question_id)
            if pq is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"试卷题目 ID {qr.paper_question_id} 不属于试卷 #{homework.paper_id}",
                )
            if qr.score < 0 or qr.score > pq.score:
                raise HTTPException(
                    status_code=422,
                    detail=f"第 {pq.display_order} 题得分必须在 0 到 {pq.score} 之间",
                )

            is_correct = qr.is_correct if qr.is_correct is not None else (qr.score >= pq.score)
            total_score += qr.score
            max_score += pq.score

            # upsert 到 HomeworkQuestionResult
            existing_qr = session.exec(
                select(HomeworkQuestionResult).where(
                    HomeworkQuestionResult.homework_result_id == result.id,
                    HomeworkQuestionResult.paper_question_id == pq.id,
                )
            ).first()
            if existing_qr is None:
                existing_qr = HomeworkQuestionResult(
                    homework_result_id=result.id,
                    paper_question_id=pq.id,
                    question_id=pq.question_id,
                )
            existing_qr.score = qr.score
            existing_qr.max_score = pq.score
            existing_qr.is_correct = is_correct
            existing_qr.answer_text = qr.answer_text
            existing_qr.time_spent_seconds = qr.time_spent_seconds
            existing_qr.recorded_at = datetime.utcnow()
            session.add(existing_qr)
            saved_q_results.append(existing_qr)

            detail_json.append(
                {
                    "paper_question_id": pq.id,
                    "question_id": pq.question_id,
                    "score": qr.score,
                    "max_score": pq.score,
                    "is_correct": is_correct,
                }
            )

        # 若未填全试卷全部题目，满分仍采用试卷快照总满分
        paper = session.get(Paper, homework.paper_id)
        if paper and paper.total_score:
            max_score = paper.total_score

        result.total_score = total_score
        result.max_score = max_score if max_score > 0 else 100.0
        result.percentage = (total_score / result.max_score * 100) if result.max_score > 0 else 0.0
        result.result_detail = detail_json
    else:
        # 兼容总分录入模式
        total = payload.total_score if payload.total_score is not None else 0.0
        max_s = payload.max_score if payload.max_score is not None else 100.0
        if total > max_s:
            raise HTTPException(status_code=422, detail="总分不能超过满分")
        result.total_score = total
        result.max_score = max_s
        result.percentage = (total / max_s * 100) if max_s > 0 else 0.0
        result.result_detail = payload.result_detail

    result.time_spent_minutes = payload.time_spent_minutes
    result.teacher_comment = payload.teacher_comment
    result.input_source = "manual"
    result.recorded_by = current_user.id
    result.updated_at = datetime.utcnow()
    session.add(result)
    session.flush()

    # 3. 自动触发学情重算，消除教师手工点重算的负担
    recompute_student_stats(session, student.id)

    add_audit_event(
        session,
        action=action,
        resource_type="homework_result",
        actor=current_user,
        resource_id=result.id,
        changes={
            "homework_id": homework.id,
            "student_id": student.id,
            "total_score": result.total_score,
            "has_question_details": len(saved_q_results) > 0,
        },
        request=request,
    )
    session.commit()
    return _result_to_dict(result, saved_q_results)


def _parse_cell_score(cell_value: object, max_score: float) -> tuple[float, bool]:
    """
    解析 Excel 单元格分值：同时支持数字得分版与对错版（√ / ×）。
    返回 (score, is_correct)。
    """
    if cell_value is None:
        raise ValueError("单元格为空")

    if isinstance(cell_value, (int, float)):
        val = float(cell_value)
        if val < 0 or val > max_score:
            raise ValueError(f"得分 {val} 超出范围 0 ~ {max_score}")
        return val, val >= max_score

    s = str(cell_value).strip()
    if not s:
        raise ValueError("单元格为空")

    # 对错标记支持
    tick_symbols = {"√", "对", "t", "true", "1", "正确", "pass", "y", "yes"}
    cross_symbols = {"×", "错", "f", "false", "0", "错误", "fail", "n", "no", "x", "X"}

    s_lower = s.lower()
    if s_lower in tick_symbols:
        return max_score, True
    if s_lower in cross_symbols:
        return 0.0, False

    # 尝试纯数字解析
    try:
        val = float(s)
        if val < 0 or val > max_score:
            raise ValueError(f"得分 {val} 超出范围 0 ~ {max_score}")
        return val, val >= max_score
    except ValueError as err:
        raise ValueError(f"无法识别的分数或对错标记: {s}") from err


@router.post("/{homework_id}/import-results", response_model=ImportSummary)
async def import_results(
    request: Request,
    homework: Annotated[Homework, Depends(require_homework_access)],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File(...)],
) -> ImportSummary:
    """
    Excel 批量导入成绩：
    1. 模板列精确绑定试卷题目（如「第1题」或「第1题(5分)」）；
    2. 同时支持得分数值版与对错版（√/×）；
    3. 幂等 upsert 并保存每题明细；
    4. 导入后自动触发受影响学生的学情重算；
    5. 返回行列级错误摘要。
    """
    content = await file.read()
    try:
        workbook = load_workbook(io.BytesIO(content))
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"无法读取 Excel: {error}") from error
    worksheet = workbook.active
    headers = [cell.value for cell in worksheet[1]]
    if "学号" not in headers or "姓名" not in headers:
        raise HTTPException(status_code=400, detail="Excel 至少需要包含列：学号、姓名")
    columns = {str(header).strip(): index for index, header in enumerate(headers) if header is not None}

    # 加载试卷全部题目
    paper = session.get(Paper, homework.paper_id)
    paper_questions = session.exec(
        select(PaperQuestion)
        .where(PaperQuestion.paper_id == homework.paper_id)
        .order_by(PaperQuestion.display_order)
    ).all()
    paper_max_score = paper.total_score if paper and paper.total_score else 100.0

    # 建立表头列与 PaperQuestion 的对应关系
    # 匹配规则：如表头包含 "第1题", "第 1 题", "第1题(5分)", 匹配 display_order == 1
    col_to_pq: dict[int, PaperQuestion] = {}
    for header, col_idx in columns.items():
        match = re.search(r"第\s*(\d+)\s*题", header)
        if match:
            order = int(match.group(1))
            pq = next((p for p in paper_questions if p.display_order == order), None)
            if pq:
                col_to_pq[col_idx] = pq

    created = 0
    updated = 0
    errors: list[ImportErrorItem] = []
    affected_students: set[int] = set()

    for row_index, row in enumerate(
        worksheet.iter_rows(min_row=2, values_only=True), start=2
    ):
        raw_no = row[columns["学号"]]
        if raw_no is None or not str(raw_no).strip():
            continue

        student_no = str(raw_no).strip()
        student = session.exec(
            select(Student).where(Student.student_no == student_no)
        ).first()
        if student is None:
            errors.append(
                ImportErrorItem(
                    row=row_index,
                    column="学号",
                    code="student_not_found",
                    message=f"学号 {student_no} 不存在",
                )
            )
            continue

        raw_name = row[columns["姓名"]]
        if raw_name is None or str(raw_name).strip() != student.name:
            errors.append(
                ImportErrorItem(
                    row=row_index,
                    column="姓名",
                    code="student_name_mismatch",
                    message=f"姓名与学号不匹配（填报：{raw_name}，系统：{student.name}）",
                )
            )
            continue

        if not _student_is_targeted(session, homework, student.id):
            errors.append(
                ImportErrorItem(
                    row=row_index,
                    column="学号",
                    code="student_forbidden",
                    message="无权为该学生录入此作业成绩或该生不在名单快照中",
                )
            )
            continue

        # 解析小题得分
        has_question_columns = len(col_to_pq) > 0
        parsed_q_scores: list[tuple[PaperQuestion, float, bool]] = []
        row_has_error = False

        if has_question_columns:
            for col_idx, pq in col_to_pq.items():
                cell_val = row[col_idx] if col_idx < len(row) else None
                if cell_val is None or str(cell_val).strip() == "":
                    continue
                try:
                    score, is_correct = _parse_cell_score(cell_val, pq.score)
                    parsed_q_scores.append((pq, score, is_correct))
                except Exception as ex:
                    errors.append(
                        ImportErrorItem(
                            row=row_index,
                            column=headers[col_idx] or f"第{col_idx+1}列",
                            code="invalid_question_score",
                            message=str(ex),
                        )
                    )
                    row_has_error = True
                    break

        if row_has_error:
            continue

        # 计算总分与满分
        if parsed_q_scores:
            total_score = sum(s for _, s, _ in parsed_q_scores)
            max_score = paper_max_score
        elif "总分" in columns and row[columns["总分"]] is not None:
            try:
                total_score = float(row[columns["总分"]])
                max_score = paper_max_score
                if total_score < 0 or total_score > max_score:
                    raise ValueError(f"总分必须在 0 到 {max_score} 之间")
            except Exception as ex:
                errors.append(
                    ImportErrorItem(
                        row=row_index,
                        column="总分",
                        code="invalid_total_score",
                        message=str(ex),
                    )
                )
                continue
        else:
            errors.append(
                ImportErrorItem(
                    row=row_index,
                    column="总分",
                    code="missing_scores",
                    message="未填写任何小题得分或总分",
                )
            )
            continue

        # 幂等查找或创建 HomeworkResult
        result = session.exec(
            select(HomeworkResult).where(
                HomeworkResult.homework_id == homework.id,
                HomeworkResult.student_id == student.id,
            )
        ).first()

        if result is None:
            result = HomeworkResult(homework_id=homework.id, student_id=student.id)
            session.add(result)
            session.flush()
            created += 1
        else:
            updated += 1

        result.total_score = total_score
        result.max_score = max_score
        result.percentage = (total_score / max_score * 100) if max_score > 0 else 0.0
        result.input_source = "excel"
        result.recorded_by = current_user.id
        result.updated_at = datetime.utcnow()

        detail_json = []
        # 保存 HomeworkQuestionResult
        for pq, score, is_correct in parsed_q_scores:
            existing_qr = session.exec(
                select(HomeworkQuestionResult).where(
                    HomeworkQuestionResult.homework_result_id == result.id,
                    HomeworkQuestionResult.paper_question_id == pq.id,
                )
            ).first()
            if existing_qr is None:
                existing_qr = HomeworkQuestionResult(
                    homework_result_id=result.id,
                    paper_question_id=pq.id,
                    question_id=pq.question_id,
                )
            existing_qr.score = score
            existing_qr.max_score = pq.score
            existing_qr.is_correct = is_correct
            existing_qr.recorded_at = datetime.utcnow()
            session.add(existing_qr)
            detail_json.append(
                {
                    "paper_question_id": pq.id,
                    "question_id": pq.question_id,
                    "score": score,
                    "max_score": pq.score,
                    "is_correct": is_correct,
                }
            )

        if detail_json:
            result.result_detail = detail_json
        session.add(result)
        affected_students.add(student.id)

    session.flush()

    # 自动重算所有受影响学生的学情
    for sid in affected_students:
        recompute_student_stats(session, sid)

    add_audit_event(
        session,
        action="import",
        resource_type="homework_result",
        actor=current_user,
        resource_id=homework.id,
        changes={
            "created": created,
            "updated": updated,
            "error_count": len(errors),
            "recomputed_students": len(affected_students),
        },
        request=request,
    )
    session.commit()
    return ImportSummary(created=created, updated=updated, errors=errors)


@router.get("/{homework_id}/template", response_class=StreamingResponse)
def download_result_template(
    homework: Annotated[Homework, Depends(require_homework_access)],
    session: Annotated[Session, Depends(get_session)],
) -> StreamingResponse:
    """下载绑定试卷题目且预填名单快照的成绩录入 Excel 模板。"""
    questions = session.exec(
        select(PaperQuestion)
        .where(PaperQuestion.paper_id == homework.paper_id)
        .order_by(PaperQuestion.display_order)
    ).all()

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "成绩录入"

    # 表头设计：学号、姓名、班级、各小题（标明满分）、总分、用时
    headers = ["学号", "姓名", "班级"]
    headers.extend(f"第{question.display_order}题({question.score}分)" for question in questions)
    headers.extend(["总分", "用时(分钟)"])
    worksheet.append(headers)

    # 预填目标名单快照中的学生
    hw_students = session.exec(
        select(HomeworkStudent).where(HomeworkStudent.homework_id == homework.id)
    ).all()
    if hw_students:
        sids = [hs.student_id for hs in hw_students]
        cids = [hs.class_id for hs in hw_students if hs.class_id is not None]
        st_map = {
            s.id: s
            for s in session.exec(select(Student).where(Student.id.in_(sids))).all()
        }
        cls_map = (
            {
                c.id: c
                for c in session.exec(select(Class).where(Class.id.in_(cids))).all()
            }
            if cids
            else {}
        )
        for hs in hw_students:
            st = st_map.get(hs.student_id)
            if st:
                cls = cls_map.get(hs.class_id) if hs.class_id else None
                row = [
                    st.student_no or "",
                    st.name,
                    cls.name if cls else "",
                ]
                # 小题分留空待填
                row.extend([""] * len(questions))
                row.extend(["", ""])
                worksheet.append(row)
    else:
        # 无名单快照时输出示例行
        sample_row = ["2024001", "示例学生", "七(1)班"]
        sample_row.extend([q.score for q in questions])
        sample_row.extend([100, 60])
        worksheet.append(sample_row)

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=homework_{homework.id}_template.xlsx"
        },
    )
