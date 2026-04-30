"""Canonical network profile handling for Konnaxion Agent.

Network profiles are declarative safety presets used by the Agent when creating
or updating a Konnaxion Instance. This module does not invent profile names or
exposure modes. It imports them from the shared canonical registry and enforces
private-by-default behavior.

The Agent must reject arbitrary public exposure, dangerous ports, and invalid
profile/exposure combinations before runtime generation or firewall changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Mapping, Sequence

from kx_shared.konnaxion_constants import (
    ALLOWED_ENTRY_PORTS,
    DEFAULT_EXPOSURE_MODE,
    DEFAULT_NETWORK_PROFILE,
    FORBIDDEN_PUBLIC_PORTS,
    ExposureMode,
    NetworkProfile,
)


class NetworkProfileError(ValueError):
    """Raised when a network profile is invalid or unsafe."""


class NetworkBinding(StrEnum):
    """Where Traefik is allowed to bind for a profile."""

    LOOPBACK = "loopback"
    LAN = "lan"
    VPN = "vpn"
    TUNNEL = "tunnel"
    PUBLIC = "public"
    NONE = "none"


@dataclass(frozen=True)
class PortRule:
    """A port exposure rule for a network profile."""

    port: int
    protocol: str = "tcp"
    public: bool = False
    reason: str = ""

    def validate(self) -> None:
        if self.port <= 0 or self.port > 65535:
            raise NetworkProfileError(f"invalid port: {self.port}")

        if self.public and self.port in FORBIDDEN_PUBLIC_PORTS:
            raise NetworkProfileError(
                f"port {self.port} must never be public in Konnaxion profiles"
            )


@dataclass(frozen=True)
class NetworkProfileSpec:
    """Declarative network profile definition."""

    profile: NetworkProfile
    exposure_mode: ExposureMode
    binding: NetworkBinding
    public_mode_enabled: bool = False
    requires_expiration: bool = False
    requires_hardened_host: bool = False
    allowed_entry_ports: tuple[int, ...] = field(default_factory=tuple)
    forbidden_public_ports: tuple[int, ...] = field(default_factory=lambda: tuple(sorted(FORBIDDEN_PUBLIC_PORTS)))
    bind_hosts: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def value(self) -> str:
        return self.profile.value

    def validate(self, *, public_mode_expires_at: str | None = None) -> None:
        """Validate the profile against canonical safety rules."""

        if self.public_mode_enabled and self.exposure_mode not in {
            ExposureMode.TEMPORARY_TUNNEL,
            ExposureMode.PUBLIC,
        }:
            raise NetworkProfileError(
                f"{self.profile.value} enables public mode with invalid exposure "
                f"{self.exposure_mode.value}"
            )

        if not self.public_mode_enabled and self.exposure_mode == ExposureMode.PUBLIC:
            raise NetworkProfileError(
                f"{self.profile.value} cannot use public exposure unless public mode is enabled"
            )

        if self.requires_expiration and not public_mode_expires_at:
            raise NetworkProfileError(
                f"{self.profile.value} requires KX_PUBLIC_MODE_EXPIRES_AT"
            )

        if public_mode_expires_at:
            _parse_expiration(public_mode_expires_at)

        for port in self.allowed_entry_ports:
            PortRule(
                port=port,
                public=self.public_mode_enabled or self.binding == NetworkBinding.PUBLIC,
                reason=f"{self.profile.value} entrypoint",
            ).validate()

        for port in self.forbidden_public_ports:
            if port in self.allowed_entry_ports:
                raise NetworkProfileError(
                    f"{self.profile.value} cannot allow forbidden public port {port}"
                )


NETWORK_PROFILE_REGISTRY: dict[NetworkProfile, NetworkProfileSpec] = {
    NetworkProfile.LOCAL_ONLY: NetworkProfileSpec(
        profile=NetworkProfile.LOCAL_ONLY,
        exposure_mode=ExposureMode.PRIVATE,
        binding=NetworkBinding.LOOPBACK,
        public_mode_enabled=False,
        allowed_entry_ports=(),
        bind_hosts=("127.0.0.1", "::1"),
        notes=("Accessible only from the local machine.",),
    ),
    NetworkProfile.INTRANET_PRIVATE: NetworkProfileSpec(
        profile=NetworkProfile.INTRANET_PRIVATE,
        exposure_mode=ExposureMode.PRIVATE,
        binding=NetworkBinding.LAN,
        public_mode_enabled=False,
        allowed_entry_ports=(ALLOWED_ENTRY_PORTS["https"],),
        bind_hosts=("0.0.0.0",),
        notes=("Default LAN/intranet profile. Not Internet-facing.",),
    ),
    NetworkProfile.PRIVATE_TUNNEL: NetworkProfileSpec(
        profile=NetworkProfile.PRIVATE_TUNNEL,
        exposure_mode=ExposureMode.VPN,
        binding=NetworkBinding.VPN,
        public_mode_enabled=False,
        allowed_entry_ports=(ALLOWED_ENTRY_PORTS["https"],),
        bind_hosts=("0.0.0.0",),
        notes=("Accessible through a private tunnel or VPN only.",),
    ),
    NetworkProfile.PUBLIC_TEMPORARY: NetworkProfileSpec(
        profile=NetworkProfile.PUBLIC_TEMPORARY,
        exposure_mode=ExposureMode.TEMPORARY_TUNNEL,
        binding=NetworkBinding.TUNNEL,
        public_mode_enabled=True,
        requires_expiration=True,
        allowed_entry_ports=(ALLOWED_ENTRY_PORTS["https"],),
        bind_hosts=("0.0.0.0",),
        notes=("Temporary public demo profile. Expiration is mandatory.",),
    ),
    NetworkProfile.PUBLIC_VPS: NetworkProfileSpec(
        profile=NetworkProfile.PUBLIC_VPS,
        exposure_mode=ExposureMode.PUBLIC,
        binding=NetworkBinding.PUBLIC,
        public_mode_enabled=True,
        requires_hardened_host=True,
        allowed_entry_ports=(
            ALLOWED_ENTRY_PORTS["https"],
            ALLOWED_ENTRY_PORTS["http_redirect"],
        ),
        bind_hosts=("0.0.0.0",),
        notes=("Permanent public profile for hardened VPS deployments only.",),
    ),
    NetworkProfile.OFFLINE: NetworkProfileSpec(
        profile=NetworkProfile.OFFLINE,
        exposure_mode=ExposureMode.PRIVATE,
        binding=NetworkBinding.NONE,
        public_mode_enabled=False,
        allowed_entry_ports=(),
        bind_hosts=(),
        notes=("No external network exposure.",),
    ),
}


def default_network_profile() -> NetworkProfileSpec:
    """Return the canonical default private profile."""

    return get_network_profile(DEFAULT_NETWORK_PROFILE)


def get_network_profile(profile: NetworkProfile | str) -> NetworkProfileSpec:
    """Return a canonical network profile definition."""

    normalized = normalize_network_profile(profile)

    try:
        return NETWORK_PROFILE_REGISTRY[normalized]
    except KeyError as exc:  # pragma: no cover - defensive guard
        raise NetworkProfileError(f"unsupported network profile: {normalized.value}") from exc


def normalize_network_profile(profile: NetworkProfile | str) -> NetworkProfile:
    """Normalize a profile value into ``NetworkProfile``."""

    if isinstance(profile, NetworkProfile):
        return profile

    try:
        return NetworkProfile(str(profile))
    except ValueError as exc:
        allowed = ", ".join(sorted(item.value for item in NetworkProfile))
        raise NetworkProfileError(
            f"unknown network profile {profile!r}; allowed values: {allowed}"
        ) from exc


def normalize_exposure_mode(exposure_mode: ExposureMode | str | None) -> ExposureMode:
    """Normalize an exposure mode into ``ExposureMode``."""

    if exposure_mode is None:
        return DEFAULT_EXPOSURE_MODE

    if isinstance(exposure_mode, ExposureMode):
        return exposure_mode

    try:
        return ExposureMode(str(exposure_mode))
    except ValueError as exc:
        allowed = ", ".join(sorted(item.value for item in ExposureMode))
        raise NetworkProfileError(
            f"unknown exposure mode {exposure_mode!r}; allowed values: {allowed}"
        ) from exc


def validate_profile_selection(
    profile: NetworkProfile | str,
    *,
    exposure_mode: ExposureMode | str | None = None,
    public_mode_enabled: bool | str | None = None,
    public_mode_expires_at: str | None = None,
) -> NetworkProfileSpec:
    """Validate a selected profile and optional runtime overrides.

    Runtime overrides are allowed only when they preserve the canonical profile's
    safety posture. This prevents the Manager/UI from turning an intranet or
    local profile into an accidental public deployment.
    """

    spec = get_network_profile(profile)
    resolved_exposure = normalize_exposure_mode(exposure_mode)

    if exposure_mode is not None and resolved_exposure != spec.exposure_mode:
        raise NetworkProfileError(
            f"profile {spec.profile.value!r} requires exposure "
            f"{spec.exposure_mode.value!r}; got {resolved_exposure.value!r}"
        )

    resolved_public = (
        spec.public_mode_enabled
        if public_mode_enabled is None
        else _parse_bool(public_mode_enabled)
    )

    if resolved_public != spec.public_mode_enabled:
        raise NetworkProfileError(
            f"profile {spec.profile.value!r} requires "
            f"KX_PUBLIC_MODE_ENABLED={str(spec.public_mode_enabled).lower()}"
        )

    spec.validate(public_mode_expires_at=public_mode_expires_at)
    return spec


def validate_all_profiles() -> None:
    """Validate the entire canonical profile registry."""

    missing = set(NetworkProfile) - set(NETWORK_PROFILE_REGISTRY)
    if missing:
        missing_values = ", ".join(sorted(profile.value for profile in missing))
        raise NetworkProfileError(f"missing canonical network profiles: {missing_values}")

    for spec in NETWORK_PROFILE_REGISTRY.values():
        spec.validate(public_mode_expires_at="2099-01-01T00:00:00Z" if spec.requires_expiration else None)


def profile_to_kx_env(
    profile: NetworkProfile | str,
    *,
    public_mode_expires_at: str | None = None,
    host: str | None = None,
) -> dict[str, str]:
    """Render canonical KX_* environment values for a profile."""

    spec = validate_profile_selection(
        profile,
        exposure_mode=get_network_profile(profile).exposure_mode,
        public_mode_enabled=get_network_profile(profile).public_mode_enabled,
        public_mode_expires_at=public_mode_expires_at,
    )

    return {
        "KX_NETWORK_PROFILE": spec.profile.value,
        "KX_EXPOSURE_MODE": spec.exposure_mode.value,
        "KX_PUBLIC_MODE_ENABLED": str(spec.public_mode_enabled).lower(),
        "KX_PUBLIC_MODE_EXPIRES_AT": public_mode_expires_at or "",
        "KX_HOST": host or "",
    }


def profile_from_kx_env(env: Mapping[str, str]) -> NetworkProfileSpec:
    """Resolve and validate a profile from KX_* environment values."""

    profile = env.get("KX_NETWORK_PROFILE", DEFAULT_NETWORK_PROFILE.value)
    exposure = env.get("KX_EXPOSURE_MODE", DEFAULT_EXPOSURE_MODE.value)
    public_enabled = env.get("KX_PUBLIC_MODE_ENABLED")
    expires_at = env.get("KX_PUBLIC_MODE_EXPIRES_AT") or None

    return validate_profile_selection(
        profile,
        exposure_mode=exposure,
        public_mode_enabled=public_enabled,
        public_mode_expires_at=expires_at,
    )


def allowed_entry_ports_for(profile: NetworkProfile | str) -> tuple[int, ...]:
    """Return allowed entry ports for a profile."""

    return get_network_profile(profile).allowed_entry_ports


def forbidden_public_ports() -> tuple[int, ...]:
    """Return canonical ports that must never be exposed directly."""

    return tuple(sorted(FORBIDDEN_PUBLIC_PORTS))


def is_public_profile(profile: NetworkProfile | str) -> bool:
    """Return whether the profile intentionally enables public mode."""

    return get_network_profile(profile).public_mode_enabled


def is_private_by_default(profile: NetworkProfile | str) -> bool:
    """Return whether the profile preserves private-by-default posture."""

    spec = get_network_profile(profile)
    return not spec.public_mode_enabled and spec.exposure_mode in {
        ExposureMode.PRIVATE,
        ExposureMode.LAN,
        ExposureMode.VPN,
    }


def compose_traefik_bind_args(profile: NetworkProfile | str) -> tuple[str, ...]:
    """Return safe Traefik bind host hints for compose/profile rendering.

    This does not write Docker Compose directly. The compose generator should
    consume these values and keep direct app services internal.
    """

    spec = get_network_profile(profile)

    if spec.binding == NetworkBinding.NONE:
        return ()

    return tuple(
        f"{host}:{port}:{port}"
        for host in spec.bind_hosts
        for port in spec.allowed_entry_ports
    )


def assert_no_forbidden_public_ports(ports: Sequence[int]) -> None:
    """Reject a set of public ports if any are canonically forbidden."""

    blocked = sorted(set(int(port) for port in ports) & set(FORBIDDEN_PUBLIC_PORTS))
    if blocked:
        raise NetworkProfileError(
            "forbidden public ports requested: " + ", ".join(str(port) for port in blocked)
        )


def _parse_bool(value: bool | str) -> bool:
    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False

    raise NetworkProfileError(f"invalid boolean value: {value!r}")


def _parse_expiration(value: str) -> datetime:
    candidate = value.strip()
    if not candidate:
        raise NetworkProfileError("public mode expiration cannot be empty")

    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise NetworkProfileError(
            "public mode expiration must be an ISO-8601 datetime"
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


__all__ = [
    "NetworkBinding",
    "NetworkProfileError",
    "NetworkProfileSpec",
    "PortRule",
    "NETWORK_PROFILE_REGISTRY",
    "allowed_entry_ports_for",
    "assert_no_forbidden_public_ports",
    "compose_traefik_bind_args",
    "default_network_profile",
    "forbidden_public_ports",
    "get_network_profile",
    "is_private_by_default",
    "is_public_profile",
    "normalize_exposure_mode",
    "normalize_network_profile",
    "profile_from_kx_env",
    "profile_to_kx_env",
    "validate_all_profiles",
    "validate_profile_selection",
]
