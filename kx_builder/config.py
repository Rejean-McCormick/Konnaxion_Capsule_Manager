"""Configuration for Konnaxion Capsule Builder.

The Builder creates signed, verifiable ``.kxcap`` artifacts from a source tree.
This module centralizes Builder-side configuration while importing canonical
product names, versions, extension rules, network profiles, paths, and service
names from ``kx_shared.konnaxion_constants``.

The Builder must never package real production secrets into a capsule. It may
package templates, non-secret defaults, manifests, OCI image archives,
healthchecks, metadata, policies, checksums, and signatures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
import os
from typing import Mapping, Sequence

from kx_shared.konnaxion_constants import (
    APP_VERSION,
    CAPSULE_EXTENSION,
    CAPSULE_FILENAME_PATTERN,
    DEFAULT_CHANNEL,
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_VERSION,
    KX_CAPSULES_DIR,
    PARAM_VERSION,
    PRODUCT_NAME,
    BUILDER_NAME,
    NetworkProfile,
)


DEFAULT_SCHEMA_VERSION = "kxcap/v1"
DEFAULT_BUILDER_VERSION = "kx-builder-0.1.0"

DEFAULT_OUTPUT_DIR = Path("dist")
DEFAULT_SOURCE_ROOT = Path(".")
DEFAULT_WORK_DIR = Path(".kxbuild")

DEFAULT_COMPOSE_TEMPLATE = Path("templates/docker-compose.capsule.yml")
DEFAULT_ENV_TEMPLATE_DIR = Path("templates/env")
DEFAULT_PROFILE_DIR = Path("profiles")
DEFAULT_POLICY_DIR = Path("policies")
DEFAULT_HEALTHCHECK_DIR = Path("healthchecks")
DEFAULT_METADATA_DIR = Path("metadata")
DEFAULT_IMAGE_DIR = Path("images")

DEFAULT_SIGNING_KEY_ENV = "KX_BUILDER_SIGNING_KEY"
DEFAULT_SIGNING_KEY_FILE_ENV = "KX_BUILDER_SIGNING_KEY_FILE"

FORBIDDEN_SECRET_ENV_NAMES = frozenset(
    {
        "DJANGO_SECRET_KEY",
        "POSTGRES_PASSWORD",
        "DATABASE_URL",
        "SSH_PRIVATE_KEY",
        "GIT_TOKEN",
        "API_TOKEN",
        "PROVIDER_TOKEN",
        "PRIVATE_CERTIFICATE_KEY",
    }
)

FORBIDDEN_SECRET_NAME_MARKERS = frozenset(
    {
        "SECRET",
        "PASSWORD",
        "PRIVATE_KEY",
        "TOKEN",
        "DATABASE_URL",
        "API_KEY",
        "CERT_KEY",
    }
)

REQUIRED_ENV_TEMPLATES = frozenset(
    {
        "django.env.template",
        "postgres.env.template",
        "redis.env.template",
        "frontend.env.template",
    }
)

REQUIRED_PROFILE_FILES = frozenset(f"{profile.value}.yaml" for profile in NetworkProfile)

REQUIRED_CAPSULE_ROOT_FILES = frozenset(
    {
        "manifest.yaml",
        "docker-compose.capsule.yml",
        "checksums.txt",
        "signature.sig",
    }
)

REQUIRED_CAPSULE_ROOT_DIRS = frozenset(
    {
        "images",
        "profiles",
        "env-templates",
        "migrations",
        "healthchecks",
        "policies",
        "metadata",
    }
)


class BuilderConfigError(ValueError):
    """Raised when Builder configuration is invalid or unsafe."""


@dataclass(frozen=True)
class BuilderConfig:
    """Builder configuration used by package, manifest, checksum, and signing code."""

    source_root: Path = DEFAULT_SOURCE_ROOT
    output_dir: Path = DEFAULT_OUTPUT_DIR
    work_dir: Path = DEFAULT_WORK_DIR

    channel: str = DEFAULT_CHANNEL
    capsule_id: str = DEFAULT_CAPSULE_ID
    capsule_version: str = DEFAULT_CAPSULE_VERSION
    app_name: str = PRODUCT_NAME
    app_version: str = APP_VERSION
    param_version: str = PARAM_VERSION
    schema_version: str = DEFAULT_SCHEMA_VERSION
    builder_name: str = BUILDER_NAME
    builder_version: str = DEFAULT_BUILDER_VERSION
    created_at: str = field(default_factory=_utc_timestamp)

    compose_template: Path = DEFAULT_COMPOSE_TEMPLATE
    env_template_dir: Path = DEFAULT_ENV_TEMPLATE_DIR
    profile_dir: Path = DEFAULT_PROFILE_DIR
    policy_dir: Path = DEFAULT_POLICY_DIR
    healthcheck_dir: Path = DEFAULT_HEALTHCHECK_DIR
    metadata_dir: Path = DEFAULT_METADATA_DIR
    image_dir: Path = DEFAULT_IMAGE_DIR

    include_seed_data: bool = True
    include_metadata: bool = True
    require_signature: bool = True
    require_checksums: bool = True
    require_all_profiles: bool = True
    require_all_env_templates: bool = True
    fail_on_secret_like_values: bool = True

    signing_key: str | None = None
    signing_key_file: Path | None = None

    extra_manifest_fields: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def from_env(
        cls,
        *,
        source_root: str | Path | None = None,
        output_dir: str | Path | None = None,
        work_dir: str | Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> "BuilderConfig":
        """Load Builder configuration from environment variables.

        Supported environment variables:

        - ``KX_BUILDER_SOURCE_ROOT``
        - ``KX_BUILDER_OUTPUT_DIR``
        - ``KX_BUILDER_WORK_DIR``
        - ``KX_BUILDER_CHANNEL``
        - ``KX_BUILDER_CAPSULE_ID``
        - ``KX_BUILDER_CAPSULE_VERSION``
        - ``KX_BUILDER_VERSION``
        - ``KX_BUILDER_REQUIRE_SIGNATURE``
        - ``KX_BUILDER_REQUIRE_CHECKSUMS``
        - ``KX_BUILDER_FAIL_ON_SECRET_LIKE_VALUES``
        - ``KX_BUILDER_SIGNING_KEY``
        - ``KX_BUILDER_SIGNING_KEY_FILE``
        """

        values = dict(os.environ if env is None else env)

        resolved_channel = values.get("KX_BUILDER_CHANNEL", DEFAULT_CHANNEL)
        resolved_capsule_id = values.get(
            "KX_BUILDER_CAPSULE_ID",
            capsule_id_for(channel=resolved_channel),
        )

        return cls(
            source_root=Path(
                source_root
                or values.get("KX_BUILDER_SOURCE_ROOT")
                or DEFAULT_SOURCE_ROOT
            ),
            output_dir=Path(
                output_dir
                or values.get("KX_BUILDER_OUTPUT_DIR")
                or DEFAULT_OUTPUT_DIR
            ),
            work_dir=Path(
                work_dir
                or values.get("KX_BUILDER_WORK_DIR")
                or DEFAULT_WORK_DIR
            ),
            channel=resolved_channel,
            capsule_id=resolved_capsule_id,
            capsule_version=values.get(
                "KX_BUILDER_CAPSULE_VERSION",
                DEFAULT_CAPSULE_VERSION,
            ),
            builder_version=values.get("KX_BUILDER_VERSION", DEFAULT_BUILDER_VERSION),
            require_signature=_parse_bool(
                values.get("KX_BUILDER_REQUIRE_SIGNATURE"),
                default=True,
            ),
            require_checksums=_parse_bool(
                values.get("KX_BUILDER_REQUIRE_CHECKSUMS"),
                default=True,
            ),
            fail_on_secret_like_values=_parse_bool(
                values.get("KX_BUILDER_FAIL_ON_SECRET_LIKE_VALUES"),
                default=True,
            ),
            signing_key=values.get(DEFAULT_SIGNING_KEY_ENV),
            signing_key_file=(
                Path(values[DEFAULT_SIGNING_KEY_FILE_ENV])
                if values.get(DEFAULT_SIGNING_KEY_FILE_ENV)
                else None
            ),
        )

    @property
    def capsule_filename(self) -> str:
        """Return canonical capsule filename."""

        return f"{self.capsule_id}{CAPSULE_EXTENSION}"

    @property
    def capsule_output_path(self) -> Path:
        """Return the final capsule output path."""

        return self.output_dir / self.capsule_filename

    @property
    def absolute_source_root(self) -> Path:
        return self.source_root.expanduser().resolve()

    @property
    def absolute_output_dir(self) -> Path:
        return self.output_dir.expanduser().resolve()

    @property
    def absolute_work_dir(self) -> Path:
        return self.work_dir.expanduser().resolve()

    def resolve(self, path: str | Path) -> Path:
        """Resolve a path relative to ``source_root``."""

        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.absolute_source_root / candidate

    def validate(self, *, require_existing_source: bool = True) -> "BuilderConfig":
        """Validate Builder configuration and return ``self``."""

        if self.app_name != PRODUCT_NAME:
            raise BuilderConfigError(f"app_name must be {PRODUCT_NAME!r}")

        if self.app_version != APP_VERSION:
            raise BuilderConfigError(f"app_version must be {APP_VERSION!r}")

        if self.param_version != PARAM_VERSION:
            raise BuilderConfigError(f"param_version must be {PARAM_VERSION!r}")

        if self.schema_version != DEFAULT_SCHEMA_VERSION:
            raise BuilderConfigError(
                f"schema_version must be {DEFAULT_SCHEMA_VERSION!r}"
            )

        if not self.channel:
            raise BuilderConfigError("channel is required")

        if not self.capsule_id:
            raise BuilderConfigError("capsule_id is required")

        if not self.capsule_id.startswith("konnaxion-v14-"):
            raise BuilderConfigError("capsule_id must start with 'konnaxion-v14-'")

        if not self.capsule_filename.endswith(CAPSULE_EXTENSION):
            raise BuilderConfigError(
                f"capsule filename must end with {CAPSULE_EXTENSION!r}"
            )

        if not self.capsule_version:
            raise BuilderConfigError("capsule_version is required")

        if require_existing_source and not self.absolute_source_root.exists():
            raise BuilderConfigError(
                f"source_root does not exist: {self.absolute_source_root}"
            )

        if self.require_signature and not (self.signing_key or self.signing_key_file):
            raise BuilderConfigError(
                "signature is required, but no signing key was provided; set "
                f"{DEFAULT_SIGNING_KEY_ENV} or {DEFAULT_SIGNING_KEY_FILE_ENV}"
            )

        if self.signing_key and self.signing_key_file:
            raise BuilderConfigError(
                "provide either signing_key or signing_key_file, not both"
            )

        return self

    def required_source_paths(self) -> tuple[Path, ...]:
        """Return source paths expected by the Builder."""

        paths = [
            self.compose_template,
            self.env_template_dir,
            self.profile_dir,
            self.policy_dir,
            self.healthcheck_dir,
        ]

        if self.include_metadata:
            paths.append(self.metadata_dir)

        return tuple(paths)

    def missing_source_paths(self) -> tuple[Path, ...]:
        """Return required source paths that do not exist."""

        missing: list[Path] = []
        for path in self.required_source_paths():
            resolved = self.resolve(path)
            if not resolved.exists():
                missing.append(resolved)
        return tuple(missing)

    def validate_required_files(self) -> None:
        """Validate required profile and env template files."""

        missing_paths = list(self.missing_source_paths())

        if self.require_all_env_templates:
            env_dir = self.resolve(self.env_template_dir)
            existing = {path.name for path in env_dir.iterdir()} if env_dir.exists() else set()
            for template in sorted(REQUIRED_ENV_TEMPLATES - existing):
                missing_paths.append(env_dir / template)

        if self.require_all_profiles:
            profile_dir = self.resolve(self.profile_dir)
            existing = {path.name for path in profile_dir.iterdir()} if profile_dir.exists() else set()
            for profile in sorted(REQUIRED_PROFILE_FILES - existing):
                missing_paths.append(profile_dir / profile)

        if missing_paths:
            rendered = ", ".join(str(path) for path in missing_paths)
            raise BuilderConfigError(f"missing required Builder source paths: {rendered}")

    def to_manifest_base(self) -> dict[str, object]:
        """Return manifest base fields generated from this config."""

        base: dict[str, object] = {
            "schema_version": self.schema_version,
            "capsule_id": self.capsule_id,
            "capsule_version": self.capsule_version,
            "app_name": self.app_name,
            "app_version": self.app_version,
            "channel": self.channel,
            "created_at": self.created_at,
            "builder_version": self.builder_version,
            "param_version": self.param_version,
        }
        base.update(dict(self.extra_manifest_fields))
        return base


def default_config() -> BuilderConfig:
    """Return a default Builder configuration without environment lookup."""

    return BuilderConfig()


def load_config_from_env() -> BuilderConfig:
    """Return validated Builder configuration from environment variables."""

    return BuilderConfig.from_env().validate(require_existing_source=False)


def capsule_id_for(*, channel: str = DEFAULT_CHANNEL, today: date | None = None) -> str:
    """Return a canonical capsule id for a channel and date."""

    build_date = today or date.today()
    date_part = build_date.strftime("%Y.%m.%d")
    return f"konnaxion-v14-{channel}-{date_part}"


def capsule_filename_for(*, channel: str = DEFAULT_CHANNEL, today: date | None = None) -> str:
    """Return a canonical capsule filename for a channel and date."""

    return f"{capsule_id_for(channel=channel, today=today)}{CAPSULE_EXTENSION}"


def render_capsule_filename_pattern(*, channel: str, today: date | None = None) -> str:
    """Render the canonical filename pattern with a concrete channel/date."""

    build_date = today or date.today()
    return CAPSULE_FILENAME_PATTERN.format(
        channel=channel,
        date=build_date.strftime("%Y.%m.%d"),
    )


def validate_no_secret_like_env(env: Mapping[str, str]) -> None:
    """Reject real secret-like environment variables before packaging.

    Capsules may contain templates and placeholders. They must not include real
    production secrets. This helper is intentionally conservative.
    """

    offenders: list[str] = []

    for name, value in env.items():
        upper_name = str(name).upper()
        string_value = str(value)

        if upper_name in FORBIDDEN_SECRET_ENV_NAMES and _looks_like_real_secret(string_value):
            offenders.append(name)
            continue

        if any(marker in upper_name for marker in FORBIDDEN_SECRET_NAME_MARKERS):
            if _looks_like_real_secret(string_value):
                offenders.append(name)

    if offenders:
        raise BuilderConfigError(
            "refusing to package secret-like environment values: "
            + ", ".join(sorted(offenders))
        )


def validate_capsule_output_path(path: str | Path) -> Path:
    """Validate and normalize a capsule output path."""

    output_path = Path(path)

    if output_path.suffix != CAPSULE_EXTENSION:
        raise BuilderConfigError(
            f"capsule output path must end with {CAPSULE_EXTENSION!r}: {output_path}"
        )

    return output_path


def ensure_build_directories(config: BuilderConfig) -> None:
    """Create output and work directories for a build."""

    config.absolute_output_dir.mkdir(parents=True, exist_ok=True)
    config.absolute_work_dir.mkdir(parents=True, exist_ok=True)


def appliance_capsule_store() -> Path:
    """Return canonical appliance capsule storage path."""

    return KX_CAPSULES_DIR


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False

    raise BuilderConfigError(f"invalid boolean value: {value!r}")


def _looks_like_real_secret(value: str) -> bool:
    stripped = value.strip()

    if not stripped:
        return False

    placeholder_values = {
        "<GENERATED_ON_INSTALL>",
        "<GENERATED>",
        "<PLACEHOLDER>",
        "<SECRET>",
        "<POSTGRES_PASSWORD>",
        "<PUBLIC_OR_PRIVATE_HOST>",
        "changeme",
        "change-me",
        "example",
        "dummy",
    }

    if stripped in placeholder_values:
        return False

    if stripped.startswith("<") and stripped.endswith(">"):
        return False

    return len(stripped) >= 12


__all__ = [
    "BuilderConfig",
    "BuilderConfigError",
    "DEFAULT_BUILDER_VERSION",
    "DEFAULT_SCHEMA_VERSION",
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_SOURCE_ROOT",
    "DEFAULT_WORK_DIR",
    "FORBIDDEN_SECRET_ENV_NAMES",
    "FORBIDDEN_SECRET_NAME_MARKERS",
    "REQUIRED_CAPSULE_ROOT_DIRS",
    "REQUIRED_CAPSULE_ROOT_FILES",
    "REQUIRED_ENV_TEMPLATES",
    "REQUIRED_PROFILE_FILES",
    "appliance_capsule_store",
    "capsule_filename_for",
    "capsule_id_for",
    "default_config",
    "ensure_build_directories",
    "load_config_from_env",
    "render_capsule_filename_pattern",
    "validate_capsule_output_path",
    "validate_no_secret_like_env",
]
