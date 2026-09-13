"""
作业路由 - 下发/成绩录入/Excel导入
"""

import io
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.homework import Homework, HomeworkResult, HomeworkStatus
from app.models.paper import Paper
from app.models.student import Student

router = APIRouter()


@router.post("/")
def create_homework(
    payload: dict,
    session: Annotated[Session, Depends(get_session)],
):
    """下发作业"""
    paper = session.get(Paper, payload["paper_id"])
    if not paper:
        raise HTTPException(status_code=404, detail="试卷不存在")

    h = Homework(
        title=payload["title"],
        type=payload.get("type", "homework"),
        status=HomeworkStatus.ASSIGNED,
        paper_id=payload["paper_id"],
        class_ids=payload.get("class_ids"),
        student_ids=payload.get("student_ids"),
        due_at=datetime.fromisoformat(payload["due_at"]) if payload.get("due_at") else None,
        time_limit_minutes=payload.get("time_limit_minutes"),
        created_by=payload.get("created_by"),
    )
    session.add(h)
    session.commit()
    session.refresh(h)
    return {"id": h.id}


@router.get("/")
def list_homework(
    session: Annotated[Session, Depends(get_session)],
    skip: int = 0,
    limit: int = 20,
):
    """作业列表"""
    stmt = select(Homework).order_by(Homework.created_at.desc()).offset(skip).limit(limit)
    items = session.exec(stmt).all()
    return [
        {
            "id": h.id,
            "title": h.title,
            "type": h.type,
            "status": h.status,
            "paper_id": h.paper_id,
            "due_at": h.due_at,
            "created_at": h.created_at,
        }
        for h in items
    ]


@router.get("/{homework_id}")
def get_homework(
    homework_id: int,
    session: Annotated[Session, Depends(get_session)],
):
    """作业详情"""
    h = session.get(Homework, homework_id)
    if not h:
        raise HTTPException(status_code=404, detail="作业不存在")

    # 已录入的成绩
    results = session.exec(
        select(HomeworkResult).where(HomeworkResult.homework_id == homework_id)
    ).all()
    return {
        "id": h.id,
        "title": h.title,
        "type": h.type,
        "status": h.status,
        "paper_id": h.paper_id,
        "class_ids": h.class_ids,
        "due_at": h.due_at,
        "results": [
            {
                "id": r.id,
                "student_id": r.student_id,
                "total_score": r.total_score,
                "max_score": r.max_score,
                "percentage": r.percentage,
                "time_spent_minutes": r.time_spent_minutes,
            }
            for r in results
        ],
    }


@router.post("/{homework_id}/results")
def record_result(
    homework_id: int,
    payload: dict,
    session: Annotated[Session, Depends(get_session)],
):
    """录入单个学生成绩"""
    h = session.get(Homework, homework_id)
    if not h:
        raise HTTPException(status_code=404, detail="作业不存在")

    # 检查学生
    student_id = payload["student_id"]
    student = session.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    # 检查是否已录入
    existing = session.exec(
        select(HomeworkResult)
        .where(HomeworkResult.homework_id == homework_id)
        .where(HomeworkResult.student_id == student_id)
    ).first()

    max_score = float(payload.get("max_score", 100))
    total_score = float(payload.get("total_score", 0))

    if existing:
        existing.total_score = total_score
        existing.max_score = max_score
        existing.percentage = (total_score / max_score * 100) if max_score > 0 else None
        existing.time_spent_minutes = payload.get("time_spent_minutes")
        existing.result_detail = payload.get("result_detail")
        existing.teacher_comment = payload.get("teacher_comment")
        existing.input_source = "manual"
        session.add(existing)
    else:
        result = HomeworkResult(
            homework_id=homework_id,
            student_id=student_id,
            total_score=total_score,
            max_score=max_score,
            percentage=(total_score / max_score * 100) if max_score > 0 else None,
            time_spent_minutes=payload.get("time_spent_minutes"),
            result_detail=payload.get("result_detail"),
            teacher_comment=payload.get("teacher_comment"),
            input_source="manual",
            recorded_by=payload.get("recorded_by"),
        )
        session.add(result)

    session.commit()
    return {"ok": True}


