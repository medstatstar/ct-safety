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

PROTOCOL (consistent with the live ct-search.coze.site/run unified endpoint):
  - POST JSON (sync) to https://ct-search.coze.site/run with `Authorization: Bearer <token>`.
    The endpoint runs the LangGraph synchronously and returns the full state dict
    (no async run_id / polling in practice; a minimal poll fallback is kept defensively).
  - Payload: {"source": "nmpa_pv", "mode": "search", "keyword": <drug>,
              "multi_keywords": "<event terms, space-separated>",
              "max_pages": N, "query_origin": <sha256(hostname)>}
  - Response: {"project_list": "<json {total_count, projects:[{title,url,date,
              source_column,snippet,matched_keywords,tier}]}>", "total_count": N,
              "run_id": "..."}  (project_list is a JSON STRING — parse it).
  - Token resolution (ct-base §5): --token > env CT_REGISTRY_COZE_TOKEN >
    embedded public blob (XOR+base64, same shared credential as ct-registry).
  - SAFE PREVIEW by default: no network I/O unless --run.
  - Outbound authorization gate (ct-base §5.212): endpoint must be present in
    adapters/config.json auto_approve_endpoints, else [AUTH-BLOCK] and exit.

DEPLOYMENT STATUS (re-probed 2026-09-01, verified live — NOT an assumption):
  The unified endpoint **now serves source "nmpa_pv"** and returns genuine
  NMPA/CDR-ADR ADR bulletins. Live probe with drug=甲氨蝶呤 returned
  hit_count=1 (通报专文: "药品不良反应信息通报（第75期）关注甲氨蝶呤片的误用风险"),
  with the `tier` field present — i.e. the response-shape guard PASSED, no
  contamination. The browser channel (Playwright on the Coze server) is exactly
  what bypasses the NMPA-main-site WAF (HTTP 412) that blocks local direct fetch.
  (Background, kept for context: before the workflow was uploaded, the endpoint
  silently FELL BACK to the default chinadrugtrials source for unknown sources —
  which is why `_reject_foreign_records` exists. That guard is STILL enforced;
  it must never be relaxed, because a regressed/unknown source could re-introduce
  the clinical-trial-into-safety-report contamination.)

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


def _billing_fields(account_id, billing_token):
    """ct-base §20.12：计费身份标识透传（可选）。

    仅当调用方显式提供才进入出站 payload；服务端未部署计费中间件时由
    `extra='ignore'` 安全忽略（向后兼容、不阻断）。与 `query_origin` 匿名机器
    指纹完全独立，不复用其字段。返回 {} 表示 legacy 未计量路径。
    """
    out = {}
    if account_id and account_id.strip():
        out["account_id"] = account_id.strip()
    if billing_token and billing_token.strip():
        out["billing_token"] = billing_token.strip()
    return out


# ── 错源污染守卫 / response-shape guard ────────────────────────────────────
# 背景：统一端点对未知 source 不报错，而是静默 fallback 到默认源（实测 2026-09-01：
# nmpa_pv / chinadrugtrials / 乱码源名返回完全一致的临床试验登记记录）。若不加守卫，
# 临床试验登记会被当成 NMPA 不良反应通报灌进安全报告——数据污染级假阳性，比硬失败更危险。
#
# NMPA 节点（nmpa_search_node._filter_and_grade）保证输出的记录键集合：
#     {title, url, date, source_column, snippet, matched_keywords, tier}
# 临床试验源（chinadrugtrials / chictr 等）的记录键含：登记号 / 试验状态 / project_id …
# 两者互斥，可据此确定性判定。
_FOREIGN_KEYS = ("登记号", "试验状态", "project_id", "试验通俗题目", "适应症",
                 "申办单位", "伦理委员会")


def _reject_foreign_records(records):
    """校验记录是否为 NMPA 通报形状。返回 (ok, reason)；ok=False 时必须拒绝合并。

    判定规则（确定性、零网络、纯函数，符合 ct-base 反幻觉护栏原则）：
      1. 任一条记录含临床试验特征键 → 错源污染；
      2. 非空记录集里 tier 全缺 → 不是 nmpa_pv 节点的产物，同样视为污染。
    """
    if not records:
        return True, ""
    sample = records[:20]
    for r in sample:
        if not isinstance(r, dict):
            return False, "record is not an object"
        for k in _FOREIGN_KEYS:
            if k in r:
                return False, (
                    "endpoint fell back to a non-NMPA source: records carry "
                    "clinical-trial field %r (source nmpa_pv not deployed on the "
                    "unified endpoint yet)" % k)
    if not any(isinstance(r, dict) and r.get("tier") for r in sample):
        return False, (
            "endpoint returned records without the 'tier' field that the NMPA "
            "node always emits — refusing to merge (unknown/degraded source)")
    return True, ""


