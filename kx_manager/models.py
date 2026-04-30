"""
Konnaxion Capsule Manager models.

These are Manager-side DTOs/view models used by routes, API responses, UI state,
and Manager-to-Agent client code. They intentionally mirror canonical Agent and
shared values without redefining service names, paths, states, network profiles,
backup statuses, restore statuses, rollback statuses, or Security Gate statuses.

The Manager should treat these models as presentation/API contracts. Host-level
actions still belong to the Konnaxion Agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Sequence

from kx_shared.konnaxion_constants import (
    APP_VERSION,
    CANONICAL_DOCKER_SERVICES,
    CANONICAL_NETWORK_PROFILES,
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_VERSION,
    DEFAULT_EXPOSURE_MODE,
    DEFAULT_INSTANCE_ID,
    DEFAULT_NETWORK_PROFILE,
    DEFAULT_PUBLIC_MODE_ENABLED,
    KX_BACKUPS_ROOT,
    KX_CAPSULES_DIR,
    KX_INSTANCES_DIR,
    BackupStatus,
    DockerService,
    ExposureMode,
    InstanceState,
    NetworkProfile,
    PARAM_VERSION,
    PUBLIC_CLI_COMMANDS,
    RestoreStatus,
    RollbackStatus,
    SecurityGateCheck,
    SecurityGateStatus,
    instance_backup_root,
    instance_compose_file,
    instance_root,
    is_canonical_exposure_mode,
    is_canonical_network_profile,
    is_canonical_service,
)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


def datetime_to_iso(value: datetime | None) -> str | None:
    """Serialize datetime as UTC ISO-8601."""
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def datetime_from_iso(value: str | None) -> datetime | None:
    """Parse ISO-8601 datetime."""
    if not value:
        return None

    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed.astimezone(UTC)


def require_non_empty(value: str, *, field_name: str) -> str:
    """Require a non-empty string."""
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def normalize_instance_state(value: str | InstanceState) -> InstanceState:
    """Return canonical InstanceState."""
    return InstanceState(str(_enum_value(value)))


def normalize_backup_status(value: str | BackupStatus) -> BackupStatus:
    """Return canonical BackupStatus."""
    return BackupStatus(str(_enum_value(value)))


def normalize_restore_status(value: str | RestoreStatus) -> RestoreStatus:
    """Return canonical RestoreStatus."""
    return RestoreStatus(str(_enum_value(value)))


def normalize_rollback_status(value: str | RollbackStatus) -> RollbackStatus:
    """Return canonical RollbackStatus."""
    return RollbackStatus(str(_enum_value(value)))


def normalize_network_profile(value: str | NetworkProfile) -> NetworkProfile:
    """Return canonical NetworkProfile."""
    raw = str(_enum_value(value))
    if not is_canonical_network_profile(raw):
        raise ValueError(f"Unknown network profile: {raw}")
    return NetworkProfile(raw)


def normalize_exposure_mode(value: str | ExposureMode) -> ExposureMode:
    """Return canonical ExposureMode."""
    raw = str(_enum_value(value))
    if not is_canonical_exposure_mode(raw):
        raise ValueError(f"Unknown exposure mode: {raw}")
    return ExposureMode(raw)


def normalize_security_gate_status(value: str | SecurityGateStatus) -> SecurityGateStatus:
    """Return canonical SecurityGateStatus."""
    return SecurityGateStatus(str(_enum_value(value)))


def normalize_security_gate_check(value: str | SecurityGateCheck) -> SecurityGateCheck:
    """Return canonical SecurityGateCheck."""
    return SecurityGateCheck(str(_enum_value(value)))


def normalize_service(value: str | DockerService) -> DockerService:
    """Return canonical DockerService."""
    raw = str(_enum_value(value))
    if not is_canonical_service(raw):
        raise ValueError(f"Unknown Docker service: {raw}")
    return DockerService(raw)


# ---------------------------------------------------------------------------
# Manager UI enums
# ---------------------------------------------------------------------------

class ManagerView(StrEnum):
    """Manager view identifiers."""

    DASHBOARD = "dashboard"
    CAPSULES = "capsules"
    INSTANCE_DETAIL = "instance_detail"
    NETWORK = "network"
    SECURITY = "security"
    BACKUPS = "backups"
    LOGS = "logs"
    SETTINGS = "settings"


class NotificationLevel(StrEnum):
    """UI notification levels."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class AgentConnectionStatus(StrEnum):
    """Manager-to-Agent connection state."""

    UNKNOWN = "unknown"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    UNAUTHORIZED = "unauthorized"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Product/capsule models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProductInfo:
    """Product identity shown by the Manager."""

    product_name: str = "Konnaxion"
    app_version: str = APP_VERSION
    param_version: str = PARAM_VERSION
    manager_name: str = "Konnaxion Capsule Manager"

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_name": self.product_name,
            "app_version": self.app_version,
            "param_version": self.param_version,
            "manager_name": self.manager_name,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProductInfo":
        return cls(
            product_name=str(data.get("product_name", "Konnaxion")),
            app_version=str(data.get("app_version", APP_VERSION)),
            param_version=str(data.get("param_version", PARAM_VERSION)),
            manager_name=str(data.get("manager_name", "Konnaxion Capsule Manager")),
        )


