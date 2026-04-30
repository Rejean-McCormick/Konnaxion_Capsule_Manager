"""
Framework-neutral page render-model builders for the Konnaxion Capsule Manager UI.
"""

from __future__ import annotations

from typing import Sequence

from kx_shared.konnaxion_constants import (
    BackupStatus,
    InstanceState,
    RestoreStatus,
    SecurityGateStatus,
)

from kx_manager.schemas import (
    BackupSummary,
    CapsuleSummary,
    DashboardSummary,
    HealthSummary,
    InstanceDetail,
    InstanceSummary,
    KxRuntimeVariables,
    NetworkProfileSummary,
    ProductInfo,
    RestoreReportSchema,
    SecurityGateReport,
    ServiceStatus,
)

from kx_manager.ui.page_alerts import (
    backup_alerts,
    security_alerts_from_instances,
    unsigned_capsule_alerts,
)
from kx_manager.ui.page_navigation import build_breadcrumbs, get_page
from kx_manager.ui.page_rows import (
    backup_summary_row,
    capsule_summary_row,
    instance_summary_row,
    runtime_variables_table,
    service_status_row,
)
from kx_manager.ui.page_status import (
    status_level_for_exposure,
    status_level_for_instance,
    status_level_for_restore,
    status_level_for_security,
)
from kx_manager.ui.page_types import (
    ActionIntent,
    Alert,
    MetricCard,
    PageAction,
    PageContext,
    PageId,
    PageRenderModel,
    UiAction,
)


def dashboard_page_model(
    summary: DashboardSummary,
    *,
    context: PageContext | None = None,
) -> PageRenderModel:
    page = get_page(PageId.DASHBOARD)
    instances = summary.instances

    running = [item for item in instances if item.state == InstanceState.RUNNING]
    blocked = [
        item
        for item in instances
        if item.state == InstanceState.SECURITY_BLOCKED
        or item.security_status == SecurityGateStatus.FAIL_BLOCKING
    ]

    metrics = (
        MetricCard(
            "Instances",
            str(len(instances)),
            "Total local Konnaxion Instances.",
        ),
        MetricCard(
            "Running",
            str(len(running)),
            "Instances currently running.",
            status="ok" if running else None,
        ),
        MetricCard(
            "Security blocked",
            str(len(blocked)),
            "Instances blocked by Security Gate.",
            status="danger" if blocked else "ok",
        ),
        MetricCard(
            "Capsules",
            str(len(summary.capsules)),
            "Imported or known Konnaxion Capsules.",
        ),
    )

    actions = (
        PageAction(UiAction.IMPORT_CAPSULE, "Import Capsule", ActionIntent.PRIMARY),
        PageAction(UiAction.CREATE_INSTANCE, "Create Instance", ActionIntent.SECONDARY),
    )

    return PageRenderModel(
        page=page,
        title="Konnaxion Capsule Manager",
        subtitle="Private-by-default capsule and instance control.",
        metrics=metrics,
        alerts=tuple(security_alerts_from_instances(instances)),
        actions=actions,
        sections={
            "instances": [instance_summary_row(item) for item in instances],
            "capsules": [capsule_summary_row(item) for item in summary.capsules],
            "recent_backups": [
                backup_summary_row(item) for item in summary.recent_backups
            ],
            "security_alerts": [
                item.to_dict() for item in summary.security_alerts
            ],
        },
        breadcrumbs=build_breadcrumbs(page, context),
    )


def capsules_page_model(
    capsules: Sequence[CapsuleSummary],
    *,
    context: PageContext | None = None,
) -> PageRenderModel:
    page = get_page(PageId.CAPSULES)

    actions = (
        PageAction(UiAction.IMPORT_CAPSULE, "Import Capsule", ActionIntent.PRIMARY),
        PageAction(UiAction.VERIFY_CAPSULE, "Verify Capsule", ActionIntent.SECONDARY),
    )

    return PageRenderModel(
        page=page,
        title="Capsules",
        subtitle="Verify and import signed .kxcap files.",
        metrics=(
            MetricCard("Capsules", str(len(capsules))),
            MetricCard(
                "Verified",
                str(sum(1 for item in capsules if item.verified)),
                status="ok",
            ),
            MetricCard(
                "Unsigned",
                str(sum(1 for item in capsules if not item.signed)),
                status="danger",
            ),
        ),
        alerts=tuple(unsigned_capsule_alerts(capsules)),
        actions=actions,
        sections={
            "capsules": [capsule_summary_row(item) for item in capsules],
        },
        breadcrumbs=build_breadcrumbs(page, context),
    )


