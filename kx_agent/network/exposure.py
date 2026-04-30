"""
Network exposure policy for Konnaxion Agent.

This module is the canonical runtime guard for exposure decisions:
- maps NETWORK_PROFILE values to allowed KX_EXPOSURE_MODE values
- blocks accidental public exposure
- requires expiration for public_temporary mode
- produces structured plans for Agent lifecycle/network code

It does not mutate firewall rules, start tunnels, or edit Docker Compose files.
Those actions belong to dedicated Agent modules and must consume the validated
ExposurePlan produced here.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Mapping

from kx_shared.konnaxion_constants import (
    DEFAULT_EXPOSURE_MODE,
    DEFAULT_NETWORK_PROFILE,
    ExposureMode,
    NetworkProfile,
)


class ExposurePolicyError(ValueError):
    """Raised when an exposure request violates Konnaxion policy."""


class ExposureRisk(StrEnum):
    """Risk level for a validated exposure plan."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


class ExposureAction(StrEnum):
    """High-level exposure transition action."""

    KEEP_PRIVATE = "keep_private"
    SET_LOCAL_ONLY = "set_local_only"
    SET_LAN = "set_lan"
    SET_VPN = "set_vpn"
    SET_TEMPORARY_TUNNEL = "set_temporary_tunnel"
    SET_PUBLIC_VPS = "set_public_vps"
    SET_OFFLINE = "set_offline"
    EXPIRE_PUBLIC_MODE = "expire_public_mode"


@dataclass(frozen=True)
class ExposureRequest:
    """Requested network exposure state."""

    network_profile: NetworkProfile
    exposure_mode: ExposureMode
    public_mode_enabled: bool = False
    public_mode_expires_at: datetime | None = None
    public_mode_duration_hours: int | None = None
    host: str = ""
    requested_by: str = "system"
    reason: str = ""

    @classmethod
    def from_environment(cls) -> "ExposureRequest":
        """Build an exposure request from KX_* environment variables."""

        public_enabled = read_bool(
            os.getenv("KX_PUBLIC_MODE_ENABLED", "false"),
            key="KX_PUBLIC_MODE_ENABLED",
        )

        expires_at_raw = os.getenv("KX_PUBLIC_MODE_EXPIRES_AT", "").strip()
        duration_raw = os.getenv("KX_PUBLIC_MODE_DURATION_HOURS", "").strip()

        return cls(
            network_profile=parse_network_profile(
                os.getenv("KX_NETWORK_PROFILE", DEFAULT_NETWORK_PROFILE.value)
            ),
            exposure_mode=parse_exposure_mode(
                os.getenv("KX_EXPOSURE_MODE", DEFAULT_EXPOSURE_MODE.value)
            ),
            public_mode_enabled=public_enabled,
            public_mode_expires_at=(
                parse_datetime_utc(expires_at_raw)
                if expires_at_raw
                else None
            ),
            public_mode_duration_hours=(
                int(duration_raw)
                if duration_raw
                else None
            ),
            host=os.getenv("KX_HOST", "").strip(),
            requested_by=os.getenv("KX_REQUESTED_BY", "system").strip() or "system",
            reason=os.getenv("KX_EXPOSURE_REASON", "").strip(),
        )


