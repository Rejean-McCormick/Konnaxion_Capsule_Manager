"""
Canonical Konnaxion Instance data models.

This module defines the file-level model used by the Agent, Manager API, CLI,
runtime writer, healthchecks, backup/restore flow, and Security Gate reporting.

The model stores canonical enum values from kx_shared.konnaxion_constants and
keeps all mutable instance state separate from immutable capsule metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from kx_shared.konnaxion_constants import (
    APP_VERSION,
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_VERSION,
    DEFAULT_EXPOSURE_MODE,
    DEFAULT_INSTANCE_ID,
    DEFAULT_NETWORK_PROFILE,
    DEFAULT_PUBLIC_MODE_ENABLED,
    DEFAULT_RELEASE_ID,
    DockerService,
    ExposureMode,
    InstanceState,
    NetworkProfile,
    PARAM_VERSION,
    ROUTES,
    SecurityGateCheck,
    SecurityGateStatus,
    instance_backup_root,
    instance_compose_file,
    instance_env_dir,
    instance_local_backups_dir,
    instance_logs_dir,
    instance_media_dir,
    instance_postgres_dir,
    instance_redis_dir,
    instance_root,
    instance_state_dir,
    is_canonical_exposure_mode,
    is_canonical_network_profile,
    is_canonical_service,
    is_public_mode,
    require_public_expiration,
)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def utc_now() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(UTC)


def datetime_to_iso(value: datetime | None) -> str | None:
    """Serialize a datetime as ISO-8601 UTC string."""
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def datetime_from_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime string."""
    if not value:
        return None

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed.astimezone(UTC)


def enum_value(value: Any) -> Any:
    """Return enum.value when available, otherwise value."""
    return getattr(value, "value", value)


