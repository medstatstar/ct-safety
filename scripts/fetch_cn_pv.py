#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fetch_cn_pv.py / 中国官方药物警戒通报检索 (v2)

Scrapes the public columns of 国家药品不良反应监测中心
(https://www.cdr-adr.org.cn) and searches them by drug (Chinese / English) and
event keywords, returning matching official pharmacovigilance bulletins.

Covered columns (all on cdr-adr.org.cn, no WAF, public):
  - 药物警戒快讯 (Drug Safety Newsletter)
  - 数据报告    (Data Reports, incl. annual / focused monitoring reports)
  - 通知通告    (Notices, incl. annual-report publication)
  - 器械警戒快讯 (Medical-device Safety Newsletter)
  - 化妆品警戒快讯 (Cosmetics Safety Newsletter)

v2 improvements (2026-08-31):
  - Pagination: traverse listing pages (max_pages per column), not just page 1
  - Date window: --since / --until filter (meta PubDate with body-date fallback)
  - Keyword expansion: auto-resolve Chinese aliases via references/drug_name_map.json
    (en -> zh reverse lookup + zh -> en forward lookup); --drug accepts comma-separated aliases
  - Event synonyms: small built-in synonym groups (肺炎/间质性肺炎/ILD, 肝损伤/DILI, ...)
  - Evidence tier per hit: 通报专文 (drug in TITLE) > 数据报告 (column=数据报告) > 提及 (other)
  - Polite scraping: 0.6s sleep between requests + one backoff retry on 5xx
  - Local cache: cn_pv_cache.json keyed by sha1(query) — repeat runs don't re-scrape

IMPORTANT — scope & method limits:
  - These are NARRATIVE official bulletins, NOT individual case reports. They
    cannot be used to build a 2x2 table (no per drug-event counts). Do NOT feed
    them into disproportionality analysis (PRR / ROR / IC) — that would be a
    methodological error. They serve only as QUALITATIVE corroboration of a
    FAERS signal ("FAERS shows ROR>1; China's official bulletin also named the risk").
  - NMPA main site (nmpa.gov.cn, incl. 《药品不良反应信息通报》) is blocked by a
    CDN/WAF (HTTP 412) — not fetched locally. Use the Coze browser channel
    (adapters/nmpa_coze.py) for NMPA coverage instead.
  - Only public pages are fetched; zero confidential data or information input
    (B-tier: ordinary input + public retrieval). Default SAFE PREVIEW — network runs only with explicit --run.

Reads only public data; zero confidential data or information input.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    requests = None

BASE = "https://www.cdr-adr.org.cn"

# (display name, listing path on cdr-adr.org.cn)
COLUMNS = [
    ("药物警戒快讯", "/drug_1/aqjs_1/drug_aqjs_jjkx/"),
    ("数据报告",     "/drug_1/aqjs_1/drug_aqjs_sjbg/"),
    ("通知通告",     "/tzgg_home/"),
    ("器械警戒快讯", "/ylqx_1/Medical_aqjs/Medical_aqjs_jjkx/"),
    ("化妆品警戒快讯", "/hzp_1/Cosmetics_aqjs/Cosmetics_aqjs_jjkx/"),
]

# 药名词表（技能根 references/drug_name_map.json；缺失时静默降级为不扩展）
_NAME_MAP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "references", "drug_name_map.json")

# 事件同义词组（命中任一同义词即视为该事件命中；snippet 关键词取实际命中的词）
EVENT_SYNONYMS = {
    "肺炎": ["肺炎", "间质性肺炎", "间质性肺病", "肺毒性", "ILD"],
    "肝损伤": ["肝损伤", "肝功能异常", "药物性肝损伤", "肝毒性", "DILI", "转氨酶升高"],
    "肾损伤": ["肾损伤", "肾功能异常", "肾毒性", "急性肾损伤"],
    "心脏毒性": ["心脏毒性", "心力衰竭", "心肌损伤", "心律失常", "QT延长"],
    "皮肤反应": ["皮疹", "皮肤反应", "Stevens-Johnson", "中毒性表皮坏死", "SJS", "TEN"],
    "过敏反应": ["过敏反应", "超敏反应", "过敏性休克"],
    "骨髓抑制": ["骨髓抑制", "中性粒细胞减少", "白细胞减少", "血小板减少", "贫血"],
    "胃肠道反应": ["胃肠道反应", "腹泻", "恶心", "呕吐", "消化道出血"],
    "神经毒性": ["神经毒性", "周围神经病变", "神经病变"],
    "血栓": ["血栓", "静脉血栓", "肺栓塞", "血栓栓塞"],
    "输液反应": ["输液反应", "输注相关反应", "注射部位反应"],
    "免疫相关不良反应": ["免疫相关不良反应", "irAE", "免疫不良反应"],
}

