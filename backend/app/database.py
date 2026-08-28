"""异步数据库引擎与会话管理。"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    """所有模型基类。"""


def _ensure_utf8mb4(url: str) -> str:
    """asyncmy 连接默认字符集可能非 utf8mb4，导致中文按名称/类型匹配失败。

    给 MySQL URL 追加 charset=utf8mb4；SQLite 等其它方言不受影响。
    """
    if "asyncmy" in url and "charset=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}charset=utf8mb4"
    return url


engine = create_async_engine(
    _ensure_utf8mb4(settings.DATABASE_URL),
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：每个请求一个会话。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        # 由各 service 显式 commit；此处仅兜底回滚


async def init_db() -> None:
    """可选：基于元数据建表（生产用 init.sql，开发可用此）。"""
    from .models import models  # noqa: F401  # 确保模型已注册

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    await engine.dispose()
