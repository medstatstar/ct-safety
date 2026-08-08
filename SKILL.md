---
slug: ct-safety
displayName: 临床试验安全信号专家 / Clinical Trial Safety Signal
name: ct-safety
cn_name: 临床试验安全信号专家
version: 0.1.35
invocable: true
required_commands: [python]
summary: 基于 FDA FAERS 公开不良事件数据做 disproportionality 信号检测（PRR / ROR / IC / EBGM），辅助药物安全性监测；可选接入中国官方药物警戒通报（cdr-adr.org.cn）作定性佐证。检索公开不良事件数据（B 档：普通输入 + 对外检索）。
license: MIT
description: "基于 FDA FAERS（经 openFDA 公开 REST API）做药物-事件 disproportionality 信号检测，计算 PRR / ROR / IC / EBGM 及 95% 置信区间与信号判定；一次性流水线默认产出两份核心交付物——① 可渲染的 HTML 报告（可视化结论）② XLSX 数据簿（含全部原始 FAERS 计数、2×2 表、四种方法及 FDA 标签/CN-PV/评分明细，供逐条查阅与审计）；同时保留 JSON / Markdown 作兼容备份。可选 --with-cn-pv 增加中国官方药物警戒通报（cdr-adr.org.cn）定性检索作信号佐证。所有数据均为公开不良事件报告，不输入任何保密数据或信息，B 档（普通数据输入 + 对外检索），可快速推广技能。 / Signal detection on FDA FAERS (via openFDA public REST API): computes PRR / ROR / IC / EBGM with 95% CIs and signal flags from the drug-event 2x2 table. The one-shot pipeline emits TWO core deliverables by default — ① a renderable HTML report (visual conclusion) and ② an XLSX workbook holding ALL raw FAERS counts, the 2x2 table, the four methods, and FDA-label / CN-PV / score details for line-by-line audit; JSON / Markdown are kept as compatibility backups. Optional --with-cn-pv adds qualitative China official PV bulletin search (cdr-adr.org.cn) as signal corroboration. All data are public adverse-event reports; zero confidential data or information input — B-tier quickly-adoptable."
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
  network: "optional"
  network_note: "Reads only public sources: FDA FAERS / openFDA (https://api.fda.gov/drug/event.json) and, when --with-cn-pv, the public columns of cdr-adr.org.cn (国家不良反应监测中心; no WAF, no key). No confidential input; ordinary input + public retrieval (B-tier). NMPA main site is WAF-blocked (HTTP 412) and intentionally excluded. Low-frequency, keyless FAERS; optional --api-key raises quota."
  filesystem: "read-only to its own files; writes outputs ONLY to the user-specified --out-dir (default: current working directory). No system-path or hidden logging; any operational log (e.g. safety_err.log) is written under --out-dir (out_live/), never outside it, and FAERS raw responses are not persisted unless the user explicitly saves them."
  data: "no confidential data input; no external transmission of user data"

---

## Language

Pick the README that matches your language for human-readable, language-specific guides:

- **English guide** → [README.md](./README.md)
- **中文指南** → [README_zh-CN.md](./README_zh-CN.md)

This skill responds in the user's current input language and auto-detects / switches accordingly. The runtime scripts embed a locale check so all user-facing prompts switch to Chinese on a `zh-*` locale and to English otherwise. Code comments and documentation are English-only.

The SKILL.md body, `references/*.md`, and `AGENTS.md` are English-only and agent-facing; runtime command prompts switch to Chinese / English by locale. For end-to-end walkthroughs and troubleshooting in your language, open the README above.

# Clinical Trial Safety Signal

> Safe by default: **overview-first**. Step 1 (overview) runs automatically; Step 2 (detailed retrieval) runs ONLY after the user explicitly confirms.

## Disclaimer & Intended Use

- **Audience.** This skill is intended for **pharmacovigilance / clinical-trial methodologists and drug-safety professionals**. It is a methodologic signal-screening aid, not end-user health software.
- **Not a clinical or regulatory decision tool.** All outputs are **statistical disproportionality signals** computed from *spontaneous* adverse-event reports (FDA FAERS), which are subject to reporting bias, under-reporting, and confounding. A signal **does NOT establish causation** and **MUST NOT** be used to start, stop, or change any medication, or to make clinical or regulatory decisions. Always corroborate with RCTs, product labels, and qualified clinical/regulatory judgment (ICH E2 family).
- **Data flow (transparent).** Reads ONLY public sources — FDA FAERS / openFDA and, optionally, the public columns of cdr-adr.org.cn. Writes outputs SOLELY to the user-specified `--out-dir` (default: current working directory). **No system-path or hidden logging**; any operational log (e.g. `safety_err.log`) is written ONLY under `--out-dir` (e.g. `out_live/`), never outside it, and FAERS raw responses are not persisted unless the user explicitly saves them. Zero confidential data input; no user data is transmitted externally.
- **Dev artifacts excluded from the runtime package.** The `tests/` directory (regression harness) is shipped only in the source repo, not in the installed runtime package.

