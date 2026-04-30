"""
Install-time secret generation for Konnaxion Instances.

Capsules must never contain real production secrets. The Konnaxion Agent
generates instance-local secrets during instance creation/update/restore flows
and writes them into the instance env directory with restrictive permissions.

This module owns:
- secure secret generation
- placeholder/default secret rejection
- DATABASE_URL construction
- atomic secret env-file writes
- redaction helpers for logs/API responses
"""

from __future__ import annotations

import os
import re
import secrets
import string
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from kx_shared.errors import (
    FileAlreadyExistsError,
    FileMissingError,
    InvalidVariableError,
    MissingRequiredVariableError,
    UnsafePathError,
    ValidationError,
)
from kx_shared.konnaxion_constants import (
    DATABASE_ENV_DEFAULTS,
    DJANGO_ENV_DEFAULTS,
    KX_ENV_DEFAULTS,
    REDIS_ENV_DEFAULTS,
    instance_env_dir,
)


# ---------------------------------------------------------------------
# Canonical secret/env keys
# ---------------------------------------------------------------------


DJANGO_SECRET_KEY = "DJANGO_SECRET_KEY"
POSTGRES_PASSWORD = "POSTGRES_PASSWORD"
DATABASE_URL = "DATABASE_URL"
DJANGO_ALLOWED_HOSTS = "DJANGO_ALLOWED_HOSTS"
NEXT_PUBLIC_API_BASE = "NEXT_PUBLIC_API_BASE"
NEXT_PUBLIC_BACKEND_BASE = "NEXT_PUBLIC_BACKEND_BASE"

DJANGO_ENV_FILE = "django.env"
POSTGRES_ENV_FILE = "postgres.env"
REDIS_ENV_FILE = "redis.env"
FRONTEND_ENV_FILE = "frontend.env"
KX_ENV_FILE = "kx.env"

REQUIRED_SECRET_KEYS: frozenset[str] = frozenset(
    {
        DJANGO_SECRET_KEY,
        POSTGRES_PASSWORD,
    }
)

SENSITIVE_KEY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"secret",
        r"password",
        r"token",
        r"private[_-]?key",
        r"api[_-]?key",
        r"credential",
        r"database_url",
        r"dsn",
    )
)

PLACEHOLDER_VALUES: frozenset[str] = frozenset(
    {
        "",
        "change-me",
        "changeme",
        "replace-me",
        "replaceme",
        "generated-on-install",
        "<generated_on_install>",
        "<generated-on-install>",
        "<postgres_password>",
        "<django_secret_key>",
        "password",
        "postgres",
        "konnaxion",
        "secret",
        "default",
        "example",
        "test",
        "admin",
        "none",
        "null",
    }
)

_SAFE_PASSWORD_ALPHABET = string.ascii_letters + string.digits + "-_=+.,:;@#%~"
_DJANGO_SECRET_ALPHABET = string.ascii_letters + string.digits + string.punctuation


# ---------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class SecretGenerationPolicy:
    """Input policy for creating instance-local secrets."""

    instance_id: str
    host: str
    capsule_id: str | None = None
    capsule_version: str | None = None
    network_profile: str | None = None
    exposure_mode: str | None = None
    overwrite_existing: bool = False
    django_secret_length: int = 64
    postgres_password_length: int = 48

    def validate(self) -> None:
        if not self.instance_id or not self.instance_id.strip():
            raise MissingRequiredVariableError(
                "Instance ID is required for secret generation.",
                {"variable": "KX_INSTANCE_ID"},
            )

        if not self.host or not self.host.strip():
            raise MissingRequiredVariableError(
                "Host is required for generated frontend/backend URLs.",
                {"variable": "KX_HOST"},
            )

        if self.django_secret_length < 50:
            raise InvalidVariableError(
                "Django secret length must be at least 50 characters.",
                {"django_secret_length": self.django_secret_length},
            )

        if self.postgres_password_length < 32:
            raise InvalidVariableError(
                "PostgreSQL password length must be at least 32 characters.",
                {"postgres_password_length": self.postgres_password_length},
            )


