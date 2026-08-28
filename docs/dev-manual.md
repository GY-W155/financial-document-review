# 财务单据智能风险审核系统 — 开发手册

## 1. 工程目录

```
financial-document-review/
├── docs/                 # 需求文档 / 开发手册
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI 入口，CORS/路由注册/异常处理
│   │   ├── config.py         # pydantic-settings，读 .env
│   │   ├── database.py       # async engine + session + Base
│   │   ├── models/           # SQLAlchemy 模型（单文件 models.py 亦可）
│   │   ├── schemas/          # Pydantic 请求/响应模型
│   │   ├── core/             # security(JWT/密码)、deps(依赖注入/权限)
│   │   ├── api/              # 路由层（每个模块一个 router）
│   │   ├── services/         # 业务逻辑层（薄 controller 调厚 service）
│   │   ├── rules/            # 规则引擎（纯函数，规则注入）
│   │   ├── llm/              # OpenAI 兼容客户端 + prompts
│   │   ├── ocr/              # PaddleOCR + 图像预处理 + 降级
│   │   └── utils/            # 通用工具（分页/哈希/金额）
│   └── requirements.txt
├── frontend/              # Vue3+Vite+Element Plus
│   └── src/{router,api,stores,views,components}
├── database/
│   ├── init.sql           # 建表 DDL
│   └── seed.sql           # 种子数据
├── docker/
│   ├── docker-compose.yml # mysql + backend + frontend(nginx)
│   ├── backend.Dockerfile
│   └── frontend.Dockerfile + nginx.conf
├── uploads/               # 附件存储根目录
└── scripts/demo_chain.py  # 一键跑通完整演示链路
```

## 2. 分层约定

- **router → service → (models / crud)**：路由只做参数校验与响应包装；业务逻辑下沉到 service。
- **async 全链路**：`async def` + `AsyncSession`。DB 用 `session.begin()` / `commit`，统一不泄漏事务。
- **规则引擎纯函数化**：每个规则 = `(ctx) -> list[RiskFindingData]`，便于单测与复用。
- **LLM/OCR 可降级**：解析/字段提取失败返回 `manual_review`，不阻断分析主流程。
- **权限在依赖层校验**：`get_current_user` + `require_roles()` + 数据归属过滤统一在 service 里做。

## 3. 模块划分与构建顺序（M0~M9）

| 里程碑 | 内容 | 对应 2.7.x |
|--------|------|-----------|
| M0 骨架 | 目录/配置/DB/启动 | 2.7.10 |
| M1 认证权限 | login/me/JWT/角色 | 2.7.3, 2.7.9 |
| M2 单据 | 五类单据 CRUD/明细/附件/状态流转 | 2.7.2, 2.7.5 |
| M3 流程 | 工作流配置/实例/任务/多节点流转 | 2.7.4, 2.7.5 |
| M4 解析 | 附件解析任务/OCR/LLM 字段提取 | 2.7.1, 2.7.9 |
| M5 分析 | 规则引擎/风险项/金额核对/整体等级 | 2.7.7, 2.7.13 |
| M6 会话 | 多轮对话/槽位澄清/已确认保活 | 2.7.6 |
| M7 报告 | 报告生成/导出/人工复核/审计 | 2.7.13, 2.7.14 |
| M8 前端 | 页面/模块 | 2.7.4, 2.7.8 |
| M9 部署 | docker-compose/CPU-GPU 分离 | 2.7.12 |

## 4. 接口清单

严格实现 2.7.11 全部接口，路径前缀 `/api/v1`，统一：

- 认证：`Authorization: Bearer <token>`
- 响应：`{ "code": 0, "message": "ok", "data": ... }`（成功 code=0；失败 code 非 0 + message）
- 分页：`?page=&page_size=` 返回 `{ items, total }`
- 错误：HTTP 状态码 + `{ code, message }` JSON body

## 5. 数据分析口径

- 金额统一用 `Decimal` 存字符串/数值，比较先量化再取绝对值（容差字段 `@diff_threshold`）。
- 证据定位 `evidence_positions_json`：`[{ page, text, field, confidence, bbox }]`。
- 风险结论必须携带 `actual_value_json / reference_value_json / threshold_json / evidence_json`，满足"展示计算值、对比值、规则阈值和数据来源"。

## 6. 关键依赖

后端：`fastapi uvicorn[standard] sqlalchemy[asyncio] asyncmy pydantic-settings python-jose[cryptography] passlib[bcrypt] python-multipart httpx openai pymupdf pillow paddleocr pydantic`。
前端：`vue vue-router pinia axios element-plus echarts`。

## 7. 运行入口

- 后端：`cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000`（需先起 MySQL 并导入 init.sql/seed.sql）。
- 前端：`cd frontend && npm install && npm run dev`（dev 代理 `/api` → `:8000`）。
- 一键演示：`python scripts/demo_chain.py`。
