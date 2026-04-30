"""
Port validation helpers for Konnaxion Agent Security Gate.

This module enforces the canonical Konnaxion rule:

- Public/LAN HTTP(S) access must enter through Traefik.
- Only approved entry ports may be exposed by network profile.
- Internal service ports must never be publicly exposed.
- Docker daemon TCP and Docker socket exposure are always forbidden.

Canonical values come from ``kx_shared.konnaxion_constants``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
import re
from typing import Any

from kx_shared.konnaxion_constants import (
    ALLOWED_ENTRY_PORTS,
    FORBIDDEN_PUBLIC_PORTS,
    INTERNAL_ONLY_PORTS,
    DockerService,
    ExposureMode,
    NetworkProfile,
)


class PortExposure(StrEnum):
    """Host exposure classification for a published Docker port."""

    LOCALHOST = "localhost"
    PRIVATE = "private"
    PUBLIC = "public"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PortMapping:
    """Normalized Docker Compose port mapping."""

    service: str
    published: int | None
    target: int | None
    host_ip: str | None = None
    protocol: str = "tcp"
    raw: Any = None

    @property
    def exposure(self) -> PortExposure:
        """Classify how the mapping is exposed."""

        if self.host_ip in {"127.0.0.1", "::1", "localhost"}:
            return PortExposure.LOCALHOST

        if self.host_ip in {None, "", "0.0.0.0", "::"}:
            return PortExposure.PUBLIC

        if self.host_ip.startswith(("10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.")):
            return PortExposure.PRIVATE

        # Approximate the full RFC1918 172.16.0.0/12 range.
        match = re.match(r"^172\.(\d{1,2})\.", self.host_ip)
        if match and 16 <= int(match.group(1)) <= 31:
            return PortExposure.PRIVATE

        return PortExposure.UNKNOWN


@dataclass(frozen=True)
class PortViolation:
    """A detected unsafe port exposure."""

    code: str
    message: str
    service: str | None = None
    port: int | None = None
    mapping: PortMapping | None = None


@dataclass(frozen=True)
class PortValidationResult:
    """Result returned by port validation functions."""

    ok: bool
    violations: tuple[PortViolation, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def raise_for_violations(self) -> None:
        """Raise ``PortPolicyError`` when blocking violations exist."""

        if not self.ok:
            raise PortPolicyError(self.violations)


class PortPolicyError(ValueError):
    """Raised when Konnaxion port policy is violated."""

    def __init__(self, violations: Iterable[PortViolation]) -> None:
        self.violations = tuple(violations)
        detail = "; ".join(violation.message for violation in self.violations)
        super().__init__(detail or "Port policy violation")


def normalize_port(port: int | str | None) -> int | None:
    """Normalize a TCP/UDP port value."""

    if port is None or port == "":
        return None

    try:
        normalized = int(str(port).strip())
    except ValueError as exc:
        raise ValueError(f"Invalid port value: {port!r}") from exc

    if not 1 <= normalized <= 65535:
        raise ValueError(f"Port out of range: {normalized}")

    return normalized


def allowed_entry_ports() -> frozenset[int]:
    """Return canonical public/LAN entry ports."""

    return frozenset(int(port) for port in ALLOWED_ENTRY_PORTS.values())


def internal_only_ports() -> frozenset[int]:
    """Return canonical ports that must not be public."""

    values: set[int] = set()
    for port in INTERNAL_ONLY_PORTS.values():
        values.add(int(port))
    return frozenset(values)


def forbidden_public_ports() -> frozenset[int]:
    """Return canonical dangerous public ports."""

    return frozenset(int(port) for port in FORBIDDEN_PUBLIC_PORTS)


def is_allowed_entry_port(port: int | str | None) -> bool:
    """Return whether a port is an approved entry port."""

    normalized = normalize_port(port)
    return normalized in allowed_entry_ports()


def is_internal_only_port(port: int | str | None) -> bool:
    """Return whether a port is reserved for internal services."""

    normalized = normalize_port(port)
    return normalized in internal_only_ports()


def is_forbidden_public_port(port: int | str | None) -> bool:
    """Return whether a port must never be publicly exposed."""

    normalized = normalize_port(port)
    return normalized in forbidden_public_ports()


def parse_compose_port_mapping(service: str, raw: Any) -> PortMapping:
    """Parse a Docker Compose port mapping.

    Supported forms include:

    - ``"80:80"``
    - ``"127.0.0.1:8000:8000"``
    - ``"443:443/tcp"``
    - ``{"published": 443, "target": 443, "host_ip": "0.0.0.0"}``
    """

    if isinstance(raw, Mapping):
        published = normalize_port(raw.get("published"))
        target = normalize_port(raw.get("target"))
        host_ip = raw.get("host_ip") or raw.get("host_ip".replace("_", ""))
        protocol = str(raw.get("protocol", "tcp"))
        return PortMapping(
            service=service,
            published=published,
            target=target,
            host_ip=str(host_ip) if host_ip else None,
            protocol=protocol,
            raw=raw,
        )

    if not isinstance(raw, str):
        raise ValueError(f"Unsupported Compose port mapping for {service}: {raw!r}")

    value = raw.strip()
    protocol = "tcp"

    if "/" in value:
        value, protocol = value.rsplit("/", 1)

    parts = value.split(":")

    if len(parts) == 1:
        # Compose short form without explicit published port exposes only to
        # linked services, not to the host.
        return PortMapping(
            service=service,
            published=None,
            target=normalize_port(parts[0]),
            protocol=protocol,
            raw=raw,
        )

    if len(parts) == 2:
        return PortMapping(
            service=service,
            published=normalize_port(parts[0]),
            target=normalize_port(parts[1]),
            protocol=protocol,
            raw=raw,
        )

    if len(parts) == 3:
        return PortMapping(
            service=service,
            host_ip=parts[0],
            published=normalize_port(parts[1]),
            target=normalize_port(parts[2]),
            protocol=protocol,
            raw=raw,
        )

    raise ValueError(f"Invalid Compose port mapping for {service}: {raw!r}")


def extract_compose_port_mappings(compose: Mapping[str, Any]) -> tuple[PortMapping, ...]:
    """Extract host port mappings from a Compose document."""

    services = compose.get("services", {})
    if not isinstance(services, Mapping):
        raise ValueError("Compose document must contain a mapping at services")

    mappings: list[PortMapping] = []

    for service, definition in services.items():
        if not isinstance(definition, Mapping):
            continue

        for raw_mapping in definition.get("ports", []) or []:
            mappings.append(parse_compose_port_mapping(str(service), raw_mapping))

    return tuple(mappings)


def _normalize_network_profile(value: str | NetworkProfile) -> str:
    return str(getattr(value, "value", value))


def _normalize_exposure_mode(value: str | ExposureMode) -> str:
    return str(getattr(value, "value", value))


def _is_public_allowed(
    network_profile: str | NetworkProfile,
    exposure_mode: str | ExposureMode,
) -> bool:
    profile = _normalize_network_profile(network_profile)
    exposure = _normalize_exposure_mode(exposure_mode)

    return profile in {
        NetworkProfile.PUBLIC_TEMPORARY.value,
        NetworkProfile.PUBLIC_VPS.value,
    } or exposure in {
        ExposureMode.TEMPORARY_TUNNEL.value,
        ExposureMode.PUBLIC.value,
    }


def validate_port_mappings(
    mappings: Iterable[PortMapping],
    *,
    network_profile: str | NetworkProfile,
    exposure_mode: str | ExposureMode,
) -> PortValidationResult:
    """Validate normalized port mappings against Konnaxion security policy."""

    violations: list[PortViolation] = []
    warnings: list[str] = []

    public_allowed = _is_public_allowed(network_profile, exposure_mode)

    for mapping in mappings:
        if mapping.published is None:
            continue

        published = mapping.published
        target = mapping.target

        if mapping.service != DockerService.TRAEFIK.value:
            violations.append(
                PortViolation(
                    code="non_traefik_host_port",
                    service=mapping.service,
                    port=published,
                    mapping=mapping,
                    message=(
                        f"{mapping.service} publishes host port {published}; "
                        "only traefik may publish HTTP(S) entry ports"
                    ),
                )
            )

        if is_forbidden_public_port(published) or is_forbidden_public_port(target):
            violations.append(
                PortViolation(
                    code="forbidden_public_port",
                    service=mapping.service,
                    port=published,
                    mapping=mapping,
                    message=(
                        f"{mapping.service} exposes forbidden internal port "
                        f"{published}->{target}"
                    ),
                )
            )

        if mapping.service == DockerService.TRAEFIK.value:
            if not is_allowed_entry_port(published):
                violations.append(
                    PortViolation(
                        code="invalid_entry_port",
                        service=mapping.service,
                        port=published,
                        mapping=mapping,
                        message=(
                            f"traefik publishes port {published}; only canonical "
                            "entry ports are allowed"
                        ),
                    )
                )

            if mapping.exposure is PortExposure.PUBLIC and not public_allowed:
                violations.append(
                    PortViolation(
                        code="public_exposure_not_allowed",
                        service=mapping.service,
                        port=published,
                        mapping=mapping,
                        message=(
                            f"traefik publishes port {published} publicly while "
                            f"profile={_normalize_network_profile(network_profile)} "
                            f"and exposure={_normalize_exposure_mode(exposure_mode)}"
                        ),
                    )
                )

        if mapping.exposure is PortExposure.UNKNOWN:
            warnings.append(
                f"{mapping.service} publishes {published} on unknown host IP "
                f"{mapping.host_ip!r}"
            )

    return PortValidationResult(
        ok=not violations,
        violations=tuple(violations),
        warnings=tuple(warnings),
    )


def validate_compose_ports(
    compose: Mapping[str, Any],
    *,
    network_profile: str | NetworkProfile,
    exposure_mode: str | ExposureMode,
) -> PortValidationResult:
    """Validate the ``ports`` sections in a Compose document."""

    return validate_port_mappings(
        extract_compose_port_mappings(compose),
        network_profile=network_profile,
        exposure_mode=exposure_mode,
    )


def validate_public_ports(
    ports: Iterable[int | str],
    *,
    network_profile: str | NetworkProfile,
    exposure_mode: str | ExposureMode,
    service: str = DockerService.TRAEFIK.value,
) -> PortValidationResult:
    """Validate an explicit list of public host ports."""

    mappings = tuple(
        PortMapping(
            service=service,
            published=normalize_port(port),
            target=normalize_port(port),
            host_ip="0.0.0.0",
            raw=port,
        )
        for port in ports
    )

    return validate_port_mappings(
        mappings,
        network_profile=network_profile,
        exposure_mode=exposure_mode,
    )


def assert_safe_compose_ports(
    compose: Mapping[str, Any],
    *,
    network_profile: str | NetworkProfile,
    exposure_mode: str | ExposureMode,
) -> None:
    """Raise when a Compose document violates Konnaxion port policy."""

    validate_compose_ports(
        compose,
        network_profile=network_profile,
        exposure_mode=exposure_mode,
    ).raise_for_violations()


def assert_no_forbidden_public_ports(ports: Iterable[int | str]) -> None:
    """Raise if any listed port is forbidden for public exposure."""

    violations = [
        PortViolation(
            code="forbidden_public_port",
            port=normalize_port(port),
            message=f"Port {normalize_port(port)} must never be publicly exposed",
        )
        for port in ports
        if is_forbidden_public_port(port)
    ]

    if violations:
        raise PortPolicyError(violations)


__all__ = [
    "PortExposure",
    "PortMapping",
    "PortPolicyError",
    "PortValidationResult",
    "PortViolation",
    "allowed_entry_ports",
    "assert_no_forbidden_public_ports",
    "assert_safe_compose_ports",
    "extract_compose_port_mappings",
    "forbidden_public_ports",
    "internal_only_ports",
    "is_allowed_entry_port",
    "is_forbidden_public_port",
    "is_internal_only_port",
    "normalize_port",
    "parse_compose_port_mapping",
    "validate_compose_ports",
    "validate_port_mappings",
    "validate_public_ports",
]
