"""从 SQLAlchemy 元数据生成 MySQL 建表脚本 database/init.sql。"""
import os
import sys

from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "backend"))

from app.database import Base  # noqa: E402
from app.models import models  # noqa: E402,F401  确保所有模型注册

OUT = os.path.join(BASE, "database", "init.sql")
lines = [
    "CREATE DATABASE IF NOT EXISTS financial_doc_review "
    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
    "USE financial_doc_review;",
]
for table in Base.metadata.sorted_tables:
    lines.append(str(CreateTable(table).compile(dialect=mysql.dialect())) + ";")
    for idx in table.indexes:
        lines.append(str(CreateIndex(idx).compile(dialect=mysql.dialect())) + ";")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n\n".join(lines) + "\n")

print(f"生成 {OUT}，共 {len(Base.metadata.sorted_tables)} 张表")
