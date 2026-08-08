#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
report.py / 报告产出

Render a disproportionality result (from disproportionality.py) into a Markdown
report. Pure local; no network. / 本地渲染 Markdown 报告，不联网。
"""
import argparse
import json
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import disproportionality


def render(res, cn_pv=None):
    drug = res.get("drug", "?")
    event = res.get("event", "?")
    tbl = res["table"]
    ror = res["ROR"]; prr = res["PRR"]; ic = res["IC"]
    sig = "⚠️ 信号阳性" if res.get("signal_overall") else "无显著信号"

    lines = []
    lines.append("# FAERS 安全性信号分析 / FAERS Safety Signal\n")
    lines.append("- 药物 Drug: **%s**" % drug)
    lines.append("- 事件 Event (MedDRA PT): **%s**" % event)
    soc = disproportionality.map_soc(event) if event else "—"
    lines.append("- 系统器官分类 SOC: **%s**" % soc)
    lines.append("- 数据源 Source: FDA FAERS (openFDA public API)")
    cont = res.get("continuity")
    lines.append("- 连续性校正 Continuity: **%s**" % (
        "已启用 Haldane-Anscombe (+0.5/格)" if cont else "未启用（可用 --no-continuity 复现 v0.1.8）"))
    lines.append("- 总体判定 Overall: **%s**\n" % sig)

    lines.append("## 2×2 列联表 / Contingency Table\n")
    lines.append("| | 事件发生 Event | 事件未发生 No Event | 合计 |")
    lines.append("|---|---|---|---|")
    lines.append("| 用药 Drug | a=%d | b=%d | %d |" % (tbl["a"], tbl["b"], tbl["a"] + tbl["b"]))
    lines.append("| 未用药 No Drug | c=%d | d=%d | %d |" % (tbl["c"], tbl["d"], tbl["c"] + tbl["d"]))
    lines.append("| 合计 | %d | %d | N=%d |\n" % (tbl["a"] + tbl["c"], tbl["b"] + tbl["d"], tbl["N"]))

    lines.append("## 信号检测结果 / Disproportionality\n")
    lines.append("| 方法 Method | 估计值 Estimate | 95% CI | 信号 Signal |")
    lines.append("|---|---|---|---|")
    lines.append("| ROR | %.3f | %.3f – %.3f | %s |" % (
        ror["value"], ror["ci_low"], ror["ci_high"], "✅" if ror["signal"] else "—"))
    lines.append("| PRR | %.3f | %.3f – %.3f | %s (χ²=%.2f) |" % (
        prr["value"], prr["ci_low"], prr["ci_high"], "✅" if prr["signal"] else "—", prr["chi2"]))
    lines.append("| IC | %.3f | %.3f – %.3f | %s |" % (
        ic["value"], ic["ci_low"], ic["ci_high"], "✅" if ic["signal"] else "—"))
    eb = res.get("EBGM") or {"value": 0.0, "eb05": 0.0, "eb95": 0.0, "signal": False}
    lines.append("| EBGM (MGPS) | %.3f | %.3f – %.3f | %s |" % (
        eb["value"], eb["eb05"], eb["eb95"], "✅" if eb["signal"] else "—"))
    lines.append("")
    lines.append("> 信号判定：ROR 下限 >1；PRR ≥2 且 χ²≥4；IC 下限 >0；EBGM EB05 ≥ 2（FDA MGPS 标准）。任一阳性即提示该药物-事件组合报告频次高于基线。")
    lines.append("> 仅供信号筛查，非因果结论；监管提交须按 GCP / ICH E2 另行评估。")

    # ---- China official PV bulletins (qualitative corroboration only) ----
    lines.append("")
    lines.append("## 中国官方药物警戒通报 / China Official PV Bulletins (定性佐证 / Qualitative)\n")
    lines.append("> ⚠️ 来源：国家药品不良反应监测中心 (cdr-adr.org.cn) 公开栏目"
                 "（药物警戒快讯 / 数据报告 / 通知通告 / 器械·化妆品警戒快讯）。")
    lines.append("> 此为**定性叙事通报**，**非个案计数，不可做 disproportionality (PRR/ROR/IC) 分析**；"
                 "仅作上方 FAERS 量化信号的**定性佐证**。NMPA《药品不良反应信息通报》主站被 WAF 拦截，"
                 "未纳入；快讯已汇总国内外风险点名。")
    if cn_pv and cn_pv.get("hit_count"):
        hits = cn_pv["hits"]
        mc = cn_pv.get("max_per_column")
        mc_disp = mc if isinstance(mc, int) else "?"
        lines.append("")
        lines.append("命中 **%d** 条（在抓取的最新 %s 篇/栏目内）：\n"
                     % (cn_pv["hit_count"], mc_disp))
        lines.append("| 日期 Date | 栏目 Column | 标题 Title | 命中词 Kw | 链接 Link |")
        lines.append("|---|---|---|---|---|")
        for h in hits:
            title = h["title"].replace("|", "/")
            link = "[原文](%s)" % h["url"]
            lines.append("| %s | %s | %s | %s | %s |" % (
                h.get("date") or "-", h.get("column", "-"),
                title, ", ".join(h.get("matched_keywords", [])), link))
        lines.append("")
        lines.append("**摘要片段 / Snippets:**")
        for h in hits:
            lines.append("- 「%s」(%s, %s): %s" % (
                h["title"], h.get("column", "-"), h.get("date") or "-",
                h.get("snippet", "")[:160]))
    else:
        lines.append("")
        lines.append("未命中中国官方通报（在抓取的最新抽样内）。注意：此为**最新页抽样检索**而非全量库检索；"
                     "如需更广覆盖，可增大 `--cn-max`，或显式传入中文事件词 `--event-cn`。")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML rendering (default deliverable for browser preview)
# ---------------------------------------------------------------------------
def _esc(s):
    """Escape raw text so it is safe inside HTML."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(s):
    """Apply inline markdown (links, bold) after escaping."""
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    return s