@dataclass(frozen=True)
class ExposurePlan:
    """Validated exposure plan for Agent network modules."""

    network_profile: NetworkProfile
    exposure_mode: ExposureMode
    action: ExposureAction
    public_mode_enabled: bool
    public_mode_expires_at: datetime | None
    host: str
    allowed_public_ports: tuple[int, ...]
    forbidden_public_ports: tuple[int, ...]
    risk: ExposureRisk
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_public(self) -> bool:
        return self.exposure_mode in {
            ExposureMode.TEMPORARY_TUNNEL,
            ExposureMode.PUBLIC,
        }

    @property
    def is_expired(self) -> bool:
        return (
            self.public_mode_expires_at is not None
            and utc_now() >= self.public_mode_expires_at
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["network_profile"] = self.network_profile.value
        data["exposure_mode"] = self.exposure_mode.value
        data["action"] = self.action.value
        data["risk"] = self.risk.value
        data["public_mode_expires_at"] = (
            self.public_mode_expires_at.isoformat()
            if self.public_mode_expires_at
            else None
        )
        return data


@dataclass(frozen=True)
class ExposurePolicy:
    """Canonical exposure policy matrix."""

    allowed_modes_by_profile: Mapping[NetworkProfile, tuple[ExposureMode, ...]]
    default_mode_by_profile: Mapping[NetworkProfile, ExposureMode]
    action_by_profile_mode: Mapping[tuple[NetworkProfile, ExposureMode], ExposureAction]
    allowed_public_ports: tuple[int, ...] = (80, 443)
    forbidden_public_ports: tuple[int, ...] = (
        3000,
        5000,
        5432,
        6379,
        5555,
        8000,
    )
    max_temporary_public_hours: int = 24

    @classmethod
    def canonical(cls) -> "ExposurePolicy":
        """Return the canonical Konnaxion exposure policy."""

        allowed_modes_by_profile = {
            NetworkProfile.LOCAL_ONLY: (ExposureMode.PRIVATE,),
            NetworkProfile.INTRANET_PRIVATE: (
                ExposureMode.PRIVATE,
                ExposureMode.LAN,
            ),
            NetworkProfile.PRIVATE_TUNNEL: (
                ExposureMode.PRIVATE,
                ExposureMode.VPN,
            ),
            NetworkProfile.PUBLIC_TEMPORARY: (
                ExposureMode.TEMPORARY_TUNNEL,
            ),
            NetworkProfile.PUBLIC_VPS: (
                ExposureMode.PUBLIC,
            ),
            NetworkProfile.OFFLINE: (
                ExposureMode.PRIVATE,
            ),
        }

        default_mode_by_profile = {
            NetworkProfile.LOCAL_ONLY: ExposureMode.PRIVATE,
            NetworkProfile.INTRANET_PRIVATE: ExposureMode.PRIVATE,
            NetworkProfile.PRIVATE_TUNNEL: ExposureMode.VPN,
            NetworkProfile.PUBLIC_TEMPORARY: ExposureMode.TEMPORARY_TUNNEL,
            NetworkProfile.PUBLIC_VPS: ExposureMode.PUBLIC,
            NetworkProfile.OFFLINE: ExposureMode.PRIVATE,
        }

        action_by_profile_mode = {
            (NetworkProfile.LOCAL_ONLY, ExposureMode.PRIVATE): ExposureAction.SET_LOCAL_ONLY,
            (NetworkProfile.INTRANET_PRIVATE, ExposureMode.PRIVATE): ExposureAction.KEEP_PRIVATE,
            (NetworkProfile.INTRANET_PRIVATE, ExposureMode.LAN): ExposureAction.SET_LAN,
            (NetworkProfile.PRIVATE_TUNNEL, ExposureMode.PRIVATE): ExposureAction.KEEP_PRIVATE,
            (NetworkProfile.PRIVATE_TUNNEL, ExposureMode.VPN): ExposureAction.SET_VPN,
            (NetworkProfile.PUBLIC_TEMPORARY, ExposureMode.TEMPORARY_TUNNEL): ExposureAction.SET_TEMPORARY_TUNNEL,
            (NetworkProfile.PUBLIC_VPS, ExposureMode.PUBLIC): ExposureAction.SET_PUBLIC_VPS,
            (NetworkProfile.OFFLINE, ExposureMode.PRIVATE): ExposureAction.SET_OFFLINE,
        }

        return cls(
            allowed_modes_by_profile=allowed_modes_by_profile,
            default_mode_by_profile=default_mode_by_profile,
            action_by_profile_mode=action_by_profile_mode,
        )


def build_exposure_plan(
    request: ExposureRequest,
    *,
    policy: ExposurePolicy | None = None,
    now: datetime | None = None,
) -> ExposurePlan:
    """
    Validate an exposure request and return an executable plan.

    Raises ExposurePolicyError for unsafe or non-canonical combinations.
    """

    active_policy = policy or ExposurePolicy.canonical()
    current_time = normalize_datetime_utc(now or utc_now())

    validate_profile_mode(request, active_policy)
    expires_at = resolve_expiration(request, active_policy, now=current_time)
    warnings = collect_warnings(request, expires_at, now=current_time)

    if expires_at is not None and current_time >= expires_at:
        return ExposurePlan(
            network_profile=request.network_profile,
            exposure_mode=ExposureMode.PRIVATE,
            action=ExposureAction.EXPIRE_PUBLIC_MODE,
            public_mode_enabled=False,
            public_mode_expires_at=expires_at,
            host=request.host,
            allowed_public_ports=active_policy.allowed_public_ports,
            forbidden_public_ports=active_policy.forbidden_public_ports,
            risk=ExposureRisk.LOW,
            warnings=("Temporary public exposure has expired; reverting to private.",),
            metadata={
                "requested_by": request.requested_by,
                "reason": request.reason,
                "original_profile": request.network_profile.value,
                "original_exposure_mode": request.exposure_mode.value,
            },
        )

    risk = classify_risk(request)

    action = active_policy.action_by_profile_mode.get(
        (request.network_profile, request.exposure_mode)
    )

    if action is None:
        raise ExposurePolicyError(
            "No canonical action is defined for "
            f"profile={request.network_profile.value} "
            f"mode={request.exposure_mode.value}."
        )

    return ExposurePlan(
        network_profile=request.network_profile,
        exposure_mode=request.exposure_mode,
        action=action,
        public_mode_enabled=request.public_mode_enabled,
        public_mode_expires_at=expires_at,
        host=request.host,
        allowed_public_ports=active_policy.allowed_public_ports,
        forbidden_public_ports=active_policy.forbidden_public_ports,
        risk=risk,
        warnings=warnings,
        metadata={
            "requested_by": request.requested_by,
            "reason": request.reason,
        },
    )


def private_default_plan(host: str = "") -> ExposurePlan:
    """Return the safe default Konnaxion exposure plan."""

    request = ExposureRequest(
        network_profile=DEFAULT_NETWORK_PROFILE,
        exposure_mode=DEFAULT_EXPOSURE_MODE,
        public_mode_enabled=False,
        host=host,
        requested_by="system",
        reason="private default",
    )
    return build_exposure_plan(request)


def plan_from_environment() -> ExposurePlan:
    """Validate and build an exposure plan from current process environment."""

    return build_exposure_plan(ExposureRequest.from_environment())


def validate_profile_mode(
    request: ExposureRequest,
    policy: ExposurePolicy,
) -> None:
    """Validate profile/mode/public flag consistency."""

    allowed_modes = policy.allowed_modes_by_profile.get(request.network_profile)

    if not allowed_modes:
        raise ExposurePolicyError(
            f"Unsupported network profile: {request.network_profile.value}"
        )

    if request.exposure_mode not in allowed_modes:
        allowed = ", ".join(mode.value for mode in allowed_modes)
        raise ExposurePolicyError(
            f"KX_EXPOSURE_MODE={request.exposure_mode.value} is not allowed for "
            f"KX_NETWORK_PROFILE={request.network_profile.value}. "
            f"Allowed: {allowed}."
        )

    if request.network_profile == NetworkProfile.PUBLIC_TEMPORARY:
        if request.exposure_mode != ExposureMode.TEMPORARY_TUNNEL:
            raise ExposurePolicyError(
                "public_temporary requires KX_EXPOSURE_MODE=temporary_tunnel."
            )

        if not request.public_mode_enabled:
            raise ExposurePolicyError(
                "public_temporary requires KX_PUBLIC_MODE_ENABLED=true."
            )

    if request.network_profile == NetworkProfile.PUBLIC_VPS:
        if request.exposure_mode != ExposureMode.PUBLIC:
            raise ExposurePolicyError(
                "public_vps requires KX_EXPOSURE_MODE=public."
            )

        if not request.public_mode_enabled:
            raise ExposurePolicyError(
                "public_vps requires KX_PUBLIC_MODE_ENABLED=true."
            )

    if request.public_mode_enabled and request.exposure_mode not in {
        ExposureMode.TEMPORARY_TUNNEL,
        ExposureMode.PUBLIC,
    }:
        raise ExposurePolicyError(
            "KX_PUBLIC_MODE_ENABLED=true is only valid for temporary_tunnel or public exposure."
        )

    if request.network_profile == NetworkProfile.OFFLINE and request.host:
        raise ExposurePolicyError("offline profile must not configure KX_HOST.")


def resolve_expiration(
    request: ExposureRequest,
    policy: ExposurePolicy,
    *,
    now: datetime,
) -> datetime | None:
    """Resolve and validate public-mode expiration."""

    if request.exposure_mode == ExposureMode.TEMPORARY_TUNNEL:
        expires_at = request.public_mode_expires_at

        if expires_at is None and request.public_mode_duration_hours is not None:
            expires_at = now + timedelta(hours=request.public_mode_duration_hours)

        if expires_at is None:
            raise ExposurePolicyError(
                "KX_PUBLIC_MODE_EXPIRES_AT is mandatory for temporary public exposure."
            )

        expires_at = normalize_datetime_utc(expires_at)

        if expires_at <= now:
            raise ExposurePolicyError(
                "KX_PUBLIC_MODE_EXPIRES_AT must be in the future for temporary public exposure."
            )

        max_expires_at = now + timedelta(hours=policy.max_temporary_public_hours)

        if expires_at > max_expires_at:
            raise ExposurePolicyError(
                "Temporary public exposure exceeds maximum duration of "
                f"{policy.max_temporary_public_hours} hours."
            )

        return expires_at

    if request.exposure_mode == ExposureMode.PUBLIC:
        if request.public_mode_expires_at is not None:
            return normalize_datetime_utc(request.public_mode_expires_at)

        return None

    if request.public_mode_expires_at is not None:
        raise ExposurePolicyError(
            "KX_PUBLIC_MODE_EXPIRES_AT is only valid for public exposure modes."
        )

    return None


def collect_warnings(
    request: ExposureRequest,
    expires_at: datetime | None,
    *,
    now: datetime,
) -> tuple[str, ...]:
    """Collect non-blocking warnings for valid exposure plans."""

    warnings: list[str] = []

    if request.exposure_mode == ExposureMode.PUBLIC:
        warnings.append("Public VPS exposure must be protected by hardened firewall and SSH policy.")

    if request.exposure_mode == ExposureMode.TEMPORARY_TUNNEL and expires_at is not None:
        remaining = expires_at - now
        if remaining <= timedelta(hours=1):
            warnings.append("Temporary public exposure expires in one hour or less.")

    if request.network_profile == NetworkProfile.INTRANET_PRIVATE and not request.host:
        warnings.append("KX_HOST is empty; Manager may not be able to display a usable LAN URL.")

    if request.exposure_mode == ExposureMode.VPN and not request.host:
        warnings.append("KX_HOST is empty; private tunnel URL is not configured.")

    return tuple(warnings)


def classify_risk(request: ExposureRequest) -> ExposureRisk:
    """Classify exposure risk."""

    if request.network_profile == NetworkProfile.OFFLINE:
        return ExposureRisk.NONE

    if request.exposure_mode == ExposureMode.PRIVATE:
        return ExposureRisk.LOW

    if request.exposure_mode in {ExposureMode.LAN, ExposureMode.VPN}:
        return ExposureRisk.MEDIUM

    if request.exposure_mode in {
        ExposureMode.TEMPORARY_TUNNEL,
        ExposureMode.PUBLIC,
    }:
        return ExposureRisk.HIGH

    return ExposureRisk.UNKNOWN  # type: ignore[attr-defined]


def default_exposure_mode_for_profile(
    network_profile: NetworkProfile | str,
    *,
    policy: ExposurePolicy | None = None,
) -> ExposureMode:
    """Return the canonical default exposure mode for a profile."""

    active_policy = policy or ExposurePolicy.canonical()
    profile = parse_network_profile(network_profile)
    return active_policy.default_mode_by_profile[profile]


def is_public_exposure(mode: ExposureMode | str) -> bool:
    """Return True if the exposure mode is externally public."""

    exposure_mode = parse_exposure_mode(mode)
    return exposure_mode in {ExposureMode.TEMPORARY_TUNNEL, ExposureMode.PUBLIC}


def is_private_profile(profile: NetworkProfile | str) -> bool:
    """Return True if profile is non-public by design."""

    network_profile = parse_network_profile(profile)
    return network_profile in {
        NetworkProfile.LOCAL_ONLY,
        NetworkProfile.INTRANET_PRIVATE,
        NetworkProfile.PRIVATE_TUNNEL,
        NetworkProfile.OFFLINE,
    }


def should_expire_public_mode(plan: ExposurePlan, *, now: datetime | None = None) -> bool:
    """Return True when a plan's temporary public mode should be expired."""

    if plan.public_mode_expires_at is None:
        return False

    if plan.exposure_mode != ExposureMode.TEMPORARY_TUNNEL:
        return False

    return normalize_datetime_utc(now or utc_now()) >= plan.public_mode_expires_at


def expired_private_request(previous_plan: ExposurePlan) -> ExposureRequest:
    """Build a safe private request after temporary public exposure expires."""

    return ExposureRequest(
        network_profile=NetworkProfile.INTRANET_PRIVATE,
        exposure_mode=ExposureMode.PRIVATE,
        public_mode_enabled=False,
        public_mode_expires_at=None,
        host=previous_plan.host,
        requested_by="system",
        reason="temporary public exposure expired",
    )


def parse_network_profile(value: NetworkProfile | str) -> NetworkProfile:
    """Parse a canonical network profile."""

    if isinstance(value, NetworkProfile):
        return value

    normalized = str(value).strip()

    try:
        return NetworkProfile(normalized)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in NetworkProfile)
        raise ExposurePolicyError(
            f"Invalid KX_NETWORK_PROFILE={value!r}. Allowed: {allowed}."
        ) from exc


