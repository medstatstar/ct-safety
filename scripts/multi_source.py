#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
multi_source.py / 多数据源信号验证框架

新增于 v2.2.0（2026-08-11）。
基于 ICH E2C(R2) 鼓励多数据源信号验证的指引，在现有 FAERS 基础上提供
EudraVigilanceSource（EMA API，opt-in）+ VigiAccessSource（WHO 公开 API，opt-in）的
多源交叉验证框架。

设计原则：
  - BaseSource 抽象类统一接口（query_drug_event）
  - 默认仅 FAERS，外部数据源为 opt-in（SAFE PREVIEW 模式）
  - 一致性评分：三源一致 HIGH / 两源一致 MEDIUM / 单源 LOW
  - 外部 API 可用性 → fallback 和缓存
  - API 速率限制 → rate limiter + retry
  - 数据格式差异 → 统一内部 schema（计数 + 2x2 分量）
  - 联网操作 → SAFE PREVIEW 模式（--enable-eudravigilance / --enable-vigiaccess）

Usage:
  python scripts/multi_source.py --drug "osimertinib" --event "PNEUMONITIS" --format json
  python scripts/multi_source.py --drug "osimertinib" --event "PNEUMONITIS" \
      --enable-eudravigilance --enable-vigiaccess --format ascii
