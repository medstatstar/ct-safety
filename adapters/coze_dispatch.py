#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
coze_dispatch.py — ct-safety 轻本地端统一外发调度器（薄客户端）

WHY THIS EXISTS
───────────────
用户指令（2026-09-01）：「统一采用轻本地端的策略，本地所有的 safety 检索需求
一律改为外发 coze 实现。」本模块是这条指令的本地落地：

  - 默认（非 --offline）：所有安全性「检索」动作经 Coze 统一端点
    ct-search.coze.site/run 外发，由服务端直连各公共 API（FAERS / FDA Label /
    DailyMed / RxClass / openFDA 召回 / 香港 ADR），仅回传**结构化结果**。
  - 本地仅负责 disproportionality / signal_score / check_event（labeled 判定）/
    报告生成等计算，以及 --offline 时的本机直连兜底。
  - 出站凭据 / 授权闸门 / PII 剥离 / 计费透传 **复用 nmpa_coze 单一真相源**，
    不重复实现 token 解码与 config 校验。

出站契约（与 ct-registry/adapters/coze 端一致）
──────────────────────────────────────────────────
  POST JSON {"source","mode":"search","keyword":<drug>,
             "multi_keywords":<event 词>", "date_from?","date_to?",
             "query_origin":<sha256(hostname)>, <billing?>}
  → 同步返回全局状态 dict，data["project_list"] 是 JSON 字符串，其内容即对应
    本地模块的输出结构（faers_counts / fda_label / Evidence.to_dict …）。
    因此本地 dispatcher 对下游计算代码**完全无感**。

覆盖的 Coze source（与 ct-registry sources.py 注册一一对应）
────────────────────────────────────────────────────
  faers / fda_label / dailymed / rxclass / fda_recall / hk_pv
（nmpa_pv 已由 nmpa_coze.search_nmpa 单独处理，仍走同一端点；
 fetch_cn_pv/cdr-adr.org.cn 本机直连即可达、无 WAF 阻断、Coze 端对该 CN 域
 可达性未验证，故刻意保留本机直连，不在此外发。）

文档化例外（仍本机直连，不外发）
────────────────────────────────
  - fetch_faers.query_total / fetch_case_reports：需原样 openFDA 任意检索式 /
    个案报告，结构化 state 无法承载，且 openFDA 直连不被 WAF 阻断；保留本机直连。
  - fetch_fda_label.check_event：纯本地判定（labeled/unlabeled），无网络。
  - fetch_faers._date_clause：纯函数，无网络。
