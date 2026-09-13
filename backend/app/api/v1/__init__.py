"""API v1 路由聚合与统一准入控制。"""

from fastapi import APIRouter, Depends

from app.api.v1 import (
    analytics,
    auth,
    classes,
    homework,
    knowledge,
    llm,
    media,
    papers,
    questions,
    students,
    users,
)
from app.core.dependencies import require_admin, require_teacher_or_admin

api_router = APIRouter()
protected = [Depends(require_teacher_or_admin)]
admin_only = [Depends(require_admin)]

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(
    users.router,
    prefix="/users",
    tags=["users"],
    dependencies=admin_only,
)
api_router.include_router(
    questions.router,
    prefix="/questions",
    tags=["questions"],
    dependencies=protected,
)
api_router.include_router(
    knowledge.router,
    prefix="/knowledge",
    tags=["knowledge"],
    dependencies=protected,
)
api_router.include_router(
    media.router,
    prefix="/media",
    tags=["media"],
    dependencies=protected,
)
api_router.include_router(
    papers.router,
    prefix="/papers",
    tags=["papers"],
    dependencies=protected,
)
api_router.include_router(
    classes.router,
    prefix="/classes",
    tags=["classes"],
    dependencies=protected,
)
api_router.include_router(
    students.router,
    prefix="/students",
    tags=["students"],
    dependencies=protected,
)
api_router.include_router(
    homework.router,
    prefix="/homework",
    tags=["homework"],
    dependencies=protected,
)
api_router.include_router(
    analytics.router,
    prefix="/analytics",
    tags=["analytics"],
    dependencies=protected,
)
api_router.include_router(
    llm.router,
    prefix="/llm",
    tags=["llm"],
    dependencies=protected,
)