def _split_row(s):
    s = s.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_sep(s):
    cells = _split_row(s)
    if not cells:
        return False
    return all(re.match(r'^:?-+:?$', c) for c in cells)


def _table_html(header, body):
    th = "".join("<th>%s</th>" % _inline(_esc(h)) for h in header)
    trs = []
    for row in body:
        tds = "".join("<td>%s</td>" % _inline(_esc(c)) for c in row)
        trs.append("<tr>%s</tr>" % tds)
    return ("<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>"
            % (th, "".join(trs)))


def md_to_html(md):
    """Convert the controlled Markdown subset produced by this skill to HTML.

    Handles: h1-h3, tables (with separator row), blockquotes, unordered lists,
    bold, and links. Good enough for our own report output; not a general MD parser.
    """
    lines = md.split("\n")
    out = []
    i, n = 0, len(lines)
    while i < n:
        stripped = lines[i].strip()
        # table block
        if stripped.startswith("|") and i + 1 < n and _is_sep(lines[i + 1].strip()):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i].strip()))
                i += 1
            data = [r for r in rows if not _is_sep("|".join(r))]
            if data:
                out.append(_table_html(data[0], data[1:]))
            continue
        # blockquote
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<blockquote>%s</blockquote>" % _inline(_esc(" ".join(buf))))
            continue
        # heading
        m = re.match(r'^(#{1,6})\s+(.*)$', stripped)
        if m:
            lvl = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (lvl, _inline(_esc(m.group(2))), lvl))
            i += 1
            continue
        # unordered list
        if re.match(r'^[-*]\s+', stripped):
            items = []
            while i < n and re.match(r'^[-*]\s+', lines[i].strip()):
                items.append(re.match(r'^[-*]\s+(.*)$', lines[i].strip()).group(1))
                i += 1
            out.append("<ul>" + "".join("<li>%s</li>" % _inline(_esc(it)) for it in items) + "</ul>")
            continue
        # blank line
        if stripped == "":
            i += 1
            continue
        # paragraph
        out.append("<p>%s</p>" % _inline(_esc(stripped)))
        i += 1
    return "\n".join(out)


def wrap_html(body, title="FAERS Safety Signal"):
    """Wrap rendered HTML body in a standalone, self-contained document."""
    css = (
        "body{font-family:-apple-system,Segoe UI,Roboto,'Helvetica Neue',"
        "Arial,'PingFang SC','Microsoft YaHei',sans-serif;max-width:900px;"
        "margin:24px auto;padding:0 16px;color:#1f2328;line-height:1.6;}"
        "h1{font-size:24px;border-bottom:2px solid #2b6cb0;padding-bottom:8px;color:#1a365d;}"
        "h2{font-size:20px;margin-top:28px;border-left:4px solid #2b6cb0;padding-left:10px;color:#1a365d;}"
        "h3{font-size:17px;margin-top:20px;color:#234e70;}"
        "table{border-collapse:collapse;width:100%;margin:14px 0;font-size:14px;}"
        "th,td{border:1px solid #d0d7de;padding:8px 10px;text-align:left;}"
        "th{background:#eef3f8;font-weight:600;}"
        "tbody tr:nth-child(even){background:#f6f8fa;}"
        "blockquote{border-left:4px solid #f0a500;background:#fff8e6;margin:14px 0;padding:10px 14px;color:#5c4b16;}"
        "ul{margin:10px 0;padding-left:22px;}li{margin:4px 0;}"
        "a{color:#2b6cb0;}code{background:#f0f0f0;padding:1px 5px;border-radius:4px;font-size:13px;}"
    )
    return ("<!doctype html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            "<title>%s</title>\n<style>%s</style>\n</head>\n<body>\n%s\n</body>\n</html>\n"
            % (title, css, body))


def main():
    ap = argparse.ArgumentParser(description="Render FAERS disproportionality report.")
    ap.add_argument("--in", dest="infile", required=True)
    ap.add_argument("--cn-pv", help="CN-PV JSON from fetch_cn_pv.py (qualitative corroboration)")
    ap.add_argument("--out", help="output Markdown path")
    ap.add_argument("--json-out", help="also dump full JSON")
    args = ap.parse_args()
    res = json.load(open(args.infile, encoding="utf-8"))
    cn_pv = None
    if args.cn_pv:
        cn_pv = json.load(open(args.cn_pv, encoding="utf-8"))
    md = render(res, cn_pv=cn_pv)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md)
        print("[OK] wrote", args.out)
    else:
        print(md)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
