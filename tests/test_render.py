#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_render.py — Markdown render-layer regression tests for ct-safety v0.1.13.

Focus: every _render_* must survive missing/None fields without crashing
(the CN-PV `%d` crash + benchmark "无可用数据" transparency were fixed in v0.1.13).
Also covers single-event report.render. No network.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import disproportionality as d
import signal_score as ss
import report as report_mod
import ct_safety as cs


def _strong_res():
    r = d.compute(150, 4850, 3000, 992000)
    r["drug"] = "osimertinib"
    r["event"] = "PNEUMONITIS"
    return r


def test_report_single_basic():
    md = report_mod.render(_strong_res())
    assert "ROR" in md and "PNEUMONITIS" in md and "SOC" in md


def test_report_cn_pv_missing_field_no_crash():
    # regression: CN-PV payload missing max_per_column must NOT crash the %d format.
    res = _strong_res()
    cn_missing = {"source": "CN-PV", "hit_count": 2, "hits": [
        {"title": "t", "column": "药物警戒快讯", "date": "2024-01-01",
         "url": "https://x", "snippet": "s", "matched_keywords": ["k"]}]}
    # max_per_column intentionally absent
    md = report_mod.render(res, cn_pv=cn_missing)
    assert "命中" in md


def test_report_cn_pv_empty():
    md = report_mod.render(_strong_res(), cn_pv={"hit_count": 0, "hits": []})
    assert "未命中" in md


def test_render_top_events_normal():
    data = {"drug_total": 5000,
            "top_events": [{"term": "PNEUMONITIS", "count": 150},
                           {"term": None}]}
    md = cs._render_top_events(data, "osimertinib")
    assert "Top adverse events" in md
    assert "Unmapped / 未归类" in md  # None term must not crash map_soc


def test_render_top_events_empty():
    md = cs._render_top_events({"drug_total": None, "top_events": []}, "x")
    assert "无数据" in md


def test_render_multi_event_mixed():
    avail = d.compute(150, 4850, 3000, 992000)
    avail["event"] = "PNEUMONITIS"; avail["available"] = True
    # unavailable rows (query-failed / skipped) are intentionally NOT rendered,
    # by design (unlike benchmark which shows "无可用数据"). Include one to prove
    # it does not crash and is silently dropped.
    multi = {"drug": "osimertinib",
             "events": [avail, {"event": "UNKNOWN_X", "available": False}]}
    md = cs._render_multi_event(multi)
    assert "多事件" in md and "PNEUMONITIS" in md  # UNKNOWN_X not shown by design


def test_render_benchmark_unavailable_shown():
    avail = d.compute(60, 4940, 3000, 992000)
    avail["drug"] = "gefitinib"; avail["available"] = True
    bench = {"event": "PNEUMONITIS",
             "benchmark": [avail, {"drug": "missing_xyz", "available": False}]}
    md = cs._render_benchmark(bench)
    assert "跨竞品" in md
    assert "无可用数据" in md  # transparency fix: unavailable competitor is shown


def test_render_compare_normal_and_error():
    agg = __import__("adjust_ror").adjusted_ror_aggregate(150, 5000, 60, 5000)
    cmp_ok = {"focal": "osimertinib", "event": "PNEUMONITIS", "focal_a": 150,
              "focal_n": 5000, "ref_drugs": [{"drug": "gefitinib", "a": 60, "n": 5000}],
              "aROR": agg}
    md = cs._render_compare(cmp_ok)
    assert "aROR" in md and "调整 ROR" in md
    md_err = cs._render_compare({"focal": "x", "event": "y", "error": "focal_no_counts"})
    assert "focal_no_counts" in md_err


def test_render_trend_present_and_empty():
    trend = {"drug": "o", "event": "P",
             "quarterly": [{"q": "2024Q1", "count": 12}],
             "detection": {"anomaly_flag": False}}
    md = cs._render_trend(trend)
    assert "时间趋势" in md and "2024Q1" in md
    md_empty = cs._render_trend({"drug": "o", "event": "P", "quarterly": [], "detection": {}})
    assert "无可用月度数据" in md_empty


def test_render_score_t1():
    score = ss.safety_signal_score(_strong_res(), fda_label_status="unlabeled",
                                    cn_pv_hits=3, trend_flag=True)
    md = cs._render_score(score, "unlabeled", "osimertinib", "PNEUMONITIS")
    assert "Safety Signal Score" in md and "T1" in md and "新信号" in md
