"""
Backup retention helpers for Konnaxion Agent.

This module applies canonical Konnaxion backup retention policy without
deleting files directly. Callers receive a retention plan and may execute it
only after audit logging and operator/Agent authorization.

Canonical defaults are imported from ``kx_shared.konnaxion_constants`` through
``KX_ENV_DEFAULTS`` and must remain aligned with the KX_* environment model.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from kx_shared.konnaxion_constants import (
    BackupStatus,
    KX_BACKUPS_ROOT,
    KX_ENV_DEFAULTS,
    instance_backup_root,
)


class BackupClass(StrEnum):
    """Canonical backup classes used by retention planning."""

    MANUAL = "manual"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    PRE_UPDATE = "pre_update"
    PRE_RESTORE = "pre_restore"


@dataclass(frozen=True)
class BackupRecord:
    """Minimal backup metadata needed by retention planning."""

    backup_id: str
    instance_id: str
    backup_class: str
    created_at: datetime
    status: str = BackupStatus.VERIFIED.value
    path: Path | None = None
    size_bytes: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_usable(self) -> bool:
        """Return whether this backup may satisfy retention requirements."""

        return self.status in {
            BackupStatus.CREATED.value,
            BackupStatus.RUNNING.value,
            BackupStatus.VERIFYING.value,
            BackupStatus.VERIFIED.value,
        }

    @property
    def retention_date(self) -> date:
        """Return the date bucket used by retention policy."""

        return self.created_at.astimezone(UTC).date()


@dataclass(frozen=True)
class RetentionPolicy:
    """Canonical backup retention policy.

    Defaults are read from ``KX_ENV_DEFAULTS``:

    - manual backups: ``KX_BACKUP_RETENTION_DAYS``
    - daily backups: ``KX_DAILY_BACKUP_RETENTION_DAYS``
    - weekly backups: ``KX_WEEKLY_BACKUP_RETENTION_WEEKS``
    - monthly backups: ``KX_MONTHLY_BACKUP_RETENTION_MONTHS``
    - pre-update backups: ``KX_PRE_UPDATE_BACKUP_RETENTION_COUNT``
    - pre-restore backups: ``KX_PRE_RESTORE_BACKUP_RETENTION_COUNT``
    """

    manual_retention_days: int = 14
    daily_retention_days: int = 14
    weekly_retention_weeks: int = 8
    monthly_retention_months: int = 12
    pre_update_retention_count: int = 5
    pre_restore_retention_count: int = 5
    keep_failed_days: int = 2
    keep_quarantined: bool = True

    @classmethod
    def from_env(cls, env: Mapping[str, Any] | None = None) -> "RetentionPolicy":
        """Build a policy from KX_* environment values."""

        values = dict(KX_ENV_DEFAULTS)
        if env:
            values.update(env)

        return cls(
            manual_retention_days=_positive_int(
                values.get("KX_BACKUP_RETENTION_DAYS"), default=14
            ),
            daily_retention_days=_positive_int(
                values.get("KX_DAILY_BACKUP_RETENTION_DAYS"), default=14
            ),
            weekly_retention_weeks=_positive_int(
                values.get("KX_WEEKLY_BACKUP_RETENTION_WEEKS"), default=8
            ),
            monthly_retention_months=_positive_int(
                values.get("KX_MONTHLY_BACKUP_RETENTION_MONTHS"), default=12
            ),
            pre_update_retention_count=_positive_int(
                values.get("KX_PRE_UPDATE_BACKUP_RETENTION_COUNT"), default=5
            ),
            pre_restore_retention_count=_positive_int(
                values.get("KX_PRE_RESTORE_BACKUP_RETENTION_COUNT"), default=5
            ),
        )


@dataclass(frozen=True)
class RetentionDecision:
    """Decision for a single backup record."""

    backup: BackupRecord
    keep: bool
    reason: str


@dataclass(frozen=True)
class RetentionPlan:
    """A safe, auditable retention plan.

    The plan does not mutate disk state. Use ``deletable_paths`` or
    ``deletable_backup_ids`` only after Agent authorization.
    """

    generated_at: datetime
    policy: RetentionPolicy
    decisions: tuple[RetentionDecision, ...]

    @property
    def keep(self) -> tuple[BackupRecord, ...]:
        """Backups retained by this plan."""

        return tuple(decision.backup for decision in self.decisions if decision.keep)

    @property
    def delete(self) -> tuple[BackupRecord, ...]:
        """Backups eligible for deletion or expiration."""

        return tuple(decision.backup for decision in self.decisions if not decision.keep)

    @property
    def deletable_backup_ids(self) -> tuple[str, ...]:
        """Backup IDs eligible for deletion or expiration."""

        return tuple(backup.backup_id for backup in self.delete)

    @property
    def deletable_paths(self) -> tuple[Path, ...]:
        """Backup paths eligible for deletion or expiration."""

        return tuple(backup.path for backup in self.delete if backup.path is not None)


class RetentionError(ValueError):
    """Raised when retention policy or metadata is invalid."""


def _positive_int(value: Any, *, default: int) -> int:
    """Parse a non-negative integer with a safe default."""

    if value in {None, ""}:
        return default

    try:
        parsed = int(str(value))
    except ValueError as exc:
        raise RetentionError(f"Invalid retention integer: {value!r}") from exc

    if parsed < 0:
        raise RetentionError(f"Retention value cannot be negative: {parsed}")

    return parsed


def _as_utc(value: datetime) -> datetime:
    """Normalize datetimes to UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _sort_newest(records: Iterable[BackupRecord]) -> list[BackupRecord]:
    """Sort backups newest first, then by backup ID for determinism."""

    return sorted(
        records,
        key=lambda item: (_as_utc(item.created_at), item.backup_id),
        reverse=True,
    )