def parse_exposure_mode(value: ExposureMode | str) -> ExposureMode:
    """Parse a canonical exposure mode."""

    if isinstance(value, ExposureMode):
        return value

    normalized = str(value).strip()

    try:
        return ExposureMode(normalized)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ExposureMode)
        raise ExposurePolicyError(
            f"Invalid KX_EXPOSURE_MODE={value!r}. Allowed: {allowed}."
        ) from exc


def parse_datetime_utc(value: str) -> datetime:
    """Parse an ISO-8601 datetime and normalize to UTC."""

    raw = value.strip()

    if not raw:
        raise ExposurePolicyError("Datetime value cannot be empty.")

    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ExposurePolicyError(f"Invalid datetime: {value!r}") from exc

    return normalize_datetime_utc(parsed)


def normalize_datetime_utc(value: datetime) -> datetime:
    """Normalize naive or aware datetimes to UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def utc_now() -> datetime:
    """Return current UTC time."""

    return datetime.now(tz=UTC)


def read_bool(value: str, *, key: str = "value") -> bool:
    """Parse a strict boolean string."""

    normalized = str(value).strip().lower()

    if normalized in {"1", "true", "yes", "y", "on"}:
        return True

    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    raise ExposurePolicyError(f"{key} must be a boolean value.")


def serialize_env_updates(plan: ExposurePlan) -> dict[str, str]:
    """Return KX_* environment updates implied by an exposure plan."""

    return {
        "KX_NETWORK_PROFILE": plan.network_profile.value,
        "KX_EXPOSURE_MODE": plan.exposure_mode.value,
        "KX_PUBLIC_MODE_ENABLED": "true" if plan.public_mode_enabled else "false",
        "KX_PUBLIC_MODE_EXPIRES_AT": (
            plan.public_mode_expires_at.isoformat()
            if plan.public_mode_expires_at
            else ""
        ),
        "KX_HOST": plan.host,
    }


def assert_safe_to_start(plan: ExposurePlan) -> None:
    """Raise if an exposure plan is not safe for runtime startup."""

    if plan.action == ExposureAction.EXPIRE_PUBLIC_MODE:
        raise ExposurePolicyError(
            "Temporary public exposure is expired; apply private fallback before startup."
        )

    if plan.is_expired:
        raise ExposurePolicyError(
            "Exposure plan is expired; apply private fallback before startup."
        )

    if plan.exposure_mode == ExposureMode.TEMPORARY_TUNNEL and not plan.public_mode_expires_at:
        raise ExposurePolicyError(
            "Temporary public exposure cannot start without expiration."
        )

    if plan.risk == ExposureRisk.BLOCKED:
        raise ExposurePolicyError("Exposure plan is blocked.")
