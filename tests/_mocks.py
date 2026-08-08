#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
_mocks.py — offline network mocks for ct-safety regression tests.

Patches the fetch_* modules so `ct_safety.run` and its sub-runners never touch
the network. All counts are synthetic but internally consistent (a<=b/c/d,
d>=0) so every code path (2x2 build, FDR, SOC, render) exercises normally.

Pure stdlib. Import side effects: adds scripts/ to sys.path and imports the
fetch modules (which tolerate `requests` being absent via try/except).
"""
import json
import os
import sys

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import fetch_faers          # noqa: E402
import fetch_cn_pv          # noqa: E402
import fetch_fda_label      # noqa: E402
import time_series          # noqa: E402

# ---- synthetic data -------------------------------------------------------
# drug -> 2x2 counts + totals. None means "no FAERS data" (simulates a drug
# with zero reports / search miss).
COUNTS = {
    "osimertinib": {"a": 150, "b": 4850, "c": 3000, "d": 992000,
                    "drug_total": 5000, "grand_total": 1000000},
    "gefitinib":   {"a": 60, "b": 4940, "c": 3000, "d": 992000,
                    "drug_total": 5000, "grand_total": 1000000},
    "erlotinib":   {"a": 40, "b": 4960, "c": 3000, "d": 992000,
                    "drug_total": 5000, "grand_total": 1000000},
    "missing_xyz": None,
}

# top adverse events for the focal drug (R13 multi-event sweep)
TOP_EVENTS = {
    "osimertinib": {
        "counts": None,
        "drug_total": 5000,
        "grand_total": 1000000,
        "top_events": [
            {"term": "PNEUMONITIS"},
            {"term": "DIARRHOEA"},
            {"term": "RASH"},
            {"term": "DEATH"},  # terminal term -> filtered by _is_adverse_event
        ],
    },
}

MONTHLY = [
    {"ym": "202401", "count": 5}, {"ym": "202402", "count": 6},
    {"ym": "202403", "count": 5}, {"ym": "202404", "count": 7},
    {"ym": "202405", "count": 6}, {"ym": "202406", "count": 5},
    {"ym": "202407", "count": 8}, {"ym": "202408", "count": 7},
    {"ym": "202409", "count": 6}, {"ym": "202410", "count": 42},
    {"ym": "202411", "count": 40}, {"ym": "202412", "count": 38},
]


def fake_fetch_counts(drug, event, field, top, api_key, *, run, out,
                      date_from=None, date_to=None, timeout=None, retries=None):
    """Write a FAERS fetch JSON to `out` (mirrors the real writer) and return it."""
    if event is None:
        data = dict(TOP_EVENTS.get(
            drug, {"counts": None, "drug_total": 5000,
                   "grand_total": 1000000, "top_events": [{"term": "PNEUMONITIS"}]}))
    else:
        c = COUNTS.get(drug)
        if c is None:
            data = {"counts": None, "drug_total": None, "grand_total": None}
        else:
            data = {"counts": {"a": c["a"], "b": c["b"], "c": c["c"], "d": c["d"]},
                    "drug_total": c["drug_total"], "grand_total": c["grand_total"]}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def fake_query_total(search, api_key=None, timeout=None, retries=None):
    """R13 per-event total. Pair query (contains AND) -> a=150; event total -> 5000."""
    if " AND " in search:
        return 150          # a = drug&event co-count
    return 5000             # event_total (c = 5000-150 = 4850, d stays positive)


def fake_fetch_case_reports(drug, event, field, n=0, run=False, out=None,
                            date_from=None, date_to=None):
    data = {"cases": [{"caseid": "1", "reportnum": "US-1", "drugname": drug}] * max(n, 1)}
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f)
    return data


def fake_fetch_monthly_series(drug, event, field, api_key, date_from, date_to):
    return list(MONTHLY)


def fake_cn_pv_search(cn_drug, cn_en=None, event=None, terms=None, max_per=10,
                      run=False, out=None):
    hits = [
        {"title": "奥希替尼相关肺损伤风险通报", "column": "药物警戒快讯",
         "date": "2024-03-01", "url": "https://example.com/1",
         "snippet": "奥希替尼 肺部炎症 …", "matched_keywords": ["奥希替尼", "肺"]},
        {"title": "EGFR-TKI 不良反应汇总", "column": "数据报告",
         "date": "2024-01-15", "url": "https://example.com/2",
         "snippet": "皮疹 腹泻 …", "matched_keywords": ["皮疹"]},
    ]
    result = {
        "source": "CN-PV (cdr-adr.org.cn)",
        "note": "qualitative",
        "query": {"drug_zh": cn_drug, "drug_en": cn_en, "event": event, "terms": terms},
        "searched_columns": ["药物警戒快讯"],
        "max_per_column": max_per,
        "hit_count": len(hits),
        "hits": hits,
    }
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    return result


def fake_fetch_label(drug, api_key=None, run=False, out=None, limit=5,
                     timeout=120, retries=3):
    """Returns a label whose adverse_reactions DOES contain pneumonitis but
    NOT diarrhoea — so a PNEUMONITIS check -> labeled, DIARRHOEA -> unlabeled."""
    result = {
        "source": "FDA Label (openFDA drug/label.json)",
        "query": drug,
        "matched_drug_terms": [drug],
        "n_results": 2,
        "adverse_reactions": ["pneumonitis and interstitial lung disease", "rash", "diarrhea"],
        "warnings": ["Hepatotoxicity has been reported"],
    }
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    return result


_ORIG = {}


def install():
    """Patch all network-touching functions with offline fakes."""
    _ORIG["fc"] = fetch_faers.fetch_counts
    _ORIG["qt"] = fetch_faers.query_total
    _ORIG["fcr"] = fetch_faers.fetch_case_reports
    _ORIG["ts"] = time_series.fetch_monthly_series
    _ORIG["cn"] = fetch_cn_pv.search
    _ORIG["lab"] = fetch_fda_label.fetch_label
    fetch_faers.fetch_counts = fake_fetch_counts
    fetch_faers.query_total = fake_query_total
    fetch_faers.fetch_case_reports = fake_fetch_case_reports
    time_series.fetch_monthly_series = fake_fetch_monthly_series
    fetch_cn_pv.search = fake_cn_pv_search
    fetch_fda_label.fetch_label = fake_fetch_label


def uninstall():
    """Restore the original network functions."""
    if not _ORIG:
        return
    fetch_faers.fetch_counts = _ORIG["fc"]
    fetch_faers.query_total = _ORIG["qt"]
    fetch_faers.fetch_case_reports = _ORIG["fcr"]
    time_series.fetch_monthly_series = _ORIG["ts"]
    fetch_cn_pv.search = _ORIG["cn"]
    fetch_fda_label.fetch_label = _ORIG["lab"]