@dataclass(slots=True, frozen=True)
class GeneratedSecrets:
    """Generated secret bundle for one Konnaxion Instance."""

    instance_id: str
    host: str
    django_secret_key: str
    postgres_password: str
    database_url: str
    django_allowed_hosts: str
    next_public_api_base: str
    next_public_backend_base: str
    extra_env: Mapping[str, str] = field(default_factory=dict)

    def to_env(self) -> dict[str, str]:
        env = {
            DJANGO_SECRET_KEY: self.django_secret_key,
            POSTGRES_PASSWORD: self.postgres_password,
            DATABASE_URL: self.database_url,
            DJANGO_ALLOWED_HOSTS: self.django_allowed_hosts,
            NEXT_PUBLIC_API_BASE: self.next_public_api_base,
            NEXT_PUBLIC_BACKEND_BASE: self.next_public_backend_base,
        }
        env.update({str(key): str(value) for key, value in self.extra_env.items()})
        return env

    def redacted(self) -> dict[str, str]:
        return redact_env(self.to_env())


# ---------------------------------------------------------------------
# Secret generation
# ---------------------------------------------------------------------


def generate_secret_bundle(policy: SecretGenerationPolicy) -> GeneratedSecrets:
    """Generate a complete secret bundle for an instance."""

    policy.validate()

    postgres_host = str(DATABASE_ENV_DEFAULTS.get("POSTGRES_HOST", "postgres"))
    postgres_port = str(DATABASE_ENV_DEFAULTS.get("POSTGRES_PORT", "5432"))
    postgres_db = str(DATABASE_ENV_DEFAULTS.get("POSTGRES_DB", "konnaxion"))
    postgres_user = str(DATABASE_ENV_DEFAULTS.get("POSTGRES_USER", "konnaxion"))

    django_secret_key = generate_django_secret_key(policy.django_secret_length)
    postgres_password = generate_password(policy.postgres_password_length)
    database_url = build_database_url(
        user=postgres_user,
        password=postgres_password,
        host=postgres_host,
        port=postgres_port,
        database=postgres_db,
    )

    host = normalize_host(policy.host)

    bundle = GeneratedSecrets(
        instance_id=policy.instance_id,
        host=host,
        django_secret_key=django_secret_key,
        postgres_password=postgres_password,
        database_url=database_url,
        django_allowed_hosts=build_allowed_hosts(host),
        next_public_api_base=f"https://{host}/api",
        next_public_backend_base=f"https://{host}",
    )

    validate_generated_secrets(bundle)
    return bundle


def generate_django_secret_key(length: int = 64) -> str:
    """Generate a Django-compatible secret key."""

    if length < 50:
        raise InvalidVariableError(
            "Django secret key length must be at least 50 characters.",
            {"length": length},
        )

    return "".join(secrets.choice(_DJANGO_SECRET_ALPHABET) for _ in range(length))


def generate_password(length: int = 48) -> str:
    """Generate a URL-safe service password with enough entropy."""

    if length < 32:
        raise InvalidVariableError(
            "Generated password length must be at least 32 characters.",
            {"length": length},
        )

    return "".join(secrets.choice(_SAFE_PASSWORD_ALPHABET) for _ in range(length))


def build_database_url(
    *,
    user: str,
    password: str,
    host: str,
    port: str | int,
    database: str,
) -> str:
    """Build the internal PostgreSQL DATABASE_URL."""

    for name, value in {
        "user": user,
        "password": password,
        "host": host,
        "port": str(port),
        "database": database,
    }.items():
        if not value:
            raise MissingRequiredVariableError(
                "Cannot build DATABASE_URL with missing value.",
                {"missing": name},
            )

    # Generated passwords intentionally use a restricted alphabet that is safe
    # in this URL form.
    return f"postgres://{user}:{password}@{host}:{port}/{database}"


def normalize_host(host: str) -> str:
    """Normalize a host value for env generation."""

    normalized = host.strip()
    normalized = normalized.removeprefix("https://").removeprefix("http://")
    normalized = normalized.rstrip("/")

    if not normalized:
        raise MissingRequiredVariableError(
            "Host cannot be empty.",
            {"variable": "KX_HOST"},
        )

    if "/" in normalized:
        raise InvalidVariableError(
            "Host must not contain a path.",
            {"host": host},
        )

    return normalized


