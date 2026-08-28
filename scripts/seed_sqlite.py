"""本地调试用：创建 SQLite 测试库并写入种子数据（无 MySQL 时快速跑通链路）。

用法：DATABASE_URL=sqlite+aiosqlite:///./test.db python scripts/seed_sqlite.py
"""
import os
import sys
from datetime import date

AIOSQLITE = "sqlite+aiosqlite:///./test.db"
os.environ["DATABASE_URL"] = os.environ.get("DATABASE_URL", AIOSQLITE)
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "backend"))

from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.database import AsyncSessionLocal, engine, init_db  # noqa: E402
from app.models import (  # noqa: E402
    ApprovalWorkflow, ApprovalWorkflowNode, AuditRule, MarketPriceReference,
    Permission, Role, SupplierProfile, User, UserRole,
)


async def seed():
    await init_db()
    async with AsyncSessionLocal() as session:
        roles = [("applicant", "单据申请人"), ("approver", "审批人员"),
                 ("finance", "财务人员"), ("admin", "系统管理员")]
        role_ids = []
        for code, name in roles:
            r = Role(role_code=code, role_name=name, status="active")
            session.add(r)
            await session.flush()
            role_ids.append(r.id)

        perms = [("doc.create", "创建单据"), ("doc.view", "查看单据"),
                 ("doc.approve", "审批单据"), ("rule.manage", "维护规则"), ("sys.manage", "系统管理")]
        for c, n in perms:
            session.add(Permission(permission_code=c, permission_name=n))

        users = [("wangfang", "王芳", ["applicant"]), ("lilei", "李磊", ["approver"]),
                 ("zhaomin", "赵敏", ["finance"]), ("admin", "系统管理员", ["admin"])]
        id_map = {"applicant": role_ids[0], "approver": role_ids[1],
                  "finance": role_ids[2], "admin": role_ids[3]}
        for uname, dname, rcodes in users:
            u = User(username=uname, display_name=dname, password_hash=hash_password("123456"),
                     status="active")
            session.add(u)
            await session.flush()
            for rc in rcodes:
                session.add(UserRole(user_id=u.id, role_id=id_map[rc]))

        # 审批工作流（五类单据各一条，两节点：初审->财务复核）
        wf_items = [
            ("对公付款默认流程", "对公付款单"), ("费用报销默认流程", "费用报销单"),
            ("预付款默认流程", "预付款单"), ("批量付款默认流程", "批量付款单"),
            ("差旅报销默认流程", "差旅报销单"),
        ]
        wfs = []
        for wname, wtype in wf_items:
            w = ApprovalWorkflow(workflow_name=wname, document_type=wtype,
                                 match_conditions_json={}, status="active")
            session.add(w)
            wfs.append(w)
        await session.flush()
        for w in wfs:
            session.add_all([
                ApprovalWorkflowNode(workflow_id=w.id, node_name="初审", node_order=1,
                                     approver_role="approver", approval_mode="any"),
                ApprovalWorkflowNode(workflow_id=w.id, node_name="财务复核", node_order=2,
                                     approver_role="finance", approval_mode="any"),
            ])

        rules = [
            ("amount_consistency", "单据与发票金额一致性", "amount", {"amount_tolerance": 50}),
            ("line_total_consistency", "明细与总金额一致性", "amount", {"tolerance": 10}),
            ("expense_standard", "费用标准合规性", "expense", {"housing_standard": 600, "meal_standard": 150}),
            ("market_price", "市场价格合理性", "price", {"off_ratio": 20}),
            ("behavior_anomaly", "消费行为异常", "behavior", {"multiplier": 3}),
            ("supplier_risk", "供应商风险", "supplier", {}),
            ("attachment_completeness", "附件完整性", "attachment", {}),
            ("duplicate_invoice", "重复票据风险", "invoice", {}),
        ]
        for code, name, cat, thr in rules:
            session.add(AuditRule(rule_code=code, rule_name=name, rule_category=cat,
                                  threshold=thr, status="active"))

        session.add_all([
            MarketPriceReference(item_name="商务酒店-北京", specification="双床房", region="北京",
                                 price_min=450, price_max=750, currency="CNY",
                                 source_name="携程", effective_date=date(2026, 1, 1)),
            MarketPriceReference(item_name="高铁票-北京-上海", specification="二等座", region="北京",
                                 price_min=500, price_max=650, currency="CNY",
                                 source_name="12306", effective_date=date(2026, 1, 1)),
        ])

        session.add_all([
            SupplierProfile(supplier_code="SUP001", supplier_name="北京华宇科技有限公司",
                            credit_status="normal", blacklist_status="normal", risk_tags_json=[],
                            bank_accounts_json=[{"account": "622200001", "bank": "工商银行"}]),
            SupplierProfile(supplier_code="SUP002", supplier_name="上海瑞丰供应链有限公司",
                            credit_status="risk", blacklist_status="blacklisted",
                            risk_tags_json=["失信", "经营异常"],
                            bank_accounts_json=[{"account": "623300002", "bank": "建设银行"}]),
        ])
        await session.commit()
        await engine.dispose()
    print("SQLite 测试库已创建并写入种子数据")


if __name__ == "__main__":
    import asyncio
    asyncio.run(seed())
