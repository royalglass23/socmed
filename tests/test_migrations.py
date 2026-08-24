from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tempfile
import unittest

from royal_glass_validator.migrations import Migration, MigrationError, apply_migrations, discover_migrations


@dataclass
class FakeCursor:
    checksums: dict[str, str]
    selected_checksum: str | None = None
    statements: list[str] = field(default_factory=list)

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> None:
        self.statements.append(query)
        if query.startswith("SELECT checksum"):
            assert params is not None
            self.selected_checksum = self.checksums.get(str(params[0]))
        elif query.startswith("INSERT INTO _validator_schema_migrations"):
            assert params is not None
            self.checksums[str(params[0])] = str(params[1])

    def fetchone(self) -> tuple[str] | None:
        return (self.selected_checksum,) if self.selected_checksum else None


@dataclass
class FakeConnection:
    checksums: dict[str, str] = field(default_factory=dict)
    committed: bool = False
    rolled_back: bool = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.checksums)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class MigrationContractTests(unittest.TestCase):
    def test_discovers_migrations_in_filename_order_with_content_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "002_second.sql").write_text("SELECT 2;", encoding="utf-8")
            (directory / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")

            migrations = discover_migrations(directory)

            self.assertEqual([migration.name for migration in migrations], ["001_first.sql", "002_second.sql"])
            self.assertEqual(len(migrations[0].checksum), 64)

    def test_refuses_to_apply_a_changed_migration_that_is_already_recorded(self) -> None:
        migration = Migration(name="001_foundation.sql", checksum="new", sql="SELECT 1;")
        connection = FakeConnection(checksums={migration.name: "old"})

        with self.assertRaisesRegex(MigrationError, "checksum changed"):
            apply_migrations(connection, (migration,))

        self.assertTrue(connection.rolled_back)
        self.assertFalse(connection.committed)
