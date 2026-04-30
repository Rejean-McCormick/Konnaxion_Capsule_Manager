"""
Konnaxion Agent backup models and orchestration helpers.

Backups are application data recovery artifacts, not full host snapshots.
This module keeps backup behavior aligned with the canonical Konnaxion rules:

- backup root: /opt/konnaxion/backups/<INSTANCE_ID>/
- backup status values come from BackupStatus
- backup classes are explicit and instance-scoped
- backups include database, media, env metadata, and manifest metadata
- backups must not preserve host-level state such as Docker daemon state,
  sudoers files, cron state, authorized_keys, /tmp, or unknown host binaries

This module defines safe planning and metadata helpers. The actual archive,
database dump, Docker, and filesystem operations should be implemented by the
Agent runtime layer and called through the action plan returned here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from kx_shared.konnaxion_constants import (
    APP_VERSION,
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_VERSION,
    DEFAULT_INSTANCE_ID,
    KX_BACKUPS_ROOT,
    BackupStatus,
    instance_backup_dir,
    instance_backup_root,
)


# ---------------------------------------------------------------------------
# Backup constants
# ---------------------------------------------------------------------------

BACKUP_ID_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
BACKUP_METADATA_FILENAME = "backup.json"
BACKUP_MANIFEST_FILENAME = "manifest.snapshot.json"
BACKUP_ENV_METADATA_FILENAME = "env.snapshot.json"
BACKUP_DATABASE_FILENAME = "postgres.dump"
BACKUP_MEDIA_ARCHIVE_FILENAME = "media.tar.zst"
BACKUP_LOG_FILENAME = "backup.log"
BACKUP_VERIFY_FILENAME = "verify.json"

BACKUP_ID_PATTERN = re.compile(
    r"^(?P<instance_id>[A-Za-z0-9][A-Za-z0-9_.-]*)_"
    r"(?P<timestamp>\d{8}_\d{6})_"
    r"(?P<class>[a-z][a-z0-9_-]*)$"
)

FORBIDDEN_BACKUP_HOST_PATHS = frozenset(
    {
        "/tmp",
        "/dev/shm",
        "/etc/cron.d",
        "/var/spool/cron",
        "/etc/sudoers",
        "/etc/sudoers.d",
        "/root/.ssh/authorized_keys",
        "/home",
        "/var/lib/docker",
        "/var/run/docker.sock",
        "/run/docker.sock",
    }
)

FORBIDDEN_BACKUP_LABELS = frozenset(
    {
        "full_disk_image",
        "tmp",
        "dev_shm",
        "system_crontabs",
        "user_crontabs",
        "authorized_keys",
        "sudoers",
        "unknown_docker_volumes",
        "docker_daemon_state",
        "docker_socket",
        "unverified_host_binaries",
    }
)

DEFAULT_BACKUP_RETENTION_DAYS = 14
DEFAULT_DAILY_BACKUP_RETENTION_DAYS = 14
DEFAULT_WEEKLY_BACKUP_RETENTION_WEEKS = 8
DEFAULT_MONTHLY_BACKUP_RETENTION_MONTHS = 12
DEFAULT_PRE_UPDATE_BACKUP_RETENTION_COUNT = 5
DEFAULT_PRE_RESTORE_BACKUP_RETENTION_COUNT = 5


# ---------------------------------------------------------------------------
# Backup classes and artifact types
# ---------------------------------------------------------------------------

class BackupClass(StrEnum):
    """Canonical backup classes used by Agent workflows."""

    MANUAL = "manual"
    SCHEDULED_DAILY = "scheduled_daily"
    SCHEDULED_WEEKLY = "scheduled_weekly"
    SCHEDULED_MONTHLY = "scheduled_monthly"
    PRE_UPDATE = "pre_update"
    PRE_RESTORE = "pre_restore"
    PRE_ROLLBACK = "pre_rollback"
    TEST_RESTORE = "test_restore"


class BackupArtifactType(StrEnum):
    """Canonical files produced by a Konnaxion backup."""

    METADATA = "metadata"
    MANIFEST_SNAPSHOT = "manifest_snapshot"
    ENV_METADATA = "env_metadata"
    POSTGRES_DUMP = "postgres_dump"
    MEDIA_ARCHIVE = "media_archive"
    LOG = "log"
    VERIFY_RESULT = "verify_result"


CANONICAL_BACKUP_CLASSES = tuple(backup_class.value for backup_class in BackupClass)
CANONICAL_BACKUP_ARTIFACT_TYPES = tuple(artifact.value for artifact in BackupArtifactType)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class BackupError(Exception):
    """Base class for backup errors."""


class BackupValidationError(BackupError):
    """Raised when backup input is invalid."""


class BackupStatusError(BackupError):
    """Raised when a backup status transition is invalid."""


class UnsafeBackupScopeError(BackupValidationError):
    """Raised when a backup tries to include forbidden host-level scope."""


# ---------------------------------------------------------------------------
# Time and serialization helpers
# ---------------------------------------------------------------------------

def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


def datetime_to_iso(value: datetime | None) -> str | None:
    """Serialize a datetime as UTC ISO-8601."""
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def datetime_from_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime."""
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
        raise BackupValidationError(f"{field_name} is required.")
    return normalized


