"""Capsule manifest loading and validation.

This module owns the Agent-side interpretation of ``manifest.yaml`` from a
Konnaxion Capsule. It intentionally imports canonical names, versions, network
profiles, service names, and path rules from ``kx_shared.konnaxion_constants``
instead of redefining them locally.

The validator is strict for fields that affect runtime safety and permissive
for extra metadata so future capsule versions can add non-breaking fields.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    import yaml
except ImportError as exc:  # pragma: no cover - dependency guard
    raise RuntimeError(
        "PyYAML is required to load Konnaxion capsule manifests. "
        "Install it with: pip install pyyaml"
    ) from exc

from kx_shared.konnaxion_constants import (
    APP_VERSION,
    CAPSULE_EXTENSION,
    CANONICAL_DOCKER_SERVICES,
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_VERSION,
    DEFAULT_CHANNEL,
    PARAM_VERSION,
    PRODUCT_NAME,
    DockerService,
    NetworkProfile,
)


MANIFEST_SCHEMA_VERSION = "kxcap/v1"

REQUIRED_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "capsule_id",
        "capsule_version",
        "app_name",
        "app_version",
        "channel",
        "created_at",
        "builder_version",
        "param_version",
        "services",
        "images",
        "profiles",
        "env_templates",
        "healthchecks",
        "policies",
    }
)

REQUIRED_CAPSULE_ROOT_ENTRIES = frozenset(
    {
        "manifest.yaml",
        "docker-compose.capsule.yml",
        "images",
        "profiles",
        "env-templates",
        "migrations",
        "healthchecks",
        "policies",
        "metadata",
        "checksums.txt",
        "signature.sig",
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

REQUIRED_PROFILES = frozenset(profile.value for profile in NetworkProfile)

REQUIRED_RUNTIME_SERVICES = frozenset(
    {
        DockerService.TRAEFIK.value,
        DockerService.FRONTEND_NEXT.value,
        DockerService.DJANGO_API.value,
        DockerService.POSTGRES.value,
        DockerService.REDIS.value,
        DockerService.CELERYWORKER.value,
        DockerService.CELERYBEAT.value,
        DockerService.MEDIA_NGINX.value,
    }
)

OPTIONAL_RUNTIME_SERVICES = frozenset(
    {
        DockerService.FLOWER.value,
        DockerService.KX_AGENT.value,
    }
)


class ManifestIssueLevel(StrEnum):
    """Validation issue severity."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ManifestIssue:
    """A single manifest validation issue."""

    level: ManifestIssueLevel
    path: str
    message: str


@dataclass(frozen=True)
class ManifestValidationResult:
    """Result returned by manifest validation."""

    valid: bool
    issues: tuple[ManifestIssue, ...] = field(default_factory=tuple)

    @property
    def errors(self) -> tuple[ManifestIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.level == ManifestIssueLevel.ERROR
        )

    @property
    def warnings(self) -> tuple[ManifestIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.level == ManifestIssueLevel.WARNING
        )

    def raise_for_errors(self) -> None:
        if self.errors:
            raise CapsuleManifestError.from_issues(self.errors)


class CapsuleManifestError(ValueError):
    """Raised when a capsule manifest cannot be loaded or validated."""

    @classmethod
    def from_issues(cls, issues: Sequence[ManifestIssue]) -> "CapsuleManifestError":
        rendered = "; ".join(f"{issue.path}: {issue.message}" for issue in issues)
        return cls(f"Invalid Konnaxion capsule manifest: {rendered}")


@dataclass(frozen=True)
class CapsuleService:
    """Service declaration from the capsule manifest."""

    name: str
    image: str | None = None
    required: bool = True
    role: str | None = None


@dataclass(frozen=True)
class CapsuleImage:
    """OCI image declaration from the capsule manifest."""

    service: str
    path: str
    digest: str | None = None


