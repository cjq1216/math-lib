"""知识点树形管理路由。

功能：
1. 嵌套树与平铺列表查询（支持按年级/学科/停用状态筛选）；
2. 循环引用防御与深度上限校验（防止 A->B->C->A 环路与过深层级）；
3. 年级与层级范围校验；
4. 节点编辑与排序（display_order）；
5. 引用保护式软删除（禁止删除仍被题目使用的节点，或支持迁移目标 target_kp_id）；
6. 软删节点恢复（/restore）；
7. 结构化 JSON 导出（/export）与双向导入（/import，支持 parent_code 自动父子关联）。
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.models.knowledge_point import KnowledgePoint
from app.models.question import Question, QuestionKnowledge
from app.models.user import User
from app.schemas.common import CountResponse, IdResponse, OkResponse
from app.schemas.knowledge import (
    KnowledgeImportRequest,
    KnowledgePointCreate,
    KnowledgePointExportItem,
    KnowledgePointRead,
    KnowledgePointUpdate,
)
from app.services.audit_service import add_audit_event

router = APIRouter()

MAX_TREE_DEPTH = 6


def _check_parent_validity(
    session: Session,
    parent_id: int | None,
    current_id: int | None = None,
    child_grade: int | None = None,
) -> KnowledgePoint | None:
    """校验父节点合法性、循环引用、最大深度与年级一致性。"""
    if parent_id is None:
        return None

    if current_id is not None and parent_id == current_id:
        raise HTTPException(status_code=422, detail="知识点不能以自身为父节点")

    parent = session.get(KnowledgePoint, parent_id)
    if parent is None or not parent.is_active:
        raise HTTPException(status_code=422, detail="父知识点不存在或已停用")

    # 循环引用与深度校验：沿父节点链向上遍历
    visited_ids = {parent.id}
    curr = parent
    depth = 1

    while curr.parent_id is not None:
        if current_id is not None and curr.parent_id == current_id:
            raise HTTPException(
                status_code=422, detail="知识点存在循环引用：不能将自己的子孙节点设为父节点"
            )
        if curr.parent_id in visited_ids:
            raise HTTPException(status_code=422, detail="知识点树中已存在环状引用")

        visited_ids.add(curr.parent_id)
        next_parent = session.get(KnowledgePoint, curr.parent_id)
        if next_parent is None:
            break
        curr = next_parent
        depth += 1
        if depth > MAX_TREE_DEPTH:
            raise HTTPException(
                status_code=422,
                detail=f"知识点树层级过深，最大允许深度为 {MAX_TREE_DEPTH} 层",
            )

    # 年级继承/一致性校验
    if child_grade is not None and parent.grade is not None:
        if child_grade != parent.grade:
            raise HTTPException(
                status_code=422,
                detail=f"子知识点年级（{child_grade}年级）与父知识点年级（{parent.grade}年级）不一致",
            )

    return parent


def _to_read_dict(kp: KnowledgePoint) -> dict:
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
        "subject": kp.subject,
        "description": kp.description,
        "display_order": kp.display_order,
        "is_active": kp.is_active,
    }


@router.get("/tree", response_model=list[KnowledgePointRead])
def get_tree(
    session: Annotated[Session, Depends(get_session)],
    grade: int | None = None,
    subject: str = "math",
    include_inactive: bool = False,
) -> list[dict]:
    """获取嵌套知识点树。"""
    statement = select(KnowledgePoint).where(KnowledgePoint.subject == subject)
    if not include_inactive:
        statement = statement.where(KnowledgePoint.is_active.is_(True))
    if grade:
        statement = statement.where(KnowledgePoint.grade == grade)

    nodes = session.exec(
        statement.order_by(KnowledgePoint.display_order, KnowledgePoint.id)
    ).all()

    node_map = {item.id: {**_to_read_dict(item), "children": []} for item in nodes}
    roots: list[dict] = []
    for item in nodes:
        if item.parent_id and item.parent_id in node_map:
            node_map[item.parent_id]["children"].append(node_map[item.id])
        else:
            roots.append(node_map[item.id])
    return roots


@router.get("/export", response_model=list[KnowledgePointExportItem])
def export_knowledge_points(
    session: Annotated[Session, Depends(get_session)],
    subject: str = "math",
    include_inactive: bool = False,
) -> list[dict]:
    """导出知识点体系为标准 JSON 格式（带 parent_code 便于跨环境导入）。"""
    statement = select(KnowledgePoint).where(KnowledgePoint.subject == subject)
    if not include_inactive:
        statement = statement.where(KnowledgePoint.is_active.is_(True))

    nodes = session.exec(
        statement.order_by(KnowledgePoint.display_order, KnowledgePoint.id)
    ).all()
    id_to_code = {node.id: node.code for node in nodes}

    result = []
    for node in nodes:
        parent_code = id_to_code.get(node.parent_id) if node.parent_id else None
        item = _to_read_dict(node)
        item["parent_code"] = parent_code
        result.append(item)
    return result


@router.get("/", response_model=list[KnowledgePointRead])
def list_knowledge_points(
    session: Annotated[Session, Depends(get_session)],
    parent_id: int | None = None,
    grade: int | None = None,
    subject: str = "math",
    include_inactive: bool = False,
) -> list[dict]:
    """平铺列出知识点。"""
    statement = select(KnowledgePoint).where(KnowledgePoint.subject == subject)
    if not include_inactive:
        statement = statement.where(KnowledgePoint.is_active.is_(True))
    if parent_id is not None:
        statement = statement.where(KnowledgePoint.parent_id == parent_id)
    if grade:
        statement = statement.where(KnowledgePoint.grade == grade)

    nodes = session.exec(
        statement.order_by(KnowledgePoint.display_order, KnowledgePoint.id)
    ).all()
    return [_to_read_dict(item) for item in nodes]


@router.post("/", response_model=IdResponse, status_code=status.HTTP_201_CREATED)
def create_knowledge_point(
    payload: KnowledgePointCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IdResponse:
    """创建知识点，校验编码唯一性、父节点存在性、循环引用与层级。"""
    _check_parent_validity(
        session=session,
        parent_id=payload.parent_id,
        current_id=None,
        child_grade=payload.grade,
    )
    if (
        session.exec(
            select(KnowledgePoint.id).where(KnowledgePoint.code == payload.code)
        ).first()
        is not None
    ):
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
    """按白名单更新知识点，含父节点调整防循环引用。"""
    knowledge_point = session.get(KnowledgePoint, kp_id)
    if knowledge_point is None:
        raise HTTPException(status_code=404, detail="知识点不存在")

    updates = payload.model_dump(exclude_unset=True)

    target_parent_id = updates.get("parent_id", knowledge_point.parent_id)
    target_grade = updates.get("grade", knowledge_point.grade)

    if "parent_id" in updates or "grade" in updates:
        _check_parent_validity(
            session=session,
            parent_id=target_parent_id,
            current_id=kp_id,
            child_grade=target_grade,
        )

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
    target_kp_id: int | None = Query(
        default=None,
        description="若该知识点已被题目使用，可指定目标知识点 ID 将关联关系迁移后再删除",
    ),
) -> OkResponse:
    """软删知识点。具有子知识点或仍被未删除题目使用的知识点将被禁止删除，除非指定迁移目标。"""
    knowledge_point = session.get(KnowledgePoint, kp_id)
    if knowledge_point is None:
        raise HTTPException(status_code=404, detail="知识点不存在")

    # 1. 检查是否存在活跃子节点
    active_child = session.exec(
        select(KnowledgePoint.id).where(
            KnowledgePoint.parent_id == kp_id,
            KnowledgePoint.is_active.is_(True),
        )
    ).first()
    if active_child is not None:
        raise HTTPException(
            status_code=422,
            detail="该知识点下仍有活跃子知识点，禁止删除；请先删除或转移子知识点",
        )

    # 2. 检查是否仍被有效题目引用
    active_q_stmt = (
        select(QuestionKnowledge)
        .join(Question, Question.id == QuestionKnowledge.question_id)
        .where(
            QuestionKnowledge.knowledge_point_id == kp_id,
            Question.is_active.is_(True),
        )
    )
    active_links = session.exec(active_q_stmt).all()

    if active_links:
        if target_kp_id is None:
            raise HTTPException(
                status_code=422,
                detail=f"该知识点仍被 {len(active_links)} 道有效题目使用，禁止删除；请先在题目中解绑或指定 target_kp_id 迁移",
            )

        if target_kp_id == kp_id:
            raise HTTPException(status_code=422, detail="迁移目标知识点不能是其自身")

        target_kp = session.get(KnowledgePoint, target_kp_id)
        if target_kp is None or not target_kp.is_active:
            raise HTTPException(status_code=422, detail="迁移目标知识点不存在或已停用")

        # 迁移关联：若题目已包含 target_kp_id 则删除旧关联避免唯一键冲突；若未包含则更新 kp_id
        for link in active_links:
            exists_target = session.exec(
                select(QuestionKnowledge).where(
                    QuestionKnowledge.question_id == link.question_id,
                    QuestionKnowledge.knowledge_point_id == target_kp_id,
                )
            ).first()
            if exists_target:
                session.delete(link)
            else:
                link.knowledge_point_id = target_kp_id
                session.add(link)
        session.flush()

    # 3. 执行软删
    knowledge_point.is_active = False
    knowledge_point.updated_at = datetime.utcnow()
    session.add(knowledge_point)

    add_audit_event(
        session,
        action="delete",
        resource_type="knowledge_point",
        actor=current_user,
        resource_id=kp_id,
        changes={"migrated_to": target_kp_id, "migrated_links_count": len(active_links)},
        request=request,
    )
    session.commit()
    return OkResponse()


@router.post("/{kp_id}/restore", response_model=OkResponse)
def restore_knowledge_point(
    kp_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OkResponse:
    """恢复已软删的知识点（要求父级知识点必须为活跃状态）。"""
    knowledge_point = session.get(KnowledgePoint, kp_id)
    if knowledge_point is None:
        raise HTTPException(status_code=404, detail="知识点不存在")

    if knowledge_point.is_active:
        return OkResponse()

    # 检查父知识点状态
    if knowledge_point.parent_id is not None:
        parent = session.get(KnowledgePoint, knowledge_point.parent_id)
        if parent is None or not parent.is_active:
            raise HTTPException(
                status_code=422,
                detail="父知识点处于已删除状态，无法恢复该节点；请先恢复父知识点或更改其父级",
            )

    knowledge_point.is_active = True
    knowledge_point.updated_at = datetime.utcnow()
    session.add(knowledge_point)

    add_audit_event(
        session,
        action="restore",
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
    """批量导入知识点体系，支持 parent_code 自动父子关联及循环检测。"""
    imported_count = 0

    # 第一遍：创建或更新节点基础属性（先存入数据库生成/匹配 ID）
    code_to_kp: dict[str, KnowledgePoint] = {}
    pending_parent_codes: dict[str, str] = {}

    for item in payload.items:
        existing = session.exec(
            select(KnowledgePoint).where(KnowledgePoint.code == item.code)
        ).first()

        data = item.model_dump(exclude={"parent_code"})
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
            existing.is_active = True
            existing.updated_at = datetime.utcnow()
            session.add(existing)
            kp_obj = existing
        else:
            kp_obj = KnowledgePoint(**data, is_active=True)
            session.add(kp_obj)

        session.flush()
        code_to_kp[item.code] = kp_obj
        imported_count += 1

        if item.parent_code:
            pending_parent_codes[item.code] = item.parent_code

    # 第二遍：按 parent_code 回填 parent_id 并执行循环引用与深度校验
    for child_code, p_code in pending_parent_codes.items():
        child = code_to_kp.get(child_code)
        if not child:
            continue
        parent = code_to_kp.get(p_code) or session.exec(
            select(KnowledgePoint).where(KnowledgePoint.code == p_code)
        ).first()
        if not parent:
            raise HTTPException(
                status_code=422,
                detail=f"导入失败：未找到 parent_code 为 '{p_code}' 的知识点",
            )
        _check_parent_validity(
            session=session,
            parent_id=parent.id,
            current_id=child.id,
            child_grade=child.grade,
        )
        child.parent_id = parent.id
        session.add(child)

    add_audit_event(
        session,
        action="import",
        resource_type="knowledge_point",
        actor=current_user,
        changes={"imported_count": imported_count},
        request=request,
    )
    session.commit()
    return CountResponse(count=imported_count)