def instances_page_model(
    instances: Sequence[InstanceSummary],
    *,
    context: PageContext | None = None,
) -> PageRenderModel:
    page = get_page(PageId.INSTANCES)

    return PageRenderModel(
        page=page,
        title="Instances",
        subtitle="Create, start, stop, update, and inspect Konnaxion Instances.",
        metrics=(
            MetricCard("Total", str(len(instances))),
            MetricCard(
                "Running",
                str(sum(1 for item in instances if item.state == InstanceState.RUNNING)),
            ),
            MetricCard(
                "Stopped",
                str(sum(1 for item in instances if item.state == InstanceState.STOPPED)),
            ),
            MetricCard(
                "Blocked",
                str(
                    sum(
                        1
                        for item in instances
                        if item.state == InstanceState.SECURITY_BLOCKED
                    )
                ),
                status="danger",
            ),
        ),
        alerts=tuple(security_alerts_from_instances(instances)),
        actions=(
            PageAction(UiAction.CREATE_INSTANCE, "Create Instance", ActionIntent.PRIMARY),
        ),
        sections={
            "instances": [instance_summary_row(item) for item in instances],
        },
        breadcrumbs=build_breadcrumbs(page, context),
    )


def instance_detail_page_model(
    instance: InstanceDetail,
    *,
    context: PageContext | None = None,
) -> PageRenderModel:
    page = get_page(PageId.INSTANCE_DETAIL)
    ctx = context or PageContext(selected_instance_id=instance.instance_id)

    alerts: list[Alert] = []
    alerts.extend(security_alerts_from_instances([instance]))

    if instance.public_mode_enabled:
        alerts.append(
            Alert(
                level="warning",
                title="Public mode enabled",
                message="This instance has public exposure enabled.",
                details={
                    "expires_at": instance.public_mode_expires_at.isoformat()
                    if instance.public_mode_expires_at
                    else None
                },
            )
        )

    return PageRenderModel(
        page=page,
        title=f"Instance {instance.instance_id}",
        subtitle=(
            f"{instance.state.value} · "
            f"{instance.network_profile.value} · "
            f"{instance.exposure_mode.value}"
        ),
        metrics=(
            MetricCard(
                "State",
                instance.state.value,
                status=status_level_for_instance(instance.state),
            ),
            MetricCard(
                "Security",
                instance.security_status.value if instance.security_status else "unknown",
                status=status_level_for_security(instance.security_status),
            ),
            MetricCard("Network", instance.network_profile.value),
            MetricCard(
                "Capsule",
                instance.capsule_version or instance.capsule_id or "unknown",
            ),
        ),
        alerts=tuple(alerts),
        actions=instance_actions(instance),
        sections={
            "summary": instance_summary_row(instance),
            "services": [service_status_row(service) for service in instance.services],
            "variables": (
                runtime_variables_table(instance.variables)
                if instance.variables
                else {}
            ),
            "health": (
                instance.health.model_dump(mode="json")
                if instance.health
                else None
            ),
            "security_gate": (
                instance.security_gate.model_dump(mode="json")
                if instance.security_gate
                else None
            ),
        },
        breadcrumbs=build_breadcrumbs(page, ctx),
    )


