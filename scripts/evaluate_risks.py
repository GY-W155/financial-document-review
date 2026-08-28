"""风险检出评估（对应真实链路，替代不适用于本系统的 RAGAS 检索评估）。

思路：构造若干"已知应有风险"的金标样本（golden case），调用后端真实分析链路
（创建单据 -> 上传附件 -> 提交 -> 解析 -> 风险分析），比对"实际检出的风险项"与"金标风险项"，
按 risk_type 计算 precision / recall / F1，并输出 CSV。

用法：
  python scripts/evaluate_risks.py                 # 连 http://127.0.0.1:8000
  BASE_URL=http://localhost:8080 python scripts/evaluate_risks.py   # 透过 nginx
  python scripts/evaluate_risks.py --llm           # 附加 LLM 判定（需 OPENAI_API_KEY）

输出：
  eval/risk_metrics.csv     汇总指标
  eval/risk_detailed.csv    逐 case 明细（TP/FP/FN/检出的风险类型）
"""
import argparse
import json
import os
import sys
from collections import defaultdict

import httpx

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API = BASE + "/api/v1"
OUT_DIR = os.path.join(PROJECT, "eval")
SAMPLES_DIR = os.path.join(PROJECT, "scripts", "samples")

# ---- 金标样本：expected 为该场景"应当命中"的风险类型集合 ----
# 说明：对公付款单/费用报销单缺少合同、付款依据、费用明细等必需附件时，
#       attachment_completeness 是真实风险，故计入 expected。
GOLDEN_CASES = [
    {
        "name": "金额不一致+附件缺失",
        "doc_type": "对公付款单", "total": 1200,
        "line_items": [{"item_type": "payment", "item_name": "技术服务费", "amount": 1200}],
        "extra": {"contract_no": "HT-01", "contract_amount": 1500, "payment_ratio": 0.8},
        "payee": "北京华宇科技有限公司",
        "invoices": [1017.00],
        "expected": {"amount_consistency", "contract_payment_consistency", "attachment_completeness"},
    },
    {
        "name": "金额全部一致(仅缺附件)",
        "doc_type": "费用报销单", "total": 1000,
        "line_items": [{"item_type": "expense", "item_name": "办公费", "amount": 1000}],
        "extra": {}, "payee": "北京华宇科技有限公司", "invoices": [1000.00],
        "expected": {"attachment_completeness"},
    },
    {
        "name": "明细合计不一致",
        "doc_type": "费用报销单", "total": 1200,
        "line_items": [{"item_type": "expense", "item_name": "差旅费", "amount": 1400}],
        "extra": {}, "payee": "", "invoices": [1200.00],
        "expected": {"line_total_consistency", "attachment_completeness"},
    },
    {
        "name": "供应商黑名单风险",
        "doc_type": "对公付款单", "total": 1000,
        "line_items": [{"item_type": "payment", "item_name": "采购款", "amount": 1000}],
        "extra": {}, "payee": "上海瑞丰供应链有限公司", "invoices": [],
        "expected": {"supplier_risk", "attachment_completeness"},
    },
    {
        "name": "重复发票",
        "doc_type": "费用报销单", "total": 2000,
        "line_items": [{"item_type": "expense", "item_name": "会议费", "amount": 2000}],
        "extra": {}, "payee": "", "invoices": [1017.00, 1017.00],
        "expected": {"duplicate_invoice", "attachment_completeness"},
    },
    {
        "name": "批量付款：金额不符+重复收款对象",
        "doc_type": "批量付款单", "total": 2000,
        "line_items": [{"item_type": "payment", "item_name": "A", "amount": 800},
                       {"item_type": "payment", "item_name": "B", "amount": 700}],
        "extra": {"payees": "A,B,A"}, "payee": "", "invoices": [],
        "expected": {"batch_payment_consistency", "line_total_consistency", "attachment_completeness"},
    },
    {
        "name": "市场价格偏离",
        "doc_type": "费用报销单", "total": 1000,
        "line_items": [{"item_type": "expense", "item_name": "商务酒店-北京", "amount": 1000,
                        "quantity": 1, "unit_price": 1000}],
        "extra": {}, "payee": "", "invoices": [],
        "expected": {"market_price", "attachment_completeness"},
    },
    {
        "name": "历史金额突增(需先有一笔已通过付款)",
        "doc_type": "对公付款单", "total": 10000, "seed_history": 1000,
        "line_items": [{"item_type": "payment", "item_name": "大额采购", "amount": 10000}],
        "extra": {"contract_no": "HT-02", "contract_amount": 10000, "payment_ratio": 1.0},
        "payee": "北京华宇科技有限公司", "invoices": [10000.00],
        "expected": {"behavior_anomaly", "attachment_completeness"},
    },
]

USERS = {"applicant": "wangfang", "approver": "lilei", "finance": "zhaomin"}


def login(client, username, password="123456"):
    d = client.post(API + "/auth/login", json={"username": username, "password": password}).json()["data"]
    client.headers["Authorization"] = f"Bearer {d['access_token']}"
    return d["user"]


