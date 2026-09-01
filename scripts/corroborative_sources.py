#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
corroborative_sources.py / 佐证型安全性数据源（labeled-vs-unlabeled 判定）

新增于 2026-09-01。

设计动机
────────
`multi_source.py` 的框架是**计数型**（2×2 → PRR/ROR），只适用于个例报告数据库
（FAERS / EudraVigilance / VigiBase）。但 disproportionality 只回答"报告是否不成比例"，
不回答**"这个事件是不是已经写在说明书里了"**——而后者恰恰是信号优先级分级
（ICH E2C / CIOMS VIII）的核心判据：

  已标注事件（labeled）  → 已知风险，优先级降级
  未标注事件（unlabeled）→ 潜在新信号，优先级升级

因此本模块单独实现**佐证型源**，不产出 PRR/ROR，而产出布尔/枚举型证据，
供 signal_score / signal_prioritizer 消费。强行把这些源塞进 2×2 框架会失真，
故与 multi_source.py 解耦。

已接入源（均于 2026-09-01 本机实测可达、免密钥）
──────────────────────────────────────────────
  dailymed  — DailyMed SPL 全量说明书（NLM 官方 REST v2）
              比 openFDA drug/label.json 覆盖更全（含 OTC、生物制品、仿制药），
              且可取 SPL 全文 XML 做段落级命中判定。
              列表: /services/v2/spls.json?drug_name=X
              全文: /services/v2/spls/{setid}.xml
  rxclass   — RxClass MED-RT 药物-不良效应类目关系（NLM RxNav）
              relaSource=MEDRT 的 has_adverse_effect / may_treat 等语义关系，
              提供"权威知识库是否已认定该药可致该效应"的独立佐证。
  fda_recall— openFDA drug/enforcement.json 药品召回/执法记录
              反映"监管已采取实际行动"，是比标签更强的风险信号。

未接入源及硬性阻断原因（2026-09-01 本机实测，非推测）
────────────────────────────────────────────────────
  pmda_jader    — 下载表单含 captchaText 验证码字段
                  (info.pmda.go.jp/fukusayoudb/CsvDownload.jsp)，无法免人工自动化。
  health_canada — health-products.canada.ca API 本机连续 ReadTimeout（60s×2）。
  vaers         — CDC WONDER D8 端点 GET 返回 403 Access Denied，需 POST XML + 使用协议。
  vigiaccess    — 纯 SPA，JS bundle 内无可用数据 API，仅含外链。
  adrreports.eu — 数据在 BusinessObjects 报表内，无 JSON 端点（substances.json → 404）。
  mhra_idap     — info.mhra.gov.uk 本机 ConnectTimeout。

Usage
─────
  python scripts/corroborative_sources.py --drug metformin --event "lactic acidosis"
  python scripts/corroborative_sources.py --drug aspirin --event "gastrointestinal hemorrhage" \
      --sources dailymed,rxclass,fda_recall --format ascii
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

# ── 轻本地端：默认外发 Coze；--offline 回退本机直连（2026-09-01）──────────────
# dailymed / rxclass / fda_recall 的「检索」经 Coze 统一端点外发；本地仅做汇总判定。
try:
    _ADAPTERS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 os.pardir, "adapters")
    if _ADAPTERS_DIR not in sys.path:
        sys.path.insert(0, _ADAPTERS_DIR)
    from coze_dispatch import dispatch as _coze_dispatch, set_mode as _coze_set_mode
    _COZE_OK = True
except Exception:  # pragma: no cover - 缺失则强制离线
    _coze_dispatch = None
    _coze_set_mode = None
    _COZE_OK = False

# True=外发 Coze；False=本机直连（详见 main() 中的 --offline 处理）
BACKEND_COZE = False

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en,zh-CN;q=0.9"}
NO_PROXY = {"http": None, "https": None}

# 本机实测的硬性阻断源，供 CLI/报告如实披露，不静默假装"无数据"
BLOCKED_SOURCES: Dict[str, str] = {
    "pmda_jader": "下载表单需验证码（captchaText），无法免人工自动化",
    "health_canada": "health-products.canada.ca API 连续 ReadTimeout",
    "vaers": "CDC WONDER D8 GET 返回 403，需 POST XML + 使用协议",
    "vigiaccess": "纯 SPA，无数据 API 端点",
    "adrreports_eu": "数据在 BusinessObjects 报表内，无 JSON 端点",
    "mhra_idap": "info.mhra.gov.uk ConnectTimeout",
}


# ═════════════════════════════════════════════════════════════════════════════
# 统一结果结构
# ═════════════════════════════════════════════════════════════════════════════

