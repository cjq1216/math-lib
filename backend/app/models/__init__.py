"""models package"""

from app.models.analytics import StudentKPStats, WeakPoint
from app.models.audit_log import AuditLog
from app.models.background_task import BackgroundTask, TaskStatus, TaskType
from app.models.class_ import Class, ClassStudent
from app.models.homework import Homework, HomeworkResult
from app.models.knowledge_point import KnowledgePoint
from app.models.media import MediaResource, MediaUsageType, QuestionMedia
from app.models.paper import Paper, PaperQuestion, PaperStatus
from app.models.question import (
    Question,
    QuestionAnswer,
    QuestionKnowledge,
    QuestionType,
    SubQuestion,
)
from app.models.question_embedding import QuestionEmbedding
from app.models.source import Source
from app.models.student import Student
from app.models.user import User, UserRole

__all__ = [
    "User",
    "UserRole",
    "Student",
    "Class",
    "ClassStudent",
    "KnowledgePoint",
    "Question",
    "QuestionType",
    "SubQuestion",
    "QuestionAnswer",
    "QuestionKnowledge",
    "QuestionEmbedding",
    "Source",
    "MediaResource",
    "QuestionMedia",
    "MediaUsageType",
    "Paper",
    "PaperQuestion",
    "PaperStatus",
    "Homework",
    "HomeworkResult",
    "StudentKPStats",
    "WeakPoint",
    "AuditLog",
    "BackgroundTask",
    "TaskStatus",
    "TaskType",
]
