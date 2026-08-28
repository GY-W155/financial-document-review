# 财务单据智能风险审核系统

覆盖单据创建 → 明细维护 → 附件上传 → 提交审批 → OCR/LLM 附件解析 → 规则+大模型风险分析 → 人工复核 → 多节点审批 → 报告导出的完整链路。

- 需求文档：[docs/requirement.md](docs/requirement.md)
- 开发手册：[docs/dev-manual.md](docs/dev-manual.md)

## 技术栈

| 层 | 选型 |
|----|------|
| 后端 | Python 3.11 + FastAPI (async) + SQLAlchemy 2.0 (async) |
| 数据库 | MySQL 8（asyncmy）；开发调试可用 SQLite（aiosqlite） |
| 前端 | Vue 3 + Vite + Element Plus + Pinia + ECharts |
| LLM | OpenAI 兼容接口（DeepSeek/Qwen/Kimi/GPT；Vision 用于票据识别） |
| OCR | PaddleOCR（可选，缺失自动降级） |
| 部署 | docker-compose（MySQL + 后端 + 前端 nginx） |

## 目录结构

```
├── backend/          # FastAPI 后端
│   └── app/{api,core,models,rules,llm,ocr,services,schemas}
├── frontend/         # Vue3 前端
├── database/         # init.sql（建表，由模型生成）/ seed.sql（种子数据）
├── docker/           # docker-compose.yml
├── docs/             # 需求文档 / 开发手册
├── scripts/          # demo_chain.py 一键演示、gen_schema.py、seed_sqlite.py
└── uploads/          # 附件存储
```

## 快速开始（本地 SQLite 开发调试，无需 MySQL）

```bash
# 1. 后端
cd backend
pip install -r requirements-app.txt          # 建议用 py0525 环境(3.11)
cd .. && python scripts/seed_sqlite.py       # 建 SQLite 库 + 种子数据
cd backend
DATABASE_URL="sqlite+aiosqlite:///../test.db" uvicorn app.main:app --port 8000

# 2. 前端 (另开终端)
cd frontend
npm install
npm run dev            # http://localhost:5173 (代理 /api -> :8000)

# 3. 跑通完整演示链路
cd .. && python scripts/demo_chain.py        # 需后端已启动
```

演示账号：`wangfang` / `lilei` / `zhaomin` / `admin`，密码均为 `123456`。

## 使用 MySQL 8（Docker，推荐）

```bash
cd docker
# 可选：配置大模型
# 复制 .env.example 到 docker/.env 填写 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
docker compose up -d --build
```

- 前端：http://localhost:8080
- 后端 API：http://localhost:8000，Swagger：http://localhost:8000/docs
- MySQL：宿主机端口 **3309**，库 `financial_doc_review`，账号 `root/123456`
  （对应连接串 `mysql+asyncmy://root:123456@127.0.0.1:3309/financial_doc_review`）
- 首次启动自动执行 `database/init.sql` + `database/seed.sql` 建库建表并灌入种子数据。

## 手动切换真实库

```sql
mysql -uroot -p123456 -h127.0.0.1 -P3309 financial_doc_review < database/init.sql
mysql -uroot -p123456 -h127.0.0.1 -P3309 financial_doc_review < database/seed.sql
# 本地跑后端时设置
# DATABASE_URL=mysql+asyncmy://root:123456@127.0.0.1:3309/financial_doc_review
```

## 大模型接入

系统默认走规则引擎（无需 LLM 即可出风险结论）。要启用 LLM（多轮对话、票据字段抽取、整体建议）：

1. 安装/配置：`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`、`OPENAI_VISION_MODEL`。
2. 图片 OCR：可选 `pip install paddleocr` 并置 `OCR_ENABLED=true`；否则 图片走 LLM 视觉或降级为 `manual_review`。
3. 所有 LLM 调用失败均自动降级为规则式分析，不阻断主流程。

## 演示链路（demo_chain.py）

`scripts/demo_chain.py` 通过 HTTP 一键跑通验收标准 2.7.15 的完整链路：
登录 → 创建对公付款单 → 维护明细 → 上传发票 PDF → 提交审批 → 附件解析 → 风险分析（含金额一致性/明细合计/合同付款一致性/附件完整性/重复票据等规则）→ 风险项人工复核 → 金额核对 → 多节点审批（初审→财务复核）→ 供应商风险 → 报告导出 → 多轮智能审核对话。

本地 SQLite 全链路验证：**19 步全部通过**（节点审批、金额核对、发票解析、风险发现均正常）。

## 接口说明

后端自托管 OpenAPI：`http://localhost:8000/docs`。核心接口均以 `/api/v1` 为前缀，统一响应
`{ "code": 0, "message": "ok", "data": ... }`，认证用 `Authorization: Bearer <token>`，完整清单见需求文档 2.7.11。

## 安全边界

- 密码 pbkdf2 哈希；JWT 令牌带有效期，密码与令牌均可撤销（改密）。
- 所有数据访问校验登录态 + 角色 + 数据归属（申请人仅本人；审批/财务/管理员全量）。
- 附件上传校验类型/大小/哈希/路径；解析结果与风险结论持久化，全程审计。

## 风险检出评估（替代 RAGAS 检索评估）

本系统是「规则 + 大模型」风控，不依赖向量库检索，故经典 RAGAS 检索评估不适用。改用**风险检出评估**：用金标样本走真实分析链路，计算 precision/recall/F1 并输出 CSV。

```bash
# 后端已运行（本地或 Docker：BASE_URL=http://localhost:8080）
python scripts/evaluate_risks.py
# 输出：eval/risk_metrics.csv（汇总）、risk_detailed.csv（逐case）、risk_rules.csv（逐规则）
```

内置 8 个金标 case（金额不一致 / 明细不符 / 合同付款比 / 供应商黑名单 / 重复发票 / 批量付款 / 市场价偏离 / 历史金额突增）。当前基线（SQLite 验证）：**Precision=Recall=F1=1.0**（TP17/FN0/FP0）。该评估曾捕获并修复 `contract_payment_consistency` 的「百分比 vs 比例」比对 bug——即评估套件的回归价值所在。可自行扩充 `GOLDEN_CASES`。

> LLM-as-judge（类 RAGAS correctness）预留 `--llm` 参数，需 OPENAI_API_KEY。
