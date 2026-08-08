# AGENTS.md — ct-safety v0.1.35 (self-improvement convention)

This file defines the self-improvement and logging conventions for the ct-safety skill, following ct-base `BASE.md` §7.

## Mandatory initialization
- At the start of every new session, read this directory's `SKILL.md` and `references/units.md` to confirm the data sources and statistical methods are not outdated.

## Auto-logging
When the following occur, write to the LRN/ERR/FEAT sections of `~/.workbuddy/AGENTS.md` (format per ct-base):
- FAERS/openFDA API structural changes (field names, rate-limit rules);
- Adjustments to disproportionality formulas or signal thresholds;
- Experience integrating new data sources (e.g. EMA EudraVigilance, WHO VigiBase public layer).

## Red lines
- Read public FAERS data only; never input any confidential information; no data leaves the domain.
- Signal detection is for screening only; regulatory submissions must be separately assessed per GCP / ICH E2.