def normalize_backup_class(value: str | BackupClass) -> BackupClass:
    """Return a canonical BackupClass."""
    raw = getattr(value, "value", value)
    try:
        return BackupClass(str(raw))
    except ValueError as exc:
        raise BackupValidationError(f"Unknown backup class: {raw}") from exc


def normalize_backup_status(value: str | BackupStatus) -> BackupStatus:
    """Return a canonical BackupStatus."""
    raw = getattr(value, "value", value)
    try:
        return BackupStatus(str(raw))
    except ValueError as exc:
        raise BackupValidationError(f"Unknown backup status: {raw}") from exc


def generate_backup_id(
    instance_id: str,
    backup_class: BackupClass | str,
    *,
    created_at: datetime | None = None,
) -> str:
    """Generate a canonical backup ID."""
    normalized_instance_id = require_non_empty(instance_id, field_name="instance_id")
    normalized_class = normalize_backup_class(backup_class)
    timestamp = (created_at or utc_now()).astimezone(UTC).strftime(BACKUP_ID_TIMESTAMP_FORMAT)
    return f"{normalized_instance_id}_{timestamp}_{normalized_class.value}"


def parse_backup_id(backup_id: str) -> dict[str, str]:
    """Parse and validate a canonical backup ID."""
    normalized = require_non_empty(backup_id, field_name="backup_id")
    match = BACKUP_ID_PATTERN.match(normalized)

    if not match:
        raise BackupValidationError(f"Invalid backup ID: {backup_id}")

    parts = match.groupdict()
    normalize_backup_class(parts["class"])
    return parts


def safe_relative_path(path: str | Path) -> str:
    """Validate a relative artifact path."""
    normalized = str(path).strip()

    if not normalized:
        raise BackupValidationError("Artifact path is required.")

    candidate = Path(normalized)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise BackupValidationError(f"Backup artifact path must be relative and safe: {path}")

    return normalized