@dataclass(frozen=True)
class CapsuleManifest:
    """Typed view of ``manifest.yaml``."""

    schema_version: str
    capsule_id: str
    capsule_version: str
    app_name: str
    app_version: str
    channel: str
    created_at: str
    builder_version: str
    param_version: str
    services: tuple[CapsuleService, ...]
    images: tuple[CapsuleImage, ...]
    profiles: tuple[str, ...]
    env_templates: tuple[str, ...]
    healthchecks: tuple[str, ...]
    policies: tuple[str, ...]
    raw: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CapsuleManifest":
        """Build a typed manifest from a parsed YAML mapping."""

        if not isinstance(data, Mapping):
            raise CapsuleManifestError("Manifest root must be a YAML mapping/object.")

        services = tuple(_parse_services(data.get("services", ())))
        images = tuple(_parse_images(data.get("images", ())))

        return cls(
            schema_version=_clean_text(data.get("schema_version")),
            capsule_id=_clean_text(data.get("capsule_id")),
            capsule_version=_clean_text(data.get("capsule_version")),
            app_name=_clean_text(data.get("app_name")),
            app_version=_clean_text(data.get("app_version")),
            channel=_clean_text(data.get("channel")),
            created_at=_clean_text(data.get("created_at")),
            builder_version=_clean_text(data.get("builder_version")),
            param_version=_clean_text(data.get("param_version")),
            services=services,
            images=images,
            profiles=tuple(_as_string_list(data.get("profiles", ()))),
            env_templates=tuple(_as_string_list(data.get("env_templates", ()))),
            healthchecks=tuple(_as_string_list(data.get("healthchecks", ()))),
            policies=tuple(_as_string_list(data.get("policies", ()))),
            raw=data,
        )

    @classmethod
    def default_demo(cls) -> "CapsuleManifest":
        """Return a minimal valid demo manifest for tests and scaffolding."""

        now = _utc_now_iso_z()
        services = tuple(
            CapsuleService(
                name=service_name,
                image=f"konnaxion/{service_name}:{APP_VERSION}",
            )
            for service_name in sorted(REQUIRED_RUNTIME_SERVICES)
        )
        images = tuple(
            CapsuleImage(service=service.name, path=f"images/{service.name}.oci.tar")
            for service in services
        )

        raw: dict[str, Any] = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "capsule_id": DEFAULT_CAPSULE_ID,
            "capsule_version": DEFAULT_CAPSULE_VERSION,
            "app_name": PRODUCT_NAME,
            "app_version": APP_VERSION,
            "channel": DEFAULT_CHANNEL,
            "created_at": now,
            "builder_version": "kx-builder-0.1.0",
            "param_version": PARAM_VERSION,
            "services": [asdict(service) for service in services],
            "images": [asdict(image) for image in images],
            "profiles": sorted(REQUIRED_PROFILES),
            "env_templates": sorted(REQUIRED_ENV_TEMPLATES),
            "healthchecks": [
                "healthchecks/startup.yaml",
                "healthchecks/readiness.yaml",
            ],
            "policies": [
                "policies/security_gate.yaml",
                "policies/runtime_policy.yaml",
            ],
        }
        return cls.from_mapping(raw)

    def validate(self) -> ManifestValidationResult:
        """Validate the manifest against canonical Konnaxion capsule rules."""

        issues: list[ManifestIssue] = []

        _require_fields(self.raw, REQUIRED_ROOT_FIELDS, issues)

        _validate_equal(
            issues,
            path="schema_version",
            actual=self.schema_version,
            expected=MANIFEST_SCHEMA_VERSION,
            message_prefix="expected",
        )
        _validate_equal(
            issues,
            path="app_name",
            actual=self.app_name,
            expected=PRODUCT_NAME,
            message_prefix="expected canonical app name",
        )
        _validate_equal(
            issues,
            path="app_version",
            actual=self.app_version,
            expected=APP_VERSION,
            message_prefix="expected canonical app version",
        )
        _validate_equal(
            issues,
            path="param_version",
            actual=self.param_version,
            expected=PARAM_VERSION,
            message_prefix="expected canonical parameter version",
        )

        if not self.capsule_id:
            _add_error(issues, "capsule_id", "is required")
        elif not self.capsule_id.startswith("konnaxion-v14-"):
            _add_error(issues, "capsule_id", "must start with 'konnaxion-v14-'")

        if not self.capsule_version:
            _add_error(issues, "capsule_version", "is required")

        if not self.channel:
            _add_error(issues, "channel", "is required")

        _validate_created_at(self.created_at, issues)
        _validate_services(self.services, issues)
        _validate_images(self.images, issues)
        _validate_profiles(self.profiles, issues)
        _validate_env_templates(self.env_templates, issues)
        _validate_healthchecks(self.healthchecks, issues)
        _validate_policies(self.policies, issues)

        return ManifestValidationResult(
            valid=not _has_errors(issues),
            issues=tuple(issues),
        )

    def require_valid(self) -> "CapsuleManifest":
        """Validate and raise ``CapsuleManifestError`` on blocking errors."""

        self.validate().raise_for_errors()
        return self

    def service_names(self) -> tuple[str, ...]:
        return tuple(service.name for service in self.services)

    def image_paths(self) -> tuple[str, ...]:
        return tuple(image.path for image in self.images)


