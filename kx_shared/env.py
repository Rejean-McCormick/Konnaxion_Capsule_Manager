"""
Environment helpers for Konnaxion Capsule Manager.

This module centralizes parsing, rendering, validation, and file I/O for
Konnaxion environment files. Canonical values must come from
``kx_shared.konnaxion_constants``; this module should not invent product
names, paths, profiles, ports, service names, or lifecycle states.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import os
import re
import shlex
from typing import Any

from kx_shared.konnaxion_constants import (
    DATABASE_ENV_DEFAULTS,
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_VERSION,
    DEFAULT_EXPOSURE_MODE,
    DEFAULT_INSTANCE_ID,
    DEFAULT_NETWORK_PROFILE,
    DJANGO_ENV_DEFAULTS,
    DockerService,
    FRONTEND_ENV_DEFAULTS,
    KX_BACKUPS_ROOT,
    KX_ENV_DEFAULTS,
    NetworkProfile,
    REDIS_ENV_DEFAULTS,
    instance_backup_root,
    instance_compose_file,
)

EnvMap = dict[str, str]

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_FALSE_VALUES = {"0", "false", "no", "n", "off", ""}

_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

_SECRET_KEYS = frozenset(
    {
        "DJANGO_SECRET_KEY",
        "POSTGRES_PASSWORD",
        "DATABASE_URL",
        "SECRET_KEY",
        "API_TOKEN",
        "GIT_TOKEN",
        "PROVIDER_TOKEN",
        "SSH_PRIVATE_KEY",
        "PRIVATE_KEY",
        "CERT_PRIVATE_KEY",
    }
)

_ALLOWED_KX_KEYS = frozenset(KX_ENV_DEFAULTS.keys()) | {
    "KX_PUBLIC_MODE_DURATION_HOURS",
    "KX_COMPOSE_FILE",
    "KX_BACKUP_DIR",
}


class EnvError(ValueError):
    """Raised when an environment value or file is invalid."""


@dataclass(frozen=True)
class EnvValidationResult:
    """Result returned by ``validate_kx_env``."""

    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def _stringify(value: Any) -> str:
    """Convert a supported value to a stable env-file string."""

    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _enum_value(value: Any) -> str:
    """Return enum .value when available, otherwise a string."""

    return str(getattr(value, "value", value))


def parse_bool(value: str | bool | int | None) -> bool:
    """Parse common env boolean values.

    Accepted true values: ``1``, ``true``, ``yes``, ``y``, ``on``.
    Accepted false values: ``0``, ``false``, ``no``, ``n``, ``off``, empty.
    """

    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)

    normalized = "" if value is None else str(value).strip().lower()

    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False

    raise EnvError(f"Invalid boolean value: {value!r}")


def normalize_network_profile(value: str | NetworkProfile | None) -> str:
    """Normalize and validate a canonical Konnaxion network profile."""

    if value is None:
        return _enum_value(DEFAULT_NETWORK_PROFILE)

    normalized = _enum_value(value).strip()
    allowed = {profile.value for profile in NetworkProfile}

    if normalized not in allowed:
        raise EnvError(
            f"Invalid KX_NETWORK_PROFILE={normalized!r}; "
            f"expected one of: {', '.join(sorted(allowed))}"
        )

    return normalized


def normalize_exposure_mode(value: str | Any | None) -> str:
    """Normalize and validate a canonical Konnaxion exposure mode."""

    if value is None:
        return _enum_value(DEFAULT_EXPOSURE_MODE)

    normalized = _enum_value(value).strip()

    # DEFAULT_EXPOSURE_MODE normally belongs to ExposureMode. Importing the
    # enum name directly is intentionally avoided here so older constants files
    # can still be used during early scaffolding.
    allowed = {
        "private",
        "lan",
        "vpn",
        "temporary_tunnel",
        "public",
    }

    if normalized not in allowed:
        raise EnvError(
            f"Invalid KX_EXPOSURE_MODE={normalized!r}; "
            f"expected one of: {', '.join(sorted(allowed))}"
        )

    return normalized


def merge_env(
    defaults: Mapping[str, Any],
    overrides: Mapping[str, Any] | None = None,
) -> EnvMap:
    """Merge defaults and overrides into a string-only env mapping."""

    result: EnvMap = {str(key): _stringify(value) for key, value in defaults.items()}

    for key, value in (overrides or {}).items():
        result[str(key)] = _stringify(value)

    return result


def default_kx_env(
    *,
    instance_id: str = DEFAULT_INSTANCE_ID,
    capsule_id: str = DEFAULT_CAPSULE_ID,
    capsule_version: str = DEFAULT_CAPSULE_VERSION,
    network_profile: str | NetworkProfile | None = None,
    exposure_mode: str | Any | None = None,
    host: str = "",
    public_mode_enabled: bool | str = False,
    public_mode_expires_at: str = "",
    backup_class: str = "manual",
    backup_id: str = "",
    overrides: Mapping[str, Any] | None = None,
) -> EnvMap:
    """Return canonical KX_* env values for an instance.

    Runtime-specific paths are generated from canonical path helpers.
    """

    env = merge_env(KX_ENV_DEFAULTS)

    env.update(
        {
            "KX_INSTANCE_ID": instance_id,
            "KX_CAPSULE_ID": capsule_id,
            "KX_CAPSULE_VERSION": capsule_version,
            "KX_NETWORK_PROFILE": normalize_network_profile(network_profile),
            "KX_EXPOSURE_MODE": normalize_exposure_mode(exposure_mode),
            "KX_PUBLIC_MODE_ENABLED": "true"
            if parse_bool(public_mode_enabled)
            else "false",
            "KX_PUBLIC_MODE_EXPIRES_AT": public_mode_expires_at,
            "KX_BACKUP_ROOT": str(KX_BACKUPS_ROOT),
            "KX_COMPOSE_FILE": str(instance_compose_file(instance_id)),
            "KX_BACKUP_DIR": str(
                instance_backup_root(instance_id) / backup_class / backup_id
            ).rstrip("/"),
            "KX_HOST": host,
        }
    )

    if overrides:
        env = merge_env(env, overrides)

    validation = validate_kx_env(env)
    if not validation.ok:
        raise EnvError("; ".join(validation.errors))

    return env


def default_django_env(
    *,
    host: str,
    django_secret_key: str = "<GENERATED_ON_INSTALL>",
    postgres_password: str = "<GENERATED_ON_INSTALL>",
    overrides: Mapping[str, Any] | None = None,
) -> EnvMap:
    """Return canonical Django env values."""

    env = merge_env(DJANGO_ENV_DEFAULTS)
    env.update(
        {
            "DJANGO_SECRET_KEY": django_secret_key,
            "DJANGO_ALLOWED_HOSTS": host,
            "DATABASE_URL": render_database_url(postgres_password),
        }
    )
    return merge_env(env, overrides)


def default_postgres_env(
    *,
    postgres_password: str = "<GENERATED_ON_INSTALL>",
    overrides: Mapping[str, Any] | None = None,
) -> EnvMap:
    """Return canonical PostgreSQL env values."""

    env = merge_env(DATABASE_ENV_DEFAULTS)
    env["POSTGRES_PASSWORD"] = postgres_password
    return merge_env(env, overrides)


def default_redis_env(overrides: Mapping[str, Any] | None = None) -> EnvMap:
    """Return canonical Redis/Celery env values."""

    return merge_env(REDIS_ENV_DEFAULTS, overrides)


def default_frontend_env(
    *,
    host: str,
    scheme: str = "https",
    overrides: Mapping[str, Any] | None = None,
) -> EnvMap:
    """Return canonical frontend env values."""

    frontend_urls = render_frontend_urls(host=host, scheme=scheme)
    env = merge_env(FRONTEND_ENV_DEFAULTS)
    env.update(frontend_urls)
    return merge_env(env, overrides)


def default_service_envs(
    *,
    host: str,
    django_secret_key: str = "<GENERATED_ON_INSTALL>",
    postgres_password: str = "<GENERATED_ON_INSTALL>",
    scheme: str = "https",
) -> dict[str, EnvMap]:
    """Return env maps keyed by canonical Docker service name."""

    return {
        DockerService.DJANGO_API.value: default_django_env(
            host=host,
            django_secret_key=django_secret_key,
            postgres_password=postgres_password,
        ),
        DockerService.POSTGRES.value: default_postgres_env(
            postgres_password=postgres_password,
        ),
        DockerService.REDIS.value: default_redis_env(),
        DockerService.CELERYWORKER.value: default_redis_env(),
        DockerService.CELERYBEAT.value: default_redis_env(),
        DockerService.FRONTEND_NEXT.value: default_frontend_env(
            host=host,
            scheme=scheme,
        ),
    }


def render_database_url(
    postgres_password: str,
    *,
    user: str | None = None,
    host: str | None = None,
    port: str | int | None = None,
    database: str | None = None,
) -> str:
    """Render the canonical internal PostgreSQL DATABASE_URL."""

    user = user or DATABASE_ENV_DEFAULTS["POSTGRES_USER"]
    host = host or DATABASE_ENV_DEFAULTS["POSTGRES_HOST"]
    port = port or DATABASE_ENV_DEFAULTS["POSTGRES_PORT"]
    database = database or DATABASE_ENV_DEFAULTS["POSTGRES_DB"]

    return f"postgres://{user}:{postgres_password}@{host}:{port}/{database}"


def render_frontend_urls(*, host: str, scheme: str = "https") -> EnvMap:
    """Render canonical frontend public URL variables."""

    clean_host = host.strip().rstrip("/")
    if not clean_host:
        raise EnvError("host is required to render frontend URLs")

    base = f"{scheme}://{clean_host}"

    return {
        "NEXT_PUBLIC_API_BASE": f"{base}/api",
        "NEXT_PUBLIC_BACKEND_BASE": base,
    }


def parse_env_text(text: str) -> EnvMap:
    """Parse simple KEY=VALUE env text.

    Supports blank lines, comments, optional ``export KEY=VALUE`` syntax, and
    shell-like quoting through ``shlex``.
    """

    env: EnvMap = {}

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            raise EnvError(f"Invalid env line {line_number}: missing '='")

        key, raw_value = line.split("=", 1)
        key = key.strip()

        if not _ENV_KEY_RE.match(key):
            raise EnvError(f"Invalid env key on line {line_number}: {key!r}")

        try:
            parsed = shlex.split(raw_value, comments=False, posix=True)
        except ValueError as exc:
            raise EnvError(f"Invalid quoting on line {line_number}: {exc}") from exc

        if len(parsed) > 1:
            value = " ".join(parsed)
        elif len(parsed) == 1:
            value = parsed[0]
        else:
            value = ""

        env[key] = value

    return env


def read_env_file(path: str | Path) -> EnvMap:
    """Read and parse a dotenv-style file."""

    return parse_env_text(Path(path).read_text(encoding="utf-8"))


def _quote_env_value(value: str) -> str:
    """Quote env values only when required."""

    if value == "":
        return ""

    if re.match(r"^[A-Za-z0-9_./:@%+=,~\-]+$", value):
        return value

    return shlex.quote(value)


def serialize_env(
    env: Mapping[str, Any],
    *,
    sort_keys: bool = True,
    trailing_newline: bool = True,
) -> str:
    """Serialize a mapping to stable dotenv text."""

    items = env.items()
    if sort_keys:
        items = sorted(items)

    lines: list[str] = []
    for key, value in items:
        key = str(key)
        if not _ENV_KEY_RE.match(key):
            raise EnvError(f"Invalid env key: {key!r}")

        lines.append(f"{key}={_quote_env_value(_stringify(value))}")

    text = "\n".join(lines)
    return f"{text}\n" if trailing_newline else text


def write_env_file(
    path: str | Path,
    env: Mapping[str, Any],
    *,
    mode: int = 0o600,
    sort_keys: bool = True,
) -> Path:
    """Write a dotenv-style file with restrictive permissions."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(serialize_env(env, sort_keys=sort_keys), encoding="utf-8")
    os.chmod(target, mode)
    return target


