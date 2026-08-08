#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
diagnose_rounds.py — ct-safety 迭代鲁棒性诊断 harness

为每一轮（iteration）生成 10 个「简单→复杂、覆盖各场景」的案例，离线（mock 网络）
跑 `ct_safety.run()`，自动分类：
    CRASH    : 运行抛异常
    ANOMALY  : 输出含 nan/inf/Traceback，或违反硬编码契约（评分越界、tier 非法、
               零细胞却报信号、SOC 映射错误等）
    OK       : 通过

用法:
    python tests/diagnose_rounds.py --iter 1        # 跑第 1 轮 10 案例
    python tests/diagnose_rounds.py --iter all      # 依次跑全部（不自动修复）
    python tests/diagnose_rounds.py --list          # 仅列出各轮案例名

修复问题后，用 --iter N 复跑确认全绿，然后升版本号。
纯 stdlib；依赖 tests/_mocks.py 的离线网络桩（并在其基础上按案例注入计数）。
"""
import argparse
import importlib
import json
import os
import re
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, "..", "scripts"))
for p in (HERE, SCRIPTS):
    if p not in sys.path:
        sys.path.insert(0, p)

import disproportionality  # noqa: E402  (供 checks 直接调用 compute/map_soc)
import ct_safety  # noqa: E402
import fetch_faers  # noqa: E402
import time_series  # noqa: E402
import fetch_cn_pv  # noqa: E402
import fetch_fda_label  # noqa: E402
import _mocks  # noqa: E402

GENERIC = {"a": 120, "b": 4880, "c": 3000, "d": 992000,
           "drug_total": 5000, "grand_total": 1000000}
GENERIC_TOP = {"counts": None, "drug_total": 5000, "grand_total": 1000000,
               "top_events": [{"term": "PNEUMONITIS"},
                              {"term": "DIARRHOEA"},
                              {"term": "RASH"}]}


# ---------------------------------------------------------------------------
# per-case mock builders
# ---------------------------------------------------------------------------
def make_fake_fetch_counts(counts_map, top_events):
    def fake(drug, event, field, top, api_key, *, run, out,
             date_from=None, date_to=None, timeout=None, retries=None):
        if event is None:
            if top_events:
                data = {"counts": None, "drug_total": 5000, "grand_total": 1000000,
                        "top_events": top_events}
            else:
                data = dict(GENERIC_TOP)
        else:
            c = counts_map.get((drug, event))
            if c == "MISSING":
                data = {"counts": None, "drug_total": None, "grand_total": None}
            elif isinstance(c, dict):
                data = {"counts": {"a": c["a"], "b": c["b"], "c": c["c"], "d": c["d"]},
                        "drug_total": c.get("drug_total", 5000),
                        "grand_total": c.get("grand_total", 1000000)}
            else:
                data = {"counts": {"a": GENERIC["a"], "b": GENERIC["b"],
                                   "c": GENERIC["c"], "d": GENERIC["d"]},
                        "drug_total": GENERIC["drug_total"],
                        "grand_total": GENERIC["grand_total"]}
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data
    return fake


def make_fake_qtotal():
    def qt(search, api_key=None, timeout=None, retries=None):
        return 150 if " AND " in search else 5000
    return qt


def make_fake_monthly(monthly):
    def fm(drug, event, field, api_key, date_from, date_to):
        return list(monthly)
    return fm


def make_fake_label(empty):
    def fl(drug, api_key=None, run=False, out=None, limit=5, timeout=120, retries=3):
        if empty:
            result = {"source": "FDA Label (openFDA drug/label.json)",
                      "query": drug, "matched_drug_terms": [drug], "n_results": 0,
                      "adverse_reactions": [], "warnings": []}
        else:
            result = {"source": "FDA Label (openFDA drug/label.json)",
                      "query": drug, "matched_drug_terms": [drug], "n_results": 2,
                      "adverse_reactions": ["pneumonitis and interstitial lung disease",
                                            "rash", "diarrhea"],
                      "warnings": ["Hepatotoxicity has been reported"]}
        if out:
            with open(out, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        return result
    return fl


def make_fake_cn_pv(override):
    base = {"source": "CN-PV (cdr-adr.org.cn)", "note": "qualitative",
            "query": {}, "searched_columns": ["药物警戒快讯"], "max_per_column": 10,
            "hit_count": 2,
            "hits": [{"title": "x", "column": "药物警戒快讯", "date": "2024-03-01",
                      "url": "https://example.com/1", "matched_keywords": ["x"]}]}
    if override:
        base.update(override)

    def fs(cn_drug, cn_en=None, event=None, terms=None, max_per=10,
           run=False, out=None):
        result = dict(base)
        result["max_per_column"] = base.get("max_per_column", 10)
        if out:
            with open(out, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        return result
    return fs


def make_fake_case_reports(error):
    def fcr(drug, event, field, n=0, run=False, out=None,
            date_from=None, date_to=None):
        if error:
            raise RuntimeError("simulated case-report fetch failure")
        data = {"cases": [{"caseid": "1", "reportnum": "US-1", "drugname": drug}] * max(n, 1)}
        if out:
            with open(out, "w", encoding="utf-8") as f:
                json.dump(data, f)
        return data
    return fcr


# ---------------------------------------------------------------------------
# install mocks for a case (baseline from _mocks + per-case overrides)
# ---------------------------------------------------------------------------
def install_case_mocks(case):
    _mocks.install()
    counts_map = case.get("counts", {})
    top_events = case.get("top_events")
    fetch_faers.fetch_counts = make_fake_fetch_counts(counts_map, top_events)
    fetch_faers.query_total = make_fake_qtotal()
    if case.get("monthly") is not None:
        time_series.fetch_monthly_series = make_fake_monthly(case["monthly"])
    if case.get("label_empty") is not None:
        fetch_fda_label.fetch_label = make_fake_label(case["label_empty"])
    if case.get("cn_pv_override") is not None:
        fetch_cn_pv.search = make_fake_cn_pv(case["cn_pv_override"])
    if case.get("case_error"):
        fetch_faers.fetch_case_reports = make_fake_case_reports(True)


# ---------------------------------------------------------------------------
# parsing helpers
# ---------------------------------------------------------------------------
def parse_signal(md):
    if "⚠️ 信号阳性" in md:
        return "pos"
    if "无显著信号" in md:
        return "neg"
    return None


def parse_score(md):
    m = re.search(r"Safety Signal Score:\s*\*\*([\d.]+)\s*/\s*100\*\*", md)
    return float(m.group(1)) if m else None


def parse_tier(md):
    m = re.search(r"Evidence Tier:\s*\*\*(T[1-4])\b", md)
    return m.group(1) if m else None


def parse_soc(md):
    # single-event report SOC line
    m = re.search(r"系统器官分类 SOC:\s*\*\*([^*]+?)\*\*", md)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# generic anomaly checks (run regardless of case)
# ---------------------------------------------------------------------------
def generic_checks(md, md_out, case):
    problems = []
    if md is None:
        return ["md 未生成"]
    low = md.lower()
    for tok in ("nan", "infinity", "traceback"):
        if tok in low:
            problems.append("输出含 '%s'" % tok)
    # stray 'inf' token (avoid matching words like 'information'); crude but useful
    if re.search(r"\binf\b", low):
        problems.append("输出含裸 'inf'")
    # score range
    sc = parse_score(md)
    if sc is not None:
        if sc < 0 or sc > 100:
            problems.append("评分越界 %.1f" % sc)
    # tier valid
    t = parse_tier(md)
    if t is not None and t not in ("T1", "T2", "T3", "T4"):
        problems.append("非法 tier %s" % t)
    return problems


# ---------------------------------------------------------------------------
# case runner
# ---------------------------------------------------------------------------
def run_case(case):
    name = case.get("name", case.get("id", "?"))
    out_dir = tempfile.mkdtemp(prefix="ctdiag_")
    kwargs = dict(
        drug=case.get("drug", "osimertinib"),
        event=case.get("event", "PNEUMONITIS"),
        field=case.get("field", "patient.drug.medicinalproduct"),
        top=case.get("top", 10),
        api_key=case.get("api_key"),
        out_dir=out_dir,
        with_cn_pv=case.get("with_cn_pv", False),
        drug_cn=case.get("drug_cn"),
        event_cn=case.get("event_cn"),
        cn_terms=case.get("cn_terms"),
        cn_max=case.get("cn_max", 10),
        date_from=case.get("date_from"),
        date_to=case.get("date_to"),
        benchmark_drugs=case.get("benchmark_drugs"),
        top_events_signal=case.get("top_events_signal"),
        continuity=case.get("continuity", True),
        trend=case.get("trend", False),
        compare_drugs=case.get("compare_drugs"),
        with_fda_label=case.get("with_fda_label", False),
        case_level=case.get("case_level", 0),
    )
    md = None
    exc = None
    try:
        if case.get("validate"):
            ct_safety._run_validate_controls(
                out_dir, kwargs["api_key"], kwargs["field"], kwargs["top"],
                continuity=kwargs["continuity"])
            md_out = os.path.join(out_dir, "control_validation.md")
            md = open(md_out, encoding="utf-8").read() if os.path.exists(md_out) else ""
        else:
            md_out = ct_safety.run(**kwargs)
            md = open(md_out, encoding="utf-8").read() if os.path.exists(md_out) else None
    except Exception as e:  # noqa: BLE001
        exc = e
        md = None

    problems = []
    if exc is not None:
        return {"name": name, "status": "CRASH",
                "detail": "%s: %s" % (type(exc).__name__, exc),
                "tb": traceback.format_exc()}
    problems += generic_checks(md, None, case)
    # contract assertions expressed in the case
    exp_sig = case.get("expect_signal")
    if exp_sig is not None:
        got = parse_signal(md)
        if got != exp_sig:
            problems.append("信号预期 %s 实际 %s" % (exp_sig, got))
    exp_soc = case.get("expect_soc")
    if exp_soc is not None:
        got = parse_soc(md)
        if got != exp_soc:
            problems.append("SOC 预期 %r 实际 %r" % (exp_soc, got))
    # custom checks
    for cname, fn in case.get("checks", []):
        try:
            fn({"md": md, "case": case, "kwargs": kwargs})
        except AssertionError as ae:
            problems.append("%s: %s" % (cname, ae))
        except Exception as e:  # noqa: BLE001
            problems.append("%s: 检查异常 %s" % (cname, e))
    if problems:
        return {"name": name, "status": "ANOMALY", "detail": "；".join(problems),
                "md": md}
    return {"name": name, "status": "OK", "detail": "", "md": md}


# ---------------------------------------------------------------------------
# ITERATION DEFINITIONS  (10 iterations × 10 cases)
# ---------------------------------------------------------------------------
def soc_check(term, expected):
    def fn(ctx):
        got = disproportionality.map_soc(term)
        assert got == expected, "%s -> %r" % (term, got)
    return ("map_soc:%s" % term, fn)


def sig_check(a, b, c, d, continuity, expected):
    def fn(ctx):
        from disproportionality import compute
        res = compute(a, b, c, d, continuity=continuity)
        got = "pos" if res["signal_overall"] else "neg"
        assert got == expected, "compute(%s) -> %s" % ((a, b, c, d), got)
    return ("compute:sig", fn)


ITERATIONS = {}

# ---- Iteration 1 : 数值 / 2×2 边界 -------------------------------------------
ITERATIONS[1] = [
    {"id": "I1C1", "name": "基础阳性信号", "drug": "osimertinib", "event": "PNEUMONITIS",
     "counts": {("osimertinib", "PNEUMONITIS"): {"a": 150, "b": 4850, "c": 3000, "d": 992000}},
     "expect_signal": "pos", "expect_soc": "Respiratory, thoracic and mediastinal disorders"},
    {"id": "I1C2", "name": "零共现 a=0 (保守null)", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 0, "b": 100, "c": 100, "d": 100000}},
     "expect_signal": "neg", "checks": [sig_check(0, 100, 100, 100000, True, "neg")]},
    {"id": "I1C3", "name": "负值 d (应夹断不崩)", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 10, "b": 10, "c": 10, "d": -5}},
     "expect_signal": "neg"},
    {"id": "I1C4", "name": "负值 a (应夹断不崩)", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": -3, "b": 10, "c": 10, "d": 100}},
     "expect_signal": "neg"},
    {"id": "I1C5", "name": "超大计数 (防溢出)", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 10**6, "b": 10**7, "c": 10**7, "d": 10**9}}},
    {"id": "I1C6", "name": "分数计数 (compute 收 float)", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 12.5, "b": 300.5, "c": 280.5, "d": 992000.5}}},
    {"id": "I1C7", "name": "不一致 a>b (有限不崩)", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 500, "b": 10, "c": 500, "d": 100000}}},
    {"id": "I1C8", "name": "全零格 (a=0 守卫)", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 0, "b": 0, "c": 0, "d": 0}},
     "expect_signal": "neg"},
    {"id": "I1C9", "name": "缺失药物 (counts=None)", "drug": "missing_xyz", "event": "PNEUMONITIS",
     "counts": {("missing_xyz", "PNEUMONITIS"): "MISSING"}},
    {"id": "I1C10", "name": "零细胞 + 关闭连续性", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 0, "b": 100, "c": 100, "d": 100000}},
     "continuity": False, "expect_signal": "neg"},
]

# ---- Iteration 2 : 事件 / SOC 映射 ------------------------------------------
ITERATIONS[2] = [
    {"id": "I2C1", "name": "未知 PT -> Unmapped", "event": "ZZZ UNKNOWN",
     "expect_soc": "Unmapped / 未归类"},
    {"id": "I2C2", "name": "小写 nausea -> GI", "event": "nausea",
     "expect_soc": "Gastrointestinal disorders"},
    {"id": "I2C3", "name": "空事件字符串 (走 top-events)", "event": ""},
    {"id": "I2C4", "name": "无事件 (top-events 渲染)", "event": None,
     "top_events": [{"term": "PNEUMONITIS"}, {"term": "DIARRHOEA"}, {"term": "DEATH"}]},
    {"id": "I2C5", "name": "CHEST PAIN -> Cardiac", "event": "CHEST PAIN",
     "expect_soc": "Cardiac disorders"},
    {"id": "I2C6", "name": "BACK PAIN -> Musculoskeletal", "event": "BACK PAIN",
     "expect_soc": "Musculoskeletal and connective tissue disorders"},
    {"id": "I2C7", "name": "KIDNEY INJURY -> Renal", "event": "KIDNEY INJURY",
     "expect_soc": "Renal and urinary disorders"},
    {"id": "I2C8", "name": "STOMACH PAIN 不误归 (Unmapped)", "event": "STOMACH PAIN",
     "checks": [("map_soc:STOMACH PAIN", lambda c: (
         __import__("disproportionality").map_soc("STOMACH PAIN")
         not in ("Gastrointestinal disorders",
                 "General disorders and administration site conditions")))]},
    {"id": "I2C9", "name": "ABDOMINAL PAIN -> GI", "event": "ABDOMINAL PAIN",
     "expect_soc": "Gastrointestinal disorders"},
    {"id": "I2C10", "name": "ANGINA -> Cardiac", "event": "ANGINA",
     "expect_soc": "Cardiac disorders"},
]

# ---- Iteration 3 : benchmark / compare / multi-event ------------------------
ITERATIONS[3] = [
    {"id": "I3C1", "name": "benchmark 正常", "event": "PNEUMONITIS",
     "benchmark_drugs": ["gefitinib", "erlotinib"]},
    {"id": "I3C2", "name": "benchmark 含缺失药 (显无可用数据)", "event": "PNEUMONITIS",
     "benchmark_drugs": ["gefitinib", "missing_b"],
     "counts": {("missing_b", "PNEUMONITIS"): "MISSING"},
     "checks": [("bench:无可用数据", lambda c: "无可用数据" in c["md"])]},
    {"id": "I3C3", "name": "compare 两药", "event": "PNEUMONITIS",
     "compare_drugs": ["osimertinib", "gefitinib"]},
    {"id": "I3C4", "name": "compare 单药 (跳过)", "event": "PNEUMONITIS",
     "compare_drugs": ["osimertinib"]},
    {"id": "I3C5", "name": "compare 无事件 (跳过)", "event": None,
     "compare_drugs": ["osimertinib", "gefitinib"]},
    {"id": "I3C6", "name": "multi-event top3", "event": None, "top_events_signal": 3,
     "top_events": [{"term": "PNEUMONITIS"}, {"term": "DIARRHOEA"}, {"term": "RASH"}]},
    {"id": "I3C7", "name": "multi-event 含 DEATH 过滤", "event": None, "top_events_signal": 4,
     "top_events": [{"term": "PNEUMONITIS"}, {"term": "DEATH"},
                    {"term": "DIARRHOEA"}, {"term": "RASH"}]},
    {"id": "I3C8", "name": "multi-event top0", "event": None, "top_events_signal": 0,
     "top_events": [{"term": "PNEUMONITIS"}]},
    {"id": "I3C9", "name": "benchmark+compare+multi 组合", "event": "PNEUMONITIS",
     "benchmark_drugs": ["gefitinib"], "compare_drugs": ["osimertinib", "erlotinib"],
     "top_events_signal": 2,
     "top_events": [{"term": "PNEUMONITIS"}, {"term": "DIARRHOEA"}]},
    {"id": "I3C10", "name": "multi-event 全终末词 (无可用数据)", "event": None,
     "top_events_signal": 3, "top_events": [{"term": "DEATH"}, {"term": "NEOPLASM"},
                                            {"term": "PROGRESSION"}],
     "checks": [("multi:无可用数据", lambda c: "无可用数据" in c["md"])]},
]

# ---- Iteration 4 : trend / 时间序列 -----------------------------------------
FLAT = [{"ym": "2024%02d" % m, "count": 6} for m in range(1, 13)]
SPIKE_LAST = FLAT[:-1] + [{"ym": "202412", "count": 60}]
SINGLE = [{"ym": "202401", "count": 5}]
ZEROS = [{"ym": "2024%02d" % m, "count": 0} for m in range(1, 13)]
ITERATIONS[4] = [
    {"id": "I4C1", "name": "trend 正常 (mock 含尖峰)", "event": "PNEUMONITIS", "trend": True},
    {"id": "I4C2", "name": "trend 无事件 (跳过)", "event": None, "trend": True},
    {"id": "I4C3", "name": "trend 平坦序列", "event": "PNEUMONITIS", "trend": True,
     "monthly": FLAT},
    {"id": "I4C4", "name": "trend 单点", "event": "PNEUMONITIS", "trend": True,
     "monthly": SINGLE},
    {"id": "I4C5", "name": "trend 全零", "event": "PNEUMONITIS", "trend": True,
     "monthly": ZEROS},
    {"id": "I4C6", "name": "trend 末季尖峰", "event": "PNEUMONITIS", "trend": True,
     "monthly": SPIKE_LAST},
    {"id": "I4C7", "name": "trend + fda-label", "event": "PNEUMONITIS", "trend": True,
     "with_fda_label": True},
    {"id": "I4C8", "name": "trend 平坦 + 评分", "event": "PNEUMONITIS", "trend": True,
     "monthly": FLAT, "with_fda_label": True, "with_cn_pv": True},
    {"id": "I4C9", "name": "trend + benchmark", "event": "PNEUMONITIS", "trend": True,
     "benchmark_drugs": ["gefitinib"]},
    {"id": "I4C10", "name": "trend + compare", "event": "PNEUMONITIS", "trend": True,
     "compare_drugs": ["osimertinib", "gefitinib"]},
]

# ---- Iteration 5 : 评分 / tier / label / cn-pv / control --------------------
ITERATIONS[5] = [
    {"id": "I5C1", "name": "fda-label labeled(PNEUMONITIS)", "event": "PNEUMONITIS",
     "with_fda_label": True,
     "checks": [("label:已收录", lambda c: "已收录" in c["md"])]},
    {"id": "I5C2", "name": "fda-label unlabeled(DIARRHOEA)", "event": "DIARRHOEA",
     "with_fda_label": True,
     "checks": [("label:未收录", lambda c: "未收录" in c["md"])]},
    {"id": "I5C3", "name": "fda-label unknown(空结果)", "event": "PNEUMONITIS",
     "with_fda_label": True, "label_empty": True,
     "checks": [("label:unknown", lambda c: "无法判断" in c["md"] or "unknown" in c["md"].lower())]},
    {"id": "I5C4", "name": "cn-pv 开启 (2 hits)", "event": "PNEUMONITIS",
     "with_cn_pv": True},
    {"id": "I5C5", "name": "cn-pv 关闭 (默认)", "event": "PNEUMONITIS"},
    {"id": "I5C6", "name": "阳性对照锚点 (cerivastatin/RABDOMYOLYSIS)",
     "drug": "cerivastatin", "event": "RABDOMYOLYSIS",
     "counts": {("cerivastatin", "RABDOMYOLYSIS"): {"a": 200, "b": 4800, "c": 3000, "d": 992000}}},
    {"id": "I5C7", "name": "阴性对照锚点 (paracetamol/RABDOMYOLYSIS)",
     "drug": "paracetamol", "event": "RABDOMYOLYSIS",
     "counts": {("paracetamol", "RABDOMYOLYSIS"): {"a": 5, "b": 4995, "c": 3000, "d": 992000}}},
    {"id": "I5C8", "name": "高分组合 (faers+cn+trend+label+control)",
     "drug": "cerivastatin", "event": "RABDOMYOLYSIS",
     "counts": {("cerivastatin", "RABDOMYOLYSIS"): {"a": 200, "b": 4800, "c": 3000, "d": 992000}},
     "with_cn_pv": True, "trend": True, "with_fda_label": True, "monthly": SPIKE_LAST},
    {"id": "I5C9", "name": "零信号 + cn-pv (低分 T4)", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 0, "b": 100, "c": 100, "d": 100000}},
     "with_cn_pv": True, "expect_signal": "neg"},
    {"id": "I5C10", "name": "label unknown + trend + cn-pv", "event": "PNEUMONITIS",
     "with_fda_label": True, "label_empty": True, "trend": True, "with_cn_pv": True,
     "monthly": SPIKE_LAST},
]

# ---- Iteration 6 : 对照验证 + 连续性 ----------------------------------------
ITERATIONS[6] = [
    {"id": "I6C1", "name": "validate-controls 全量", "validate": True},
    {"id": "I6C2", "name": "关闭连续性 (a=1 微小)", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 1, "b": 1, "c": 1, "d": 1}},
     "continuity": False},
    {"id": "I6C3", "name": "validate 含缺失对照 (不崩)", "validate": True,
     "counts": {("cerivastatin", "RABDOMYOLYSIS"): "MISSING"}},
    {"id": "I6C4", "name": "连续性 1/1/1/1 防 inf", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 1, "b": 1, "c": 1, "d": 1}},
     "continuity": True},
    {"id": "I6C5", "name": "零细胞 + 关连续性 (a==0 守卫)", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 0, "b": 10, "c": 10, "d": 10}},
     "continuity": False, "expect_signal": "neg"},
    {"id": "I6C6", "name": "validate 仅阴性组", "validate": True,
     "counts": {("cerivastatin", "RABDOMYOLYSIS"): "MISSING",
                ("troglitazone", "HEPATITIS"): "MISSING",
                ("rosiglitazone", "MYOCARDIAL INFARCTION"): "MISSING",
                ("leflunomide", "HEPATIC FAILURE"): "MISSING",
                ("fluoroquinolone", "TENDON RUPTURE"): "MISSING"}},
    {"id": "I6C7", "name": "validate 仅阳性组", "validate": True,
     "counts": {("paracetamol", "RABDOMYOLYSIS"): "MISSING",
                ("ibuprofen", "PNEUMONITIS"): "MISSING",
                ("amoxicillin", "MYOCARDIAL INFARCTION"): "MISSING",
                ("salbutamol", "HEPATIC FAILURE"): "MISSING"}},
    {"id": "I6C8", "name": "validate 阳性对照却无信号 (低一致率,不崩)", "validate": True,
     "counts": {("cerivastatin", "RABDOMYOLYSIS"): {"a": 1, "b": 4999, "c": 3000, "d": 992000}}},
    {"id": "I6C9", "name": "连续性 超大计数", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 10**6, "b": 10**7, "c": 10**7, "d": 10**9}}},
    {"id": "I6C10", "name": "benchmark + 关连续性", "event": "PNEUMONITIS",
     "benchmark_drugs": ["gefitinib"], "continuity": False},
]

# ---- Iteration 7 : CLI 参数组合 / 边界 --------------------------------------
ITERATIONS[7] = [
    {"id": "I7C1", "name": "全参数组合集成", "event": "PNEUMONITIS",
     "benchmark_drugs": ["gefitinib"], "compare_drugs": ["osimertinib", "erlotinib"],
     "top_events_signal": 2, "trend": True, "with_cn_pv": True, "with_fda_label": True,
     "case_level": 2, "monthly": SPIKE_LAST,
     "top_events": [{"term": "PNEUMONITIS"}, {"term": "DIARRHOEA"}]},
    {"id": "I7C2", "name": "top=1", "event": "PNEUMONITIS", "top": 1},
    {"id": "I7C3", "name": "自定义 field", "event": "PNEUMONITIS",
     "field": "patient.drug.openfda.pharm_class_epc"},
    {"id": "I7C4", "name": "date_from/to", "event": "PNEUMONITIS",
     "date_from": "20200101", "date_to": "20241231"},
    {"id": "I7C5", "name": "case_level=3", "event": "PNEUMONITIS", "case_level": 3},
    {"id": "I7C6", "name": "api_key 字符串 (mock忽略)", "event": "PNEUMONITIS",
     "api_key": "DUMMYKEY"},
    {"id": "I7C7", "name": "药物名尾空格", "drug": "osimertinib ", "event": "PNEUMONITIS",
     "counts": {("osimertinib ", "PNEUMONITIS"): {"a": 150, "b": 4850, "c": 3000, "d": 992000}}},
    {"id": "I7C8", "name": "benchmark 特殊字符药名", "event": "PNEUMONITIS",
     "benchmark_drugs": ["drug-a.b"]},
    {"id": "I7C9", "name": "compare 三参照", "event": "PNEUMONITIS",
     "compare_drugs": ["osimertinib", "gefitinib", "erlotinib"]},
    {"id": "I7C10", "name": "仅基础 (全默认)", "event": "PNEUMONITIS"},
]

# ---- Iteration 8 : case-level & 集成 ----------------------------------------
ITERATIONS[8] = [
    {"id": "I8C1", "name": "case_level=5", "event": "PNEUMONITIS", "case_level": 5},
    {"id": "I8C2", "name": "case_level=0", "event": "PNEUMONITIS", "case_level": 0},
    {"id": "I8C3", "name": "case_level 抓取失败 (优雅降级)", "event": "PNEUMONITIS",
     "case_level": 3, "case_error": True},
    {"id": "I8C4", "name": "全集成", "event": "PNEUMONITIS",
     "benchmark_drugs": ["gefitinib"], "compare_drugs": ["osimertinib", "erlotinib"],
     "top_events_signal": 2, "trend": True, "with_cn_pv": True, "with_fda_label": True,
     "case_level": 2, "monthly": SPIKE_LAST,
     "top_events": [{"term": "PNEUMONITIS"}, {"term": "DIARRHOEA"}]},
    {"id": "I8C5", "name": "集成 + 缺失药物 (降级)", "drug": "missing_xyz", "event": "PNEUMONITIS",
     "counts": {("missing_xyz", "PNEUMONITIS"): "MISSING"},
     "benchmark_drugs": ["gefitinib"], "case_level": 2},
    {"id": "I8C6", "name": "case_level + trend", "event": "PNEUMONITIS", "case_level": 2,
     "trend": True, "monthly": SPIKE_LAST},
    {"id": "I8C7", "name": "case_level + benchmark", "event": "PNEUMONITIS", "case_level": 2,
     "benchmark_drugs": ["gefitinib"]},
    {"id": "I8C8", "name": "case_level + multi", "event": None, "case_level": 2,
     "top_events_signal": 2, "top_events": [{"term": "PNEUMONITIS"}, {"term": "DIARRHOEA"}]},
    {"id": "I8C9", "name": "case_level + compare", "event": "PNEUMONITIS", "case_level": 2,
     "compare_drugs": ["osimertinib", "gefitinib"]},
    {"id": "I8C10", "name": "case_level + score + cn-pv", "event": "PNEUMONITIS",
     "case_level": 2, "with_cn_pv": True, "with_fda_label": True},
]

# ---- Iteration 9 : 对抗 / fuzz ----------------------------------------------
ITERATIONS[9] = [
    {"id": "I9C1", "name": "空药物名", "drug": "", "event": "PNEUMONITIS"},
    {"id": "I9C2", "name": "小写未知事件 (大小写无关+Unmapped)", "event": "zzzunknown",
     "expect_soc": "Unmapped / 未归类"},
    {"id": "I9C3", "name": "超大 a (1e12)", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 10**12, "b": 10**12, "c": 10**12, "d": 10**14}}},
    {"id": "I9C4", "name": "极小 a (1e-9)", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 1e-9, "b": 100, "c": 100, "d": 100000}}},
    {"id": "I9C5", "name": "负值 c", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 10, "b": 10, "c": -5, "d": 100}}},
    {"id": "I9C6", "name": "超长药物名", "drug": "a" * 200, "event": "PNEUMONITIS",
     "counts": {("a" * 200, "PNEUMONITIS"): {"a": 150, "b": 4850, "c": 3000, "d": 992000}}},
    {"id": "I9C7", "name": "超长事件名", "event": "A" * 200},
    {"id": "I9C8", "name": "负值 b", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 10, "b": -5, "c": 10, "d": 100}}},
    {"id": "I9C9", "name": "大负 d", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 10, "b": 10, "c": 10, "d": -100000}}},
    {"id": "I9C10", "name": "a 远超 b/c", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 9999, "b": 1, "c": 1, "d": 100000}}},
]

# ---- Iteration 10 : 已修复 bug 回归 -----------------------------------------
ITERATIONS[10] = [
    {"id": "I10C1", "name": "回归: 零细胞+连续性 (v0.1.12)", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": 0, "b": 100, "c": 100, "d": 100000}},
     "continuity": True, "expect_signal": "neg"},
    {"id": "I10C2", "name": "回归: 负值输入 (v0.1.13)", "drug": "x", "event": "PNEUMONITIS",
     "counts": {("x", "PNEUMONITIS"): {"a": -3, "b": 10, "c": 10, "d": 100}},
     "expect_signal": "neg"},
    {"id": "I10C3", "name": "回归: CN-PV max_per_column 非 int (v0.1.13)",
     "event": "PNEUMONITIS", "with_cn_pv": True,
     "cn_pv_override": {"max_per_column": "?"}},
    {"id": "I10C4", "name": "回归: benchmark 缺失药显无可用 (v0.1.13)", "event": "PNEUMONITIS",
     "benchmark_drugs": ["gefitinib", "missing_b"],
     "counts": {("missing_b", "PNEUMONITIS"): "MISSING"},
     "checks": [("bench:无可用数据", lambda c: "无可用数据" in c["md"])]},
    {"id": "I10C5", "name": "回归: CHEST PAIN->Cardiac (v0.1.14)", "event": "CHEST PAIN",
     "expect_soc": "Cardiac disorders"},
    {"id": "I10C6", "name": "回归: 阳性对照 controls 分量非零 (v0.1.14)",
     "drug": "cerivastatin", "event": "RABDOMYOLYSIS",
     "counts": {("cerivastatin", "RABDOMYOLYSIS"): {"a": 200, "b": 4800, "c": 3000, "d": 992000}}},
    {"id": "I10C7", "name": "回归: trend 平坦不崩 (v0.1.13)", "event": "PNEUMONITIS",
     "trend": True, "monthly": FLAT},
    {"id": "I10C8", "name": "回归: multi 全终末词 (v0.1.13)", "event": None,
     "top_events_signal": 3, "top_events": [{"term": "DEATH"}, {"term": "NEOPLASM"},
                                            {"term": "PROGRESSION"}],
     "checks": [("multi:无可用数据", lambda c: "无可用数据" in c["md"])]},
    {"id": "I10C9", "name": "回归: 评分恒 <=100", "drug": "cerivastatin", "event": "RABDOMYOLYSIS",
     "counts": {("cerivastatin", "RABDOMYOLYSIS"): {"a": 200, "b": 4800, "c": 3000, "d": 992000}},
     "with_cn_pv": True, "trend": True, "with_fda_label": True, "monthly": SPIKE_LAST,
     "checks": [("score<=100", lambda c: parse_score(c["md"]) is not None and
                 parse_score(c["md"]) <= 100)]},
    {"id": "I10C10", "name": "回归: 全集成不崩", "event": "PNEUMONITIS",
     "benchmark_drugs": ["gefitinib"], "compare_drugs": ["osimertinib", "erlotinib"],
     "top_events_signal": 2, "trend": True, "with_cn_pv": True, "with_fda_label": True,
     "case_level": 2, "monthly": SPIKE_LAST,
     "top_events": [{"term": "PNEUMONITIS"}, {"term": "DIARRHOEA"}]},
]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def run_iteration(it):
    cases = ITERATIONS[it]
    print("=" * 78)
    print("ITERATION %d  (%d cases)" % (it, len(cases)))
    print("=" * 78)
    n_ok = n_anom = n_crash = 0
    for case in cases:
        install_case_mocks(case)
        res = run_case(case)
        mark = {"OK": "✅", "ANOMALY": "⚠️", "CRASH": "❌"}.get(res["status"], "?")
        print("[%s] %-46s %s" % (mark, res["name"], res["status"]))
        if res["detail"]:
            print("       ↳ %s" % res["detail"])
        if res["status"] == "OK":
            n_ok += 1
        elif res["status"] == "ANOMALY":
            n_anom += 1
        else:
            n_crash += 1
    print("-" * 78)
    print("汇总: OK=%d  ANOMALY=%d  CRASH=%d" % (n_ok, n_anom, n_crash))
    return n_ok, n_anom, n_crash


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iter", default="1", help="1..10 或 all")
    ap.add_argument("--list", action="store_true", help="仅列出案例名")
    args = ap.parse_args()

    if args.list:
        for it in sorted(ITERATIONS):
            print("ITER %d:" % it)
            for c in ITERATIONS[it]:
                print("  %-8s %s" % (c["id"], c["name"]))
        return

    its = range(1, 11) if args.iter == "all" else [int(args.iter)]
    tot_ok = tot_anom = tot_crash = 0
    for it in its:
        ok, anom, crash = run_iteration(it)
        tot_ok += ok; tot_anom += anom; tot_crash += crash
    if args.iter == "all":
        print("=" * 78)
        print("ALL: OK=%d  ANOMALY=%d  CRASH=%d" % (tot_ok, tot_anom, tot_crash))


if __name__ == "__main__":
    main()
