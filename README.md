# Clinical Trial Safety Signal (ct-safety)

[🇨🇳 中文](./README_zh-CN.md) ｜ [🇺🇸 English](#)

<div align="center">
  <img src="assets/icon.svg" width="240" height="240" alt="ct-safety logo"/>
</div>

> **Works without installation:** If you'd rather not install and just want to quickly use this skill's basic features, you can also visit the ct-series unified web portal **https://ct.medstatstar.com** directly.

> A pharmacovigilance skill that is safe out of the box: it screens **FDA FAERS** public adverse-event data for drug–event safety signals (PRR / ROR / IC / EBGM with 95% CIs), with optional **device adverse events (MAUDE)**, **China PV corroboration**, **FDA Label triangulation**, and **Naranjo causality assessment**. Reads only public data — **zero confidential input (A-tier, `network=public-retrieval`)**. All retrieval uses a **thin local client**: local side only computes, outbound queries go to the unified endpoint `ct-search.coze.site`.

## Who This Is For

The `ct-*` clinical-trial skill family serves three groups:

- **Clinical-trial practitioners at pharmaceutical companies** — sponsors, CROs, and medical / statistical / regulatory roles;
- **Clinicians and nurses who design, manage, or run clinical-trial projects**;
- **Medical students who want to learn clinical-trial methodology in a structured way**.

## Time & Volume Warning

> ⚠️ **Runtime and download limits.** All retrieval goes through the unified endpoint `ct-search.coze.site`. Wall-clock time depends on processing + network. Measured on **2026-10-08** (Shanghai / ~200 Mbps):
>
> | Workload | Command shape | Measured wall-clock | Output |
> |---|---|---|---|
> | **Overview** (count-facet, the default path) | `ct_safety.py --drug candesartan --run` (no `--event`) | **≈10–30 s** | matched reports, top-10 reactions |
> | **Signal detection** | `ct_safety.py --drug candesartan --event NAUSEA --run` | **≈15–45 s** | 2×2 table + PRR/ROR/IC/EBGM |
> | **Top-N events signal** | `ct_safety.py --drug candesartan --top-events-signal 6 --run` | **≈30–90 s** | multi-event disproportionality |
> | **With CN-PV corroboration** | `ct_safety.py --drug osimertinib --event PNEUMONITIS --with-cn-pv --drug-cn 奥希替尼 --event-cn 肺炎 --run` | **≈20–60 s** | FAERS signal + China bulletin |
> | **Multi-source + score** | `ct_safety.py --drug osimertinib --event PNEUMONITIS --with-fda-label --with-cn-pv --run` | **≈30–90 s** | Safety Signal Score 0–100, T1–T4 |
> | **Device (MAUDE)** | `ct_safety.py --device --drug "pacemaker" --event "malfunction" --run` | **≈15–45 s** | device 2×2 + four measures |
>
> **Per-run limits (match the implementation):**
> - `fetch_reports.py --max <n>` → hard cap **10,000** (`HARD_CAP`); larger values auto-clamp with `[WARN]`.
> - `ct_safety.py --case-level <n>` → **single-page** fetch, hard cap **100**; requires `--event` (silently ignored otherwise). For bulk pulls use `fetch_reports.py --max`.
> - openFDA quota (local-direct `query_total` / `fetch_case_reports` only): anonymous 240 req/min, 1,000 req/day per IP; free key 240 req/min, 120,000 req/day per key. Per-request timeout 120 s.
>
> **How to avoid long waits:** start with the overview to size the population; narrow the window with `--date-from` / `--date-to`; grow `--max` gradually (500 → 2000 → …).

## How to Use (in conversation)

Tell the assistant what you want in plain language (examples below). Real computation follows the **two-step safe workflow** described under **Safety**.

### Example 1 · A drug's top adverse events

**You say:**
> Show me what adverse events are most reported for candesartan in FAERS.

**How to trigger:**
> The overview runs automatically. Say "skip preview and run" (or "跳过预览，直接跑") to fetch the FAERS facets and print the summary.

### Example 2 · A specific drug–event signal

**You say:**
> Does candesartan increase the risk of angioedema?

**How to trigger:**
> The overview runs first and stops for confirmation. Reply "yes, run the detail" or "skip preview and run" to execute the signal detection (2×2 → PRR/ROR/IC/EBGM).

### Example 3 · Multi-event safety signal screen

**You say:**
> Screen the top 6 adverse events of osimertinib for safety signals in FAERS.

**How to trigger:**
> Confirm the detail step — runs disproportionality on each top event, applies BH-FDR, and flags cross-method signals.

### Example 4 · Corroborate with China official PV bulletins

**You say:**
> Is there any Chinese official safety bulletin about osimertinib and pneumonitis?

**How to trigger:**
> Confirm the detail step with Chinese terms (`--drug-cn 奥希替尼 --event-cn 肺炎`) for higher recall. Returns qualitative corroboration only.

### Example 5 · Multi-source triangulation + evidence tier

**You say:**
> Give me a safety signal score for osimertinib pneumonitis — pull in FDA label and China PV too.

**How to trigger:**
> Confirm the detail step — queries FAERS + FDA Label + CN-PV, synthesizes a Safety Signal Score (0–100) with T1–T4 evidence tier.

### Example 6 · Multi-drug comparison

**You say:**
> Compare osimertinib vs gefitinib vs erlotinib for pneumonitis safety.

**How to trigger:**
> Pick a configuration from the routing menu (aROR / FDR / temporal / full triangulation). Then the two-step workflow applies.

### Example 7 · Device adverse events (MAUDE)

**You say:**
> Any safety signals for pacemaker malfunction reports in MAUDE?

**How to trigger:**
> Confirm the detail step — runs the same 2×2 / four-measure pipeline on `device/event.json` via `--device`.

### Example 8 · Individual case reports with de-duplication

**You say:**
> Pull the individual FAERS case reports for osimertinib pneumonitis so I can review them.

**How to trigger:**
> Confirm the detail step with `--case-level 50` — fetches up to 100 cases per page, deduplicates by `safetyreportid` (L1) and flags suspected duplicates by reaction-set Jaccard (L2).

### Example 9 · Naranjo causality assessment

**You say:**
> Add a Naranjo causality assessment to the osimertinib pneumonitis signal.

**How to trigger:**
> Confirm the detail step with `--with-causality` — appends an independent Naranjo 7-criteria section (qualitative, never mixed into PRR/ROR).

### Example 10 · PSUR auto-generation

**You say:**
> Generate a PSUR for the osimertinib signals we found.

**How to trigger:**
> Confirm the detail step with `--psur --psur-period 2026H1` — auto-generates `psur.md` from detected signals.

### Example 11 · Bug reporting

**You say:**
> report a bug / 上报问题

**What happens:**
> The assistant proposes a sanitized 11-key report, shows it for your review, then sends (with your explicit consent) to `https://ct-bugreport.coze.site/run`. Nothing transmits without your "send" confirmation.

## What It Can Do — Scenarios

| What you can do | Method | Try saying |
|---|---|---|
| Drug adverse-event profile | FAERS counts (top reactions, seriousness, demographics) | "Show candesartan's top reported reactions in FAERS" |
| Drug–event signal detection | PRR / ROR / IC / EBGM + 95% CI + signal flags | "Does candesartan raise angioedema risk?" |
| Multi-method cross-judgement | ROR lower-CI > 1 · PRR ≥ 2 & χ² ≥ 4 · IC lower-CI > 0 · EBGM EB05 ≥ 2 | "Is this signal robust across methods?" |
| Multi-event safety screen | `--top-events-signal N` on focal drug's top events | "Screen the top 6 events of osimertinib for signals" |
| China official PV corroboration | cdr-adr.org.cn public bulletins (qualitative only) | "有任何中国官方的奥希替尼肺炎通报吗？" |
| Multi-event FDR control | Benjamini-Hochberg q-value across Top-N events | "Screen all top events with false-discovery control" |
| PT→SOC organ grouping | MedDRA PT → System Organ Class mapping | "Group these signals by organ system" |
| Temporal anomaly detection | `--trend` CUSUM / rolling-Z / changepoint | "Any recent spike in osimertinib pneumonitis reports?" |
| Multi-drug adjusted ROR | aROR via `--compare-drugs` (focal vs pooled reference) | "Compare osimertinib vs gefitinib for pneumonitis" |
| Competitor benchmark | `--benchmark-drug` (same event, horizontal comparison) | "Benchmark osimertinib against gefitinib and erlotinib for pneumonitis" |
| Multi-source triangulation + score | `--with-fda-label` → Safety Signal Score 0–100, T1–T4 | "Give me an overall signal score with evidence tier" |
| Device adverse events | `--device` MAUDE `device/event.json` | "Any signals for pacemaker malfunction?" |
| Individual case reports | `--case-level N` with L1/L2 de-duplication | "Pull case reports for review" |
| Naranjo causality | `--with-causality` independent 7-criteria assessment | "Add Naranjo causality to this signal" |
| Signal verification | `--verify-signal` temporal / dose-response / deconvolution | "Verify this signal's robustness" |
| Signal prioritization | `--prioritize` label-gap + trend dimensions | "Prioritize the signals by risk" |
| PSUR auto-generation | `--psur` auto-generate from detected signals | "Generate a PSUR for these signals" |
| Non-ASCII drug name | `--drug 阿司匹林` auto-resolves to INN | "查一下阿司匹林的不良反应" |
| Published safety-literature corroboration | Chain to **`ct-literature --safety`** for CSM subset | "Pull published reviews on osimertinib pneumonitis" |
| MedDRA verbatim coding | `--code-verbatim` local dictionary coding | "Code this AE verbatim term to PT" |

### Corroborating with published literature (chain to `ct-literature --safety`)

When a FAERS signal needs *qualitative* backing from published evidence, invoke **`ct-literature --safety`**. It returns the CSM qualitative subset as a separate **Safety-Related** sheet.

> **Boundary.** `ct-literature --safety` is published-literature context only — it must **NOT** feed the FAERS 2×2 table. Use it to corroborate, never as a quantitative source.

## FAQ

**Can I run it with just a drug name and no event?**
Yes. If you give only `--drug`, it auto-degrades to a top-adverse-event report (no 2×2 table). Add `--event <PT>` for a specific signal.

**What's the difference between PRR and ROR?**
Both are disproportionality measures on the 2×2 table. ROR signals when its lower 95% CI > 1. PRR signals when PRR ≥ 2 **and** χ² ≥ 4. IC signals when lower CI > 0; EBGM signals when EB05 ≥ 2. All four are reported with BH-FDR across events.

**How do I actually get the signal table?**
By default the skill shows an overview and stops. Confirm the detail step, or say "skip preview and run" — then it executes and returns results (HTML / XLSX / JSON / Markdown).

**Does it output in Chinese?**
Yes. The skill follows your input language. Reports switch to Chinese on `zh-*` locale and English otherwise.

**How do I configure the openFDA API key?**
A key is **not required** for the default path (via unified endpoint). For local-direct fallback only, openFDA runs anonymously. Register a free key at https://open.fda.gov/api/register/ for higher throughput. Provide via env `OPENFDA_API_KEY`, skill-root `.env`, or `--api-key`. The key stays local and is only sent over HTTPS to the official openFDA API.

**Q: What if I found an error — how do I report it?**
A: Say **"report a bug" / "上报问题"**. The skill also proactively asks when it detects a likely defect (at most once per session). Either way: (1) propose sanitized 11-key report → (2) show for your review → (3) send after explicit consent → (4) receive acknowledgment.

**Q: Do I need to install the skill?**
A: No — for the basics you can visit the ct-series unified web portal **https://ct.medstatstar.com** without installing anything. For full capabilities, install and invoke the `ct-safety` skill.

## Safety (safe preview)

**Two-step workflow, safe out of the box.** Step 1 (overview) runs automatically. Step 2 (detailed retrieval / signal detection) runs **only after explicit confirmation** — or when you say "skip preview and run".

**Outbound data disclosure.** Local side only computes; ALL outbound retrieval goes to the unified endpoint `ct-search.coze.site`. The skill reads:
- **FDA FAERS** (required, quantitative) — via `faers` node;
- **MAUDE** when `--device` is used (optional device events) — via `maude` node;
- **FDA Label** when `--with-fda-label` (optional third source) — via `fda_label` node;
- **国家不良反应监测中心** when `--with-cn-pv` (optional, qualitative) — via `nmpa_pv` node.

**Zero confidential data input** (A-tier). Bug reports send only an 11-key whitelist to `https://ct-bugreport.coze.site/run`. Signal detection is screening only, not causal inference.

## Advanced Reference

### Data sources

| Source | Access | Status |
|---|---|---|
| FDA FAERS (openFDA `drug/event.json`) | Thin local client → unified endpoint `ct-search.coze.site` (`faers` node). `query_total` / `fetch_case_reports` always local-direct | Required (A-tier, quantitative) |
| MAUDE (openFDA `device/event.json`) | Thin local client → unified endpoint (`maude` node). Default dimension `patient.device.brand_name` | Optional `--device` (quantitative) |
| FDA Label (openFDA `drug/label.json`) | Thin local client → unified endpoint (`fda_label` node). `check_event` local-only | Optional `--with-fda-label` |
| 国家不良反应监测中心 (cdr-adr.org.cn) | Thin local client → unified endpoint (`nmpa_pv` node). Local keeps keyword expansion + evidence grading + cache | Optional `--with-cn-pv` (qualitative) |

### Requirements

- Python 3.10+ (Anaconda `C:\Tools\anaconda3\python.exe` recommended).
- Required: `requests`. Optional: `matplotlib` (PNG charts). Network: read-only FAERS public API.

### CLI workflow

```bash
# Overview (auto-run; totals + Top-N, then STOP for confirmation)
python scripts/ct_safety.py --drug "candesartan" --top 10 --date-from 20200101 --date-to 20261231

# Summary Excel (default present flow; count facets, seconds)
python scripts/fetch_reports.py --drug "candesartan" --date-from 20200101 --date-to 20261231 --out-xlsx faers_summary.xlsx

# Detail download (case-level data; hard cap 10000)
python scripts/fetch_reports.py --drug "candesartan" --max 10000 --date-from 20200101 --date-to 20261231 \
    --run --out faers_reports_raw.json --out-csv faers_reports.csv --out-xlsx faers_reports.xlsx

# Drug-event signal detection (2x2 -> PRR/ROR/IC/EBGM); only after confirmation
python scripts/ct_safety.py --drug "candesartan" --event "ANGIOEDEMA" \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# Multi-event safety signal screen (--top-events-signal N)
python scripts/ct_safety.py --drug "osimertinib" --top-events-signal 6 \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# China PV qualitative corroboration (optional)
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --with-cn-pv --drug-cn "奥希替尼" --event-cn "肺炎" --run --out-dir ./out

# Multi-source triangulation + Safety Signal Score 0-100 + T1-T4
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --with-fda-label --with-cn-pv --drug-cn "奥希替尼" --event-cn "肺炎" \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# Device adverse events (MAUDE)
python scripts/ct_safety.py --device --drug "pacemaker" --event "malfunction" \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# Case-level reports with de-duplication
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --case-level 50 --run --out-dir ./out

# Naranjo causality (qualitative add-on, independent of disproportionality)
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --with-causality --run --out-dir ./out

# Temporal anomaly (requires --event)
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --trend --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# Multi-drug adjusted ROR (first drug = focal, rest = reference pool)
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --compare-drugs osimertinib gefitinib erlotinib \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# Competitor benchmark (same event, horizontal comparison)
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --benchmark-drug gefitinib erlotinib \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# Signal verification (temporal / dose-response / deconvolution)
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --verify-signal --run --out-dir ./out

# PSUR auto-generation
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --psur --psur-period 2026H1 --run --out-dir ./out

# Pipeline self-check against known +/- controls
python scripts/ct_safety.py --validate-controls --out-dir ./out

# Standalone CN-PV search
python scripts/fetch_cn_pv.py --drug "奥希替尼" --event-cn "肝损伤" --out cn_pv.json
```

### FAERS field boundaries

- **Indexable / countable**: `patient.drug.medicinalproduct`, `patient.reaction.reactionmeddrapt` (use `.exact` for Top-N), `receivedate`, `serious*` booleans, `patient.patientsex` (1=M / 2=F / 0=unknown).
- **Not facetable via API**: `patient.patientage`, `primarysource.reportertype`, `primarysourcecountry`. Download cases (`--run`) to compute locally.
- Multi-word MedDRA PTs: some 3-word phrases consistently 404 — use standard PT `ACUTE KIDNEY INJURY`.

### Errors

| Error | Cause | Fix |
|---|---|---|
| `URLError` / timeout | No network / proxy | Confirm network reachable; configure proxy |
| Endpoint error | Quota exhausted / token invalid / endpoint not allow-listed | Check Coze deployment status and `config.json` `auto_approve_endpoints` |
| HTTP 429 | Exceeds openFDA quota (local-direct only) | Add `--api-key`; or lower frequency |
| `--drug` without `--event` | Intent = top reactions | Auto-degrades to Top-N report; add `--event <PT>` |
| CN-PV 0 hits | Keyword too specific | Pass `--drug-cn` + `--event-cn`; raise `--cn-max` |
| `--max > 10000` | Hard cap | Auto-clamped to `HARD_CAP=10000`; note selection bias |

### Comparative study design mode

When the user asks for a *comparison*, switch to the comparative track: (1) data prep → (2) pick study style + workload → (3) metrics / comparators / robustness → (4) label every result with evidence tier. Hard rules: never run disproportionality on unprepared counts; always present all four configurations; forbid Tier-4 claims without external data.

### Regression tests

```bash
python tests/run_tests.py            # offline (mock network)
python tests/run_tests.py --live     # also runs tests/test_live.py (real openFDA)
CT_SAFETY_LIVE=1 python tests/run_tests.py
```

**Version**: v0.10.0 | **License**: MIT | **Authors**: medstatstar, phoe-zip

For feature requests, bug reports, or feedback: medstatstar@gmail.com (Wintone Zhang / 张文彤).

---

## Confidentiality Notice

> The CT series consists of 20+ domain skills organized into **two tiers — A, B** — by whether input contains confidential information (see ct-base §11).
>
> - **Tier A (non-confidential)**: ordinary input + optional public retrieval; published openly on GitHub.
> - **B 档（输入涉密）**: 输入含药企需严格保密的临床试验数据 / 方案 / CRF；B 档**既能本地处理**（`egress=none`，数据不出域）**也能对外公开检索**（`network=public-retrieval`，如 ct-protocol 调 ct-registry / ct-literature 抓取公开试验设计与文献作参考——仅公开查询词出域）；或需审批出站（`egress=approval-req`，如 ct-eligibility）。但**均不对外公开发布**；涉密输入绝不随包 / 出站；若有定制 / 本地部署需求，欢迎与作者联系。
>
> 📧 Contact: medstatstar@gmail.com (Wintone Zhang / 张文彤)
