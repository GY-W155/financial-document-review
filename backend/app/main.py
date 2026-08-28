"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import (
    analysis, approvals, auth, dashboard, documents, rules, sessions, suppliers,
)
from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    from .database import dispose_engine
    await dispose_engine()


app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    from fastapi import HTTPException
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code,
                            content={"code": exc.status_code, "message": exc.detail})
    import logging
    logging.getLogger(__name__).exception("Unhandled error")
    return JSONResponse(status_code=500, content={"code": 500, "message": f"服务器内部错误：{exc}"})


API = settings.API_PREFIX
app.include_router(auth.router, prefix=API)
app.include_router(documents.router, prefix=API)
app.include_router(approvals.router, prefix=API)
app.include_router(analysis.router, prefix=API)
app.include_router(sessions.router, prefix=API)
app.include_router(suppliers.router, prefix=API)
app.include_router(rules.router, prefix=API)
app.include_router(dashboard.router, prefix=API)


@app.get("/")
async def root():
    return {"app": settings.APP_NAME, "status": "ok", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
