# ct-safety — Advanced Reference

Detailed reference moved out of `SKILL.md` to keep it within the 200-line soft cap (ct-base §16.1). SKILL.md keeps behaviour rules + pointers; this file holds the expanded tables and rationale.

---

## 1. Full capability table (expanded)

Companion to the condensed `## Features` table in SKILL.md — same capabilities, with scenarios and boundaries.

| Capability | Source | Scenario |
|---|---|---|
| Drug adverse-event profile | FAERS | Safety baseline: a drug's top reported reactions |
| Drug–event signal detection | FAERS | Is a drug–event pair over-reported (PRR/ROR/IC/EBGM) |
| Multi-method cross-judgement | — | ROR CI>1 / PRR≥2 & χ²≥4 / IC CI>0 / EB05≥2 |
| Structured output | — | HTML (visual) + XLSX (all raw data) are the core deliverables; JSON / MD are backups; PNG optional |
| China official PV bulletins | cdr-adr.org.cn | Qualitative corroboration only — NOT for disproportionality |
| Labeled / unlabeled corroboration | `corroborative_sources.py` (DailyMed SPL + RxClass MED-RT + openFDA recalls) | Tells whether an event is already in the label / authoritative KB → downgrades known risks, upgrades unlabeled signals (ICH E2C / CIOMS VIII) |
| Chained invocation | — | → `ct-protocol` (safety plan), → `ct-registry` (trial design), → `ct-literature --safety` (published safety/CSM literature subset) |
| Published safety-literature corroboration | `ct-literature --safety` | Qualitative published-evidence backing (reviews / PV papers). **Boundary:** MUST NOT feed FAERS 2×2 disproportionality (would distort the counts) |
| Statistical guards | — | BH-FDR q-value over top-N / benchmarks · PT→SOC readable grouping · sparse 2×2 guard with `--validate-controls` self-check |
| Temporal anomaly (`--trend`) | — | Quarterly CUSUM / rolling-Z / changepoint |
| Multi-drug aROR (`--compare-drugs`) | — | Focal vs pooled-reference adjusted ROR |
| Score 0–100 + T1–T4 (`--with-fda-label`) | FAERS × Label × CN-PV | Triangulated evidence tier |
| Naranjo causality attribution (`--with-causality`) | FAERS time / dechallenge / rechallenge + optional label | Qualitative causality side-evidence (non-causal, independent of statistical signals) |
| Signal verification workflow (`--verify-signal`) | FAERS quarterly-report series | Time-series CUSUM / Poisson trend + dose-response / deconvolution (confirmatory supplement; dose-response / deconvolution need `--case-level` case data) |
| MedDRA coding aid (`--code-verbatim`) | verbatim AE terms | verbatim→PT fuzzy matching (built-in dictionary; LLM mode opt-in, not auto-enabled) |
| Signal prioritization & risk tiering (`--prioritize`) | Detected signals | Multi-dimensional score (severity × novelty × frequency × trend × multi-source) → CRITICAL/HIGH/MEDIUM/LOW; with `--with-fda-label` + `--trend`, adds a label-gap / anomaly-trend escalation layer |
| PSUR/PBRER auto-report (`--psur`) | Detected signals | Generates CIOMS / ICH E2C(R2)-format PSUR Markdown (psur.md) |
| Case-level de-duplication (on by default with `--case-level`) | FAERS individual case reports | L1 collapses follow-up `safetyreportversion` per `safetyreportid`; L2 flags suspected duplicates (demographic fingerprint + reaction-PT Jaccard, default 0.8) — flag-only unless `--drop-suspected-dupes`. Applies to the case listing ONLY; PRR/ROR/IC/EBGM come from aggregate endpoints and are NOT corrected. Disable via `--no-case-dedup` |
| Non-ASCII drug-name auto-translate | — | `--drug 阿司匹林` → `aspirin`; disable `--no-resolve-drug-name` |

---

## 2. Blocked / excluded sources — full evidence table

Not silently dropped — each was tested from this machine (2026-09-01) and the blocking reason recorded in `multi_source.COUNT_SOURCE_FEASIBILITY` / `corroborative_sources.BLOCKED_SOURCES`.