@dataclass(frozen=True)
class CapsuleSummary:
    """Capsule row shown by the Manager."""

    capsule_id: str = DEFAULT_CAPSULE_ID
    capsule_version: str = DEFAULT_CAPSULE_VERSION
    app_version: str = APP_VERSION
    channel: str = "demo"
    path: str | None = None
    imported: bool = False
    signature_verified: bool = False
    checksum_verified: bool = False
    created_at: datetime | None = None
    imported_at: datetime | None = None
    size_bytes: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "capsule_id", require_non_empty(self.capsule_id, field_name="capsule_id"))
        object.__setattr__(
            self,
            "capsule_version",
            require_non_empty(self.capsule_version, field_name="capsule_version"),
        )

        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes must not be negative.")

    @property
    def display_name(self) -> str:
        return f"{self.capsule_id} ({self.capsule_version})"

    @property
    def local_path(self) -> str:
        return self.path or str(KX_CAPSULES_DIR / f"{self.capsule_id}.kxcap")

    def to_dict(self) -> dict[str, Any]:
        return {
            "capsule_id": self.capsule_id,
            "capsule_version": self.capsule_version,
            "app_version": self.app_version,
            "channel": self.channel,
            "path": self.path,
            "local_path": self.local_path,
            "imported": self.imported,
            "signature_verified": self.signature_verified,
            "checksum_verified": self.checksum_verified,
            "created_at": datetime_to_iso(self.created_at),
            "imported_at": datetime_to_iso(self.imported_at),
            "size_bytes": self.size_bytes,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CapsuleSummary":
        return cls(
            capsule_id=str(data.get("capsule_id", DEFAULT_CAPSULE_ID)),
            capsule_version=str(data.get("capsule_version", DEFAULT_CAPSULE_VERSION)),
            app_version=str(data.get("app_version", APP_VERSION)),
            channel=str(data.get("channel", "demo")),
            path=data.get("path"),
            imported=bool(data.get("imported", False)),
            signature_verified=bool(data.get("signature_verified", False)),
            checksum_verified=bool(data.get("checksum_verified", False)),
            created_at=datetime_from_iso(data.get("created_at")),
            imported_at=datetime_from_iso(data.get("imported_at")),
            size_bytes=data.get("size_bytes"),
            metadata=dict(data.get("metadata", {})),
        )


# ---------------------------------------------------------------------------
# Network models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NetworkProfileOption:
    """Selectable network profile in the Manager UI."""

    value: NetworkProfile
    label: str
    description: str
    default: bool = False
    public: bool = False
    requires_expiration: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", normalize_network_profile(self.value))

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value.value,
            "label": self.label,
            "description": self.description,
            "default": self.default,
            "public": self.public,
            "requires_expiration": self.requires_expiration,
        }