class Evidence:
    """佐证型证据（非计数型）。

    labeled: True=事件已在该源明确记载 / False=未记载 / None=无法判定（源不可用）
    """

    __slots__ = ("source", "drug", "event", "labeled", "detail",
                 "records", "error", "fetched_at")

    def __init__(self, source: str, drug: str, event: str,
                 labeled: Optional[bool] = None,
                 detail: str = "",
                 records: Optional[List[Dict[str, Any]]] = None,
                 error: Optional[str] = None):
        self.source = source
        self.drug = drug
        self.event = event
        self.labeled = labeled
        self.detail = detail
        self.records = records or []
        self.error = error
        self.fetched_at = datetime.now().isoformat(timespec="seconds")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "drug": self.drug,
            "event": self.event,
            "labeled": self.labeled,
            "detail": self.detail,
            "record_count": len(self.records),
            "records": self.records[:10],
            "error": self.error,
            "fetched_at": self.fetched_at,
        }


def _get(url: str, timeout: int = 30) -> Optional[Any]:
    """带重试的 GET；失败返回 None（调用方负责标注 error）。"""
    if requests is None:
        return None
    last = None
    for attempt in range(2):
        try:
            return requests.get(url, headers=HEADERS, timeout=timeout,
                                proxies=NO_PROXY)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET 失败: {type(last).__name__}: {last}")


def _norm(text: str) -> str:
    """归一化用于匹配：小写、压缩空白、去标点。"""
    t = (text or "").lower()
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# MedDRA PT 与说明书用词的常见差异（英美拼写 + 临床同义表达）。
# 说明书写 "gastrointestinal bleeding"，MedDRA PT 是 "gastrointestinal haemorrhage"，
# 整词精确匹配会产生假阴性——2026-09-01 用 aspirin + GI hemorrhage 实测踩到此坑。
_SPELLING = [("hemorrhage", "haemorrhage"), ("edema", "oedema"),
             ("diarrhea", "diarrhoea"), ("anemia", "anaemia"),
             ("esophag", "oesophag"), ("leukemia", "leukaemia"),
             ("tumor", "tumour")]
_SYNONYMS = {
    "hemorrhage": ["bleeding", "bleed", "blood loss"],
    "haemorrhage": ["bleeding", "bleed", "blood loss"],
    "gastrointestinal": ["gi", "stomach", "gastric"],
    "pyrexia": ["fever"],
    "myocardial infarction": ["heart attack"],
    "hypersensitivity": ["allergic reaction", "allergy"],
    "hepatotoxicity": ["liver injury", "liver damage"],
    "nephrotoxicity": ["kidney injury", "renal impairment"],
    "thrombocytopenia": ["low platelet"],
    "neutropenia": ["low neutrophil"],
    "alopecia": ["hair loss"],
}
# 匹配时忽略的通用修饰词，避免"universalis"这类限定词导致漏配或误配
_STOPWORDS = {"universalis", "acute", "chronic", "severe", "unspecified",
              "nos", "disorder", "syndrome", "of", "the", "and"}


def _event_variants(event: str) -> List[str]:
    """生成事件词的整词匹配变体（拼写 + 同义表达 + 单复数）。"""
    e = _norm(event)
    if not e:
        return []
    vs = {e}
    for a, b in _SPELLING:
        for v in list(vs):
            if a in v:
                vs.add(v.replace(a, b))
            if b in v:
                vs.add(v.replace(b, a))
    # 同义替换（逐词/逐短语）
    for key, alts in _SYNONYMS.items():
        for v in list(vs):
            if key in v:
                for alt in alts:
                    vs.add(v.replace(key, alt))
    # 单复数
    for v in list(vs):
        if v.endswith("s") and len(v) > 4:
            vs.add(v[:-1])
        else:
            vs.add(v + "s")
    return sorted(x for x in vs if x)


def _event_tokens(event: str) -> List[str]:
    """事件词的实义 token（用于短语未整体命中时的回退匹配）。"""
    toks = [t for t in _norm(event).split()
            if len(t) > 3 and t not in _STOPWORDS]
    return toks