def security_page_model(
    report: SecurityGateReport,
    *,
    context: PageContext | None = None,
) -> PageRenderModel:
    page = get_page(PageId.SECURITY)
    ctx = context or PageContext(selected_instance_id=report.instance_id)

    failures = [
        result
        for result in report.results
        if result.status == SecurityGateStatus.FAIL_BLOCKING
    ]

    alerts = [
        Alert(
            level="danger",
            title="Security Gate blocking failure",
            message=result.message,
            details={"check": result.check.value, **result.details},
        )
        for result in failures
    ]

    return PageRenderModel(
        page=page,
        title="Security Gate",
        subtitle=f"Instance {report.instance_id}",
        metrics=(
            MetricCard(
                "Status",
                report.status.value,
                status=status_level_for_security(report.status),
            ),
            MetricCard("Checks", str(len(report.results))),
            MetricCard(
                "Blocking failures",
                str(len(failures)),
                status="danger" if failures else "ok",
            ),
        ),
        alerts=tuple(alerts),
        actions=(
            PageAction(
                UiAction.RUN_SECURITY_CHECK,
                "Run Security Check",
                ActionIntent.PRIMARY,
                payload={"instance_id": report.instance_id},
            ),
        ),
        sections={
            "results": [result.model_dump(mode="json") for result in report.results],
            "blocking_failures": [
                result.model_dump(mode="json") for result in failures
            ],
        },
        breadcrumbs=build_breadcrumbs(page, ctx),
    )


def network_page_model(
    instance: InstanceSummary,
    profiles: Sequence[NetworkProfileSummary],
    *,
    context: PageContext | None = None,
) -> PageRenderModel:
    page = get_page(PageId.NETWORK)
    ctx = context or PageContext(selected_instance_id=instance.instance_id)

    alerts: list[Alert] = []

    if instance.public_mode_enabled:
        alerts.append(
            Alert(
                level="warning",
                title="Public mode enabled",
                message="Public exposure is active and must have an expiration.",
                details={
                    "expires_at": instance.public_mode_expires_at.isoformat()
                    if instance.public_mode_expires_at
                    else None
                },
            )
        )

    return PageRenderModel(
        page=page,
        title="Network",
        subtitle=f"{instance.network_profile.value} · {instance.exposure_mode.value}",
        metrics=(
            MetricCard("Profile", instance.network_profile.value),
            MetricCard(
                "Exposure",
                instance.exposure_mode.value,
                status=status_level_for_exposure(instance.exposure_mode),
            ),
            MetricCard(
                "Public mode",
                "enabled" if instance.public_mode_enabled else "disabled",
                status="warning" if instance.public_mode_enabled else "ok",
            ),
        ),
        alerts=tuple(alerts),
        actions=(
            PageAction(
                UiAction.SET_NETWORK_PROFILE,
                "Set Network Profile",
                ActionIntent.PRIMARY,
                payload={"instance_id": instance.instance_id},
            ),
            PageAction(
                UiAction.DISABLE_PUBLIC_MODE,
                "Disable Public Mode",
                ActionIntent.WARNING,
                disabled=not instance.public_mode_enabled,
                reason_disabled="Public mode is not enabled.",
                payload={"instance_id": instance.instance_id},
            ),
        ),
        sections={
            "current_instance": instance_summary_row(instance),
            "profiles": [profile.model_dump(mode="json") for profile in profiles],
        },
        breadcrumbs=build_breadcrumbs(page, ctx),
    )


def backups_page_model(
    instance: InstanceSummary,
    backups: Sequence[BackupSummary],
    *,
    context: PageContext | None = None,
) -> PageRenderModel:
    page = get_page(PageId.BACKUPS)
    ctx = context or PageContext(selected_instance_id=instance.instance_id)

    verified = [backup for backup in backups if backup.status == BackupStatus.VERIFIED]
    failed = [backup for backup in backups if backup.status == BackupStatus.FAILED]

    return PageRenderModel(
        page=page,
        title="Backups",
        subtitle=f"Instance {instance.instance_id}",
        metrics=(
            MetricCard("Backups", str(len(backups))),
            MetricCard("Verified", str(len(verified)), status="ok"),
            MetricCard(
                "Failed",
                str(len(failed)),
                status="danger" if failed else "ok",
            ),
        ),
        alerts=tuple(backup_alerts(backups)),
        actions=(
            PageAction(
                UiAction.CREATE_BACKUP,
                "Create Backup",
                ActionIntent.PRIMARY,
                payload={"instance_id": instance.instance_id},
            ),
            PageAction(
                UiAction.VERIFY_BACKUP,
                "Verify Backup",
                ActionIntent.SECONDARY,
            ),
        ),
        sections={
            "backups": [backup_summary_row(backup) for backup in backups],
        },
        breadcrumbs=build_breadcrumbs(page, ctx),
    )


