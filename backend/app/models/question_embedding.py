"""题目 Embedding 的可移植持久化模型。"""

from datetime import datetime

from sqlmodel import JSON, Field, SQLModel


class QuestionEmbedding(SQLModel, table=True):
    """保存题目向量；相似度索引在后续迭代按数据库能力单独构建。"""

    __tablename__ = "question_embeddings"

    question_id: int = Field(
        primary_key=True,
        foreign_key="questions.id",
        ondelete="CASCADE",
    )
    embedding: list[float] = Field(sa_type=JSON)
    dimensions: int
    model: str = Field(max_length=128)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
