#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_run_integration.py — `ct_safety.run` end-to-end (offline, mocked network).

Every branch of `run` is exercised with synthetic FAERS data so a future
regression in data assembly / render fails loudly. Network is fully mocked via
tests/_mocks.py.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))

import ct_safety as cs
from _mocks import install, uninstall

FIELD = "patient.drug.medicinalproduct"


def _tmp():
    return tempfile.mkdtemp(prefix="cts_test_")


def test_run_single_event():
    out = _tmp()
    try:
        install()
        cs.run("osimertinib", "PNEUMONITIS", FIELD, 10, None, out,
               continuity=True)
        md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
        assert "ROR" in md and "PNEUMONITIS" in md
    finally:
        uninstall()


def test_run_top_events_only():
    out = _tmp()
    try:
        install()
        cs.run("osimertinib", None, FIELD, 10, None, out)
        md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
        assert "Top adverse events" in md
    finally:
        uninstall()


def test_run_with_cn_pv():
    out = _tmp()
    try:
        install()
        cs.run("osimertinib", "PNEUMONITIS", FIELD, 10, None, out,
               with_cn_pv=True)
        md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
        assert "中国官方药物警戒通报" in md  # CN-PV section rendered
    finally:
        uninstall()


def test_run_benchmark_with_unavailable():
    out = _tmp()
    try:
        install()
        cs.run("osimertinib", "PNEUMONITIS", FIELD, 10, None, out,
               benchmark_drugs=["gefitinib", "missing_xyz"])
        md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
        assert "跨竞品" in md and "无可用数据" in md  # unavailable competitor shown
    finally:
        uninstall()


def test_run_multi_event():
    out = _tmp()
    try:
        install()
        cs.run("osimertinib", None, FIELD, 10, None, out, top_events_signal=3)
        md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
        assert "多事件" in md and "PNEUMONITIS" in md
    finally:
        uninstall()


def test_run_trend():
    out = _tmp()
    try:
        install()
        cs.run("osimertinib", "PNEUMONITIS", FIELD, 10, None, out, trend=True)
        md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
        assert "时间趋势" in md
    finally:
        uninstall()


def test_run_compare():
    out = _tmp()
    try:
        install()
        cs.run("osimertinib", "PNEUMONITIS", FIELD, 10, None, out,
               compare_drugs=["osimertinib", "gefitinib"])
        md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
        assert "aROR" in md and "调整 ROR" in md
    finally:
        uninstall()


def test_run_with_fda_label():
    out = _tmp()
    try:
        install()
        cs.run("osimertinib", "PNEUMONITIS", FIELD, 10, None, out,
               with_fda_label=True)
        md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
        assert "Safety Signal Score" in md and "已收录" in md  # mock label has pneumonitis
    finally:
        uninstall()


def test_run_case_level():
    out = _tmp()
    try:
        install()
        cs.run("osimertinib", "PNEUMONITIS", FIELD, 10, None, out, case_level=2)
        assert os.path.exists(os.path.join(out, "faers_cases.json"))
    finally:
        uninstall()


def test_run_full_combo():
    out = _tmp()
    try:
        install()
        cs.run("osimertinib", "PNEUMONITIS", FIELD, 10, None, out,
               with_cn_pv=True, benchmark_drugs=["gefitinib", "missing_xyz"],
               top_events_signal=3, trend=True,
               compare_drugs=["osimertinib", "gefitinib"], with_fda_label=True,
               case_level=1)
        md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
        for section in ("ROR", "中国官方药物警戒通报", "跨竞品", "多事件",
                        "时间趋势", "aROR", "Safety Signal Score"):
            assert section in md, "missing section: %s" % section
    finally:
        uninstall()
