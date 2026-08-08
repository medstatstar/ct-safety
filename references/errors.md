# Errors & Troubleshooting (agent-facing)

Companion to the `## Errors` section of SKILL.md. Full error table preserved here.

| Error | Cause | Fix |
|---|---|---|
| `urllib.error.URLError` / timeout | No network / proxy | Confirm `api.fda.gov` reachable; configure proxy |
| HTTP 429 / rate-limited | Exceeded openFDA quota. **Official limits:** anonymous **240 req/min, 1,000 req/day (per IP)**; free API key **240 req/min, 120,000 req/day (per key)**. Rate-limited by **request count, not row count**; FAERS single-request `limit` max = 100 rows | Add `--api-key` (raises to 120k/day); or lower frequency. `fetch_reports.py` sleeps 0.5s/page + HARD_CAP 10000 (=100 requests) — only 10% of anonymous daily cap, safe |
| `--drug` given, `--event` omitted | Intent = top adverse events of a drug, not a pair signal | **No longer errors**: auto-degrades to "top-N adverse-event report" (no 2×2). Add `--event <MedDRA PT>` to compute a signal |
| Field-name mismatch | Wrong drug-name field | Default `patient.drug.medicinalproduct`; standardize via `--field patient.drug.openfda.substance_name` |
| CN-PV: HTTP 412 / WAF | nmpa.gov.cn blocked by CDN/WAF | Expected — only cdr-adr.org.cn is scraped; NMPA intentionally excluded |
| CN-PV: 0 hits | Keyword too specific / only latest page sampled | Pass `--drug-cn` (Chinese name) + `--event-cn`; raise `--cn-max` (sampling only, not full archive) |
| FAERS multi-word event **persistent** 404 `NOT_FOUND` | That three-word PT is not accepted by openFDA (e.g. `RENAL FAILURE ACUTE`), not transient jitter | `total()` has built-in "404 → `.exact` downgrade"; still 404 → swap to standard MedDRA PT (`ACUTE KIDNEY INJURY`, not `RENAL FAILURE ACUTE`); two-word PTs (e.g. `HEPATIC FAILURE`) usually work |
| Case download `--max > 10000` | Trying to exceed free quota cap | HARD_CAP=10000; auto-clamped to 10000 with a warning. Downloaded = **first N in API-return order (not random sample)** — mind selection bias in stats |

## Diagnostic / regression harnesses

- `tests/run_tests.py` — stdlib-only regression suite (no pytest). Offline (mock
  network) covers pure functions / modules / render / `run` branches.
  - `python tests/run_tests.py` (offline) / `--live` (real openFDA) /
    `CT_SAFETY_LIVE=1 python tests/run_tests.py`.
- `tests/_mocks.py` — offline network stub: synthetic but internally consistent
  FAERS counts drive `run` branches without consuming quota.
- `tests/diagnose_rounds.py` — adversarial per-iteration harness: 10 scenarios per
  iteration (simple→complex, every code path), auto-classifies CRASH/ANOMALY/OK with
  hardcoded contract checks (zero co-occurrence must not fabricate a signal; negative
  cells must not crash; score ∈ [0,100]; tier ∈ {T1–T4}; `map_soc` correctness).
  - `python tests/diagnose_rounds.py --iter 1` / `--iter all` (100 cases) / `--list`.
  - 10 themed iterations: ① numeric/2×2 edge ② SOC mapping ③ benchmark/compare/multi
    ④ trend ⑤ score/tier/label/cn-pv/control ⑥ control-validation+continuity
    ⑦ CLI-flag combos ⑧ case-level integration ⑨ adversarial/fuzz ⑩ previously-fixed
    bug regression.
