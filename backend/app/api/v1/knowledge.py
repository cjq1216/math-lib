"""知识点树形管理路由。"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.models.knowledge_point import KnowledgePoint
from app.models.user import User
from app.schemas.common import CountResponse, IdResponse, OkResponse
from app.schemas.knowledge import (
    KnowledgeImportRequest,
    KnowledgePointCreate,
    KnowledgePointRead,
    KnowledgePointUpdate,
)
from app.services.audit_service import add_audit_event

router = APIRouter()


def _ensure_parent(session: Session, parent_id: int | None, current_id: int | None = None) -> None:
    if parent_id is None:
        return
    if parent_id == current_id:
        raise HTTPException(status_code=422, detail="知识点不能以自身为父节点")
    if session.get(KnowledgePoint, parent_id) is None:
        raise HTTPException(status_code=422, detail="父知识点不存在")


def _to_dict(knowledge_point: KnowledgePoint) -> dict:
    return {
        "id": knowledge_point.id,
        "code": knowledge_point.code,
        "name": knowledge_point.name,
        "parent_id": knowledge_point.parent_id,
        "grade": knowledge_point.grade,
        "semester": knowledge_point.semester,
        "chapter": knowledge_point.chapter,
        "section": knowledge_point.section,
        "difficulty_hint": knowledge_point.difficulty_hint,
        "subject": knowledge_point.subject,
        "description": knowledge_point.description,
    }


@router.get("/tree", response_model=list[KnowledgePointRead])
def get_tree(
    session: Annotated[Session, Depends(get_session)],
    grade: int | None = None,
    subject: str = "math",
) -> list[dict]:
    """获取嵌套知识点树。"""
    statement = select(KnowledgePoint).where(
        KnowledgePoint.is_active.is_(True),
        KnowledgePoint.subject == subject,
    )
    if grade:
        statement = statement.where(KnowledgePoint.grade == grade)
    nodes = session.exec(
        statement.order_by(KnowledgePoint.display_order, KnowledgePoint.id)
    ).all()
    node_map = {item.id: {**_to_dict(item), "children": []} for item in nodes}
    roots: list[dict] = []
    for item in nodes:
        if item.parent_id and item.parent_id in node_map:
            node_map[item.parent_id]["children"].append(node_map[item.id])
        else:
            roots.append(node_map[item.id])
    return roots


@router.get("/", response_model=list[KnowledgePointRead])
def list_knowledge_points(
    session: Annotated[Session, Depends(get_session)],
    parent_id: int | None = None,
    grade: int | None = None,
    subject: str = "math",
) -> list[dict]:
    """平铺列出知识点。"""
    statement = select(KnowledgePoint).where(
        KnowledgePoint.is_active.is_(True),
        KnowledgePoint.subject == subject,
    )
    if parent_id is not None:
        statement = statement.where(KnowledgePoint.parent_id == parent_id)
    if grade:
        statement = statement.where(KnowledgePoint.grade == grade)
    return [
        _to_dict(item)
        for item in session.exec(statement.order_by(KnowledgePoint.display_order)).all()
    ]


@router.post("/", response_model=IdResponse, status_code=status.HTTP_201_CREATED)
def create_knowledge_point(
    payload: KnowledgePointCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IdResponse:
    """创建知识点。"""
    _ensure_parent(session, payload.parent_id)
    if session.exec(
        select(KnowledgePoint.id).where(KnowledgePoint.code == payload.code)
    ).first() is not None:
        raise HTTPException(status_code=400, detail="知识点编号已存在")
    knowledge_point = KnowledgePoint(**payload.model_dump())
    session.add(knowledge_point)
    session.flush()
    add_audit_event(
        session,
        action="create",
        resource_type="knowledge_point",
        actor=current_user,
        resource_id=knowledge_point.id,
        changes={"code": knowledge_point.code, "name": knowledge_point.name},
        request=request,
    )
    session.commit()
    return IdResponse(id=knowledge_point.id)


@router.patch("/{kp_id}", response_model=IdResponse)
def update_knowledge_point(
    kp_id: int,
    payload: KnowledgePointUpdate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IdResponse:
    """按白名单更新知识点。"""
    knowledge_point = session.get(KnowledgePoint, kp_id)
    if knowledge_point is None:
        raise HTTPException(status_code=404, detail="知识点不存在")
    updates = payload.model_dump(exclude_unset=True)
    if "parent_id" in updates:
        _ensure_parent(session, updates["parent_id"], kp_id)
    if "code" in updates:
        duplicate = session.exec(
            select(KnowledgePoint.id).where(
                KnowledgePoint.code == updates["code"],
                KnowledgePoint.id != kp_id,
            )
        ).first()
        if duplicate is not None:
            raise HTTPException(status_code=400, detail="知识点编号已存在")
    for field, value in updates.items():
        setattr(knowledge_point, field, value)
    knowledge_point.updated_at = datetime.utcnow()
    session.add(knowledge_point)
    add_audit_event(
        session,
        action="update",
        resource_type="knowledge_point",
        actor=current_user,
        resource_id=kp_id,
        changes={"fields": sorted(updates)},
        request=request,
    )
    session.commit()
    return IdResponse(id=kp_id)


@router.delete("/{kp_id}", response_model=OkResponse)
def delete_knowledge_point(
    kp_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OkResponse:
    """软删知识点。"""
    knowledge_point = session.get(KnowledgePoint, kp_id)
    if knowledge_point is None:
        raise HTTPException(status_code=404, detail="知识点不存在")
    knowledge_point.is_active = False
    knowledge_point.updated_at = datetime.utcnow()
    session.add(knowledge_point)
    add_audit_event(
        session,
        action="delete",
        resource_type="knowledge_point",
        actor=current_user,
        resource_id=kp_id,
        request=request,
    )
    session.commit()
    return OkResponse()


@router.post("/import", response_model=CountResponse)
def import_knowledge_points(
    payload: KnowledgeImportRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CountResponse:
    """批量导入知识点。"""
    for item in payload.items:
        _ensure_parent(session, item.parent_id)
        session.add(KnowledgePoint(**item.model_dump()))
    add_audit_event(
        session,
        action="import",
        resource_type="knowledge_point",
        actor=current_user,
        changes={"count": len(payload.items)},
        request=request,
    )
    session.commit()
    return CountResponse(count=len(payload.items))