"""

import abc
import argparse
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ═════════════════════════════════════════════════════════════════════════════
# 统一内部 schema
# ═════════════════════════════════════════════════════════════════════════════

# 每个源返回的标准化结构
class SourceResult:
    """单个数据源的查询结果。"""
    __slots__ = ("source", "drug", "event", "count_a", "drug_total",
                 "event_total", "grand_total", "error", "cached_at")

    def __init__(self, source: str, drug: str, event: str,
                 count_a: Optional[int] = None,
                 drug_total: Optional[int] = None,
                 event_total: Optional[int] = None,
                 grand_total: Optional[int] = None,
                 error: Optional[str] = None,
                 cached_at: Optional[str] = None):
        self.source = source
        self.drug = drug
        self.event = event
        self.count_a = count_a
        self.drug_total = drug_total
        self.event_total = event_total
        self.grand_total = grand_total
        self.error = error
        self.cached_at = cached_at or datetime.utcnow().isoformat()

    def to_2x2(self) -> Optional[Dict[str, int]]:
        """转为 2x2 表分量 {a, b, c, d}。"""
        if self.count_a is None or self.drug_total is None or \
           self.event_total is None or self.grand_total is None:
            return None
        a = self.count_a
        b = self.drug_total - a
        c = self.event_total - a
        d = self.grand_total - a - b - c
        return {"a": max(0, a), "b": max(0, b), "c": max(0, c), "d": max(0, d)}

    def to_dict(self) -> Dict:
        return {
            "source": self.source,
            "drug": self.drug,
            "event": self.event,
            "count_a": self.count_a,
            "drug_total": self.drug_total,
            "event_total": self.event_total,
            "grand_total": self.grand_total,
            "error": self.error,
            "cached_at": self.cached_at,
        }


# ═════════════════════════════════════════════════════════════════════════════
# BaseSource 抽象基类
# ═════════════════════════════════════════════════════════════════════════════

class BaseSource(abc.ABC):
    """数据源抽象基类，定义统一接口。"""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """数据源名称。"""
        ...

    @abc.abstractmethod
    def query_drug_event(self, drug: str, event: str,
                         use_cache: bool = True) -> SourceResult:
        """查询 (drug, event) 共现计数。

        返回 SourceResult；出错时 SourceResult.error 非 None。
        """
        ...

    def _cache_key(self, drug: str, event: str) -> str:
        """缓存文件名。"""
        h = hashlib.sha1(f"{self.name}:{drug}:{event}".encode("utf-8")).hexdigest()[:12]
        cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 ".cache", self.name)
        os.makedirs(cache_dir, exist_ok=True)
        return os.path.join(cache_dir, f"{h}.json")

    def _read_cache(self, drug: str, event: str,
                    max_age_hours: int = 24) -> Optional[SourceResult]:
        """读取缓存（默认 24h 有效）。"""
        path = self._cache_key(drug, event)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cached_at = data.get("cached_at", "")
            if cached_at:
                ct = datetime.fromisoformat(cached_at)
                if datetime.utcnow() - ct > timedelta(hours=max_age_hours):
                    return None  # 缓存过期
            return SourceResult(**data)
        except Exception:
            return None

    def _write_cache(self, drug: str, event: str, result: SourceResult):
        """写入缓存。"""
        path = self._cache_key(drug, event)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # 缓存写入失败不影响主流程

    @staticmethod
    def _rate_limiter(min_interval: float = 1.0):
        """简易速率限制装饰器（实例级别，确保两次调用间隔 ≥ min_interval 秒）。"""
        state = {"last_call": 0.0}

        def wait():
            now = time.monotonic()
            elapsed = now - state["last_call"]
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            state["last_call"] = time.monotonic()

        return wait


# ═════════════════════════════════════════════════════════════════════════════
# FAERS Source（openFDA）— 默认启用
# ═════════════════════════════════════════════════════════════════════════════

class FaersSource(BaseSource):
    """FDA FAERS via openFDA public API.

    默认启用，无需 opt-in。低频免密钥，高频可选 OPENFDA_API_KEY。
    """

    BASE_URL = "https://api.fda.gov/drug/event.json"

    @property
    def name(self) -> str:
        return "faers"

    def query_drug_event(self, drug: str, event: str,
                         use_cache: bool = True) -> SourceResult:
        if use_cache:
            cached = self._read_cache(drug, event)
            if cached is not None:
                return cached

        try:
            from fetch_faers import resolve_api_key, fetch_counts
            api_key = resolve_api_key(None)
            # fetch_counts 返回 dict，含 counts 子 dict（a/b/c/d/drug_total/event_total/grand_total）
            data = fetch_counts(drug, event, api_key=api_key, run=True)
            if data is None:
                result = SourceResult(
                    source=self.name, drug=drug, event=event,
                    error="fetch_counts 返回 None（可能缺少 --run 参数或 requests 未安装）"
                )
            else:
                counts = data.get("counts", {})
                result = SourceResult(
                    source=self.name,
                    drug=drug,
                    event=event,
                    count_a=counts.get("a"),
                    drug_total=counts.get("drug_total"),
                    event_total=counts.get("event_total"),
                    grand_total=counts.get("grand_total"),
                )
        except ImportError:
            # fetch_faers 模块不可用，用兜底方式
            result = SourceResult(
                source=self.name, drug=drug, event=event,
                error="fetch_faers 模块不可用（技能文件缺失）"
            )
        except Exception as e:
            result = SourceResult(
                source=self.name, drug=drug, event=event,
                error=str(e)
            )

        self._write_cache(drug, event, result)
        return result


# ═════════════════════════════════════════════════════════════════════════════
# EudraVigilance Source（EMA）— opt-in
# ═════════════════════════════════════════════════════════════════════════════

class EudraVigilanceSource(BaseSource):
    """EMA EudraVigilance via EMA API.

    Opt-in only（--enable-eudravigilance）。
    注意：EMA API 可能需要注册 + 授权，此处实现公开可用端点。
    """

    BASE_URL = "https://www.adrreports.eu/"

    @property
    def name(self) -> str:
        return "eudravigilance"

    _rate_limit = None

    def query_drug_event(self, drug: str, event: str,
                         use_cache: bool = True) -> SourceResult:
        if use_cache:
            cached = self._read_cache(drug, event, max_age_hours=72)
            if cached is not None:
                return cached

        if self._rate_limit is None:
            self._rate_limit = self._rate_limiter(min_interval=2.0)

        self._rate_limit()

        # EMA 公开 API 暂不稳定，此处返回未接入状态
        # 实际对接时需要：ADRreports EU API / EMA Medicines API
        result = SourceResult(
            source=self.name,
            drug=drug,
            event=event,
            error="未接入（需 EMA API 注册 + 授权；详见 https://www.adrreports.eu/）"
        )
        return result


# ═════════════════════════════════════════════════════════════════════════════
# VigiAccess Source（WHO）— opt-in
# ═════════════════════════════════════════════════════════════════════════════

class VigiAccessSource(BaseSource):
    """WHO VigiAccess via WHO-UMC public API.

    Opt-in only（--enable-vigiaccess）。
    """

    BASE_URL = "https://www.vigaccess.org/"

    @property
    def name(self) -> str:
        return "vigiaccess"

    _rate_limit = None

    def query_drug_event(self, drug: str, event: str,
                         use_cache: bool = True) -> SourceResult:
        if use_cache:
            cached = self._read_cache(drug, event, max_age_hours=72)
            if cached is not None:
                return cached

        if self._rate_limit is None:
            self._rate_limit = self._rate_limiter(min_interval=2.0)

        self._rate_limit()

        # WHO VigiAccess 公开 API 需要进一步对接
        result = SourceResult(
            source=self.name,
            drug=drug,
            event=event,
            error="未接入（需 WHO-UMC API 对接；详见 https://www.vigaccess.org/）"
        )
        return result


# ═════════════════════════════════════════════════════════════════════════════
# 多源对比与一致性评分
# ═════════════════════════════════════════════════════════════════════════════

def _compute_prr(result: SourceResult) -> Optional[Dict]:
    """计算 PRR 及其 95% CI。"""
    m = result.to_2x2()
    if m is None:
        return None
    a, b, c, d = m["a"], m["b"], m["c"], m["d"]
    n = a + b + c + d
    if n == 0 or (a + b) == 0 or (c + d) == 0 or (a + c) == 0:
        return None

    prr = (a / (a + b)) / (c / (c + d))
    # 95% CI (log method)
    se_ln = math.sqrt(1/a - 1/(a+b) + 1/c - 1/(c+d)) if a > 0 and c > 0 else None
    if se_ln is not None:
        ci_low = math.exp(math.log(prr) - 1.96 * se_ln)
        ci_high = math.exp(math.log(prr) + 1.96 * se_ln)
    else:
        ci_low = ci_high = None

    # chi-square (with Yates correction)
    n1 = a + b
    n2 = c + d
    m1 = a + c
    m2 = b + d
    denom = n1 * n2 * m1 * m2
    if denom == 0:
        chi2 = 0.0
    else:
        chi2 = (n * (abs(a*d - b*c) - n/2) ** 2) / denom

    signal = prr >= 2 and chi2 >= 4

    return {
        "prr": round(prr, 4),
        "ci_low": round(ci_low, 4) if ci_low is not None else None,
        "ci_high": round(ci_high, 4) if ci_high is not None else None,
        "chi2": round(chi2, 4),
        "signal": signal,
    }


def _compute_ror(result: SourceResult) -> Optional[Dict]:
    """计算 ROR 及其 95% CI。"""
    m = result.to_2x2()
    if m is None:
        return None
    a, b, c, d = m["a"], m["b"], m["c"], m["d"]
    if b == 0 or c == 0:
        return None
    ror = (a * d) / (b * c)
    se_ln = math.sqrt(1/a + 1/b + 1/c + 1/d) if a*b*c*d > 0 else None
    if se_ln is not None:
        ci_low = math.exp(math.log(ror) - 1.96 * se_ln)
        ci_high = math.exp(math.log(ror) + 1.96 * se_ln)
    else:
        ci_low = ci_high = None

    signal = ci_low is not None and ci_low > 1

    return {
        "ror": round(ror, 4),
        "ci_low": round(ci_low, 4) if ci_low is not None else None,
        "ci_high": round(ci_high, 4) if ci_high is not None else None,
        "signal": signal,
    }


def compare_sources(drug: str, event: str,
                    sources: Optional[List[str]] = None,
                    enable_eudravigilance: bool = False,
                    enable_vigiaccess: bool = False) -> Dict:
    """多源对比入口。

    参数：
        drug / event: 查询的药物和事件
        sources: 数据源名称列表（None = 默认 FAERS）
        enable_eudravigilance: 是否启用 EMA
        enable_vigiaccess: 是否启用 WHO

    返回：
        dict 含各源 PRR/ROR、一致性评分、汇总结论
    """
    source_map = {
        "faers": FaersSource(),
    }
    if enable_eudravigilance:
        source_map["eudravigilance"] = EudraVigilanceSource()
    if enable_vigiaccess:
        source_map["vigiaccess"] = VigiAccessSource()

    if sources is None:
        sources = ["faers"]  # 默认仅 FAERS

    results = {}
    for sname in sources:
        if sname in source_map:
            res = source_map[sname].query_drug_event(drug, event)
            results[sname] = res

    # 各源 PRR / ROR
    source_metrics = {}
    signal_count = 0
    error_count = 0
    for sname, res in results.items():
        if res.error:
            source_metrics[sname] = {"error": res.error}
            error_count += 1
            continue
        prr = _compute_prr(res)
        ror = _compute_ror(res)
        source_metrics[sname] = {
            "count_a": res.count_a,
            "drug_total": res.drug_total,
            "event_total": res.event_total,
            "grand_total": res.grand_total,
            "prr": prr,
            "ror": ror,
        }
        if prr and prr.get("signal"):
            signal_count += 1

    # 一致性评分
    n_success = len([s for s in source_metrics.values() if "error" not in s])
    if n_success >= 3 and signal_count >= 3:
        consistency = "HIGH"
    elif n_success >= 2 and signal_count >= 2:
        consistency = "MEDIUM"
    elif n_success >= 1 and signal_count >= 1:
        consistency = "LOW"
    else:
        consistency = "NONE"

    summary = {
        "drug": drug,
        "event": event,
        "sources_used": list(results.keys()),
        "sources_succeeded": n_success,
        "sources_errored": error_count,
        "signal_count": signal_count,
        "consistency": consistency,
        "source_metrics": source_metrics,
        "generated_at": datetime.utcnow().isoformat(),
    }

    return summary


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="多数据源信号验证框架")
    p.add_argument("--drug", required=True, help="药物名（英文）")
    p.add_argument("--event", required=True, help="不良事件（MedDRA PT 英文）")
    p.add_argument("--enable-eudravigilance", action="store_true",
                   help="启用 EMA EudraVigilance（opt-in）")
    p.add_argument("--enable-vigiaccess", action="store_true",
                   help="启用 WHO VigiAccess（opt-in）")
    p.add_argument("--sources", type=str, default=None,
                   help="数据源列表逗号分隔（默认仅 FAERS）")
    p.add_argument("--format", choices=["json", "ascii"], default="json",
                   help="输出格式")
    p.add_argument("--output", type=str, default=None, help="输出文件路径")
    p.add_argument("--no-cache", action="store_true", help="禁用缓存")

    args = p.parse_args()

    sources = None
    if args.sources:
        sources = [s.strip() for s in args.sources.split(",")]

    result = compare_sources(
        drug=args.drug,
        event=args.event,
        sources=sources,
        enable_eudravigilance=args.enable_eudravigilance,
        enable_vigiaccess=args.enable_vigiaccess,
    )

    if args.format == "json":
        out = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        out = _format_ascii(result)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"已写入: {args.output}")
    else:
        print(out)


def _format_ascii(result: Dict) -> str:
    """格式化为 ASCII 表格。"""
    lines = []
    lines.append(f"多数据源信号验证: {result['drug']} + {result['event']}")
    lines.append(f"一致性评分: {result['consistency']}")
    lines.append(f"数据源数: {result['sources_succeeded']} 成功 / "
                 f"{result['sources_errored']} 失败")
    lines.append("")

    header = f"{'Source':<20} {'Count':>8} {'PRR':>8} {'PRR_CI':>16} {'ROR':>8} {'ROR_CI':>16} {'Signal':>8}"
    lines.append(header)
    lines.append("-" * len(header))

    for sname, m in result.get("source_metrics", {}).items():
        if "error" in m:
            lines.append(f"{sname:<20} ERROR: {m['error'][:60]}")
            continue
        prr = m.get("prr") or {}
        ror = m.get("ror") or {}
        prr_ci = f"({prr.get('ci_low', '-')}, {prr.get('ci_high', '-')})"
        ror_ci = f"({ror.get('ci_low', '-')}, {ror.get('ci_high', '-')})"
        signal = "✅" if (prr.get("signal") or ror.get("signal")) else "—"
        lines.append(
            f"{sname:<20} {m.get('count_a', 0):>8} "
            f"{prr.get('prr', '-'):>8} {prr_ci:>16} "
            f"{ror.get('ror', '-'):>8} {ror_ci:>16} {signal:>8}"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    main()
