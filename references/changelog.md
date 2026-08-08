# Changelog (agent-facing)

Moved from SKILL.md to keep the main file ≤200 lines (ct-base v1.1.20 §16.1).
Technical-fact reference; the most recent entry is authoritative.

- **v0.1.23** (2026-08-03) — **Bug fix: skill-root `.env` was never read.** `resolve_api_key()` declared `_DOTENV` but did not use it as the default, so `if dotenv_path and ...` short-circuited whenever the argument was omitted — a key in skill-root `.env` was silently ignored on the default path (`fetch_fda_label` unaffected because its call sites passed `_DOTENV` explicitly). Both modules now fall back to `_DOTENV` when `dotenv_path is None`. Added regression tests `test_resolve_api_key_priority_faers` / `_fda_label` covering the default path plus full CLI > env > `.env` > None precedence; they repoint `mod._DOTENV` at a temp file so a real `.env` is never touched. Verified fault-injection. Suite: 46 total, 44 PASS / 0 FAIL / 2 SKIP.

- **v0.1.22** (2026-08-03) — API-key application + packaging hygiene (no functional regression to signal math):
  - Key resolution hardened: `fetch_faers.py` and `fetch_fda_label.py` resolve the openFDA key from (priority) CLI `--api-key` > env `OPENFDA_API_KEY` > skill-root `.env`. The `.env` is git-ignored.
  - Packaging red line: new `.gitignore` (GitHub) and `.clawhubignore` (ClawHub) at skill root exclude `.env` / `*.key` / `*.secret` / `credentials.json` / `secrets.json` + runtime caches/outputs, so a key is never transferred.
  - Key-application guidance + post-install prompt: new `references/openfda_api_key.md` (bilingual). SKILL.md / README / sop.md carry the "apply & provide key after install" prompt and the "do not ship keys" rule.

- **v0.1.21** (2026-08-02) — Added the iterative robustness diagnostic harness `tests/diagnose_rounds.py` (no functional code change). Iterative 10×10 diagnostic battery: parameterized offline harness generating 10 scenarios/iteration (simple→complex, every code path) running `ct_safety.run()` against `tests/_mocks.py`, auto-classifying CRASH/ANOMALY/OK with hardcoded contract checks. 10 themed iterations: ① numeric/2×2 edge ② SOC mapping ③ benchmark/compare/multi-event ④ trend ⑤ score/tier/label/cn-pv/control ⑥ control-validation+continuity ⑦ CLI-flag combos ⑧ case-level integration ⑨ adversarial/fuzz ⑩ regression of all previously-fixed bugs. Result: 0 CRASH, 0 real skill defects. Note: changelog gap for v0.1.15–v0.1.20 (fill on request).

- **v0.1.14** (2026-08-02) — Resolved three known non-blocking limitations (regression suite 44 PASS / 2 SKIP, 0 FAIL):
  - **#① `controls` component no longer always 0**: `safety_signal_score()` gains `control_pair`. In a normal `--run`, if the queried (drug,event) is itself a `CONTROL_DRUGS` anchor, it is scored by whether the measured signal matches the known expectation (match=10, mismatch=0), no extra network; on match it also counts as a control-validation corroboration source. Previously always 0 in a single `--run`.
  - **#② `map_soc` substring mis-grouping fix**: substring fallback now applies only to multi-word dictionary keys, longest-match-first, explicitly excluding generic words (`PAIN`/`KIDNEY`) from hijacking compound PTs (e.g. `CHEST PAIN` → explicit `Cardiac` entry, no longer `General`). Added explicit compound entries (`CHEST PAIN`/`ANGINA`/`BACK PAIN`/`JOINT PAIN`/`MUSCLE PAIN`/`NECK PAIN`/`FLANK PAIN`/`KIDNEY FAILURE`/`KIDNEY INJURY`/`RENAL PAIN`). Still a curated, non-certified MedDRA map.
  - **#③ cleaned `PT_TO_SOC` literal duplicate keys**: removed duplicate `GASTROINTESTINAL HAEMORRHAGE` / `INSOMNIA`; kept intentional cross-SOC same-name entries (`PNEUMONIA`/`PYREXIA`/`FATIGUE`).

- **v0.1.13** (2026-08-02) — Round-2 robustness fixes (10/10 PASS after fix):
  - **`compute()` negative-cell guard**: negative counts previously raised `OverflowError`/`NaN`; now any cell `< 0` returns conservative null (`signal_overall=False`, all sub-flags False) with explicit `note`, mirroring the `a==0` guard.
  - **`report.py` CN-PV `%d` crash (real bug)**: CN-PV section formatted `max_per_column` with `%d` while default was the **string** `"?"` — crashed with `TypeError` whenever that field was omitted. Now guards with `isinstance(mc, int)` and uses `%s`. Broke the entire `--with-cn-pv` report path.
  - **`_render_benchmark` transparency**: competitor drugs with no available counts were silently dropped; now unavailable rows render an explicit `无可用数据` row.
  - Test-only: corrected an over-strict `map_soc` expected value in the harness.