# ---------------------------------------------------------------------------
# Backup artifact and scope models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BackupArtifact:
    """A file produced by a backup."""

    artifact_type: BackupArtifactType
    relative_path: str
    size_bytes: int | None = None
    sha256: str | None = None
    required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_type",
            BackupArtifactType(getattr(self.artifact_type, "value", self.artifact_type)),
        )
        object.__setattr__(self, "relative_path", safe_relative_path(self.relative_path))

        if self.size_bytes is not None and self.size_bytes < 0:
            raise BackupValidationError("size_bytes must not be negative.")

    @property
    def filename(self) -> str:
        """Return the artifact filename."""
        return Path(self.relative_path).name

    def to_dict(self) -> dict[str, Any]:
        """Serialize to primitive dict."""
        return {
            "artifact_type": self.artifact_type.value,
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "required": self.required,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BackupArtifact":
        """Deserialize from primitive dict."""
        return cls(
            artifact_type=BackupArtifactType(str(data["artifact_type"])),
            relative_path=str(data["relative_path"]),
            size_bytes=data.get("size_bytes"),
            sha256=data.get("sha256"),
            required=bool(data.get("required", True)),
        )


@dataclass(frozen=True)
class BackupScope:
    """Application-level scope included in a backup."""

    include_database: bool = True
    include_media: bool = True
    include_env_metadata: bool = True
    include_manifest_snapshot: bool = True
    include_logs: bool = False
    requested_paths: tuple[str, ...] = field(default_factory=tuple)
    excluded_labels: frozenset[str] = FORBIDDEN_BACKUP_LABELS

    def __post_init__(self) -> None:
        normalized_paths = tuple(str(path).strip() for path in self.requested_paths if str(path).strip())
        object.__setattr__(self, "requested_paths", normalized_paths)
        self.assert_safe()

    def assert_safe(self) -> None:
        """Reject forbidden host-level backup scope."""
        unsafe_paths = sorted(
            path
            for path in self.requested_paths
            if any(path == forbidden or path.startswith(f"{forbidden}/") for forbidden in FORBIDDEN_BACKUP_HOST_PATHS)
        )

        if unsafe_paths:
            raise UnsafeBackupScopeError(
                "Backup scope includes forbidden host-level paths: "
                + ", ".join(unsafe_paths)
            )

    def expected_artifacts(self) -> tuple[BackupArtifact, ...]:
        """Return expected backup artifacts for this scope."""
        artifacts: list[BackupArtifact] = [
            BackupArtifact(BackupArtifactType.METADATA, BACKUP_METADATA_FILENAME),
        ]

        if self.include_manifest_snapshot:
            artifacts.append(
                BackupArtifact(BackupArtifactType.MANIFEST_SNAPSHOT, BACKUP_MANIFEST_FILENAME)
            )

        if self.include_env_metadata:
            artifacts.append(
                BackupArtifact(BackupArtifactType.ENV_METADATA, BACKUP_ENV_METADATA_FILENAME)
            )

        if self.include_database:
            artifacts.append(
                BackupArtifact(BackupArtifactType.POSTGRES_DUMP, BACKUP_DATABASE_FILENAME)
            )

        if self.include_media:
            artifacts.append(
                BackupArtifact(BackupArtifactType.MEDIA_ARCHIVE, BACKUP_MEDIA_ARCHIVE_FILENAME)
            )

        if self.include_logs:
            artifacts.append(
                BackupArtifact(BackupArtifactType.LOG, BACKUP_LOG_FILENAME, required=False)
            )

        return tuple(artifacts)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to primitive dict."""
        return {
            "include_database": self.include_database,
            "include_media": self.include_media,
            "include_env_metadata": self.include_env_metadata,
            "include_manifest_snapshot": self.include_manifest_snapshot,
            "include_logs": self.include_logs,
            "requested_paths": list(self.requested_paths),
            "excluded_labels": sorted(self.excluded_labels),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BackupScope":
        """Deserialize from primitive dict."""
        return cls(
            include_database=bool(data.get("include_database", True)),
            include_media=bool(data.get("include_media", True)),
            include_env_metadata=bool(data.get("include_env_metadata", True)),
            include_manifest_snapshot=bool(data.get("include_manifest_snapshot", True)),
            include_logs=bool(data.get("include_logs", False)),
            requested_paths=tuple(str(path) for path in data.get("requested_paths", ())),
            excluded_labels=frozenset(str(label) for label in data.get("excluded_labels", FORBIDDEN_BACKUP_LABELS)),
        )


# ---------------------------------------------------------------------------
# Backup metadata and status
# ---------------------------------------------------------------------------

VALID_BACKUP_TRANSITIONS: dict[BackupStatus, frozenset[BackupStatus]] = {
    BackupStatus.CREATED: frozenset({BackupStatus.RUNNING, BackupStatus.FAILED, BackupStatus.DELETED}),
    BackupStatus.RUNNING: frozenset({BackupStatus.VERIFYING, BackupStatus.FAILED}),
    BackupStatus.VERIFYING: frozenset({BackupStatus.VERIFIED, BackupStatus.FAILED, BackupStatus.QUARANTINED}),
    BackupStatus.VERIFIED: frozenset({BackupStatus.EXPIRED, BackupStatus.DELETED, BackupStatus.QUARANTINED}),
    BackupStatus.FAILED: frozenset({BackupStatus.DELETED, BackupStatus.QUARANTINED}),
    BackupStatus.EXPIRED: frozenset({BackupStatus.DELETED}),
    BackupStatus.DELETED: frozenset(),
    BackupStatus.QUARANTINED: frozenset({BackupStatus.DELETED}),
}


@dataclass(frozen=True)
class BackupMetadata:
    """Canonical metadata record for one backup."""

    backup_id: str
    instance_id: str
    backup_class: BackupClass
    status: BackupStatus = BackupStatus.CREATED
    root_dir: Path | None = None
    capsule_id: str = DEFAULT_CAPSULE_ID
    capsule_version: str = DEFAULT_CAPSULE_VERSION
    app_version: str = APP_VERSION
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    verified_at: datetime | None = None
    scope: BackupScope = field(default_factory=BackupScope)
    artifacts: tuple[BackupArtifact, ...] = field(default_factory=tuple)
    size_bytes: int | None = None
    sha256: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        parsed = parse_backup_id(self.backup_id)

        object.__setattr__(self, "instance_id", require_non_empty(self.instance_id, field_name="instance_id"))
        object.__setattr__(self, "backup_class", normalize_backup_class(self.backup_class))
        object.__setattr__(self, "status", normalize_backup_status(self.status))
        object.__setattr__(self, "artifacts", tuple(self.artifacts))

        if parsed["instance_id"] != self.instance_id:
            raise BackupValidationError("backup_id instance_id does not match metadata instance_id.")

        if parsed["class"] != self.backup_class.value:
            raise BackupValidationError("backup_id class does not match metadata backup_class.")

        if self.root_dir is None:
            object.__setattr__(
                self,
                "root_dir",
                instance_backup_dir(self.instance_id, self.backup_class.value, self.backup_id),
            )

        if self.size_bytes is not None and self.size_bytes < 0:
            raise BackupValidationError("size_bytes must not be negative.")

    @property
    def metadata_path(self) -> Path:
        """Return path to backup metadata JSON."""
        assert self.root_dir is not None
        return self.root_dir / BACKUP_METADATA_FILENAME

    @property
    def is_terminal(self) -> bool:
        """Return True if backup status no longer transitions to active work."""
        return self.status in {
            BackupStatus.VERIFIED,
            BackupStatus.FAILED,
            BackupStatus.EXPIRED,
            BackupStatus.DELETED,
            BackupStatus.QUARANTINED,
        }

    @property
    def usable_for_restore(self) -> bool:
        """Return True if backup is verified and usable for restore."""
        return self.status == BackupStatus.VERIFIED

    def transition(self, new_status: BackupStatus | str, *, error: str | None = None) -> "BackupMetadata":
        """Return copy transitioned to a new canonical backup status."""
        target = normalize_backup_status(new_status)
        allowed = VALID_BACKUP_TRANSITIONS.get(self.status, frozenset())

        if target != self.status and target not in allowed:
            raise BackupStatusError(f"Invalid backup status transition: {self.status.value} -> {target.value}")

        now = utc_now()
        started_at = self.started_at
        completed_at = self.completed_at
        verified_at = self.verified_at

        if target == BackupStatus.RUNNING and started_at is None:
            started_at = now

        if target in {
            BackupStatus.VERIFIED,
            BackupStatus.FAILED,
            BackupStatus.EXPIRED,
            BackupStatus.DELETED,
            BackupStatus.QUARANTINED,
        }:
            completed_at = completed_at or now

        if target == BackupStatus.VERIFIED:
            verified_at = verified_at or now

        return replace(
            self,
            status=target,
            updated_at=now,
            started_at=started_at,
            completed_at=completed_at,
            verified_at=verified_at,
            error=error,
        )

    def with_artifacts(self, artifacts: Iterable[BackupArtifact]) -> "BackupMetadata":
        """Return copy with artifacts replaced."""
        return replace(
            self,
            artifacts=tuple(artifacts),
            updated_at=utc_now(),
        )

    def with_size_and_hash(self, *, size_bytes: int | None, sha256: str | None) -> "BackupMetadata":
        """Return copy with aggregate size/hash updated."""
        if size_bytes is not None and size_bytes < 0:
            raise BackupValidationError("size_bytes must not be negative.")

        return replace(
            self,
            size_bytes=size_bytes,
            sha256=sha256,
            updated_at=utc_now(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to primitive dict."""
        return {
            "backup_id": self.backup_id,
            "instance_id": self.instance_id,
            "backup_class": self.backup_class.value,
            "status": self.status.value,
            "root_dir": str(self.root_dir),
            "capsule_id": self.capsule_id,
            "capsule_version": self.capsule_version,
            "app_version": self.app_version,
            "created_at": datetime_to_iso(self.created_at),
            "updated_at": datetime_to_iso(self.updated_at),
            "started_at": datetime_to_iso(self.started_at),
            "completed_at": datetime_to_iso(self.completed_at),
            "verified_at": datetime_to_iso(self.verified_at),
            "scope": self.scope.to_dict(),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "error": self.error,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BackupMetadata":
        """Deserialize from primitive dict."""
        return cls(
            backup_id=str(data["backup_id"]),
            instance_id=str(data.get("instance_id", DEFAULT_INSTANCE_ID)),
            backup_class=normalize_backup_class(str(data.get("backup_class", BackupClass.MANUAL.value))),
            status=normalize_backup_status(str(data.get("status", BackupStatus.CREATED.value))),
            root_dir=Path(str(data["root_dir"])) if data.get("root_dir") else None,
            capsule_id=str(data.get("capsule_id", DEFAULT_CAPSULE_ID)),
            capsule_version=str(data.get("capsule_version", DEFAULT_CAPSULE_VERSION)),
            app_version=str(data.get("app_version", APP_VERSION)),
            created_at=datetime_from_iso(data.get("created_at")) or utc_now(),
            updated_at=datetime_from_iso(data.get("updated_at")) or utc_now(),
            started_at=datetime_from_iso(data.get("started_at")),
            completed_at=datetime_from_iso(data.get("completed_at")),
            verified_at=datetime_from_iso(data.get("verified_at")),
            scope=BackupScope.from_dict(data.get("scope", {})),
            artifacts=tuple(
                BackupArtifact.from_dict(artifact)
                for artifact in data.get("artifacts", ())
            ),
            size_bytes=data.get("size_bytes"),
            sha256=data.get("sha256"),
            error=data.get("error"),
            metadata=dict(data.get("metadata", {})),
        )

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_json(cls, value: str) -> "BackupMetadata":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(value))


# ---------------------------------------------------------------------------
# Backup action planning
# ---------------------------------------------------------------------------

class BackupActionType(StrEnum):
    """Safe backup action names for the Agent runtime layer."""

    CREATE_DIRECTORY = "create_directory"
    SNAPSHOT_MANIFEST = "snapshot_manifest"
    SNAPSHOT_ENV_METADATA = "snapshot_env_metadata"
    DUMP_POSTGRES = "dump_postgres"
    ARCHIVE_MEDIA = "archive_media"
    WRITE_METADATA = "write_metadata"
    VERIFY_BACKUP = "verify_backup"


@dataclass(frozen=True)
class BackupAction:
    """One safe backup action to be performed by the Agent runtime layer."""

    action_type: BackupActionType
    target: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "action_type",
            BackupActionType(getattr(self.action_type, "value", self.action_type)),
        )
        object.__setattr__(self, "target", str(self.target))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to primitive dict."""
        return {
            "action_type": self.action_type.value,
            "target": self.target,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class BackupPlan:
    """Safe, declarative backup plan."""

    metadata: BackupMetadata
    actions: tuple[BackupAction, ...]
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to primitive dict."""
        return {
            "metadata": self.metadata.to_dict(),
            "actions": [action.to_dict() for action in self.actions],
            "created_at": datetime_to_iso(self.created_at),
        }


