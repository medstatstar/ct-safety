#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_obf_key_and_signal.py — regression tests for ct-safety v0.1.29.

Covers the v0.1.29 private-credential hardening (ct-base §5):
  - _deobfuscate() three branches: `obf:` blob decode / plaintext passthrough / empty
  - cross-module OBF_KEY consistency (fetch_faers vs fetch_fda_label)
  - resolve_api_key() reads an `obf:`-prefixed .env value end-to-end
  - resolve_api_key() still reads a plaintext .env value (backward compatible)
Plus a known strong-signal 2x2 table (osimertinib + pneumonitis) where all four
disproportionality measures must flag.

No network. Pure stdlib + scripts/.
"""
import base64
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import fetch_faers as ff
import fetch_fda_label as fl
import disproportionality as d


def _make_obf(plain):
    """Mirror resolve_api_key's encoder so the test is self-contained."""
    return "obf:" + base64.b64encode(
        bytes(c ^ ff._OBF_KEY[i % len(ff._OBF_KEY)] for i, c in enumerate(plain.encode()))
    ).decode()


# ---- _deobfuscate three branches ------------------------------------------

def test_obf_decode():
    k = "test-openfda-key-123"
    obf = _make_obf(k)
    assert obf.startswith("obf:")
    assert ff._deobfuscate(obf) == k
    assert fl._deobfuscate(obf) == k


def test_plaintext_passthrough():
    k = "test-openfda-key-123"
    # A non-obf: value (plaintext key) must pass through unchanged.
    assert ff._deobfuscate(k) == k
    assert fl._deobfuscate(k) == k


def test_empty_key():
    # Empty string is not an obf blob; must return as-is (never raise).
    assert ff._deobfuscate("") == ""
    assert fl._deobfuscate("") == ""


def test_obf_key_cross_module_consistent():
    # Both fetch scripts must share the same XOR key, or a blob written by one
    # cannot be decoded by the other.
    assert ff._OBF_KEY == fl._OBF_KEY


# ---- resolve_api_key end-to-end -------------------------------------------

def test_resolve_api_key_reads_obf_dotenv():
    plain = "test-openfda-key-123"
    obf = _make_obf(plain)
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8") as tf:
        tf.write("OPENFDA_API_KEY=%s\n" % obf)
        path = tf.name
    try:
        got = ff.resolve_api_key(None, dotenv_path=path)
        assert got == plain, got
    finally:
        os.unlink(path)


def test_resolve_api_key_reads_plaintext_dotenv():
    plain = "test-openfda-key-123"
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8") as tf:
        tf.write("OPENFDA_API_KEY=%s\n" % plain)
        path = tf.name
    try:
        # Backward compatible: pre-v0.1.29 plaintext .env still works.
        assert ff.resolve_api_key(None, dotenv_path=path) == plain
    finally:
        os.unlink(path)


def test_resolve_api_key_cli_wins():
    # CLI --api-key always takes priority over any .env (plaintext or obf).
    plain = "cli-key-wins-456"
    obf = _make_obf("dotenv-key-789")
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8") as tf:
        tf.write("OPENFDA_API_KEY=%s\n" % obf)
        path = tf.name
    try:
        assert ff.resolve_api_key(plain, dotenv_path=path) == plain
    finally:
        os.unlink(path)


# ---- known strong signal (EGFR-TKI class; osimertinib + pneumonitis) ------

def test_known_strong_signal_osimertinib_pneumonitis():
    # 2x2 from _mocks.COUNTS: a=150, b=4850, c=3000, d=992000.
    # Osimertinib is a well-documented interstitial lung disease / pneumonitis
    # signal; all four disproportionality measures must flag.
    r = d.compute(150, 4850, 3000, 992000)
    assert r["ROR"]["signal"] is True and r["ROR"]["ci_low"] > 1
    assert r["PRR"]["signal"] is True and r["PRR"]["chi2"] >= 4
    assert r["IC"]["signal"] is True and r["IC"]["ci_low"] > 0
    eb = r["EBGM"]
    eb05 = eb.get("EB05", eb.get("eb05", 0))
    assert r["EBGM"]["signal"] is True and eb05 >= 2
    assert r["signal_overall"] is True
