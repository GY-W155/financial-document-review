"""一键跑通完整审核链路（HTTP 驱动，验收标准 2.7.15 的落地）。

前置：后端已启动（uvicorn app.main:app --port 8000），数据库已初始化并导入 init/seed。
用法：python scripts/demo_chain.py   （可用 BASE_URL 覆盖后端地址）

链路：登录 -> 创建单据 -> 维护明细 -> 上传附件 -> 提交审批 -> 附件解析 ->
      风险分析 -> 多节点审批 -> 供应商风险 -> 报告导出 -> 多轮对话。
"""
import json
import os

import httpx

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API = BASE + "/api/v1"

PASS = 0
FAIL = 0


def step(name: str, fn) -> object:
    global PASS, FAIL
    print(f"\n▶ {name}")
    try:
        out = fn()
        print("  ✓", json.dumps(out, ensure_ascii=False)[:420] if isinstance(out, (dict, list)) else out)
        PASS += 1
        return out
    except Exception as exc:
        FAIL += 1
        print(f"  ✗ 失败：{exc}")
        return None


def req(client: httpx.Client, method: str, path: str, **kw):
    resp = client.request(method, API + path, **kw)
    if resp.status_code >= 400:
        raise RuntimeError(f"{resp.status_code}: {resp.text[:300]}")
    return resp.json()


def login(client, username) -> object:
    d = req(client, "POST", "/auth/login", json={"username": username, "password": "123456"})["data"]
    client.headers["Authorization"] = f"Bearer {d['access_token']}"
    return d["user"]


def make_invoice_pdf() -> bytes:
    """读取预生成的样例发票 PDF，客户端无需 pymupdf。"""
    import os
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "scripts", "samples", "invoice_1017.pdf")
    with open(p, "rb") as f:
        return f.read()


def approve_as(client, role: str) -> object:
    """以指定角色登录并处理第一个待办审批任务。"""
    username = {"approver": "lilei", "finance": "zhaomin", "admin": "admin"}[role]
    login(client, username)
    tasks = req(client, "GET", "/approval/tasks?status=pending")["data"]
    items = tasks["items"] if isinstance(tasks, dict) else tasks
    if not items:
        return {"note": "无待办任务"}
    return req(client, "POST", f"/approval/tasks/{items[0]['task_id']}/approve?comment=同意")["data"]


def main():
    client = httpx.Client(base_url=BASE, timeout=60)

    step("申请人登录", lambda: login(client, "wangfang"))

    doc = step("创建对公付款单", lambda: req(client, "POST", "/documents", json={
        "document_type": "对公付款单", "applicant_department": "财务部", "budget_department": "财务部",
        "payee_name": "北京华宇科技有限公司", "payee_account": "622200001", "expense_category": "技术服务费",
        "total_amount": 1200, "currency": "CNY", "apply_date": "2026-08-27", "reason_text": "采购技术开发服务",
        "extra_fields": {"contract_no": "HT-2026-001", "contract_amount": 1500, "payment_ratio": 0.8},
        "line_items": [{"item_type": "payment", "item_name": "技术服务费", "amount": 1200, "quantity": 1, "unit_price": 1200}],
    })["data"])
    doc_id = doc["id"]
    doc_no = doc["document_no"]

    step("维护费用明细", lambda: req(client, "POST", f"/documents/{doc_id}/line-items", json={
        "item_type": "expense", "item_name": "交通费", "amount": 200, "quantity": 1, "unit_price": 200})["data"])

    pdf = make_invoice_pdf()
    att = step("上传发票附件", lambda: req(client, "POST", f"/documents/{doc_id}/attachments",
                files={"file": ("invoice.pdf", pdf, "application/pdf")})["data"])
    att_id = att["id"]

    step("提交审批", lambda: req(client, "POST", f"/documents/{doc_id}/submit")["data"])
    step("解析附件", lambda: req(client, "POST", f"/documents/{doc_id}/attachments/{att_id}/parse")["data"])

    analysis = step("发起风险分析", lambda: req(client, "POST", f"/documents/{doc_id}/analysis")["data"])
    task_id = analysis["task_id"]

    step("查询分析任务状态", lambda: req(client, "GET", f"/analysis/tasks/{task_id}")["data"])

    findings = step("查询风险项", lambda: req(client, "GET", f"/analysis/tasks/{task_id}/findings")["data"])
    items = findings["items"] if isinstance(findings, dict) else findings
    if items:
        step("风险项人工复核确认", lambda: req(client, "PATCH",
             f"/analysis/risk-findings/{items[0]['id']}/review-status",
             json={"review_status": "confirmed"})["data"])

    report = step("查询风险报告", lambda: req(client, "GET", f"/analysis/tasks/{task_id}/report")["data"])
    report_id = report["id"]

    step("金额核对面板", lambda: req(client, "GET", f"/documents/{doc_id}/amount-comparison")["data"])

    step("节点1 审批人员通过", lambda: approve_as(client, "approver"))
    step("节点2 财务人员通过", lambda: approve_as(client, "finance"))

    step("供应商风险查询", lambda: req(client, "GET", "/suppliers/SUP001/risks")["data"])
    step("报告导出", lambda: client.get(API + f"/analysis/review-reports/{report_id}/export").text[:80])

    sess = step("创建审核会话", lambda: req(client, "POST", "/review-sessions", json={})["data"])
    sid = sess["id"]
    step("会话消息(缺编号)", lambda: req(client, "POST", f"/review-sessions/{sid}/messages",
         json={"content": "帮我分析对公付款单"})["data"])
    step("会话消息(补编号)", lambda: req(client, "POST", f"/review-sessions/{sid}/messages",
         json={"content": f"单据是 {doc_no}"})["data"])

    print(f"\n{'='*60}\n链路完成：通过 {PASS} 步，失败 {FAIL} 步。单据 {doc_no}")


if __name__ == "__main__":
    main()