def restore_page_model(
    instance: InstanceSummary,
    backups: Sequence[BackupSummary],
    latest_report: RestoreReportSchema | None = None,
    *,
    context: PageContext | None = None,
) -> PageRenderModel:
    page = get_page(PageId.RESTORE)
    ctx = context or PageContext(selected_instance_id=instance.instance_id)

    verified_backups = [
        backup for backup in backups if backup.status == BackupStatus.VERIFIED
    ]

    alerts: list[Alert] = []

    if not verified_backups:
        alerts.append(
            Alert(
                level="warning",
                title="No verified backups",
                message="Restore should use a verified backup.",
            )
        )

    if latest_report and latest_report.status == RestoreStatus.FAILED:
        alerts.append(
            Alert(
                level="danger",
                title="Last restore failed",
                message="Review the restore report before retrying.",
                details={"restore_id": latest_report.restore_id},
            )
        )

    return PageRenderModel(
        page=page,
        title="Restore",
        subtitle="Prefer restore-new when validating disaster recovery.",
        metrics=(
            MetricCard(
                "Verified backups",
                str(len(verified_backups)),
                status="ok" if verified_backups else "warning",
            ),
            MetricCard(
                "Latest restore",
                latest_report.status.value if latest_report else "none",
                status=status_level_for_restore(
                    latest_report.status if latest_report else None
                ),
            ),
        ),
        alerts=tuple(alerts),
        actions=(
            PageAction(
                UiAction.RESTORE_BACKUP_NEW,
                "Restore to New Instance",
                ActionIntent.PRIMARY,
                requires_confirmation=True,
            ),
            PageAction(
                UiAction.RESTORE_BACKUP,
                "Restore Same Instance",
                ActionIntent.DANGER,
                requires_confirmation=True,
            ),
        ),
        sections={
            "instance": instance_summary_row(instance),
            "verified_backups": [
                backup_summary_row(backup) for backup in verified_backups
            ],
            "latest_report": (
                latest_report.model_dump(mode="json") if latest_report else None
            ),
        },
        breadcrumbs=build_breadcrumbs(page, ctx),
    )


def logs_page_model(
    instance: InstanceSummary,
    services: Sequence[ServiceStatus],
    *,
    context: PageContext | None = None,
) -> PageRenderModel:
    page = get_page(PageId.LOGS)
    ctx = context or PageContext(selected_instance_id=instance.instance_id)

    return PageRenderModel(
        page=page,
        title="Logs",
        subtitle=f"Instance {instance.instance_id}",
        actions=(
            PageAction(UiAction.VIEW_LOGS, "Refresh Logs", ActionIntent.PRIMARY),
        ),
        sections={
            "instance": instance_summary_row(instance),
            "services": [service_status_row(service) for service in services],
            "filters": {
                "default_lines": 200,
                "max_lines": 5000,
            },
        },
        breadcrumbs=build_breadcrumbs(page, ctx),
    )


def health_page_model(
    health: HealthSummary,
    *,
    context: PageContext | None = None,
) -> PageRenderModel:
    page = get_page(PageId.HEALTH)
    ctx = context or PageContext(selected_instance_id=health.instance_id)

    unhealthy = [
        check
        for check in health.checks
        if check.status in {"unhealthy", "unknown"}
    ]

    return PageRenderModel(
        page=page,
        title="Health",
        subtitle=f"Instance {health.instance_id}",
        metrics=(
            MetricCard(
                "Status",
                health.status,
                status="ok" if health.healthy else "danger",
            ),
            MetricCard("Checks", str(len(health.checks))),
            MetricCard(
                "Unhealthy/unknown",
                str(len(unhealthy)),
                status="danger" if unhealthy else "ok",
            ),
        ),
        alerts=tuple(
            Alert(
                level="danger",
                title=f"Healthcheck: {check.name}",
                message=check.message or check.status,
                details=check.details,
            )
            for check in unhealthy
        ),
        actions=(
            PageAction(UiAction.VIEW_HEALTH, "Refresh Health", ActionIntent.PRIMARY),
        ),
        sections={
            "checks": [check.model_dump(mode="json") for check in health.checks],
        },
        breadcrumbs=build_breadcrumbs(page, ctx),
    )