def load_manifest(path: str | Path) -> CapsuleManifest:
    """Load and validate a capsule ``manifest.yaml`` from disk."""

    manifest_path = Path(path)

    if manifest_path.name != "manifest.yaml":
        raise CapsuleManifestError(
            f"Expected a file named 'manifest.yaml', got {manifest_path.name!r}."
        )

    if not manifest_path.exists():
        raise CapsuleManifestError(f"Manifest file does not exist: {manifest_path}")

    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest = CapsuleManifest.from_mapping(data)
    return manifest.require_valid()


def load_manifest_text(text: str) -> CapsuleManifest:
    """Load and validate manifest YAML from a string."""

    data = yaml.safe_load(text)
    manifest = CapsuleManifest.from_mapping(data)
    return manifest.require_valid()


def validate_capsule_root(capsule_root: str | Path) -> ManifestValidationResult:
    """Validate the required extracted capsule root layout.

    This checks the extracted capsule directory layout, not the cryptographic
    signature or content checksums. Those are handled by ``signature.py`` and
    ``checksums.py``.
    """

    root = Path(capsule_root)
    issues: list[ManifestIssue] = []

    if not root.exists():
        _add_error(issues, str(root), "capsule root does not exist")
        return ManifestValidationResult(valid=False, issues=tuple(issues))

    if not root.is_dir():
        _add_error(issues, str(root), "capsule root must be a directory")
        return ManifestValidationResult(valid=False, issues=tuple(issues))

    existing = {item.name for item in root.iterdir()}
    missing = REQUIRED_CAPSULE_ROOT_ENTRIES - existing

    for entry in sorted(missing):
        _add_error(issues, entry, "required capsule root entry is missing")

    return ManifestValidationResult(
        valid=not _has_errors(issues),
        issues=tuple(issues),
    )


def capsule_filename_for(capsule_id: str) -> str:
    """Return the canonical filename for a capsule id."""

    if not capsule_id:
        raise CapsuleManifestError("capsule_id is required")

    return f"{capsule_id}{CAPSULE_EXTENSION}"


def _parse_services(value: Any) -> list[CapsuleService]:
    if value is None:
        return []

    if isinstance(value, Mapping):
        return [
            CapsuleService(
                name=str(name),
                image=_optional_text(config.get("image"))
                if isinstance(config, Mapping)
                else None,
                required=bool(config.get("required", True))
                if isinstance(config, Mapping)
                else True,
                role=_optional_text(config.get("role"))
                if isinstance(config, Mapping)
                else None,
            )
            for name, config in value.items()
        ]

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        parsed: list[CapsuleService] = []

        for item in value:
            if isinstance(item, str):
                parsed.append(CapsuleService(name=item))
            elif isinstance(item, Mapping):
                parsed.append(
                    CapsuleService(
                        name=_clean_text(item.get("name")),
                        image=_optional_text(item.get("image")),
                        required=bool(item.get("required", True)),
                        role=_optional_text(item.get("role")),
                    )
                )
            else:
                parsed.append(CapsuleService(name=""))

        return parsed

    return []


def _parse_images(value: Any) -> list[CapsuleImage]:
    if value is None:
        return []

    if isinstance(value, Mapping):
        parsed: list[CapsuleImage] = []

        for service, config in value.items():
            if isinstance(config, str):
                parsed.append(CapsuleImage(service=str(service), path=config))
            elif isinstance(config, Mapping):
                parsed.append(
                    CapsuleImage(
                        service=str(service),
                        path=_clean_text(config.get("path")),
                        digest=_optional_text(config.get("digest")),
                    )
                )

        return parsed

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        parsed: list[CapsuleImage] = []

        for item in value:
            if isinstance(item, Mapping):
                parsed.append(
                    CapsuleImage(
                        service=_clean_text(item.get("service")),
                        path=_clean_text(item.get("path")),
                        digest=_optional_text(item.get("digest")),
                    )
                )

        return parsed

    return []


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, Mapping):
        return [str(key) for key in value.keys()]

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item) for item in value]

    if isinstance(value, str):
        return [value]

    return []


def _require_fields(
    data: Mapping[str, Any],
    required_fields: frozenset[str],
    issues: list[ManifestIssue],
) -> None:
    missing = required_fields - set(data.keys())

    for field_name in sorted(missing):
        _add_error(issues, field_name, "required manifest field is missing")


def _validate_created_at(created_at: str, issues: list[ManifestIssue]) -> None:
    if not created_at:
        _add_error(issues, "created_at", "is required")
        return

    candidate = created_at.strip()

    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"

    try:
        datetime.fromisoformat(candidate)
    except ValueError:
        _add_error(issues, "created_at", "must be an ISO-8601 datetime")


