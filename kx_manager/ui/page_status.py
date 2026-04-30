# kx_manager/ui/page_status.py

"""
Status display helpers for Konnaxion Capsule Manager UI pages.

These helpers convert canonical Manager / Agent enum states into framework-neutral
UI status levels consumed by page render models and reusable UI components.
"""

from __future__ import annotations

from kx_shared.konnaxion_constants import (
    BackupStatus,
    ExposureMode,
    InstanceState,
    RestoreStatus,
    SecurityGateStatus,
)

from kx_manager.schemas import ServiceStatus


def status_level_for_instance(state: InstanceState | None) -> str:
    if state is None:
        return "unknown"

    if state == InstanceState.RUNNING:
        return "ok"

    if state in {
        InstanceState.CREATED,
        InstanceState.READY,
        InstanceState.STOPPED,
    }:
        return "neutral"

    if state in {
        InstanceState.IMPORTING,
        InstanceState.VERIFYING,
        InstanceState.STARTING,
        InstanceState.STOPPING,
        InstanceState.UPDATING,
        InstanceState.ROLLING_BACK,
    }:
        return "info"

    if state == InstanceState.DEGRADED:
        return "warning"

    if state in {
        InstanceState.FAILED,
        InstanceState.SECURITY_BLOCKED,
    }:
        return "danger"

    return "unknown"


def status_level_for_security(status: SecurityGateStatus | None) -> str:
    if status is None:
        return "unknown"

    if status == SecurityGateStatus.PASS:
        return "ok"

    if status == SecurityGateStatus.WARN:
        return "warning"

    if status == SecurityGateStatus.FAIL_BLOCKING:
        return "danger"

    if status in {
        SecurityGateStatus.SKIPPED,
        SecurityGateStatus.UNKNOWN,
    }:
        return "neutral"

    return "unknown"


def status_level_for_backup(status: BackupStatus | None) -> str:
    if status is None:
        return "unknown"

    if status == BackupStatus.VERIFIED:
        return "ok"

    if status in {
        BackupStatus.CREATED,
        BackupStatus.RUNNING,
        BackupStatus.VERIFYING,
    }:
        return "info"

    if status in {
        BackupStatus.EXPIRED,
        BackupStatus.DELETED,
    }:
        return "neutral"

    if status in {
        BackupStatus.FAILED,
        BackupStatus.QUARANTINED,
    }:
        return "danger"

    return "unknown"


def status_level_for_restore(status: RestoreStatus | None) -> str:
    if status is None:
        return "neutral"

    if status == RestoreStatus.RESTORED:
        return "ok"

    if status in {
        RestoreStatus.PLANNED,
        RestoreStatus.PREFLIGHT,
        RestoreStatus.CREATING_PRE_RESTORE_BACKUP,
        RestoreStatus.RESTORING_DATABASE,
        RestoreStatus.RESTORING_MEDIA,
        RestoreStatus.RUNNING_MIGRATIONS,
        RestoreStatus.RUNNING_SECURITY_GATE,
        RestoreStatus.RUNNING_HEALTHCHECKS,
    }:
        return "info"

    if status in {
        RestoreStatus.DEGRADED,
        RestoreStatus.ROLLED_BACK,
    }:
        return "warning"

    if status == RestoreStatus.FAILED:
        return "danger"

    return "unknown"


def status_level_for_exposure(exposure: ExposureMode | None) -> str:
    if exposure is None:
        return "unknown"

    if exposure == ExposureMode.PRIVATE:
        return "ok"

    if exposure in {
        ExposureMode.LAN,
        ExposureMode.VPN,
    }:
        return "neutral"

    if exposure == ExposureMode.TEMPORARY_TUNNEL:
        return "warning"

    if exposure == ExposureMode.PUBLIC:
        return "danger"

    return "unknown"


def status_level_for_service(service: ServiceStatus) -> str:
    if not service.running:
        return "neutral"

    if service.healthy is True:
        return "ok"

    if service.healthy is False:
        return "danger"

    return "unknown"


__all__ = [
    "status_level_for_backup",
    "status_level_for_exposure",
    "status_level_for_instance",
    "status_level_for_restore",
    "status_level_for_security",
    "status_level_for_service",
]