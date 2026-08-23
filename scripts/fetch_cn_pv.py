#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fetch_cn_pv.py / 中国官方药物警戒通报检索

Scrapes the public columns of 国家药品不良反应监测中心
(https://www.cdr-adr.org.cn) and searches them by drug (Chinese / English) and
event keywords, returning matching official pharmacovigilance bulletins.

Covered columns (all on cdr-adr.org.cn, no WAF, public):
  - 药物警戒快讯 (Drug Safety Newsletter)
  - 数据报告    (Data Reports, incl. annual / focused monitoring reports)
  - 通知通告    (Notices, incl. annual-report publication)
  - 器械警戒快讯 (Medical-device Safety Newsletter)
  - 化妆品警戒快讯 (Cosmetics Safety Newsletter)

IMPORTANT — scope & method limits:
  - These are NARRATIVE official bulletins, NOT individual case reports. They
    cannot be used to build a 2x2 table (no per drug-event counts). Do NOT feed
    them into disproportionality analysis (PRR / ROR / IC) — that would be a
    methodological error. They serve only as QUALITATIVE corroboration of a
    FAERS signal ("FAERS shows ROR>1; China's official bulletin also named the risk").
  - NMPA main site (nmpa.gov.cn, incl. 《药品不良反应信息通报》) is blocked by a
    CDN/WAF (HTTP 412) — not forcibly bypassed. The Drug Safety Newsletter already
    aggregates domestic + international risk call-outs, so coverage is sufficient.
  - Only public pages are fetched; zero confidential data or information input
    (B-tier: ordinary input + public retrieval). Default SAFE PREVIEW — network runs only with explicit --run.

Reads only public data; zero confidential data or information input.
"""
import argparse
import json
import re
import sys
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

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

WAF_KW = ["安全狗", "SafeDog", "访问被拒绝", "Access Denied", "验证码",
          "captcha", "WAF", "拦截", "请输入验证码", "human verification"]


def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    return s


def _get(session, url, timeout=25):
    r = session.get(url, timeout=timeout)
    if r.status_code == 412:
        raise RuntimeError("HTTP 412 (CDN/WAF blocked): %s" % url)
    r.raise_for_status()
    return r


def list_articles(session, col_path, max_per=10):
    """Return up to max_per article stubs {url,title,column_path} from a listing page."""
    url = BASE + col_path
    r = _get(session, url)
    raw = re.findall(r'<a[^>]*href="(\./[^\"]+\.html?)"[^>]*>(.*?)</a>', r.text, re.S)
    arts, seen = [], set()
    for href, txt in raw:
        title = re.sub(r'<[^>]+>', '', txt).strip()
        if not title or len(title) < 4:
            continue
        u = urljoin(url, href)
        if u in seen:
            continue
        seen.add(u)
        arts.append({"url": u, "title": title, "column_path": col_path})
        if len(arts) >= max_per:
            break
    return arts


def _extract_body(html):
    """Strip scripts/styles/CSS noise and return readable text of an article page."""
    html = re.sub(r'<script.*?</script>|<style.*?</style>', '', html, flags=re.S)
    html = re.sub(r'<!--.*?-->', ' ', html, flags=re.S)
    # common content containers first
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
            # Grab everything from TRS_Editor opening to </body> to get full article text
            m = re.search(r'class=["\']?TRS_Editor["\']?[^>]*>(.*)', html, re.S | re.I)
            if m:
                body = m.group(1)
                # Cut at </body> to avoid navigation/footer noise
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


def fetch_article(session, art):
    r = _get(session, art["url"])
    html = r.text
    m = re.search(r'<meta[^>]+name="PubDate"[^>]+content="([^"]+)"', html, re.I)
    date = m.group(1)[:10] if m else None
    body = _extract_body(html)
    return {"url": art["url"], "title": art["title"],
            "column_path": art["column_path"], "date": date, "body": body}


def _make_snippet(text, keywords, width=120):
    low = text.lower()
    pos = -1
    for kw in keywords:
        if not kw:
            continue
        i = low.find(kw.lower())
        if i >= 0 and (pos < 0 or i < pos):
            pos = i
    if pos < 0:
        return text[:width]
    start = max(0, pos - width // 3)
    return text[start:start + width]


def search(drug_zh, drug_en=None, event=None, terms=None, max_per=10,
           run=False, out=None):
    if requests is None:
        raise RuntimeError("requests not installed: pip install requests")
    if not run:
        print("[PREVIEW] would scrape cdr-adr.org.cn for drug=%r (en=%r) event=%r "
              "terms=%r across %d columns x %d latest (use --run to execute)"
              % (drug_zh, drug_en, event, terms, len(COLUMNS), max_per))
        return None

    session = _session()
    drug_kw = [k.strip() for k in [drug_zh, drug_en] if k and k.strip()]
    event_kw = [event.strip()] if event and event.strip() else []
    extra = [t.strip() for t in (terms or []) if t and t.strip()]

    hits = []
    for col_name, col_path in COLUMNS:
        try:
            arts = list_articles(session, col_path, max_per)
        except Exception as e:
            print("[WARN] column %s skipped: %s" % (col_name, e))
            continue
        for art in arts:
            try:
                a = fetch_article(session, art)
            except Exception as e:
                print("[WARN] article %s skipped: %s" % (art.get("url"), e))
                continue
            text = (a["title"] + "\n" + a["body"])
            low = text.lower()
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
            snippet_kw = drug_hit + event_hit + extra_hit
            hits.append({
                "title": a["title"],
                "column": col_name,
                "date": a["date"],
                "url": a["url"],
                "snippet": _make_snippet(text, snippet_kw),
                "matched_keywords": sorted(set(snippet_kw)),
            })

    result = {
        "source": "CN-PV (cdr-adr.org.cn)",
        "note": ("定性叙事通报检索；非个案计数，不可做 disproportionality (PRR/ROR/IC) 分析。"
                 "仅作 FAERS 量化信号的定性佐证。"),
        "query": {"drug_zh": drug_zh, "drug_en": drug_en,
                  "event": event, "terms": terms},
        "searched_columns": [c[0] for c in COLUMNS],
        "max_per_column": max_per,
        "hit_count": len(hits),
        "hits": hits,
    }
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print("[OK] wrote", out, "(hits=%d)" % len(hits))
    return result


def main():
    ap = argparse.ArgumentParser(
        description="Search China official PV bulletins (cdr-adr.org.cn). Qualitative only.")
    ap.add_argument("--drug", required=True, help="drug name (Chinese preferred, e.g. 奥希替尼)")
    ap.add_argument("--drug-en", help="drug English name / synonym (e.g. osimertinib)")
    ap.add_argument("--event", help="event keyword (e.g. 肝损伤 / hepatotoxicity)")
    ap.add_argument("--terms", nargs="*", help="extra AND keywords")
    ap.add_argument("--max-per-column", type=int, default=10,
                    help="max latest articles scraped per column (default 10)")
    ap.add_argument("--run", action="store_true", help="execute network scrape")
    ap.add_argument("--out", help="output JSON path")
    args = ap.parse_args()

    res = search(args.drug, args.drug_en, args.event, args.terms,
                 args.max_per_column, args.run, args.out)
    if res and not args.out:
        print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