@dataclass(frozen=True)
class BackupRequest:
    """Request to create a backup."""

    instance_id: str = DEFAULT_INSTANCE_ID
    backup_class: BackupClass = BackupClass.MANUAL
    capsule_id: str = DEFAULT_CAPSULE_ID
    capsule_version: str = DEFAULT_CAPSULE_VERSION
    app_version: str = APP_VERSION
    scope: BackupScope = field(default_factory=BackupScope)
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "instance_id", require_non_empty(self.instance_id, field_name="instance_id"))
        object.__setattr__(self, "backup_class", normalize_backup_class(self.backup_class))
        self.scope.assert_safe()


def create_backup_metadata(request: BackupRequest) -> BackupMetadata:
    """Create initial backup metadata from a request."""
    created_at = request.created_at or utc_now()
    backup_id = generate_backup_id(
        request.instance_id,
        request.backup_class,
        created_at=created_at,
    )

    scope = request.scope
    return BackupMetadata(
        backup_id=backup_id,
        instance_id=request.instance_id,
        backup_class=request.backup_class,
        status=BackupStatus.CREATED,
        capsule_id=request.capsule_id,
        capsule_version=request.capsule_version,
        app_version=request.app_version,
        created_at=created_at,
        updated_at=created_at,
        scope=scope,
        artifacts=scope.expected_artifacts(),
        metadata=dict(request.metadata),
    )


