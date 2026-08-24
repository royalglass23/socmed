# Royal Glass Validator

Local Python foundation for Phase 4 competitor validation. It owns versioned rules, the database migration contract, a guarded development-Neon import of the authoritative Needs Validation workbook, and bounded official-site evidence capture; it does not classify competitors or send results to external systems.

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

7. Classify fetched records with the tracked deterministic rubric:

   ```powershell
   python -m royal_glass_validator classify --confirm-development-neon
   ```

   Only clear official evidence of Tier 1 glass balustrade or pool-fencing delivery in New Zealand is auto-approved as
   Direct. Clear official Adjacent and Supplier / Ecosystem evidence may also auto-approve; Irrelevant, incomplete,
   conflicting, and failed evidence remain Review Required. The command links a Source Record only when one existing
   Competitor Entity has a compatible normalized official domain or a matching verified phone and name. Auckland
   evidence raises the linked entity's monitoring priority without changing eligibility.

The migration runner requires an explicit confirmation and a code-reviewed, exact development target identity in `config/development-target.toml`. It records a SHA-256 checksum for every applied migration, refuses altered applied files, and never prints the connection string.