def _match_event(body_norm: str, event: str) -> List[str]:
    """在归一化文本中匹配事件。

    两级策略：
      1) 整词/变体短语命中 → 直接返回命中的变体（高置信）。
      2) 短语未命中时，要求**全部**实义 token 及其同义形式都出现 → 记为
         token 级命中（中置信），标注为 'tokens:xxx' 以便审计时区分。

    第 2 级是必要的：MedDRA PT 的词序/修饰与标签自由文本常不一致，
    仅靠短语匹配会系统性低估"已标注"比例。
    """
    variants = _event_variants(event)
    hits = [v for v in variants if v and v in body_norm]
    if hits:
        return hits

    toks = _event_tokens(event)
    if not toks:
        return []
    matched_all = True
    for t in toks:
        cands = {t}
        for a, b in _SPELLING:
            if a in t:
                cands.add(t.replace(a, b))
            if b in t:
                cands.add(t.replace(b, a))
        for key, alts in _SYNONYMS.items():
            if key == t or key in t:
                cands.update(alts)
        if not any(c in body_norm for c in cands):
            matched_all = False
            break
    return [f"tokens:{'+'.join(toks)}"] if matched_all else []


# ═════════════════════════════════════════════════════════════════════════════
# DailyMed SPL（美国说明书全量）
# ═════════════════════════════════════════════════════════════════════════════

class DailyMedSource:
    """DailyMed SPL 说明书全文，判定事件是否已标注。

    实测（2026-09-01）：spls.json 200 JSON；spls/{setid}.xml 200，
    metformin 的 SPL 全文 418KB，含 'adverse reaction' / 'lactic acidosis'。
    """

    name = "dailymed"
    LIST_URL = ("https://dailymed.nlm.nih.gov/dailymed/services/v2/"
                "spls.json?drug_name={drug}&pagesize={n}")
    XML_URL = ("https://dailymed.nlm.nih.gov/dailymed/services/v2/"
               "spls/{setid}.xml")

    def __init__(self, max_labels: int = 3):
        self.max_labels = max_labels

    def query(self, drug: str, event: str) -> Evidence:
        try:
            r = _get(self.LIST_URL.format(drug=drug, n=self.max_labels), 30)
            if r is None:
                return Evidence(self.name, drug, event,
                                error="requests 未安装")
            if r.status_code != 200:
                return Evidence(self.name, drug, event,
                                error=f"列表 HTTP {r.status_code}")
            data = r.json().get("data", [])
            if not data:
                return Evidence(self.name, drug, event, labeled=False,
                                detail="DailyMed 未检索到该药品的 SPL 说明书")

            recs: List[Dict[str, Any]] = []
            hit_any = False
            for item in data[:self.max_labels]:
                setid = item.get("setid")
                title = (item.get("title") or "")[:120]
                if not setid:
                    continue
                xr = _get(self.XML_URL.format(setid=setid), 45)
                if xr is None or xr.status_code != 200:
                    recs.append({"setid": setid, "title": title,
                                 "matched": None,
                                 "note": f"全文 HTTP {getattr(xr, 'status_code', 'ERR')}"})
                    continue
                body = _norm(xr.text)
                matched = _match_event(body, event)
                if matched:
                    hit_any = True
                recs.append({
                    "setid": setid,
                    "title": title,
                    "spl_version": item.get("spl_version"),
                    "published_date": item.get("published_date"),
                    "matched": matched,
                    "url": (f"https://dailymed.nlm.nih.gov/dailymed/"
                            f"drugInfo.cfm?setid={setid}"),
                })

            detail = ("事件词已出现在 SPL 说明书全文中（已标注风险）"
                      if hit_any else
                      "检索到说明书但全文未出现该事件词（潜在未标注信号）")
            return Evidence(self.name, drug, event, labeled=hit_any,
                            detail=detail, records=recs)
        except Exception as e:  # noqa: BLE001
            return Evidence(self.name, drug, event, error=str(e)[:200])


# ═════════════════════════════════════════════════════════════════════════════
# RxClass MED-RT（药物-效应知识库关系）
# ═════════════════════════════════════════════════════════════════════════════

class RxClassSource:
    """RxNav RxClass MED-RT 关系，佐证"权威知识库是否已认定该关联"。

    实测（2026-09-01）：byDrugName.json?relaSource=MEDRT 200 JSON。
    """

    name = "rxclass"
    URL = ("https://rxnav.nlm.nih.gov/REST/rxclass/class/byDrugName.json"
           "?drugName={drug}&relaSource=MEDRT")

    def query(self, drug: str, event: str) -> Evidence:
        try:
            r = _get(self.URL.format(drug=drug), 30)
            if r is None:
                return Evidence(self.name, drug, event,
                                error="requests 未安装")
            if r.status_code != 200:
                return Evidence(self.name, drug, event,
                                error=f"HTTP {r.status_code}")
            payload = r.json().get("rxclassDrugInfoList", {})
            infos = payload.get("rxclassDrugInfo", []) if payload else []
            if not infos:
                return Evidence(self.name, drug, event, labeled=False,
                                detail="RxClass MED-RT 无该药目类关系记录")

            variants = _event_variants(event)
            recs: List[Dict[str, Any]] = []
            hit = False
            for info in infos:
                cls = info.get("rxclassMinConceptItem", {}) or {}
                cname = cls.get("className", "") or ""
                rela = info.get("rela", "") or ""
                cn = _norm(cname)
                matched = [v for v in variants if v and (v in cn or cn in v)]
                if matched:
                    hit = True
                    recs.append({"class_name": cname, "rela": rela,
                                 "class_id": cls.get("classId"),
                                 "matched": matched})
            detail = ("MED-RT 存在与该事件语义匹配的类目关系（已知关联）"
                      if hit else
                      f"MED-RT 有 {len(infos)} 条类目关系，但无一匹配该事件词")
            return Evidence(self.name, drug, event, labeled=hit,
                            detail=detail, records=recs)
        except Exception as e:  # noqa: BLE001
            return Evidence(self.name, drug, event, error=str(e)[:200])


