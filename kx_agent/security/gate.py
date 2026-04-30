"""
Konnaxion Agent Security Gate.

The Security Gate is the mandatory pre-start validation layer for every
Konnaxion Instance. It evaluates capsule integrity, manifest shape, generated
secrets, exposed ports, service policy, Docker runtime hazards, admin exposure,
and backup readiness.

This module is intentionally deterministic and side-effect-light. It consumes a
SecurityGateContext prepared by higher-level Agent components and returns a
SecurityGateSummary that the lifecycle layer can use to allow or block startup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from kx_shared.konnaxion_constants import (
    BLOCKING_SECURITY_CHECKS,
    CANONICAL_DOCKER_SERVICES,
    FORBIDDEN_PUBLIC_PORTS,
    INTERNAL_ONLY_PORTS,
    KX_BACKUPS_ROOT,
    ROUTES,
    DockerService,
    SecurityGateCheck,
    SecurityGateStatus,
    is_canonical_service,
)

from kx_agent.instances.model import (
    SecurityGateCheckResult,
    SecurityGateSummary,
)


# ---------------------------------------------------------------------------
# Security Gate constants
# ---------------------------------------------------------------------------

REQUIRED_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "capsule_id",
        "capsule_version",
        "app_name",
        "app_version",
        "channel",
    }
)

REQUIRED_SECRET_KEYS = frozenset(
    {
        "DJANGO_SECRET_KEY",
        "POSTGRES_PASSWORD",
        "DATABASE_URL",
    }
)

SECRET_PLACEHOLDER_VALUES = frozenset(
    {
        "",
        "changeme",
        "change-me",
        "change_me",
        "password",
        "postgres",
        "secret",
        "default",
        "<generated_on_install>",
        "<generated-from-profile>",
        "<generated_from_profile>",
        "<postgres_password>",
        "<public_or_private_host>",
    }
)

SECRET_PLACEHOLDER_SUBSTRINGS = frozenset(
    {
        "<generated",
        "<postgres_password>",
        "<public_or_private_host>",
        "changeme",
        "change-me",
        "example",
        "placeholder",
        "dummy",
        "default-secret",
    }
)

FORBIDDEN_MOUNT_PATHS = frozenset(
    {
        "/var/run/docker.sock",
        "/run/docker.sock",
        "docker.sock",
    }
)

FORBIDDEN_HOST_NETWORK_VALUES = frozenset(
    {
        "host",
    }
)

FORBIDDEN_PRIVILEGED_VALUES = frozenset(
    {
        True,
        "true",
        "True",
        "yes",
        "1",
        1,
    }
)

DEFAULT_ALLOWED_IMAGES = frozenset(
    {
        DockerService.TRAEFIK.value,
        DockerService.FRONTEND_NEXT.value,
        DockerService.DJANGO_API.value,
        DockerService.POSTGRES.value,
        DockerService.REDIS.value,
        DockerService.CELERYWORKER.value,
        DockerService.CELERYBEAT.value,
        DockerService.FLOWER.value,
        DockerService.MEDIA_NGINX.value,
        DockerService.KX_AGENT.value,
    }
)


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PublishedPort:
    """A host-published port discovered in runtime configuration."""

    service: str
    host_port: int
    container_port: int | None = None
    protocol: str = "tcp"
    host_ip: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "service", str(self.service))
        object.__setattr__(self, "host_port", int(self.host_port))
        if self.container_port is not None:
            object.__setattr__(self, "container_port", int(self.container_port))


@dataclass(frozen=True)
class RuntimeServicePolicy:
    """Security-relevant runtime settings for one service."""

    name: str
    image: str | None = None
    privileged: bool = False
    network_mode: str | None = None
    mounts: tuple[str, ...] = field(default_factory=tuple)
    published_ports: tuple[PublishedPort, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "mounts", tuple(str(mount) for mount in self.mounts))
        object.__setattr__(
            self,
            "published_ports",
            tuple(self.published_ports),
        )


@dataclass(frozen=True)
class SecurityGatePolicy:
    """Toggles used by the Security Gate."""

    require_signed_capsule: bool = True
    require_image_checksums: bool = True
    require_firewall_enabled: bool = True
    require_backup_configured: bool = True
    allow_unknown_images: bool = False
    allow_privileged_containers: bool = False
    allow_docker_socket_mount: bool = False
    allow_host_network: bool = False
    allowed_images: frozenset[str] = DEFAULT_ALLOWED_IMAGES

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "SecurityGatePolicy":
        """Build policy from KX_* environment values."""
        return cls(
            require_signed_capsule=_env_bool(env, "KX_REQUIRE_SIGNED_CAPSULE", True),
            require_image_checksums=True,
            require_firewall_enabled=True,
            require_backup_configured=_env_bool(env, "KX_BACKUP_ENABLED", True),
            allow_unknown_images=_env_bool(env, "KX_ALLOW_UNKNOWN_IMAGES", False),
            allow_privileged_containers=_env_bool(env, "KX_ALLOW_PRIVILEGED_CONTAINERS", False),
            allow_docker_socket_mount=_env_bool(env, "KX_ALLOW_DOCKER_SOCKET_MOUNT", False),
            allow_host_network=_env_bool(env, "KX_ALLOW_HOST_NETWORK", False),
        )


@dataclass(frozen=True)
class SecurityGateContext:
    """
    Complete input to run the Security Gate.

    Higher-level Agent code should prepare this from the verified capsule,
    generated instance env, resolved compose model, network profile, firewall
    status, and backup configuration.
    """

    instance_id: str
    capsule_path: Path | None = None
    manifest: Mapping[str, Any] = field(default_factory=dict)
    env: Mapping[str, str] = field(default_factory=dict)
    services: tuple[RuntimeServicePolicy, ...] = field(default_factory=tuple)
    published_ports: tuple[PublishedPort, ...] = field(default_factory=tuple)
    allowed_images: frozenset[str] = DEFAULT_ALLOWED_IMAGES
    capsule_signature_verified: bool = False
    image_checksums_verified: bool = False
    firewall_enabled: bool = False
    backup_configured: bool = False
    backup_root: Path = KX_BACKUPS_ROOT
    admin_surface_private: bool = True
    postgres_public: bool = False
    redis_public: bool = False
    policy: SecurityGatePolicy = field(default_factory=SecurityGatePolicy)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "instance_id", str(self.instance_id).strip())
        object.__setattr__(self, "services", tuple(self.services))
        object.__setattr__(self, "published_ports", tuple(self.published_ports))
        object.__setattr__(self, "allowed_images", frozenset(self.allowed_images))

        if not self.instance_id:
            raise ValueError("instance_id is required.")


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(UTC)


def _env_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    value = env.get(key)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _result(
    check: SecurityGateCheck,
    status: SecurityGateStatus,
    message: str,
    *,
    details: Mapping[str, Any] | None = None,
) -> SecurityGateCheckResult:
    return SecurityGateCheckResult(
        check=check,
        status=status,
        message=message,
        blocking=check in BLOCKING_SECURITY_CHECKS,
        details=dict(details or {}),
        checked_at=_utc_now(),
    )


def _pass(check: SecurityGateCheck, message: str, *, details: Mapping[str, Any] | None = None) -> SecurityGateCheckResult:
    return _result(check, SecurityGateStatus.PASS, message, details=details)


def _warn(check: SecurityGateCheck, message: str, *, details: Mapping[str, Any] | None = None) -> SecurityGateCheckResult:
    return _result(check, SecurityGateStatus.WARN, message, details=details)


def _fail(check: SecurityGateCheck, message: str, *, details: Mapping[str, Any] | None = None) -> SecurityGateCheckResult:
    return _result(check, SecurityGateStatus.FAIL_BLOCKING, message, details=details)


def _skipped(check: SecurityGateCheck, message: str, *, details: Mapping[str, Any] | None = None) -> SecurityGateCheckResult:
    return _result(check, SecurityGateStatus.SKIPPED, message, details=details)


def _unknown(check: SecurityGateCheck, message: str, *, details: Mapping[str, Any] | None = None) -> SecurityGateCheckResult:
    return _result(check, SecurityGateStatus.UNKNOWN, message, details=details)


def _public_ports(context: SecurityGateContext) -> tuple[PublishedPort, ...]:
    return tuple((*context.published_ports, *(port for service in context.services for port in service.published_ports)))


def _has_forbidden_mount(mounts: Iterable[str]) -> bool:
    for mount in mounts:
        normalized = str(mount).lower()
        if any(forbidden in normalized for forbidden in FORBIDDEN_MOUNT_PATHS):
            return True
    return False


def _image_base_name(image: str | None) -> str | None:
    if not image:
        return None

    raw = image.strip()
    if not raw:
        return None

    # registry/path/name:tag -> name
    name_with_tag = raw.rsplit("/", 1)[-1]
    return name_with_tag.split(":", 1)[0]


def _secret_is_placeholder(value: str | None) -> bool:
    if value is None:
        return True

    normalized = str(value).strip()
    lowered = normalized.lower()

    if lowered in SECRET_PLACEHOLDER_VALUES:
        return True

    return any(fragment in lowered for fragment in SECRET_PLACEHOLDER_SUBSTRINGS)


def _database_url_has_placeholder(value: str | None) -> bool:
    if not value:
        return True

    lowered = value.lower()
    return (
        "<postgres_password>" in lowered
        or "changeme" in lowered
        or "password@" in lowered
        or ":postgres@" in lowered
        or "placeholder" in lowered
    )


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_capsule_signature(context: SecurityGateContext) -> SecurityGateCheckResult:
    """Validate capsule signature status."""
    check = SecurityGateCheck.CAPSULE_SIGNATURE

    if not context.policy.require_signed_capsule:
        return _warn(check, "Signed capsule enforcement is disabled by policy.")

    if context.capsule_signature_verified:
        return _pass(check, "Capsule signature verified.")

    return _fail(check, "Capsule signature is missing or invalid.")


def check_image_checksums(context: SecurityGateContext) -> SecurityGateCheckResult:
    """Validate OCI image checksum verification status."""
    check = SecurityGateCheck.IMAGE_CHECKSUMS

    if not context.policy.require_image_checksums:
        return _warn(check, "Image checksum enforcement is disabled by policy.")

    if context.image_checksums_verified:
        return _pass(check, "Image checksums verified.")

    return _fail(check, "Image checksums are missing or invalid.")


def check_manifest_schema(context: SecurityGateContext) -> SecurityGateCheckResult:
    """Validate the manifest contains required root fields."""
    check = SecurityGateCheck.MANIFEST_SCHEMA

    if not context.manifest:
        return _fail(check, "Manifest is missing.")

    missing = sorted(REQUIRED_MANIFEST_FIELDS.difference(context.manifest.keys()))
    if missing:
        return _fail(
            check,
            "Manifest is missing required fields.",
            details={"missing_fields": missing},
        )

    services = context.manifest.get("services")
    if services is not None:
        invalid_services = sorted(
            service for service in _extract_service_names(services) if not is_canonical_service(service)
        )
        if invalid_services:
            return _fail(
                check,
                "Manifest references non-canonical service names.",
                details={"invalid_services": invalid_services},
            )

    return _pass(
        check,
        "Manifest schema has required canonical fields.",
        details={"required_fields": sorted(REQUIRED_MANIFEST_FIELDS)},
    )


def check_secrets_present(context: SecurityGateContext) -> SecurityGateCheckResult:
    """Validate required generated secrets are present."""
    check = SecurityGateCheck.SECRETS_PRESENT
    missing = sorted(key for key in REQUIRED_SECRET_KEYS if not str(context.env.get(key, "")).strip())

    if missing:
        return _fail(
            check,
            "Required generated secrets are missing.",
            details={"missing_secret_keys": missing},
        )

    return _pass(check, "Required generated secrets are present.")


def check_secrets_not_default(context: SecurityGateContext) -> SecurityGateCheckResult:
    """Validate required secrets are not placeholders or default values."""
    check = SecurityGateCheck.SECRETS_NOT_DEFAULT
    default_like: list[str] = []

    for key in REQUIRED_SECRET_KEYS:
        value = context.env.get(key)

        if key == "DATABASE_URL":
            if _database_url_has_placeholder(value):
                default_like.append(key)
            continue

        if _secret_is_placeholder(value):
            default_like.append(key)

    if default_like:
        return _fail(
            check,
            "Required secrets still look like defaults or placeholders.",
            details={"default_like_secret_keys": sorted(default_like)},
        )

    return _pass(check, "Required secrets are generated values.")


def check_firewall_enabled(context: SecurityGateContext) -> SecurityGateCheckResult:
    """Validate firewall status."""
    check = SecurityGateCheck.FIREWALL_ENABLED

    if not context.policy.require_firewall_enabled:
        return _warn(check, "Firewall enforcement is disabled by policy.")

    if context.firewall_enabled:
        return _pass(check, "Firewall is enabled.")

    return _warn(check, "Firewall is not confirmed enabled.")


def check_dangerous_ports_blocked(context: SecurityGateContext) -> SecurityGateCheckResult:
    """Validate internal-only ports are not published publicly."""
    check = SecurityGateCheck.DANGEROUS_PORTS_BLOCKED
    ports = _public_ports(context)

    dangerous = sorted(
        {
            port.host_port
            for port in ports
            if port.host_port in FORBIDDEN_PUBLIC_PORTS
        }
    )

    if dangerous:
        return _fail(
            check,
            "Internal-only ports are published.",
            details={
                "forbidden_public_ports": dangerous,
                "internal_only_ports": dict(INTERNAL_ONLY_PORTS),
            },
        )

    return _pass(check, "No internal-only ports are published.")


def check_postgres_not_public(context: SecurityGateContext) -> SecurityGateCheckResult:
    """Validate PostgreSQL is not public."""
    check = SecurityGateCheck.POSTGRES_NOT_PUBLIC

    postgres_ports = [
        port.host_port
        for port in _public_ports(context)
        if port.service == DockerService.POSTGRES.value or port.host_port == INTERNAL_ONLY_PORTS[DockerService.POSTGRES.value]
    ]

    if context.postgres_public or postgres_ports:
        return _fail(
            check,
            "PostgreSQL is publicly exposed or published.",
            details={"published_ports": sorted(set(postgres_ports))},
        )

    return _pass(check, "PostgreSQL is not public.")


def check_redis_not_public(context: SecurityGateContext) -> SecurityGateCheckResult:
    """Validate Redis is not public."""
    check = SecurityGateCheck.REDIS_NOT_PUBLIC

    redis_ports = [
        port.host_port
        for port in _public_ports(context)
        if port.service == DockerService.REDIS.value or port.host_port == INTERNAL_ONLY_PORTS[DockerService.REDIS.value]
    ]

    if context.redis_public or redis_ports:
        return _fail(
            check,
            "Redis is publicly exposed or published.",
            details={"published_ports": sorted(set(redis_ports))},
        )

    return _pass(check, "Redis is not public.")


def check_docker_socket_not_mounted(context: SecurityGateContext) -> SecurityGateCheckResult:
    """Validate Docker socket is not mounted into app containers."""
    check = SecurityGateCheck.DOCKER_SOCKET_NOT_MOUNTED

    if context.policy.allow_docker_socket_mount:
        return _warn(check, "Docker socket mount is allowed by policy.")

    offenders = sorted(service.name for service in context.services if _has_forbidden_mount(service.mounts))

    if offenders:
        return _fail(
            check,
            "Docker socket mount detected.",
            details={"services": offenders},
        )

    return _pass(check, "Docker socket is not mounted into app containers.")


def check_no_privileged_containers(context: SecurityGateContext) -> SecurityGateCheckResult:
    """Validate no runtime service uses privileged containers."""
    check = SecurityGateCheck.NO_PRIVILEGED_CONTAINERS

    if context.policy.allow_privileged_containers:
        return _warn(check, "Privileged containers are allowed by policy.")

    offenders = sorted(
        service.name
        for service in context.services
        if service.privileged in FORBIDDEN_PRIVILEGED_VALUES
    )

    if offenders:
        return _fail(
            check,
            "Privileged containers detected.",
            details={"services": offenders},
        )

    return _pass(check, "No privileged containers detected.")


def check_no_host_network(context: SecurityGateContext) -> SecurityGateCheckResult:
    """Validate no service uses host networking."""
    check = SecurityGateCheck.NO_HOST_NETWORK

    if context.policy.allow_host_network:
        return _warn(check, "Host networking is allowed by policy.")

    offenders = sorted(
        service.name
        for service in context.services
        if str(service.network_mode or "").strip().lower() in FORBIDDEN_HOST_NETWORK_VALUES
    )

    if offenders:
        return _fail(
            check,
            "Host network mode detected.",
            details={"services": offenders},
        )

    return _pass(check, "No host network mode detected.")


def check_allowed_images_only(context: SecurityGateContext) -> SecurityGateCheckResult:
    """Validate service images are allowlisted or canonical."""
    check = SecurityGateCheck.ALLOWED_IMAGES_ONLY

    if context.policy.allow_unknown_images:
        return _warn(check, "Unknown images are allowed by policy.")

    allowed = set(context.allowed_images or context.policy.allowed_images or DEFAULT_ALLOWED_IMAGES)
    unknown: list[dict[str, str]] = []

    for service in context.services:
        base = _image_base_name(service.image)
        service_name = service.name

        if not base:
            unknown.append({"service": service_name, "image": ""})
            continue

        if base not in allowed and service_name not in allowed and base not in CANONICAL_DOCKER_SERVICES:
            unknown.append({"service": service_name, "image": service.image or ""})

    if unknown:
        return _fail(
            check,
            "Runtime references unknown or non-allowlisted images.",
            details={"unknown_images": unknown, "allowed_images": sorted(allowed)},
        )

    return _pass(check, "Runtime images are allowlisted.")


def check_admin_surface_private(context: SecurityGateContext) -> SecurityGateCheckResult:
    """Validate admin surface is not directly public."""
    check = SecurityGateCheck.ADMIN_SURFACE_PRIVATE

    if context.admin_surface_private:
        return _pass(check, "Admin surface is private or routed through approved entrypoint.")

    return _warn(check, "Admin surface privacy is not confirmed.")


def check_backup_configured(context: SecurityGateContext) -> SecurityGateCheckResult:
    """Validate backup configuration is present."""
    check = SecurityGateCheck.BACKUP_CONFIGURED

    if not context.policy.require_backup_configured:
        return _skipped(check, "Backup requirement disabled by policy.")

    if context.backup_configured:
        return _pass(
            check,
            "Backup is configured.",
            details={"backup_root": str(context.backup_root)},
        )

    return _warn(
        check,
        "Backup is not confirmed configured.",
        details={"backup_root": str(context.backup_root)},
    )


# ---------------------------------------------------------------------------
# Compose/runtime extraction helpers
# ---------------------------------------------------------------------------

def _extract_service_names(services: Any) -> tuple[str, ...]:
    """Extract service names from a list or mapping."""
    if isinstance(services, Mapping):
        return tuple(str(name) for name in services.keys())

    if isinstance(services, Sequence) and not isinstance(services, (str, bytes)):
        names: list[str] = []
        for item in services:
            if isinstance(item, Mapping):
                name = item.get("name") or item.get("service")
                if name:
                    names.append(str(name))
            else:
                names.append(str(item))
        return tuple(names)

    return tuple()


def parse_port_mapping(service_name: str, raw_port: Any) -> PublishedPort | None:
    """
    Parse a Docker Compose-style port entry into PublishedPort.

    Supported examples:
        "80:80"
        "127.0.0.1:8000:8000"
        {"published": 443, "target": 443, "protocol": "tcp"}
    """
    if isinstance(raw_port, Mapping):
        published = raw_port.get("published") or raw_port.get("host_port")
        target = raw_port.get("target") or raw_port.get("container_port")
        protocol = str(raw_port.get("protocol", "tcp"))
        host_ip = raw_port.get("host_ip")

        if published is None:
            return None

        return PublishedPort(
            service=service_name,
            host_port=int(published),
            container_port=int(target) if target is not None else None,
            protocol=protocol,
            host_ip=str(host_ip) if host_ip else None,
        )

    if isinstance(raw_port, int):
        return PublishedPort(service=service_name, host_port=raw_port)

    if isinstance(raw_port, str):
        port_part = raw_port.split("/", 1)[0]
        parts = port_part.split(":")

        try:
            if len(parts) == 1:
                return PublishedPort(service=service_name, host_port=int(parts[0]))
            if len(parts) == 2:
                return PublishedPort(
                    service=service_name,
                    host_port=int(parts[0]),
                    container_port=int(parts[1]),
                )
            if len(parts) == 3:
                return PublishedPort(
                    service=service_name,
                    host_ip=parts[0],
                    host_port=int(parts[1]),
                    container_port=int(parts[2]),
                )
        except ValueError:
            return None

    return None


def services_from_compose(compose: Mapping[str, Any]) -> tuple[RuntimeServicePolicy, ...]:
    """Build RuntimeServicePolicy records from a Compose-like mapping."""
    raw_services = compose.get("services", {})
    if not isinstance(raw_services, Mapping):
        return tuple()

    services: list[RuntimeServicePolicy] = []

    for service_name, spec in raw_services.items():
        if not isinstance(spec, Mapping):
            spec = {}

        ports = tuple(
            parsed
            for raw_port in spec.get("ports", ()) or ()
            if (parsed := parse_port_mapping(str(service_name), raw_port)) is not None
        )

        mounts = tuple(
            str(mount)
            for key in ("volumes", "mounts")
            for mount in (spec.get(key, ()) or ())
        )

        services.append(
            RuntimeServicePolicy(
                name=str(service_name),
                image=spec.get("image"),
                privileged=bool(spec.get("privileged", False)),
                network_mode=spec.get("network_mode"),
                mounts=mounts,
                published_ports=ports,
            )
        )

    return tuple(services)


def context_from_compose(
    *,
    instance_id: str,
    compose: Mapping[str, Any],
    manifest: Mapping[str, Any],
    env: Mapping[str, str],
    capsule_signature_verified: bool,
    image_checksums_verified: bool,
    firewall_enabled: bool,
    backup_configured: bool,
    admin_surface_private: bool = True,
    postgres_public: bool = False,
    redis_public: bool = False,
    policy: SecurityGatePolicy | None = None,
) -> SecurityGateContext:
    """Build SecurityGateContext from a Compose-like mapping."""
    services = services_from_compose(compose)
    published_ports = tuple(port for service in services for port in service.published_ports)

    return SecurityGateContext(
        instance_id=instance_id,
        manifest=manifest,
        env=env,
        services=services,
        published_ports=published_ports,
        capsule_signature_verified=capsule_signature_verified,
        image_checksums_verified=image_checksums_verified,
        firewall_enabled=firewall_enabled,
        backup_configured=backup_configured,
        admin_surface_private=admin_surface_private,
        postgres_public=postgres_public,
        redis_public=redis_public,
        policy=policy or SecurityGatePolicy.from_env(env),
    )


# ---------------------------------------------------------------------------
# Gate runner
# ---------------------------------------------------------------------------

class SecurityGate:
    """Runs all canonical Konnaxion Security Gate checks."""

    CHECKS = (
        check_capsule_signature,
        check_image_checksums,
        check_manifest_schema,
        check_secrets_present,
        check_secrets_not_default,
        check_firewall_enabled,
        check_dangerous_ports_blocked,
        check_postgres_not_public,
        check_redis_not_public,
        check_docker_socket_not_mounted,
        check_no_privileged_containers,
        check_no_host_network,
        check_allowed_images_only,
        check_admin_surface_private,
        check_backup_configured,
    )

    def run(self, context: SecurityGateContext) -> SecurityGateSummary:
        """Run all canonical checks and return an aggregate summary."""
        results = tuple(check(context) for check in self.CHECKS)
        summary = SecurityGateSummary(
            status=SecurityGateStatus.UNKNOWN,
            checks=results,
            checked_at=_utc_now(),
        )
        return summary.with_derived_status()

    def assert_start_allowed(self, context: SecurityGateContext) -> SecurityGateSummary:
        """
        Run the Security Gate and raise SecurityGateBlocked if startup is blocked.
        """
        summary = self.run(context)
        if summary.status == SecurityGateStatus.FAIL_BLOCKING:
            raise SecurityGateBlocked(summary)
        return summary


class SecurityGateBlocked(RuntimeError):
    """Raised when the Security Gate blocks instance startup."""

    def __init__(self, summary: SecurityGateSummary) -> None:
        self.summary = summary
        failures = ", ".join(check.check.value for check in summary.blocking_failures)
        super().__init__(f"Konnaxion Security Gate blocked startup: {failures}")


def run_security_gate(context: SecurityGateContext) -> SecurityGateSummary:
    """Convenience wrapper for running the canonical Security Gate."""
    return SecurityGate().run(context)


def assert_security_gate_allows_start(context: SecurityGateContext) -> SecurityGateSummary:
    """Convenience wrapper that raises when startup must be blocked."""
    return SecurityGate().assert_start_allowed(context)


__all__ = [
    "DEFAULT_ALLOWED_IMAGES",
    "FORBIDDEN_HOST_NETWORK_VALUES",
    "FORBIDDEN_MOUNT_PATHS",
    "FORBIDDEN_PRIVILEGED_VALUES",
    "REQUIRED_MANIFEST_FIELDS",
    "REQUIRED_SECRET_KEYS",
    "SECRET_PLACEHOLDER_SUBSTRINGS",
    "SECRET_PLACEHOLDER_VALUES",
    "PublishedPort",
    "RuntimeServicePolicy",
    "SecurityGate",
    "SecurityGateBlocked",
    "SecurityGateContext",
    "SecurityGatePolicy",
    "assert_security_gate_allows_start",
    "check_admin_surface_private",
    "check_allowed_images_only",
    "check_backup_configured",
    "check_capsule_signature",
    "check_dangerous_ports_blocked",
    "check_docker_socket_not_mounted",
    "check_firewall_enabled",
    "check_image_checksums",
    "check_manifest_schema",
    "check_no_host_network",
    "check_no_privileged_containers",
    "check_postgres_not_public",
    "check_redis_not_public",
    "check_secrets_not_default",
    "check_secrets_present",
    "context_from_compose",
    "parse_port_mapping",
    "run_security_gate",
    "services_from_compose",
]
