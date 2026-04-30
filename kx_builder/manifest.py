"""
Konnaxion Capsule manifest generation and validation.

The manifest is the primary machine-readable contract inside a
``.kxcap`` file. It describes the application version, capsule identity,
runtime services, images, profiles, env templates, routes, healthchecks,
security expectations, and build metadata.

This module is used by the Konnaxion Capsule Builder. It should not read
host runtime state, secrets, databases, or mutable instance data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    import yaml
except ImportError as exc:  # pragma: no cover - dependency guard
    raise RuntimeError(
        "PyYAML is required for kx_builder.manifest. Install with: pip install pyyaml"
    ) from exc

from kx_shared.konnaxion_constants import (
    APP_VERSION,
    CAPSULE_EXTENSION,
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_VERSION,
    DEFAULT_CHANNEL,
    DEFAULT_EXPOSURE_MODE,
    DEFAULT_NETWORK_PROFILE,
    DockerService,
    ExposureMode,
    NetworkProfile,
    PARAM_VERSION,
    PRODUCT_NAME,
    ROUTES,
)


MANIFEST_SCHEMA_VERSION = "kxcap/v1"
DEFAULT_BUILDER_VERSION = "kx-builder-0.1.0"

REQUIRED_ROOT_ENTRIES = (
    "manifest.yaml",
    "docker-compose.capsule.yml",
    "images/",
    "profiles/",
    "env-templates/",
    "migrations/",
    "healthchecks/",
    "policies/",
    "metadata/",
    "checksums.txt",
    "signature.sig",
)

DEFAULT_ENV_TEMPLATES = (
    "env-templates/django.env.template",
    "env-templates/postgres.env.template",
    "env-templates/redis.env.template",
    "env-templates/frontend.env.template",
)

DEFAULT_PROFILE_FILES = {
    NetworkProfile.LOCAL_ONLY: "profiles/local_only.yaml",
    NetworkProfile.INTRANET_PRIVATE: "profiles/intranet_private.yaml",
    NetworkProfile.PRIVATE_TUNNEL: "profiles/private_tunnel.yaml",
    NetworkProfile.PUBLIC_TEMPORARY: "profiles/public_temporary.yaml",
    NetworkProfile.PUBLIC_VPS: "profiles/public_vps.yaml",
    NetworkProfile.OFFLINE: "profiles/offline.yaml",
}

DEFAULT_IMAGE_ARCHIVES = {
    DockerService.TRAEFIK: "images/traefik.oci.tar",
    DockerService.FRONTEND_NEXT: "images/frontend-next.oci.tar",
    DockerService.DJANGO_API: "images/django-api.oci.tar",
    DockerService.POSTGRES: "images/postgres.oci.tar",
    DockerService.REDIS: "images/redis.oci.tar",
    DockerService.CELERYWORKER: "images/celeryworker.oci.tar",
    DockerService.CELERYBEAT: "images/celerybeat.oci.tar",
    DockerService.FLOWER: "images/flower.oci.tar",
    DockerService.MEDIA_NGINX: "images/media-nginx.oci.tar",
}


class ManifestError(ValueError):
    """Raised when a Konnaxion Capsule manifest is invalid."""


@dataclass(frozen=True, slots=True)
class ManifestImage:
    """OCI image archive declared by the capsule manifest."""

    service: DockerService
    archive: str
    image: str
    digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "service": self.service.value,
            "archive": self.archive,
            "image": self.image,
        }
        if self.digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True, slots=True)
class ManifestProfile:
    """Network profile file declared by the capsule manifest."""

    name: NetworkProfile
    path: str
    default: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name.value,
            "path": self.path,
            "default": self.default,
        }


@dataclass(frozen=True, slots=True)
class ManifestRoute:
    """HTTP route mapping handled by Traefik."""

    path: str
    service: DockerService

    def to_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "service": self.service.value,
        }


@dataclass(frozen=True, slots=True)
class ManifestRuntime:
    """Runtime service topology declared by the capsule."""

    compose_file: str = "docker-compose.capsule.yml"
    entrypoint_service: DockerService = DockerService.TRAEFIK
    services: tuple[DockerService, ...] = (
        DockerService.TRAEFIK,
        DockerService.FRONTEND_NEXT,
        DockerService.DJANGO_API,
        DockerService.POSTGRES,
        DockerService.REDIS,
        DockerService.CELERYWORKER,
        DockerService.CELERYBEAT,
        DockerService.FLOWER,
        DockerService.MEDIA_NGINX,
    )
    routes: tuple[ManifestRoute, ...] = field(
        default_factory=lambda: tuple(
            ManifestRoute(path=path, service=DockerService(service))
            for path, service in ROUTES.items()
        )
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "compose_file": self.compose_file,
            "entrypoint_service": self.entrypoint_service.value,
            "services": [service.value for service in self.services],
            "routes": [route.to_dict() for route in self.routes],
        }


@dataclass(frozen=True, slots=True)
class ManifestSecurity:
    """Security policy expectations declared by the capsule."""

    require_signature: bool = True
    require_checksums: bool = True
    require_generated_secrets: bool = True
    allow_unknown_images: bool = False
    allow_privileged_containers: bool = False
    allow_docker_socket_mount: bool = False
    allow_host_network: bool = False
    private_by_default: bool = True
    default_exposure_mode: ExposureMode = DEFAULT_EXPOSURE_MODE

    def to_dict(self) -> dict[str, Any]:
        return {
            "require_signature": self.require_signature,
            "require_checksums": self.require_checksums,
            "require_generated_secrets": self.require_generated_secrets,
            "allow_unknown_images": self.allow_unknown_images,
            "allow_privileged_containers": self.allow_privileged_containers,
            "allow_docker_socket_mount": self.allow_docker_socket_mount,
            "allow_host_network": self.allow_host_network,
            "private_by_default": self.private_by_default,
            "default_exposure_mode": self.default_exposure_mode.value,
        }


@dataclass(frozen=True, slots=True)
class ManifestHealthcheck:
    """Healthcheck declaration for a service."""

    name: str
    path: str
    service: DockerService | None = None
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = {
            "name": self.name,
            "path": self.path,
            "required": self.required,
        }
        if self.service is not None:
            data["service"] = self.service.value
        return data


@dataclass(frozen=True, slots=True)
class CapsuleManifest:
    """Complete Konnaxion Capsule manifest."""

    schema_version: str = MANIFEST_SCHEMA_VERSION
    capsule_id: str = DEFAULT_CAPSULE_ID
    capsule_version: str = DEFAULT_CAPSULE_VERSION
    app_name: str = PRODUCT_NAME
    app_version: str = APP_VERSION
    param_version: str = PARAM_VERSION
    channel: str = DEFAULT_CHANNEL
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    builder_version: str = DEFAULT_BUILDER_VERSION
    default_network_profile: NetworkProfile = DEFAULT_NETWORK_PROFILE
    runtime: ManifestRuntime = field(default_factory=ManifestRuntime)
    security: ManifestSecurity = field(default_factory=ManifestSecurity)
    images: tuple[ManifestImage, ...] = field(default_factory=tuple)
    profiles: tuple[ManifestProfile, ...] = field(default_factory=tuple)
    env_templates: tuple[str, ...] = DEFAULT_ENV_TEMPLATES
    healthchecks: tuple[ManifestHealthcheck, ...] = field(default_factory=tuple)
    required_root_entries: tuple[str, ...] = REQUIRED_ROOT_ENTRIES
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "capsule_id": self.capsule_id,
            "capsule_version": self.capsule_version,
            "app_name": self.app_name,
            "app_version": self.app_version,
            "param_version": self.param_version,
            "channel": self.channel,
            "created_at": self.created_at.isoformat(),
            "builder_version": self.builder_version,
            "default_network_profile": self.default_network_profile.value,
            "runtime": self.runtime.to_dict(),
            "security": self.security.to_dict(),
            "images": [image.to_dict() for image in self.images],
            "profiles": [profile.to_dict() for profile in self.profiles],
            "env_templates": list(self.env_templates),
            "healthchecks": [
                healthcheck.to_dict() for healthcheck in self.healthchecks
            ],
            "required_root_entries": list(self.required_root_entries),
            "metadata": self.metadata,
        }


def default_images(
    *,
    image_prefix: str = "konnaxion",
    tag: str = APP_VERSION,
    digests: Mapping[str, str] | None = None,
) -> tuple[ManifestImage, ...]:
    """Create default image declarations for the canonical service set."""

    digest_map = dict(digests or {})
    images: list[ManifestImage] = []

    for service, archive in DEFAULT_IMAGE_ARCHIVES.items():
        service_name = service.value
        images.append(
            ManifestImage(
                service=service,
                archive=archive,
                image=f"{image_prefix}/{service_name}:{tag}",
                digest=digest_map.get(service_name),
            )
        )

    return tuple(images)


def default_profiles(
    *,
    default_profile: NetworkProfile = DEFAULT_NETWORK_PROFILE,
) -> tuple[ManifestProfile, ...]:
    """Create default profile declarations for canonical network profiles."""

    return tuple(
        ManifestProfile(
            name=profile,
            path=path,
            default=(profile == default_profile),
        )
        for profile, path in DEFAULT_PROFILE_FILES.items()
    )


def default_healthchecks() -> tuple[ManifestHealthcheck, ...]:
    """Create default healthcheck declarations."""

    return (
        ManifestHealthcheck(
            name="frontend",
            path="healthchecks/frontend-next.http",
            service=DockerService.FRONTEND_NEXT,
        ),
        ManifestHealthcheck(
            name="api",
            path="healthchecks/django-api.http",
            service=DockerService.DJANGO_API,
        ),
        ManifestHealthcheck(
            name="postgres",
            path="healthchecks/postgres.sh",
            service=DockerService.POSTGRES,
        ),
        ManifestHealthcheck(
            name="redis",
            path="healthchecks/redis.sh",
            service=DockerService.REDIS,
        ),
    )


def build_manifest(
    *,
    capsule_id: str = DEFAULT_CAPSULE_ID,
    capsule_version: str = DEFAULT_CAPSULE_VERSION,
    channel: str = DEFAULT_CHANNEL,
    app_version: str = APP_VERSION,
    param_version: str = PARAM_VERSION,
    builder_version: str = DEFAULT_BUILDER_VERSION,
    image_prefix: str = "konnaxion",
    image_tag: str | None = None,
    image_digests: Mapping[str, str] | None = None,
    default_network_profile: NetworkProfile = DEFAULT_NETWORK_PROFILE,
    metadata: Mapping[str, Any] | None = None,
) -> CapsuleManifest:
    """Build a canonical Konnaxion Capsule manifest object."""

    tag = image_tag or app_version

    manifest = CapsuleManifest(
        capsule_id=capsule_id,
        capsule_version=capsule_version,
        app_version=app_version,
        param_version=param_version,
        channel=channel,
        builder_version=builder_version,
        default_network_profile=default_network_profile,
        images=default_images(
            image_prefix=image_prefix,
            tag=tag,
            digests=image_digests,
        ),
        profiles=default_profiles(default_profile=default_network_profile),
        healthchecks=default_healthchecks(),
        metadata=dict(metadata or {}),
    )
    validate_manifest_dict(manifest.to_dict())
    return manifest


def write_manifest(manifest: CapsuleManifest | Mapping[str, Any], path: str | Path) -> Path:
    """Write a manifest to YAML."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = manifest.to_dict() if isinstance(manifest, CapsuleManifest) else dict(manifest)
    validate_manifest_dict(data)

    output_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return output_path