# ═════════════════════════════════════════════════════════════════════════════
# openFDA 药品召回/执法
# ═════════════════════════════════════════════════════════════════════════════

class FdaRecallSource:
    """openFDA drug/enforcement.json 召回记录。

    价值：召回是"监管已实际行动"，强于标签记载。
    实测（2026-09-01）：drug/enforcement.json 200 JSON，免密钥。
    """

    name = "fda_recall"
    URL = ("https://api.fda.gov/drug/enforcement.json"
           "?search=openfda.generic_name:%22{drug}%22+OR+"
           "openfda.brand_name:%22{drug}%22&limit={n}")

    def __init__(self, limit: int = 20):
        self.limit = limit

    def query(self, drug: str, event: str) -> Evidence:
        try:
            safe = re.sub(r"[^A-Za-z0-9 \-]", "", drug).replace(" ", "+")
            r = _get(self.URL.format(drug=safe, n=self.limit), 30)
            if r is None:
                return Evidence(self.name, drug, event,
                                error="requests 未安装")
            if r.status_code == 404:
                return Evidence(self.name, drug, event, labeled=False,
                                detail="openFDA 无该药品召回记录（404 = 零命中）")
            if r.status_code != 200:
                return Evidence(self.name, drug, event,
                                error=f"HTTP {r.status_code}")
            results = r.json().get("results", [])
            recs: List[Dict[str, Any]] = []
            event_related = False
            for it in results:
                reason = it.get("reason_for_recall", "") or ""
                rn = _norm(reason)
                matched = _match_event(rn, event)
                if matched:
                    event_related = True
                recs.append({
                    "recall_number": it.get("recall_number"),
                    "classification": it.get("classification"),
                    "status": it.get("status"),
                    "recall_initiation_date": it.get("recall_initiation_date"),
                    "reason_for_recall": reason[:200],
                    "matched": matched,
                })
            if not results:
                detail = "openFDA 无该药品召回记录"
                labeled: Optional[bool] = False
            elif event_related:
                detail = (f"存在 {len(results)} 条召回记录，其中召回原因与该事件词匹配"
                          f"（监管已行动，强风险证据）")
                labeled = True
            else:
                detail = (f"存在 {len(results)} 条召回记录，但召回原因与该事件无关"
                          f"（多为质量缺陷，非本事件证据）")
                labeled = False
            return Evidence(self.name, drug, event, labeled=labeled,
                            detail=detail, records=recs)
        except Exception as e:  # noqa: BLE001
            return Evidence(self.name, drug, event, error=str(e)[:200])


# ═════════════════════════════════════════════════════════════════════════════
# 汇总
# ═════════════════════════════════════════════════════════════════════════════

class CozeSource:
    """经 Coze 统一端点的佐证源（薄客户端）。

    query() 外发检索，Coze 端返回与本地 Evidence.to_dict 同构的 JSON，
    本类仅包装为本地 Evidence，使 collect() 的汇总判定逻辑零改动。
    """

    def __init__(self, name: str):
        self.name = name

    def query(self, drug: str, event: str) -> "Evidence":
        if not _COZE_OK or _coze_dispatch is None:
            return Evidence(self.name, drug, event,
                            error="coze_dispatch 不可用")
        try:
            d = _coze_dispatch(self.name, drug, event, run=True)
        except Exception as e:  # noqa: BLE001
            return Evidence(self.name, drug, event, error=str(e)[:200])
        if not isinstance(d, dict):
            return Evidence(self.name, drug, event, error="empty response")
        if d.get("error"):
            return Evidence(self.name, drug, event, error=str(d["error"])[:200])
        return Evidence(
            self.name, drug, event,
            labeled=d.get("labeled"),
            detail=d.get("detail", ""),
            records=d.get("records", []),
            error=d.get("error"),
        )


