#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_unit.py — pure-function regression tests for ct-safety v0.1.13.

Covers disproportionality.compute (incl. zero-cell / negative-cell guards),
BH-FDR, MedDRA PT->SOC mapping, control validation, Safety Signal Score tiers,
and FDA-label event check. No network.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import disproportionality as d
import signal_score as ss
import fetch_fda_label as fl


def test_compute_strong_signal():
    r = d.compute(150, 4850, 3000, 992000)
    assert r["ROR"]["value"] > 1 and r["signal_overall"] is True
    assert r["PRR"]["p_value"] >= 0 and r["PRR"]["p_value"] <= 1


def test_compute_zero_cell_null():
    # a==0 structural zero must NEVER signal, regardless of continuity.
    for cont in (False, True):
        r = d.compute(0, 100, 0, 100000, continuity=cont)
        assert r["signal_overall"] is False
        assert r["ROR"]["value"] == 0.0
        assert r["EBGM"]["value"] >= 0  # EBGM shrinks toward baseline, finite


def test_compute_negative_cell_guarded():
    # negative cell counts are invalid; must clamp to conservative null,
    # never raise OverflowError / produce NaN.
    r = d.compute(10, -5, 3000, 992000)
    assert r["signal_overall"] is False
    assert r["ROR"]["value"] == 0.0
    assert r["note"].startswith("negative")
    # all numeric fields finite
    for m in ("ROR", "PRR", "IC"):
        for k in ("value", "ci_low", "ci_high"):
            assert __import__("math").isfinite(r[m][k])


def test_compute_continuity_toggle():
    base = d.compute(150, 4850, 3000, 992000, continuity=False)
    corr = d.compute(150, 4850, 3000, 992000, continuity=True)
    # Haldane shifts the estimate only slightly on a non-sparse table
    assert abs(corr["ROR"]["value"] - base["ROR"]["value"]) < 0.05
    assert corr["raw_counts"] is not None and corr["continuity"] is True
    assert base["raw_counts"] is None and base["continuity"] is False


def test_prr_pvalue():
    import math
    p = d.prr_pvalue_from_chi2(4.0)
    assert 0 < p < 0.05
    assert d.prr_pvalue_from_chi2(0) == 1.0
    assert d.prr_pvalue_from_chi2(-1) == 1.0


def test_bh_fdr_canonical():
    q = d.benjamini_hochberg([0.001, 0.01, 0.02, 0.5, 0.7])
    exp = [0.005, 0.025, 1.0 / 30, 0.625, 0.7]
    assert len(q) == len(exp) and all(abs(a - b) < 1e-9 for a, b in zip(q, exp))


def test_bh_fdr_edge():
    assert d.benjamini_hochberg([]) == []
    assert d.benjamini_hochberg([0.03]) == [0.03]
    assert d.benjamini_hochberg([0.5, 0.5, 0.5]) == [0.5, 0.5, 0.5]
    # out-of-range p clamped to [0,1]; q-values stay within [0,1] and are
    # non-decreasing when sorted ascending; clamped extremes land correctly.
    q = d.benjamini_hochberg([0.001, 0.01, 0.02, 0.5, 0.7, -0.1, 2.0])
    assert len(q) == 7 and all(0.0 <= x <= 1.0 for x in q)
    sa = sorted(q)
    assert all(sa[i] <= sa[i + 1] for i in range(len(sa) - 1))
    assert sa[0] == 0.0 and sa[-1] == 1.0


def test_map_soc():
    assert d.map_soc("PNEUMONITIS").startswith("Respiratory")
    assert d.map_soc("NAUSEA") == "Gastrointestinal disorders"
    assert d.map_soc(None) == "Unmapped / 未归类"
    assert d.map_soc("ZZZ UNKNOWN TERM") == "Unmapped / 未归类"
    assert d.map_soc("nausea").startswith("Gastrointestinal")  # case-insensitive
    # v0.1.14: compound terms must NOT be hijacked by a generic single-word
    # fallback (e.g. "CHEST PAIN" -> Cardiac, not bare "PAIN" -> General).
    assert d.map_soc("CHEST PAIN") == "Cardiac disorders"
    assert d.map_soc("BACK PAIN").startswith("Musculoskeletal")
    assert d.map_soc("KIDNEY INJURY") == "Renal and urinary disorders"
    # a non-listed compound must not collapse onto a generic word bucket
    assert d.map_soc("STOMACH PAIN") != "Gastrointestinal disorders"


def test_control_validation_summary():
    recs = [
        {"drug": "a", "event": "x", "group": "positive", "expected": True, "signal": True},
        {"drug": "b", "event": "y", "group": "positive", "expected": True, "signal": False},
        {"drug": "c", "event": "z", "group": "negative", "expected": False, "signal": False},
        {"drug": "e", "event": "w", "group": "negative", "expected": False, "signal": True},
    ]
    s = d.summarize_control_validation(recs)
    assert s["positive"] == {"n": 2, "agree": 1, "rate": 0.5}
    assert s["negative"] == {"n": 2, "agree": 1, "rate": 0.5}
    assert s["n_total"] == 4