def _month_index(value: date) -> int:
    """Convert a date to a monotonic month index."""

    return value.year * 12 + value.month


def _is_within_days(created_at: datetime, *, now: datetime, days: int) -> bool:
    """Return whether a backup is within a day-based retention window."""

    return _as_utc(created_at) >= _as_utc(now) - timedelta(days=days)


def _is_within_weeks(created_at: datetime, *, now: datetime, weeks: int) -> bool:
    """Return whether a backup is within a week-based retention window."""

    return _as_utc(created_at) >= _as_utc(now) - timedelta(weeks=weeks)


def _is_within_months(created_at: datetime, *, now: datetime, months: int) -> bool:
    """Return whether a backup is within a calendar-month retention window."""

    created_month = _month_index(_as_utc(created_at).date())
    current_month = _month_index(_as_utc(now).date())
    return created_month >= current_month - max(months - 1, 0)


def _backup_class(value: str) -> str:
    """Normalize a backup class value."""

    return str(value).strip().lower()


def canonical_backup_path(
    *,
    instance_id: str,
    backup_class: str,
    backup_id: str,
    backup_root: str | Path | None = None,
) -> Path:
    """Return the canonical path for a backup directory."""

    root = Path(backup_root) if backup_root else KX_BACKUPS_ROOT
    return root / instance_id / backup_class / backup_id


def infer_backup_class_from_path(path: str | Path) -> str | None:
    """Infer a backup class from a canonical backup path when possible."""

    parts = Path(path).parts
    known = {item.value for item in BackupClass}

    for part in reversed(parts):
        if part in known:
            return part

    return None


def normalize_backup_record(
    raw: Mapping[str, Any],
    *,
    default_instance_id: str | None = None,
) -> BackupRecord:
    """Normalize backup metadata from JSON/YAML/database rows."""

    instance_id = str(raw.get("instance_id") or default_instance_id or "").strip()
    if not instance_id:
        raise RetentionError("Backup record is missing instance_id")

    backup_id = str(raw.get("backup_id") or raw.get("id") or "").strip()
    if not backup_id:
        raise RetentionError("Backup record is missing backup_id")

    path_value = raw.get("path")
    path = Path(path_value) if path_value else None

    backup_class = str(
        raw.get("backup_class")
        or raw.get("class")
        or (infer_backup_class_from_path(path) if path else "")
        or BackupClass.MANUAL.value
    ).strip()

    created_at_value = raw.get("created_at")
    if isinstance(created_at_value, datetime):
        created_at = _as_utc(created_at_value)
    elif isinstance(created_at_value, str):
        created_at = _as_utc(datetime.fromisoformat(created_at_value.replace("Z", "+00:00")))
    else:
        raise RetentionError(f"Invalid created_at for backup {backup_id!r}")

    status = str(raw.get("status") or BackupStatus.VERIFIED.value)

    return BackupRecord(
        backup_id=backup_id,
        instance_id=instance_id,
        backup_class=backup_class,
        created_at=created_at,
        status=status,
        path=path,
        size_bytes=raw.get("size_bytes"),
        metadata=dict(raw),
    )