NETWORK_PROFILE_OPTIONS: tuple[NetworkProfileOption, ...] = (
    NetworkProfileOption(
        value=NetworkProfile.LOCAL_ONLY,
        label="Local only",
        description="Accessible only from the local machine.",
    ),
    NetworkProfileOption(
        value=NetworkProfile.INTRANET_PRIVATE,
        label="Intranet private",
        description="Accessible from the LAN only.",
        default=True,
    ),
    NetworkProfileOption(
        value=NetworkProfile.PRIVATE_TUNNEL,
        label="Private tunnel",
        description="Accessible through a private tunnel or VPN.",
    ),
    NetworkProfileOption(
        value=NetworkProfile.PUBLIC_TEMPORARY,
        label="Public temporary",
        description="Temporarily exposed for demos with mandatory expiration.",
        public=True,
        requires_expiration=True,
    ),
    NetworkProfileOption(
        value=NetworkProfile.PUBLIC_VPS,
        label="Public VPS",
        description="Full public VPS deployment with hardened 80/443 exposure.",
        public=True,
    ),
    NetworkProfileOption(
        value=NetworkProfile.OFFLINE,
        label="Offline",
        description="No external network exposure.",
    ),
)


@dataclass(frozen=True)
class NetworkState:
    """Network state for one instance."""

    profile: NetworkProfile = DEFAULT_NETWORK_PROFILE
    exposure_mode: ExposureMode = DEFAULT_EXPOSURE_MODE
    public_mode_enabled: bool = DEFAULT_PUBLIC_MODE_ENABLED
    public_mode_expires_at: datetime | None = None
    host: str | None = None
    url: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile", normalize_network_profile(self.profile))
        object.__setattr__(self, "exposure_mode", normalize_exposure_mode(self.exposure_mode))

    @property
    def is_public(self) -> bool:
        return self.public_mode_enabled or self.profile in {
            NetworkProfile.PUBLIC_TEMPORARY,
            NetworkProfile.PUBLIC_VPS,
        } or self.exposure_mode in {
            ExposureMode.TEMPORARY_TUNNEL,
            ExposureMode.PUBLIC,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.value,
            "exposure_mode": self.exposure_mode.value,
            "public_mode_enabled": self.public_mode_enabled,
            "public_mode_expires_at": datetime_to_iso(self.public_mode_expires_at),
            "host": self.host,
            "url": self.url,
            "is_public": self.is_public,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "NetworkState":
        return cls(
            profile=normalize_network_profile(str(data.get("profile", DEFAULT_NETWORK_PROFILE.value))),
            exposure_mode=normalize_exposure_mode(
                str(data.get("exposure_mode", DEFAULT_EXPOSURE_MODE.value))
            ),
            public_mode_enabled=bool(data.get("public_mode_enabled", False)),
            public_mode_expires_at=datetime_from_iso(data.get("public_mode_expires_at")),
            host=data.get("host"),
            url=data.get("url"),
        )


# ---------------------------------------------------------------------------
# Runtime, health, and logs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ServiceView:
    """Manager view of a canonical Docker service."""

    service: DockerService
    running: bool = False
    healthy: bool | None = None
    desired: bool = True
    image: str | None = None
    ports: tuple[int, ...] = field(default_factory=tuple)
    message: str | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "service", normalize_service(self.service))
        object.__setattr__(self, "ports", tuple(int(port) for port in self.ports))

    @property
    def status_label(self) -> str:
        if not self.desired:
            return "disabled"
        if self.healthy is True:
            return "healthy"
        if self.running:
            return "running"
        if self.healthy is False:
            return "unhealthy"
        return "stopped"

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service.value,
            "running": self.running,
            "healthy": self.healthy,
            "desired": self.desired,
            "image": self.image,
            "ports": list(self.ports),
            "message": self.message,
            "status_label": self.status_label,
            "updated_at": datetime_to_iso(self.updated_at),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ServiceView":
        return cls(
            service=normalize_service(str(data["service"])),
            running=bool(data.get("running", False)),
            healthy=data.get("healthy"),
            desired=bool(data.get("desired", True)),
            image=data.get("image"),
            ports=tuple(int(port) for port in data.get("ports", ())),
            message=data.get("message"),
            updated_at=datetime_from_iso(data.get("updated_at") or data.get("checked_at")),
        )