def build_allowed_hosts(host: str) -> str:
    """Build Django allowed hosts for the selected runtime host."""

    normalized = normalize_host(host)
    hosts = [normalized]

    if normalized not in {"localhost", "127.0.0.1"}:
        hosts.extend(["localhost", "127.0.0.1"])

    return ",".join(dict.fromkeys(hosts))


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------


def validate_generated_secrets(bundle: GeneratedSecrets) -> None:
    env = bundle.to_env()

    for key in REQUIRED_SECRET_KEYS:
        value = env.get(key)
        validate_secret_value(key, value)

    if not env.get(DATABASE_URL):
        raise MissingRequiredVariableError(
            "DATABASE_URL is required.",
            {"variable": DATABASE_URL},
        )

    if bundle.postgres_password not in bundle.database_url:
        raise ValidationError(
            "DATABASE_URL does not contain the generated PostgreSQL password.",
            {"variable": DATABASE_URL},
        )


def validate_secret_value(key: str, value: str | None) -> None:
    if value is None:
        raise MissingRequiredVariableError(
            "Required secret is missing.",
            {"variable": key},
        )

    if is_placeholder_secret(value):
        raise InvalidVariableError(
            "Secret value is empty, default, or placeholder.",
            {"variable": key},
        )

    if len(value) < minimum_secret_length(key):
        raise InvalidVariableError(
            "Secret value is too short.",
            {"variable": key, "minimum_length": minimum_secret_length(key)},
        )


def minimum_secret_length(key: str) -> int:
    normalized = key.upper()
    if normalized == DJANGO_SECRET_KEY:
        return 50
    if normalized == POSTGRES_PASSWORD:
        return 32
    return 16


def is_placeholder_secret(value: str | None) -> bool:
    if value is None:
        return True

    normalized = value.strip().lower()
    normalized = normalized.strip("'"")

    return normalized in PLACEHOLDER_VALUES


def has_sensitive_key(key: str) -> bool:
    return any(pattern.search(key) for pattern in SENSITIVE_KEY_PATTERNS)


# ---------------------------------------------------------------------
# Env-file rendering/writing
# ---------------------------------------------------------------------


def build_env_files(bundle: GeneratedSecrets, policy: SecretGenerationPolicy) -> dict[str, dict[str, str]]:
    """Build canonical env-file contents from generated secrets."""

    kx_env = {
        "KX_INSTANCE_ID": policy.instance_id,
        "KX_CAPSULE_ID": policy.capsule_id or str(KX_ENV_DEFAULTS.get("KX_CAPSULE_ID", "")),
        "KX_CAPSULE_VERSION": policy.capsule_version
        or str(KX_ENV_DEFAULTS.get("KX_CAPSULE_VERSION", "")),
        "KX_NETWORK_PROFILE": policy.network_profile
        or str(KX_ENV_DEFAULTS.get("KX_NETWORK_PROFILE", "")),
        "KX_EXPOSURE_MODE": policy.exposure_mode
        or str(KX_ENV_DEFAULTS.get("KX_EXPOSURE_MODE", "")),
        "KX_HOST": bundle.host,
    }

    django_env = {
        **{str(k): str(v) for k, v in DJANGO_ENV_DEFAULTS.items()},
        DJANGO_SECRET_KEY: bundle.django_secret_key,
        DJANGO_ALLOWED_HOSTS: bundle.django_allowed_hosts,
        DATABASE_URL: bundle.database_url,
    }

    postgres_env = {
        **{str(k): str(v) for k, v in DATABASE_ENV_DEFAULTS.items()},
        POSTGRES_PASSWORD: bundle.postgres_password,
    }

    redis_env = {str(k): str(v) for k, v in REDIS_ENV_DEFAULTS.items()}

    frontend_env = {
        NEXT_PUBLIC_API_BASE: bundle.next_public_api_base,
        NEXT_PUBLIC_BACKEND_BASE: bundle.next_public_backend_base,
        "NEXT_TELEMETRY_DISABLED": "1",
        "NODE_OPTIONS": "--max-old-space-size=4096",
    }

    return {
        KX_ENV_FILE: kx_env,
        DJANGO_ENV_FILE: django_env,
        POSTGRES_ENV_FILE: postgres_env,
        REDIS_ENV_FILE: redis_env,
        FRONTEND_ENV_FILE: frontend_env,
    }


def write_instance_secret_env_files(
    policy: SecretGenerationPolicy,
    *,
    env_dir: Path | None = None,
) -> dict[str, Path]:
    """Generate and write canonical env files for an instance.

    Files are written atomically and chmodded to 0600.
    """

    policy.validate()
    target_dir = env_dir or instance_env_dir(policy.instance_id)
    ensure_safe_env_dir(target_dir, policy.instance_id)

    bundle = generate_secret_bundle(policy)
    env_files = build_env_files(bundle, policy)

    written: dict[str, Path] = {}
    for filename, values in env_files.items():
        target_path = target_dir / filename

        if target_path.exists() and not policy.overwrite_existing:
            raise FileAlreadyExistsError(
                "Refusing to overwrite existing env file.",
                {"path": str(target_path)},
            )

        write_env_file_atomic(target_path, values)
        written[filename] = target_path

    return written


def write_env_file_atomic(path: Path, values: Mapping[str, str]) -> None:
    """Write a .env file atomically with restrictive permissions."""

    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )

    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={quote_env_value(str(value))}\n")

        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        finally:
            raise


