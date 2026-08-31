#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nmpa_coze.py — NMPA《药品不良反应信息通报》检索的 Coze 浏览器通道客户端

WHY THIS EXISTS:
  NMPA 主站 (nmpa.gov.cn，含《药品不良反应信息通报》) 对本机直连返回 HTTP 412
  (CDN/WAF 拦截)。与 ct-registry 的 Tier2 统一检索（WHO ICTRP / CDE / ChiCTR 等
  无公开 API 源走 Coze 服务器端浏览器抓取）同一架构：把检索委派给 Coze 统一
  工作流端点 ct-search.coze.site/run，由服务端浏览器通道抓取并返回结构化结果，
  本地零 Playwright、零浏览器依赖。

PROTOCOL (mirrors ct-registry adapters/extsvc_client.py):
  - POST JSON to https://ct-search.coze.site/run with `Authorization: Bearer <token>`.
  - Payload: {"source": "nmpa_pv", "mode": "search", "drug": [...], "event": [...],
              "terms": [...], "max_pages": N, "query_origin": <sha256(hostname)>}
  - Async: gateway returns {"status":"accepted","run_id"} -> poll
    GET <base>/run/status/{run_id} until completed; result records are
    {"title","url","date","source_column","snippet"} shaped.
  - Token resolution (ct-base §5): --token > env CT_REGISTRY_COZE_TOKEN >
    embedded public blob (XOR+base64, same shared credential as ct-registry).
  - SAFE PREVIEW by default: no network I/O unless --run.
  - Outbound authorization gate (ct-base §5.212): endpoint must be present in
    adapters/config.json auto_approve_endpoints, else [AUTH-BLOCK] and exit.

NOTE (server-side dependency): the server workflow must recognise source
"nmpa_pv". If it replies "unknown source", the channel is wired correctly but
the server-side source needs deploying (separate authorisation) — the client
surfaces that verbatim instead of guessing.

