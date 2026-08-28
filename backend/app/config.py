"""应用配置。全部通过 .env / 环境变量注入。"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 基础
    APP_NAME: str = "financial-document-review"
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = False  # 生产建议 False；True 会打印 SQL 回显

    # 数据库（MySQL 8，docker 容器内 3306 → 宿主机 3309）
    # charset=utf8mb4 必须显式携带，否则 asyncmy 连接字符集非 utf8mb4，
    # 导致按中文名称/类型（供应商、单据类型、商品名）的匹配全部失效。
    DATABASE_URL: str = (
        "mysql+asyncmy://root:123456@127.0.0.1:3309/financial_doc_review?charset=utf8mb4"
    )

    # 安全
    SECRET_KEY: str = "change-me-in-production-please"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720

    # 文件存储
    STORAGE_DIR: str = "uploads"
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_FILE_TYPES: list[str] = ["pdf", "png", "jpg", "jpeg"]

    # LLM（OpenAI 兼容）
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_VISION_MODEL: str = "gpt-4o-mini"
    LLM_ENABLED: bool = True
    OCR_ENABLED: bool = False

    # 分页默认
    DEFAULT_PAGE_SIZE: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
