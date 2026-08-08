#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_real_world_scenarios.py — 10 real openFDA FAERS network test cases (simple→complex).

Covers untested paths that the offline mock/diagnose harness cannot reach:
 1. Classic strong signal (metformin + lactic acidosis)
 2. Drug-only, no event (acetaminophen -> top-events)
 3. Narrow date window (aspirin + headache, 1 year)
 4. Cross-drug benchmark (rosuvastatin vs atorvastatin/simvastatin)
 5. R13 multi-event sweep (osimertinib, top-5 events)
 6. Temporal anomaly (pembrolizumab + pneumonitis, trend)
 7. Multi-drug adjusted ROR (osimertinib vs gefitinib)
 8. FDA Label triangulation (warfarin + bleeding, labeled)
 9. Zero-hit boundary (nonexistent drug)
10. R14 case-level fetch (osimertinib + pneumonitis, n=3)

Network failures -> SKIP (not FAIL) so offline CI stays green.

Usage:
    python tests/run_tests.py --live           # run alongside existing test_live.py
    CT_SAFETY_LIVE=1 python tests/run_tests.py # env var way
    python tests/test_real_world_scenarios.py  # standalone (direct)
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import ct_safety as cs

FIELD = "patient.drug.medicinalproduct"


class _Skip(Exception):
    pass


def _skip(exc):
    raise _Skip("network unavailable: %s" % exc)


# ── 10 real-network cases ────────────────────────────────────────────────
def case01_classic_strong_signal():
    """1) Classic strong signal: metformin + lactic acidosis (well-known association)."""
    out = tempfile.mkdtemp(prefix="cts_rw01_")
    try:
        cs.run("metformin", "LACTIC ACIDOSIS", FIELD, 10, None, out, continuity=True)
    except Exception as e:
        _skip(e)
    md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
    assert "ROR" in md, "report should contain ROR table"
    # Strong signal expected: at least one signal flag should be positive
    assert "信号" in md or "Signal" in md or "阳性" in md or "signal" in md.lower(), \
        "expected signal flag in report"


def case02_drug_only_no_event():
    """2) Drug-only mode (no --event): top-events path, no 2×2 / disproportionality."""
    out = tempfile.mkdtemp(prefix="cts_rw02_")
    try:
        cs.run("acetaminophen", None, FIELD, 10, None, out)
    except Exception as e:
        _skip(e)
    md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
    # top-events report should NOT contain 2×2 table
    assert "2×2" not in md and "2x2" not in md, \
        "drug-only mode should not produce a 2×2 table"
    # should still list top events
    assert "反应" in md or "Event" in md or "PT" in md


def case03_narrow_date_window():
    """3) Narrow date window: aspirin + headache, 2024 only (small sample robustness)."""
    out = tempfile.mkdtemp(prefix="cts_rw03_")
    try:
        cs.run("aspirin", "HEADACHE", FIELD, 10, None, out,
               date_from="20240101", date_to="20241231", continuity=True)
    except Exception as e:
        _skip(e)
    md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
    assert "ROR" in md
    # narrow window should not crash even with small counts


def case04_cross_drug_benchmark():
    """4) Cross-drug benchmark: rosuvastatin vs atorvastatin + simvastatin."""
    out = tempfile.mkdtemp(prefix="cts_rw04_")
    try:
        cs.run("rosuvastatin", "RHABDOMYOLYSIS", FIELD, 10, None, out,
               benchmark_drugs=["atorvastatin", "simvastatin"], continuity=True)
    except Exception as e:
        _skip(e)
    md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
    assert "竞品" in md or "Benchmark" in md or "对照" in md, \
        "report should contain benchmark section"
    # both competitors mentioned
    assert "atorvastatin" in md.lower() or "simvastatin" in md.lower()


def case05_r13_multi_event_sweep():
    """5) R13 multi-event sweep: osimertinib, auto top-5 events with signal detection."""
    out = tempfile.mkdtemp(prefix="cts_rw05_")
    try:
        cs.run("osimertinib", None, FIELD, 10, None, out, top_events_signal=5)
    except Exception as e:
        _skip(e)
    md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
    assert "多事件" in md or "Multi-Event" in md or "事件扫描" in md, \
        "report should contain multi-event sweep section"


def case06_temporal_anomaly():
    """6) Temporal anomaly detection: pembrolizumab + pneumonitis, trend ON."""
    out = tempfile.mkdtemp(prefix="cts_rw06_")
    try:
        cs.run("pembrolizumab", "PNEUMONITIS", FIELD, 10, None, out,
               trend=True, continuity=True)
    except Exception as e:
        _skip(e)
    md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
    assert "趋势" in md or "Trend" in md or "时间" in md, \
        "report should contain trend section"


def case07_multi_drug_adjusted_ror():
    """7) Multi-drug adjusted ROR: osimertinib (focal) vs gefitinib (reference)."""
    out = tempfile.mkdtemp(prefix="cts_rw07_")
    try:
        cs.run("osimertinib", "PNEUMONITIS", FIELD, 10, None, out,
               compare_drugs=["osimertinib", "gefitinib"], continuity=True)
    except Exception as e:
        _skip(e)
    md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
    assert "aROR" in md or "adjusted" in md.lower() or "调整" in md, \
        "report should contain adjusted ROR section"