## Purpose

Run pharmacovigilance disproportionality analysis on FDA FAERS public adverse-event data to surface potential drug–event safety signals (PRR / ROR / IC / EBGM), supporting clinical-trial safety surveillance and label / signal screening. Optional China official PV bulletins (cdr-adr.org.cn) provide qualitative corroboration only.

## Data Sources

| Source | Access | Status |
|---|---|---|
| FDA FAERS (`drug/event.json`) | Official public REST API, direct-connect, no key needed (low-frequency) | Required (B-tier, quantitative) |
| FDA Label (`drug/label.json`) | Same openFDA, no key; adverse_reactions / warnings | Optional `--with-fda-label` (3rd source) |
| cdr-adr.org.cn | Public columns scraped (no WAF, no key) | Optional `--with-cn-pv` (qualitative only) |

**Key mechanism:** openFDA works keyless (anonymous 240 req/min, 1,000 req/day per IP); an optional free key only raises quota. The key, when used, is **stored locally only** (env var / local `.env`) and sent **only over HTTPS to the official openFDA endpoint** — never to any third party. NMPA main site is WAF-blocked (HTTP 412) and intentionally excluded. All data are public adverse-event reports; zero confidential input.

See `references/fetch_pipeline.md` for endpoint details, indexable/non-indexable fields, and `count` endpoint pitfalls.

## Methods

Four disproportionality measures on the drug–event 2×2 table, plus multiple-testing and corroboration layers:

- **PRR** — signal if PRR ≥ 2 **and** χ² ≥ 4.
- **ROR** — signal if lower 95% CI > 1.
- **IC** (UMC/VigiBase Information Component) — signal if lower 95% CI > 0.
- **EBGM** (FDA MGPS Bayesian shrinkage) — signal if EB05 ≥ 2.
- **BH-FDR** Benjamini-Hochberg q-value across top-N events (R13) and benchmarks (R5).
- **PT→SOC** MedDRA organ-class grouping (curated, "Unmapped" fallback).
- **Continuity** Haldane-Anscombe (+0.5/cell; `a==0` and negative cells → conservative null).
- **aROR** multi-drug adjusted ROR (`--compare-drugs`).
- **Temporal anomaly** CUSUM / rolling-Z / changepoint (`--trend`).
- **Safety Signal Score (0–100) + T1–T4 tier** (`--with-fda-label`).

Full formulas, thresholds, EBGM/MGPS math, FDR, aROR, trend, and the score/tier weighting are in `references/methods.md`.

## Features

| Capability | Source | Scenario |
|---|---|---|
| Drug adverse-event profile | FAERS | Safety baseline: a drug's top reported reactions |
| Drug–event signal detection | FAERS | Is a drug–event pair over-reported (PRR/ROR/IC/EBGM) |
| Multi-method cross-judgement | — | ROR CI>1 / PRR≥2 & χ²≥4 / IC CI>0 / EB05≥2 |
| Structured output (HTML + XLSX = core deliverables / JSON / MD backup, optional PNG) | — | Export — HTML (visual) + XLSX (all raw data) |
| China official PV bulletins | cdr-adr.org.cn | Qualitative corroboration only — NOT for disproportionality |
| Chained invocation | — | → `ct-protocol` (safety plan), → `ct-registry` (trial design) |
| Multi-event FDR control | — | BH q-value over top-N / benchmarks |
| PT→SOC grouping | — | Readable signal grouping |
| Continuity + control validation | — | Sparse 2×2 guard; `--validate-controls` self-check |
| Temporal anomaly (`--trend`) | — | Quarterly CUSUM / rolling-Z / changepoint |
| Multi-drug aROR (`--compare-drugs`) | — | Focal vs pooled-reference adjusted ROR |
| Score 0–100 + T1–T4 (`--with-fda-label`) | FAERS×Label×CN-PV | Triangulated evidence tier |
| Non-ASCII drug-name auto-translate | — | `--drug 阿司匹林` → `aspirin`; disable `--no-resolve-drug-name` |

## Requirements

- Python 3.10+ (Anaconda `C:\Tools\anaconda3\python.exe` recommended).
- Required: `requests`. Optional: `matplotlib` (PNG charts).
- Network: read-only FAERS public API.
- Optional: openFDA API key (raises quota only; never required).

## ⚠️ Safety

- Network: retrieval (present / `--out-xlsx`) runs lightweight openFDA `count` facet queries (seconds, no case download); **case-level download requires explicit `--run`** (throttled by HARD_CAP=10000).
- Reads FAERS public reports ONLY — **zero confidential data or information input** (B-tier).
- China PV bulletins are **qualitative narrative** — NO per-drug-event counts; must **NOT** feed disproportionality; only corroborate a FAERS signal.
- Signal detection is for screening, not causal conclusion; regulatory submission (DSUR / PBRER / label change) must be assessed per GCP / ICH E2 separately.

