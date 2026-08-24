"""Load local, non-secret validator settings without exposing credentials."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib
from urllib.parse import unquote, urlsplit


class ConfigurationError(ValueError):
    """Raised when the local validator configuration is incomplete or malformed."""


@dataclass(frozen=True)
class ValidatorSettings:
    database_url: str | None
    ruleset_path: Path
    database_environment: str | None


@dataclass(frozen=True)
class DevelopmentDatabaseTarget:
    target_id: str
    host: str
    database_name: str


@dataclass(frozen=True)
class RuleSet:
    version: str
    brand: str
    country: str
    classifications: tuple[str, ...]
    review_outcome: str
    confidence_bands: tuple[str, ...]
    tags: tuple[str, ...]
    fetch_failure_outcome: str
    irrelevant_requires_human_review: bool
    protected_override_is_authoritative: bool


def load_settings(project_root: Path, environment: dict[str, str] | None = None) -> ValidatorSettings:
    """Load environment settings, allowing process values to override local .env values."""
    values = _read_dotenv(project_root / ".env")
    values.update(environment or os.environ)
    ruleset_value = values.get("VALIDATOR_RULESET", "config/rules/v1.toml")
    ruleset_path = Path(ruleset_value)
    if not ruleset_path.is_absolute():
        ruleset_path = project_root / ruleset_path
    database_environment = values.get("VALIDATOR_DATABASE_ENVIRONMENT")
    database_key_by_environment = {
        "development": "DATABASE_URL_DEV",
        "production": "DATABASE_URL_PROD",
    }
    database_url = values.get(database_key_by_environment.get(database_environment, ""))
    return ValidatorSettings(
        database_url=database_url,
        ruleset_path=ruleset_path,
        database_environment=database_environment,
    )


def load_development_database_target(project_root: Path) -> DevelopmentDatabaseTarget:
    """Load the tracked, credential-free development database identity."""
    path = project_root / "config" / "development-target.toml"
    try:
        with path.open("rb") as target_file:
            data = tomllib.load(target_file)
    except FileNotFoundError as error:
        raise ConfigurationError("Development database target configuration is missing.") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigurationError("Development database target configuration is not valid TOML.") from error
    fields = {key: data.get(key) for key in ("target_id", "host", "database_name")}
    if not all(isinstance(value, str) for value in fields.values()):
        raise ConfigurationError("Development database target requires string target_id, host, and database_name fields.")
    return DevelopmentDatabaseTarget(**fields)


def load_ruleset(path: Path) -> RuleSet:
    """Load the tracked ruleset and validate the metadata required by the schema."""
    try:
        with path.open("rb") as ruleset_file:
            data = tomllib.load(ruleset_file)
    except FileNotFoundError as error:
        raise ConfigurationError(f"Ruleset file does not exist: {path}") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigurationError(f"Ruleset file is not valid TOML: {path}") from error

    outcomes = data.get("outcomes", {})
    safeguards = data.get("safeguards", {})
    version = data.get("version")
    brand = data.get("brand")
    country = data.get("country")
    classifications = tuple(outcomes.get("classifications", ()))
    review_outcome = outcomes.get("review_outcome")
    confidence_bands = tuple(outcomes.get("confidence_bands", ()))
    tags = tuple(outcomes.get("tags", ()))
    if not isinstance(version, str) or not version.strip():
        raise ConfigurationError("Ruleset requires a non-empty version.")
    if brand != "Royal Glass":
        raise ConfigurationError("Ruleset brand must be Royal Glass.")
    if country != "NZ":
        raise ConfigurationError("Ruleset country must be NZ.")
    if not classifications or not confidence_bands or not tags:
        raise ConfigurationError("Ruleset requires classifications, confidence bands, and tags.")
    if set(classifications) != {"direct", "adjacent", "supplier_ecosystem", "irrelevant"}:
        raise ConfigurationError("Ruleset classifications must exclude the review_required outcome.")
    if review_outcome != "review_required":
        raise ConfigurationError("Ruleset review outcome must be review_required.")
    if safeguards.get("fetch_failure_outcome") != "review_required":
        raise ConfigurationError("Fetch failures must remain review_required.")
    if safeguards.get("irrelevant_requires_human_review") is not True:
        raise ConfigurationError("Irrelevant outcomes must require human review.")
    if safeguards.get("protected_override_is_authoritative") is not True:
        raise ConfigurationError("Protected human overrides must remain authoritative.")
    return RuleSet(
        version=version,
        brand=brand,
        country=country,
        classifications=classifications,
        review_outcome=review_outcome,
        confidence_bands=confidence_bands,
        tags=tags,
        fetch_failure_outcome="review_required",
        irrelevant_requires_human_review=True,
        protected_override_is_authoritative=True,
    )


def _read_dotenv(path: Path) -> dict[str, str]:
    """Read plain KEY=VALUE local settings; comments and blank lines are ignored."""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line_number, source_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = source_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigurationError(f"Invalid .env line {line_number}; expected KEY=VALUE.")
        key, value = line.split("=", maxsplit=1)
        key = key.strip()
        if not key:
            raise ConfigurationError(f"Invalid .env line {line_number}; key is empty.")
        values[key] = value.strip().strip("\"'")
    return values


def validate_development_database_target(
    settings: ValidatorSettings,
    target: DevelopmentDatabaseTarget,
    *,
    confirmed: bool,
) -> None:
    """Fail closed unless an operator explicitly confirms the approved development target."""
    if not confirmed:
        raise ConfigurationError("Pass --confirm-development-neon before applying migrations.")
    if settings.database_environment != "development":
        raise ConfigurationError("VALIDATOR_DATABASE_ENVIRONMENT must be development.")
    if not settings.database_url:
        raise ConfigurationError("DATABASE_URL_DEV is required to apply development migrations.")
    if target.target_id == "UNCONFIGURED" or not target.host or not target.database_name:
        raise ConfigurationError("A code-reviewed development target must be configured before applying migrations.")
    parsed = urlsplit(settings.database_url)
    database_name = unquote(parsed.path).lstrip("/")
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname:
        raise ConfigurationError("DATABASE_URL must be a PostgreSQL URL.")
    if parsed.hostname.casefold() != target.host.casefold():
        raise ConfigurationError("DATABASE_URL host does not match the approved development target.")
    if database_name != target.database_name:
        raise ConfigurationError("DATABASE_URL database does not match the approved development target.")