EGRESS: only PUBLIC query terms (drug / event keywords) are sent. No
confidential data; PII patterns are stripped from the payload (ct-base §5.50).
"""
import argparse
import hashlib
import json
import os
import re
import socket
import sys
import time

import base64

# ── ct-base §5 公用凭据：与 ct-registry 同一份统一端点 token ──────────────
# XOR key 与 ct-registry adapters/endpoint_token.py 保持一致以兼容同一 blob。
OBFUSCATION_KEY = b"ct-registry-extsvc-obf-v1-9c4d2a"

_EMBEDDED_COZE_UNIFIED = (
    "Bg1nGgcgCho7GzN-MAI9QjgKZBwrC1kGa25wVX0Jfxk5Hk5HKyM_HjgmM0UoPDUHOCdKGDsPHB5oR1IbeDBnVSwwRkc8VTgKOTYRRigBPkpYBlQlEgUeO1hiUClbAHozFBdXHRMrWzUDEyoYDxpHAxovQCEXL0QBWHRhNV8tWBEBPUE4MQYCQjYgPWBWGkclIDdDCBsrHhJod30tZikAGRM5RxYSBQMbRStKfBwxGEMFKkA5VgVuPwdifSpMKXYoUTpHFVYpAxBBPSpaDBkjNUYqRwAaKFcRAGBtNgYrdjhXOG44HwM-Oh09EGcfGzMfGzlAOlQqVE9ZTn4IQT0AWFUufkcPBQBKRxBKZxcaM0oeOWtWEjxqIERJfg8EAWFYEy5pHVYpAypFPS1KVzcgIkYuaQQYKXkzS2BtJgQtWxYKFx44Dy4DHB0TLhgMGkclAzlrVgoCdSRedQslXj0ANxkXHEtVBVsHGBAVFBUiMBxFLUc2USt5HUZgQzoHKXYoUDt5FVcpLSIMOxcdSzVEEEA8WjUAKF0YAkp2M1M3UwIKHwAdCAk6PhAxPmYsPx8aACp9PiQNSkZoTHc2TR58BS0HFCgCViMEEhhMXUhARitAElkXGgh4FEtlVVNkVn84BC0cFCEoOio6Mw18DykDMiUzFSsNUlwYUHdrCW0AZlQvPGUFXRIRNBU9C2scQEUJOQdbXCAnXiFub35VR1BKAycZfCJdDCM-Bj4qfy0qGTIfCX0ZLSF6E2IVFFEHVQEUEzpUATVUIhYlPE58MRYbQx0pQSoLF3QdYXVRMAI1XhNRDHsKUz0NQDELL3sJKTE3BAlvPRNWawxgRwkvUyBEEBc3HydVXz1DTQdIVxVOK0U7FRo1Ug5XAkBkCzVZVVZWWyRVChM0ExkiPAxaNDIXERoGSSVbV10uQGZWE30gBikXMmMlFlczHgImIX8sQUAXEA19GDc8GU9oRHUJeQhEIlIsWg=="
)

DEFAULT_ENDPOINT = "https://ct-search.coze.site/run"
SOURCE = "nmpa_pv"
DEFAULT_TOKEN_ENV = "CT_REGISTRY_COZE_TOKEN"

# 出站授权闸门（ct-base §5.212）：端点须在 adapters/config.json auto_approve_endpoints
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def _obf_decode(blob: str) -> str:
    data = base64.urlsafe_b64decode(blob.strip())
    plain = bytes(b ^ OBFUSCATION_KEY[i % len(OBFUSCATION_KEY)]
                  for i, b in enumerate(data))
    return plain.decode("utf-8")


def get_token(cli_token=None, token_env=None):
    """token 解析优先级：CLI > env(CT_REGISTRY_COZE_TOKEN) > 内嵌公用 blob。"""
    if cli_token:
        return cli_token
    env = token_env or DEFAULT_TOKEN_ENV
    v = os.environ.get(env)
    if v:
        return v
    return _obf_decode(_EMBEDDED_COZE_UNIFIED)


def check_outbound_authorization(endpoint):
    """端点在 config.json auto_approve_endpoints 即放行；否则 [AUTH-BLOCK] 返回 False。"""
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        if endpoint in cfg.get("auto_approve_endpoints", []):
            return True
    except Exception:
        pass
    sys.stderr.write(
        "[AUTH-BLOCK] outbound to %s requires user confirmation.\n"
        "Add it to adapters/config.json auto_approve_endpoints after user approval.\n" % endpoint)
    return False


# ── ct-base §5.50: 出站 payload 剥离 PII ────────────────────────────────
_PII_PATTERNS = [
    (re.compile(r"\b1[3-9]\d{9}\b"), "<phone>"),
    (re.compile(r"\b\d{17}[\dXx]\b"), "<id-card>"),
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "<email>"),
]


def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, str):
        for pat, repl in _PII_PATTERNS:
            obj = pat.sub(repl, obj)
        return obj
    return obj


def _query_origin():
    return hashlib.sha256(socket.gethostname().encode("utf-8")).hexdigest()[:32]


def search_nmpa(drug_keywords, event_keywords=None, terms=None, max_pages=3,
                run=False, out=None, timeout=300, token=None, endpoint=None):
    """检索 NMPA 通报（经 Coze 统一端点浏览器通道）。返回 result dict 或 None(preview)。"""
    endpoint = endpoint or DEFAULT_ENDPOINT
    payload = {
        "source": SOURCE,
        "mode": "search",
        "drug": [d for d in drug_keywords if d],
        "event": [e for e in (event_keywords or []) if e],
        "terms": [t for t in (terms or []) if t],
        "max_pages": max(1, int(max_pages)),
        "query_origin": _query_origin(),
    }
    if not run:
        print("[PREVIEW] nmpa-coze: no network request will be made. Add --run to execute.")
        print("[PREVIEW] Endpoint : %s" % endpoint)
        print("[PREVIEW] Payload  : %s" % json.dumps(payload, ensure_ascii=False))
        return None

    if not check_outbound_authorization(endpoint):
        return {"source": "NMPA via coze", "hit_count": 0, "hits": [],
                "error": "AUTH-BLOCK: endpoint not in auto_approve_endpoints"}

    import requests
    tok = get_token(token)
    headers = {"Content-Type": "application/json", "Authorization": "Bearer %s" % tok}

    safe_payload = _sanitize(payload)
    try:
        resp = requests.post(endpoint, headers=headers, json=safe_payload, timeout=30)
    except requests.exceptions.ProxyError:
        # ct-base §5.49：系统代理残留 → 绕代理直连重试
        resp = requests.post(endpoint, headers=headers, json=safe_payload, timeout=30,
                             proxies={"http": None, "https": None})
    except requests.RequestException as e:
        return {"source": "NMPA via coze", "hit_count": 0, "hits": [],
                "error": "request failed: %s" % e}

    try:
        data = resp.json()
    except Exception:
        data = {}

    if resp.status_code != 200:
        return {"source": "NMPA via coze", "hit_count": 0, "hits": [],
                "error": "HTTP %s: %s" % (resp.status_code, resp.text[:300])}

    run_id = data.get("run_id")
    if data.get("status") == "accepted" and run_id:
        base = endpoint.rsplit("/run", 1)[0]
        status_url = "%s/run/status/%s" % (base.rstrip("/"), run_id)
        deadline = time.time() + timeout
        wait = 5.0
        while time.time() < deadline:
            try:
                r = requests.get(status_url, headers=headers, timeout=15)
                sd = r.json()
            except Exception:
                time.sleep(min(wait, max(1, deadline - time.time())))
                wait = min(wait * 2, 30)
                continue
            st = sd.get("status")
            if st == "running":
                time.sleep(min(wait, max(1, deadline - time.time())))
                wait = min(wait * 2, 30)
                continue
            if st in ("failed", "cancelled"):
                return {"source": "NMPA via coze", "hit_count": 0, "hits": [],
                        "error": "remote run %s: %s" % (st, sd.get("error")),
                        "run_id": run_id}
            data = sd.get("result", sd)
            break
        else:
            return {"source": "NMPA via coze", "hit_count": 0, "hits": [],
                    "error": "timeout after %ss polling run_id=%s" % (timeout, run_id),
                    "run_id": run_id}

    records = data.get("records") or []
    result = {
        "source": "NMPA via coze (nmpa.gov.cn browser channel)",
        "note": ("NMPA《药品不良反应信息通报》定性叙事检索；非个案计数，不可做 "
                 "disproportionality 分析。仅作 FAERS 信号定性佐证。"),
        "query": payload,
        "run_id": data.get("run_id") or run_id,
        "hit_count": len(records),
        "hits": records,
    }
    if isinstance(data, dict) and data.get("error"):
        result["error"] = data["error"]
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print("[OK] wrote", out, "(hits=%d)" % len(records))
    return result


def main():
    ap = argparse.ArgumentParser(
        description="Search NMPA adverse-reaction bulletins via Coze browser channel.")
    ap.add_argument("--drug", required=True,
                    help="drug keyword(s), comma-separated Chinese/English aliases")
    ap.add_argument("--event", help="event keyword")
    ap.add_argument("--terms", nargs="*", help="extra AND keywords")
    ap.add_argument("--max-pages", type=int, default=3)
    ap.add_argument("--run", action="store_true", help="execute network call")
    ap.add_argument("--out", help="output JSON path")
    ap.add_argument("--timeout", type=int, default=300, help="poll timeout seconds")
    ap.add_argument("--token", help="override Bearer token (ct-base §5 resolution otherwise)")
    ap.add_argument("--endpoint", help="override endpoint URL")
    args = ap.parse_args()

    drug_kw = [k.strip() for k in args.drug.split(",") if k.strip()]
    res = search_nmpa(drug_kw, [args.event] if args.event else [], args.terms,
                      args.max_pages, args.run, args.out, args.timeout,
                      args.token, args.endpoint)
    if res and not args.out:
        print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
