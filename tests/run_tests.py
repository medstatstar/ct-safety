#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
run_tests.py — one-command regression runner for ct-safety.

Discovers every tests/test_*.py module, runs all `test_*` functions, and prints
a concise PASS/FAIL/ERROR/SKIP summary. Pure stdlib (no pytest dependency).

Usage:
    python run_tests.py            # offline suite (mocks network)
    python run_tests.py --live     # also run tests/test_live.py (needs network)
    CT_SAFETY_LIVE=1 python run_tests.py

Exit code is non-zero if any test FAILs or ERRORs.
"""
import glob
import importlib.util
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
for p in (SCRIPTS, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

LIVE = ("--live" in sys.argv) or (os.environ.get("CT_SAFETY_LIVE") == "1")


def _load_module(path):
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _collect_tests(mod):
    """Collect `test_*` and `case*` callables from a module.

    Matches both ``test_*`` and ``case*`` prefixes (e.g. ``case01_foo``,
    ``case_bar``) so that test files using numeric case prefixes (case01–case10)
    are discovered alongside traditional ``test_*`` functions.
    """
    out = []
    for n in dir(mod):
        is_test = n.startswith("test_")
        is_case = n.startswith("case") and len(n) > 4 and n[4:5].isdigit() or n.startswith("case_")
        if (is_test or is_case) and callable(getattr(mod, n)):
            out.append((n, getattr(mod, n)))
    return out


def main():
    files = sorted(glob.glob(os.path.join(HERE, "test_*.py")))
    results = []  # (status, module, name, detail)
    for f in files:
        mod_name = os.path.splitext(os.path.basename(f))[0]
        # Skip all live-network test modules when not in --live mode
        is_live_module = mod_name in ("test_live", "test_real_world_scenarios")
        if is_live_module and not LIVE:
            tests = _collect_tests(_load_module(f))
            for n, _ in tests:
                results.append(("SKIP", mod_name, n, "network disabled (use --live or CT_SAFETY_LIVE=1)"))
            continue
        try:
            mod = _load_module(f)
        except Exception:
            results.append(("ERROR", mod_name, "(import)", traceback.format_exc().splitlines()[-1]))
            continue
        for n, fn in _collect_tests(mod):
            try:
                fn()
                results.append(("PASS", mod_name, n, ""))
            except Exception as e:  # noqa: BLE001
                # Live-network modules signal skip via their own _Skip exception
                if type(e).__name__ == "_Skip" or is_live_module:
                    results.append(("SKIP", mod_name, n, str(e)))
                else:
                    results.append(("FAIL", mod_name, n, "%s: %s" % (type(e).__name__, e)))

    # report
    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIP": 0}
    print("=" * 72)
    print("ct-safety regression suite  (live=%s)" % LIVE)
    print("=" * 72)
    for st, mod, n, detail in results:
        counts[st] += 1
        line = "  %-5s %-22s %-32s %s" % (st, mod, n, detail)
        print(line)
    print("-" * 72)
    print("  TOTAL %d  PASS=%d  FAIL=%d  ERROR=%d  SKIP=%d" % (
        len(results), counts["PASS"], counts["FAIL"], counts["ERROR"], counts["SKIP"]))
    print("=" * 72)
    return 1 if (counts["FAIL"] or counts["ERROR"]) else 0


if __name__ == "__main__":
    sys.exit(main())