def normalize_backup_records(
    records: Iterable[BackupRecord | Mapping[str, Any]],
    *,
    default_instance_id: str | None = None,
) -> tuple[BackupRecord, ...]:
    """Normalize a sequence of backup records."""

    normalized: list[BackupRecord] = []

    for record in records:
        if isinstance(record, BackupRecord):
            normalized.append(record)
        else:
            normalized.append(
                normalize_backup_record(
                    record,
                    default_instance_id=default_instance_id,
                )
            )

    return tuple(normalized)


def plan_retention(
    records: Iterable[BackupRecord | Mapping[str, Any]],
    *,
    policy: RetentionPolicy | None = None,
    now: datetime | None = None,
    default_instance_id: str | None = None,
) -> RetentionPlan:
    """Create a retention plan for backup records.

    Strategy:
    - quarantined backups are retained by default
    - failed/deleted/expired backups are retained briefly for audit only
    - manual and daily backups use day windows
    - weekly backups use week windows
    - monthly backups use month windows
    - pre-update and pre-restore backups use count windows
    """

    generated_at = _as_utc(now or datetime.now(UTC))
    active_policy = policy or RetentionPolicy.from_env()
    backups = normalize_backup_records(records, default_instance_id=default_instance_id)

    grouped: dict[str, list[BackupRecord]] = defaultdict(list)
    for backup in backups:
        grouped[_backup_class(backup.backup_class)].append(backup)

    decisions: dict[str, RetentionDecision] = {}

    def decide(backup: BackupRecord, keep: bool, reason: str) -> None:
        decisions[backup.backup_id] = RetentionDecision(
            backup=backup,
            keep=keep,
            reason=reason,
        )

    for backup in backups:
        if backup.status == BackupStatus.QUARANTINED.value and active_policy.keep_quarantined:
            decide(backup, True, "quarantined backups are retained for investigation")
            continue

        if backup.status in {
            BackupStatus.FAILED.value,
            BackupStatus.EXPIRED.value,
            BackupStatus.DELETED.value,
        }:
            keep = _is_within_days(
                backup.created_at,
                now=generated_at,
                days=active_policy.keep_failed_days,
            )
            decide(
                backup,
                keep,
                (
                    f"{backup.status} backup retained for short audit window"
                    if keep
                    else f"{backup.status} backup outside short audit window"
                ),
            )

    for backup in grouped.get(BackupClass.MANUAL.value, []):
        if backup.backup_id in decisions:
            continue

        keep = _is_within_days(
            backup.created_at,
            now=generated_at,
            days=active_policy.manual_retention_days,
        )
        decide(
            backup,
            keep,
            (
                f"manual backup within {active_policy.manual_retention_days}-day window"
                if keep
                else f"manual backup older than {active_policy.manual_retention_days} days"
            ),
        )

    for backup in grouped.get(BackupClass.DAILY.value, []):
        if backup.backup_id in decisions:
            continue

        keep = _is_within_days(
            backup.created_at,
            now=generated_at,
            days=active_policy.daily_retention_days,
        )
        decide(
            backup,
            keep,
            (
                f"daily backup within {active_policy.daily_retention_days}-day window"
                if keep
                else f"daily backup older than {active_policy.daily_retention_days} days"
            ),
        )

    for backup in grouped.get(BackupClass.WEEKLY.value, []):
        if backup.backup_id in decisions:
            continue

        keep = _is_within_weeks(
            backup.created_at,
            now=generated_at,
            weeks=active_policy.weekly_retention_weeks,
        )
        decide(
            backup,
            keep,
            (
                f"weekly backup within {active_policy.weekly_retention_weeks}-week window"
                if keep
                else f"weekly backup older than {active_policy.weekly_retention_weeks} weeks"
            ),
        )

    for backup in grouped.get(BackupClass.MONTHLY.value, []):
        if backup.backup_id in decisions:
            continue

        keep = _is_within_months(
            backup.created_at,
            now=generated_at,
            months=active_policy.monthly_retention_months,
        )
        decide(
            backup,
            keep,
            (
                f"monthly backup within {active_policy.monthly_retention_months}-month window"
                if keep
                else f"monthly backup older than {active_policy.monthly_retention_months} months"
            ),
        )

    _apply_count_policy(
        grouped.get(BackupClass.PRE_UPDATE.value, []),
        decisions=decisions,
        count=active_policy.pre_update_retention_count,
        label="pre-update",
    )

    _apply_count_policy(
        grouped.get(BackupClass.PRE_RESTORE.value, []),
        decisions=decisions,
        count=active_policy.pre_restore_retention_count,
        label="pre-restore",
    )

    # Unknown classes default to manual-like retention to avoid surprise loss.
    known_classes = {item.value for item in BackupClass}
    for backup in backups:
        if backup.backup_id in decisions:
            continue

        if _backup_class(backup.backup_class) not in known_classes:
            keep = _is_within_days(
                backup.created_at,
                now=generated_at,
                days=active_policy.manual_retention_days,
            )
            decide(
                backup,
                keep,
                (
                    "unknown backup class treated as manual within retention window"
                    if keep
                    else "unknown backup class treated as manual outside retention window"
                ),
            )

    ordered_decisions = tuple(
        decisions[backup.backup_id]
        for backup in _sort_newest(backups)
        if backup.backup_id in decisions
    )

    return RetentionPlan(
        generated_at=generated_at,
        policy=active_policy,
        decisions=ordered_decisions,
    )


