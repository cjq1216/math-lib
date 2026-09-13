"""api package"""
from fastapi import APIRouter

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

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(questions.router, prefix="/questions", tags=["questions"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(media.router, prefix="/media", tags=["media"])
api_router.include_router(papers.router, prefix="/papers", tags=["papers"])
api_router.include_router(classes.router, prefix="/classes", tags=["classes"])
api_router.include_router(students.router, prefix="/students", tags=["students"])
api_router.include_router(homework.router, prefix="/homework", tags=["homework"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(llm.router, prefix="/llm", tags=["llm"])