def read_manifest(path: str | Path) -> dict[str, Any]:
    """Read and validate a manifest YAML file."""

    manifest_path = Path(path)
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ManifestError(f"Manifest is not a YAML object: {manifest_path}")

    validate_manifest_dict(data)
    return data


def validate_manifest_dict(data: Mapping[str, Any]) -> None:
    """Validate the required canonical manifest fields."""

    required_top_level = {
        "schema_version",
        "capsule_id",
        "capsule_version",
        "app_name",
        "app_version",
        "param_version",
        "channel",
        "created_at",
        "builder_version",
        "default_network_profile",
        "runtime",
        "security",
        "images",
        "profiles",
        "env_templates",
        "healthchecks",
        "required_root_entries",
        "metadata",
    }
    missing = sorted(required_top_level.difference(data.keys()))
    if missing:
        raise ManifestError(f"Manifest missing required fields: {', '.join(missing)}")

    if data["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise ManifestError(
            f"Unsupported manifest schema_version: {data['schema_version']!r}"
        )

    capsule_id = str(data["capsule_id"])
    if capsule_id.endswith(CAPSULE_EXTENSION):
        raise ManifestError(
            "capsule_id must not include the .kxcap file extension."
        )

    validate_network_profile(data["default_network_profile"])
    validate_runtime(data["runtime"])
    validate_security(data["security"])
    validate_images(data["images"])
    validate_profiles(data["profiles"], default_profile=data["default_network_profile"])
    validate_env_templates(data["env_templates"])
    validate_required_root_entries(data["required_root_entries"])