- **v0.1.12** (2026-08-02) — Bug fix: zero-co-occurrence no longer fabricates a signal under continuity. `disproportionality.compute()` with `continuity=True` (default) applied Haldane-Anscombe +0.5 to a structural-zero cell (a==0), producing a (often huge) OR from a never-co-reported pair and flagging it as a signal — contradicting EBGM (~1, no signal). Now `a==0` always returns conservative null (`signal_overall=False`, all four sub-method flags False) **regardless of `continuity`**, with explicit `note`. Completes the partial v0.1.9 `a==0` fix (which only addressed the exp-overflow crash).

- **v0.1.11** (2026-08-02) — Safety-signal method completion (all three backlog items closed):
  - **① EBGM / MGPS Bayesian shrinkage**: new `ebgm.py` implements FDA Mult-item Gamma-Poisson Shrinkage (DuMouchel 1999) gamma-Poisson mixture — posterior mean (EBGM), 2.5%/97.5% quantiles (EB05/EB95), signal when **EB05 ≥ 2**. Pure stdlib (regularized lower incomplete gamma via Numerical Recipes series / continued-fraction, no scipy). `disproportionality.compute()` now returns `EBGM` alongside ROR/PRR/IC (from raw counts, independent of Haldane). Corrects the prior mislabel that called IC "EBGM".
  - **② Case-level `case_id` fetch**: `fetch_faers.py` gains `fetch_case_reports()` (openFDA `limit` query) + CLI `--case-level N` to pull individual case safety reports (`safetyreportid` / `receivedate` / `seriousness` / `outcome` / `reaction_pt[]` / `drug[]`), written to `faers_cases.json`. Closes the R14 surveillance traceability interface (`case_id` reserved for `ct-pipeline build_traceability()`).
  - **③ MedDRA PT→SOC expansion**: `disproportionality.PT_TO_SOC` extended with EGFR-TKI / NSCLC class-effect high-frequency terms. Still curated, non-certified.

- **v0.1.10** (2026-08-02) — M2 backlog #4 (multi-source triangulation + quantitative scoring):
  - **#4 Multi-source triangulation + Safety Signal Score (0-100) + T1-T4 tiering**: new `fetch_fda_label.py` adds FDA Label (`drug/label.json`, keyless) as 3rd evidence source — `check_event()` flags labeled (known/expected) vs unlabeled (new/unexpected, higher priority). New `signal_score.py` composites FAERS × FDA Label × China PV × trend × control into a transparent 0-100 score and T1-T4 tier; weights centralized in `signal_score.WEIGHTS`. Exposed via `--with-fda-label` (defaults to FAERS × CN-PV dual-source when omitted).

- **v0.1.9** (2026-08-02) — M1 backlog #6, #5, #3:
  - **#6 Continuity correction + control validation**: `compute(continuity=True)` applies Haldane-Anscombe (+0.5/cell), default ON from v0.1.9 (`--no-continuity` reproduces v0.1.8); `CONTROL_DRUGS` + `summarize_control_validation()` drive `--validate-controls`. Also fixed a latent `a==0` exp-overflow crash.
  - **#5 Temporal anomaly**: new `time_series.py` — `fetch_monthly_series()` → `to_quarterly()` → `detect_anomaly()` (CUSUM + rolling-Z + changepoint, pure stdlib). Exposed via `--trend` (requires `--event`).
  - **#3 Multi-drug adjusted ROR (aROR)**: new `adjust_ror.py` — `adjusted_ror_aggregate()` (focal vs pooled reference, Haldane fallback), `mantel_haenszel_or()` (stratified pooled OR), `logistic_irls()` with Firth penalization (individual-level hook). Exposed via `--compare-drugs focal ref1 ref2 ...` (requires `--event`).

- **v0.1.8** (2026-08-02) — Two upstream-inspired enhancements:
  - **BH-FDR multiple-comparison control**: `disproportionality.benjamini_hochberg()` applied to R13 multi-event sweep and R5 competitor benchmark, surfacing `fdr_q` / `fdr_signal`. PRR p-value (1-df χ² upper tail via `math.erfc`, no scipy) feeds the correction.
  - **MedDRA PT→SOC grouping**: `disproportionality.map_soc()` maps high-frequency PTs to SOC (curated dictionary with "Unmapped" fallback); SOC column added to all event tables.

- **v0.1.7** (2026-07-31) — Fixed `--top-events-signal N` hanging silently / exiting 1. Root cause: R13 sweep issued 5 openFDA queries/event; in the sandbox `requests` socket timeout not reliably honored when openFDA holds a connection, so a throttled query stalled the sweep. Fix: each per-event query reuses up-front `drug_total`/`grand_total` (2 queries/event), runs in a daemon thread with hard join-timeout (~20s), adds a 150s wall-clock budget, wraps the multi-event stage so the main FAERS report is always written. Degrades gracefully under rate-limiting.