def create_backup_plan(request: BackupRequest) -> BackupPlan:
    """Create a safe declarative backup plan for the Agent runtime."""
    metadata = create_backup_metadata(request)
    root = metadata.root_dir
    assert root is not None

    actions: list[BackupAction] = [
        BackupAction(BackupActionType.CREATE_DIRECTORY, str(root)),
    ]

    if metadata.scope.include_manifest_snapshot:
        actions.append(
            BackupAction(
                BackupActionType.SNAPSHOT_MANIFEST,
                str(root / BACKUP_MANIFEST_FILENAME),
            )
        )

    if metadata.scope.include_env_metadata:
        actions.append(
            BackupAction(
                BackupActionType.SNAPSHOT_ENV_METADATA,
                str(root / BACKUP_ENV_METADATA_FILENAME),
                details={"redact_secrets": True},
            )
        )

    if metadata.scope.include_database:
        actions.append(
            BackupAction(
                BackupActionType.DUMP_POSTGRES,
                str(root / BACKUP_DATABASE_FILENAME),
                details={"instance_id": metadata.instance_id},
            )
        )

    if metadata.scope.include_media:
        actions.append(
            BackupAction(
                BackupActionType.ARCHIVE_MEDIA,
                str(root / BACKUP_MEDIA_ARCHIVE_FILENAME),
                details={"compression": "zstd"},
            )
        )

    actions.extend(
        [
            BackupAction(BackupActionType.WRITE_METADATA, str(root / BACKUP_METADATA_FILENAME)),
            BackupAction(BackupActionType.VERIFY_BACKUP, str(root / BACKUP_VERIFY_FILENAME)),
        ]
    )

    return BackupPlan(metadata=metadata, actions=tuple(actions))


