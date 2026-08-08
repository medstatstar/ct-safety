#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
r_libs.py -- validation / sanitization helpers for the ct- skill library.

IMPORTANT (architectural decision, 2026-08-08):
  This SHARED base module does NOT contain an R code-execution primitive.
  Executing R (`run_r`) is intentionally NOT part of the shared base -- each
  skill that genuinely needs R execution carries its OWN scoped runner (copied
  from a prior template) with its own `confirmed` gate, allowlist validation
  and output sanitization. A general "execute arbitrary R" function is never
  propagated from the base into every skill (including pure-Python skills that
  have no business running R).

This module provides reusable defensive helpers only:
  - find_rscript() / is_valid_rscript()
        Locate the Rscript binary and verify it is genuinely Rscript (prevents
        binary substitution). Used only by skills that opt into R execution.
  - _validate_token() / _safe_r_path_literal()
        Allowlist validation of every user string that reaches generated R, so a
        user value can NEVER break out of an R string literal and inject code.
  - sanitize_output()
        Strip file paths and truncate before any output is shown to the user.
"""

import os
import re
import textwrap


# ═══════════════════════════════════════════════════════════════════════════
# Security: strict validation of EVERY user string that reaches generated R
# ═══════════════════════════════════════════════════════════════════════════
# Goal: make it impossible for a user-supplied value to break out of an R string
# literal and inject arbitrary R code (RCE). Generated R embeds user values
# inside single- or double-quoted literals, so we reject any value containing
# characters that could terminate the string or start a new R statement.
#
# _SAFE_TOKEN_RE : for short categorical tokens (option names, design names, ...)
# _SAFE_PATH_RE  : for filesystem paths (allows separators, spaces, CJK names)
_SAFE_TOKEN_RE = re.compile(r'^[A-Za-z0-9_\-]+$')
_SAFE_PATH_RE = re.compile(r'^[A-Za-z0-9_.\- /\\:一-鿿]+$')


def find_rscript():
    """Locate the Rscript executable (env override, PATH lookup, then known paths)."""
    env_path = os.environ.get("RSCRIPT_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    from shutil import which
    path = which("Rscript")
    if path:
        return path
    defaults = [
        r"C:\Tools\R-4.5.1\bin\x64\Rscript.exe",
        r"C:\Program Files\R\R-4.5.1\bin\x64\Rscript.exe",
        "/usr/local/bin/Rscript",
        "/usr/bin/Rscript",
    ]
    for d in defaults:
        if os.path.isfile(d):
            return d
    return None


def is_valid_rscript(path):
    """Ensure the resolved executable is genuinely Rscript (prevent binary substitution).

    The caller runs generated R code via subprocess, so we must guarantee the
    binary we invoke is the real Rscript, not an attacker-supplied executable,
    and that it is actually executable.
    """
    if not path or not os.path.isfile(path):
        return False
    try:
        real = os.path.realpath(path)
    except OSError:
        return False
    base = os.path.basename(real).lower()
    if base not in ("rscript", "rscript.exe"):
        return False
    if not os.access(real, os.X_OK):
        return False
    return True


def _validate_token(name, value):
    """Reject categorical string args that could break out into R code."""
    if value is None:
        return value
    if not _SAFE_TOKEN_RE.match(value):
        raise ValueError(
            "Invalid %s=%r: only [A-Za-z0-9_-] allowed "
            "(no quotes, semicolons or parentheses)." % (name, value)
        )
    return value


def _safe_r_path_literal(path):
    """Return `path` safely embedded in an R string literal, or None if absent.

    Validates against a path allowlist, then normalises Windows separators to
    forward slashes (R accepts them on every platform). Raises ValueError on any
    value that could escape the R string context.
    """
    if path is None:
        return None
    if not _SAFE_PATH_RE.match(path):
        raise ValueError(
            "Unsafe output path %r: only letters, digits, spaces and ._-:/\\ "
            "are allowed (no quotes, semicolons or parentheses)." % path
        )
    return path.replace("\\", "/")


def sanitize_output(raw, max_lines=200, max_col=200):
    """Strip file paths and truncate output before showing it to the user."""
    cleaned = re.sub(
        r'[A-Za-z]:\\(?:[^\s:"\']+\\)*[^\s:"\']+|/(?:[^\s:"\']+/)+[^\s:"\']+',
        lambda m: os.path.basename(m.group(0)), raw
    )
    lines = cleaned.split('\n')
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f'... ({len(lines) - max_lines} lines truncated)']
    lines = [
        textwrap.shorten(l, width=max_col, break_long_words=False, placeholder='…')
        if len(l) > max_col else l for l in lines
    ]
    return '\n'.join(lines)