| Source | Status | Verified reason (2026-09-01) |
|---|---|---|
| PMDA JADER (Japan) | Not automatable (live) | `CsvDownload.jsp` contains `captchaText`; the full 4-table CSV is obtainable via browser/Coze channel or manual download (planned — see roadmap) |
| Health Canada (live API) | Legacy API unreachable locally | `health-products.canada.ca` API ReadTimeout; **but `open.canada.ca` open-data portal offers a full-database ZIP for download (planned)** |
| VAERS / CDC WONDER | Needs data-use agreement | D8 endpoint GET → 403, requires POST XML + agreement acceptance |
| EudraVigilance (EMA) | Needs authorization | Data sits inside BusinessObjects reports; `substances.json` → 404 |
| VigiAccess / VigiBase (WHO) | No public API | Pure SPA (757B), JS bundle has no data endpoint; full access requires paid authorization |
| MHRA iDAP (UK) | Unreachable locally | `info.mhra.gov.uk` ConnectTimeout |
| Taiwan FDA PV (fda.gov.tw) | Unreachable locally | 2026-09-01 live test 502 + ProxyError (needs special network/proxy), temporarily unconnectable |

Re-test any of these before claiming "no data" — conditions (e.g. PMDA dropping the captcha, or a non-CN egress) may change.

---

## 3. Thin-local-client architecture — expanded

Since v0.9.8 all safety retrieval uses a **thin local client**: the local side only performs computation (disproportionality / signal_score / check_event), while outbound retrieval defaults to the Coze unified endpoint `ct-search.coze.site/run` (shared with ct-registry; source names `faers` / `fda_label` / `dailymed` / `rxclass` / `fda_recall` / `hk_pv`). `adapters/coze_dispatch.py` rebinds global names via `FaersShim` / `FdaLabelShim`, so call sites in `ct_safety.py` and `corroborative_sources.py` need zero changes.

- **Default (outbound):** retrieval requests (drug/event public keywords) go to the Coze endpoint; server-side completes openFDA / NLM fetching and returns structured JSON. No local browser dependency; immune to local egress / WAF limits.
- **`--offline` (local-direct fallback):** skips Coze, connects directly to openFDA / NLM locally; `cdr-adr.org.cn` always local-direct (no WAF, Coze reachability for this CN domain unverified → not outbound).
- **Always local-direct exceptions:** `fetch_faers.query_total` (arbitrary query) and `fetch_case_reports` (raw case reports) — structured state cannot carry them, and openFDA direct is not WAF-blocked; `fetch_fda_label.check_event` (local-only judgement); `fetch_cn_pv` (cdr-adr.org.cn, reachable local-direct).
- **Publish red line:** Coze-side `safety_rest_node.py` (6 nodes) takes effect only after the author uploads the workflow bundle to the Coze console. Local code runs in `--offline` / local-direct mode without deployment; **the outbound path depends on Coze-side deployment.**

### Bilingual retrieval send-strategy (ct-base `bilingual_retrieval.md`)

All six English sources translate keywords **before** dispatch, in `coze_dispatch.dispatch()`:
- drug name → `drug_name_resolver.resolve(drug, auto=True)` (map `references/drug_name_map.json`, 471 entries);
- event term → `kw_localize.localize_with_fallback(event, "en")` (term map first, online translate API fallback, `CT_TRANSLATE_ONLINE=0` disables).
Both degrade to verbatim passthrough if the resolver is missing. This fixed the Chinese-keyword HTTP 400 against openFDA (verified live: `二甲双胍 + 乳酸酸中毒` → `metformin + Lactic acidosis` → real 2×2).

---

## 4. Reference index

| Topic | File |
|---|---|
| Methods, formulas, thresholds, EBGM/MGPS math | `methods.md` |
| Retrieval pipeline, caching, XLSX layout, MedDRA PT caveats | `fetch_pipeline.md` |
| Full error table + regression-test details | `errors.md` |
| openFDA API-key setup, quota, packaging red line | `openfda_api_key.md` |
| Comparative-study design (data prep / workloads / metrics / evidence tiers) | `faers-data-prep.md`, `faers-comparative-design.md`, `faers-method-library.md`, `evidence-hierarchy.md` |
| T1 trio roadmap (CA / JP / AU, deferred) | `roadmap_external_sources.md` |
| Bug reporting rules + 11-key whitelist | `bug_reporting.md` |
| Atomic-task unit index | `units.md` |
| Changelog | `../CHANGELOG.md` |
