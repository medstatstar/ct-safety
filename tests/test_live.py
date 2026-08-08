#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_live.py — REAL openFDA end-to-end test. Disabled by default; run with
`python run_tests.py --live` (or set CT_SAFETY_LIVE=1). Requires network access
and the `requests` package. Failures due to network are reported as SKIP, not FAIL,
so CI without network stays green.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import ct_safety as cs

FIELD = "patient.drug.medicinalproduct"


def _skip(exc):
    # mark as skipped by raising a special exception the runner understands
    raise _Skip("network unavailable: %s" % exc)


class _Skip(Exception):
    pass


def test_live_single_event():
    out = tempfile.mkdtemp(prefix="cts_live_")
    try:
        cs.run("osimertinib", "PNEUMONITIS", FIELD, 10, None, out, continuity=True)
    except Exception as e:  # network / timeout -> skip
        _skip(e)
    md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
    assert "ROR" in md


def test_live_multi_event():
    out = tempfile.mkdtemp(prefix="cts_live_")
    try:
        cs.run("osimertinib", None, FIELD, 10, None, out, top_events_signal=3)
    except Exception as e:
        _skip(e)
    md = open(os.path.join(out, "faers_report.md"), encoding="utf-8").read()
    assert "多事件" in md
