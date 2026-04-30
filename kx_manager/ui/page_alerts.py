"""
Alert builders for Konnaxion Capsule Manager UI pages.

This module is framework-neutral. It converts Manager schema objects into
lightweight Alert models used by page render builders.

The UI must not execute privileged operations here. Alerts are display metadata
only.
"""

from __future__ import annotations

from typing import Iterable

from kx_shared.konnaxion_constants import (
    BackupStatus,
    InstanceState,
    SecurityGateStatus,
)

from kx_manager.schemas import (
    BackupSummary,
    CapsuleSummary,
    InstanceSummary,
)

from kx_manager.ui.page_types import Alert


def security_alerts_from_instances(instances: Iterable[InstanceSummary]) -> list[Alert]:
    """Build security-related alerts for one or more instances."""

    alerts: list[Alert] = []

    for instance in instances:
        if instance.state == InstanceState.SECURITY_BLOCKED:
            alerts.append(
                Alert(
                    level="danger",
                    title="Instance security blocked",
                    message=(
                        f"Instance {instance.instance_id} is blocked by the "
                        "Security Gate."
                    ),
                    details={"instance_id": instance.instance_id},
                )
            )
        elif instance.security_status == SecurityGateStatus.FAIL_BLOCKING:
            alerts.append(
                Alert(
                    level="danger",
                    title="Security Gate failure",
                    message=(
                        f"Instance {instance.instance_id} has a blocking "
                        "Security Gate failure."
                    ),
                    details={"instance_id": instance.instance_id},
                )
            )
        elif instance.security_status == SecurityGateStatus.WARN:
            alerts.append(
                Alert(
                    level="warning",
                    title="Security warning",
                    message=(
                        f"Instance {instance.instance_id} has non-blocking "
                        "security warnings."
                    ),
                    details={"instance_id": instance.instance_id},
                )
            )

    return alerts


def unsigned_capsule_alerts(capsules: Iterable[CapsuleSummary]) -> list[Alert]:
    """Build alerts for unsigned capsules."""

    return [
        Alert(
            level="danger",
            title="Unsigned capsule",
            message=f"Capsule {capsule.capsule_id} is not signed.",
            details={"capsule_id": capsule.capsule_id},
        )
        for capsule in capsules
        if not capsule.signed
    ]


def backup_alerts(backups: Iterable[BackupSummary]) -> list[Alert]:
    """Build alerts for failed or quarantined backups."""

    alerts: list[Alert] = []

    for backup in backups:
        if backup.status == BackupStatus.FAILED:
            alerts.append(
                Alert(
                    level="danger",
                    title="Backup failed",
                    message=f"Backup {backup.backup_id} failed.",
                    details={
                        "backup_id": backup.backup_id,
                        "instance_id": backup.instance_id,
                    },
                )
            )
        elif backup.status == BackupStatus.QUARANTINED:
            alerts.append(
                Alert(
                    level="danger",
                    title="Backup quarantined",
                    message=(
                        f"Backup {backup.backup_id} was quarantined by a "
                        "safety check."
                    ),
                    details={
                        "backup_id": backup.backup_id,
                        "instance_id": backup.instance_id,
                    },
                )
            )

    return alerts


__all__ = [
    "backup_alerts",
    "security_alerts_from_instances",
    "unsigned_capsule_alerts",
]