def req(client, method, path, **kw):
    resp = client.request(method, API + path, **kw)
    if resp.status_code >= 400:
        raise RuntimeError(f"{resp.status_code}: {resp.text[:200]}")
    return resp.json()


def invoice_pdf(amount: float) -> bytes:
    """读取仓库内预先生成的样例发票 PDF，客户端无需依赖 pymupdf。"""
    path = os.path.join(SAMPLES_DIR, f"invoice_{int(amount)}.pdf")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"缺少样例发票 {path}；请先运行 `python scripts/gen_samples.py`（需在装有 pymupdf 的环境执行一次即可）")
    with open(path, "rb") as f:
        return f.read()


def approve_doc(client, doc_id):
    """走完两节点审批（初审->财务复核），使单据 approved，供 history 统计。"""
    for role in ("approver", "finance"):
        login(client, USERS[role])
        tasks = req(client, "GET", "/approval/tasks?status=pending")["data"]
        items = tasks if isinstance(tasks, list) else tasks.get("items", [])
        if items:
            req(client, "POST", f"/approval/tasks/{items[0]['task_id']}/approve?comment=评估")


def run_case(client, case):
    """创建单据+附件，跑分析，返回检出的风险类型集合。"""
    login(client, USERS["applicant"])
    if case.get("seed_history"):
        # 先创建另一笔同收款方的小额单据并走完审批，作为历史金额
        seed = {"document_type": case["doc_type"], "total_amount": case["seed_history"],
                "payee_name": case["payee"], "apply_date": "2026-08-01",
                "extra_fields": {"contract_no": "HT-0", "contract_amount": case["seed_history"],
                                 "payment_ratio": 1.0},
                "line_items": [{"item_type": "payment", "item_name": "历史采购", "amount": case["seed_history"]}]}
        d = req(client, "POST", "/documents", json=seed)["data"]
        req(client, "POST", f"/documents/{d['id']}/submit")  # 提交以生成审批任务
        approve_doc(client, d["id"])

    payload = {"document_type": case["doc_type"], "total_amount": case["total"],
               "payee_name": case["payee"], "apply_date": "2026-08-27",
               "extra_fields": case["extra"],
               "line_items": case["line_items"]}
    doc = req(client, "POST", "/documents", json=payload)["data"]
    doc_id = doc["id"]

    for amt in case["invoices"]:
        req(client, "POST", f"/documents/{doc_id}/attachments",
            files={"file": (f"inv-{amt}.pdf", invoice_pdf(amt), "application/pdf")})
        # attachments 列表：取返回
    # 全部解析并触发分析
    attach = req(client, "GET", f"/documents/{doc_id}")["data"]["attachments"]
    for a in attach:
        req(client, "POST", f"/documents/{doc_id}/attachments/{a['id']}/parse")
    r = req(client, "POST", f"/documents/{doc_id}/analysis")["data"]
    findings = req(client, "GET", f"/analysis/tasks/{r['task_id']}/findings")["data"]
    items = findings if isinstance(findings, list) else findings.get("items", findings)
    detected = {f["risk_type"] for f in items}
    return detected