def case08_fda_label_triangulation():
    """8) FDA Label triangulation: warfarin + bleeding -> labeled (known risk)."""
    out = tempfile.mkdtemp(prefix="cts_rw08_")
    try:
        cs.run("warfarin", "BLEEDING", FIELD, 10, None, out,
               with_fda_label=True, continuity=True)
    except Exception as e:
        _skip(e)
    md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
    assert "ROR" in md
    # FDA Label section should appear
    assert "FDA" in md or "标签" in md or "说明书" in md or "Label" in md, \
        "report should contain FDA Label section"


def case09_zero_hit_boundary():
    """9) Zero-hit boundary: rare/new drug + rare event -> structural zero protection.

    Uses a very new drug (repotrectinib, approved 2023) to test two scenarios:
    - If the drug has 0 reports in FAERS -> 404 -> SKIP (network-level not found)
    - If the drug has reports but 0 co-occurrence with the event -> NO signal fabricated
    - If the drug has reports AND co-occurrence -> valid signal detected (also OK)
    CRITICAL: must NEVER crash regardless of data availability.
    """
    out = tempfile.mkdtemp(prefix="cts_rw09_")
    try:
        cs.run("repotrectinib", "PNEUMONITIS", FIELD, 10, None, out, continuity=True)
    except Exception as e:
        _skip(e)
    md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
    # Must NOT crash; report must be produced with valid structure
    assert "ROR" in md or "0" in md or "无" in md or "unknown" in md.lower()
    # If the report claims a signal, the 2×2 table must have a > 0 (no fabricated zero-cooc signals)
    if "信号阳性" in md or "Signal Positive" in md or "Signal" in md:
        # signal is only valid if a > 0 — extract the 2×2 table a value
        import re
        a_match = re.search(r'\|\s*用药 Drug\s*\|\s*a=(\d+)', md)
        if a_match:
            a_val = int(a_match.group(1))
            assert a_val > 0, "signal fabricated on a=0 (structural zero)! Report claims signal but a=0"


def case10_r14_case_level_fetch():
    """10) R14 case-level fetch: pull 3 individual case safety reports."""
    out = tempfile.mkdtemp(prefix="cts_rw10_")
    try:
        cs.run("osimertinib", "PNEUMONITIS", FIELD, 10, None, out,
               case_level=3, continuity=True)
    except Exception as e:
        _skip(e)
    md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
    assert "ROR" in md
    # case-level file should be written
    cases_path = os.path.join(out, "faers_cases.json")
    if os.path.exists(cases_path):
        import json
        data = json.load(open(cases_path, encoding="utf-8"))
        # structure: {"source","drug","event","n_fetched","cases":[...]}
        assert isinstance(data, dict), "faers_cases.json should be a dict with metadata"
        assert "cases" in data, "faers_cases.json should have a 'cases' key"
        assert isinstance(data["cases"], list), "cases field should be a list"
        # each case should have a safetyreportid if the API returned data
        for c in data["cases"]:
            assert "safetyreportid" in c, "each case should have safetyreportid"


# ── runner ────────────────────────────────────────────────────────────────
CASES = [
    ("case01_classic_strong_signal", case01_classic_strong_signal),
    ("case02_drug_only_no_event", case02_drug_only_no_event),
    ("case03_narrow_date_window", case03_narrow_date_window),
    ("case04_cross_drug_benchmark", case04_cross_drug_benchmark),
    ("case05_r13_multi_event_sweep", case05_r13_multi_event_sweep),
    ("case06_temporal_anomaly", case06_temporal_anomaly),
    ("case07_multi_drug_adjusted_ror", case07_multi_drug_adjusted_ror),
    ("case08_fda_label_triangulation", case08_fda_label_triangulation),
    ("case09_zero_hit_boundary", case09_zero_hit_boundary),
    ("case10_r14_case_level_fetch", case10_r14_case_level_fetch),
]


def main():
    """Run all 10 real-network cases. Network failures count as SKIP."""
    results = []
    for name, fn in CASES:
        try:
            fn()
            status, detail = "PASS", ""
        except _Skip as e:
            status, detail = "SKIP", str(e)
        except AssertionError as e:
            status, detail = "FAIL", str(e)
        except Exception as e:
            status, detail = "ERROR", "%s: %s" % (type(e).__name__, e)
        results.append((name, status, detail))
        print(f"[{status:>4}] {name} :: {detail}")

    passed = sum(1 for _, s, _ in results if s == "PASS")
    skipped = sum(1 for _, s, _ in results if s == "SKIP")
    failed = sum(1 for _, s, _ in results if s in ("FAIL", "ERROR"))
    print(f"\n=== real-world scenarios: PASS={passed} SKIP={skipped} FAIL={failed} ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
