"""生成种子数据 database/seed.sql：用户/角色/权限/规则/工作流/供应商/市场价。"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "backend"))

from app.core.security import hash_password  # noqa: E402

OUT = os.path.join(BASE, "database", "seed.sql")

users = [
    ("wangfang", "王芳", ["applicant"], "财务部"),
    ("lilei", "李磊", ["approver"], "财务部"),
    ("zhaomin", "赵敏", ["finance"], "财务部"),
    ("admin", "系统管理员", ["admin"], "信息部"),
]

roles = [
    ("applicant", "单据申请人"),
    ("approver", "审批人员"),
    ("finance", "财务人员"),
    ("admin", "系统管理员"),
]

permissions = [
    ("doc.create", "创建单据", "document", "create"),
    ("doc.view", "查看单据", "document", "view"),
    ("doc.approve", "审批单据", "document", "approve"),
    ("rule.manage", "维护规则", "rule", "manage"),
    ("sys.manage", "系统管理", "system", "manage"),
]

L = []
L.append("USE financial_doc_review;")
L.append("SET NAMES utf8mb4;")
# 用 DELETE 而非 TRUNCATE：MySQL 不允许 TRUNCATE 被外键引用的父表（即便 FK_CHECKS=0），
# 会导致脚本中断、后续工作流/供应商/市场价未插入。DELETE 在 FK_CHECKS=0 下安全。
L.append("SET FOREIGN_KEY_CHECKS = 0;")
for tbl in [
    "audit_logs", "session_messages", "review_sessions", "approval_tasks",
    "approval_instances", "document_status_logs", "document_versions",
    "invoice_records", "attachment_parse_results", "risk_findings",
    "manual_reviews", "review_reports", "analysis_tasks", "document_line_items",
    "document_attachments", "financial_documents", "role_permissions", "user_roles",
    "permissions", "roles", "users",
]:
    L.append(f"DELETE FROM {tbl};")
L.append("SET FOREIGN_KEY_CHECKS = 1;")

# Roles
for code, name in roles:
    L.append(f"INSERT INTO roles (role_code, role_name, status) VALUES ('{code}', '{name}', 'active');")

# Permissions
perm_sql = ", ".join(
    f"('{c}', '{n}', '{rt}', '{at}')" for c, n, rt, at in permissions
)
L.append(f"INSERT INTO permissions (permission_code, permission_name, resource_type, action_type) VALUES {perm_sql};")

# Users + user_roles (admin 拥有全部角色，便于演示)
for i, (uname, dname, rcodes, dept) in enumerate(users, start=1):
    pwd = hash_password("123456")
    L.append(f"INSERT INTO users (id, username, display_name, password_hash, status) VALUES ({i}, '{uname}', '{dname}', '{pwd}', 'active');")
    for rc in rcodes:
        rid = roles.index((rc, dict(roles)[rc])) + 1
        L.append(f"INSERT INTO user_roles (user_id, role_id) VALUES ({i}, {rid});")

# 审批工作流（五类单据各一条，含两节点：初审->财务复核）
wf_config = [
    (1, "对公付款默认流程", "对公付款单"),
    (2, "费用报销默认流程", "费用报销单"),
    (3, "预付款默认流程", "预付款单"),
    (4, "批量付款默认流程", "批量付款单"),
    (5, "差旅报销默认流程", "差旅报销单"),
]
for wid, wname, wtype in wf_config:
    L.append(f"INSERT INTO approval_workflows (id, workflow_name, document_type, match_conditions_json, status) VALUES ({wid}, '{wname}', '{wtype}', '{{}}', 'active');")
    L.append(f"INSERT INTO approval_workflow_nodes (workflow_id, node_name, node_order, approver_role, approval_mode) VALUES ({wid}, '初审', 1, 'approver', 'any');")
    L.append(f"INSERT INTO approval_workflow_nodes (workflow_id, node_name, node_order, approver_role, approval_mode) VALUES ({wid}, '财务复核', 2, 'finance', 'any');")

# 审核规则
rules = [
    ("amount_consistency", "单据与发票金额一致性", "amount", '{"amount_tolerance": 50}'),
    ("line_total_consistency", "明细与总金额一致性", "amount", '{"tolerance": 10}'),
    ("expense_standard", "费用标准合规性", "expense", '{"housing_standard": 600, "meal_standard": 150}'),
    ("market_price", "市场价格合理性", "price", '{"off_ratio": 20}'),
    ("behavior_anomaly", "消费行为异常", "behavior", '{"multiplier": 3}'),
    ("supplier_risk", "供应商风险", "supplier", '{}'),
    ("attachment_completeness", "附件完整性", "attachment", '{}'),
    ("duplicate_invoice", "重复票据风险", "invoice", '{}'),
]
for code, name, cat, thr in rules:
    L.append(f"INSERT INTO audit_rules (rule_code, rule_name, rule_category, threshold, status) VALUES ('{code}', '{name}', '{cat}', '{thr}', 'active');")

# 市场价参考
prices = [
    ("商务酒店-北京", "双床房", "北京", 450, 750, "CNY", "携程", "2026-01-01"),
    ("高铁票-北京-上海", "二等座", "北京", 500, 650, "CNY", "12306", "2026-01-01"),
]
L.append("INSERT INTO market_price_references (item_name, specification, region, price_min, price_max, currency, source_name, effective_date) VALUES "
         + ", ".join(f"('{a}', '{b}', '{c}', {d}, {e}, '{f}', '{g}', '{h}')" for a, b, c, d, e, f, g, h in prices) + ";")

# 供应商
L.append("INSERT INTO supplier_profiles (supplier_code, supplier_name, credit_status, blacklist_status, risk_tags_json, bank_accounts_json) "
         "VALUES ('SUP001', '北京华宇科技有限公司', 'normal', 'normal', '[]', '[{\"account\":\"622200001\",\"bank\":\"工商银行\"}]');")
L.append("INSERT INTO supplier_profiles (supplier_code, supplier_name, credit_status, blacklist_status, risk_tags_json, bank_accounts_json) "
         "VALUES ('SUP002', '上海瑞丰供应链有限公司', 'risk', 'blacklisted', '[\"失信\",\"经营异常\"]', '[{\"account\":\"623300002\",\"bank\":\"建设银行\"}]');")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(L) + "\n")

print(f"生成 {OUT}")
