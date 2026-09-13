"""作业下发、成绩录入和 Excel 导入。"""

import io
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
from app.models.class_ import ClassStudent
from app.models.homework import Homework, HomeworkResult, HomeworkStatus
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


@router.post("/", response_model=HomeworkSummary, status_code=status.HTTP_201_CREATED)
def create_homework(
    payload: HomeworkCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """向有权访问的班级/学生下发作业。"""
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
    add_audit_event(
        session,
        action="create",
        resource_type="homework",
        actor=current_user,
        resource_id=homework.id,
        changes={"class_ids": class_ids, "student_ids": student_ids},
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
    """读取有权访问的作业和已录入成绩。"""
    results = session.exec(
        select(HomeworkResult).where(HomeworkResult.homework_id == homework.id)
    ).all()
    return {
        "id": homework.id,
        "title": homework.title,
        "type": homework.type,
        "status": homework.status,
        "paper_id": homework.paper_id,
        "class_ids": homework.class_ids,
        "student_ids": homework.student_ids,
        "due_at": homework.due_at,
        "results": [_result_to_dict(result) for result in results],
    }


@router.post("/{homework_id}/results", response_model=HomeworkResultRead)
def record_result(
    payload: HomeworkResultCreate,
    request: Request,
    homework: Annotated[Homework, Depends(require_homework_access)],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """录入作业汇总成绩，R2 再正规化每题明细。"""
    student = session.get(Student, payload.student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    if not can_access_student(session, current_user, student.id):
        raise HTTPException(status_code=403, detail="无权访问该学生")
    if not _student_is_targeted(session, homework, student.id):
        raise HTTPException(status_code=403, detail="该学生不在作业目标名单中")
    if payload.total_score > payload.max_score:
        raise HTTPException(status_code=422, detail="总分不能超过满分")

    result = session.exec(
        select(HomeworkResult).where(
            HomeworkResult.homework_id == homework.id,
            HomeworkResult.student_id == student.id,
        )
    ).first()
    action = "update_result" if result else "create_result"
    if result is None:
        result = HomeworkResult(homework_id=homework.id, student_id=student.id)
    result.total_score = payload.total_score
    result.max_score = payload.max_score
    result.percentage = payload.total_score / payload.max_score * 100
    result.time_spent_minutes = payload.time_spent_minutes
    result.result_detail = payload.result_detail
    result.teacher_comment = payload.teacher_comment
    result.input_source = "manual"
    result.recorded_by = current_user.id
    result.updated_at = datetime.utcnow()
    session.add(result)
    session.flush()
    add_audit_event(
        session,
        action=action,
        resource_type="homework_result",
        actor=current_user,
        resource_id=result.id,
        changes={"homework_id": homework.id, "student_id": student.id},
        request=request,
    )
    session.commit()
    return _result_to_dict(result)


@router.post("/{homework_id}/import-results", response_model=ImportSummary)
async def import_results(
    request: Request,
    homework: Annotated[Homework, Depends(require_homework_access)],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    file: UploadFile = File(...),
) -> ImportSummary:
    """Excel 批量导入成绩并返回结构化行错误。"""
    content = await file.read()
    try:
        workbook = load_workbook(io.BytesIO(content))
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"无法读取 Excel: {error}") from error
    worksheet = workbook.active
    headers = [cell.value for cell in worksheet[1]]
    if "学号" not in headers or "姓名" not in headers:
        raise HTTPException(status_code=400, detail="Excel 至少需要包含列：学号、姓名")
    columns = {header: index for index, header in enumerate(headers) if header}
    paper = session.get(Paper, homework.paper_id)
    max_score = paper.total_score if paper else 100.0
    created = 0
    updated = 0
    errors: list[ImportErrorItem] = []

    for row_index, row in enumerate(
        worksheet.iter_rows(min_row=2, values_only=True), start=2
    ):
        if not row[columns["学号"]]:
            continue
        try:
            student_no = str(row[columns["学号"]]).strip()
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
            if str(row[columns["姓名"]]).strip() != student.name:
                errors.append(
                    ImportErrorItem(
                        row=row_index,
                        column="姓名",
                        code="student_name_mismatch",
                        message="姓名与学号不匹配",
                    )
                )
                continue
            if not can_access_student(session, current_user, student.id) or not _student_is_targeted(
                session, homework, student.id
            ):
                errors.append(
                    ImportErrorItem(
                        row=row_index,
                        column="学号",
                        code="student_forbidden",
                        message="无权为该学生录入此作业成绩",
                    )
                )
                continue

            if "总分" in columns and row[columns["总分"]] is not None:
                total_score = float(row[columns["总分"]])
            else:
                total_score = sum(
                    float(row[index])
                    for index, header in enumerate(headers)
                    if header and str(header).startswith("第") and isinstance(row[index], (int, float))
                )
            if total_score < 0 or total_score > max_score:
                raise ValueError(f"总分必须在 0 到 {max_score} 之间")
            detail = [
                {
                    "question_index": index,
                    "score": float(row[index]),
                    "is_correct": float(row[index]) > 0,
                }
                for index, header in enumerate(headers)
                if header and str(header).startswith("第") and isinstance(row[index], (int, float))
            ]
            result = session.exec(
                select(HomeworkResult).where(
                    HomeworkResult.homework_id == homework.id,
                    HomeworkResult.student_id == student.id,
                )
            ).first()
            if result is None:
                result = HomeworkResult(homework_id=homework.id, student_id=student.id)
                created += 1
            else:
                updated += 1
            result.total_score = total_score
            result.max_score = max_score
            result.percentage = total_score / max_score * 100 if max_score > 0 else None
            result.result_detail = detail
            result.input_source = "excel"
            result.recorded_by = current_user.id
            result.updated_at = datetime.utcnow()
            session.add(result)
        except Exception as error:
            errors.append(
                ImportErrorItem(row=row_index, code="invalid_row", message=str(error))
            )

    add_audit_event(
        session,
        action="import",
        resource_type="homework_result",
        actor=current_user,
        resource_id=homework.id,
        changes={"created": created, "updated": updated, "error_count": len(errors)},
        request=request,
    )
    session.commit()
    return ImportSummary(created=created, updated=updated, errors=errors)


@router.get("/{homework_id}/template", response_class=StreamingResponse)
def download_result_template(
    homework: Annotated[Homework, Depends(require_homework_access)],
    session: Annotated[Session, Depends(get_session)],
) -> StreamingResponse:
    """下载按试卷题目生成的成绩导入模板。"""
    questions = session.exec(
        select(PaperQuestion)
        .where(PaperQuestion.paper_id == homework.paper_id)
        .order_by(PaperQuestion.display_order)
    ).all()
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "成绩录入"
    headers = ["学号", "姓名", "班级"]
    headers.extend(f"第{question.display_order}题" for question in questions)
    headers.extend(["总分", "用时(分钟)"])
    worksheet.append(headers)
    worksheet.append(
        ["示例：2024001", "张三", "七(1)班"]
        + [5] * len(questions)
        + [100, 90]
    )
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


def _result_to_dict(result: HomeworkResult) -> dict:
    return {
        "id": result.id,
        "student_id": result.student_id,
        "total_score": result.total_score,
        "max_score": result.max_score,
        "percentage": result.percentage,
        "time_spent_minutes": result.time_spent_minutes,
    }