def test_signal_score_tiers():
    strong = d.compute(150, 4850, 3000, 992000)
    weak = d.compute(3, 9997, 300, 999000)

    s1 = ss.safety_signal_score(strong, fda_label_status="unlabeled",
                                cn_pv_hits=3, trend_flag=True)
    assert s1["tier"] == "T1" and s1["score"] >= 80

    s2 = ss.safety_signal_score(weak, fda_label_status="skipped",
                                cn_pv_hits=0, trend_flag=False)
    assert s2["tier"] == "T4" and s2["score"] < 40

    s3 = ss.safety_signal_score(strong, fda_label_status="skipped",
                                cn_pv_hits=1, trend_flag=False)
    assert s3["tier"] == "T2" and 60 <= s3["score"] < 80

    s4 = ss.safety_signal_score(strong, fda_label_status="labeled",
                                cn_pv_hits=0, trend_flag=False)
    assert s4["tier"] == "T3"
    # weights always sum to the cap domain (auditable)
    assert isinstance(s4["components"], dict)


def test_signal_score_control_pair():
    strong = d.compute(150, 4850, 3000, 992000)  # signal_overall True
    # positive control, expected True, pipeline agrees -> controls = 10, counts as source
    s = ss.safety_signal_score(strong, control_pair={"group": "positive",
                                                     "expected": True, "signal": True})
    assert s["components"]["controls"] == 10.0
    assert "控制验证" in s["corroborate_sources"]
    # positive control but pipeline misses (signal False) -> disagree -> controls 0
    s2 = ss.safety_signal_score(strong, control_pair={"group": "positive",
                                                      "expected": True, "signal": False})
    assert s2["components"]["controls"] == 0.0
    assert "控制验证" not in s2["corroborate_sources"]
    # no control info -> controls stays 0 (no silent inflation)
    s3 = ss.safety_signal_score(strong)
    assert s3["components"]["controls"] == 0.0


def test_check_event_three_states():
    labeled = {"n_results": 2, "adverse_reactions": ["pneumonitis and ILD"], "warnings": []}
    unlabeled = {"n_results": 1, "adverse_reactions": ["headache"], "warnings": []}
    unknown = {"n_results": 0}
    assert fl.check_event(labeled, "PNEUMONITIS")["status"] == "labeled"
    assert fl.check_event(unlabeled, "PNEUMONITIS")["status"] == "unlabeled"
    assert fl.check_event(unknown, "PNEUMONITIS")["status"] == "unknown"


def _dotenv_priority_case(mod):
    """Shared body for resolve_api_key priority tests.

    REGRESSION GUARD (v0.1.23): ``resolve_api_key(None)`` must fall back to the
    skill-root ``.env``. A previous build declared ``_DOTENV`` but never used it
    as the default, so ``if dotenv_path and ...`` short-circuited and the file
    was NEVER read on the default code path. The original test passed an
    explicit path and therefore missed the bug entirely.

    ``mod._DOTENV`` is temporarily repointed at a temp file, so the user's real
    ``.env`` (which may hold a live key) is never read, written, or deleted.
    """
    import shutil
    import tempfile

    orig_dotenv = mod._DOTENV
    orig_env = os.environ.pop("OPENFDA_API_KEY", None)
    tmpdir = tempfile.mkdtemp(prefix="ctsafety_env_")
    tmp_dotenv = os.path.join(tmpdir, ".env")
    with open(tmp_dotenv, "w", encoding="utf-8") as fh:
        fh.write("# comment line\n\nOPENFDA_API_KEY=FROMFILE\n")
    try:
        mod._DOTENV = tmp_dotenv
        # 1. default path (no dotenv_path arg) MUST read the skill-root .env
        assert mod.resolve_api_key(None) == "FROMFILE"
        # 2. CLI beats .env
        assert mod.resolve_api_key("FROMCLI") == "FROMCLI"
        # 3. env var beats .env; CLI still beats env var
        os.environ["OPENFDA_API_KEY"] = "FROMENV"
        assert mod.resolve_api_key(None) == "FROMENV"
        assert mod.resolve_api_key("FROMCLI") == "FROMCLI"
        os.environ.pop("OPENFDA_API_KEY", None)
        # 4. missing .env -> None (keyless anonymous access stays valid)
        mod._DOTENV = os.path.join(tmpdir, "nope.env")
        assert mod.resolve_api_key(None) is None
    finally:
        mod._DOTENV = orig_dotenv
        os.environ.pop("OPENFDA_API_KEY", None)
        if orig_env is not None:
            os.environ["OPENFDA_API_KEY"] = orig_env
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_resolve_api_key_priority_fda_label():
    _dotenv_priority_case(fl)


def test_resolve_api_key_priority_faers():
    import fetch_faers as ff
    _dotenv_priority_case(ff)