def create_manual_backup_request(
    instance_id: str,
    *,
    capsule_id: str = DEFAULT_CAPSULE_ID,
    capsule_version: str = DEFAULT_CAPSULE_VERSION,
    app_version: str = APP_VERSION,
) -> BackupRequest:
    """Create a manual backup request."""
    return BackupRequest(
        instance_id=instance_id,
        backup_class=BackupClass.MANUAL,
        capsule_id=capsule_id,
        capsule_version=capsule_version,
        app_version=app_version,
    )


def create_pre_update_backup_request(
    instance_id: str,
    *,
    capsule_id: str = DEFAULT_CAPSULE_ID,
    capsule_version: str = DEFAULT_CAPSULE_VERSION,
    app_version: str = APP_VERSION,
    target_capsule_id: str | None = None,
    target_capsule_version: str | None = None,
) -> BackupRequest:
    """Create a pre-update backup request."""
    return BackupRequest(
        instance_id=instance_id,
        backup_class=BackupClass.PRE_UPDATE,
        capsule_id=capsule_id,
        capsule_version=capsule_version,
        app_version=app_version,
        metadata={
            "target_capsule_id": target_capsule_id,
            "target_capsule_version": target_capsule_version,
        },
    )


def create_pre_restore_backup_request(
    instance_id: str,
    *,
    capsule_id: str = DEFAULT_CAPSULE_ID,
    capsule_version: str = DEFAULT_CAPSULE_VERSION,
    app_version: str = APP_VERSION,
    source_backup_id: str | None = None,
) -> BackupRequest:
    """Create a pre-restore backup request."""
    return BackupRequest(
        instance_id=instance_id,
        backup_class=BackupClass.PRE_RESTORE,
        capsule_id=capsule_id,
        capsule_version=capsule_version,
        app_version=app_version,
        metadata={"source_backup_id": source_backup_id},
    )


