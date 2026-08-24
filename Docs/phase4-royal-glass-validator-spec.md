# Phase 4 Royal Glass Competitor Validator

Status: **Approved for Phase 4 ticketing**  
Scope: Royal Glass Phase 4 only

## Purpose

Validate the existing Royal Glass **Needs Validation** cohort with reproducible website evidence. The validator classifies clear cases, sends uncertainty to human review, preserves source provenance, and retains history for later manual comparison runs.

## MVP boundary

Included:

- One authoritative Royal Glass workbook per run, supplied in `data/input`.
- Only the workbook's Needs Validation cohort.
- Limited official-site fetching, deterministic classification, retained evidence/errors, Neon Postgres history, and an Excel reviewer export.
- Manual re-runs that can identify new, changed, unresolved, or failed records.

Excluded:

- Blue Haven, Phase 5 intelligence, n8n orchestration, scheduling, notifications, dashboards, browser automation, generic crawling, sitemap or whole-site crawling, queue infrastructure, and numeric confidence scoring.

## Geographic and classification rubric

The competitor universe is New Zealand-wide. Auckland is a monitoring-priority attribute, not an eligibility boundary. An overseas business is included only when evidence shows relevant New Zealand delivery.

| Classification | Rule |
| --- | --- |
| Direct | Clear official evidence of Royal Glass Tier 1 delivery in New Zealand: glass balustrades and/or glass pool fencing. |
| Adjacent | Relevant to the same project or customer journey but not a confirmed Tier 1 competitor. |
| Supplier / Ecosystem | Relevant supplier or trade-support business without proven competing installation delivery. |
| Irrelevant | Evidenced as outside the Royal Glass competitor universe; it always requires human review in v1. |
| Review Required | An outcome, not a classification, used for insufficient, conflicting, blocked, or failed evidence. |

Tags retain nuance without creating subclasses: `pool-fencing`, `balustrades`, `both`, `broad-glazier`, `supplier-with-installation`, `regional`, `residential`, and `commercial`.

- A broad glazier with credible Tier 1 installation evidence is Direct with `broad-glazier`.
- A supplier with clear Tier 1 installation delivery is Direct with `supplier-with-installation`.
- Direct requires Tier 1 and New Zealand delivery evidence; a business need not serve every New Zealand region.

## Evidence and confidence

For each checked page, retain URL, title, short exact evidence snippet, fetch timestamp, content hash, structured service and region facts, and source type.

Official websites govern service claims. Google or business listings support identity, location, and contact facts. Material conflicts require review.

| Confidence | Meaning | Action |
| --- | --- | --- |
| High | Clear official Tier 1 and New Zealand-delivery evidence with no material conflict. | Auto-approve Direct, Adjacent, or Supplier / Ecosystem. |
| Medium | Relevant but incomplete evidence. | Review Required. |
| Low | Weak, unavailable, failed, or contradictory evidence. | Review Required. |

No fetch failure, missing site, 403, block, robots restriction, timeout, or lack of evidence may become Irrelevant. A missed Direct is treated as more costly than a false Direct.

## Identity and review

- A **Competitor Entity** represents the real business.
- A **Source Record** is an immutable imported or discovered row linked to an entity when identity is high certainty.
- Keep every Source Record and its provenance. Do not silently delete or merge rows.
- Automatically link only high-certainty matches, such as a normalized final domain with compatible identity or matching verified phone and name. Redirects, franchises, shared corporate sites, and conflicts require review.
- A protected human override remains authoritative until a reviewer explicitly supersedes it, with reason and timestamp. Automation can flag conflicting new evidence but cannot replace it.

The reviewer export shows the original record, proposed classification and reasons, tags, evidence, conflicts, fetch errors, duplicate links, and override/note controls.

## Fetcher policy

For each site, fetch the homepage and at most three relevant same-domain service, about, or contact pages.

- Use ordinary HTTP requests only.
- Allow 15 seconds per request.
- Retry transient timeout, rate-limit, or server failures once.
- Record each result as it is processed and continue the batch after individual failures.
- JavaScript-only, blocked, robots-restricted, and inaccessible sites become Review Required. There is no browser fallback in v1.

## Data contract

The persistent model must remain simple and migration-friendly:

- `competitor_entities`: the real business and current identity facts.
- `source_records`: immutable imported/discovered rows and provenance.
- `entity_links`: high-certainty links or reviewer-resolved identity links.
- `validation_runs`: input identity, timestamps, rule version, counts, and run outcome.
- `page_evidence`: compact retained evidence, extracted facts, and hashes.
- `fetch_failures`: failure type, attempted URL, retry information, and timestamp.
- `classification_decisions`: proposed/approved classification, confidence band, reasons, and rule version.
- `human_overrides`: reviewer decision, rationale, timestamps, and supersession history.

Keep compact audit history indefinitely. Retain raw page snapshots for 90 days, then prune them while retaining the compact evidence record.

## Monitoring boundary and future scaffolding

V1 runs manually. A later manual run imports a new discovery workbook, links known entities, identifies new candidates, compares stored hashes, and re-checks Direct, Adjacent, unresolved, and failed records. Supplier / Ecosystem records remain stored but are not automatically monitored yet.

Future scaffolding is limited to:

- versioned classification rules;
- the persistent data contract above; and
- a compact run summary that a future caller can consume.

Future n8n may trigger the existing CLI and read the summary. It must not own classification rules, evidence history, or the source of truth.

## Gold-set and acceptance gate

Before a full run, verify 25 manually approved cases: five each of Direct, Adjacent, Supplier / Ecosystem, Irrelevant, and Review Required. Include five failure scenarios: dead site, timeout, block, JavaScript-only site, and conflicting sources.

The user approves genuinely ambiguous gold-set cases and reviews every High-confidence auto-approval from the first full run. V1 is acceptable only when fetch failures never become Irrelevant, human overrides are never replaced, and every outcome retains evidence or a captured failure.

## Small implementation plan

1. Create configuration, rule-versioning, and the Neon schema/migrations; keep credentials in a local ignored `.env` file.
2. Import and preserve the one workbook's Needs Validation source rows.
3. Implement the bounded HTTP fetcher and evidence/failure recording.
4. Implement the deterministic rubric, confidence bands, duplicate linking, and protected overrides.
5. Produce the reviewer export and compact run summary.
6. Build and run the gold set, then process the full cohort with the required human review.

## Proposed operating model pending sign-off

Run v1 locally as a Python CLI. It reads `data/input`, connects to Neon, and writes a dated Excel review export. Use one Neon project with isolated dev and live branches/databases so gold-set work cannot alter live competitor history. Connection strings remain in a local ignored `.env` file.

No production code, Neon provisioning, credentials, migrations, or data import is authorised by this specification alone.