def settings_page_model(
    variables: KxRuntimeVariables,
    *,
    context: PageContext | None = None,
) -> PageRenderModel:
    page = get_page(PageId.SETTINGS)

    return PageRenderModel(
        page=page,
        title="Settings",
        subtitle="Canonical runtime variables.",
        metrics=(
            MetricCard("Instance", variables.kx_instance_id),
            MetricCard("Network", variables.kx_network_profile.value),
            MetricCard(
                "Exposure",
                variables.kx_exposure_mode.value,
                status=status_level_for_exposure(variables.kx_exposure_mode),
            ),
            MetricCard(
                "Backups",
                "enabled" if variables.kx_backup_enabled else "disabled",
                status="ok" if variables.kx_backup_enabled else "warning",
            ),
        ),
        sections={
            "variables": runtime_variables_table(variables),
        },
        breadcrumbs=build_breadcrumbs(page, context),
    )


def about_page_model(
    product: ProductInfo | None = None,
    *,
    context: PageContext | None = None,
) -> PageRenderModel:
    page = get_page(PageId.ABOUT)
    product = product or ProductInfo()

    return PageRenderModel(
        page=page,
        title="About Konnaxion",
        subtitle="Portable, signed, private-by-default Konnaxion Capsule runtime.",
        sections={
            "product": product.model_dump(mode="json"),
        },
        breadcrumbs=build_breadcrumbs(page, context),
    )


def instance_actions(instance: InstanceSummary) -> tuple[PageAction, ...]:
    can_start = instance.state in {
        InstanceState.CREATED,
        InstanceState.READY,
        InstanceState.STOPPED,
        InstanceState.DEGRADED,
    }
    can_stop = instance.state == InstanceState.RUNNING
    blocked = instance.state == InstanceState.SECURITY_BLOCKED

    return (
        PageAction(
            UiAction.OPEN_INSTANCE,
            "Open Konnaxion",
            ActionIntent.PRIMARY,
            disabled=not bool(instance.url) or instance.state != InstanceState.RUNNING,
            reason_disabled="Instance must be running with a URL.",
            payload={"instance_id": instance.instance_id, "url": instance.url},
        ),
        PageAction(
            UiAction.START_INSTANCE,
            "Start",
            ActionIntent.PRIMARY,
            disabled=not can_start or blocked,
            reason_disabled=(
                "Instance is not in a startable state."
                if not can_start
                else "Security Gate is blocking startup."
            ),
            payload={"instance_id": instance.instance_id},
        ),
        PageAction(
            UiAction.STOP_INSTANCE,
            "Stop",
            ActionIntent.WARNING,
            disabled=not can_stop,
            reason_disabled="Instance is not running.",
            payload={"instance_id": instance.instance_id},
        ),
        PageAction(
            UiAction.CREATE_BACKUP,
            "Create Backup",
            ActionIntent.SECONDARY,
            disabled=not instance.backup_enabled,
            reason_disabled="Backups are disabled.",
            payload={"instance_id": instance.instance_id},
        ),
        PageAction(
            UiAction.RUN_SECURITY_CHECK,
            "Security Check",
            ActionIntent.SECONDARY,
            payload={"instance_id": instance.instance_id},
        ),
        PageAction(
            UiAction.ROLLBACK_INSTANCE,
            "Rollback",
            ActionIntent.DANGER,
            requires_confirmation=True,
            payload={"instance_id": instance.instance_id},
        ),
    )


__all__ = [
    "about_page_model",
    "backups_page_model",
    "capsules_page_model",
    "dashboard_page_model",
    "health_page_model",
    "instance_actions",
    "instance_detail_page_model",
    "instances_page_model",
    "logs_page_model",
    "network_page_model",
    "restore_page_model",
    "security_page_model",
    "settings_page_model",
]