@dataclass(frozen=True)
class HealthView:
    """Manager health summary."""

    healthy: bool = False
    ready: bool = False
    services: tuple[ServiceView, ...] = field(default_factory=tuple)
    message: str | None = None
    checked_at: datetime | None = None

    @property
    def unhealthy_services(self) -> tuple[ServiceView, ...]:
        return tuple(service for service in self.services if service.healthy is False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "ready": self.ready,
            "services": [service.to_dict() for service in self.services],
            "unhealthy_services": [service.service.value for service in self.unhealthy_services],
            "message": self.message,
            "checked_at": datetime_to_iso(self.checked_at),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HealthView":
        return cls(
            healthy=bool(data.get("healthy", False)),
            ready=bool(data.get("ready", False)),
            services=tuple(ServiceView.from_dict(item) for item in data.get("services", ())),
            message=data.get("message"),
            checked_at=datetime_from_iso(data.get("checked_at")),
        )


@dataclass(frozen=True)
class LogEntry:
    """Manager-visible log entry."""

    timestamp: datetime
    level: str
    source: str
    message: str
    service: DockerService | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.service is not None:
            object.__setattr__(self, "service", normalize_service(self.service))
        object.__setattr__(self, "level", str(self.level).upper())
        object.__setattr__(self, "source", require_non_empty(self.source, field_name="source"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": datetime_to_iso(self.timestamp),
            "level": self.level,
            "source": self.source,
            "message": self.message,
            "service": self.service.value if self.service else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LogEntry":
        service = data.get("service")
        return cls(
            timestamp=datetime_from_iso(data.get("timestamp")) or utc_now(),
            level=str(data.get("level", "INFO")),
            source=str(data.get("source", "manager")),
            message=str(data.get("message", "")),
            service=normalize_service(str(service)) if service else None,
            metadata=dict(data.get("metadata", {})),
        )


# ---------------------------------------------------------------------------
# Security Gate models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SecurityCheckView:
    """Manager view of one Security Gate check."""

    check: SecurityGateCheck
    status: SecurityGateStatus
    message: str | None = None
    blocking: bool = False
    details: dict[str, Any] = field(default_factory=dict)
    checked_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "check", normalize_security_gate_check(self.check))
        object.__setattr__(self, "status", normalize_security_gate_status(self.status))

    @property
    def blocks_startup(self) -> bool:
        return self.blocking and self.status == SecurityGateStatus.FAIL_BLOCKING

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check.value,
            "status": self.status.value,
            "message": self.message,
            "blocking": self.blocking,
            "blocks_startup": self.blocks_startup,
            "details": dict(self.details),
            "checked_at": datetime_to_iso(self.checked_at),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SecurityCheckView":
        return cls(
            check=normalize_security_gate_check(str(data["check"])),
            status=normalize_security_gate_status(str(data["status"])),
            message=data.get("message"),
            blocking=bool(data.get("blocking", False)),
            details=dict(data.get("details", {})),
            checked_at=datetime_from_iso(data.get("checked_at")),
        )


@dataclass(frozen=True)
class SecurityGateView:
    """Manager view of aggregate Security Gate state."""

    status: SecurityGateStatus = SecurityGateStatus.UNKNOWN
    checks: tuple[SecurityCheckView, ...] = field(default_factory=tuple)
    checked_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", normalize_security_gate_status(self.status))

    @property
    def passed(self) -> bool:
        return self.status == SecurityGateStatus.PASS

    @property
    def blocking_failures(self) -> tuple[SecurityCheckView, ...]:
        return tuple(check for check in self.checks if check.blocks_startup)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
            "blocking_failures": [check.check.value for check in self.blocking_failures],
            "checked_at": datetime_to_iso(self.checked_at),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SecurityGateView":
        return cls(
            status=normalize_security_gate_status(str(data.get("status", SecurityGateStatus.UNKNOWN.value))),
            checks=tuple(SecurityCheckView.from_dict(item) for item in data.get("checks", ())),
            checked_at=datetime_from_iso(data.get("checked_at")),
        )


# ---------------------------------------------------------------------------
# Backup, restore, rollback models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BackupSummary:
    """Backup row shown in Manager."""

    backup_id: str
    instance_id: str
    status: BackupStatus
    backup_class: str = "manual"
    root_dir: str | None = None
    size_bytes: int | None = None
    capsule_id: str | None = None
    capsule_version: str | None = None
    created_at: datetime | None = None
    verified_at: datetime | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "backup_id", require_non_empty(self.backup_id, field_name="backup_id"))
        object.__setattr__(self, "instance_id", require_non_empty(self.instance_id, field_name="instance_id"))
        object.__setattr__(self, "status", normalize_backup_status(self.status))

        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes must not be negative.")

    @property
    def usable_for_restore(self) -> bool:
        return self.status == BackupStatus.VERIFIED

    @property
    def display_path(self) -> str:
        return self.root_dir or str(instance_backup_root(self.instance_id))

    def to_dict(self) -> dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "instance_id": self.instance_id,
            "status": self.status.value,
            "backup_class": self.backup_class,
            "root_dir": self.root_dir,
            "display_path": self.display_path,
            "size_bytes": self.size_bytes,
            "capsule_id": self.capsule_id,
            "capsule_version": self.capsule_version,
            "created_at": datetime_to_iso(self.created_at),
            "verified_at": datetime_to_iso(self.verified_at),
            "usable_for_restore": self.usable_for_restore,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BackupSummary":
        return cls(
            backup_id=str(data["backup_id"]),
            instance_id=str(data.get("instance_id", DEFAULT_INSTANCE_ID)),
            status=normalize_backup_status(str(data.get("status", BackupStatus.CREATED.value))),
            backup_class=str(data.get("backup_class", "manual")),
            root_dir=data.get("root_dir"),
            size_bytes=data.get("size_bytes"),
            capsule_id=data.get("capsule_id"),
            capsule_version=data.get("capsule_version"),
            created_at=datetime_from_iso(data.get("created_at")),
            verified_at=datetime_from_iso(data.get("verified_at")),
            error=data.get("error"),
        )


@dataclass(frozen=True)
class RestoreSummary:
    """Restore operation summary shown in Manager."""

    restore_id: str
    instance_id: str
    source_backup_id: str
    status: RestoreStatus = RestoreStatus.PLANNED
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "restore_id", require_non_empty(self.restore_id, field_name="restore_id"))
        object.__setattr__(self, "instance_id", require_non_empty(self.instance_id, field_name="instance_id"))
        object.__setattr__(
            self,
            "source_backup_id",
            require_non_empty(self.source_backup_id, field_name="source_backup_id"),
        )
        object.__setattr__(self, "status", normalize_restore_status(self.status))

    def to_dict(self) -> dict[str, Any]:
        return {
            "restore_id": self.restore_id,
            "instance_id": self.instance_id,
            "source_backup_id": self.source_backup_id,
            "status": self.status.value,
            "created_at": datetime_to_iso(self.created_at),
            "updated_at": datetime_to_iso(self.updated_at),
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RestoreSummary":
        return cls(
            restore_id=str(data["restore_id"]),
            instance_id=str(data.get("instance_id", DEFAULT_INSTANCE_ID)),
            source_backup_id=str(data["source_backup_id"]),
            status=normalize_restore_status(str(data.get("status", RestoreStatus.PLANNED.value))),
            created_at=datetime_from_iso(data.get("created_at")) or utc_now(),
            updated_at=datetime_from_iso(data.get("updated_at")) or utc_now(),
            error=data.get("error"),
        )


@dataclass(frozen=True)
class RollbackSummary:
    """Rollback operation summary shown in Manager."""

    rollback_id: str
    instance_id: str
    status: RollbackStatus = RollbackStatus.PLANNED
    previous_capsule_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "rollback_id", require_non_empty(self.rollback_id, field_name="rollback_id"))
        object.__setattr__(self, "instance_id", require_non_empty(self.instance_id, field_name="instance_id"))
        object.__setattr__(self, "status", normalize_rollback_status(self.status))

    def to_dict(self) -> dict[str, Any]:
        return {
            "rollback_id": self.rollback_id,
            "instance_id": self.instance_id,
            "status": self.status.value,
            "previous_capsule_id": self.previous_capsule_id,
            "created_at": datetime_to_iso(self.created_at),
            "updated_at": datetime_to_iso(self.updated_at),
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RollbackSummary":
        return cls(
            rollback_id=str(data["rollback_id"]),
            instance_id=str(data.get("instance_id", DEFAULT_INSTANCE_ID)),
            status=normalize_rollback_status(str(data.get("status", RollbackStatus.PLANNED.value))),
            previous_capsule_id=data.get("previous_capsule_id"),
            created_at=datetime_from_iso(data.get("created_at")) or utc_now(),
            updated_at=datetime_from_iso(data.get("updated_at")) or utc_now(),
            error=data.get("error"),
        )


# ---------------------------------------------------------------------------
# Instance models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InstanceSummary:
    """Primary Manager view of one Konnaxion Instance."""

    instance_id: str = DEFAULT_INSTANCE_ID
    state: InstanceState = InstanceState.CREATED
    capsule_id: str = DEFAULT_CAPSULE_ID
    capsule_version: str = DEFAULT_CAPSULE_VERSION
    app_version: str = APP_VERSION
    network: NetworkState = field(default_factory=NetworkState)
    health: HealthView = field(default_factory=HealthView)
    security_gate: SecurityGateView = field(default_factory=SecurityGateView)
    last_backup: BackupSummary | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "instance_id", require_non_empty(self.instance_id, field_name="instance_id"))
        object.__setattr__(self, "state", normalize_instance_state(self.state))

    @property
    def root_path(self) -> str:
        return str(instance_root(self.instance_id))

    @property
    def compose_file(self) -> str:
        return str(instance_compose_file(self.instance_id))

    @property
    def backup_root(self) -> str:
        return str(instance_backup_root(self.instance_id))

    @property
    def can_start(self) -> bool:
        return self.state in {
            InstanceState.CREATED,
            InstanceState.READY,
            InstanceState.STOPPED,
            InstanceState.DEGRADED,
        }

    @property
    def can_stop(self) -> bool:
        return self.state in {
            InstanceState.STARTING,
            InstanceState.RUNNING,
            InstanceState.DEGRADED,
        }

    @property
    def can_backup(self) -> bool:
        return self.state in {
            InstanceState.READY,
            InstanceState.RUNNING,
            InstanceState.STOPPED,
            InstanceState.DEGRADED,
        }

    @property
    def blocked_by_security(self) -> bool:
        return self.state == InstanceState.SECURITY_BLOCKED or bool(self.security_gate.blocking_failures)

    def with_state(self, state: InstanceState | str) -> "InstanceSummary":
        return replace(self, state=normalize_instance_state(state), updated_at=utc_now())

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "state": self.state.value,
            "capsule_id": self.capsule_id,
            "capsule_version": self.capsule_version,
            "app_version": self.app_version,
            "network": self.network.to_dict(),
            "health": self.health.to_dict(),
            "security_gate": self.security_gate.to_dict(),
            "last_backup": self.last_backup.to_dict() if self.last_backup else None,
            "paths": {
                "root": self.root_path,
                "compose_file": self.compose_file,
                "backup_root": self.backup_root,
            },
            "can_start": self.can_start,
            "can_stop": self.can_stop,
            "can_backup": self.can_backup,
            "blocked_by_security": self.blocked_by_security,
            "created_at": datetime_to_iso(self.created_at),
            "updated_at": datetime_to_iso(self.updated_at),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "InstanceSummary":
        last_backup = data.get("last_backup")
        return cls(
            instance_id=str(data.get("instance_id", DEFAULT_INSTANCE_ID)),
            state=normalize_instance_state(str(data.get("state", InstanceState.CREATED.value))),
            capsule_id=str(data.get("capsule_id", DEFAULT_CAPSULE_ID)),
            capsule_version=str(data.get("capsule_version", DEFAULT_CAPSULE_VERSION)),
            app_version=str(data.get("app_version", APP_VERSION)),
            network=NetworkState.from_dict(data.get("network", {})),
            health=HealthView.from_dict(data.get("health", {})),
            security_gate=SecurityGateView.from_dict(data.get("security_gate", {})),
            last_backup=BackupSummary.from_dict(last_backup) if isinstance(last_backup, Mapping) else None,
            created_at=datetime_from_iso(data.get("created_at")) or utc_now(),
            updated_at=datetime_from_iso(data.get("updated_at")) or utc_now(),
            metadata=dict(data.get("metadata", {})),
        )


