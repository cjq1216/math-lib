"""
学生路由 - 录入/查询/批量导入
"""

import io
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.student import Student

router = APIRouter()


@router.post("/")
def create_student(
    payload: dict,
    session: Annotated[Session, Depends(get_session)],
):
    """创建学生"""
    s = Student(
        student_no=payload["student_no"],
        name=payload["name"],
        gender=payload.get("gender"),
        grade=payload["grade"],
        enrollment_year=payload.get("enrollment_year"),
        phone=payload.get("phone"),
        parent_phone=payload.get("parent_phone"),
        notes=payload.get("notes"),
        created_by=payload.get("created_by"),
    )
    session.add(s)
    session.commit()
    session.refresh(s)
    return {"id": s.id}


@router.get("/")
def list_students(
    session: Annotated[Session, Depends(get_session)],
    grade: int | None = None,
    is_active: bool = True,
    skip: int = 0,
    limit: int = 50,
    keyword: str | None = None,
):
    """学生列表"""
    stmt = select(Student).where(Student.is_active == is_active)
    if grade:
        stmt = stmt.where(Student.grade == grade)
    if keyword:
        stmt = stmt.where((Student.name.contains(keyword)) | (Student.student_no.contains(keyword)))
    stmt = stmt.order_by(Student.grade, Student.student_no).offset(skip).limit(limit)
    return [
        {
            "id": s.id,
            "student_no": s.student_no,
            "name": s.name,
            "gender": s.gender,
            "grade": s.grade,
            "phone": s.phone,
            "average_score": s.average_score,
        }
        for s in session.exec(stmt).all()
    ]


@router.post("/import")
async def import_students(
    session: Annotated[Session, Depends(get_session)],
    file: UploadFile = File(...),
):
    """从 Excel 批量导入学生"""
    content = await file.read()
    wb = load_workbook(io.BytesIO(content))
    ws = wb.active

    headers = [c.value for c in ws[1]]
    expected = ["学号", "姓名", "性别", "年级", "联系电话", "家长电话", "备注"]
    if not all(h in headers for h in ["学号", "姓名", "年级"]):
        raise HTTPException(status_code=400, detail=f"Excel 至少需要包含列：{expected}")

    col_idx = {h: i for i, h in enumerate(headers)}
    created, updated, errors = 0, 0, []

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row[col_idx["学号"]]:
            continue
        try:
            student_no = str(row[col_idx["学号"]]).strip()
            grade = int(row[col_idx["年级"]])
            name = str(row[col_idx["姓名"]]).strip()

            existing = session.exec(select(Student).where(Student.student_no == student_no)).first()
            if existing:
                existing.name = name
                existing.grade = grade
                existing.gender = (
                    row[col_idx.get("性别", -1)]
                    if col_idx.get("性别", -1) >= 0 and row[col_idx.get("性别", -1)]
                    else existing.gender
                )
                session.add(existing)
                updated += 1
            else:
                s = Student(
                    student_no=student_no,
                    name=name,
                    gender=row[col_idx.get("性别", -1)] if col_idx.get("性别", -1) >= 0 else None,
                    grade=grade,
                    phone=str(row[col_idx.get("联系电话", -1)])
                    if col_idx.get("联系电话", -1) >= 0 and row[col_idx.get("联系电话", -1)]
                    else None,
                    parent_phone=str(row[col_idx.get("家长电话", -1)])
                    if col_idx.get("家长电话", -1) >= 0 and row[col_idx.get("家长电话", -1)]
                    else None,
                    notes=str(row[col_idx.get("备注", -1)])
                    if col_idx.get("备注", -1) >= 0 and row[col_idx.get("备注", -1)]
                    else None,
                )
                session.add(s)
                created += 1
        except Exception as e:
            errors.append(f"第 {row_idx} 行: {e}")

    session.commit()
    return {"created": created, "updated": updated, "errors": errors}


@router.get("/template")
def download_student_template():
    """下载学生导入模板"""
    wb = Workbook()
    ws = wb.active
    ws.title = "学生信息"
    headers = ["学号", "姓名", "性别", "年级", "联系电话", "家长电话", "备注"]
    ws.append(headers)
    # 示例行
    ws.append(["2024001", "张三", "男", 7, "138xxxx", "139xxxx", ""])
    ws.append(["2024002", "李四", "女", 7, "138xxxx", "", ""])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=students_template.xlsx"},
    )


@router.delete("/{student_id}")
def delete_student(
    student_id: int,
    session: Annotated[Session, Depends(get_session)],
):
    """软删学生"""
    s = session.get(Student, student_id)
    if not s:
        raise HTTPException(status_code=404, detail="学生不存在")
    s.is_active = False
    session.add(s)
    session.commit()
    return {"ok": True}
