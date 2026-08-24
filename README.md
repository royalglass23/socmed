# Royal Glass Validator

Local Python foundation for Phase 4 competitor validation. It owns versioned rules and the database migration contract; it does not import workbooks, fetch websites, classify competitors, or send data externally yet.

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

The migration runner requires an explicit confirmation and a code-reviewed, exact development target identity in `config/development-target.toml`. It records a SHA-256 checksum for every applied migration, refuses altered applied files, and never prints the connection string.
