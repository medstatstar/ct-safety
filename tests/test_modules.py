#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_modules.py — module-level pure-function tests (time_series / adjust_ror / ebgm).
No network.
"""
import os
import sys
import math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from ebgm import ebgm as ebgm_fn
import time_series as ts
import adjust_ror as ar


def test_ebgm_basic():
    # strong signal: high co-occurrence relative to marginals -> EB05 >= 2 (signal)
    r = ebgm_fn(150, 4850, 3000, 992000)
    assert set(["value", "eb05", "eb95", "signal", "weights"]).issubset(r.keys())
    assert r["eb05"] >= 2.0 and r["signal"] is True
    for k in ("value", "eb05", "eb95"):
        assert math.isfinite(r[k])


def test_ebgm_zero_cell():
    r = ebgm_fn(0, 100, 0, 100000)
    assert r["value"] < 1.0 and r["signal"] is False  # shrinks to baseline


def test_to_quarterly():
    monthly = [{"ym": "202401", "count": 3}, {"ym": "202402", "count": 4},
               {"ym": "202403", "count": 5}, {"ym": "202404", "count": 2},
               {"ym": "202405", "count": 1}]
    q = ts.to_quarterly(monthly)
    assert q == [{"q": "2024Q1", "count": 12}, {"q": "2024Q2", "count": 3}]


def test_detect_anomaly_spike():
    spike = [5, 6, 5, 7, 6, 5, 8, 7, 6, 40, 42, 38, 45, 41, 39]
    det = ts.detect_anomaly(spike)
    assert det["anomaly_flag"] is True
    assert det["changepoint_idx"] is not None
    assert det["changepoint_lift"] is not None


def test_detect_anomaly_flat():
    flat = [10, 11, 9, 10, 12, 10, 9, 11, 10, 10, 11, 9, 10, 12, 11]
    det = ts.detect_anomaly(flat)
    assert det["anomaly_flag"] is False


def test_detect_anomaly_short():
    short = ts.detect_anomaly([1, 2, 3])
    assert short["anomaly_flag"] is False and short["note"]


def test_adjusted_ror_aggregate():
    agg = ar.adjusted_ror_aggregate(150, 10000, 300, 50000)
    assert agg["or"] > 1 and agg["signal"] is True
    assert agg["ci_low"] > 1  # clearly higher than reference


def test_adjusted_ror_sparse():
    sp = ar.adjusted_ror_aggregate(0, 10000, 300, 50000, continuity=True)
    assert sp["sparse"] is True
    assert sp["or"] > 0 and sp["or"] < 1e9 and math.isfinite(sp["or"])


def test_mantel_haenszel():
    # two strata each OR ~4.06 -> pooled ~4.06
    mh = ar.mantel_haenszel_or([(100, 4900, 50, 9950), (200, 9800, 100, 19900)])
    assert abs(mh["or_mh"] - 4.06) < 0.1 and mh["or_mh"] > 1


def test_logistic_irls_firth():
    X = [[1.0], [1.0], [0.0], [0.0], [1.0], [0.0]]
    y = [1, 1, 0, 0, 1, 0]
    b = ar.logistic_irls(X, y, add_intercept=False, firth=True)
    assert all(abs(v) < 50 for v in b)  # finite, Firth keeps it bounded
    aor = ar.adjusted_ror_from_logistic(b[0])
    assert aor["aor"] > 0  # aor is a dict {aor, beta}