def _validate_services(
    services: Sequence[CapsuleService],
    issues: list[ManifestIssue],
) -> None:
    service_names = {service.name for service in services if service.name}

    if not service_names:
        _add_error(issues, "services", "at least one service is required")
        return

    missing = REQUIRED_RUNTIME_SERVICES - service_names
    for service_name in sorted(missing):
        _add_error(
            issues,
            f"services.{service_name}",
            "required runtime service is missing",
        )

    allowed = set(CANONICAL_DOCKER_SERVICES)
    unknown = service_names - allowed
    for service_name in sorted(unknown):
        _add_error(
            issues,
            f"services.{service_name}",
            "service name is not canonical",
        )

    for service in services:
        if not service.name:
            _add_error(issues, "services[]", "service name is required")


def _validate_images(
    images: Sequence[CapsuleImage],
    issues: list[ManifestIssue],
) -> None:
    image_services = {image.service for image in images if image.service}

    if not image_services:
        _add_error(issues, "images", "at least one image is required")
        return

    missing = REQUIRED_RUNTIME_SERVICES - image_services
    for service_name in sorted(missing):
        _add_error(
            issues,
            f"images.{service_name}",
            "required runtime image is missing",
        )

    allowed_services = REQUIRED_RUNTIME_SERVICES | OPTIONAL_RUNTIME_SERVICES
    unknown = image_services - allowed_services
    for service_name in sorted(unknown):
        _add_error(
            issues,
            f"images.{service_name}",
            "image references a non-canonical service",
        )

    for image in images:
        if not image.service:
            _add_error(issues, "images[]", "image service is required")

        if not image.path:
            _add_error(
                issues,
                f"images.{image.service or '<unknown>'}.path",
                "image path is required",
            )
        elif not image.path.startswith("images/") or not image.path.endswith(".oci.tar"):
            _add_error(
                issues,
                f"images.{image.service}.path",
                "image path must be under images/ and end with .oci.tar",
            )


def _validate_profiles(profiles: Sequence[str], issues: list[ManifestIssue]) -> None:
    profile_set = set(profiles)

    missing = REQUIRED_PROFILES - profile_set
    for profile in sorted(missing):
        _add_error(
            issues,
            f"profiles.{profile}",
            "required network profile is missing",
        )

    unknown = profile_set - REQUIRED_PROFILES
    for profile in sorted(unknown):
        _add_error(
            issues,
            f"profiles.{profile}",
            "network profile is not canonical",
        )


def _validate_env_templates(
    env_templates: Sequence[str],
    issues: list[ManifestIssue],
) -> None:
    template_names = {Path(template).name for template in env_templates}

    missing = REQUIRED_ENV_TEMPLATES - template_names
    for template in sorted(missing):
        _add_error(
            issues,
            f"env_templates.{template}",
            "required environment template is missing",
        )

    for template in env_templates:
        name = Path(template).name

        if name not in REQUIRED_ENV_TEMPLATES:
            _add_warning(
                issues,
                f"env_templates.{template}",
                "non-canonical env template; keep secret-free",
            )


def _validate_healthchecks(
    healthchecks: Sequence[str],
    issues: list[ManifestIssue],
) -> None:
    if not healthchecks:
        _add_error(
            issues,
            "healthchecks",
            "at least one healthcheck definition is required",
        )


def _validate_policies(policies: Sequence[str], issues: list[ManifestIssue]) -> None:
    if not policies:
        _add_error(
            issues,
            "policies",
            "at least one runtime/security policy is required",
        )


def _validate_equal(
    issues: list[ManifestIssue],
    *,
    path: str,
    actual: str,
    expected: str,
    message_prefix: str,
) -> None:
    if actual == expected:
        return

    if message_prefix == "expected":
        message = f"expected {expected!r}, got {actual!r}"
    else:
        message = f"{message_prefix} {expected!r}"

    _add_error(issues, path, message)


def _add_error(issues: list[ManifestIssue], path: str, message: str) -> None:
    issues.append(ManifestIssue(ManifestIssueLevel.ERROR, path, message))


def _add_warning(issues: list[ManifestIssue], path: str, message: str) -> None:
    issues.append(ManifestIssue(ManifestIssueLevel.WARNING, path, message))


def _has_errors(issues: Sequence[ManifestIssue]) -> bool:
    return any(issue.level == ManifestIssueLevel.ERROR for issue in issues)


def _clean_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip()


def _optional_text(value: Any) -> str | None:
    text = _clean_text(value)
    return text or None


def _utc_now_iso_z() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")