def quote_env_value(value: str) -> str:
    """Render a value safely for simple dotenv parsing."""

    if value == "":
        return ""

    if re.fullmatch(r"[A-Za-z0-9_./:@%+=,;#~\-]+", value):
        return value

    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def read_env_file(path: Path) -> dict[str, str]:
    """Read a simple KEY=VALUE env file written by this module."""

    if not path.exists():
        raise FileMissingError(
            "Env file does not exist.",
            {"path": str(path)},
        )

    result: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            raise InvalidVariableError(
                "Invalid env-file line.",
                {"path": str(path), "line_number": line_number},
            )

        key, value = line.split("=", 1)
        result[key.strip()] = unquote_env_value(value.strip())

    return result


def unquote_env_value(value: str) -> str:
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        inner = value[1:-1]
        return inner.replace('\"', '"').replace("\\\\", "\\")
    return value


def ensure_safe_env_dir(path: Path, instance_id: str) -> None:
    """Ensure env files are written under the canonical instance env path."""

    expected = instance_env_dir(instance_id).resolve()
    resolved = path.resolve()

    if resolved != expected:
        raise UnsafePathError(
            "Env directory must be the canonical instance env directory.",
            {"expected": str(expected), "received": str(resolved)},
        )

    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


# ---------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------


def redact_env(values: Mapping[str, Any]) -> dict[str, str]:
    """Redact sensitive env values for logs/API responses."""

    return {
        str(key): redact_value(str(key), value)
        for key, value in values.items()
    }


def redact_value(key: str, value: Any) -> str:
    if has_sensitive_key(key):
        return "<REDACTED>"

    text = "" if value is None else str(value)
    if is_placeholder_secret(text):
        return "<EMPTY_OR_PLACEHOLDER>"

    return text


__all__ = [
    "DATABASE_URL",
    "DJANGO_ALLOWED_HOSTS",
    "DJANGO_ENV_FILE",
    "DJANGO_SECRET_KEY",
    "FRONTEND_ENV_FILE",
    "GeneratedSecrets",
    "KX_ENV_FILE",
    "PLACEHOLDER_VALUES",
    "POSTGRES_ENV_FILE",
    "POSTGRES_PASSWORD",
    "REDIS_ENV_FILE",
    "REQUIRED_SECRET_KEYS",
    "SENSITIVE_KEY_PATTERNS",
    "SecretGenerationPolicy",
    "build_allowed_hosts",
    "build_database_url",
    "build_env_files",
    "generate_django_secret_key",
    "generate_password",
    "generate_secret_bundle",
    "has_sensitive_key",
    "is_placeholder_secret",
    "minimum_secret_length",
    "normalize_host",
    "quote_env_value",
    "read_env_file",
    "redact_env",
    "redact_value",
    "unquote_env_value",
    "validate_generated_secrets",
    "validate_secret_value",
    "write_env_file_atomic",
    "write_instance_secret_env_files",
]
