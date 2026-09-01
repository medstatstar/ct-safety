---
slug: ct-safety
displayName: Clinical Trial Safety Signal / 临床试验安全信号专家
name: ct-safety
cn_name: 临床试验安全信号专家
version: 0.9.8
invocable: true
required_commands: [python]
summary: "基于 FDA FAERS 公开不良事件数据做 disproportionality 信号检测（PRR/ROR/IC/EBGM），辅助药物安全性监测。"
license: MIT
description: "Signal detection on FDA FAERS (via openFDA public REST API): computes PRR / ROR / IC / EBGM with 95% CIs and signal flags from the drug–event 2×2 table, emitting two core deliverables — ① a renderable HTML report (visual conclusion) and ② an XLSX workbook holding all raw counts for line-by-line audit (JSON / Markdown as backups). Optional corroboration: China official PV bulletins (--with-cn-pv) and labeled-vs-unlabeled judgement from DailyMed SPL / RxClass MED-RT / openFDA recalls. Public data only; zero confidential input — A-tier (network=public-retrieval). / 基于 FDA FAERS（经 openFDA 公开 REST API）做药物-事件 disproportionality 信号检测，计算 PRR / ROR / IC / EBGM 及 95% 置信区间与信号判定；默认产出 ① 可渲染的 HTML 报告（可视化结论）② XLSX 数据簿（含全部原始计数，供逐条审计），JSON / Markdown 作备份。可选中国官方药物警戒通报（--with-cn-pv）与 DailyMed 说明书 / RxClass MED-RT / openFDA 召回做 labeled-vs-unlabeled 佐证。仅公开数据，零保密输入（A 档，network=public-retrieval）。"
triggers:
  - "FAERS safety signal"
  - "安全性信号分析"
  - "药物不良反应信号"
  - "disproportionality analysis"
  - "ct-safety"
  - "compare drug X vs Y adverse events"
  - "FAERS safety comparison"
  - "active-comparator disproportionality"
  - "多药安全性对比"
  - "药物类别头对头安全性比较"
metadata:
  openclaw: { emoji: "🛡️" }
  authors: ["medstatstar", "phoe-zip"]
  license: "MIT"
  tags: [clinical-trial, safety, faers, pharmacovigilance, signal-detection]
  homepage: "https://github.com/medstatstar/ct-safety"
permissions:
  scope: "user-space-only"
  network: "public-retrieval"
  network_note: "Reads only public sources: FDA FAERS / openFDA (https://api.fda.gov/drug/event.json), optional China PV (cdr-adr.org.cn, no WAF/no key), and optional corroborative sources via corroborative_sources.py — dailymed.nlm.nih.gov (SPL labels), rxnav.nlm.nih.gov (RxClass MED-RT), api.fda.gov drug/enforcement (recalls); all keyless public. No confidential input; ordinary input + public retrieval (A-tier, network=public-retrieval per ct-base §11). NMPA main site is WAF-blocked (HTTP 412) and intentionally excluded. Count-source feasibility is verified per-source (multi_source.COUNT_SOURCE_FEASIBILITY): PMDA JADER (captcha), Health Canada (timeout), VAERS (403), EudraVigilance (BO report, no JSON), VigiAccess (SPA, no API), MHRA iDAP (timeout) are verified blocked/unreachable on 2026-09-01 and intentionally excluded — not silently dropped. Low-frequency, keyless FAERS; optional --api-key raises quota. Default retrieval for faers / fda_label / dailymed / rxclass / fda_recall / hk_pv is OUTBOUND to the ct-registry unified endpoint ct-search.coze.site/run (thin local client, default); --offline forces local direct-connect to openFDA / NLM. cdr-adr.org.cn stays local-only."
  filesystem: "read-only to its own files; writes outputs ONLY to the user-specified --out-dir (default: current working directory). No system-path or hidden logging; any operational log (e.g. safety_err.log) is written under --out-dir (out_live/), never outside it, and FAERS raw responses are not persisted unless the user explicitly saves them."
  data: "no confidential data input. Retrieval requests (drug/event public query keywords) are sent to the ct-registry unified endpoint ct-search.coze.site/run (thin local client, default; --offline keeps everything local). Only public query parameters + public retrieval results cross the boundary; no confidential user data is ever transmitted."