SOURCE_REGISTRY = {
    "dailymed": DailyMedSource,
    "rxclass": RxClassSource,
    "fda_recall": FdaRecallSource,
}
DEFAULT_SOURCES = ["dailymed", "rxclass", "fda_recall"]


def collect(drug: str, event: str,
            sources: Optional[List[str]] = None) -> Dict[str, Any]:
    """采集佐证证据并给出 labeled/unlabeled 综合判定。"""
    names = sources or DEFAULT_SOURCES
    unknown = [n for n in names if n not in SOURCE_REGISTRY]
    used = [n for n in names if n in SOURCE_REGISTRY]

    evidences: Dict[str, Any] = {}
    labeled_hits: List[str] = []
    errored: List[str] = []
    for n in used:
        src = CozeSource(n) if BACKEND_COZE else SOURCE_REGISTRY[n]()
        ev = src.query(drug, event)
        evidences[n] = ev.to_dict()
        if ev.error:
            errored.append(n)
        elif ev.labeled:
            labeled_hits.append(n)

    n_ok = len(used) - len(errored)
    if not n_ok:
        verdict = "UNDETERMINED"
        rationale = "所有佐证源均不可用，无法判定标注状态"
    elif labeled_hits:
        verdict = "LABELED"
        rationale = f"以下源已记载该事件: {', '.join(labeled_hits)}"
    else:
        verdict = "UNLABELED"
        rationale = (f"{n_ok} 个可用源均未记载该事件 → 潜在未标注信号，"
                     f"按 ICH E2C 应升级优先级")

    return {
        "drug": drug,
        "event": event,
        "verdict": verdict,
        "rationale": rationale,
        "labeled_sources": labeled_hits,
        "sources_used": used,
        "sources_errored": errored,
        "unknown_sources": unknown,
        "blocked_sources": BLOCKED_SOURCES,
        "evidences": evidences,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _ascii(res: Dict[str, Any]) -> str:
    L = [f"佐证型安全性数据源 / labeled-vs-unlabeled 判定",
         f"药物: {res['drug']}    事件: {res['event']}",
         f"结论: {res['verdict']}  —  {res['rationale']}", ""]
    L.append(f"{'Source':<12} {'Labeled':<10} {'Recs':>5}  Detail")
    L.append("-" * 78)
    for n, ev in res["evidences"].items():
        if ev.get("error"):
            L.append(f"{n:<12} {'ERROR':<10} {'-':>5}  {ev['error'][:44]}")
            continue
        lab = {True: "YES", False: "no", None: "unknown"}[ev["labeled"]]
        L.append(f"{n:<12} {lab:<10} {ev['record_count']:>5}  "
                 f"{ev['detail'][:44]}")
    L.append("")
    L.append("未接入源（硬性阻断，本机实测）:")
    for k, v in res["blocked_sources"].items():
        L.append(f"  - {k:<14} {v}")
    return "\n".join(L)


def main() -> int:
    p = argparse.ArgumentParser(
        description="佐证型安全性数据源：判定事件是否已在说明书/知识库标注")
    p.add_argument("--drug", required=True, help="药物名（英文）")
    p.add_argument("--event", required=True, help="不良事件（MedDRA PT 英文）")
    p.add_argument("--sources", default=None,
                   help=f"逗号分隔，可选: {','.join(SOURCE_REGISTRY)}"
                        f"（默认全部）")
    p.add_argument("--format", choices=["json", "ascii"], default="json")
    p.add_argument("--output", default=None, help="输出文件路径")
    p.add_argument("--list-blocked", action="store_true",
                   help="仅列出未接入源及原因后退出")
    p.add_argument("--offline", action="store_true",
                   help="（可选）本机直连检索，不走 Coze；默认外发 Coze（轻本地端）")
    a = p.parse_args()

    global BACKEND_COZE
    BACKEND_COZE = (not a.offline) and _COZE_OK
    if _COZE_OK:
        _coze_set_mode(a.offline)
    else:
        print("[WARN] coze_dispatch 不可用，强制本机直连")

    if a.list_blocked:
        print(json.dumps(BLOCKED_SOURCES, ensure_ascii=False, indent=2))
        return 0

    srcs = [s.strip() for s in a.sources.split(",")] if a.sources else None
    res = collect(a.drug, a.event, srcs)
    out = (json.dumps(res, ensure_ascii=False, indent=2)
           if a.format == "json" else _ascii(res))
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"已写入: {a.output}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
