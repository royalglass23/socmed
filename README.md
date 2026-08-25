# Royal Glass Validator

Local Python validator for Phase 4 competitor validation. It owns versioned rules, the database migration contract, a guarded development-Neon manual comparison run of the authoritative Needs Validation workbook, bounded official-site evidence capture, deterministic classification, protected reviewer overrides, and a reviewer workbook export. It does not schedule runs or send results to external systems.

## Local setup

1. Create a virtual environment and install the project with its development tools:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   ```

2. Copy `.env.example` to `.env` and set the **development Neon** `DATABASE_URL_DEV`. Keep `VALIDATOR_DATABASE_ENVIRONMENT=development`; `.env` is ignored and must never be committed. `DATABASE_URL_PROD` is reserved for an explicitly approved production release.

3. Inspect the foundation without connecting to Neon:

   ```powershell
   python -m royal_glass_validator rules
   python -m royal_glass_validator migrations
   ```

4. Once development Neon access is explicitly approved, apply the schema:

   ```powershell
   python -m royal_glass_validator migrate --confirm-development-neon
   ```

5. Place exactly one authoritative Royal Glass `.xlsx` workbook in `data/input`, then import its
   `Needs Validation` cohort into the approved development Neon database:

   ```powershell
   python -m royal_glass_validator import --confirm-development-neon
   ```

   The importer validates the whole workbook before opening its database transaction. It accepts
   only the `Needs Validation` worksheet, requires a unique `Entity ID` and a `Decision Group`
   beginning with `Needs Validation` for every imported row, and records the complete original row
   values, workbook checksum, worksheet, and source row number. It does not modify the workbook.

6. Capture evidence for imported records that have no prior fetch outcome:

   ```powershell
   python -m royal_glass_validator fetch --confirm-development-neon
   ```

   The fetcher uses ordinary HTTP only: the homepage plus at most three relevant same-domain pages,
   a 15-second timeout, and one retry for transient timeout, rate-limit, or server failures. It
   respects `robots.txt`, records each compact evidence item or fetch failure, and continues the
   batch. Blocked, JavaScript-only, inaccessible, missing, and robots-restricted sites remain
   `review_required`; there is no browser fallback. Raw page snapshots are retained with a 90-day
   expiry alongside compact evidence, and identical pages are linked to every immutable source row
   that produced them.

   For the normal first or later manual run, use the single guarded command instead. It verifies the
   25-case gold set before writing, imports the immutable workbook, rechecks only new or changed
   records plus prior Direct, Adjacent, unresolved, and failed records, then prints a compact JSON
   summary for a future caller. Supplier / Ecosystem records remain stored but are not monitored by
   default.

   ```powershell
   python -m royal_glass_validator run --confirm-development-neon
   ```

   This command has no scheduler, n8n integration, or production target. A protected override is
   never changed by the run; a later automated proposal can only appear as a reviewer revalidation
   conflict.

   If an ordinary-HTTP request is interrupted, do not re-import the workbook. Continue the retained
   running run by UUID instead; this preserves its immutable Source Records and records timeouts as
   review-required failures rather than allowing one stalled domain to block the whole cohort.

   ```powershell
   python -m royal_glass_validator resume --confirm-development-neon --run-id <validation-run-uuid>
   ```

   For a constrained shell or an intentionally small manual pass, add `--max-records 5`. Each invocation
   commits its retained outcomes before returning and reports `"outcome":"running"` until the final batch;
   repeat the same command and run UUID until it reports `"outcome":"completed"`.

7. Classify fetched records with the tracked deterministic rubric:

   ```powershell
   python -m royal_glass_validator classify --confirm-development-neon
   ```

   Only clear official evidence of Tier 1 glass balustrade or pool-fencing delivery in New Zealand is auto-approved as
   Direct. Clear official Adjacent and Supplier / Ecosystem evidence may also auto-approve; Irrelevant, incomplete,
   conflicting, and failed evidence remain Review Required. The command links a Source Record only when one existing
   Competitor Entity has a compatible normalized official domain or a matching verified phone and name. Auckland
   evidence raises the linked entity's monitoring priority without changing eligibility.

8. Export the latest reviewer view to a dated, one-way workbook:

   ```powershell
   python -m royal_glass_validator export --confirm-development-neon
   ```

   The export contains immutable source values, proposals, confidence, compact evidence, fetch errors,
   high-certainty identity links, and the active protected override. A disagreement between an automated
   proposal and that override is explicitly marked for revalidation; exporting does not alter stored data.

9. For an identity-unlinked record, explicitly link it to an existing entity or create a new entity before overriding it:

   ```powershell
   python -m royal_glass_validator resolve-identity --confirm-development-neon --decision-id <decision-uuid> --entity-id <entity-uuid> --rationale "Verified by the official contact details." --reviewer "Reviewer name"
   ```

   To create a new entity instead, replace `--entity-id` with `--legal-name` and `--display-name` (with optional
   `--primary-domain` and `--verified-phone`). Identity resolution is explicit and never replaces an existing link.

10. Record a protected, attributable human decision through the explicit review command (the workbook is not an upload path):

   ```powershell
   python -m royal_glass_validator override --confirm-development-neon --decision-id <decision-uuid> --classification adjacent --rationale "Official evidence supports an adjacent service only." --reviewer "Reviewer name"
   ```

   A reviewer must provide both their identity and rationale. Existing overrides remain immutable and can only be
   replaced through an explicit `--supersedes-override-id` value; a conflicting future automation result cannot replace them.

The migration runner requires an explicit confirmation and a code-reviewed, exact development target identity in `config/development-target.toml`. It records a SHA-256 checksum for every applied migration, refuses altered applied files, and never prints the connection string.