## Workflow

Two-step, overview-first (default since v0.1.18: **present summary in context, Excel on demand**):

1. **Step 1 — Overview (automatic):** `fetch_reports.py --drug X` sends 8 `count` facets, prints the full-matched summary to context in seconds, caches `faers_summary_cache.json`. No confirmation needed.
2. **Step 2 — Detail (only after explicit confirm):** `--out-xlsx` builds a 3-sheet + 8-chart summary Excel from cache; `--run` downloads individual case reports (HARD_CAP 10000) for age/country stats. Signal detection goes through `ct_safety.py` / `disproportionality.py`.

`scripts/overview.py` is deprecated (merged into Step 1). Full workflow, caching, `--parallel`, XLSX layout, and MedDRA PT caveats: `references/fetch_pipeline.md`.

### One-shot signal report (`ct_safety.py`) — two core deliverables

Running `ct_safety.py --drug X --event Y` (with `--run`) writes, into `--out-dir`:

- **`faers_report.html`** — the visual report (open in browser preview). **Core deliverable ①.**
- **`faers_report.xlsx`** — the data workbook with ALL raw information: FAERS counts, the 2×2 table, the four disproportionality measures, and — when enabled — FDA Label / CN-PV / Score sheets. **Core deliverable ②; use it to audit every number.**
- `faers_report.md` / `*.json` — compatibility backups only.

The run ends by printing an explicit "核心交付物 / Core Deliverables" block naming both files.

## API Key (openFDA) — optional, self-configured

The skill runs **without a key**. A free key only raises quota (240 req/min, 120,000 req/day per key). **The key is never required.** Provide it via your own configuration only (do NOT paste keys into chat or any file that ships with the skill):

- CLI: `--api-key YOUR_KEY`
- Env var: `export OPENFDA_API_KEY=YOUR_KEY` (auto-read; recommended)
- Skill-root `.env`: `OPENFDA_API_KEY=YOUR_KEY` (git-ignored, never shipped). The value may be plaintext **or** an `obf:`-prefixed XOR+base64 blob — `resolve_api_key` auto-detects and decodes (ct-base §5 recommended for private keys).

Bilingual apply steps + quota table + packaging red line: `references/openfda_api_key.md`. Skill-root `.gitignore` / `.clawhubignore` exclude `.env` / `*.key` / `credentials.json`, so a user's key can never be bundled into a published skill.

## Errors

Brief; full table in `references/errors.md`.

- **429 / rate-limited** — exceed openFDA quota (anonymous 240/min, 1,000/day; key 120k/day, by request count). Fix: `--api-key` or lower frequency.
- **`--drug` without `--event`** — auto-degrades to top-N adverse-event report; add `--event` for signal.
- **Persistent 404 on 3-word PT** (e.g. `RENAL FAILURE ACUTE`) — not indexed; swap to standard PT (`ACUTE KIDNEY INJURY`). `total()` auto-downgrades 404→`.exact`.
- **CN-PV 412/WAF** — expected; only cdr-adr.org.cn scraped.
- **`--max > 10000`** — clamped to HARD_CAP 10000 (API-return-order first N, selection bias).

## Comparative Study Design Mode

For "compare X vs Y" / "within-class head-to-head" / "active-comparator" requests, switch to the comparative track (single-drug default otherwise):

| Step | Reference |
|---|---|
| 1. Data prep (normalize → PS-role filter → de-dup → quality gate) | `references/faers-data-prep.md` |
| 2. Study style + 4 workloads (Lite/Standard/Advanced/Publication+); dependency rules | `references/faers-comparative-design.md` |
| 3. Metrics, comparator logic, characterization, robustness | `references/faers-method-library.md` |
| 4. Evidence-tier labeling + claim boundaries | `references/evidence-hierarchy.md` |

**Hard rules:** never run disproportionality on unprepared raw counts; present all four configurations then recommend one; label every result `[Tier 1]` signal / `[Tier 2]` comparative / `[Tier 3]` robustness; Tier-4 claims (incidence, causality, benefit–risk, prescribing) forbidden without external data; flag weak comparator indication overlap. Adapted from `faers-multi-drug-soc-planner` / `active-comparator-single-soc-faers-safety-comparison` (AIPOCH, MIT).

## Pipeline

- `ct-safety` → `ct-protocol`: signals feed the safety monitoring plan.
- `ct-safety` → `ct-registry`: control-trial safety-design benchmarking (CDE trials).
- CN-PV is an in-skill qualitative add-on, not a chain target.

Atomic-task unit index: `references/units.md`. Changelog: `references/changelog.md`.

## Regression Tests

Stdlib-only suite (no pytest): `python tests/run_tests.py` (offline) / `--live` (real openFDA). `tests/_mocks.py` stubs network; `tests/diagnose_rounds.py` runs 10×10 adversarial cases (CRASH/ANOMALY/OK). Details in `references/errors.md`.