---

## Language

- **English guide** → [README.md](https://github.com/medstatstar/ct-safety/blob/main/README.md) · **中文指南** → [README_zh-CN.md](https://github.com/medstatstar/ct-safety/blob/main/README_zh-CN.md)
- This skill responds in the user's input language and auto-switches; runtime prompts switch by locale. Bilingual walkthroughs live in the READMEs.

## Cross-turn Continuity (required)

Family standard: `ct-base/references/continuity.md` (pattern A). Echo the block below after every analysis; on a follow-up (changed `event` / different comparator drug / different measure), read the most recent block in the conversation and override **only the changed fields** — never rely on LLM memory alone:

```
## Current retrieval settings: drug=… | event=… | comparator=… | measure=PRR | source=FAERS
```

# Clinical Trial Safety Signal

> Safe by default: **overview-first**. Step 1 (overview) runs automatically; Step 2 (detailed retrieval) runs ONLY after the user explicitly confirms.
>
> **What counts as explicit confirmation.** Any unambiguous go-ahead — e.g. "yes, run the detail" / "确认，跑详情",
> or **`skip preview and run` / `跳过预览，直接跑`**. The last one is a *confirmation phrasing*, not a bypass:
> it means "the overview is enough, run Step 2 now". All Step-2 guardrails apply identically (no heavy download
> before confirmation, outputs confined to `--out-dir`, no confidential input). Conversely, a generic remark in
> passing conversation is **not** consent — the go-ahead must be an instruction that explicitly asks for the
> detail step to run.

## Disclaimer & Intended Use

- **Audience.** This skill is intended for **pharmacovigilance / clinical-trial methodologists and drug-safety professionals**. It is a methodologic signal-screening aid, not end-user health software.
- **Not a clinical or regulatory decision tool.** All outputs are **statistical disproportionality signals** computed from *spontaneous* adverse-event reports (FDA FAERS), which are subject to reporting bias, under-reporting, and confounding. A signal **does NOT establish causation** and **MUST NOT** be used to start, stop, or change any medication, or to make clinical or regulatory decisions. Always corroborate with RCTs, product labels, and qualified clinical/regulatory judgment (ICH E2 family).
- **Data flow (transparent).** Reads ONLY public sources — FDA FAERS / openFDA, optional cdr-adr.org.cn PV bulletins, and optional corroborative sources (DailyMed SPL, RxClass MED-RT, openFDA enforcement recalls) — all public, keyless. Writes outputs SOLELY to the user-specified `--out-dir` (default: current working directory). **No system-path or hidden logging**; any operational log (e.g. `safety_err.log`) is written ONLY under `--out-dir` (e.g. `out_live/`), never outside it, and FAERS raw responses are not persisted unless the user explicitly saves them. Zero confidential data input; no confidential user data is transmitted — retrieval queries (drug/event public keywords) are sent to the ct-registry unified endpoint ct-search.coze.site/run by default (thin local client), or stay fully local with `--offline`.
- **Dev artifacts excluded from every publish target.** The `tests/` directory (regression harness) is not tracked by git and is shipped to **no** publish target — GitHub, ClawHub, or SkillHub (ct-base §16.8). It stays on the maintainer's local disk only; the installed package contains no test code.

## Purpose

Run pharmacovigilance disproportionality analysis on FDA FAERS public adverse-event data to surface potential drug–event safety signals (PRR / ROR / IC / EBGM), supporting clinical-trial safety surveillance and label / signal screening. Optional China official PV bulletins (cdr-adr.org.cn) provide qualitative corroboration only. For *published* safety literature context (reviews / PV papers), chain to **`ct-literature --safety`** — it returns a qualitative CSM subset that corroborates signals but must not enter the FAERS 2×2.

## Data Sources

Two categories — **quantitative** (2×2 disproportionality) and **corroborative** (qualitative labeled-vs-unlabeled judgement). The latter does not feed PRR/ROR (would distort the 2×2); it informs signal prioritization per ICH E2C / CIOMS VIII (labeled = known risk → downgrade; unlabeled = potential new signal → upgrade).

| Category | Source | Access | Status |
|---|---|---|---|
| Quantitative | FDA FAERS (`drug/event.json`) | Thin local client (Coze default; `--offline` local-direct). `query_total` / `fetch_case_reports` always local-direct | Required (A-tier) |
| Quantitative | FDA Label (`drug/label.json`) | Thin local client (Coze default; `--offline` local-direct). `check_event` local-only | Optional `--with-fda-label` |
| Corroborative | DailyMed SPL · RxClass MED-RT · openFDA Enforcement | Thin local client (Coze default; `--offline` local-direct NLM / openFDA) | Optional `corroborative_sources.py` |
| Qualitative | cdr-adr.org.cn | Local-direct (public section, no WAF, no key) | Optional `--with-cn-pv` |
| Qualitative (CN add-on) | drugoffice.gov.hk (HK ADR Alerts) | Thin local client (Coze default; `--offline` local-direct, verified 200) | Coze node written; after deployment |

**Key mechanism:** openFDA works keyless (anonymous 240 req/min, 1,000 req/day per IP); an optional free key only raises quota. The key, when used, is **stored locally only** (env var / local `.env`) and sent **only over HTTPS to the official openFDA endpoint** (when running `--offline`) — never to any third party. NMPA main site (nmpa.gov.cn) is WAF-blocked (HTTP 412) for local direct fetch, but is reachable via the Coze browser channel (`--with-nmpa-coze`, source=`nmpa_pv`) — **verified live 2026-09-01** (drug=methotrexate → Bulletin No.75, tier=dedicated bulletin). All data are public adverse-event reports; zero confidential input. Endpoint details, indexable/non-indexable fields, and `count` endpoint pitfalls: `references/fetch_pipeline.md`.

### Architecture — thin local client (default: outbound to Coze)

Since v0.9.8 all safety retrieval uses a **thin local client**: the local side only computes (disproportionality / signal_score / check_event), while outbound retrieval defaults to the Coze unified endpoint `ct-search.coze.site/run` (shared with ct-registry). `adapters/coze_dispatch.py` rebinds global names via `FaersShim` / `FdaLabelShim`, so call sites need zero changes.

- **Default (outbound):** retrieval keywords go to Coze; server-side completes openFDA / NLM fetching. No local browser dependency; immune to egress / WAF limits.
- **`--offline` (local-direct fallback):** skips Coze; connects directly to openFDA / NLM.
- **Always local-direct:** `query_total` / `fetch_case_reports` (arbitrary query / raw cases), `check_event`, `fetch_cn_pv` (cdr-adr.org.cn).
- **Publish red line:** Coze-side `safety_rest_node.py` (6 nodes) takes effect only after the author uploads the workflow bundle; **the outbound path depends on Coze deployment.** Expanded: `references/ADVANCED.md`.

### Blocked / excluded sources (verified 2026-09-01)

Not silently dropped — each was tested from this machine; reasons recorded in `multi_source.COUNT_SOURCE_FEASIBILITY` / `corroborative_sources.BLOCKED_SOURCES`. Full evidence table: `references/ADVANCED.md`.

| Source | Status |
|---|---|
| PMDA JADER (Japan) | Not automatable (live) — captcha; full DB CSV obtainable (planned) |
| Health Canada (live API) | Legacy API unreachable; open-data ZIP planned |
| VAERS / CDC WONDER | Needs data-use agreement (403) |
| EudraVigilance (EMA) | Needs authorization |
| VigiAccess / VigiBase (WHO) | No public API (SPA; full access paid) |
| MHRA iDAP (UK) · Taiwan FDA PV | Unreachable locally |

Re-test before claiming "no data" — conditions may change.

**Planned (deferred 2026-09-01):** T1 trio — Health Canada bulk ZIP / PMDA JADER full CSV / TGA DAEN live retrieval. Feasibility, access models, and architecture: `references/roadmap_external_sources.md`.

## Methods

Four disproportionality measures on the drug–event 2×2 table (plus multiple-testing and corroboration layers):

- **PRR** — signal if PRR ≥ 2 **and** χ² ≥ 4.
- **ROR** — signal if lower 95% CI > 1.
- **IC** (UMC/VigiBase Information Component) — signal if lower 95% CI > 0.
- **EBGM** (FDA MGPS Bayesian shrinkage) — signal if EB05 ≥ 2.
- **Corroboration layers** — BH-FDR q-value over top-N / benchmarks; PT→SOC MedDRA grouping; Haldane-Anscombe continuity (+0.5/cell; `a==0` → conservative null); aROR (`--compare-drugs`); temporal anomaly CUSUM / rolling-Z / changepoint (`--trend`); Safety Signal Score 0–100 + T1–T4 (`--with-fda-label`); Naranjo (`--with-causality`, qualitative only — never fed into PRR/ROR/IC/EBGM).

Full formulas, thresholds, EBGM/MGPS math, FDR, aROR, trend, and score/tier weighting: `references/methods.md`.

## Features

| Capability | Flag / Source |
|---|---|
| Drug–event signal detection (PRR/ROR/IC/EBGM) + multi-method cross-judgement | FAERS |
| Statistical guards (BH-FDR · PT→SOC · sparse-2×2 `--validate-controls`) | — |
| HTML + XLSX core deliverables (JSON/MD backup) | — |
| China official PV bulletins (qualitative only) | `--with-cn-pv` |
| Labeled / unlabeled corroboration | `corroborative_sources.py` |
| Temporal anomaly · multi-drug aROR · score 0–100 + T1–T4 | `--trend` · `--compare-drugs` · `--with-fda-label` |
| Naranjo causality · MedDRA coding · prioritization · PSUR | `--with-causality` · `--code-verbatim` · `--prioritize` · `--psur` |
| Case-level de-duplication (L1 collapse / L2 flag-only) | `--case-level` |
| Non-ASCII drug-name auto-translate | `--drug 阿司匹林` → `aspirin` |
| Chained invocation | `ct-protocol` · `ct-registry` · `ct-literature --safety` |

Full capability table with scenarios and boundaries: `references/ADVANCED.md`.

## Requirements

- Python 3.10+ (Anaconda recommended). Required: `requests`. Optional: `matplotlib` (PNG charts).
- Network: read-only FAERS public API. An openFDA key is optional (raises quota only) — see below.

## ⚠️ Safety

- Network: retrieval (present / `--out-xlsx`) runs lightweight openFDA `count` facet queries (seconds, no case download); **case-level download requires explicit `--run`** (throttled by HARD_CAP=10000). Reads FAERS public reports ONLY — **zero confidential data or information input** (A-tier, `network=public-retrieval`).
- China PV bulletins are **qualitative narrative** — NO per-drug-event counts; must **NOT** feed disproportionality; only corroborate a FAERS signal.
- FAERS re-ingests the same case as follow-up versions and via multiple reporters. Case-level de-duplication fixes the **individual-case listing** only; disproportionality counts come from openFDA **aggregate** endpoints and therefore still carry duplicate-reporting bias. Never claim a signal is "de-duplicated".
- Signal detection is for screening, not causal conclusion; regulatory submission (DSUR / PBRER / label change) must be assessed per GCP / ICH E2 separately.

## Workflow

Two-step, overview-first (**present summary in context, Excel on demand**):
1. **Step 1 — Overview (automatic):** `fetch_reports.py --drug X` sends 8 `count` facets, prints the summary to context in seconds, caches `faers_summary_cache.json`. No confirmation needed.
2. **Step 2 — Detail (only after explicit confirm):** `--out-xlsx` builds the summary Excel from cache; `--run` downloads individual case reports (HARD_CAP 10000) for age/country stats. Signal detection via `ct_safety.py`.

`scripts/overview.py` is deprecated (merged into Step 1). Full workflow, caching, `--parallel`, XLSX layout: `references/fetch_pipeline.md`.

### One-shot signal report (`ct_safety.py`) — two core deliverables

`ct_safety.py --drug X --event Y --run` writes into `--out-dir` and prints a "Core Deliverables" block:

- **`faers_report.html`** — visual report (open in browser preview). **Core ①.**
- **`faers_report.xlsx`** — ALL raw data (counts, 2×2, four measures, optional Label/CN-PV/Score). **Core ②; audit every number here.** (`faers_report.md` / `*.json` are backups only.)

## API Key (openFDA) — optional, self-configured

The skill runs **without a key**; a free key only raises quota. Provide via CLI `--api-key`, env `OPENFDA_API_KEY` (recommended), or skill-root `.env` (git-ignored; plaintext or `obf:` XOR+base64 per ct-base §5) — never paste keys into chat or shipped files. Details: `references/openfda_api_key.md`.

## Errors

Brief; full table in `references/errors.md`.

- **429 / rate-limited** — exceed openFDA quota; fix: `--api-key` or lower frequency.
- **Persistent 404 on multi-word PT** — not indexed; swap to standard PT; `total()` auto-downgrades 404→`.exact`.
- **`--max > 10000`** — clamped to HARD_CAP 10000 (API-return-order first N, selection bias).
- **Outbound Coze rejected / unreachable** — endpoint not allow-listed / token invalid / `safety_rest_node` undeployed; add `--offline` to fall back to local-direct.

## Comparative Study Design Mode

For "compare X vs Y" / "within-class head-to-head" / "active-comparator" requests, switch to the comparative track (single-drug default otherwise). Steps: ① data prep (`faers-data-prep.md`) → ② study style + 4 workloads (`faers-comparative-design.md`) → ③ metrics / comparators / robustness (`faers-method-library.md`) → ④ evidence tiers + claim boundaries (`evidence-hierarchy.md`).

**Hard rules:** never run disproportionality on unprepared raw counts; present all four configurations then recommend one; label every result `[Tier 1]` signal / `[Tier 2]` comparative / `[Tier 3]` robustness; Tier-4 claims (incidence, causality, benefit–risk, prescribing) forbidden without external data; flag weak comparator indication overlap.

## Pipeline

- `ct-safety` → `ct-protocol`: signals feed the safety monitoring plan.
- `ct-safety` → `ct-registry`: control-trial safety-design benchmarking (CDE trials).
- CN-PV is an in-skill qualitative add-on, not a chain target. Units: `references/units.md`. Changelog: `CHANGELOG.md`.

## Regression Tests

Maintainer-only (stdlib, no pytest; **not shipped**): `python tests/mode_b_test.py` (10 hardening cases) and `python tests/mode_c_test.py` (F1–F11). Both offline by default. Details in `references/errors.md`.

## Bug Reporting (ct-base §20.3, adapter: `adapters/bug_report.py`)
Propose **at most once per session**, only on a strong signal **and** after ≥1 retry — never on repeated tuning. Always two-stage: ① show the sanitized report → ② send only on explicit consent; never re-propose after a decline. Full rules, 11-key whitelist, and CLI: `references/bug_reporting.md`.