@router.post("/{homework_id}/import-results")
async def import_results(
    homework_id: int,
    session: Annotated[Session, Depends(get_session)],
    file: UploadFile = File(...),
):
    """Excel 批量导入成绩（对错版或得分版）"""
    h = session.get(Homework, homework_id)
    if not h:
        raise HTTPException(status_code=404, detail="作业不存在")

    content = await file.read()
    wb = load_workbook(io.BytesIO(content))
    ws = wb.active

    headers = [c.value for c in ws[1]]
    if "学号" not in headers or "姓名" not in headers:
        raise HTTPException(status_code=400, detail="Excel 至少需要包含列：学号、姓名")

    col_idx = {h: i for i, h in enumerate(headers)}
    created, updated, errors = 0, 0, []

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row[col_idx["学号"]]:
            continue
        try:
            student_no = str(row[col_idx["学号"]]).strip()
            student = session.exec(select(Student).where(Student.student_no == student_no)).first()
            if not student:
                errors.append(f"第 {row_idx} 行: 学号 {student_no} 不存在")
                continue

            # 解析总分（"总分"列 or 计算）
            if "总分" in col_idx and row[col_idx["总分"]] is not None:
                total_score = float(row[col_idx["总分"]])
            else:
                # 自动计算：所有数字列求和
                total_score = sum(
                    float(row[i])
                    for i in range(col_idx.get("总分", 999), len(row))
                    if isinstance(row[i], (int, float))
                )

            # 解析各题得分（result_detail）
            detail = []
            for i, h_name in enumerate(headers):
                if h_name and h_name.startswith("第") and isinstance(row[i], (int, float)):
                    detail.append(
                        {
                            "question_index": i,
                            "score": float(row[i]),
                            "is_correct": float(row[i]) > 0,
                        }
                    )

            existing = session.exec(
                select(HomeworkResult)
                .where(HomeworkResult.homework_id == homework_id)
                .where(HomeworkResult.student_id == student.id)
            ).first()

            if existing:
                existing.total_score = total_score
                existing.max_score = 100.0
                existing.percentage = total_score
                existing.result_detail = detail
                existing.input_source = "excel"
                session.add(existing)
                updated += 1
            else:
                result = HomeworkResult(
                    homework_id=homework_id,
                    student_id=student.id,
                    total_score=total_score,
                    max_score=100.0,
                    percentage=total_score,
                    result_detail=detail,
                    input_source="excel",
                )
                session.add(result)
                created += 1
        except Exception as e:
            errors.append(f"第 {row_idx} 行: {e}")

    session.commit()
    return {"created": created, "updated": updated, "errors": errors}


@router.get("/{homework_id}/template")
def download_result_template(
    homework_id: int,
    session: Annotated[Session, Depends(get_session)],
):
    """下载作业成绩导入模板（按试卷题目自动生成列）"""
    h = session.get(Homework, homework_id)
    if not h:
        raise HTTPException(status_code=404, detail="作业不存在")

    from app.models.paper import PaperQuestion

    questions = session.exec(
        select(PaperQuestion)
        .where(PaperQuestion.paper_id == h.paper_id)
        .order_by(PaperQuestion.display_order)
    ).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "成绩录入"
    headers = ["学号", "姓名", "班级"]
    for q in questions:
        headers.append(f"第{q.display_order}题")
    headers.append("总分")
    headers.append("用时(分钟)")
    ws.append(headers)
    ws.append(["示例：2024001", "张三", "七(1)班"] + [5] * len(questions) + [100, 90])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=homework_{homework_id}_template.xlsx"
        },
    )