def validate_runtime(runtime: Any) -> None:
    """Validate runtime service topology."""

    if not isinstance(runtime, Mapping):
        raise ManifestError("runtime must be an object.")

    services = runtime.get("services")
    if not isinstance(services, list) or not services:
        raise ManifestError("runtime.services must be a non-empty list.")

    service_values = {service.value for service in DockerService}
    unknown = sorted(set(str(service) for service in services).difference(service_values))
    if unknown:
        raise ManifestError(f"Unknown runtime services: {', '.join(unknown)}")

    required_services = {
        DockerService.TRAEFIK.value,
        DockerService.FRONTEND_NEXT.value,
        DockerService.DJANGO_API.value,
        DockerService.POSTGRES.value,
        DockerService.REDIS.value,
        DockerService.CELERYWORKER.value,
        DockerService.CELERYBEAT.value,
        DockerService.MEDIA_NGINX.value,
    }
    missing = sorted(required_services.difference(set(services)))
    if missing:
        raise ManifestError(f"Runtime missing required services: {', '.join(missing)}")

    if runtime.get("entrypoint_service") != DockerService.TRAEFIK.value:
        raise ManifestError("runtime.entrypoint_service must be traefik.")

    routes = runtime.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ManifestError("runtime.routes must be a non-empty list.")

    for route in routes:
        if not isinstance(route, Mapping):
            raise ManifestError("Each runtime route must be an object.")
        path = route.get("path")
        service = route.get("service")
        if not isinstance(path, str) or not path.startswith("/"):
            raise ManifestError(f"Invalid route path: {path!r}")
        if service not in service_values:
            raise ManifestError(f"Invalid route service: {service!r}")


