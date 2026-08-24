"""Discover and apply checksum-protected PostgreSQL schema migrations."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol


class MigrationError(RuntimeError):
    """Raised when migration history is inconsistent or migration execution fails."""


class Cursor(Protocol):
    def execute(self, query: str, params: tuple[object, ...] | None = None) -> None: ...

    def fetchone(self) -> tuple[str] | None: ...

    def __enter__(self) -> "Cursor": ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...


class Connection(Protocol):
    def cursor(self) -> Cursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@dataclass(frozen=True)
class Migration:
    name: str
    checksum: str
    sql: str


def discover_migrations(migrations_directory: Path) -> tuple[Migration, ...]:
    """Return ordered SQL migrations with stable content checksums."""
    if not migrations_directory.is_dir():
        raise MigrationError(f"Migration directory does not exist: {migrations_directory}")
    files = sorted(migrations_directory.glob("*.sql"))
    if not files:
        raise MigrationError(f"No SQL migrations found in: {migrations_directory}")
    names = [file.name for file in files]
    if len(names) != len(set(names)):
        raise MigrationError("Migration filenames must be unique.")
    return tuple(
        Migration(name=file.name, checksum=sha256(file.read_bytes()).hexdigest(), sql=file.read_text(encoding="utf-8"))
        for file in files
    )


def apply_migrations(connection: Connection, migrations: tuple[Migration, ...]) -> tuple[str, ...]:
    """Apply unseen migrations atomically and refuse a changed applied migration."""
    applied: list[str] = []
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS _validator_schema_migrations (
                    migration_name text PRIMARY KEY,
                    checksum text NOT NULL,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext('royal_glass_validator_schema_migrations'))")
            for migration in migrations:
                cursor.execute(
                    "SELECT checksum FROM _validator_schema_migrations WHERE migration_name = %s",
                    (migration.name,),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    if existing[0] != migration.checksum:
                        raise MigrationError(f"Applied migration checksum changed: {migration.name}")
                    continue
                cursor.execute(migration.sql)
                cursor.execute(
                    "INSERT INTO _validator_schema_migrations (migration_name, checksum) VALUES (%s, %s)",
                    (migration.name, migration.checksum),
                )
                applied.append(migration.name)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return tuple(applied)