# ---------------------------------------------------------------------------
# Metadata persistence helpers
# ---------------------------------------------------------------------------

def write_backup_metadata(metadata: BackupMetadata, path: Path | None = None) -> Path:
    """Write backup metadata JSON to disk."""
    target = path or metadata.metadata_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(metadata.to_json() + "\n", encoding="utf-8")
    return target


def read_backup_metadata(path: Path) -> BackupMetadata:
    """Read backup metadata JSON from disk."""
    return BackupMetadata.from_json(path.read_text(encoding="utf-8"))


def backup_metadata_path(
    instance_id: str,
    backup_class: BackupClass | str,
    backup_id: str,
) -> Path:
    """Return canonical backup metadata path."""
    normalized_class = normalize_backup_class(backup_class)
    return instance_backup_dir(instance_id, normalized_class.value, backup_id) / BACKUP_METADATA_FILENAME


def list_backup_metadata_files(
    instance_id: str,
    *,
    root: Path = KX_BACKUPS_ROOT,
) -> tuple[Path, ...]:
    """List canonical backup metadata files for an instance."""
    base = root / instance_id
    if not base.exists():
        return tuple()

    return tuple(sorted(base.glob(f"*/*/{BACKUP_METADATA_FILENAME}")))


def load_backup_index(
    instance_id: str,
    *,
    root: Path = KX_BACKUPS_ROOT,
) -> tuple[BackupMetadata, ...]:
    """Load all readable backup metadata records for an instance."""
    records: list[BackupMetadata] = []

    for path in list_backup_metadata_files(instance_id, root=root):
        try:
            records.append(read_backup_metadata(path))
        except (OSError, json.JSONDecodeError, BackupError, KeyError, ValueError):
            continue

    return tuple(sorted(records, key=lambda item: item.created_at, reverse=True))


# ---------------------------------------------------------------------------
# Retention helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BackupRetentionPolicy:
    """Canonical backup retention settings."""

    backup_retention_days: int = DEFAULT_BACKUP_RETENTION_DAYS
    daily_backup_retention_days: int = DEFAULT_DAILY_BACKUP_RETENTION_DAYS
    weekly_backup_retention_weeks: int = DEFAULT_WEEKLY_BACKUP_RETENTION_WEEKS
    monthly_backup_retention_months: int = DEFAULT_MONTHLY_BACKUP_RETENTION_MONTHS
    pre_update_backup_retention_count: int = DEFAULT_PRE_UPDATE_BACKUP_RETENTION_COUNT
    pre_restore_backup_retention_count: int = DEFAULT_PRE_RESTORE_BACKUP_RETENTION_COUNT

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "BackupRetentionPolicy":
        """Build retention policy from KX_* environment values."""
        return cls(
            backup_retention_days=_env_int(env, "KX_BACKUP_RETENTION_DAYS", DEFAULT_BACKUP_RETENTION_DAYS),
            daily_backup_retention_days=_env_int(
                env,
                "KX_DAILY_BACKUP_RETENTION_DAYS",
                DEFAULT_DAILY_BACKUP_RETENTION_DAYS,
            ),
            weekly_backup_retention_weeks=_env_int(
                env,
                "KX_WEEKLY_BACKUP_RETENTION_WEEKS",
                DEFAULT_WEEKLY_BACKUP_RETENTION_WEEKS,
            ),
            monthly_backup_retention_months=_env_int(
                env,
                "KX_MONTHLY_BACKUP_RETENTION_MONTHS",
                DEFAULT_MONTHLY_BACKUP_RETENTION_MONTHS,
            ),
            pre_update_backup_retention_count=_env_int(
                env,
                "KX_PRE_UPDATE_BACKUP_RETENTION_COUNT",
                DEFAULT_PRE_UPDATE_BACKUP_RETENTION_COUNT,
            ),
            pre_restore_backup_retention_count=_env_int(
                env,
                "KX_PRE_RESTORE_BACKUP_RETENTION_COUNT",
                DEFAULT_PRE_RESTORE_BACKUP_RETENTION_COUNT,
            ),
        )