def require_non_empty(value: str, *, field_name: str) -> str:
    """Validate that a string field is not empty."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def normalize_network_profile(value: str | NetworkProfile) -> NetworkProfile:
    """Return a canonical NetworkProfile enum."""
    raw = enum_value(value)
    if not is_canonical_network_profile(raw):
        raise ValueError(f"Unknown network profile: {raw}")
    return NetworkProfile(raw)


def normalize_exposure_mode(value: str | ExposureMode) -> ExposureMode:
    """Return a canonical ExposureMode enum."""
    raw = enum_value(value)
    if not is_canonical_exposure_mode(raw):
        raise ValueError(f"Unknown exposure mode: {raw}")
    return ExposureMode(raw)


def normalize_instance_state(value: str | InstanceState) -> InstanceState:
    """Return a canonical InstanceState enum."""
    raw = enum_value(value)
    return InstanceState(raw)


def normalize_service(value: str | DockerService) -> DockerService:
    """Return a canonical DockerService enum."""
    raw = enum_value(value)
    if not is_canonical_service(raw):
        raise ValueError(f"Unknown Docker service: {raw}")
    return DockerService(raw)


def normalize_security_status(value: str | SecurityGateStatus) -> SecurityGateStatus:
    """Return a canonical SecurityGateStatus enum."""
    raw = enum_value(value)
    return SecurityGateStatus(raw)


def normalize_security_check(value: str | SecurityGateCheck) -> SecurityGateCheck:
    """Return a canonical SecurityGateCheck enum."""
    raw = enum_value(value)
    return SecurityGateCheck(raw)


# ---------------------------------------------------------------------------
# Capsule and release references
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CapsuleRef:
    """Immutable reference to the capsule used by an instance."""

    capsule_id: str = DEFAULT_CAPSULE_ID
    capsule_version: str = DEFAULT_CAPSULE_VERSION
    app_version: str = APP_VERSION
    param_version: str = PARAM_VERSION
    channel: str = "demo"
    path: str | None = None
    checksum: str | None = None
    signature_verified: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "capsule_id", require_non_empty(self.capsule_id, field_name="capsule_id"))
        object.__setattr__(
            self,
            "capsule_version",
            require_non_empty(self.capsule_version, field_name="capsule_version"),
        )
        object.__setattr__(self, "app_version", require_non_empty(self.app_version, field_name="app_version"))
        object.__setattr__(
            self,
            "param_version",
            require_non_empty(self.param_version, field_name="param_version"),
        )
        object.__setattr__(self, "channel", require_non_empty(self.channel, field_name="channel"))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to primitive dict."""
        return {
            "capsule_id": self.capsule_id,
            "capsule_version": self.capsule_version,
            "app_version": self.app_version,
            "param_version": self.param_version,
            "channel": self.channel,
            "path": self.path,
            "checksum": self.checksum,
            "signature_verified": self.signature_verified,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CapsuleRef":
        """Deserialize from primitive dict."""
        return cls(
            capsule_id=str(data.get("capsule_id", DEFAULT_CAPSULE_ID)),
            capsule_version=str(data.get("capsule_version", DEFAULT_CAPSULE_VERSION)),
            app_version=str(data.get("app_version", APP_VERSION)),
            param_version=str(data.get("param_version", PARAM_VERSION)),
            channel=str(data.get("channel", "demo")),
            path=data.get("path"),
            checksum=data.get("checksum"),
            signature_verified=bool(data.get("signature_verified", False)),
        )


@dataclass(frozen=True)
class ReleaseRef:
    """Reference to a release directory or current release pointer."""

    release_id: str = DEFAULT_RELEASE_ID
    previous_release_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "release_id", require_non_empty(self.release_id, field_name="release_id"))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to primitive dict."""
        return {
            "release_id": self.release_id,
            "previous_release_id": self.previous_release_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReleaseRef":
        """Deserialize from primitive dict."""
        return cls(
            release_id=str(data.get("release_id", DEFAULT_RELEASE_ID)),
            previous_release_id=data.get("previous_release_id"),
        )


# ---------------------------------------------------------------------------
# Network and routing
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NetworkConfig:
    """Canonical network profile and exposure configuration for an instance."""

    profile: NetworkProfile = DEFAULT_NETWORK_PROFILE
    exposure_mode: ExposureMode = DEFAULT_EXPOSURE_MODE
    public_mode_enabled: bool = DEFAULT_PUBLIC_MODE_ENABLED
    public_mode_expires_at: datetime | None = None
    host: str | None = None
    routes: dict[str, str] = field(default_factory=lambda: dict(ROUTES))

    def __post_init__(self) -> None:
        profile = normalize_network_profile(self.profile)
        exposure_mode = normalize_exposure_mode(self.exposure_mode)

        object.__setattr__(self, "profile", profile)
        object.__setattr__(self, "exposure_mode", exposure_mode)

        if self.public_mode_enabled or is_public_mode(profile, exposure_mode):
            require_public_expiration(
                public_mode_enabled=True,
                expires_at=datetime_to_iso(self.public_mode_expires_at),
            )

        if exposure_mode == ExposureMode.PUBLIC and profile != NetworkProfile.PUBLIC_VPS:
            raise ValueError("public exposure mode requires public_vps network profile.")

        if profile == NetworkProfile.PUBLIC_TEMPORARY and exposure_mode != ExposureMode.TEMPORARY_TUNNEL:
            raise ValueError("public_temporary profile requires temporary_tunnel exposure mode.")

        for route, service in self.routes.items():
            if not route.startswith("/"):
                raise ValueError(f"Route must start with '/': {route}")
            if not is_canonical_service(service):
                raise ValueError(f"Route {route} targets non-canonical service: {service}")

    @property
    def is_public(self) -> bool:
        """Return True if this network config implies public exposure."""
        return self.public_mode_enabled or is_public_mode(self.profile, self.exposure_mode)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to primitive dict."""
        return {
            "profile": self.profile.value,
            "exposure_mode": self.exposure_mode.value,
            "public_mode_enabled": self.public_mode_enabled,
            "public_mode_expires_at": datetime_to_iso(self.public_mode_expires_at),
            "host": self.host,
            "routes": dict(self.routes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "NetworkConfig":
        """Deserialize from primitive dict."""
        return cls(
            profile=normalize_network_profile(str(data.get("profile", DEFAULT_NETWORK_PROFILE.value))),
            exposure_mode=normalize_exposure_mode(
                str(data.get("exposure_mode", DEFAULT_EXPOSURE_MODE.value))
            ),
            public_mode_enabled=bool(data.get("public_mode_enabled", False)),
            public_mode_expires_at=datetime_from_iso(data.get("public_mode_expires_at")),
            host=data.get("host"),
            routes=dict(data.get("routes", ROUTES)),
        )


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InstancePaths:
    """Resolved canonical paths for an instance."""

    instance_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "instance_id",
            require_non_empty(self.instance_id, field_name="instance_id"),
        )

    @property
    def root(self) -> Path:
        return instance_root(self.instance_id)

    @property
    def env(self) -> Path:
        return instance_env_dir(self.instance_id)

    @property
    def postgres(self) -> Path:
        return instance_postgres_dir(self.instance_id)

    @property
    def redis(self) -> Path:
        return instance_redis_dir(self.instance_id)

    @property
    def media(self) -> Path:
        return instance_media_dir(self.instance_id)

    @property
    def logs(self) -> Path:
        return instance_logs_dir(self.instance_id)

    @property
    def local_backups(self) -> Path:
        return instance_local_backups_dir(self.instance_id)

    @property
    def state(self) -> Path:
        return instance_state_dir(self.instance_id)

    @property
    def compose_file(self) -> Path:
        return instance_compose_file(self.instance_id)

    @property
    def backup_root(self) -> Path:
        return instance_backup_root(self.instance_id)

    def to_dict(self) -> dict[str, str]:
        """Serialize paths to string values."""
        return {
            "root": str(self.root),
            "env": str(self.env),
            "postgres": str(self.postgres),
            "redis": str(self.redis),
            "media": str(self.media),
            "logs": str(self.logs),
            "local_backups": str(self.local_backups),
            "state": str(self.state),
            "compose_file": str(self.compose_file),
            "backup_root": str(self.backup_root),
        }


# ---------------------------------------------------------------------------
# Runtime services and health
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ServiceStatus:
    """Runtime status of one canonical Docker service."""

    service: DockerService
    desired: bool = True
    running: bool = False
    healthy: bool | None = None
    container_id: str | None = None
    image: str | None = None
    ports: tuple[int, ...] = field(default_factory=tuple)
    message: str | None = None
    checked_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "service", normalize_service(self.service))
        object.__setattr__(self, "ports", tuple(int(port) for port in self.ports))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to primitive dict."""
        return {
            "service": self.service.value,
            "desired": self.desired,
            "running": self.running,
            "healthy": self.healthy,
            "container_id": self.container_id,
            "image": self.image,
            "ports": list(self.ports),
            "message": self.message,
            "checked_at": datetime_to_iso(self.checked_at),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ServiceStatus":
        """Deserialize from primitive dict."""
        return cls(
            service=normalize_service(str(data["service"])),
            desired=bool(data.get("desired", True)),
            running=bool(data.get("running", False)),
            healthy=data.get("healthy"),
            container_id=data.get("container_id"),
            image=data.get("image"),
            ports=tuple(int(port) for port in data.get("ports", ())),
            message=data.get("message"),
            checked_at=datetime_from_iso(data.get("checked_at")),
        )


@dataclass(frozen=True)
class HealthSummary:
    """Aggregated instance health."""

    healthy: bool = False
    ready: bool = False
    services: tuple[ServiceStatus, ...] = field(default_factory=tuple)
    message: str | None = None
    checked_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to primitive dict."""
        return {
            "healthy": self.healthy,
            "ready": self.ready,
            "services": [service.to_dict() for service in self.services],
            "message": self.message,
            "checked_at": datetime_to_iso(self.checked_at),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HealthSummary":
        """Deserialize from primitive dict."""
        return cls(
            healthy=bool(data.get("healthy", False)),
            ready=bool(data.get("ready", False)),
            services=tuple(
                ServiceStatus.from_dict(service)
                for service in data.get("services", ())
            ),
            message=data.get("message"),
            checked_at=datetime_from_iso(data.get("checked_at")),
        )


# ---------------------------------------------------------------------------
# Security Gate result models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SecurityGateCheckResult:
    """Result of one Security Gate check."""

    check: SecurityGateCheck
    status: SecurityGateStatus
    message: str | None = None
    blocking: bool = False
    details: dict[str, Any] = field(default_factory=dict)
    checked_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "check", normalize_security_check(self.check))
        object.__setattr__(self, "status", normalize_security_status(self.status))

    @property
    def failed_blocking(self) -> bool:
        """Return True when this result blocks startup."""
        return self.blocking and self.status == SecurityGateStatus.FAIL_BLOCKING

    def to_dict(self) -> dict[str, Any]:
        """Serialize to primitive dict."""
        return {
            "check": self.check.value,
            "status": self.status.value,
            "message": self.message,
            "blocking": self.blocking,
            "details": dict(self.details),
            "checked_at": datetime_to_iso(self.checked_at),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SecurityGateCheckResult":
        """Deserialize from primitive dict."""
        return cls(
            check=normalize_security_check(str(data["check"])),
            status=normalize_security_status(str(data["status"])),
            message=data.get("message"),
            blocking=bool(data.get("blocking", False)),
            details=dict(data.get("details", {})),
            checked_at=datetime_from_iso(data.get("checked_at")),
        )


@dataclass(frozen=True)
class SecurityGateSummary:
    """Aggregated Security Gate status for an instance."""

    status: SecurityGateStatus = SecurityGateStatus.UNKNOWN
    checks: tuple[SecurityGateCheckResult, ...] = field(default_factory=tuple)
    checked_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", normalize_security_status(self.status))

    @property
    def passed(self) -> bool:
        """Return True if the Security Gate passed."""
        return self.status == SecurityGateStatus.PASS

    @property
    def blocking_failures(self) -> tuple[SecurityGateCheckResult, ...]:
        """Return blocking failures."""
        return tuple(check for check in self.checks if check.failed_blocking)

    def derive_status(self) -> SecurityGateStatus:
        """Derive aggregate status from check results."""
        if any(check.failed_blocking for check in self.checks):
            return SecurityGateStatus.FAIL_BLOCKING
        if any(check.status == SecurityGateStatus.UNKNOWN for check in self.checks):
            return SecurityGateStatus.UNKNOWN
        if any(check.status == SecurityGateStatus.WARN for check in self.checks):
            return SecurityGateStatus.WARN
        if self.checks and all(
            check.status in {SecurityGateStatus.PASS, SecurityGateStatus.SKIPPED}
            for check in self.checks
        ):
            return SecurityGateStatus.PASS
        return self.status

    def with_derived_status(self) -> "SecurityGateSummary":
        """Return a copy with aggregate status derived from checks."""
        return SecurityGateSummary(
            status=self.derive_status(),
            checks=self.checks,
            checked_at=self.checked_at or utc_now(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to primitive dict."""
        return {
            "status": self.status.value,
            "checks": [check.to_dict() for check in self.checks],
            "checked_at": datetime_to_iso(self.checked_at),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SecurityGateSummary":
        """Deserialize from primitive dict."""
        return cls(
            status=normalize_security_status(str(data.get("status", SecurityGateStatus.UNKNOWN.value))),
            checks=tuple(
                SecurityGateCheckResult.from_dict(check)
                for check in data.get("checks", ())
            ),
            checked_at=datetime_from_iso(data.get("checked_at")),
        )


# ---------------------------------------------------------------------------
# Main instance model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InstanceModel:
    """Canonical Konnaxion Instance model."""

    instance_id: str = DEFAULT_INSTANCE_ID
    state: InstanceState = InstanceState.CREATED
    capsule: CapsuleRef = field(default_factory=CapsuleRef)
    release: ReleaseRef = field(default_factory=ReleaseRef)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    health: HealthSummary = field(default_factory=HealthSummary)
    security_gate: SecurityGateSummary = field(default_factory=SecurityGateSummary)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    last_backup_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "instance_id",
            require_non_empty(self.instance_id, field_name="instance_id"),
        )
        object.__setattr__(self, "state", normalize_instance_state(self.state))

    @property
    def paths(self) -> InstancePaths:
        """Return resolved canonical paths for this instance."""
        return InstancePaths(self.instance_id)

    @property
    def can_start(self) -> bool:
        """Return True if the current state allows startup."""
        return self.state in {
            InstanceState.CREATED,
            InstanceState.READY,
            InstanceState.STOPPED,
            InstanceState.DEGRADED,
        }

    @property
    def is_running(self) -> bool:
        """Return True if instance state is running."""
        return self.state == InstanceState.RUNNING

    @property
    def is_terminal_failure(self) -> bool:
        """Return True if instance is failed or security-blocked."""
        return self.state in {InstanceState.FAILED, InstanceState.SECURITY_BLOCKED}

    def transition(self, new_state: InstanceState | str) -> "InstanceModel":
        """Return a copy with a new canonical state and updated timestamps."""
        state = normalize_instance_state(new_state)
        now = utc_now()

        started_at = self.started_at
        stopped_at = self.stopped_at

        if state == InstanceState.RUNNING and started_at is None:
            started_at = now

        if state == InstanceState.STOPPED:
            stopped_at = now

        return InstanceModel(
            instance_id=self.instance_id,
            state=state,
            capsule=self.capsule,
            release=self.release,
            network=self.network,
            health=self.health,
            security_gate=self.security_gate,
            created_at=self.created_at,
            updated_at=now,
            started_at=started_at,
            stopped_at=stopped_at,
            last_backup_id=self.last_backup_id,
            metadata=dict(self.metadata),
        )

    def with_security_gate(self, security_gate: SecurityGateSummary) -> "InstanceModel":
        """Return a copy with updated Security Gate summary."""
        state = self.state
        derived = security_gate.with_derived_status()

        if derived.status == SecurityGateStatus.FAIL_BLOCKING:
            state = InstanceState.SECURITY_BLOCKED

        return InstanceModel(
            instance_id=self.instance_id,
            state=state,
            capsule=self.capsule,
            release=self.release,
            network=self.network,
            health=self.health,
            security_gate=derived,
            created_at=self.created_at,
            updated_at=utc_now(),
            started_at=self.started_at,
            stopped_at=self.stopped_at,
            last_backup_id=self.last_backup_id,
            metadata=dict(self.metadata),
        )

    def with_health(self, health: HealthSummary) -> "InstanceModel":
        """Return a copy with updated health summary."""
        state = self.state

        if self.state == InstanceState.RUNNING and not health.healthy:
            state = InstanceState.DEGRADED

        return InstanceModel(
            instance_id=self.instance_id,
            state=state,
            capsule=self.capsule,
            release=self.release,
            network=self.network,
            health=health,
            security_gate=self.security_gate,
            created_at=self.created_at,
            updated_at=utc_now(),
            started_at=self.started_at,
            stopped_at=self.stopped_at,
            last_backup_id=self.last_backup_id,
            metadata=dict(self.metadata),
        )

    def with_last_backup(self, backup_id: str) -> "InstanceModel":
        """Return a copy with updated last backup ID."""
        return InstanceModel(
            instance_id=self.instance_id,
            state=self.state,
            capsule=self.capsule,
            release=self.release,
            network=self.network,
            health=self.health,
            security_gate=self.security_gate,
            created_at=self.created_at,
            updated_at=utc_now(),
            started_at=self.started_at,
            stopped_at=self.stopped_at,
            last_backup_id=require_non_empty(backup_id, field_name="backup_id"),
            metadata=dict(self.metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the instance model to primitive dict."""
        return {
            "instance_id": self.instance_id,
            "state": self.state.value,
            "capsule": self.capsule.to_dict(),
            "release": self.release.to_dict(),
            "network": self.network.to_dict(),
            "paths": self.paths.to_dict(),
            "health": self.health.to_dict(),
            "security_gate": self.security_gate.to_dict(),
            "created_at": datetime_to_iso(self.created_at),
            "updated_at": datetime_to_iso(self.updated_at),
            "started_at": datetime_to_iso(self.started_at),
            "stopped_at": datetime_to_iso(self.stopped_at),
            "last_backup_id": self.last_backup_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "InstanceModel":
        """Deserialize the instance model from primitive dict."""
        return cls(
            instance_id=str(data.get("instance_id", DEFAULT_INSTANCE_ID)),
            state=normalize_instance_state(str(data.get("state", InstanceState.CREATED.value))),
            capsule=CapsuleRef.from_dict(data.get("capsule", {})),
            release=ReleaseRef.from_dict(data.get("release", {})),
            network=NetworkConfig.from_dict(data.get("network", {})),
            health=HealthSummary.from_dict(data.get("health", {})),
            security_gate=SecurityGateSummary.from_dict(data.get("security_gate", {})),
            created_at=datetime_from_iso(data.get("created_at")) or utc_now(),
            updated_at=datetime_from_iso(data.get("updated_at")) or utc_now(),
            started_at=datetime_from_iso(data.get("started_at")),
            stopped_at=datetime_from_iso(data.get("stopped_at")),
            last_backup_id=data.get("last_backup_id"),
            metadata=dict(data.get("metadata", {})),
        )


def create_default_instance(instance_id: str = DEFAULT_INSTANCE_ID) -> InstanceModel:
    """Create a default Konnaxion Instance model."""
    return InstanceModel(instance_id=instance_id)


__all__ = [
    "CapsuleRef",
    "HealthSummary",
    "InstanceModel",
    "InstancePaths",
    "NetworkConfig",
    "ReleaseRef",
    "SecurityGateCheckResult",
    "SecurityGateSummary",
    "ServiceStatus",
    "create_default_instance",
    "datetime_from_iso",
    "datetime_to_iso",
    "enum_value",
    "normalize_exposure_mode",
    "normalize_instance_state",
    "normalize_network_profile",
    "normalize_security_check",
    "normalize_security_status",
    "normalize_service",
    "require_non_empty",
    "utc_now",
]
