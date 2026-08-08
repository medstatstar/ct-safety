#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
report_xlsx.py / 信号分析数据工作簿

Build the FAERS signal-analysis .xlsx companion workbook (xlsxwriter).
This is one of the TWO core deliverables (alongside faers_report.html):
it holds ALL raw information — FAERS counts, the 2x2 table, the four
disproportionality measures, supporting sources (FDA Label / CN-PV) and the
composite score — so every number can be audited. Pure local; no network.

Usage (inside ct_safety.py):
    import report_xlsx
    report_xlsx.build_signal_xlsx(out_path, drug=drug, event=event,
                                  fetch_data=data, disp_res=res,
                                  cn_pv=cn_pv, label_data=label_data,
                                  label_status=label_status, score_res=score_res)
"""
import os
import sys
import json

import xlsxwriter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import disproportionality


def _soc(event):
    try:
        return disproportionality.map_soc(event) if event else "—"
    except Exception:
        return "—"


def build_signal_xlsx(out_path, *, drug, event, fetch_data, disp_res=None,
                      cn_pv=None, label_data=None, label_status=None,
                      score_res=None):
    wb = xlsxwriter.Workbook(out_path, {"in_memory": True})

    f_title = wb.add_format({"bold": True, "font_size": 15, "font_color": "#1a365d"})
    f_h2 = wb.add_format({"bold": True, "font_size": 12, "font_color": "#1a365d",
                          "bottom": 1, "border_color": "#2b6cb0"})
    f_hdr = wb.add_format({"bold": True, "bg_color": "#eef3f8", "border": 1,
                           "text_wrap": True, "valign": "top"})
    f_cell = wb.add_format({"border": 1, "text_wrap": True, "valign": "top"})
    f_bold = wb.add_format({"bold": True, "border": 1, "valign": "top"})
    f_wrap = wb.add_format({"text_wrap": True, "valign": "top"})
    f_sig = wb.add_format({"border": 1, "bold": True, "font_color": "#b00020"})

    # ---------------- README ----------------
    ws = wb.add_worksheet("README")
    ws.set_column(0, 0, 110)
    ws.write(0, 0, "FAERS 安全性信号分析 — 数据工作簿 / FAERS Safety Signal Workbook", f_title)
    readme = [
        "",
        "本工作簿是信号分析的【核心交付物之一】，与 faers_report.html 配套：",
        "  ① faers_report.html — 可视化报告（结论与图表，便于快速阅读）",
        "  ② faers_report.xlsx — 本文件，含全部原始信息与计算明细，供逐条查阅 / 审计",
        "",
        "各工作表说明 / Sheets:",
        "  • Summary      — 2×2 列联表 + 四种信号检测方法（ROR / PRR / IC / EBGM）结果",
        "  • Raw_Counts   — FAERS 底层计数（a/b/c/d、各合计、药物/事件总量、Top 不良反应）",
        "  • FDA_Label    — FDA 说明书相关警示 / 不良反应（仅 --with-fda-label 时填充）",
        "  • CN_PV        — 中国官方药物警戒通报命中（仅 --with-cn-pv 时填充）",
        "  • Score        — 综合安全信号评分分量（仅 --with-fda-label 时填充）",
        "",
        "数据来源 / Source: FDA FAERS (openFDA public REST API)，全部为公开不良事件报告，",
        "零保密输入（B 档：普通输入 + 对外检索）。信号仅用于筛查，非因果结论；",
        "监管提交须按 GCP / ICH E2 另行评估。",
    ]
    for i, line in enumerate(readme, start=2):
        ws.write(i, 0, line, f_wrap)

    # ---------------- Summary ----------------
    ws = wb.add_worksheet("Summary")
    ws.set_column(0, 0, 34)
    ws.set_column(1, 4, 22)
    r = 0
    ws.write(r, 0, "核心结果 / Summary", f_title); r += 2
    meta = [
        ("药物 Drug", drug),
        ("事件 Event (MedDRA PT)", event),
        ("系统器官分类 SOC", _soc(event)),
        ("数据源 Source", "FDA FAERS (openFDA)"),
        ("连续性校正 Continuity", "已启用 Haldane-Anscombe (+0.5/格)" if (disp_res or {}).get("continuity") else "未启用"),
        ("总体判定 Overall", "⚠️ 信号阳性 (signal positive)" if (disp_res or {}).get("signal_overall") else "无显著信号 (no signal)"),
    ]
    for k, v in meta:
        ws.write(r, 0, k, f_bold); ws.write(r, 1, v, f_cell); r += 1
    r += 1
    ws.write(r, 0, "2×2 列联表 / Contingency Table", f_h2); r += 1
    ws.write_row(r, 0, ["", "事件发生 Event", "事件未发生 No Event", "合计"], f_hdr); r += 1
    cnt = (fetch_data or {}).get("counts") or {}
    a, b, c, d = cnt.get("a"), cnt.get("b"), cnt.get("c"), cnt.get("d")
    if a is not None:
        ws.write(r, 0, "用药 Drug", f_bold)
        ws.write(r, 1, a, f_cell); ws.write(r, 2, b, f_cell); ws.write(r, 3, (a or 0) + (b or 0), f_cell); r += 1
        ws.write(r, 0, "未用药 No Drug", f_bold)
        ws.write(r, 1, c, f_cell); ws.write(r, 2, d, f_cell); ws.write(r, 3, (c or 0) + (d or 0), f_cell); r += 1
        ws.write(r, 0, "合计", f_bold)
        ws.write(r, 1, (a or 0) + (c or 0), f_cell); ws.write(r, 2, (b or 0) + (d or 0), f_cell)
        ws.write(r, 3, (a or 0) + (b or 0) + (c or 0) + (d or 0), f_cell); r += 1
    r += 1
    ws.write(r, 0, "信号检测 / Disproportionality", f_h2); r += 1
    ws.write_row(r, 0, ["方法 Method", "估计值 Estimate", "95% CI", "信号 Signal"], f_hdr); r += 1
    if disp_res:
        for name, key in (("ROR", "ROR"), ("PRR", "PRR"), ("IC", "IC"), ("EBGM (MGPS)", "EBGM")):
            m = disp_res.get(key) or {}
            lo, hi = m.get("ci_low"), m.get("ci_high")
            ci = "%.3f – %.3f" % (lo, hi) if lo is not None else "—"
            sig = "✅" if m.get("signal") else "—"
            if name == "PRR" and m.get("chi2") is not None:
                sig += " (χ²=%.2f)" % m["chi2"]
            ws.write(r, 0, name, f_bold)
            ws.write(r, 1, "%.3f" % m["value"], f_cell)
            ws.write(r, 2, ci, f_cell)
            ws.write(r, 3, sig, f_sig if m.get("signal") else f_cell)
            r += 1
    r += 1
    ws.write(r, 0, "信号判定 / Criteria: ROR 下限>1；PRR≥2 且 χ²≥4；IC 下限>0；EBGM EB05≥2。仅供筛查，非因果结论。", f_wrap)

    # ---------------- Raw_Counts ----------------
    ws = wb.add_worksheet("Raw_Counts")
    ws.set_column(0, 0, 38); ws.set_column(1, 1, 80)
    r = 0
    ws.write(r, 0, "FAERS 原始计数 / Raw Counts", f_title); r += 2
    fd = fetch_data or {}
    meta_rows = [
        ("source", fd.get("source")),
        ("api", fd.get("api")),
        ("drug", fd.get("drug")),
        ("field", fd.get("field")),
        ("date_from", fd.get("date_from")),
        ("date_to", fd.get("date_to")),
        ("drug_total (reports mentioning drug)", fd.get("drug_total")),
        ("event_total (reports mentioning event)", fd.get("event_total")),
        ("grand_total (all FAERS reports)", fd.get("grand_total")),
    ]
    for k, v in meta_rows:
        ws.write(r, 0, k, f_bold); ws.write(r, 1, "" if v is None else str(v), f_cell); r += 1
    r += 1
    ws.write(r, 0, "2×2 原始计数 (未校正) / Raw 2x2", f_h2); r += 1
    ws.write_row(r, 0, ["cell", "value"], f_hdr); r += 1
    for kk in ("a", "b", "c", "d"):
        ws.write(r, 0, kk, f_bold); ws.write(r, 1, cnt.get(kk), f_cell); r += 1
    rc = (disp_res or {}).get("raw_counts")
    if rc:
        r += 1
        ws.write(r, 0, "原始计数 (disproportionality 输入) / raw_counts", f_h2); r += 1
        ws.write_row(r, 0, ["cell", "value"], f_hdr); r += 1
        for kk in ("a", "b", "c", "d"):
            ws.write(r, 0, kk, f_bold); ws.write(r, 1, rc.get(kk), f_cell); r += 1
    te = fd.get("top_events")
    if te:
        r += 1
        ws.write(r, 0, "Top 不良反应 (该药) / Top adverse events", f_h2); r += 1
        ws.write_row(r, 0, ["事件 Event", "报告数 Count"], f_hdr); r += 1
        if isinstance(te, list):
            for it in te:
                if isinstance(it, (list, tuple)) and len(it) == 2:
                    ws.write(r, 0, str(it[0]), f_cell); ws.write(r, 1, it[1], f_cell)
                else:
                    ws.write(r, 0, str(it), f_cell)
                r += 1
        elif isinstance(te, dict):
            for kk, vv in te.items():
                ws.write(r, 0, str(kk), f_cell); ws.write(r, 1, vv, f_cell); r += 1

    # ---------------- FDA_Label ----------------
    if label_data is not None:
        ws = wb.add_worksheet("FDA_Label")
        ws.set_column(0, 0, 30); ws.set_column(1, 1, 110)
        r = 0
        ws.write(r, 0, "FDA 说明书 / FDA Label", f_title); r += 1
        ws.write(r, 0, "标签状态 Label status", f_bold)
        ws.write(r, 1, label_status or "—", f_cell); r += 2
        matched = label_data.get("matched_drug_terms")
        if matched:
            ws.write(r, 0, "匹配药品词 Matched terms", f_bold)
            ws.write(r, 1, ", ".join(matched), f_cell); r += 2
        ev = (event or "").upper()

        def _sheet_block(title, items):
            nonlocal r
            ws.write(r, 0, title, f_h2); r += 1
            ws.write_row(r, 0, ["#", "内容 Content"], f_hdr); r += 1
            items = items or []
            if ev:
                hit = [x for x in items if ev in str(x).upper()]
                if hit:
                    items = hit
            for i, it in enumerate(items[:50], 1):
                ws.write(r, 0, i, f_cell); ws.write(r, 1, str(it), f_cell); r += 1
            r += 1

        _sheet_block("WARNINGS", label_data.get("warnings"))
        _sheet_block("ADVERSE_REACTIONS", label_data.get("adverse_reactions"))

    # ---------------- CN_PV ----------------
    if cn_pv and cn_pv.get("hit_count"):
        ws = wb.add_worksheet("CN_PV")
        widths = [14, 18, 60, 18, 40]
        for i, w in enumerate(widths):
            ws.set_column(i, i, w)
        ws.write(0, 0, "中国官方药物警戒通报 / CN PV Bulletins", f_title)
        ws.write_row(1, 0, ["日期 Date", "栏目 Column", "标题 Title", "命中词 Kw", "链接 Link"], f_hdr)
        rr = 2
        for h in cn_pv["hits"]:
            ws.write(rr, 0, h.get("date") or "-", f_cell)
            ws.write(rr, 1, h.get("column", "-"), f_cell)
            ws.write(rr, 2, h.get("title", "").replace("|", "/"), f_cell)
            ws.write(rr, 3, ", ".join(h.get("matched_keywords", [])), f_cell)
            ws.write(rr, 4, h.get("url", ""), f_cell)
            rr += 1

    # ---------------- Score ----------------
    if score_res is not None:
        ws = wb.add_worksheet("Score")
        ws.set_column(0, 0, 42); ws.set_column(1, 1, 18)
        r = 0
        ws.write(r, 0, "综合安全信号评分 / Safety Signal Score", f_title); r += 2
        ws.write(r, 0, "总分 Score (0-100)", f_bold); ws.write(r, 1, score_res.get("score"), f_cell); r += 1
        tier = score_res.get("tier") or score_res.get("evidence_tier")
        ws.write(r, 0, "证据分级 Tier", f_bold); ws.write(r, 1, tier, f_cell); r += 1
        comp = score_res.get("components") or score_res.get("breakdown")
        if comp:
            r += 1
            ws.write(r, 0, "评分分量 / Components", f_h2); r += 1
            ws.write_row(r, 0, ["分量 Component", "得分 Points"], f_hdr); r += 1
            for kk, vv in comp.items():
                ws.write(r, 0, str(kk), f_cell); ws.write(r, 1, vv, f_cell); r += 1
        rationale = score_res.get("rationale")
        if rationale:
            r += 1
            ws.write(r, 0, "理由 Rationale", f_bold); ws.write(r, 1, rationale, f_cell)

    wb.close()
    return out_path


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build FAERS signal-analysis .xlsx from cached JSON.")
    ap.add_argument("--fetch", required=True, help="faers_fetch.json")
    ap.add_argument("--disp", help="disproportionality.json")
    ap.add_argument("--label", help="fda_label.json")
    ap.add_argument("--cn-pv", help="cn_pv.json")
    ap.add_argument("--score", help="score json (optional)")
    ap.add_argument("--drug", default="?")
    ap.add_argument("--event", default="?")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    data = json.load(open(args.fetch, encoding="utf-8")) if args.fetch else {}
    disp = json.load(open(args.disp, encoding="utf-8")) if args.disp else None
    label = json.load(open(args.label, encoding="utf-8")) if args.label else None
    cn = json.load(open(args.cn_pv, encoding="utf-8")) if args.cn_pv else None
    score = json.load(open(args.score, encoding="utf-8")) if args.score else None
    build_signal_xlsx(args.out, drug=args.drug, event=args.event,
                      fetch_data=data, disp_res=disp, cn_pv=cn,
                      label_data=label, score_res=score)
    print("[OK] wrote", args.out)
