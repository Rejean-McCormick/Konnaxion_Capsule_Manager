"""
Row/table helpers for Konnaxion Capsule Manager UI pages.

This module converts Manager schema objects into framework-neutral dictionaries
consumed by page render models and HTML/UI renderers.
"""

from __future__ import annotations

from typing import Any

from kx_manager.schemas import (
    BackupSummary,
    CapsuleSummary,
    InstanceDetail,
    InstanceSummary,
    KxRuntimeVariables,
    ServiceStatus,
)

from kx_manager.ui.page_status import (
    status_level_for_backup,
    status_level_for_exposure,
    status_level_for_instance,
    status_level_for_security,
    status_level_for_service,
)


def _enum_value(value: Any) -> Any:
    """Return canonical enum value while tolerating plain strings/None."""

    return getattr(value, "value", value)


def _isoformat(value: Any) -> str | None:
    """Return ISO formatted datetime/date values while tolerating None."""

    return value.isoformat() if value else None


def instance_summary_row(instance: InstanceSummary | InstanceDetail) -> dict[str, Any]:
    return {
        "instance_id": instance.instance_id,
        "state": _enum_value(instance.state),
        "state_status": status_level_for_instance(instance.state),
        "capsule_id": instance.capsule_id,
        "capsule_version": instance.capsule_version,
        "network_profile": _enum_value(instance.network_profile),
        "exposure_mode": _enum_value(instance.exposure_mode),
        "public_mode_enabled": instance.public_mode_enabled,
        "public_mode_expires_at": _isoformat(instance.public_mode_expires_at),
        "url": instance.url,
        "security_status": _enum_value(instance.security_status)
        if instance.security_status
        else None,
        "security_status_level": status_level_for_security(instance.security_status),
        "backup_enabled": instance.backup_enabled,
        "last_backup_id": instance.last_backup_id,
    }


def capsule_summary_row(capsule: CapsuleSummary) -> dict[str, Any]:
    return {
        "capsule_id": capsule.capsule_id,
        "capsule_version": capsule.capsule_version,
        "app_version": capsule.app_version,
        "param_version": capsule.param_version,
        "channel": capsule.channel,
        "path": str(capsule.path) if capsule.path else None,
        "imported_at": _isoformat(capsule.imported_at),
        "verified": capsule.verified,
        "signed": capsule.signed,
    }


def backup_summary_row(backup: BackupSummary) -> dict[str, Any]:
    return {
        "backup_id": backup.backup_id,
        "instance_id": backup.instance_id,
        "status": _enum_value(backup.status),
        "status_level": status_level_for_backup(backup.status),
        "backup_class": backup.backup_class,
        "path": str(backup.path) if backup.path else None,
        "size_bytes": backup.size_bytes,
        "created_at": _isoformat(backup.created_at),
        "verified_at": _isoformat(backup.verified_at),
        "capsule_id": backup.capsule_id,
        "capsule_version": backup.capsule_version,
    }


def service_status_row(service: ServiceStatus) -> dict[str, Any]:
    return {
        "service": service.service,
        "running": service.running,
        "healthy": service.healthy,
        "status_level": status_level_for_service(service),
        "image": service.image,
        "ports": service.ports,
        "started_at": _isoformat(service.started_at),
        "message": service.message,
    }


def runtime_variables_table(variables: KxRuntimeVariables) -> dict[str, Any]:
    return {
        "KX_INSTANCE_ID": variables.kx_instance_id,
        "KX_CAPSULE_ID": variables.kx_capsule_id,
        "KX_CAPSULE_VERSION": variables.kx_capsule_version,
        "KX_APP_VERSION": variables.kx_app_version,
        "KX_PARAM_VERSION": variables.kx_param_version,
        "KX_NETWORK_PROFILE": _enum_value(variables.kx_network_profile),
        "KX_EXPOSURE_MODE": _enum_value(variables.kx_exposure_mode),
        "KX_PUBLIC_MODE_ENABLED": variables.kx_public_mode_enabled,
        "KX_PUBLIC_MODE_EXPIRES_AT": _isoformat(
            variables.kx_public_mode_expires_at
        ),
        "KX_BACKUP_ENABLED": variables.kx_backup_enabled,
        "KX_BACKUP_ROOT": str(variables.kx_backup_root),
        "KX_HOST": variables.kx_host,
    }


__all__ = [
    "backup_summary_row",
    "capsule_summary_row",
    "instance_summary_row",
    "runtime_variables_table",
    "service_status_row",
]