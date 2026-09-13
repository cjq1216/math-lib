"""
知识点路由 - 树形管理
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.knowledge_point import KnowledgePoint

router = APIRouter()


@router.get("/tree")
def get_tree(
    session: Annotated[Session, Depends(get_session)],
    grade: int | None = None,
    subject: str = "math",
):
    """获取知识点树（嵌套结构）"""
    stmt = select(KnowledgePoint).where(
        KnowledgePoint.is_active == True,
        KnowledgePoint.subject == subject,
    )
    if grade:
        stmt = stmt.where(KnowledgePoint.grade == grade)
    stmt = stmt.order_by(KnowledgePoint.display_order, KnowledgePoint.id)

    nodes = session.exec(stmt).all()

    # 转嵌套结构
    node_map = {n.id: {**_kp_to_dict(n), "children": []} for n in nodes}
    roots = []
    for n in nodes:
        if n.parent_id and n.parent_id in node_map:
            node_map[n.parent_id]["children"].append(node_map[n.id])
        else:
            roots.append(node_map[n.id])

    return roots


@router.get("/")
def list_kps(
    session: Annotated[Session, Depends(get_session)],
    parent_id: int | None = None,
    grade: int | None = None,
    subject: str = "math",
):
    """平铺列出知识点"""
    stmt = select(KnowledgePoint).where(
        KnowledgePoint.is_active == True,
        KnowledgePoint.subject == subject,
    )
    if parent_id is not None:
        stmt = stmt.where(KnowledgePoint.parent_id == parent_id)
    if grade:
        stmt = stmt.where(KnowledgePoint.grade == grade)
    stmt = stmt.order_by(KnowledgePoint.display_order)

    return [_kp_to_dict(kp) for kp in session.exec(stmt).all()]


@router.post("/")
def create_kp(
    payload: dict,
    session: Annotated[Session, Depends(get_session)],
):
    """创建知识点"""
    kp = KnowledgePoint(
        code=payload["code"],
        name=payload["name"],
        parent_id=payload.get("parent_id"),
        grade=payload.get("grade"),
        semester=payload.get("semester"),
        chapter=payload.get("chapter"),
        section=payload.get("section"),
        difficulty_hint=payload.get("difficulty_hint"),
        description=payload.get("description"),
        display_order=payload.get("display_order", 0),
    )
    session.add(kp)
    session.commit()
    session.refresh(kp)
    return {"id": kp.id}


@router.patch("/{kp_id}")
def update_kp(
    kp_id: int,
    payload: dict,
    session: Annotated[Session, Depends(get_session)],
):
    """更新知识点"""
    kp = session.get(KnowledgePoint, kp_id)
    if not kp:
        raise HTTPException(status_code=404, detail="知识点不存在")
    for k, v in payload.items():
        setattr(kp, k, v)
    session.add(kp)
    session.commit()
    return {"id": kp.id}


@router.delete("/{kp_id}")
def delete_kp(
    kp_id: int,
    session: Annotated[Session, Depends(get_session)],
):
    """软删知识点"""
    kp = session.get(KnowledgePoint, kp_id)
    if not kp:
        raise HTTPException(status_code=404, detail="知识点不存在")
    kp.is_active = False
    session.add(kp)
    session.commit()
    return {"ok": True}


@router.post("/import")
def import_kps(
    payload: dict,
    session: Annotated[Session, Depends(get_session)],
):
    """批量导入知识点（JSON 列表）"""
    items = payload.get("items", [])
    created = 0
    for item in items:
        kp = KnowledgePoint(**item)
        session.add(kp)
        created += 1
    session.commit()
    return {"created": created}


def _kp_to_dict(kp: KnowledgePoint) -> dict:
    return {
        "id": kp.id,
        "code": kp.code,
        "name": kp.name,
        "parent_id": kp.parent_id,
        "grade": kp.grade,
        "semester": kp.semester,
        "chapter": kp.chapter,
        "section": kp.section,
        "difficulty_hint": kp.difficulty_hint,
        "description": kp.description,
    }