# ---------------------------------------------------------------------------
# Agent and Manager state models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentStatus:
    """Status of the local Konnaxion Agent from the Manager perspective."""

    connection: AgentConnectionStatus = AgentConnectionStatus.UNKNOWN
    version: str | None = None
    local_only: bool = True
    last_seen_at: datetime | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "connection",
            AgentConnectionStatus(str(_enum_value(self.connection))),
        )

    @property
    def connected(self) -> bool:
        return self.connection == AgentConnectionStatus.CONNECTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "connection": self.connection.value,
            "connected": self.connected,
            "version": self.version,
            "local_only": self.local_only,
            "last_seen_at": datetime_to_iso(self.last_seen_at),
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentStatus":
        return cls(
            connection=AgentConnectionStatus(str(data.get("connection", AgentConnectionStatus.UNKNOWN.value))),
            version=data.get("version"),
            local_only=bool(data.get("local_only", True)),
            last_seen_at=datetime_from_iso(data.get("last_seen_at")),
            message=data.get("message"),
        )


@dataclass(frozen=True)
class Notification:
    """Manager UI notification."""

    id: str
    level: NotificationLevel
    message: str
    created_at: datetime = field(default_factory=utc_now)
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_non_empty(self.id, field_name="id"))
        object.__setattr__(self, "level", NotificationLevel(str(_enum_value(self.level))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "level": self.level.value,
            "message": self.message,
            "created_at": datetime_to_iso(self.created_at),
            "details": dict(self.details),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Notification":
        return cls(
            id=str(data["id"]),
            level=NotificationLevel(str(data.get("level", NotificationLevel.INFO.value))),
            message=str(data.get("message", "")),
            created_at=datetime_from_iso(data.get("created_at")) or utc_now(),
            details=dict(data.get("details", {})),
        )


@dataclass(frozen=True)
class ManagerState:
    """Top-level Manager state snapshot."""

    product: ProductInfo = field(default_factory=ProductInfo)
    agent: AgentStatus = field(default_factory=AgentStatus)
    capsules: tuple[CapsuleSummary, ...] = field(default_factory=tuple)
    instances: tuple[InstanceSummary, ...] = field(default_factory=tuple)
    backups: tuple[BackupSummary, ...] = field(default_factory=tuple)
    notifications: tuple[Notification, ...] = field(default_factory=tuple)
    active_view: ManagerView = ManagerView.DASHBOARD
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_view", ManagerView(str(_enum_value(self.active_view))))
        object.__setattr__(self, "capsules", tuple(self.capsules))
        object.__setattr__(self, "instances", tuple(self.instances))
        object.__setattr__(self, "backups", tuple(self.backups))
        object.__setattr__(self, "notifications", tuple(self.notifications))

    @property
    def running_instances(self) -> tuple[InstanceSummary, ...]:
        return tuple(instance for instance in self.instances if instance.state == InstanceState.RUNNING)

    @property
    def security_blocked_instances(self) -> tuple[InstanceSummary, ...]:
        return tuple(instance for instance in self.instances if instance.blocked_by_security)

    def find_instance(self, instance_id: str) -> InstanceSummary | None:
        for instance in self.instances:
            if instance.instance_id == instance_id:
                return instance
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "product": self.product.to_dict(),
            "agent": self.agent.to_dict(),
            "capsules": [capsule.to_dict() for capsule in self.capsules],
            "instances": [instance.to_dict() for instance in self.instances],
            "backups": [backup.to_dict() for backup in self.backups],
            "notifications": [notification.to_dict() for notification in self.notifications],
            "active_view": self.active_view.value,
            "running_instance_count": len(self.running_instances),
            "security_blocked_instance_count": len(self.security_blocked_instances),
            "updated_at": datetime_to_iso(self.updated_at),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ManagerState":
        return cls(
            product=ProductInfo.from_dict(data.get("product", {})),
            agent=AgentStatus.from_dict(data.get("agent", {})),
            capsules=tuple(CapsuleSummary.from_dict(item) for item in data.get("capsules", ())),
            instances=tuple(InstanceSummary.from_dict(item) for item in data.get("instances", ())),
            backups=tuple(BackupSummary.from_dict(item) for item in data.get("backups", ())),
            notifications=tuple(Notification.from_dict(item) for item in data.get("notifications", ())),
            active_view=ManagerView(str(data.get("active_view", ManagerView.DASHBOARD.value))),
            updated_at=datetime_from_iso(data.get("updated_at")) or utc_now(),
        )


# ---------------------------------------------------------------------------
# API request models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InstanceCreateRequest:
    """Manager request to create an instance through the Agent."""

    instance_id: str = DEFAULT_INSTANCE_ID
    capsule_id: str = DEFAULT_CAPSULE_ID
    network_profile: NetworkProfile = DEFAULT_NETWORK_PROFILE

    def __post_init__(self) -> None:
        object.__setattr__(self, "instance_id", require_non_empty(self.instance_id, field_name="instance_id"))
        object.__setattr__(self, "capsule_id", require_non_empty(self.capsule_id, field_name="capsule_id"))
        object.__setattr__(self, "network_profile", normalize_network_profile(self.network_profile))

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "capsule_id": self.capsule_id,
            "network_profile": self.network_profile.value,
        }


@dataclass(frozen=True)
class NetworkProfileChangeRequest:
    """Manager request to change an instance network profile."""

    instance_id: str
    network_profile: NetworkProfile
    exposure_mode: ExposureMode = DEFAULT_EXPOSURE_MODE
    public_mode_expires_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "instance_id", require_non_empty(self.instance_id, field_name="instance_id"))
        object.__setattr__(self, "network_profile", normalize_network_profile(self.network_profile))
        object.__setattr__(self, "exposure_mode", normalize_exposure_mode(self.exposure_mode))

        if self.network_profile == NetworkProfile.PUBLIC_TEMPORARY and self.public_mode_expires_at is None:
            raise ValueError("public_temporary network profile requires public_mode_expires_at.")

        if self.exposure_mode == ExposureMode.PUBLIC and self.network_profile != NetworkProfile.PUBLIC_VPS:
            raise ValueError("public exposure mode requires public_vps network profile.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "network_profile": self.network_profile.value,
            "exposure_mode": self.exposure_mode.value,
            "public_mode_expires_at": datetime_to_iso(self.public_mode_expires_at),
        }