def validate_security(security: Any) -> None:
    """Validate security posture fields."""

    if not isinstance(security, Mapping):
        raise ManifestError("security must be an object.")

    must_be_false = (
        "allow_unknown_images",
        "allow_privileged_containers",
        "allow_docker_socket_mount",
        "allow_host_network",
    )
    for key in must_be_false:
        if security.get(key) is not False:
            raise ManifestError(f"security.{key} must be false.")

    must_be_true = (
        "require_signature",
        "require_checksums",
        "require_generated_secrets",
        "private_by_default",
    )
    for key in must_be_true:
        if security.get(key) is not True:
            raise ManifestError(f"security.{key} must be true.")

    validate_exposure_mode(security.get("default_exposure_mode"))


def validate_images(images: Any) -> None:
    """Validate image declarations."""

    if not isinstance(images, list) or not images:
        raise ManifestError("images must be a non-empty list.")

    service_values = {service.value for service in DockerService}
    seen_services: set[str] = set()

    for image in images:
        if not isinstance(image, Mapping):
            raise ManifestError("Each image entry must be an object.")

        service = image.get("service")
        archive = image.get("archive")
        image_name = image.get("image")

        if service not in service_values:
            raise ManifestError(f"Invalid image service: {service!r}")
        if not isinstance(archive, str) or not archive.startswith("images/"):
            raise ManifestError(f"Invalid image archive path: {archive!r}")
        if not isinstance(image_name, str) or ":" not in image_name:
            raise ManifestError(f"Invalid image name: {image_name!r}")

        seen_services.add(service)

    required = {
        DockerService.TRAEFIK.value,
        DockerService.FRONTEND_NEXT.value,
        DockerService.DJANGO_API.value,
        DockerService.POSTGRES.value,
        DockerService.REDIS.value,
        DockerService.CELERYWORKER.value,
        DockerService.CELERYBEAT.value,
        DockerService.MEDIA_NGINX.value,
    }
    missing = sorted(required.difference(seen_services))
    if missing:
        raise ManifestError(f"Images missing required services: {', '.join(missing)}")