# 佐证等级（tier）
TIER_BULLETIN = "通报专文"      # 标题即点名该药物（专文通报）
TIER_DATA_REPORT = "数据报告"   # 数据报告栏目命中
TIER_MENTION = "提及"          # 其他栏目正文提及


def load_name_map():
    """加载 drug_name_map.json -> {zh2en: {zh: [en...]}, en2zh: {en_lower: [zh...]}} 双向索引。"""
    idx = {"zh2en": {}, "en2zh": {}}
    try:
        with open(_NAME_MAP_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return idx
    for zh, ens in raw.items():
        if zh.startswith("_") or not isinstance(ens, list):
            continue
        idx["zh2en"][zh] = [e for e in ens if isinstance(e, str)]
        for e in ens:
            if isinstance(e, str):
                idx["en2zh"].setdefault(e.lower(), []).append(zh)
    return idx


def expand_drug_keywords(drug, drug_en=None, name_map=None):
    """把用户输入的药名扩展为关键词组：用户原词 + 词表反向/正向候选。

    drug 可为逗号分隔多别名（如 "奥希替尼,osimertinib,泰瑞沙"）。
    """
    kws = []
    for part in (drug or "").split(","):
        p = part.strip()
        if p:
            kws.append(p)
    if drug_en and drug_en.strip():
        kws.append(drug_en.strip())
    if name_map is None:
        name_map = load_name_map()
    for k in list(kws):
        low = k.lower()
        for cand in name_map["zh2en"].get(k, []) + name_map["en2zh"].get(low, []):
            if cand and cand not in kws:
                kws.append(cand)
    return kws


def expand_event_keywords(event):
    """事件词 -> [原词] + 同义词组命中词（组内任一原词出现即整组生效）。"""
    if not event or not event.strip():
        return []
    e = event.strip()
    out = [e]
    for keys, syns in EVENT_SYNONYMS.items():
        if e == keys or e in syns:
            for s in syns:
                if s.strip() and s not in out:
                    out.append(s.strip())
            break
    return [x for x in out if x]


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

WAF_KW = ["安全狗", "SafeDog", "访问被拒绝", "Access Denied", "验证码",
          "captcha", "WAF", "拦截", "请输入验证码", "human verification"]

POLITE_SLEEP = 0.6  # 秒；请求间隔（礼貌抓取）


def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    return s


def _get(session, url, timeout=25):
    """GET + 5xx 一次退避重试（礼貌抓取）。412 视为 WAF，直接抛错不重试。"""
    last = None
    for attempt in (1, 2):
        r = session.get(url, timeout=timeout)
        # 中文站若未在 Content-Type 声明 charset，requests 默认按 ISO-8859-1 解码 →
        # 全篇中文乱码、命中率直接归零且无任何报错。此处强制嗅探真实编码兜底。
        if not r.encoding or r.encoding.lower() in ("iso-8859-1", "latin-1"):
            r.encoding = r.apparent_encoding or "utf-8"
        if r.status_code == 200:
            return r
        last = r
        if r.status_code == 412:
            raise RuntimeError("HTTP 412 (CDN/WAF blocked): %s" % url)
        if 500 <= r.status_code < 600 and attempt == 1:
            time.sleep(2.0)
            continue
        break
    last.raise_for_status()
    return last


# 列表页链接：相对/绝对、带引号或不带引号的 .html/.htm 链接
# （放宽自 v1 只匹配 href="./xxx.html" 相对路径）
_ART_HREF_RE = re.compile(
    r'<a[^>]*?href=["\']?([^"\'\s>]+?\.html?)["\']?[^>]*?>(.*?)</a>', re.S | re.I)
_PAGINATION_HREF_RE = re.compile(r"^index(_\d+)?\.html?$", re.I)


def _listing_page_urls(col_path, page):
    """cdr-adr（TRS CMS）列表分页 URL 约定：page 1 = 栏目根；page N = index_(N-1).html。"""
    if page <= 1:
        return BASE + col_path
    return urljoin(BASE + col_path, "index_%d.html" % (page - 1))


def list_articles(session, col_path, max_per=10, max_pages=1):
    """Return up to max_per article stubs {url,title,column_path}; traverse max_pages listing pages."""
    arts, seen = [], set()
    for page in range(1, max(1, max_pages) + 1):
        url = _listing_page_urls(col_path, page)
        try:
            r = _get(session, url)
        except Exception as e:
            if page == 1:
                raise  # 首页失败 = 栏目不可用，交由上层 WARN
            break        # 翻页失败 = 到头了，静默结束
        raw = _ART_HREF_RE.findall(r.text)
        new_cnt = 0
        for href, txt in raw:
            if _PAGINATION_HREF_RE.match(href.strip().rsplit("/", 1)[-1]):
                continue  # 跳过分页导航自身
            title = re.sub(r'<[^>]+>', '', txt).strip()
            if not title or len(title) < 4:
                continue
            u = urljoin(url, href)
            if u in seen:
                continue
            seen.add(u)
            arts.append({"url": u, "title": title, "column_path": col_path})
            new_cnt += 1
            if len(arts) >= max_per:
                return arts
        time.sleep(POLITE_SLEEP)
        if new_cnt == 0:
            break  # 该页无新文章 = 无更多分页
    return arts


def _extract_body(html):
    """Strip scripts/styles/CSS noise and return readable text of an article page."""
    html = re.sub(r'<script.*?</script>|<style.*?</style>', '', html, flags=re.S)
    html = re.sub(r'<!--.*?-->', ' ', html, flags=re.S)
    body = None
    # Pattern 1: class="contentbox..." (quoted class)
    m = re.search(r'class="([^"]*contentbox[^"]*)"[^>]*>(.*?)(?:</div>\s*</div>|</div>\s*</td>)', html, re.S | re.I)
    if m:
        body = m.group(2)
    else:
        # Pattern 2: id="content"
        m = re.search(r'id="content"[^>]*>(.*?)</div>', html, re.S | re.I)
        if m:
            body = m.group(1)
        else:
            # Pattern 3: class=TRS_Editor (quoted OR unquoted — cdr-adr.org.cn uses unquoted)
            m = re.search(r'class=["\']?TRS_Editor["\']?[^>]*>(.*)', html, re.S | re.I)
            if m:
                body = m.group(1)
                body_end = body.find('</body>')
                if body_end > 0:
                    body = body[:body_end]
    if body is None:
        body = html
    txt = re.sub(r'<[^>]+>', ' ', body)
    txt = re.sub(r'/\*.*?\*/', ' ', txt, flags=re.S)  # css comments
    txt = re.sub(r'&[a-z]+;', ' ', txt)               # html entities
    txt = re.sub(r'\s+', ' ', txt).strip()
    return txt


_BODY_DATE_RE = re.compile(r"(20\d{2})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})")


def _fallback_date(text):
    """正文日期兜底：取正文中第一个 20xx-xx-xx 形态日期（无则 None）。"""
    m = _BODY_DATE_RE.search(text or "")
    if not m:
        return None
    y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
    if 1 <= mo <= 12 and 1 <= d <= 31:
        return "%s-%02d-%02d" % (y, mo, d)
    return None


def fetch_article(session, art):
    r = _get(session, art["url"])
    html = r.text
    m = re.search(r'<meta[^>]+name="PubDate"[^>]+content="([^"]+)"', html, re.I)
    date = m.group(1)[:10] if m else None
    body = _extract_body(html)
    if not date:
        date = _fallback_date(body)
    time.sleep(POLITE_SLEEP)
    return {"url": art["url"], "title": art["title"],
            "column_path": art["column_path"], "date": date, "body": body}


def _make_snippet(text, keywords, width=120):
    """取全部命中关键词中最早两处的覆盖窗口，尽量覆盖多个命中点。"""
    low = text.lower()
    positions = []
    for kw in keywords:
        if not kw:
            continue
        i = low.find(kw.lower())
        if i >= 0:
            positions.append(i)
    if not positions:
        return text[:width]
    positions = sorted(set(positions))[:2]
    start = max(0, positions[0] - width // 3)
    end = max(positions[-1] + width, start + width)
    return text[start:end]


def _grade_hit(title_low, col_name, drug_hits):
    """佐证等级：标题点名药物（通报专文）> 数据报告栏目 > 一般提及。"""
    if any(d and d.lower() in title_low for d in drug_hits):
        return TIER_BULLETIN
    if col_name == "数据报告" and drug_hits:
        return TIER_DATA_REPORT
    return TIER_MENTION


def _cache_path(out):
    """缓存文件与 out 同目录（out 为 None 时返回 None）。"""
    if not out:
        return None
    return os.path.join(os.path.dirname(os.path.abspath(out)) or ".",
                        "cn_pv_cache.json")


def _cache_key(query):
    return hashlib.sha1(json.dumps(query, sort_keys=True,
                                   ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _cache_load(path, key):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get(key)
    except Exception:
        return None


def _cache_save(path, key, result):
    try:
        data = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        data[key] = result
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("[WARN] cache write failed: %s" % e)


def _coverage_note(stats, total_columns):
    """抓取覆盖率说明：让「0 命中」与「抓取失败」在报告层可区分。"""
    parts = ["扫描 %d 篇 / %d 栏目" % (stats.get("scanned", 0), total_columns)]
    if stats.get("failed_columns"):
        names = "、".join(c["column"] for c in stats["failed_columns"])
        parts.append("⚠️ %d 个栏目抓取失败（%s）——这些栏目未覆盖"
                     % (len(stats["failed_columns"]), names))
    if stats.get("failed_articles"):
        parts.append("⚠️ %d 篇文章正文抓取失败" % stats["failed_articles"])
    if stats.get("empty_columns"):
        parts.append("%d 个栏目列表为空（%s）"
                     % (len(stats["empty_columns"]), "、".join(stats["empty_columns"])))
    if stats.get("skipped_window"):
        parts.append("%d 条因日期窗被剔除" % stats["skipped_window"])
    return "；".join(parts) + "。"


def search(drug_zh, drug_en=None, event=None, terms=None, max_per=10,
           run=False, out=None, max_pages=1, since=None, until=None,
           use_cache=True):
    """检索 cdr-adr.org.cn 公开栏目。

    max_per: 每栏目最多抓取文章数；max_pages: 每栏目遍历列表页数（1=仅首页，兼容 v1）。
    since/until: 'YYYY' 或 'YYYY-MM-DD' 日期窗（含边界；无日期文章保留、降级展示不漏检）。
    use_cache: 结果按查询指纹缓存到 cn_pv_cache.json（与 out 同目录）。
    """
    if requests is None:
        raise RuntimeError("requests not installed: pip install requests")

    drug_kw = expand_drug_keywords(drug_zh, drug_en)
    event_kw = expand_event_keywords(event)
    extra = [t.strip() for t in (terms or []) if t and t.strip()]

    query = {"drug": drug_kw, "event": event_kw, "terms": extra,
             "max_per": max_per, "max_pages": max_pages,
             "since": since, "until": until}
    cpath = _cache_path(out) if use_cache else None
    if cpath and run:
        cached = _cache_load(cpath, _cache_key(query))
        if cached is not None:
            print("[CACHE] cn_pv hit (%s) — reuse cached result" % _cache_key(query))
            cached = dict(cached)
            cached["from_cache"] = True
            if cached.get("_cached_for_out") != out:
                with open(out, "w", encoding="utf-8") as f:
                    json.dump(cached, f, ensure_ascii=False, indent=2)
                print("[OK] wrote", out, "(hits=%d, from cache)" % cached["hit_count"])
            return cached

    if not run:
        print("[PREVIEW] would scrape cdr-adr.org.cn for drug=%r (en=%r) event=%r "
              "terms=%r across %d columns x %d latest x %d page(s) "
              "(use --run to execute)"
              % (drug_zh, drug_en, event, terms, len(COLUMNS), max_per, max_pages))
        return None

    session = _session()

    def _in_window(date):
        if not date:
            return True  # 无日期文章保留（降级展示），不在日期维度上漏检
        d = date[:10]
        if since and d < (since if len(since) > 4 else since + "-01-01"):
            return False
        if until and d > (until if len(until) > 4 else until + "-12-31"):
            return False
        return True

    hits = []
    stats = {"scanned": 0, "skipped_window": 0,
             "failed_columns": [], "failed_articles": 0,
             "empty_columns": []}
    for col_name, col_path in COLUMNS:
        try:
            arts = list_articles(session, col_path, max_per, max_pages)
        except Exception as e:
            # 栏目整体不可达：记入 stats（此前只 print，导致「抓取失败」与「真的 0 命中」不可区分）
            print("[WARN] column %s skipped: %s" % (col_name, e))
            stats["failed_columns"].append(
                {"column": col_name, "error": str(e)[:200]})
            continue
        if not arts:
            stats["empty_columns"].append(col_name)
        for art in arts:
            stats["scanned"] += 1
            try:
                a = fetch_article(session, art)
            except Exception as e:
                print("[WARN] article %s skipped: %s" % (art.get("url"), e))
                stats["failed_articles"] += 1
                continue
            text = (a["title"] + "\n" + a["body"])
            low = text.lower()
            title_low = a["title"].lower()
            drug_hit = [k for k in drug_kw if k and k.lower() in low]
            event_hit = [k for k in event_kw if k and k.lower() in low]
            extra_hit = [k for k in extra if k and k.lower() in low]
            # matching rule: drug required; event required if provided; extra required if provided
            matched = bool(drug_hit)
            if event_kw:
                matched = matched and bool(event_hit)
            if extra:
                matched = matched and bool(extra_hit)
            if not matched:
                continue
            if not _in_window(a.get("date")):
                stats["skipped_window"] += 1
                continue
            tier = _grade_hit(title_low, col_name, drug_hit)
            snippet_kw = drug_hit + event_hit + extra_hit
            hits.append({
                "title": a["title"],
                "column": col_name,
                "tier": tier,
                "date": a["date"],
                "url": a["url"],
                "snippet": _make_snippet(text, snippet_kw),
                "matched_keywords": sorted(set(snippet_kw)),
            })

    # 排序：佐证等级优先（专文 > 数据报告 > 提及），同级内日期新在前（稳定排序）
    tier_order = {TIER_BULLETIN: 0, TIER_DATA_REPORT: 1, TIER_MENTION: 2}
    hits.sort(key=lambda h: h.get("date") or "0000-00-00", reverse=True)
    hits.sort(key=lambda h: tier_order.get(h.get("tier"), 9))

    result = {
        "source": "CN-PV (cdr-adr.org.cn)",
        "note": ("定性叙事通报检索；非个案计数，不可做 disproportionality (PRR/ROR/IC) 分析。"
                 "仅作 FAERS 量化信号的定性佐证。NMPA《药品不良反应信息通报》主站被 WAF 拦截，"
                 "不在本模块覆盖内（可用 adapters/nmpa_coze.py 的 Coze 浏览器通道检索）。"),
        "query": {"drug_raw": drug_zh, "drug_en": drug_en,
                  "event": event, "terms": terms},
        "expanded_keywords": {"drug": drug_kw, "event": event_kw, "extra": extra},
        "searched_columns": [c[0] for c in COLUMNS],
        "max_per_column": max_per,
        "max_pages": max_pages,
        "since": since, "until": until,
        "stats": stats,
        # degraded=True 表示抓取不完整（有栏目失败/有文章失败）→ 此时 0 命中
        # 不可解读为"官方无相关通报"，报告层须显式提示。
        "degraded": bool(stats["failed_columns"] or stats["failed_articles"]),
        "coverage_note": _coverage_note(stats, len(COLUMNS)),
        "tier_counts": {t: sum(1 for h in hits if h.get("tier") == t)
                        for t in (TIER_BULLETIN, TIER_DATA_REPORT, TIER_MENTION)},
        "hit_count": len(hits),
        "hits": hits,
    }
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print("[OK] wrote", out, "(hits=%d)" % len(hits))
        result["_cached_for_out"] = out
    if cpath:
        _cache_save(cpath, _cache_key(query), result)
    result.pop("_cached_for_out", None)
    return result


def main():
    ap = argparse.ArgumentParser(
        description="Search China official PV bulletins (cdr-adr.org.cn). Qualitative only.")
    ap.add_argument("--drug", required=True,
                    help="drug name(s), Chinese preferred; comma-separated aliases OK "
                         "(e.g. 奥希替尼 or 奥希替尼,osimertinib,泰瑞沙)")
    ap.add_argument("--drug-en", help="drug English name / synonym (e.g. osimertinib); "
                                      "auto-expanded via drug_name_map.json")
    ap.add_argument("--event", help="event keyword (e.g. 肝损伤); synonym group auto-expanded")
    ap.add_argument("--terms", nargs="*", help="extra AND keywords")
    ap.add_argument("--max-per-column", type=int, default=10,
                    help="max articles scraped per column (default 10)")
    ap.add_argument("--max-pages", type=int, default=1,
                    help="listing pages to traverse per column (default 1 = latest page only, "
                         "v1-compatible; use 3-5 for history coverage)")
    ap.add_argument("--since", help="date window start, YYYY or YYYY-MM-DD")
    ap.add_argument("--until", help="date window end, YYYY or YYYY-MM-DD")
    ap.add_argument("--no-cache", action="store_true",
                    help="disable cn_pv_cache.json reuse")
    ap.add_argument("--run", action="store_true", help="execute network scrape")
    ap.add_argument("--out", help="output JSON path")
    args = ap.parse_args()

    res = search(args.drug, args.drug_en, args.event, args.terms,
                 args.max_per_column, args.run, args.out,
                 max_pages=args.max_pages, since=args.since, until=args.until,
                 use_cache=not args.no_cache)
    if res and not args.out:
        print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