def _apply_count_policy(
    backups: Iterable[BackupRecord],
    *,
    decisions: dict[str, RetentionDecision],
    count: int,
    label: str,
) -> None:
    """Apply newest-N retention to a backup class."""

    sorted_backups = [
        backup for backup in _sort_newest(backups) if backup.backup_id not in decisions
    ]

    keep_ids = {backup.backup_id for backup in sorted_backups[:count]}

    for backup in sorted_backups:
        keep = backup.backup_id in keep_ids
        decisions[backup.backup_id] = RetentionDecision(
            backup=backup,
            keep=keep,
            reason=(
                f"{label} backup is among newest {count}"
                if keep
                else f"{label} backup exceeds newest {count} retention count"
            ),
        )


def summarize_retention_plan(plan: RetentionPlan) -> dict[str, Any]:
    """Return a JSON-serializable summary of a retention plan."""

    return {
        "generated_at": plan.generated_at.isoformat(),
        "keep_count": len(plan.keep),
        "delete_count": len(plan.delete),
        "keep_backup_ids": [backup.backup_id for backup in plan.keep],
        "delete_backup_ids": [backup.backup_id for backup in plan.delete],
        "delete_paths": [str(path) for path in plan.deletable_paths],
        "decisions": [
            {
                "backup_id": decision.backup.backup_id,
                "instance_id": decision.backup.instance_id,
                "backup_class": decision.backup.backup_class,
                "created_at": decision.backup.created_at.isoformat(),
                "status": decision.backup.status,
                "keep": decision.keep,
                "reason": decision.reason,
                "path": str(decision.backup.path) if decision.backup.path else None,
            }
            for decision in plan.decisions
        ],
    }


__all__ = [
    "BackupClass",
    "BackupRecord",
    "RetentionDecision",
    "RetentionError",
    "RetentionPlan",
    "RetentionPolicy",
    "canonical_backup_path",
    "infer_backup_class_from_path",
    "normalize_backup_record",
    "normalize_backup_records",
    "plan_retention",
    "summarize_retention_plan",
]