def validate_kx_env(env: Mapping[str, Any]) -> EnvValidationResult:
    """Validate canonical KX_* environment values."""

    errors: list[str] = []
    warnings: list[str] = []

    for key in env:
        if key.startswith("KX_") and key not in _ALLOWED_KX_KEYS:
            warnings.append(f"Unknown KX_* key: {key}")

    required = {
        "KX_INSTANCE_ID",
        "KX_CAPSULE_ID",
        "KX_CAPSULE_VERSION",
        "KX_NETWORK_PROFILE",
        "KX_EXPOSURE_MODE",
        "KX_PUBLIC_MODE_ENABLED",
        "KX_REQUIRE_SIGNED_CAPSULE",
        "KX_GENERATE_SECRETS_ON_INSTALL",
        "KX_BACKUP_ENABLED",
        "KX_BACKUP_ROOT",
    }

    missing = sorted(key for key in required if not _stringify(env.get(key)))
    if missing:
        errors.append(f"Missing required KX env keys: {', '.join(missing)}")

    try:
        normalize_network_profile(_stringify(env.get("KX_NETWORK_PROFILE")))
    except EnvError as exc:
        errors.append(str(exc))

    try:
        normalize_exposure_mode(_stringify(env.get("KX_EXPOSURE_MODE")))
    except EnvError as exc:
        errors.append(str(exc))

    try:
        public_enabled = parse_bool(env.get("KX_PUBLIC_MODE_ENABLED"))
    except EnvError as exc:
        public_enabled = False
        errors.append(str(exc))

    public_expires_at = _stringify(env.get("KX_PUBLIC_MODE_EXPIRES_AT"))
    if public_enabled and not public_expires_at:
        errors.append(
            "KX_PUBLIC_MODE_EXPIRES_AT is mandatory when "
            "KX_PUBLIC_MODE_ENABLED=true"
        )

    if _stringify(env.get("KX_REQUIRE_SIGNED_CAPSULE")).lower() not in _TRUE_VALUES:
        errors.append("KX_REQUIRE_SIGNED_CAPSULE must be true")

    dangerous_flags = {
        "KX_ALLOW_UNKNOWN_IMAGES",
        "KX_ALLOW_PRIVILEGED_CONTAINERS",
        "KX_ALLOW_DOCKER_SOCKET_MOUNT",
        "KX_ALLOW_HOST_NETWORK",
    }

    for key in sorted(dangerous_flags):
        try:
            if parse_bool(env.get(key)):
                errors.append(f"{key} must be false")
        except EnvError as exc:
            errors.append(str(exc))

    return EnvValidationResult(
        ok=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def assert_no_real_secrets(env: Mapping[str, Any]) -> None:
    """Reject obvious real secrets in capsule templates.

    Templates may contain placeholders like ``<GENERATED_ON_INSTALL>``. This
    function blocks likely real secrets from being packaged into capsules.
    """

    for key, value in env.items():
        if key not in _SECRET_KEYS:
            continue

        text = _stringify(value).strip()
        if not text:
            continue

        is_placeholder = text.startswith("<") and text.endswith(">")
        if is_placeholder:
            continue

        raise EnvError(
            f"{key} appears to contain a real secret; capsules may only "
            "contain templates/placeholders"
        )


def env_from_os(prefix: str = "KX_") -> EnvMap:
    """Return current process env values matching a prefix."""

    return {key: value for key, value in os.environ.items() if key.startswith(prefix)}


def overlay_os_env(base: Mapping[str, Any], prefix: str = "KX_") -> EnvMap:
    """Overlay process env values onto a base env mapping."""

    return merge_env(base, env_from_os(prefix=prefix))


__all__ = [
    "EnvError",
    "EnvMap",
    "EnvValidationResult",
    "assert_no_real_secrets",
    "default_django_env",
    "default_frontend_env",
    "default_kx_env",
    "default_postgres_env",
    "default_redis_env",
    "default_service_envs",
    "env_from_os",
    "merge_env",
    "normalize_exposure_mode",
    "normalize_network_profile",
    "overlay_os_env",
    "parse_bool",
    "parse_env_text",
    "read_env_file",
    "render_database_url",
    "render_frontend_urls",
    "serialize_env",
    "validate_kx_env",
    "write_env_file",
]
