# Phase 4 Royal Glass Validator - Decision Ledger

This ledger records decisions made during the Phase 4 grilling session. All entries marked **LOCKED** are governed by the user's explicit decision on 24 August 2026.

| ID | State | Decision | Governing source |
| --- | --- | --- | --- |
| D01 | LOCKED | The first validator is for Royal Glass only. Blue Haven remains a separate future workflow. | User decision |
| D02 | LOCKED | The first run processes only the Needs Validation cohort. | User decision |
| D03 | LOCKED | Each run receives one authoritative input workbook in `data/input`; original values and provenance are never overwritten. | User decision |
| D04 | LOCKED | Neon Postgres is the persistent source of truth, with a reviewer-friendly Excel export for each run. | User decision; Linear MT-263 |
| D05 | LOCKED | Retain compact audit evidence indefinitely; retain raw page snapshots for 90 days. | User decision |
| D06 | LOCKED | A human override is protected: automation can flag conflicting new evidence but cannot silently replace the decision. | User decision |
| D07 | LOCKED | Model real businesses as Competitor Entities linked to immutable Source Records. Auto-link only high-certainty matches; retain and review ambiguity. | User decision |
| D08 | LOCKED | A successful v1 gives every input record a reproducible evidence-backed classification or a clear human-review outcome. | User decision |
| D09 | LOCKED | The competitor universe is New Zealand-wide. Include overseas businesses when evidence shows relevant New Zealand delivery; Auckland is a higher monitoring priority, not an eligibility boundary. | User decision |
| D10 | LOCKED | Retain URL, title, short evidence snippet, fetch timestamp, content hash, structured service and region facts, and source type. Official sites govern service claims; material source conflicts and any fetch failure require review rather than Irrelevant. | User decision |
| D11 | LOCKED | Use evidence-backed High, Medium, and Low confidence bands rather than a numeric score. High may auto-approve; Medium and Low require review. | User decision |
| D12 | LOCKED | At High confidence, Direct, Adjacent, and Supplier / Ecosystem may auto-approve. Irrelevant always requires human review in v1. | User decision |
| D13 | LOCKED | The reviewer view includes the original record, proposed result and reasons, tags, evidence, conflicts, fetch errors, duplicate links, and override/note controls. | User decision |
| D14 | LOCKED | A missed Direct is costlier than a false Direct; ambiguous cases are reviewed instead of excluded. | User decision |
| D15 | LOCKED | Fetch only the homepage and up to three relevant same-domain pages. Use ordinary HTTP fetching, a 15-second timeout, and one transient-failure retry; retain failures and continue the batch. JS-only, blocked, robots-restricted, and inaccessible sites require review. | User decision |
| D16 | LOCKED | Before the first full run, verify a 25-record gold set covering the five outcomes and five failure scenarios. The user approves genuinely ambiguous cases and reviews every first-run High-confidence auto-approval. | User decision |
| D17 | LOCKED | V1 has no scheduler, n8n integration, notifications, dashboard, or automated action. Manual future runs compare new input with stored history, identify new or changed entities, and re-check Direct, Adjacent, unresolved, and failed records by default. | User decision |
| D18 | LOCKED | Build Phase 4 only. Future-facing scaffolding is limited to durable history, versioned rules, and a structured run summary; it must not implement Phase 5 intelligence or n8n orchestration. | User decision |

## MVP Guardrails

- Build a narrow Royal Glass validator, not a generic crawling platform.
- Do not include Blue Haven, Phase 5 intelligence, browser automation, sitemap/whole-site crawling, a queue platform, or numeric confidence scoring in v1.
- Do not include scheduled monitoring, notifications, dashboards, or n8n orchestration in v1.
- Keep future-phase scaffolding limited to stable data, versioned rules, and a structured run summary.
- The simple path is: import one workbook, fetch limited official evidence, classify or require review, persist the audit history, and export a reviewer workbook.

## Open Questions

- Classification rubric, including exact Adjacent/Supplier/Ecosystem/Irrelevant definitions and conflict handling.
- Fetcher limits and fallback policy.
- Gold-set composition, error priorities, and acceptance targets.
- Monitoring triggers, review cadence, n8n boundary, deployment, and security controls.