def preflight(client):
    """确认后端基础种子数据就绪；若读到的值与预期不符，打印实际内容以便区分
    「数据缺失」与「读取为乱码（连接字符集问题）」。"""
    login(client, "admin")
    miss = []
    stock = {"对公付款单", "预付款单", "批量付款单", "费用报销单", "差旅报销单"}

    def show(name, rows, field):
        vals = sorted({repr(r.get(field)) for r in rows})
        print(f"   [{name}] 读到 {len(rows)} 行，{field}= {vals}")

    try:
        wfs = req(client, "GET", "/approval/workflows")["data"] or []
        have = {w["document_type"] for w in wfs}
        if stock - have:
            show("审批工作流", wfs, "document_type")
        miss += [f"工作流缺失({t})" for t in stock - have]
    except Exception:
        miss.append("无法读取审批工作流")
    try:
        mps = req(client, "GET", "/rules/market-prices")["data"] or []
        if not any(m["item_name"] == "商务酒店-北京" for m in mps):
            show("市场价参考", mps, "item_name")
            miss.append("市场价参考缺失(商务酒店-北京)")
    except Exception:
        miss.append("无法读取市场价")
    try:
        r = client.get(API + "/suppliers/SUP002/risks")
        if r.status_code == 404:
            miss.append("供应商缺失(SUP002 黑名单)")
    except Exception:
        miss.append("无法读取供应商")

    if miss:
        print("⚠️  后端基础种子数据缺失：", "；".join(miss))
        print("   若上方「读到 N 行」且值形如 'å¯¹å…¬ä»˜…'，则说明数据在库里是乱码，"
              "属连接字符集未用 utf8mb4（而非数据缺失）。")
        print("   修复（清空数据卷重灌 + 使用带 charset=utf8mb4 的连接串）：")
        print("      cd docker  &&  docker compose down -v  &&  docker compose up -d --build")
        print("   （`docker compose restart` 不会重灌数据，务必用 down -v）\n")
    else:
        print("✅ 后端基础种子数据就绪（工作流/供应商/市场价完整）\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true",
                    help="（预留）用 LLM 判定每个发现是否真实风险，得到类 RAGAS 的 correctness 分数，需 OPENAI_API_KEY")
    args = ap.parse_args()
    if args.llm:
        print("提示：--llm 尚未接入 LLM判定，请直接使用确定性 precision/recall/F1 指标。")
        sys.exit(0)

    client = httpx.Client(timeout=90)
    preflight(client)
    rows = []
    agg = defaultdict(lambda: {"gold": 0, "detected": 0, "tp": 0, "fp": 0, "fn": 0})

    for case in GOLDEN_CASES:
        name = case["name"]
        try:
            detected = run_case(client, case)
        except Exception as exc:
            print(f"[{name}] 执行异常：{exc}")
            rows.append({"case": name, "error": str(exc), "gold": "|".join(sorted(case["expected"])),
                         "detected": "", "tp": 0, "fp": 0, "fn": 0})
            continue
        gold = case["expected"]
        tp = gold & detected
        fp = detected - gold
        fn = gold - detected
        print(f"[{name}] 金标={sorted(gold)} 检出={sorted(detected)} TP={len(tp)} FP={len(fp)} FN={len(fn)}")
        rows.append({"case": name, "gold": "|".join(sorted(gold)), "detected": "|".join(sorted(detected)),
                     "tp": len(tp), "fp": len(fp), "fn": len(fn)})
        for t in tp:
            agg[t]["tp"] += 1
        for t in fp:
            agg[t]["fp"] += 1
            agg[t]["detected"] += 1
        for t in fn:
            agg[t]["fn"] += 1
            agg[t]["gold"] += 1
        for t in gold:
            agg[t]["gold"] += 1
        for t in detected:
            agg[t]["detected"] += 1

    os.makedirs(OUT_DIR, exist_ok=True)

    # 汇总
    tot_tp = sum(r["tp"] for r in rows)
    tot_fp = sum(r["fp"] for r in rows)
    tot_fn = sum(r["fn"] for r in rows)
    precision = tot_tp / (tot_tp + tot_fp) if (tot_tp + tot_fp) else 0.0
    recall = tot_tp / (tot_tp + tot_fn) if (tot_tp + tot_fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    # metrics CSV
    lines = [["dataset", "metric", "value"],
             ["golden_risks", "total_cases", len(GOLDEN_CASES)],
             ["golden_risks", "total_gold", tot_tp + tot_fn],
             ["golden_risks", "total_detected", tot_tp + tot_fp],
             ["golden_risks", "tp", tot_tp],
             ["golden_risks", "fp", tot_fp],
             ["golden_risks", "fn", tot_fn],
             ["golden_risks", "precision", round(precision, 4)],
             ["golden_risks", "recall", round(recall, 4)],
             ["golden_risks", "f1", round(f1, 4)]]
    with open(os.path.join(OUT_DIR, "risk_metrics.csv"), "w", encoding="utf-8") as f:
        f.write("\n".join(",".join(str(c) for c in l) for l in lines) + "\n")

    # detailed CSV
    det_lines = [["case", "gold_risk_types", "detected_risk_types", "tp", "fp", "fn"]]
    for r in rows:
        det_lines.append([r["case"], r["gold"], r["detected"], r["tp"], r["fp"], r["fn"]])
    with open(os.path.join(OUT_DIR, "risk_detailed.csv"), "w", encoding="utf-8") as f:
        f.write("\n".join(",".join(str(c) for c in l) for l in det_lines) + "\n")

    # per-rule
    rule_lines = [["rule", "gold", "detected", "tp", "fp", "fn", "precision", "recall", "f1"]]
    for rule, m in sorted(agg.items()):
        p = m["tp"] / (m["tp"] + m["fp"]) if (m["tp"] + m["fp"]) else 0.0
        rc = m["tp"] / (m["tp"] + m["fn"]) if (m["tp"] + m["fn"]) else 0.0
        ff = 2 * p * rc / (p + rc) if (p + rc) else 0.0
        rule_lines.append([rule, m["gold"], m["detected"], m["tp"], m["fp"], m["fn"],
                           round(p, 4), round(rc, 4), round(ff, 4)])
    with open(os.path.join(OUT_DIR, "risk_rules.csv"), "w", encoding="utf-8") as f:
        f.write("\n".join(",".join(str(c) for c in l) for l in rule_lines) + "\n")

    print("\n" + "=" * 60)
    print(f"风险评估结果（{len(GOLDEN_CASES)} 个金标 case，基于 {BASE}）")
    print(f"  Precision = {precision:.4f}   Recall = {recall:.4f}   F1 = {f1:.4f}")
    print(f"  TP={tot_tp} FP={tot_fp} FN={tot_fn}")
    print(f"  CSV 已写入：{os.path.join(OUT_DIR, 'risk_metrics.csv')}")


if __name__ == "__main__":
    main()
