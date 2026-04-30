"""
Typed domain contracts for the Konnaxion Capsule Manager system.

This module intentionally does not define canonical names, paths, ports,
profiles, exposure modes, states, or service names. Those values belong in
``kx_shared.konnaxion_constants`` and are imported here when needed.

Use this file for shared typed structures passed between the Builder, Manager,
Agent, CLI, and tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Mapping, NewType, Sequence, TypeAlias, TypedDict

from kx_shared.konnaxion_constants import (
    BackupStatus,
    DockerService,
    ExposureMode,
    InstanceState,
    NetworkProfile,
    RestoreStatus,
    RollbackStatus,
    SecurityGateCheck,
    SecurityGateStatus,
)


# ---------------------------------------------------------------------
# Strong identifier aliases
# ---------------------------------------------------------------------

InstanceID = NewType("InstanceID", str)
ReleaseID = NewType("ReleaseID", str)
CapsuleID = NewType("CapsuleID", str)
CapsuleVersion = NewType("CapsuleVersion", str)
AppVersion = NewType("AppVersion", str)
ParamVersion = NewType("ParamVersion", str)
BackupID = NewType("BackupID", str)
RestoreID = NewType("RestoreID", str)
RollbackID = NewType("RollbackID", str)
ImageDigest = NewType("ImageDigest", str)
Checksum = NewType("Checksum", str)
Hostname = NewType("Hostname", str)
URL = NewType("URL", str)


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
EnvMap: TypeAlias = dict[str, str]
LabelsMap: TypeAlias = dict[str, str]
AnnotationsMap: TypeAlias = dict[str, str]
PathLike: TypeAlias = str | Path


# ---------------------------------------------------------------------
# Capsule manifest types
# ---------------------------------------------------------------------

class CapsuleImageRef(TypedDict):
    service: str
    archive: str
    digest: str


class CapsuleRouteRef(TypedDict):
    path: str
    service: str


class CapsuleCompatibility(TypedDict, total=False):
    min_manager_version: str
    min_agent_version: str
    supported_profiles: list[str]
    supported_architectures: list[str]


class CapsuleManifestDict(TypedDict, total=False):
    schema_version: str
    capsule_id: str
    capsule_version: str
    app_name: str
    app_version: str
    param_version: str
    channel: str
    created_at: str
    builder_version: str
    images: list[CapsuleImageRef]
    services: list[str]
    routes: list[CapsuleRouteRef]
    compatibility: CapsuleCompatibility
    metadata: JsonObject


@dataclass(frozen=True, slots=True)
class CapsuleImage:
    service: DockerService
    archive: Path
    digest: ImageDigest


@dataclass(frozen=True, slots=True)
class CapsuleRoute:
    path: str
    service: DockerService


@dataclass(frozen=True, slots=True)
class CapsuleManifest:
    schema_version: str
    capsule_id: CapsuleID
    capsule_version: CapsuleVersion
    app_name: str
    app_version: AppVersion
    param_version: ParamVersion
    channel: str
    created_at: datetime
    builder_version: str
    images: tuple[CapsuleImage, ...] = ()
    services: tuple[DockerService, ...] = ()
    routes: tuple[CapsuleRoute, ...] = ()
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CapsuleArtifact:
    capsule_id: CapsuleID
    capsule_version: CapsuleVersion
    path: Path
    manifest: CapsuleManifest
    checksum: Checksum | None = None
    signature_path: Path | None = None
    imported_at: datetime | None = None


# ---------------------------------------------------------------------
# Network and exposure types
# ---------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class NetworkProfileConfig:
    profile: NetworkProfile
    exposure_mode: ExposureMode
    public_mode_enabled: bool = False
    public_mode_expires_at: datetime | None = None
    host: Hostname | None = None
    allowed_entry_ports: tuple[int, ...] = ()
    internal_only_ports: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeEndpoint:
    host: Hostname
    url: URL
    profile: NetworkProfile
    exposure_mode: ExposureMode
    is_public: bool = False
    expires_at: datetime | None = None


# ---------------------------------------------------------------------
# Instance types
# ---------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class InstancePaths:
    root: Path
    env_dir: Path
    postgres_dir: Path
    redis_dir: Path
    media_dir: Path
    logs_dir: Path
    backups_dir: Path
    state_dir: Path
    compose_file: Path


@dataclass(frozen=True, slots=True)
class InstanceSpec:
    instance_id: InstanceID
    capsule_id: CapsuleID
    capsule_version: CapsuleVersion
    app_version: AppVersion
    param_version: ParamVersion
    network_profile: NetworkProfile
    exposure_mode: ExposureMode
    host: Hostname | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class InstanceRecord:
    instance_id: InstanceID
    state: InstanceState
    capsule_id: CapsuleID
    capsule_version: CapsuleVersion
    app_version: AppVersion
    param_version: ParamVersion
    network_profile: NetworkProfile
    exposure_mode: ExposureMode
    paths: InstancePaths
    created_at: datetime
    updated_at: datetime
    endpoint: RuntimeEndpoint | None = None
    last_security_gate_id: str | None = None
    last_backup_id: BackupID | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class InstanceTransition:
    instance_id: InstanceID
    from_state: InstanceState
    to_state: InstanceState
    reason: str
    created_at: datetime
    actor: str = "system"


# ---------------------------------------------------------------------
# Compose/runtime types
# ---------------------------------------------------------------------

ServiceHealthStatus = Literal["healthy", "unhealthy", "starting", "unknown", "not_running"]


@dataclass(frozen=True, slots=True)
class ComposeServiceSpec:
    name: DockerService
    image: str
    env_file: tuple[Path, ...] = ()
    volumes: tuple[str, ...] = ()
    depends_on: tuple[DockerService, ...] = ()
    internal_port: int | None = None
    public_ports: tuple[int, ...] = ()
    labels: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ComposeRuntimeSpec:
    instance_id: InstanceID
    compose_file: Path
    services: tuple[ComposeServiceSpec, ...]
    network_profile: NetworkProfile
    exposure_mode: ExposureMode
    env: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ServiceHealth:
    service: DockerService
    status: ServiceHealthStatus
    checked_at: datetime
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeHealth:
    instance_id: InstanceID
    state: InstanceState
    services: tuple[ServiceHealth, ...]
    checked_at: datetime


@dataclass(frozen=True, slots=True)
class RuntimeLogRequest:
    instance_id: InstanceID
    service: DockerService | None = None
    lines: int = 200
    since: datetime | None = None


# ---------------------------------------------------------------------
# Security Gate types
# ---------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SecurityGateFinding:
    check: SecurityGateCheck
    status: SecurityGateStatus
    message: str
    blocking: bool = False
    remediation: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SecurityGateResult:
    instance_id: InstanceID
    status: SecurityGateStatus
    findings: tuple[SecurityGateFinding, ...]
    checked_at: datetime
    capsule_id: CapsuleID | None = None
    network_profile: NetworkProfile | None = None
    exposure_mode: ExposureMode | None = None

    @property
    def passed(self) -> bool:
        return self.status == SecurityGateStatus.PASS

    @property
    def blocking_failures(self) -> tuple[SecurityGateFinding, ...]:
        return tuple(
            finding
            for finding in self.findings
            if finding.status == SecurityGateStatus.FAIL_BLOCKING or finding.blocking
        )


# ---------------------------------------------------------------------
# Backup, restore, and rollback types
# ---------------------------------------------------------------------

BackupClass = Literal["manual", "scheduled", "pre_update", "pre_restore", "test_restore"]


@dataclass(frozen=True, slots=True)
class BackupRecord:
    backup_id: BackupID
    instance_id: InstanceID
    status: BackupStatus
    backup_class: BackupClass
    path: Path
    capsule_id: CapsuleID
    capsule_version: CapsuleVersion
    created_at: datetime
    verified_at: datetime | None = None
    size_bytes: int | None = None
    checksum: Checksum | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RestorePlan:
    restore_id: RestoreID
    source_backup_id: BackupID
    target_instance_id: InstanceID
    status: RestoreStatus
    created_at: datetime
    restore_database: bool = True
    restore_media: bool = True
    run_migrations: bool = True
    run_security_gate: bool = True


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    rollback_id: RollbackID
    instance_id: InstanceID
    status: RollbackStatus
    target_capsule_id: CapsuleID
    target_capsule_version: CapsuleVersion
    created_at: datetime
    restore_data: bool = False
    backup_id: BackupID | None = None


# ---------------------------------------------------------------------
# Agent and Manager API types
# ---------------------------------------------------------------------

AgentActionName = Literal[
    "verify_capsule",
    "import_capsule",
    "create_instance",
    "start_instance",
    "stop_instance",
    "update_instance",
    "rollback_instance",
    "run_security_gate",
    "create_backup",
    "restore_backup",
    "collect_logs",
    "set_network_profile",
]


@dataclass(frozen=True, slots=True)
class AgentActionRequest:
    action: AgentActionName
    instance_id: InstanceID | None = None
    capsule_id: CapsuleID | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    requested_at: datetime | None = None
    requested_by: str | None = None


@dataclass(frozen=True, slots=True)
class AgentActionResult:
    action: AgentActionName
    ok: bool
    message: str
    instance_id: InstanceID | None = None
    capsule_id: CapsuleID | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    completed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ManagerStatus:
    instances: tuple[InstanceRecord, ...]
    capsules: tuple[CapsuleArtifact, ...]
    generated_at: datetime
    active_instance_id: InstanceID | None = None


# ---------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------

def require_non_empty(value: str, field_name: str) -> str:
    """Return a stripped non-empty string or raise ``ValueError``."""

    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def as_instance_id(value: str) -> InstanceID:
    return InstanceID(require_non_empty(value, "instance_id"))


def as_capsule_id(value: str) -> CapsuleID:
    return CapsuleID(require_non_empty(value, "capsule_id"))


def as_capsule_version(value: str) -> CapsuleVersion:
    return CapsuleVersion(require_non_empty(value, "capsule_version"))


def as_backup_id(value: str) -> BackupID:
    return BackupID(require_non_empty(value, "backup_id"))


def env_without_none(values: Mapping[str, str | None]) -> EnvMap:
    """Return env values with ``None`` entries removed."""

    return {key: value for key, value in values.items() if value is not None}


__all__ = [
    "AgentActionName",
    "AgentActionRequest",
    "AgentActionResult",
    "AnnotationsMap",
    "AppVersion",
    "BackupClass",
    "BackupID",
    "BackupRecord",
    "CapsuleArtifact",
    "CapsuleCompatibility",
    "CapsuleID",
    "CapsuleImage",
    "CapsuleImageRef",
    "CapsuleManifest",
    "CapsuleManifestDict",
    "CapsuleRoute",
    "CapsuleRouteRef",
    "CapsuleVersion",
    "Checksum",
    "ComposeRuntimeSpec",
    "ComposeServiceSpec",
    "EnvMap",
    "Hostname",
    "ImageDigest",
    "InstanceID",
    "InstancePaths",
    "InstanceRecord",
    "InstanceSpec",
    "InstanceTransition",
    "JsonObject",
    "JsonScalar",
    "JsonValue",
    "LabelsMap",
    "ManagerStatus",
    "NetworkProfileConfig",
    "PathLike",
    "ReleaseID",
    "RestoreID",
    "RestorePlan",
    "RollbackID",
    "RollbackPlan",
    "RuntimeEndpoint",
    "RuntimeHealth",
    "RuntimeLogRequest",
    "SecurityGateFinding",
    "SecurityGateResult",
    "ServiceHealth",
    "ServiceHealthStatus",
    "URL",
    "as_backup_id",
    "as_capsule_id",
    "as_capsule_version",
    "as_instance_id",
    "env_without_none",
    "require_non_empty",
]