def _env_int(env: Mapping[str, str], key: str, default: int) -> int:
    try:
        return int(str(env.get(key, default)).strip())
    except ValueError:
        return default


def backups_to_prune_by_count(
    backups: Sequence[BackupMetadata],
    *,
    backup_class: BackupClass | str,
    keep: int,
) -> tuple[BackupMetadata, ...]:
    """Return old backups of a class exceeding count retention."""
    normalized_class = normalize_backup_class(backup_class)
    matching = sorted(
        (backup for backup in backups if backup.backup_class == normalized_class),
        key=lambda backup: backup.created_at,
        reverse=True,
    )

    if keep < 0:
        keep = 0

    return tuple(matching[keep:])


# ---------------------------------------------------------------------------
# Public facade
# ---------------------------------------------------------------------------

class BackupPlanner:
    """Creates canonical Konnaxion backup plans."""

    def create_plan(self, request: BackupRequest) -> BackupPlan:
        """Create a backup plan."""
        return create_backup_plan(request)

    def manual(self, instance_id: str, **kwargs: Any) -> BackupPlan:
        """Create a manual backup plan."""
        return self.create_plan(create_manual_backup_request(instance_id, **kwargs))

    def pre_update(self, instance_id: str, **kwargs: Any) -> BackupPlan:
        """Create a pre-update backup plan."""
        return self.create_plan(create_pre_update_backup_request(instance_id, **kwargs))

    def pre_restore(self, instance_id: str, **kwargs: Any) -> BackupPlan:
        """Create a pre-restore backup plan."""
        return self.create_plan(create_pre_restore_backup_request(instance_id, **kwargs))


__all__ = [
    "BACKUP_DATABASE_FILENAME",
    "BACKUP_ENV_METADATA_FILENAME",
    "BACKUP_ID_PATTERN",
    "BACKUP_ID_TIMESTAMP_FORMAT",
    "BACKUP_LOG_FILENAME",
    "BACKUP_MANIFEST_FILENAME",
    "BACKUP_MEDIA_ARCHIVE_FILENAME",
    "BACKUP_METADATA_FILENAME",
    "BACKUP_VERIFY_FILENAME",
    "CANONICAL_BACKUP_ARTIFACT_TYPES",
    "CANONICAL_BACKUP_CLASSES",
    "DEFAULT_BACKUP_RETENTION_DAYS",
    "DEFAULT_DAILY_BACKUP_RETENTION_DAYS",
    "DEFAULT_MONTHLY_BACKUP_RETENTION_MONTHS",
    "DEFAULT_PRE_RESTORE_BACKUP_RETENTION_COUNT",
    "DEFAULT_PRE_UPDATE_BACKUP_RETENTION_COUNT",
    "DEFAULT_WEEKLY_BACKUP_RETENTION_WEEKS",
    "FORBIDDEN_BACKUP_HOST_PATHS",
    "FORBIDDEN_BACKUP_LABELS",
    "BackupAction",
    "BackupActionType",
    "BackupArtifact",
    "BackupArtifactType",
    "BackupClass",
    "BackupError",
    "BackupMetadata",
    "BackupPlan",
    "BackupPlanner",
    "BackupRequest",
    "BackupRetentionPolicy",
    "BackupScope",
    "BackupStatusError",
    "BackupValidationError",
    "UnsafeBackupScopeError",
    "backup_metadata_path",
    "backups_to_prune_by_count",
    "create_backup_metadata",
    "create_backup_plan",
    "create_manual_backup_request",
    "create_pre_restore_backup_request",
    "create_pre_update_backup_request",
    "datetime_from_iso",
    "datetime_to_iso",
    "generate_backup_id",
    "list_backup_metadata_files",
    "load_backup_index",
    "normalize_backup_class",
    "normalize_backup_status",
    "parse_backup_id",
    "read_backup_metadata",
    "require_non_empty",
    "safe_relative_path",
    "utc_now",
    "write_backup_metadata",
]
