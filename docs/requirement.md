# 财务单据智能风险审核系统 — 需求文档

> 原始需求见 2.7.1 ~ 2.7.15，本文档在其基础上补充**技术选型**、**实现口径**与**验收映射**，作为开发与验收的基线。

## 1. 项目概述

面向企业内部财务场景，实现一个**独立运行**的单据智能风险审核系统，覆盖：单据创建 → 明细维护 → 附件上传 → 提交审批 → OCR/LLM 附件解析 → 规则+大模型风险分析 → 人工复核 → 审批流转 → 报告导出 的完整链路。

- 领域：企业财务风控 / 智能审核 / 审批自动化
- 融合大模型能力：自然语言多轮对话（智能审核对话）、图片/OCR 识别、结构化字段提取、风险结论生成
- 交付形式：可运行**前端**（Vue3+Vite）+ **后端**（FastAPI async）+ **数据库初始化脚本**（MySQL8）+ **文件存储模块** + **示例数据** + **接口说明** + **完整审核演示链路**

## 2. 技术选型（已由用户确认）

| 维度 | 选型 | 说明 |
|------|------|------|
| 后端 | Python 3.11 + FastAPI | async 模式 |
| ORM | SQLAlchemy 2.x async | 与上一项目保持一致 |
| 数据库驱动 | asyncmy | MySQL 8 |
| 数据库 | MySQL 8 | Docker 部署，容器内 3306 → 宿主机 3309 |
| 连接串 | `mysql+asyncmy://root:123456@127.0.0.1:3309/financial_doc_review` | 库名 `financial_doc_review` |
| 建表脚本 | `database/init.sql` | 由 SQLAlchemy 元数据生成，也提供手写 DDL |
| 种子数据 | `database/seed.sql` | 用户/角色/单据/规则/供应商/市场价示例 |
| 前端 | Vue 3 + Vite + Element Plus + Pinia + Vue Router + Axios | |
| LLM | **OpenAI 兼容接口** | 通过 `OPENAI_BASE_URL`/`OPENAI_API_KEY`/`OPENAI_MODEL` 配置，兼容 DeepSeek/Qwen/Kimi/GPT 等；VLM 视觉用于发票/图片 OCR |
| OCR | PaddleOCR（图片/PDF 转图）+ LLM 视觉识别 双通道 | 解析失败时降级为 `manual_review` 状态 |
| 存储 | 本地文件系统 `uploads/` | 校验类型/大小/路径；生产可换对象存储 |
| 部署 | docker-compose（MySQL + 后端 + 前端 nginx） | 支持 CPU/GPU 分流：视觉/OCR 可单列 GPU 服务 |

## 3. 角色与权限（2.7.3）

| 角色 code | 名称 | 核心权限 |
|-----------|------|----------|
| `applicant` | 单据申请人 | 创建/编辑/复制/提交/撤回/作废本人单据；查看本人单据 |
| `approver` | 审批人员 | 发起分析、查看风险面板/证据、填写复核意见、通过/退回/驳回 |
| `finance` | 财务人员 | 查看全部单据分析结果、维护审核规则/市场价/供应商风险 |
| `admin` | 系统管理员 | 用户/角色/权限/审批流程/模型配置/系统参数 |

统一规则：所有数据访问校验**登录态 + 角色 + 数据归属权限**。申请人仅能访问本人单据；审批人/财务可见余额更大（详见实现语义）。

## 4. 核心状态机

- 单据 `document_status`：`draft` `pending_review` `reviewing` `returned` `approved` `rejected` `withdrawn` `voided`
- 审批实例 `instance_status`：`pending` `running` `approved` `returned` `rejected` `cancelled`
- 审批任务 `task_status`：`pending` `approved` `returned` `rejected` `cancelled`
- 附件存储 `storage_status`：`uploading` `stored` `failed`
- 附件解析 `parse_status`：`pending` `parsing` `succeeded` `failed` `manual_review`
- 分析任务 `task_status`：`queued` `querying_document` `loading_attachments` `parsing_attachments` `analyzing` `succeeded` `failed` `cancelled`
- 风险项复核 `review_status`：`pending` `confirmed` `dismissed`

## 5. 五类单据（2.7.2）

`对公付款单` `预付款单` `批量付款单` `费用报销单` `差旅报销单`

共用结构化字段：单据类型/编号/申请人/申请部门/预算部门/收款单位/收款账号/费用类别/支出金额/总金额/币种/申请日期/事由。
补充字段：
- 对公付款单、预付款单：合同编号/供应商名称/付款比例/付款条件/计划付款日期
- 批量付款单：付款明细（收款对象/单笔金额/批次总金额/付款笔数）
- 费用报销单：费用明细（消费日期/消费地点/费用科目/报销金额）
- 差旅报销单：出差地点/出差起止日期/交通费/住宿费/餐费/补贴金额

## 6. 风险分析规则（2.7.7）

| 规则 code | 名称 | 要点 |
|-----------|------|------|
| `amount_consistency` | 单据与发票金额一致性 | 申请/报销金额 vs 发票含税合计，输出差异额+比例 |
| `line_total_consistency` | 明细与总金额一致性 | 明细合计 vs 总金额，标记漏项/重复项/差异 |
| `contract_payment_consistency` | 合同与付款一致性 | 合同主体/金额/付款条件/比例 vs 当前付款 |
| `batch_payment_consistency` | 批量付款一致性 | 笔数/各笔合计 vs 批次总额，识别重复收款账号 |
| `expense_standard` | 费用标准合规性 | 按类别/部门/职级/地区/日期对比企业标准 |
| `market_price` | 市场价格合理性 | 按名称/规格/地区/时间对比市场价区间 |
| `behavior_anomaly` | 消费行为异常 | 高频/同日重复/节假日/异地/拆单/金额突增 |
| `supplier_risk` | 供应商风险 | 黑名单/资质/关联交易/履约异常/账号变更/集中付款 |
| `attachment_completeness` | 附件完整性 | 必需附件/清晰度/关键字段/主体一致性 |
| `duplicate_invoice` | 重复票据风险 | 发票代码+号码+金额+开票日期+销售方 |

单项等级：`low` `medium` `high`；整体等级 = 取最高单项并结合风险数量。

## 7. 验收映射（2.7.15）

每条验收点对应实现模块（见开发手册 §3），确保用例可跑通。交付同时提供 `scripts/demo_chain.py` 一键跑通端到端链路。

## 8. 待定/可配置项

- `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` 由用户提供，通过 `.env` 配置
- 费用标准/市场价/供应商风险数据由 `seed.sql` + 规则维护接口提供