"""
import json
import os
import sys
import time

# 复用 nmpa_coze 的凭据/授权/PII/计费单一真相源（同目录）
from nmpa_coze import (
    get_token,
    check_outbound_authorization,
    _sanitize,
    _query_origin,
    _billing_fields,
    DEFAULT_ENDPOINT,
)

# 中文药名 → 英文 INN 自动映射（复用 ct-base 共享 resolver，本地已注入 scripts/）。
# 单一真源 ct-base/references/drug_name_map.json（471 条），开发期本地优先读取
# ct-safety/references/drug_name_map.json（publish_inject 注入副本）。
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _SCRIPTS_DIR = os.path.join(os.path.dirname(_HERE), "scripts")
    if _SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, _SCRIPTS_DIR)
    from drug_name_resolver import is_non_ascii as _dnr_is_non_ascii, \
        resolve as _dnr_resolve
except Exception:  # pragma: no cover — resolver 缺失时降级为原样外发
    _dnr_is_non_ascii = None
    _dnr_resolve = None

# 中文事件词 → 英文（复用 ct-base 共享 kw_localize，本地已注入 scripts/）。
# 对照表（term_map.json / kw_lexicon.json）优先；表内没有的词走 online_translate
# 零密钥公共端点兜底（CT_TRANSLATE_ONLINE=0 可关）。对齐 bilingual_retrieval.md §2。
try:
    from kw_localize import detect_lang as _kwl_detect_lang, \
        localize_with_fallback as _kwl_localize_with_fallback
except Exception:  # pragma: no cover — 缺失时降级为原样外发
    _kwl_detect_lang = None
    _kwl_localize_with_fallback = None

# 可由本调度器外发的源（fail-closed：不在表内一律拒绝）
DISPATCHABLE_SOURCES = frozenset({
    "faers", "fda_label", "dailymed", "rxclass", "fda_recall", "hk_pv",
})

# 这些源返回「佐证型 Evidence」结构（dailymed/rxclass/fda_recall）；
# 出错时也回传同构 error 载体，便于 corroborative_sources.collect() 无感消费。
_EVIDENCE_SOURCES = frozenset({"dailymed", "rxclass", "fda_recall"})

# 后端模式：False=外发 Coze（默认），True=本机直连兜底。由调用方 set_mode() 设置。
OFFLINE = False


def set_mode(offline: bool) -> None:
    """设置后端模式。offline=True → 本机直连；False（默认）→ 外发 Coze。"""
    global OFFLINE
    OFFLINE = bool(offline)


def _translate_drug(drug):
    """非 ASCII（中文）药名 → 英文 INN（来自 ct-base 共享 drug_name_map）。

    返回 (send_keyword, translated: bool)。英文 / 空 / 未命中映射时原样返回。
    仅在 dispatch() 调用，故只作用于 6 个英文源（faers / fda_label / dailymed /
    rxclass / fda_recall / hk_pv）；nmpa_pv 走 nmpa_coze.search_nmpa，不经过本函数，
    中文药名不受影响（openFDA 等仅认英文 INN，中文名直发会 400）。
    """
    if not drug or _dnr_is_non_ascii is None or not _dnr_is_non_ascii(drug):
        return drug, False
    eng, translated = _dnr_resolve(drug, auto=True)
    if eng and eng.strip() and eng != drug:
        return eng, translated
    return drug, False


def _translate_event(event):
    """非 ASCII（中文）事件词 → 英文（对照表优先 + 在线 API 兜底，来自 ct-base 共享 kw_localize）。

    返回 (send_event, translated: bool)。英文 / 空 / 未命中映射且在线兜底也失败时原样返回。
    对齐 bilingual_retrieval.md §2：翻译前置，表内没有的词外接翻译 API 兜底。
    事件词整短语保留（不截断），供 Coze 端整短语文引用（修 faers_node 首词截断 bug 的前提）。
    """
    if not event or _kwl_detect_lang is None or _kwl_detect_lang(event) != "zh":
        return event, False
    eng, st = _kwl_localize_with_fallback(event, "en")
    if eng and eng.strip() and eng != event:
        return eng, (st in ("term_map", "online"))
    return event, False


def _evidence_error(source, drug, event, err):
    """佐证源出错时的同构载体（与 Evidence.to_dict 形状一致，collect() 无感消费）。"""
    return {
        "source": source, "drug": drug, "event": event,
        "labeled": None, "detail": "", "record_count": 0,
        "records": [], "error": err,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _generic_error(source, err):
    return {"error": err, "source": source}


def dispatch(source, drug, event=None, date_from=None, date_to=None,
             run=False, out=None, timeout=300, token=None, endpoint=None,
             account_id=None, billing_token=None, extra=None):
    """统一外发检索。返回解析后的 result dict（与本地模块同构）；run=False 仅预览。

    `out` 非空时把结果写盘，兼容 ct_safety.py 既有 `json.load(open(out))` 往返。
    """
    if source not in DISPATCHABLE_SOURCES:
        raise ValueError("coze_dispatch: unsupported source %r (allowed: %s)"
                         % (source, sorted(DISPATCHABLE_SOURCES)))
    endpoint = endpoint or DEFAULT_ENDPOINT
    # ① 中文药名 → 英文 INN（仅作用于英文源；resolver 缺失时降级为原样）
    send_keyword, translated_drug = _translate_drug(drug)
    if translated_drug:
        print("[coze-dispatch][%s] 中文药名 %r → 英文 INN %r（自动映射）"
              % (source, drug, send_keyword))
    # ② 中文事件词 → 英文（对照表优先 + 在线 API 兜底；整短语保留不截断）
    send_event, translated_event = _translate_event(event)
    if translated_event:
        print("[coze-dispatch][%s] 中文事件 %r → 英文 %r（自动映射）"
              % (source, event, send_event))
    payload = {
        "source": source,
        "mode": "search",
        "keyword": send_keyword or "",
        "multi_keywords": (send_event or "").strip(),
        "query_origin": _query_origin(),
    }
    if date_from:
        payload["date_from"] = date_from
    if date_to:
        payload["date_to"] = date_to
    if extra:
        payload.update(extra)
    billing = _billing_fields(account_id, billing_token)
    if billing:
        payload.update(billing)

    if not run:
        print("[PREVIEW] coze-dispatch[%s] payload=%s (no network; add run to execute)"
              % (source, json.dumps(payload, ensure_ascii=False)))
        return None
    if not check_outbound_authorization(endpoint):
        err = "AUTH-BLOCK: endpoint %s not in auto_approve_endpoints" % endpoint
        print("[coze-dispatch][%s] %s" % (source, err))
        return _evidence_error(source, drug, event, err) if source in _EVIDENCE_SOURCES \
            else _generic_error(source, err)

    import requests
    tok = get_token(token)
    headers = {"Content-Type": "application/json",
               "Authorization": "Bearer %s" % tok}
    safe = _sanitize(payload)
    try:
        resp = requests.post(endpoint, headers=headers, json=safe, timeout=timeout)
    except requests.exceptions.ProxyError:
        # ct-base §5.49：系统代理残留 → 绕代理直连重试
        resp = requests.post(endpoint, headers=headers, json=safe, timeout=timeout,
                             proxies={"http": None, "https": None})
    except requests.RequestException as e:
        err = "request failed: %s" % e
        print("[coze-dispatch][%s] %s" % (source, err))
        return _evidence_error(source, drug, event, err) if source in _EVIDENCE_SOURCES \
            else _generic_error(source, err)

    if resp.status_code != 200:
        err = "HTTP %s: %s" % (resp.status_code, resp.text[:300])
        print("[coze-dispatch][%s] %s" % (source, err))
        return _evidence_error(source, drug, event, err) if source in _EVIDENCE_SOURCES \
            else _generic_error(source, err)

    data = {}
    try:
        data = resp.json()
    except Exception:
        data = {}
    result = None
    pl = data.get("project_list") if isinstance(data, dict) else None
    if pl:
        try:
            result = json.loads(pl)
        except Exception as e:
            err = "project_list parse failed: %s" % e
            print("[coze-dispatch][%s] %s" % (source, err))
            return _evidence_error(source, drug, event, err) if source in _EVIDENCE_SOURCES \
                else _generic_error(source, err)
    if result is None:
        err = "empty project_list from endpoint"
        return _evidence_error(source, drug, event, err) if source in _EVIDENCE_SOURCES \
            else _generic_error(source, err)

    if out:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            with open(out, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print("[OK] coze-dispatch[%s] wrote %s" % (source, out))
        except Exception as e:
            print("[WARN] coze-dispatch[%s] write %s failed: %s" % (source, out, e))
    return result


# ═════════════════════════════════════════════════════════════════════════════
# ct_safety.py 用的薄垫片：把 fetch_faers / fetch_fda_label 的「检索」调用重定向到
# Coze；本地计算（check_event / _date_clause）与未外发的辅助检索（query_total /
# fetch_case_reports）保留本机直连。通过 rebind 模块全局名实现，调用点零改动。
# ═════════════════════════════════════════════════════════════════════════════
class FaersShim:
    """fetch_faers 的薄垫片：fetch_counts → Coze；其余保留本机直连。"""

    def __init__(self, real):
        self._real = real
        self._date_clause = real._date_clause  # 纯函数，本机直连

    def fetch_counts(self, drug, event=None, field="patient.drug.medicinalproduct",
                     top=10, api_key=None, run=False, out=None,
                     date_from=None, date_to=None, timeout=120, retries=3):
        if OFFLINE:
            return self._real.fetch_counts(drug, event, field, top, api_key,
                                           run=run, out=out, date_from=date_from,
                                           date_to=date_to, timeout=timeout, retries=retries)
        # Coze 服务端用默认 field；忽略本地 api_key/retries（服务端自有 key/重试）
        return dispatch("faers", drug, event, date_from=date_from, date_to=date_to,
                        run=run, out=out, timeout=max(int(timeout), 120))

    def query_total(self, search, api_key=None, timeout=120, retries=3):
        # 文档化例外：openFDA 任意检索式，结构化 state 无法承载 → 本机直连
        return self._real.query_total(search, api_key=api_key, timeout=timeout, retries=retries)

    def fetch_case_reports(self, drug, event=None, field="patient.drug.medicinalproduct",
                           n=20, api_key=None, run=False, out=None,
                           date_from=None, date_to=None, timeout=120, retries=3):
        # 文档化例外：个例报告直取 openFDA → 本机直连
        return self._real.fetch_case_reports(drug, event, field, n, api_key, run=run,
                                             out=out, date_from=date_from, date_to=date_to,
                                             timeout=timeout, retries=retries)

    def __getattr__(self, name):
        # 其它属性（如模块级常量）透明转发到真实模块
        return getattr(self._real, name)


class FdaLabelShim:
    """fetch_fda_label 的薄垫片：fetch_label → Coze；check_event 本地判定。"""

    def __init__(self, real):
        self._real = real

    def fetch_label(self, drug, api_key=None, run=False, out=None, limit=5,
                    timeout=120, retries=3):
        if OFFLINE:
            return self._real.fetch_label(drug, api_key=api_key, run=run, out=out,
                                          limit=limit, timeout=timeout, retries=retries)
        return dispatch("fda_label", drug, event=None, run=run, out=out,
                        timeout=max(int(timeout), 120))

    def check_event(self, label_data, event):
        # 本地判定（labeled/unlabeled），无网络
        return self._real.check_event(label_data, event)

    def __getattr__(self, name):
        return getattr(self._real, name)