def validate_profiles(profiles: Any, *, default_profile: str) -> None:
    """Validate profile declarations."""

    if not isinstance(profiles, list) or not profiles:
        raise ManifestError("profiles must be a non-empty list.")

    profile_values = {profile.value for profile in NetworkProfile}
    seen_profiles: set[str] = set()
    default_count = 0

    for profile in profiles:
        if not isinstance(profile, Mapping):
            raise ManifestError("Each profile entry must be an object.")

        name = profile.get("name")
        path = profile.get("path")
        is_default = profile.get("default")

        if name not in profile_values:
            raise ManifestError(f"Invalid profile name: {name!r}")
        if not isinstance(path, str) or not path.startswith("profiles/"):
            raise ManifestError(f"Invalid profile path: {path!r}")
        if not isinstance(is_default, bool):
            raise ManifestError("profile.default must be a boolean.")

        seen_profiles.add(name)
        if is_default:
            default_count += 1
            if name != default_profile:
                raise ManifestError(
                    "The profile marked as default must match default_network_profile."
                )

    if default_count != 1:
        raise ManifestError("Exactly one profile must be marked as default.")

    missing = sorted(profile_values.difference(seen_profiles))
    if missing:
        raise ManifestError(f"Profiles missing canonical entries: {', '.join(missing)}")


def validate_env_templates(env_templates: Any) -> None:
    """Validate env template declarations."""

    if not isinstance(env_templates, list) or not env_templates:
        raise ManifestError("env_templates must be a non-empty list.")

    for template in env_templates:
        if not isinstance(template, str) or not template.startswith("env-templates/"):
            raise ManifestError(f"Invalid env template path: {template!r}")
        if not template.endswith(".template"):
            raise ManifestError(f"Env template must end with .template: {template!r}")


def validate_required_root_entries(entries: Any) -> None:
    """Validate required root entries declared by the manifest."""

    if not isinstance(entries, list) or not entries:
        raise ManifestError("required_root_entries must be a non-empty list.")

    missing = sorted(set(REQUIRED_ROOT_ENTRIES).difference(set(entries)))
    if missing:
        raise ManifestError(
            f"required_root_entries missing canonical entries: {', '.join(missing)}"
        )


def validate_network_profile(value: Any) -> NetworkProfile:
    """Validate and return a canonical network profile."""

    try:
        return value if isinstance(value, NetworkProfile) else NetworkProfile(str(value))
    except ValueError as exc:
        raise ManifestError(f"Invalid network profile: {value!r}") from exc


def validate_exposure_mode(value: Any) -> ExposureMode:
    """Validate and return a canonical exposure mode."""

    try:
        return value if isinstance(value, ExposureMode) else ExposureMode(str(value))
    except ValueError as exc:
        raise ManifestError(f"Invalid exposure mode: {value!r}") from exc


def manifest_filename(capsule_id: str) -> str:
    """Return the expected capsule filename for a capsule id."""

    clean_id = capsule_id.removesuffix(CAPSULE_EXTENSION)
    return f"{clean_id}{CAPSULE_EXTENSION}"


def assert_no_secrets_in_manifest(data: Mapping[str, Any]) -> None:
    """Reject obvious secret-bearing keys or values in manifest data."""

    forbidden_tokens = (
        "DJANGO_SECRET_KEY",
        "POSTGRES_PASSWORD",
        "DATABASE_URL",
        "SSH_PRIVATE_KEY",
        "API_TOKEN",
        "GIT_TOKEN",
        "PROVIDER_TOKEN",
        "PRIVATE_KEY",
    )
    serialized = yaml.safe_dump(dict(data), sort_keys=True)

    for token in forbidden_tokens:
        if token in serialized:
            raise ManifestError(
                f"Manifest must not contain real or placeholder secret token: {token}"
            )


