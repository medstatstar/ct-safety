# Clinical Trial Safety Signal (ct-safety)

[🇨🇳 中文](./README_zh-CN.md) ｜ [🇺🇸 English](#)

<div align="center">
  <img src="assets/icon.svg" width="240" height="240" alt="ct-safety logo"/>
</div>

> A safe-by-default pharmacovigilance skill that screens **FDA FAERS** public adverse-event data for drug–event safety signals (PRR / ROR / IC / EBGM with 95% CIs), with optional China official PV corroboration. Reads only public data — **zero confidential input (B-tier)**.

## Who This Is For

The `ct-*` clinical-trial skill family covers the entire clinical-trial lifecycle. It serves three groups:

- **Clinical-trial practitioners at pharmaceutical companies** — sponsors, CROs, and medical / statistical / regulatory roles;
- **Clinicians and nurses who design, manage, or run clinical-trial projects**;
- **Medical students who want to learn clinical-trial methodology in a structured way**.

## How to Use (in conversation)

Just tell the assistant what you want in plain language. Below are real examples you can copy — labels and sketches only; real computation follows the two-step safe workflow described under **Safety**.

### Example 1 · A drug's top adverse events

**You say:**
> Show me what adverse events are most reported for candesartan in FAERS.

**Assistant replies (sketch):**
> I'll summarize the top reported reactions for candesartan from the FAERS public database, with counts, seriousness, and organ-class grouping — a safety baseline before any specific signal question.

**How to trigger real computation:**
> The overview runs automatically. Say "calculate directly" (or "直接计算") and the skill fetches the FAERS facets and prints the summary; no `--event` is required — it auto-degrades to a top-reactions report.

### Example 2 · A specific drug–event signal

**You say:**
> Does candesartan increase the risk of angioedema?

**Assistant replies (sketch):**
> I'll build a 2×2 drug–event table from FAERS and report PRR / ROR / IC / EBGM with 95% CIs and signal flags, plus a Benjamini-Hochberg FDR check across top events.

**How to trigger real computation:**
> The overview (total + Top-N) runs first and then stops for your confirmation. To run the detailed signal detection, reply "yes, run the detail" — or simply say "calculate directly" to skip the preview and execute.

### Example 3 · Corroborate with China official PV bulletins

**You say:**
> Is there any Chinese official safety bulletin about osimertinib and pneumonitis?

**Assistant replies (sketch):**
> I'll search the public columns of the 国家不良反应监测中心 (cdr-adr.org.cn) for matching bulletins as **qualitative corroboration** of the FAERS signal. These are narrative bulletins only — not case counts — so they never feed the disproportionality math.

**How to trigger real computation:**
> The Chinese keyword search is part of the detailed run. Confirm the detail step (or "calculate directly"), passing the Chinese terms for higher recall: e.g. drug 奥希替尼 / event 肺炎.

### Example 4 · Complex: multi-drug comparison (popup menu)

**You say:**
> Compare osimertinib vs gefitinib vs erlotinib for pneumonitis safety.

**Assistant replies (sketch):**
> Rather than guess, I'll show a routing menu because this needs several choices:
>
> - **Compare on one event (pneumonitis) — adjusted ROR (aROR)** · focal vs pooled reference
> - **Add FDR / temporal / control validation** · more rigorous, more queries
> - **Add China PV + FDA Label triangulation + Safety Signal Score (T1–T4)** · three-source evidence
> - **Not sure yet → explain the differences in detail** · I'll walk through each option's trade-offs before you decide

**How to trigger real computation:**
> Pick a menu item (or choose "explain the differences" first). The chosen configuration then follows the two-step workflow: a lightweight overview first, detailed retrieval only after you confirm.

### Example 5 · Vague: not sure what to compare (grill-me)

**You say:**
> I want to look at this drug's safety but I'm not sure what to compare it against.

**Assistant replies (sketch):**
> No problem — let me narrow it down branch by branch:
>
> 1. Do you have a **specific event** in mind (e.g. pneumonitis), or want the **top reported reactions** first?
> 2. Is this about a **single drug**, or a **head-to-head against competitors** in the same class?
> 3. Do you need a **regulatory-grade evidence tier (T1–T4)** with China/FDA corroboration, or a quick screen?
>
> Once you answer, I'll propose the exact analysis instead of dumping a full menu.

**How to trigger real computation:**
> After the branches resolve your intent, the same two-step workflow applies: overview auto-runs, detail waits for your confirmation (or "calculate directly" to execute now).

### Example 6 · Force the real run

**You say:**
> Calculate directly — run the candesartan angioedema signal detection now.

**Assistant replies (sketch):**
> Acknowledged. I'll skip the preview and execute the detailed FAERS retrieval and disproportionality analysis, then return the JSON / Markdown report.

**How to trigger real computation:**
> "Calculate directly" / "直接计算" is the explicit override that performs the detail step immediately.

## What It Can Do — Scenarios

| What you can do | Method | Try saying |
|---|---|---|
| Drug adverse-event profile | FAERS counts (top reactions, seriousness, demographics) | "Show candesartan's top reported reactions in FAERS" |
| Drug–event signal detection | PRR / ROR / IC / EBGM + 95% CI + signal flags | "Does candesartan raise angioedema risk?" |
| Multi-method cross-judgement | ROR lower-CI > 1 · PRR ≥ 2 & χ² ≥ 4 · IC lower-CI > 0 · EBGM EB05 ≥ 2 | "Is this signal robust across methods?" |
| China official PV corroboration | cdr-adr.org.cn public bulletins (qualitative only) | "有任何中国官方的奥希替尼肺炎通报吗？" |
| Multi-event FDR control | Benjamini-Hochberg q-value across Top-N events | "Screen all top events with false-discovery control" |
| PT→SOC organ grouping | MedDRA PT → System Organ Class mapping | "Group these signals by organ system" |
| Temporal anomaly detection | `--trend` CUSUM / rolling-Z / changepoint | "Any recent spike in osimertinib pneumonitis reports?" |
| Multi-drug adjusted ROR | aROR via `--compare-drugs` (focal vs pooled reference) | "Compare osimertinib vs gefitinib for pneumonitis" |
| Multi-source triangulation + score | `--with-fda-label` → Safety Signal Score 0–100, T1–T4 | "Give me an overall signal score with evidence tier" |
| Non-ASCII drug name | `--drug 阿司匹林` auto-resolves to INN | "查一下阿司匹林的不良反应" |

## FAQ

**Can I run it with just a drug name and no event?**
Yes. If you give only `--drug` (or just say the drug), it no longer errors — it auto-degrades to a top-adverse-event report (no 2×2 table). To compute a specific signal, add an event (a MedDRA Preferred Term, e.g. `ANGIOEDEMA`).

**What's the difference between PRR and ROR?**
Both are disproportionality measures on the drug–event 2×2 table. ROR (Reporting Odds Ratio) uses a odds-ratio form and flags a signal when its lower 95% CI > 1. PRR (Proportional Reporting Ratio) flags when PRR ≥ 2 **and** the χ² ≥ 4. IC (Information Component, UMC/VigiBase) signals when its lower CI > 0; EBGM (FDA MGPS Bayesian shrinkage) signals when EB05 ≥ 2. The skill reports all four and applies Benjamini-Hochberg FDR across multiple events.

**How do I actually get the signal table, not just code?**
By default the skill shows an overview (totals + Top-N) and stops. Confirm the detail step, or say "calculate directly" / "直接计算" — then it executes the FAERS retrieval and disproportionality analysis and returns JSON / Markdown (and optional PNG charts).

**Does it output in Chinese?**
Yes. The skill follows your input language: prompts and reports switch to Chinese on a `zh-*` locale and English otherwise. Code comments and documentation remain English-only.

**How do I configure the openFDA API key?**
A key is **not required** — openFDA runs anonymously (240 req/min, 1,000 req/day per IP). For high throughput only, register a free key at https://open.fda.gov/api/register/ (email-only, no card). Provide it via one of three self-configured methods:
- Environment variable: `export OPENFDA_API_KEY=YOUR_KEY` (recommended, auto-read by every script);
- A skill-root `.env` file: `OPENFDA_API_KEY=YOUR_KEY` (git-ignored, never shipped);
- CLI flag: `--api-key YOUR_KEY`.

Never share your key in a chat message or put it in any file that ships with the skill — the key stays local and is only sent over HTTPS to the official openFDA API.

## Safety (safe preview)

**Two-step workflow, safe by default.** Step 1 (overview: totals + Top-N) runs automatically. Step 2 (detailed retrieval / signal detection) runs **only after you explicitly confirm** — or when you say "calculate directly". Nothing heavy executes until then, so a casual question never triggers a large download.

**Outbound data disclosure.** The skill only reads public sources:
- **FDA FAERS** via openFDA `https://api.fda.gov/drug/event.json` (required, quantitative);
- **FDA Label** via openFDA `drug/label.json` when `--with-fda-label` is used (optional third source);
- **国家不良反应监测中心** `cdr-adr.org.cn` public columns when `--with-cn-pv` is used (optional, qualitative corroboration only — narrative bulletins, no case counts, never fed into disproportionality).

There is **zero confidential data or information input** (B-tier: ordinary input + public retrieval). The NMPA main site is WAF-blocked (HTTP 412) and is intentionally excluded. Your openFDA key, if used, is **stored only locally** and sent **only over HTTPS to the official openFDA API**.

**Bug-report endpoint disclosure (ct-base §5 / §20.3, mandatory).** When you confirm sending a (sanitized) error report via the in-skill bug reporter (`adapters/bug_report.py`), the skill sends **only** the 11-key whitelist envelope (skill name / version / error type / error code / engine status / your free-text `description` / locale / `query_origin` / session hash / retry count / test) to the unified bug-report endpoint `https://ct-bugreport.coze.site/run`. It sends **no analysis data and no personal identifiers** — `description` is the only free-text field and you review it before consent (hard boundary: no identifiable person/institution/subject info). If you decline, nothing is sent; if there is no cloud call this session, the report is saved locally instead (`save_local_report`, data never leaves the machine).

Signal detection is screening only, not causal inference; regulatory submissions (DSUR / PBRER / labeling) require separate GCP / ICH E2 assessment.

## Advanced Reference

Developer CLI, parameters, data-source boundaries, and error handling live here (moved out of the first screen per the user-facing layout).

### Data sources

| Source | Access | Status |
|---|---|---|
| FDA FAERS (openFDA `drug/event.json`) | Official public REST API, direct-connect, low-frequency no-key | Required (B-tier, quantitative) |
| FDA Label (openFDA `drug/label.json`) | Same openFDA, no key; `adverse_reactions` / `warnings` | Optional `--with-fda-label` (labeled vs unlabeled risk) |
| 国家不良反应监测中心 (cdr-adr.org.cn) | Public columns scraped (药物警戒快讯 / 数据报告 / 通知通告 / 器械·化妆品警戒快讯); no WAF, no key | Optional `--with-cn-pv` (qualitative corroboration only) |

### Requirements

- Python 3.10+ (Anaconda `C:\Tools\anaconda3\python.exe` recommended).
- Required: `requests`. Optional: `matplotlib` (PNG charts). Network: read-only FAERS public API.

### CLI workflow

```bash
# Step 1 — overview (auto-run; totals + Top-N, then STOP for confirmation)
python scripts/overview.py --drug "candesartan" --top 10 \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# Step 2 — summary Excel (default present flow; count facets, seconds, full-match base)
python scripts/fetch_reports.py --drug "candesartan" \
    --date-from 20200101 --date-to 20261231 --out-xlsx faers_summary.xlsx

# Step 3 — detail download (only when case-level data is explicitly wanted; hard cap 10000)
python scripts/fetch_reports.py --drug "candesartan" --max 10000 \
    --date-from 20200101 --date-to 20261231 --run \
    --out faers_reports_raw.json --out-csv faers_reports.csv --out-xlsx faers_reports.xlsx

# Drug-event signal detection (2x2 -> PRR/ROR/IC/EBGM); only after confirmation
python scripts/ct_safety.py --drug "candesartan" --event "ANGIOEDEMA" \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# China PV qualitative corroboration (optional)
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --with-cn-pv --drug-cn "奥希替尼" --event-cn "肺炎" --run --out-dir ./out

# Continuity correction (default ON; --no-continuity reproduces v0.1.8)
python scripts/ct_safety.py --drug "candesartan" --event "ANGIOEDEMA" \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out
# Pipeline self-check against known +/- controls (no --drug/--event needed)
python scripts/ct_safety.py --validate-controls --out-dir ./out
# Temporal anomaly (requires --event)
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --trend --date-from 20200101 --date-to 20261231 --run --out-dir ./out
# Multi-drug adjusted ROR (first drug = focal, rest = reference pool; requires --event)
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --compare-drugs osimertinib gefitinib erlotinib \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out
# Multi-source triangulation + Safety Signal Score (0-100) + T1-T4 (default FAERS x CN-PV; add --with-fda-label for 3rd source)
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --with-cn-pv --drug-cn "奥希替尼" --event-cn "肺炎" --with-fda-label \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# Standalone CN-PV search (no FAERS needed)
python scripts/fetch_cn_pv.py --drug "奥希替尼" --event-cn "肝损伤" --run --out cn_pv.json
```

### FAERS field boundaries (verified)

- **Indexable / countable**: `patient.drug.medicinalproduct`, `patient.reaction.reactionmeddrapt` (use `.exact` for Top-N), `receivedate`, `serious*` booleans, `patient.patientsex` (1=M / 2=F / 0=unknown).
- **Not facetable via API** (exist only in case bodies): `patient.patientage`, `primarysource.reportertype`, `primarysourcecountry` (use `.exact`). Download cases (`--run`) to compute age / country / reporter-type locally.
- Multi-word MedDRA PTs: some 3-word phrases (`RENAL FAILURE ACUTE`) consistently 404 — use standard PT `ACUTE KIDNEY INJURY`. Two-word PTs (`HEPATIC FAILURE`) usually work. `total()` auto-downgrades 404 → `.exact`.

### Errors

| Error | Cause | Fix |
|---|---|---|
| `URLError` / timeout | No network / proxy | Confirm `api.fda.gov` reachable; configure proxy |
| HTTP 429 / rate-limited | Exceeds openFDA quota (per request, not per row): anonymous 240/min, 1,000/day per IP; free key 240/min, 120,000/day per key | Add `--api-key`; or lower frequency |
| `--drug` without `--event` | Intent = top reactions, not a 2×2 signal | Auto-degrades to top-N report; add `--event <PT>` for a signal |
| Field-name mismatch | Wrong drug-name field | Default `patient.drug.medicinalproduct`; standardize via `--field patient.drug.openfda.substance_name` |
| CN-PV HTTP 412 / WAF | nmpa.gov.cn blocked | Expected — only cdr-adr.org.cn is scraped; NMPA excluded |
| CN-PV 0 hits | Keyword too specific | Pass `--drug-cn` + `--event-cn`; raise `--cn-max` |
| Multi-word event persistent 404 | That 3-word PT not indexed | Switch to standard MedDRA PT |
| `--max > 10000` | Quota hard cap | Auto-clamped to `HARD_CAP=10000`; note selection bias (API order, not random) |

### Comparative study design mode (multi-drug / single-SOC)

When the user asks for a *comparison* ("compare X vs Y", "within-class head-to-head", "active-comparator disproportionality", "publishable comparative PV paper"), switch to the comparative track: (1) data prep → (2) pick a study style + Lite/Standard/Advanced/Publication+ workload → (3) choose metrics, comparator logic, robustness routes → (4) label every result with an evidence tier. Hard rules: never run disproportionality on unprepared raw counts; always present all four configurations then recommend one; every material result carries a tier label (`[Tier 1]` signal / `[Tier 2]` comparative / `[Tier 3]` robustness); Tier-4 claims (incidence, causality, benefit–risk, prescribing) are forbidden without external data.

### Regression tests

```bash
python tests/run_tests.py            # offline (mock network)
python tests/run_tests.py --live     # also runs tests/test_live.py (real openFDA)
CT_SAFETY_LIVE=1 python tests/run_tests.py
```

**Version**: v0.1.28 | **License**: MIT | **Authors**: medstatstar, phoe-zip

For feature requests, bug reports, or other feedback, please contact the author directly at medstatstar@gmail.com (Wintone Zhang / 张文彤).

---

## Confidentiality Notice

> The CT series consists of 20+ specialized domain skills, organized into two tiers — A, B — by "confidential-data-exfiltration risk + whether external retrieval is needed", providing full coverage of the entire new-drug clinical trial (Clinical Trial) lifecycle.
>
> - **Tier A (non-confidential · public)**: takes only ordinary (non-confidential) input; runs fully locally (`network=off`) or performs public retrieval (`network=public-retrieval`, e.g. ct-registry / ct-advisor) — never involves confidential information. Tier A skills are published openly on GitHub.
> - **Tier B (confidential · internal)**: involve strictly confidential clinical-trial data and internal information from pharma sponsors (e.g., ct-analysis, ct-sdtm, ct-eligibility); Tier B is processed locally (`egress=none`, data never leaves the machine) or requires approved egress (`egress=approval-req`, e.g. ct-eligibility). These skills are designated for internal enterprise use only and are not publicly released at present.
>
> If you do have a genuine need for these confidential skills, please contact the author to request custom installation.
>
> 📧 Contact: medstatstar@gmail.com (Wintone Zhang / 张文彤)
