"""
Konnaxion Agent security policy engine.

Responsibilities:
- Define the deny-by-default runtime policy used by Security Gate checks.
- Validate Docker Compose service definitions before startup.
- Reject public exposure of internal ports.
- Reject privileged containers, host networking, and Docker socket mounts.
- Validate canonical service names and image allowlists.
- Validate network profile / exposure mode compatibility.
- Validate KX_* runtime environment policy.

This module is pure policy logic:
- It does not mutate files.
- It does not start containers.
- It does not apply firewall rules.
- It does not import or verify capsules directly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum, StrEnum
from typing import Any, Iterable, Mapping, Sequence

try:
    from kx_shared.konnaxion_constants import (
        ALLOWED_ENTRY_PORTS,
        BLOCKING_SECURITY_CHECKS,
        CANONICAL_DOCKER_SERVICES,
        DEFAULT_EXPOSURE_MODE,
        DEFAULT_NETWORK_PROFILE,
        DockerService,
        ExposureMode,
        FORBIDDEN_PUBLIC_PORTS,
        KX_ENV_DEFAULTS,
        NetworkProfile,
        SecurityGateCheck,
        SecurityGateStatus,
    )
except ImportError:  # pragma: no cover - early scaffold fallback
    class DockerService(StrEnum):
        TRAEFIK = "traefik"
        FRONTEND_NEXT = "frontend-next"
        DJANGO_API = "django-api"
        POSTGRES = "postgres"
        REDIS = "redis"
        CELERYWORKER = "celeryworker"
        CELERYBEAT = "celerybeat"
        FLOWER = "flower"
        MEDIA_NGINX = "media-nginx"
        KX_AGENT = "kx-agent"

    class NetworkProfile(StrEnum):
        LOCAL_ONLY = "local_only"
        INTRANET_PRIVATE = "intranet_private"
        PRIVATE_TUNNEL = "private_tunnel"
        PUBLIC_TEMPORARY = "public_temporary"
        PUBLIC_VPS = "public_vps"
        OFFLINE = "offline"

    class ExposureMode(StrEnum):
        PRIVATE = "private"
        LAN = "lan"
        VPN = "vpn"
        TEMPORARY_TUNNEL = "temporary_tunnel"
        PUBLIC = "public"

    class SecurityGateStatus(StrEnum):
        PASS = "PASS"
        WARN = "WARN"
        FAIL_BLOCKING = "FAIL_BLOCKING"
        SKIPPED = "SKIPPED"
        UNKNOWN = "UNKNOWN"

    class SecurityGateCheck(StrEnum):
        CAPSULE_SIGNATURE = "capsule_signature"
        IMAGE_CHECKSUMS = "image_checksums"
        MANIFEST_SCHEMA = "manifest_schema"
        SECRETS_PRESENT = "secrets_present"
        SECRETS_NOT_DEFAULT = "secrets_not_default"
        FIREWALL_ENABLED = "firewall_enabled"
        DANGEROUS_PORTS_BLOCKED = "dangerous_ports_blocked"
        POSTGRES_NOT_PUBLIC = "postgres_not_public"
        REDIS_NOT_PUBLIC = "redis_not_public"
        DOCKER_SOCKET_NOT_MOUNTED = "docker_socket_not_mounted"
        NO_PRIVILEGED_CONTAINERS = "no_privileged_containers"
        NO_HOST_NETWORK = "no_host_network"
        ALLOWED_IMAGES_ONLY = "allowed_images_only"
        ADMIN_SURFACE_PRIVATE = "admin_surface_private"
        BACKUP_CONFIGURED = "backup_configured"

    ALLOWED_ENTRY_PORTS = {"https": 443, "http_redirect": 80, "ssh_admin_restricted": 22}
    FORBIDDEN_PUBLIC_PORTS = frozenset({3000, 5000, 5432, 6379, 5555, 8000})
    CANONICAL_DOCKER_SERVICES = tuple(service.value for service in DockerService)
    BLOCKING_SECURITY_CHECKS = frozenset(
        {
            SecurityGateCheck.CAPSULE_SIGNATURE,
            SecurityGateCheck.IMAGE_CHECKSUMS,
            SecurityGateCheck.MANIFEST_SCHEMA,
            SecurityGateCheck.SECRETS_PRESENT,
            SecurityGateCheck.SECRETS_NOT_DEFAULT,
            SecurityGateCheck.DANGEROUS_PORTS_BLOCKED,
            SecurityGateCheck.POSTGRES_NOT_PUBLIC,
            SecurityGateCheck.REDIS_NOT_PUBLIC,
            SecurityGateCheck.DOCKER_SOCKET_NOT_MOUNTED,
            SecurityGateCheck.NO_PRIVILEGED_CONTAINERS,
            SecurityGateCheck.NO_HOST_NETWORK,
            SecurityGateCheck.ALLOWED_IMAGES_ONLY,
        }
    )
    KX_ENV_DEFAULTS = {
        "KX_REQUIRE_SIGNED_CAPSULE": "true",
        "KX_GENERATE_SECRETS_ON_INSTALL": "true",
        "KX_ALLOW_UNKNOWN_IMAGES": "false",
        "KX_ALLOW_PRIVILEGED_CONTAINERS": "false",
        "KX_ALLOW_DOCKER_SOCKET_MOUNT": "false",
        "KX_ALLOW_HOST_NETWORK": "false",
        "KX_BACKUP_ENABLED": "true",
    }
    DEFAULT_NETWORK_PROFILE = NetworkProfile.INTRANET_PRIVATE
    DEFAULT_EXPOSURE_MODE = ExposureMode.PRIVATE


class PolicyError(RuntimeError):
    """Raised when a policy object or validation input is invalid."""


class PolicySeverity(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class PolicyFinding:
    """Single policy finding produced by a validator."""

    check: str
    status: str
    severity: str
    message: str
    service: str | None = None
    field: str | None = None
    value: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyReport:
    """Aggregate result for a policy validation run."""

    accepted: bool
    status: str
    findings: tuple[PolicyFinding, ...] = field(default_factory=tuple)

    @property
    def blocking_findings(self) -> tuple[PolicyFinding, ...]:
        return tuple(
            finding
            for finding in self.findings
            if finding.severity == PolicySeverity.BLOCK.value
        )

    @property
    def warnings(self) -> tuple[PolicyFinding, ...]:
        return tuple(
            finding
            for finding in self.findings
            if finding.severity == PolicySeverity.WARN.value
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "status": self.status,
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class RuntimeSecurityPolicy:
    """
    Canonical deny-by-default runtime policy.

    The defaults match Konnaxion's intended posture:
    - signed capsules only
    - generated secrets on install
    - no unknown images unless explicitly allowlisted
    - no privileged containers
    - no Docker socket mount
    - no host networking
    - no public internal ports
    - backups enabled
    """

    require_signed_capsule: bool = True
    generate_secrets_on_install: bool = True
    allow_unknown_images: bool = False
    allow_privileged_containers: bool = False
    allow_docker_socket_mount: bool = False
    allow_host_network: bool = False
    backup_required: bool = True
    admin_surface_private: bool = True
    allowed_images: tuple[str, ...] = field(default_factory=tuple)
    allowed_entry_ports: tuple[int, ...] = (
        int(ALLOWED_ENTRY_PORTS["http_redirect"]),
        int(ALLOWED_ENTRY_PORTS["https"]),
    )
    forbidden_public_ports: tuple[int, ...] = tuple(
        sorted(int(port) for port in FORBIDDEN_PUBLIC_PORTS)
    )
    canonical_services: tuple[str, ...] = tuple(CANONICAL_DOCKER_SERVICES)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RuntimeSecurityPolicy":
        """Build policy from KX_* environment values."""

        merged = dict(KX_ENV_DEFAULTS)
        if env:
            merged.update({key: str(value) for key, value in env.items()})

        return cls(
            require_signed_capsule=parse_bool(
                merged.get("KX_REQUIRE_SIGNED_CAPSULE"),
                default=True,
                field_name="KX_REQUIRE_SIGNED_CAPSULE",
            ),
            generate_secrets_on_install=parse_bool(
                merged.get("KX_GENERATE_SECRETS_ON_INSTALL"),
                default=True,
                field_name="KX_GENERATE_SECRETS_ON_INSTALL",
            ),
            allow_unknown_images=parse_bool(
                merged.get("KX_ALLOW_UNKNOWN_IMAGES"),
                default=False,
                field_name="KX_ALLOW_UNKNOWN_IMAGES",
            ),
            allow_privileged_containers=parse_bool(
                merged.get("KX_ALLOW_PRIVILEGED_CONTAINERS"),
                default=False,
                field_name="KX_ALLOW_PRIVILEGED_CONTAINERS",
            ),
            allow_docker_socket_mount=parse_bool(
                merged.get("KX_ALLOW_DOCKER_SOCKET_MOUNT"),
                default=False,
                field_name="KX_ALLOW_DOCKER_SOCKET_MOUNT",
            ),
            allow_host_network=parse_bool(
                merged.get("KX_ALLOW_HOST_NETWORK"),
                default=False,
                field_name="KX_ALLOW_HOST_NETWORK",
            ),
            backup_required=parse_bool(
                merged.get("KX_BACKUP_ENABLED"),
                default=True,
                field_name="KX_BACKUP_ENABLED",
            ),
        )


FORBIDDEN_SERVICE_ALIASES = frozenset(
    {
        "backend",
        "api",
        "web",
        "next",
        "frontend",
        "db",
        "database",
        "cache",
        "worker",
        "scheduler",
        "media",
        "agent",
    }
)

PROFILE_EXPOSURE_COMPATIBILITY: Mapping[str, frozenset[str]] = {
    NetworkProfile.LOCAL_ONLY.value: frozenset({ExposureMode.PRIVATE.value}),
    NetworkProfile.INTRANET_PRIVATE.value: frozenset(
        {ExposureMode.PRIVATE.value, ExposureMode.LAN.value}
    ),
    NetworkProfile.PRIVATE_TUNNEL.value: frozenset(
        {ExposureMode.PRIVATE.value, ExposureMode.VPN.value}
    ),
    NetworkProfile.PUBLIC_TEMPORARY.value: frozenset({ExposureMode.TEMPORARY_TUNNEL.value}),
    NetworkProfile.PUBLIC_VPS.value: frozenset({ExposureMode.PUBLIC.value}),
    NetworkProfile.OFFLINE.value: frozenset({ExposureMode.PRIVATE.value}),
}

PUBLIC_PROFILES = frozenset(
    {
        NetworkProfile.PUBLIC_TEMPORARY.value,
        NetworkProfile.PUBLIC_VPS.value,
    }
)

INTERNAL_ONLY_SERVICES = frozenset(
    {
        DockerService.FRONTEND_NEXT.value,
        DockerService.DJANGO_API.value,
        DockerService.POSTGRES.value,
        DockerService.REDIS.value,
        DockerService.CELERYWORKER.value,
        DockerService.CELERYBEAT.value,
        DockerService.FLOWER.value,
        DockerService.MEDIA_NGINX.value,
    }
)


def enum_value(value: Any) -> str:
    """Return enum .value when available, otherwise stable string."""

    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def parse_bool(value: Any, *, default: bool, field_name: str = "value") -> bool:
    """Parse common boolean environment string values."""

    if value is None:
        return default

    if isinstance(value, bool):
        return value

    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", ""}:
        return False

    raise PolicyError(f"{field_name} must be boolean-like; got {value!r}")


def make_report(findings: Iterable[PolicyFinding]) -> PolicyReport:
    """Create an aggregate report from findings."""

    collected = tuple(findings)
    accepted = not any(finding.severity == PolicySeverity.BLOCK.value for finding in collected)

    if not accepted:
        status = SecurityGateStatus.FAIL_BLOCKING.value
    elif any(finding.severity == PolicySeverity.WARN.value for finding in collected):
        status = SecurityGateStatus.WARN.value
    else:
        status = SecurityGateStatus.PASS.value

    return PolicyReport(accepted=accepted, status=status, findings=collected)


def finding(
    check: SecurityGateCheck | str,
    message: str,
    *,
    severity: PolicySeverity = PolicySeverity.BLOCK,
    service: str | None = None,
    field: str | None = None,
    value: Any | None = None,
    status: SecurityGateStatus | str | None = None,
) -> PolicyFinding:
    """Create a normalized policy finding."""

    sev = enum_value(severity)
    default_status = (
        SecurityGateStatus.FAIL_BLOCKING.value
        if sev == PolicySeverity.BLOCK.value
        else SecurityGateStatus.WARN.value
        if sev == PolicySeverity.WARN.value
        else SecurityGateStatus.PASS.value
    )
    return PolicyFinding(
        check=enum_value(check),
        status=enum_value(status) if status is not None else default_status,
        severity=sev,
        message=message,
        service=service,
        field=field,
        value=value,
    )


def parse_compose_port(port: Any) -> tuple[int | None, int | None]:
    """
    Parse Compose port mapping into (published, target).

    Supports:
        "443:443"
        "127.0.0.1:443:443"
        {"published": 443, "target": 443}
        {"mode": "host", "published": "443", "target": "443"}
    """

    if isinstance(port, Mapping):
        published = port.get("published")
        target = port.get("target")
        return (
            int(published) if published is not None else None,
            int(target) if target is not None else None,
        )

    text = str(port).strip()
    parts = text.split(":")

    try:
        if len(parts) == 1:
            value = int(parts[0])
            return value, value
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
        if len(parts) == 3:
            return int(parts[1]), int(parts[2])
    except ValueError as exc:
        raise PolicyError(f"invalid Compose port mapping: {port!r}") from exc

    raise PolicyError(f"unsupported Compose port mapping: {port!r}")


def validate_network_exposure_policy(
    *,
    network_profile: str = enum_value(DEFAULT_NETWORK_PROFILE),
    exposure_mode: str = enum_value(DEFAULT_EXPOSURE_MODE),
    public_mode_enabled: bool = False,
    public_mode_expires_at: str | None = None,
) -> PolicyReport:
    """Validate network profile and exposure mode compatibility."""

    profile = enum_value(network_profile)
    exposure = enum_value(exposure_mode)
    findings: list[PolicyFinding] = []

    if profile not in PROFILE_EXPOSURE_COMPATIBILITY:
        findings.append(
            finding(
                SecurityGateCheck.ADMIN_SURFACE_PRIVATE,
                f"unknown network profile: {profile}",
                field="network_profile",
                value=profile,
            )
        )
        return make_report(findings)

    allowed_exposures = PROFILE_EXPOSURE_COMPATIBILITY[profile]
    if exposure not in allowed_exposures:
        findings.append(
            finding(
                SecurityGateCheck.ADMIN_SURFACE_PRIVATE,
                f"exposure mode {exposure!r} is not allowed for profile {profile!r}",
                field="exposure_mode",
                value=exposure,
            )
        )

    if public_mode_enabled and profile not in PUBLIC_PROFILES:
        findings.append(
            finding(
                SecurityGateCheck.ADMIN_SURFACE_PRIVATE,
                "public mode may only be enabled for public_temporary or public_vps profiles",
                field="public_mode_enabled",
                value=public_mode_enabled,
            )
        )

    if (
        public_mode_enabled
        and not public_mode_expires_at
        and profile == NetworkProfile.PUBLIC_TEMPORARY.value
    ):
        findings.append(
            finding(
                SecurityGateCheck.ADMIN_SURFACE_PRIVATE,
                "public_temporary mode requires KX_PUBLIC_MODE_EXPIRES_AT",
                field="public_mode_expires_at",
                value=public_mode_expires_at,
            )
        )

    if (
        profile == NetworkProfile.PUBLIC_TEMPORARY.value
        and exposure != ExposureMode.TEMPORARY_TUNNEL.value
    ):
        findings.append(
            finding(
                SecurityGateCheck.ADMIN_SURFACE_PRIVATE,
                "public_temporary profile must use temporary_tunnel exposure",
                field="exposure_mode",
                value=exposure,
            )
        )

    if profile != NetworkProfile.PUBLIC_VPS.value and exposure == ExposureMode.PUBLIC.value:
        findings.append(
            finding(
                SecurityGateCheck.ADMIN_SURFACE_PRIVATE,
                "permanent public exposure is allowed only for public_vps profile",
                field="exposure_mode",
                value=exposure,
            )
        )

    return make_report(findings)


def validate_env_policy(
    env: Mapping[str, Any],
    policy: RuntimeSecurityPolicy | None = None,
) -> PolicyReport:
    """
    Validate KX_* runtime security variables.

    Non-KX variables are allowed because Django/Postgres/Redis/Frontend env files
    use their own canonical prefixes. This function only validates KX security
    posture when those keys are present.
    """

    policy = policy or RuntimeSecurityPolicy.from_env(env)
    findings: list[PolicyFinding] = []

    unsafe_bools = {
        "KX_REQUIRE_SIGNED_CAPSULE": policy.require_signed_capsule,
        "KX_GENERATE_SECRETS_ON_INSTALL": policy.generate_secrets_on_install,
        "KX_BACKUP_ENABLED": policy.backup_required,
    }

    for key, enabled in unsafe_bools.items():
        if not enabled:
            check = (
                SecurityGateCheck.CAPSULE_SIGNATURE
                if key == "KX_REQUIRE_SIGNED_CAPSULE"
                else SecurityGateCheck.SECRETS_PRESENT
                if key == "KX_GENERATE_SECRETS_ON_INSTALL"
                else SecurityGateCheck.BACKUP_CONFIGURED
            )
            findings.append(
                finding(
                    check,
                    f"{key} must remain enabled for default runtime policy",
                    field=key,
                    value=env.get(key),
                )
            )

    forbidden_allow_flags = {
        "KX_ALLOW_UNKNOWN_IMAGES": policy.allow_unknown_images,
        "KX_ALLOW_PRIVILEGED_CONTAINERS": policy.allow_privileged_containers,
        "KX_ALLOW_DOCKER_SOCKET_MOUNT": policy.allow_docker_socket_mount,
        "KX_ALLOW_HOST_NETWORK": policy.allow_host_network,
    }

    for key, enabled in forbidden_allow_flags.items():
        if enabled:
            check = {
                "KX_ALLOW_UNKNOWN_IMAGES": SecurityGateCheck.ALLOWED_IMAGES_ONLY,
                "KX_ALLOW_PRIVILEGED_CONTAINERS": SecurityGateCheck.NO_PRIVILEGED_CONTAINERS,
                "KX_ALLOW_DOCKER_SOCKET_MOUNT": SecurityGateCheck.DOCKER_SOCKET_NOT_MOUNTED,
                "KX_ALLOW_HOST_NETWORK": SecurityGateCheck.NO_HOST_NETWORK,
            }[key]
            findings.append(
                finding(
                    check,
                    f"{key}=true weakens the deny-by-default policy",
                    field=key,
                    value=env.get(key),
                )
            )

    public_mode_enabled = parse_bool(
        env.get("KX_PUBLIC_MODE_ENABLED"),
        default=False,
        field_name="KX_PUBLIC_MODE_ENABLED",
    )
    network_report = validate_network_exposure_policy(
        network_profile=str(
            env.get("KX_NETWORK_PROFILE", enum_value(DEFAULT_NETWORK_PROFILE))
        ),
        exposure_mode=str(env.get("KX_EXPOSURE_MODE", enum_value(DEFAULT_EXPOSURE_MODE))),
        public_mode_enabled=public_mode_enabled,
        public_mode_expires_at=empty_to_none(env.get("KX_PUBLIC_MODE_EXPIRES_AT")),
    )
    findings.extend(network_report.findings)

    return make_report(findings)


def empty_to_none(value: Any) -> str | None:
    """Return None for empty strings and None-like values."""

    if value is None:
        return None

    text = str(value).strip()
    return text or None


def validate_required_services(
    services: Mapping[str, Any],
    policy: RuntimeSecurityPolicy,
) -> list[PolicyFinding]:
    """Validate canonical required service names for a full runtime Compose file."""

    findings: list[PolicyFinding] = []
    service_names = set(services.keys())
    canonical_names = set(policy.canonical_services)

    aliases = service_names & FORBIDDEN_SERVICE_ALIASES
    if aliases:
        findings.append(
            finding(
                SecurityGateCheck.MANIFEST_SCHEMA,
                f"forbidden non-canonical service aliases found: {sorted(aliases)}",
                field="services",
                value=sorted(aliases),
            )
        )

    unknown = service_names - canonical_names
    if unknown:
        findings.append(
            finding(
                SecurityGateCheck.MANIFEST_SCHEMA,
                f"unknown non-canonical service names found: {sorted(unknown)}",
                field="services",
                value=sorted(unknown),
            )
        )

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
    missing = required - service_names
    if missing:
        findings.append(
            finding(
                SecurityGateCheck.MANIFEST_SCHEMA,
                f"missing required runtime services: {sorted(missing)}",
                field="services",
                value=sorted(missing),
            )
        )

    return findings


def validate_service_runtime_policy(
    service_name: str,
    service: Mapping[str, Any],
    policy: RuntimeSecurityPolicy,
) -> list[PolicyFinding]:
    """Validate one Compose service against Konnaxion runtime policy."""

    findings: list[PolicyFinding] = []

    if service.get("privileged") is True and not policy.allow_privileged_containers:
        findings.append(
            finding(
                SecurityGateCheck.NO_PRIVILEGED_CONTAINERS,
                "privileged containers are forbidden",
                service=service_name,
                field="privileged",
                value=True,
            )
        )

    if service.get("network_mode") == "host" and not policy.allow_host_network:
        findings.append(
            finding(
                SecurityGateCheck.NO_HOST_NETWORK,
                "host networking is forbidden",
                service=service_name,
                field="network_mode",
                value="host",
            )
        )

    if service.get("pid") == "host":
        findings.append(
            finding(
                SecurityGateCheck.NO_HOST_NETWORK,
                "host PID namespace is forbidden",
                service=service_name,
                field="pid",
                value="host",
            )
        )

    if service.get("ipc") == "host":
        findings.append(
            finding(
                SecurityGateCheck.NO_HOST_NETWORK,
                "host IPC namespace is forbidden",
                service=service_name,
                field="ipc",
                value="host",
            )
        )

    for volume in service.get("volumes", []) or []:
        volume_text = str(volume)
        if "/var/run/docker.sock" in volume_text and not policy.allow_docker_socket_mount:
            findings.append(
                finding(
                    SecurityGateCheck.DOCKER_SOCKET_NOT_MOUNTED,
                    "Docker socket must never be mounted into app containers",
                    service=service_name,
                    field="volumes",
                    value=volume_text,
                )
            )

    service_ports = service.get("ports", []) or []
    if service_name != DockerService.TRAEFIK.value and service_ports:
        findings.append(
            finding(
                SecurityGateCheck.DANGEROUS_PORTS_BLOCKED,
                "only traefik may publish host ports",
                service=service_name,
                field="ports",
                value=service_ports,
            )
        )

    for port in service_ports:
        published, target = parse_compose_port(port)

        exposed_values = {value for value in (published, target) if value is not None}
        forbidden = exposed_values & set(policy.forbidden_public_ports)
        if forbidden:
            findings.append(
                finding(
                    SecurityGateCheck.DANGEROUS_PORTS_BLOCKED,
                    f"forbidden public port(s): {sorted(forbidden)}",
                    service=service_name,
                    field="ports",
                    value=port,
                )
            )

        if service_name == DockerService.POSTGRES.value and exposed_values:
            findings.append(
                finding(
                    SecurityGateCheck.POSTGRES_NOT_PUBLIC,
                    "PostgreSQL must never publish host ports",
                    service=service_name,
                    field="ports",
                    value=port,
                )
            )

        if service_name == DockerService.REDIS.value and exposed_values:
            findings.append(
                finding(
                    SecurityGateCheck.REDIS_NOT_PUBLIC,
                    "Redis must never publish host ports",
                    service=service_name,
                    field="ports",
                    value=port,
                )
            )

        if service_name == DockerService.TRAEFIK.value:
            if target is not None and target not in set(policy.allowed_entry_ports):
                findings.append(
                    finding(
                        SecurityGateCheck.DANGEROUS_PORTS_BLOCKED,
                        "traefik may only expose canonical entry ports 80/443",
                        service=service_name,
                        field="ports",
                        value=port,
                    )
                )

    image = service.get("image")
    if image and not policy.allow_unknown_images and policy.allowed_images:
        if not image_allowed(str(image), policy.allowed_images):
            findings.append(
                finding(
                    SecurityGateCheck.ALLOWED_IMAGES_ONLY,
                    "image is not in the allowed image policy",
                    service=service_name,
                    field="image",
                    value=image,
                )
            )

    if service_name in {DockerService.POSTGRES.value, DockerService.REDIS.value}:
        networks = normalize_list(service.get("networks"))
        if any(network in {"kx-public", "public", "default"} for network in networks):
            check = (
                SecurityGateCheck.POSTGRES_NOT_PUBLIC
                if service_name == DockerService.POSTGRES.value
                else SecurityGateCheck.REDIS_NOT_PUBLIC
            )
            findings.append(
                finding(
                    check,
                    f"{service_name} must not attach to a public/default network",
                    service=service_name,
                    field="networks",
                    value=networks,
                )
            )

    return findings


def image_allowed(image: str, allowed_images: Sequence[str]) -> bool:
    """
    Return True when an image matches allowed image policy.

    Supports exact matches and prefix wildcards ending with '*':
        konnaxion/*
        postgres:16-alpine
    """

    for allowed in allowed_images:
        if allowed.endswith("*") and image.startswith(allowed[:-1]):
            return True
        if image == allowed:
            return True

    return False


def normalize_list(value: Any) -> list[str]:
    """Normalize Compose scalar/list/mapping values into a list of strings."""

    if value is None:
        return []
    if isinstance(value, Mapping):
        return [str(key) for key in value.keys()]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def validate_runtime_policy(
    runtime: Mapping[str, Any],
    policy: RuntimeSecurityPolicy | None = None,
    *,
    require_complete_compose: bool = False,
) -> PolicyReport:
    """
    Validate runtime policy and raise on blocking findings.

    This is the public compatibility API expected by tests and other modules.
    It accepts a Compose-like mapping:

        {"services": {"django-api": {"privileged": True}}}

    By default, partial service maps are allowed so unit tests and targeted
    policy checks can validate one service at a time. Set
    `require_complete_compose=True` to require the complete canonical runtime
    service set.
    """

    policy = policy or RuntimeSecurityPolicy()

    services = runtime.get("services")
    if not isinstance(services, Mapping):
        report = make_report(
            [
                finding(
                    SecurityGateCheck.MANIFEST_SCHEMA,
                    "runtime policy input must contain a services mapping",
                    field="services",
                    value=services,
                )
            ]
        )
        assert_policy_accepts(report)
        return report

    findings: list[PolicyFinding] = []

    if require_complete_compose:
        findings.extend(validate_required_services(services, policy))
    else:
        service_names = set(str(name) for name in services.keys())
        aliases = service_names & FORBIDDEN_SERVICE_ALIASES
        if aliases:
            findings.append(
                finding(
                    SecurityGateCheck.MANIFEST_SCHEMA,
                    f"forbidden non-canonical service aliases found: {sorted(aliases)}",
                    field="services",
                    value=sorted(aliases),
                )
            )

    for service_name, service in services.items():
        if not isinstance(service, Mapping):
            findings.append(
                finding(
                    SecurityGateCheck.MANIFEST_SCHEMA,
                    "service definition must be a mapping",
                    service=str(service_name),
                    field="services",
                    value=service,
                )
            )
            continue

        findings.extend(
            validate_service_runtime_policy(
                str(service_name),
                service,
                policy,
            )
        )

    env = runtime.get("env") or runtime.get("environment")
    if isinstance(env, Mapping):
        findings.extend(validate_env_policy(env, policy).findings)

    networks = runtime.get("networks", {})
    if isinstance(networks, Mapping):
        for network_name in ("kx-private", "kx-data"):
            network_spec = networks.get(network_name)
            if isinstance(network_spec, Mapping) and network_spec.get("internal") is not True:
                findings.append(
                    finding(
                        SecurityGateCheck.DANGEROUS_PORTS_BLOCKED,
                        f"{network_name} must be internal",
                        field=f"networks.{network_name}.internal",
                        value=network_spec.get("internal"),
                    )
                )

    report = make_report(findings)
    assert_policy_accepts(report)
    return report


def validate_compose_policy(
    compose: Mapping[str, Any],
    policy: RuntimeSecurityPolicy | None = None,
) -> PolicyReport:
    """
    Validate a complete Docker Compose mapping against Konnaxion security policy.
    """

    policy = policy or RuntimeSecurityPolicy()

    services = compose.get("services")
    if not isinstance(services, Mapping):
        return make_report(
            [
                finding(
                    SecurityGateCheck.MANIFEST_SCHEMA,
                    "Compose spec must contain a services mapping",
                    field="services",
                    value=services,
                )
            ]
        )

    findings: list[PolicyFinding] = []
    findings.extend(validate_required_services(services, policy))

    for service_name, service in services.items():
        if not isinstance(service, Mapping):
            findings.append(
                finding(
                    SecurityGateCheck.MANIFEST_SCHEMA,
                    "service definition must be a mapping",
                    service=str(service_name),
                    field="services",
                    value=service,
                )
            )
            continue

        findings.extend(validate_service_runtime_policy(str(service_name), service, policy))

    networks = compose.get("networks", {})
    if isinstance(networks, Mapping):
        for network_name in ("kx-private", "kx-data"):
            network_spec = networks.get(network_name)
            if isinstance(network_spec, Mapping) and network_spec.get("internal") is not True:
                findings.append(
                    finding(
                        SecurityGateCheck.DANGEROUS_PORTS_BLOCKED,
                        f"{network_name} must be internal",
                        field=f"networks.{network_name}.internal",
                        value=network_spec.get("internal"),
                    )
                )

    return make_report(findings)


def validate_capsule_acceptance_policy(
    *,
    signed: bool,
    checksums_valid: bool,
    manifest_valid: bool,
    policy: RuntimeSecurityPolicy | None = None,
) -> PolicyReport:
    """Validate high-level capsule acceptance policy."""

    policy = policy or RuntimeSecurityPolicy()
    findings: list[PolicyFinding] = []

    if policy.require_signed_capsule and not signed:
        findings.append(
            finding(
                SecurityGateCheck.CAPSULE_SIGNATURE,
                "capsule signature is required",
                field="signed",
                value=signed,
            )
        )

    if not checksums_valid:
        findings.append(
            finding(
                SecurityGateCheck.IMAGE_CHECKSUMS,
                "capsule image/content checksums are invalid",
                field="checksums_valid",
                value=checksums_valid,
            )
        )

    if not manifest_valid:
        findings.append(
            finding(
                SecurityGateCheck.MANIFEST_SCHEMA,
                "capsule manifest schema is invalid",
                field="manifest_valid",
                value=manifest_valid,
            )
        )

    return make_report(findings)


def merge_reports(*reports: PolicyReport) -> PolicyReport:
    """Merge multiple policy reports into one aggregate report."""

    findings: list[PolicyFinding] = []
    for report in reports:
        findings.extend(report.findings)
    return make_report(findings)


def report_to_security_gate_checks(report: PolicyReport) -> dict[str, str]:
    """
    Convert a PolicyReport to Security Gate check status mapping.

    Checks not present in the report are omitted; the Security Gate aggregator
    can merge this with concrete check results from verifier/firewall/secrets.
    """

    statuses: dict[str, str] = {}
    for item in report.findings:
        current = statuses.get(item.check)
        if current == SecurityGateStatus.FAIL_BLOCKING.value:
            continue
        statuses[item.check] = item.status
    return statuses


def assert_policy_accepts(report: PolicyReport) -> None:
    """Raise PolicyError if a report contains blocking findings."""

    if not report.accepted:
        messages = "; ".join(finding.message for finding in report.blocking_findings)
        raise PolicyError(messages or "security policy rejected the input")


__all__ = [
    "FORBIDDEN_SERVICE_ALIASES",
    "INTERNAL_ONLY_SERVICES",
    "PROFILE_EXPOSURE_COMPATIBILITY",
    "PUBLIC_PROFILES",
    "PolicyError",
    "PolicyFinding",
    "PolicyReport",
    "PolicySeverity",
    "RuntimeSecurityPolicy",
    "assert_policy_accepts",
    "empty_to_none",
    "enum_value",
    "finding",
    "image_allowed",
    "make_report",
    "merge_reports",
    "normalize_list",
    "parse_bool",
    "parse_compose_port",
    "report_to_security_gate_checks",
    "validate_capsule_acceptance_policy",
    "validate_compose_policy",
    "validate_env_policy",
    "validate_network_exposure_policy",
    "validate_required_services",
    "validate_runtime_policy",
    "validate_service_runtime_policy",
]