def search_nmpa(drug_keywords, event_keywords=None, terms=None, max_pages=3,
                run=False, out=None, timeout=300, token=None, endpoint=None,
                account_id=None, billing_token=None):
    """检索 NMPA 通报（经 Coze 统一端点浏览器通道）。返回 result dict 或 None(preview)。

    契约（与 ct-registry 统一端点一致）：服务端同步返回全局状态 dict，
    project_list 为 JSON 字符串，内含 projects 列表（公报记录）。
    """
    endpoint = endpoint or DEFAULT_ENDPOINT
    drug_list = [d for d in (drug_keywords or []) if d]
    event_list = [e for e in (event_keywords or []) if e]
    terms_list = [t for t in (terms or []) if t]
    primary_drug = drug_list[0] if drug_list else (event_list[0] if event_list else "")
    # 事件词 + 额外词作为本地 AND 过滤条件（服务端 multi_keywords）
    multi_kw = " ".join(event_list + terms_list)

    payload = {
        "source": SOURCE,
        "mode": "search",
        "keyword": primary_drug,
        "multi_keywords": multi_kw,
        "max_pages": max(1, int(max_pages)),
        "query_origin": _query_origin(),
    }
    billing = _billing_fields(account_id, billing_token)
    if billing:
        payload.update(billing)
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
        resp = requests.post(endpoint, headers=headers, json=safe_payload, timeout=timeout)
    except requests.exceptions.ProxyError:
        # ct-base §5.49：系统代理残留 → 绕代理直连重试
        resp = requests.post(endpoint, headers=headers, json=safe_payload, timeout=timeout,
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

    # 极小概率异步分支（本端点实际同步返回，防御性保留）
    run_id = data.get("run_id")
    if data.get("status") == "accepted" and run_id and not data.get("project_list"):
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

    # 解析 project_list（JSON 字符串）
    projects = []
    if data.get("project_list"):
        try:
            pl = json.loads(data["project_list"])
            projects = pl.get("projects", []) if isinstance(pl, dict) else []
        except Exception as e:
            return {"source": "NMPA via coze", "hit_count": 0, "hits": [],
                    "error": "project_list parse failed: %s" % e}

    # 错源污染守卫：形状不符一律 fail-closed，绝不把临床试验登记并入安全报告
    ok, reason = _reject_foreign_records(projects)
    if not ok:
        return {"source": "NMPA via coze", "hit_count": 0, "hits": [],
                "tier_counts": {}, "query": payload,
                "run_id": data.get("run_id"),
                "error": "NMPA_SOURCE_NOT_DEPLOYED: %s" % reason}

    hits = []
    tier_counts = {}
    for p in projects:
        tier = p.get("tier") or "NMPA通报"
        hit = {
            "title": p.get("title", ""),
            "url": p.get("url", ""),
            "date": p.get("date"),
            "source_column": p.get("source_column", "NMPA通报"),
            "snippet": p.get("snippet", ""),
            "matched_keywords": p.get("matched_keywords", []),
            "tier": tier,
        }
        hits.append(hit)
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    result = {
        "source": "NMPA via coze (nmpa.gov.cn browser channel)",
        "note": ("NMPA《药品不良反应信息通报》定性叙事检索；非个案计数，不可做 "
                 "disproportionality 分析。仅作 FAERS 信号定性佐证。"),
        "query": payload,
        "run_id": data.get("run_id"),
        "hit_count": len(hits),
        "tier_counts": tier_counts,
        "hits": hits,
    }
    if isinstance(data, dict) and data.get("error"):
        result["error"] = data["error"]
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print("[OK] wrote", out, "(hits=%d)" % len(hits))
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
    ap.add_argument("--account-id", help="（可选）付费账户标识，透传至统一端点（ct-base §20.12 计费预留）")
    ap.add_argument("--billing-token", help="（可选）服务端签发的计费令牌，透传至统一端点")
    args = ap.parse_args()

    # 计费标识：CLI 优先，env (CT_BILLING_ACCOUNT_ID / CT_BILLING_TOKEN) 兜底
    account_id = args.account_id or os.environ.get("CT_BILLING_ACCOUNT_ID")
    billing_token = args.billing_token or os.environ.get("CT_BILLING_TOKEN")

    drug_kw = [k.strip() for k in args.drug.split(",") if k.strip()]
    res = search_nmpa(drug_kw, [args.event] if args.event else [], args.terms,
                      args.max_pages, args.run, args.out, args.timeout,
                      args.token, args.endpoint, account_id, billing_token)
    if res and not args.out:
        print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
