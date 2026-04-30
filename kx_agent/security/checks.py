"""
Reusable Security Gate checks for Konnaxion Agent.

This module contains pure validation primitives used by kx_agent.security.gate.
The checks avoid side effects where possible and return structured results
instead of raising, so the caller can aggregate PASS/WARN/FAIL_BLOCKING states.

Canonical Security Gate checks:

- capsule_signature
- image_checksums
- manifest_schema
- secrets_present
- secrets_not_default
- firewall_enabled
- dangerous_ports_blocked
- postgres_not_public
- redis_not_public
- docker_socket_not_mounted
- no_privileged_containers
- no_host_network
- allowed_images_only
- admin_surface_private
- backup_configured
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from kx_shared.konnaxion_constants import (
    BLOCKING_SECURITY_CHECKS,
    DockerService,
    FORBIDDEN_PUBLIC_PORTS,
    SecurityGateCheck,
    SecurityGateStatus,
)

try:
    from kx_agent.instances.secrets import (
        DJANGO_SECRET_KEY,
        POSTGRES_PASSWORD,
        is_placeholder_secret,
    )
except Exception:  # pragma: no cover - allows isolated file-level tests
    DJANGO_SECRET_KEY = "DJANGO_SECRET_KEY"
    POSTGRES_PASSWORD = "POSTGRES_PASSWORD"

    def is_placeholder_secret(value: str | None) -> bool:
        return value is None or value.strip().lower() in {
            "",
            "change-me",
            "changeme",
            "replace-me",
            "replaceme",
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


# ---------------------------------------------------------------------
# Result DTOs
# ---------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class SecurityCheckResult:
    """One Security Gate check result."""

    check: SecurityGateCheck
    status: SecurityGateStatus
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)
    blocking: bool = False

    @property
    def passed(self) -> bool:
        return self.status == SecurityGateStatus.PASS

    @property
    def failed_blocking(self) -> bool:
        return self.status == SecurityGateStatus.FAIL_BLOCKING

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check.value,
            "status": self.status.value,
            "message": self.message,
            "details": dict(self.details),
            "blocking": self.blocking,
        }


@dataclass(slots=True, frozen=True)
class SecurityCheckContext:
    """Input context used by the Security Gate.

    All fields are optional so individual checks can be tested independently.
    Missing data usually returns UNKNOWN unless the check can safely fail closed.
    """

    capsule_signature_valid: bool | None = None
    capsule_signature_required: bool = True

    image_checksums_valid: bool | None = None
    manifest_schema_valid: bool | None = None

    env: Mapping[str, str] = field(default_factory=dict)
    required_secret_keys: Sequence[str] = field(
        default_factory=lambda: (DJANGO_SECRET_KEY, POSTGRES_PASSWORD)
    )

    firewall_enabled: bool | None = None
    compose: Mapping[str, Any] = field(default_factory=dict)
    allowed_images: Iterable[str] = field(default_factory=tuple)

    network_profile: str | None = None
    exposure_mode: str | None = None
    admin_public: bool | None = None

    backup_enabled: bool | None = None
    backup_root: str | Path | None = None


# ---------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------


def pass_result(
    check: SecurityGateCheck,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> SecurityCheckResult:
    return SecurityCheckResult(
        check=check,
        status=SecurityGateStatus.PASS,
        message=message,
        details=details or {},
        blocking=is_blocking_check(check),
    )


def warn_result(
    check: SecurityGateCheck,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> SecurityCheckResult:
    return SecurityCheckResult(
        check=check,
        status=SecurityGateStatus.WARN,
        message=message,
        details=details or {},
        blocking=False,
    )


def skipped_result(
    check: SecurityGateCheck,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> SecurityCheckResult:
    return SecurityCheckResult(
        check=check,
        status=SecurityGateStatus.SKIPPED,
        message=message,
        details=details or {},
        blocking=False,
    )


def unknown_result(
    check: SecurityGateCheck,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> SecurityCheckResult:
    return SecurityCheckResult(
        check=check,
        status=SecurityGateStatus.UNKNOWN,
        message=message,
        details=details or {},
        blocking=is_blocking_check(check),
    )


def fail_result(
    check: SecurityGateCheck,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> SecurityCheckResult:
    return SecurityCheckResult(
        check=check,
        status=SecurityGateStatus.FAIL_BLOCKING,
        message=message,
        details=details or {},
        blocking=True,
    )


def is_blocking_check(check: SecurityGateCheck | str) -> bool:
    if isinstance(check, str):
        check = SecurityGateCheck(check)
    return check in BLOCKING_SECURITY_CHECKS


# ---------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------


def check_capsule_signature(
    signature_valid: bool | None,
    *,
    required: bool = True,
) -> SecurityCheckResult:
    check = SecurityGateCheck.CAPSULE_SIGNATURE

    if not required:
        return skipped_result(check, "Capsule signatures are not required by policy.")

    if signature_valid is True:
        return pass_result(check, "Capsule signature is valid.")

    if signature_valid is False:
        return fail_result(check, "Capsule signature is missing or invalid.")

    return unknown_result(check, "Capsule signature status is unknown.")


def check_image_checksums(checksum_valid: bool | None) -> SecurityCheckResult:
    check = SecurityGateCheck.IMAGE_CHECKSUMS

    if checksum_valid is True:
        return pass_result(check, "Capsule image checksums are valid.")

    if checksum_valid is False:
        return fail_result(check, "Capsule image checksums are missing or invalid.")

    return unknown_result(check, "Capsule image checksum status is unknown.")


def check_manifest_schema(schema_valid: bool | None) -> SecurityCheckResult:
    check = SecurityGateCheck.MANIFEST_SCHEMA

    if schema_valid is True:
        return pass_result(check, "Capsule manifest schema is valid.")

    if schema_valid is False:
        return fail_result(check, "Capsule manifest schema validation failed.")

    return unknown_result(check, "Capsule manifest schema status is unknown.")


def check_secrets_present(
    env: Mapping[str, str],
    *,
    required_keys: Sequence[str] | None = None,
) -> SecurityCheckResult:
    check = SecurityGateCheck.SECRETS_PRESENT
    required = tuple(required_keys or (DJANGO_SECRET_KEY, POSTGRES_PASSWORD))
    missing = [key for key in required if not env.get(key)]

    if not missing:
        return pass_result(
            check,
            "Required instance secrets are present.",
            {"required_keys": list(required)},
        )

    return fail_result(
        check,
        "Required instance secrets are missing.",
        {"missing": missing},
    )


def check_secrets_not_default(
    env: Mapping[str, str],
    *,
    secret_keys: Sequence[str] | None = None,
) -> SecurityCheckResult:
    check = SecurityGateCheck.SECRETS_NOT_DEFAULT
    keys = tuple(secret_keys or (DJANGO_SECRET_KEY, POSTGRES_PASSWORD))
    default_or_placeholder = [
        key for key in keys if is_placeholder_secret(env.get(key))
    ]

    if not default_or_placeholder:
        return pass_result(
            check,
            "Required instance secrets are non-default.",
            {"checked_keys": list(keys)},
        )

    return fail_result(
        check,
        "Required instance secrets are default, empty, or placeholders.",
        {"invalid_keys": default_or_placeholder},
    )


def check_firewall_enabled(enabled: bool | None) -> SecurityCheckResult:
    check = SecurityGateCheck.FIREWALL_ENABLED

    if enabled is True:
        return pass_result(check, "Host firewall is enabled.")

    if enabled is False:
        # Firewall being disabled is important, but the canonical blocking list
        # does not make this check a startup blocker.
        return warn_result(check, "Host firewall is disabled.")

    return unknown_result(check, "Host firewall status is unknown.")


def check_dangerous_ports_blocked(
    compose: Mapping[str, Any],
    *,
    forbidden_ports: Iterable[int] | None = None,
) -> SecurityCheckResult:
    check = SecurityGateCheck.DANGEROUS_PORTS_BLOCKED
    forbidden = set(forbidden_ports or FORBIDDEN_PUBLIC_PORTS)
    exposed = collect_forbidden_public_ports(compose, forbidden_ports=forbidden)

    if not exposed:
        return pass_result(
            check,
            "Forbidden internal service ports are not publicly exposed.",
            {"forbidden_ports": sorted(forbidden)},
        )

    return fail_result(
        check,
        "Forbidden internal service ports are publicly exposed.",
        {"exposed": exposed, "forbidden_ports": sorted(forbidden)},
    )


def check_postgres_not_public(compose: Mapping[str, Any]) -> SecurityCheckResult:
    check = SecurityGateCheck.POSTGRES_NOT_PUBLIC
    service = DockerService.POSTGRES.value

    public_ports = collect_service_public_ports(compose, service)
    bad = [port for port in public_ports if port.container_port == 5432 or port.host_port == 5432]

    if not bad:
        return pass_result(check, "PostgreSQL is not publicly exposed.")

    return fail_result(
        check,
        "PostgreSQL is publicly exposed.",
        {"service": service, "ports": [port.to_dict() for port in bad]},
    )


def check_redis_not_public(compose: Mapping[str, Any]) -> SecurityCheckResult:
    check = SecurityGateCheck.REDIS_NOT_PUBLIC
    service = DockerService.REDIS.value

    public_ports = collect_service_public_ports(compose, service)
    bad = [port for port in public_ports if port.container_port == 6379 or port.host_port == 6379]

    if not bad:
        return pass_result(check, "Redis is not publicly exposed.")

    return fail_result(
        check,
        "Redis is publicly exposed.",
        {"service": service, "ports": [port.to_dict() for port in bad]},
    )


def check_docker_socket_not_mounted(compose: Mapping[str, Any]) -> SecurityCheckResult:
    check = SecurityGateCheck.DOCKER_SOCKET_NOT_MOUNTED
    offenders = collect_docker_socket_mounts(compose)

    if not offenders:
        return pass_result(check, "Docker socket is not mounted into app containers.")

    return fail_result(
        check,
        "Docker socket is mounted into one or more containers.",
        {"offenders": offenders},
    )


def check_no_privileged_containers(compose: Mapping[str, Any]) -> SecurityCheckResult:
    check = SecurityGateCheck.NO_PRIVILEGED_CONTAINERS
    offenders = collect_privileged_containers(compose)

    if not offenders:
        return pass_result(check, "No privileged app containers are configured.")

    return fail_result(
        check,
        "One or more containers are configured as privileged.",
        {"offenders": offenders},
    )


def check_no_host_network(compose: Mapping[str, Any]) -> SecurityCheckResult:
    check = SecurityGateCheck.NO_HOST_NETWORK
    offenders = collect_host_network_containers(compose)

    if not offenders:
        return pass_result(check, "No app containers use host networking.")

    return fail_result(
        check,
        "One or more containers use host networking.",
        {"offenders": offenders},
    )


def check_allowed_images_only(
    compose: Mapping[str, Any],
    *,
    allowed_images: Iterable[str],
) -> SecurityCheckResult:
    check = SecurityGateCheck.ALLOWED_IMAGES_ONLY
    allowed = set(allowed_images)

    if not allowed:
        return unknown_result(
            check,
            "Allowed image set is empty or unavailable.",
        )

    used = collect_service_images(compose)
    unknown = {
        service: image
        for service, image in used.items()
        if image and image not in allowed
    }

    if not unknown:
        return pass_result(
            check,
            "All configured service images are allowlisted.",
            {"used_images": used},
        )

    return fail_result(
        check,
        "One or more configured service images are not allowlisted.",
        {"unknown_images": unknown, "allowed_images": sorted(allowed)},
    )


def check_admin_surface_private(
    *,
    network_profile: str | None,
    exposure_mode: str | None,
    admin_public: bool | None,
) -> SecurityCheckResult:
    check = SecurityGateCheck.ADMIN_SURFACE_PRIVATE

    if admin_public is False:
        return pass_result(check, "Admin surface is private.")

    if admin_public is True:
        if network_profile == "public_vps" and exposure_mode == "public":
            return warn_result(
                check,
                "Admin surface is public under public_vps profile; verify auth and firewall policy.",
                {
                    "network_profile": network_profile,
                    "exposure_mode": exposure_mode,
                },
            )

        return fail_result(
            check,
            "Admin surface is public outside approved public_vps exposure.",
            {
                "network_profile": network_profile,
                "exposure_mode": exposure_mode,
            },
        )

    return unknown_result(
        check,
        "Admin surface exposure status is unknown.",
        {
            "network_profile": network_profile,
            "exposure_mode": exposure_mode,
        },
    )


def check_backup_configured(
    *,
    enabled: bool | None,
    backup_root: str | Path | None,
) -> SecurityCheckResult:
    check = SecurityGateCheck.BACKUP_CONFIGURED

    if enabled is False:
        return warn_result(check, "Backups are disabled.")

    if enabled is None:
        return unknown_result(check, "Backup enabled status is unknown.")

    if backup_root is None or str(backup_root).strip() == "":
        return warn_result(check, "Backups are enabled but backup root is not configured.")

    return pass_result(
        check,
        "Backups are enabled and backup root is configured.",
        {"backup_root": str(backup_root)},
    )


# ---------------------------------------------------------------------
# Aggregate check runners
# ---------------------------------------------------------------------


def run_all_security_checks(context: SecurityCheckContext) -> list[SecurityCheckResult]:
    """Run the canonical Security Gate check set."""

    return [
        check_capsule_signature(
            context.capsule_signature_valid,
            required=context.capsule_signature_required,
        ),
        check_image_checksums(context.image_checksums_valid),
        check_manifest_schema(context.manifest_schema_valid),
        check_secrets_present(
            context.env,
            required_keys=context.required_secret_keys,
        ),
        check_secrets_not_default(
            context.env,
            secret_keys=context.required_secret_keys,
        ),
        check_firewall_enabled(context.firewall_enabled),
        check_dangerous_ports_blocked(context.compose),
        check_postgres_not_public(context.compose),
        check_redis_not_public(context.compose),
        check_docker_socket_not_mounted(context.compose),
        check_no_privileged_containers(context.compose),
        check_no_host_network(context.compose),
        check_allowed_images_only(
            context.compose,
            allowed_images=context.allowed_images,
        ),
        check_admin_surface_private(
            network_profile=context.network_profile,
            exposure_mode=context.exposure_mode,
            admin_public=context.admin_public,
        ),
        check_backup_configured(
            enabled=context.backup_enabled,
            backup_root=context.backup_root,
        ),
    ]


def has_blocking_failures(results: Sequence[SecurityCheckResult]) -> bool:
    return any(result.failed_blocking for result in results)


def blocking_failures(results: Sequence[SecurityCheckResult]) -> list[SecurityCheckResult]:
    return [result for result in results if result.failed_blocking]


def summarize_results(results: Sequence[SecurityCheckResult]) -> dict[str, Any]:
    counts = {status.value: 0 for status in SecurityGateStatus}
    for result in results:
        counts[result.status.value] += 1

    failures = blocking_failures(results)
    return {
        "status": (
            SecurityGateStatus.FAIL_BLOCKING.value
            if failures
            else SecurityGateStatus.PASS.value
        ),
        "counts": counts,
        "blocking_failures": [result.to_dict() for result in failures],
        "results": [result.to_dict() for result in results],
    }


# ---------------------------------------------------------------------
# Compose inspection helpers
# ---------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class PublishedPort:
    service: str
    host_ip: str | None
    host_port: int | None
    container_port: int | None
    protocol: str | None = None
    raw: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "host_ip": self.host_ip,
            "host_port": self.host_port,
            "container_port": self.container_port,
            "protocol": self.protocol,
            "raw": self.raw,
        }


def collect_forbidden_public_ports(
    compose: Mapping[str, Any],
    *,
    forbidden_ports: Iterable[int] | None = None,
) -> list[dict[str, Any]]:
    forbidden = set(forbidden_ports or FORBIDDEN_PUBLIC_PORTS)
    offenders: list[dict[str, Any]] = []

    for port in collect_public_ports(compose):
        if port.host_port in forbidden or port.container_port in forbidden:
            offenders.append(port.to_dict())

    return offenders


def collect_public_ports(compose: Mapping[str, Any]) -> list[PublishedPort]:
    services = get_compose_services(compose)
    ports: list[PublishedPort] = []

    for service_name, service_config in services.items():
        for raw_port in service_config.get("ports", []) or []:
            parsed = parse_compose_port(service_name, raw_port)
            if parsed is not None:
                ports.append(parsed)

    return ports


def collect_service_public_ports(
    compose: Mapping[str, Any],
    service_name: str,
) -> list[PublishedPort]:
    return [
        port
        for port in collect_public_ports(compose)
        if port.service == service_name
    ]


def parse_compose_port(service_name: str, raw_port: Any) -> PublishedPort | None:
    """Parse common Docker Compose port formats.

    Supported examples:
    - "443:443"
    - "127.0.0.1:3000:3000"
    - "80:80/tcp"
    - {"published": 443, "target": 443, "protocol": "tcp"}
    """

    if isinstance(raw_port, int):
        return PublishedPort(
            service=service_name,
            host_ip=None,
            host_port=raw_port,
            container_port=raw_port,
            raw=raw_port,
        )

    if isinstance(raw_port, Mapping):
        published = _to_int(raw_port.get("published"))
        target = _to_int(raw_port.get("target"))
        host_ip = raw_port.get("host_ip") or raw_port.get("host_ip")
        protocol = raw_port.get("protocol")
        return PublishedPort(
            service=service_name,
            host_ip=str(host_ip) if host_ip else None,
            host_port=published,
            container_port=target,
            protocol=str(protocol) if protocol else None,
            raw=dict(raw_port),
        )

    if not isinstance(raw_port, str):
        return None

    value = raw_port.strip()
    protocol = None
    if "/" in value:
        value, protocol = value.rsplit("/", 1)

    parts = value.split(":")
    host_ip = None
    host_port: int | None = None
    container_port: int | None = None

    if len(parts) == 1:
        container_port = _to_int(parts[0])
        host_port = container_port
    elif len(parts) == 2:
        host_port = _to_int(parts[0])
        container_port = _to_int(parts[1])
    else:
        host_ip = ":".join(parts[:-2])
        host_port = _to_int(parts[-2])
        container_port = _to_int(parts[-1])

    return PublishedPort(
        service=service_name,
        host_ip=host_ip,
        host_port=host_port,
        container_port=container_port,
        protocol=protocol,
        raw=raw_port,
    )


def collect_docker_socket_mounts(compose: Mapping[str, Any]) -> list[dict[str, Any]]:
    offenders: list[dict[str, Any]] = []

    for service_name, service_config in get_compose_services(compose).items():
        volumes = service_config.get("volumes", []) or []
        for volume in volumes:
            if volume_references_docker_socket(volume):
                offenders.append({"service": service_name, "volume": volume})

    return offenders


def volume_references_docker_socket(volume: Any) -> bool:
    if isinstance(volume, str):
        return "/var/run/docker.sock" in volume

    if isinstance(volume, Mapping):
        source = str(volume.get("source") or volume.get("src") or "")
        target = str(volume.get("target") or volume.get("dst") or volume.get("destination") or "")
        return "/var/run/docker.sock" in source or "/var/run/docker.sock" in target

    return False


def collect_privileged_containers(compose: Mapping[str, Any]) -> list[str]:
    offenders: list[str] = []

    for service_name, service_config in get_compose_services(compose).items():
        if service_config.get("privileged") is True:
            offenders.append(service_name)

    return offenders


def collect_host_network_containers(compose: Mapping[str, Any]) -> list[str]:
    offenders: list[str] = []

    for service_name, service_config in get_compose_services(compose).items():
        if service_config.get("network_mode") == "host":
            offenders.append(service_name)

    return offenders


def collect_service_images(compose: Mapping[str, Any]) -> dict[str, str]:
    images: dict[str, str] = {}

    for service_name, service_config in get_compose_services(compose).items():
        image = service_config.get("image")
        if image:
            images[service_name] = str(image)

    return images


def get_compose_services(compose: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    services = compose.get("services", {})
    if not isinstance(services, Mapping):
        return {}

    normalized: dict[str, Mapping[str, Any]] = {}
    for service_name, service_config in services.items():
        if isinstance(service_config, Mapping):
            normalized[str(service_name)] = service_config

    return normalized


def _to_int(value: Any) -> int | None:
    if value is None:
        return None

    if isinstance(value, int):
        return value

    match = re.search(r"\d+", str(value))
    if not match:
        return None

    return int(match.group(0))


__all__ = [
    "PublishedPort",
    "SecurityCheckContext",
    "SecurityCheckResult",
    "blocking_failures",
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
    "collect_docker_socket_mounts",
    "collect_forbidden_public_ports",
    "collect_host_network_containers",
    "collect_privileged_containers",
    "collect_public_ports",
    "collect_service_images",
    "collect_service_public_ports",
    "fail_result",
    "get_compose_services",
    "has_blocking_failures",
    "is_blocking_check",
    "parse_compose_port",
    "pass_result",
    "run_all_security_checks",
    "skipped_result",
    "summarize_results",
    "unknown_result",
    "volume_references_docker_socket",
    "warn_result",
]