def load_checksum_map(path: str | Path) -> dict[str, str]:
    """Load a checksums.txt-style digest map.

    Expected line format:
        <digest>  <relative_path>
    """

    checksum_path = Path(path)
    checksums: dict[str, str] = {}

    for line_number, raw_line in enumerate(
        checksum_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            raise ManifestError(
                f"Invalid checksum line {line_number} in {checksum_path}: {raw_line!r}"
            )

        digest, relative_path = parts
        checksums[relative_path.strip()] = digest.strip()

    return checksums


def attach_image_digests(
    manifest: CapsuleManifest,
    checksums: Mapping[str, str],
) -> CapsuleManifest:
    """Return a copy of a manifest with image digests attached."""

    images = tuple(
        ManifestImage(
            service=image.service,
            archive=image.archive,
            image=image.image,
            digest=checksums.get(image.archive, image.digest),
        )
        for image in manifest.images
    )

    updated = CapsuleManifest(
        schema_version=manifest.schema_version,
        capsule_id=manifest.capsule_id,
        capsule_version=manifest.capsule_version,
        app_name=manifest.app_name,
        app_version=manifest.app_version,
        param_version=manifest.param_version,
        channel=manifest.channel,
        created_at=manifest.created_at,
        builder_version=manifest.builder_version,
        default_network_profile=manifest.default_network_profile,
        runtime=manifest.runtime,
        security=manifest.security,
        images=images,
        profiles=manifest.profiles,
        env_templates=manifest.env_templates,
        healthchecks=manifest.healthchecks,
        required_root_entries=manifest.required_root_entries,
        metadata=manifest.metadata,
    )
    validate_manifest_dict(updated.to_dict())
    return updated


def ensure_manifest_paths_exist(
    *,
    capsule_root: str | Path,
    manifest: CapsuleManifest | Mapping[str, Any],
) -> None:
    """Check that manifest-declared files exist under a capsule staging root."""

    root = Path(capsule_root)
    data = manifest.to_dict() if isinstance(manifest, CapsuleManifest) else dict(manifest)
    validate_manifest_dict(data)

    required_paths: list[str] = []
    required_paths.extend(
        entry.rstrip("/")
        for entry in data["required_root_entries"]
        if entry != "signature.sig"
    )
    required_paths.extend(image["archive"] for image in data["images"])
    required_paths.extend(profile["path"] for profile in data["profiles"])
    required_paths.extend(data["env_templates"])
    required_paths.extend(healthcheck["path"] for healthcheck in data["healthchecks"])

    missing = sorted(
        relative_path
        for relative_path in set(required_paths)
        if not (root / relative_path).exists()
    )
    if missing:
        raise ManifestError(
            f"Capsule staging root is missing manifest paths: {', '.join(missing)}"
        )


def manifest_to_yaml(manifest: CapsuleManifest | Mapping[str, Any]) -> str:
    """Serialize a manifest object or mapping to YAML."""

    data = manifest.to_dict() if isinstance(manifest, CapsuleManifest) else dict(manifest)
    validate_manifest_dict(data)
    assert_no_secrets_in_manifest(data)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def manifests_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """Return true when two manifest dictionaries are equivalent as YAML data."""

    return yaml.safe_dump(dict(left), sort_keys=True) == yaml.safe_dump(
        dict(right),
        sort_keys=True,
    )


def service_values(services: Iterable[DockerService]) -> list[str]:
    """Return canonical string values for Docker services."""

    return [service.value for service in services]


__all__ = [
    "CapsuleManifest",
    "DEFAULT_BUILDER_VERSION",
    "DEFAULT_ENV_TEMPLATES",
    "DEFAULT_IMAGE_ARCHIVES",
    "DEFAULT_PROFILE_FILES",
    "MANIFEST_SCHEMA_VERSION",
    "ManifestError",
    "ManifestHealthcheck",
    "ManifestImage",
    "ManifestProfile",
    "ManifestRoute",
    "ManifestRuntime",
    "ManifestSecurity",
    "REQUIRED_ROOT_ENTRIES",
    "assert_no_secrets_in_manifest",
    "attach_image_digests",
    "build_manifest",
    "default_healthchecks",
    "default_images",
    "default_profiles",
    "ensure_manifest_paths_exist",
    "load_checksum_map",
    "manifest_filename",
    "manifest_to_yaml",
    "manifests_equal",
    "read_manifest",
    "service_values",
    "validate_env_templates",
    "validate_exposure_mode",
    "validate_images",
    "validate_manifest_dict",
    "validate_network_profile",
    "validate_profiles",
    "validate_required_root_entries",
    "validate_runtime",
    "validate_security",
    "write_manifest",
]
