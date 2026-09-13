"""
应用配置
所有配置项通过 .env 文件或环境变量注入。
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== 应用基础 =====
    app_name: str = "math-bank-backend"
    app_env: Literal["development", "production", "testing"] = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    api_v1_prefix: str = "/api/v1"

    # ===== 安全 =====
    jwt_secret_key: str = "dev-secret-please-change-in-production-32chars-min"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24  # 24 小时
    jwt_refresh_token_expire_days: int = 30

    # ===== 数据库 =====
    database_url: str = "sqlite:///./data/math_bank.db"
    db_echo: bool = False  # 生产环境必须 False

    @property
    def sync_database_url(self) -> str:
        """返回同步 SQLAlchemy URL，并兼容旧的异步环境配置。"""
        return self.database_url.replace("sqlite+aiosqlite://", "sqlite://", 1).replace(
            "postgresql+asyncpg://", "postgresql+psycopg://", 1
        )

    # ===== 媒体文件 =====
    media_root: str = "./data/images"
    media_base_url: str = "http://localhost:8000/static"

    # ===== LLM =====
    llm_provider: Literal["minimax", "ollama"] = "minimax"
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimaxi.com/v1"
    minimax_model: str = "MiniMax-Text-01"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:14b"

    # ===== Embedding =====
    embedding_provider: str = "bge-m3"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.minimaxi.com/v1"
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024

    # ===== 日志 =====
    log_level: str = "INFO"
    log_file: str = "./data/logs/app.log"

    # ===== CORS =====
    cors_origins: list[str] = Field(default=["http://localhost:3000", "http://127.0.0.1:3000"])

    # ===== 业务约束 =====
    max_question_embedding_concurrency: int = 3  # 题目入库时并发生成向量数


@lru_cache
def get_settings() -> Settings:
    """单例获取配置"""
    return Settings()


# 全局快捷访问
settings = get_settings()