@dataclass(frozen=True)
class AgentActionRequest:
    """Generic Manager-to-Agent action request."""

    operation: str
    instance_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation", require_non_empty(self.operation, field_name="operation"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "instance_id": self.instance_id,
            "payload": dict(self.payload),
        }


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def create_default_manager_state() -> ManagerState:
    """Create an empty default Manager state."""
    return ManagerState()


def create_default_instance_summary(instance_id: str = DEFAULT_INSTANCE_ID) -> InstanceSummary:
    """Create a default Manager instance summary."""
    return InstanceSummary(instance_id=instance_id)


def create_canonical_service_views() -> tuple[ServiceView, ...]:
    """Create default service views for all canonical Docker services."""
    return tuple(
        ServiceView(service=normalize_service(service), desired=True)
        for service in CANONICAL_DOCKER_SERVICES
    )


__all__ = [
    "AgentActionRequest",
    "AgentConnectionStatus",
    "AgentStatus",
    "BackupSummary",
    "CapsuleSummary",
    "HealthView",
    "InstanceCreateRequest",
    "InstanceSummary",
    "LogEntry",
    "ManagerState",
    "ManagerView",
    "NETWORK_PROFILE_OPTIONS",
    "NetworkProfileChangeRequest",
    "NetworkProfileOption",
    "NetworkState",
    "Notification",
    "NotificationLevel",
    "ProductInfo",
    "RestoreSummary",
    "RollbackSummary",
    "SecurityCheckView",
    "SecurityGateView",
    "ServiceView",
    "create_canonical_service_views",
    "create_default_instance_summary",
    "create_default_manager_state",
    "datetime_from_iso",
    "datetime_to_iso",
    "normalize_backup_status",
    "normalize_exposure_mode",
    "normalize_instance_state",
    "normalize_network_profile",
    "normalize_restore_status",
    "normalize_rollback_status",
    "normalize_security_gate_check",
    "normalize_security_gate_status",
    "normalize_service",
    "require_non_empty",
    "utc_now",
]
