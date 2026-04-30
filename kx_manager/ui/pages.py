"""
Konnaxion Capsule Manager UI page definitions.

This module is intentionally framework-neutral. It defines the canonical page
registry, navigation structure, page metadata, action bindings, and lightweight
render models consumed by kx_manager.ui.app or any future desktop/web UI layer.

The UI must never execute privileged operations directly. Buttons and forms
should create Manager API requests, which then become allowlisted Konnaxion
Agent actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Iterable, Mapping, Sequence

from kx_shared.konnaxion_constants import (
    BackupStatus,
    ExposureMode,
    InstanceState,
    NetworkProfile,
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


# ---------------------------------------------------------------------
# Page identity
# ---------------------------------------------------------------------


class PageId(StrEnum):
    DASHBOARD = "dashboard"
    CAPSULES = "capsules"
    CAPSULE_IMPORT = "capsule_import"
    INSTANCES = "instances"
    INSTANCE_DETAIL = "instance_detail"
    INSTANCE_CREATE = "instance_create"
    SECURITY = "security"
    NETWORK = "network"
    BACKUPS = "backups"
    RESTORE = "restore"
    LOGS = "logs"
    HEALTH = "health"
    SETTINGS = "settings"
    ABOUT = "about"


class PageGroup(StrEnum):
    OVERVIEW = "overview"
    OPERATIONS = "operations"
    SAFETY = "safety"
    SYSTEM = "system"


class UiAction(StrEnum):
    OPEN_INSTANCE = "open_instance"
    IMPORT_CAPSULE = "import_capsule"
    VERIFY_CAPSULE = "verify_capsule"
    CREATE_INSTANCE = "create_instance"
    START_INSTANCE = "start_instance"
    STOP_INSTANCE = "stop_instance"
    UPDATE_INSTANCE = "update_instance"
    ROLLBACK_INSTANCE = "rollback_instance"
    CREATE_BACKUP = "create_backup"
    VERIFY_BACKUP = "verify_backup"
    RESTORE_BACKUP = "restore_backup"
    RESTORE_BACKUP_NEW = "restore_backup_new"
    RUN_SECURITY_CHECK = "run_security_check"
    SET_NETWORK_PROFILE = "set_network_profile"
    DISABLE_PUBLIC_MODE = "disable_public_mode"
    VIEW_LOGS = "view_logs"
    VIEW_HEALTH = "view_health"


class ActionIntent(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    WARNING = "warning"
    DANGER = "danger"


@dataclass(slots=True, frozen=True)
class PageAction:
    """UI action metadata.

    The actual operation must be executed by the Manager API/Agent, not by this
    UI metadata layer.
    """

    action: UiAction
    label: str
    intent: ActionIntent = ActionIntent.SECONDARY
    requires_confirmation: bool = False
    disabled: bool = False
    reason_disabled: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "label": self.label,
            "intent": self.intent.value,
            "requires_confirmation": self.requires_confirmation,
            "disabled": self.disabled,
            "reason_disabled": self.reason_disabled,
            "payload": dict(self.payload),
        }


@dataclass(slots=True, frozen=True)
class PageDefinition:
    page_id: PageId
    title: str
    route: str
    group: PageGroup
    nav_label: str | None = None
    description: str = ""
    icon: str = ""
    order: int = 100
    visible_in_nav: bool = True
    requires_instance: bool = False

    def nav_text(self) -> str:
        return self.nav_label or self.title

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id.value,
            "title": self.title,
            "route": self.route,
            "group": self.group.value,
            "nav_label": self.nav_text(),
            "description": self.description,
            "icon": self.icon,
            "order": self.order,
            "visible_in_nav": self.visible_in_nav,
            "requires_instance": self.requires_instance,
        }


@dataclass(slots=True, frozen=True)
class NavigationGroup:
    group: PageGroup
    label: str
    pages: Sequence[PageDefinition]

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.group.value,
            "label": self.label,
            "pages": [page.to_dict() for page in self.pages],
        }


@dataclass(slots=True, frozen=True)
class PageContext:
    """Current UI context shared across page render builders."""

    selected_instance_id: str | None = None
    selected_capsule_id: str | None = None
    selected_backup_id: str | None = None
    current_route: str = "/"
    user_display_name: str | None = None


@dataclass(slots=True, frozen=True)
class Alert:
    level: str
    title: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "title": self.title,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(slots=True, frozen=True)
class MetricCard:
    label: str
    value: str
    help_text: str = ""
    status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            "help_text": self.help_text,
            "status": self.status,
        }


@dataclass(slots=True, frozen=True)
class PageRenderModel:
    """Framework-neutral model consumed by the UI renderer."""

    page: PageDefinition
    title: str
    subtitle: str = ""
    metrics: Sequence[MetricCard] = field(default_factory=tuple)
    alerts: Sequence[Alert] = field(default_factory=tuple)
    actions: Sequence[PageAction] = field(default_factory=tuple)
    sections: Mapping[str, Any] = field(default_factory=dict)
    breadcrumbs: Sequence[str] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page.to_dict(),
            "title": self.title,
            "subtitle": self.subtitle,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "alerts": [alert.to_dict() for alert in self.alerts],
            "actions": [action.to_dict() for action in self.actions],
            "sections": dict(self.sections),
            "breadcrumbs": list(self.breadcrumbs),
        }


# ---------------------------------------------------------------------
# Canonical page registry
# ---------------------------------------------------------------------


PAGE_REGISTRY: tuple[PageDefinition, ...] = (
    PageDefinition(
        page_id=PageId.DASHBOARD,
        title="Dashboard",
        route="/",
        group=PageGroup.OVERVIEW,
        description="Instance status, security state, backups, and quick actions.",
        icon="layout-dashboard",
        order=10,
    ),
    PageDefinition(
        page_id=PageId.CAPSULES,
        title="Capsules",
        route="/capsules",
        group=PageGroup.OPERATIONS,
        description="Verify, import, and inspect Konnaxion Capsules.",
        icon="package",
        order=20,
    ),
    PageDefinition(
        page_id=PageId.CAPSULE_IMPORT,
        title="Import Capsule",
        route="/capsules/import",
        group=PageGroup.OPERATIONS,
        nav_label="Import Capsule",
        description="Import a signed .kxcap file.",
        icon="upload",
        order=21,
        visible_in_nav=False,
    ),
    PageDefinition(
        page_id=PageId.INSTANCES,
        title="Instances",
        route="/instances",
        group=PageGroup.OPERATIONS,
        description="Create, start, stop, update, and inspect Konnaxion Instances.",
        icon="server",
        order=30,
    ),
    PageDefinition(
        page_id=PageId.INSTANCE_DETAIL,
        title="Instance Detail",
        route="/instances/detail",
        group=PageGroup.OPERATIONS,
        description="Detailed status for one Konnaxion Instance.",
        icon="server-cog",
        order=31,
        visible_in_nav=False,
        requires_instance=True,
    ),
    PageDefinition(
        page_id=PageId.INSTANCE_CREATE,
        title="Create Instance",
        route="/instances/create",
        group=PageGroup.OPERATIONS,
        description="Create a new Konnaxion Instance from an imported Capsule.",
        icon="plus",
        order=32,
        visible_in_nav=False,
    ),
    PageDefinition(
        page_id=PageId.SECURITY,
        title="Security Gate",
        route="/security",
        group=PageGroup.SAFETY,
        description="Run and inspect Security Gate checks.",
        icon="shield-check",
        order=40,
        requires_instance=True,
    ),
    PageDefinition(
        page_id=PageId.NETWORK,
        title="Network",
        route="/network",
        group=PageGroup.SAFETY,
        description="Choose canonical network profiles and exposure modes.",
        icon="network",
        order=50,
        requires_instance=True,
    ),
    PageDefinition(
        page_id=PageId.BACKUPS,
        title="Backups",
        route="/backups",
        group=PageGroup.OPERATIONS,
        description="Create, verify, and inspect application backups.",
        icon="database-backup",
        order=60,
        requires_instance=True,
    ),
    PageDefinition(
        page_id=PageId.RESTORE,
        title="Restore",
        route="/restore",
        group=PageGroup.OPERATIONS,
        description="Restore a backup into the same or a new Konnaxion Instance.",
        icon="rotate-ccw",
        order=70,
        requires_instance=True,
    ),
    PageDefinition(
        page_id=PageId.LOGS,
        title="Logs",
        route="/logs",
        group=PageGroup.SYSTEM,
        description="View service and Agent logs.",
        icon="scroll-text",
        order=80,
        requires_instance=True,
    ),
    PageDefinition(
        page_id=PageId.HEALTH,
        title="Health",
        route="/health",
        group=PageGroup.SYSTEM,
        description="View service healthchecks and runtime readiness.",
        icon="activity",
        order=90,
        requires_instance=True,
    ),
    PageDefinition(
        page_id=PageId.SETTINGS,
        title="Settings",
        route="/settings",
        group=PageGroup.SYSTEM,
        description="Manager settings and runtime variables.",
        icon="settings",
        order=100,
    ),
    PageDefinition(
        page_id=PageId.ABOUT,
        title="About",
        route="/about",
        group=PageGroup.SYSTEM,
        description="Product and build information.",
        icon="info",
        order=110,
    ),
)


# ---------------------------------------------------------------------
# Page lookup and navigation
# ---------------------------------------------------------------------


def get_page(page_id: PageId | str) -> PageDefinition:
    normalized = PageId(page_id)
    for page in PAGE_REGISTRY:
        if page.page_id == normalized:
            return page
    raise KeyError(f"Unknown page: {page_id}")


def find_page_by_route(route: str) -> PageDefinition:
    normalized = normalize_route(route)
    for page in PAGE_REGISTRY:
        if page.route == normalized:
            return page
    return get_page(PageId.DASHBOARD)


def normalize_route(route: str) -> str:
    if not route:
        return "/"
    normalized = route.strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if normalized != "/":
        normalized = normalized.rstrip("/")
    return normalized


def build_navigation(
    *,
    selected_instance_id: str | None = None,
    include_hidden: bool = False,
) -> list[NavigationGroup]:
    pages = [
        page
        for page in PAGE_REGISTRY
        if (include_hidden or page.visible_in_nav)
        and (not page.requires_instance or selected_instance_id is not None)
    ]

    groups: list[NavigationGroup] = []
    labels = {
        PageGroup.OVERVIEW: "Overview",
        PageGroup.OPERATIONS: "Operations",
        PageGroup.SAFETY: "Safety",
        PageGroup.SYSTEM: "System",
    }

    for group in PageGroup:
        grouped_pages = sorted(
            [page for page in pages if page.group == group],
            key=lambda item: item.order,
        )
        if grouped_pages:
            groups.append(
                NavigationGroup(
                    group=group,
                    label=labels[group],
                    pages=tuple(grouped_pages),
                )
            )

    return groups


def build_breadcrumbs(page: PageDefinition, context: PageContext | None = None) -> tuple[str, ...]:
    crumbs = ["Konnaxion Capsule Manager"]

    if page.group != PageGroup.OVERVIEW:
        crumbs.append(page.group.value.replace("_", " ").title())

    crumbs.append(page.title)

    if context and context.selected_instance_id and page.requires_instance:
        crumbs.append(context.selected_instance_id)

    return tuple(crumbs)


# ---------------------------------------------------------------------
# Render-model builders
# ---------------------------------------------------------------------


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
        MetricCard("Instances", str(len(instances)), "Total local Konnaxion Instances."),
        MetricCard("Running", str(len(running)), "Instances currently running.", status="ok" if running else None),
        MetricCard("Security blocked", str(len(blocked)), "Instances blocked by Security Gate.", status="danger" if blocked else "ok"),
        MetricCard("Capsules", str(len(summary.capsules)), "Imported or known Konnaxion Capsules."),
    )

    alerts = tuple(security_alerts_from_instances(instances))

    actions = (
        PageAction(UiAction.IMPORT_CAPSULE, "Import Capsule", ActionIntent.PRIMARY),
        PageAction(UiAction.CREATE_INSTANCE, "Create Instance", ActionIntent.SECONDARY),
    )

    return PageRenderModel(
        page=page,
        title="Konnaxion Capsule Manager",
        subtitle="Private-by-default capsule and instance control.",
        metrics=metrics,
        alerts=alerts,
        actions=actions,
        sections={
            "instances": [instance_summary_row(item) for item in instances],
            "capsules": [capsule_summary_row(item) for item in summary.capsules],
            "recent_backups": [backup_summary_row(item) for item in summary.recent_backups],
            "security_alerts": [item.to_dict() for item in summary.security_alerts],
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
            MetricCard("Verified", str(sum(1 for item in capsules if item.verified)), status="ok"),
            MetricCard("Unsigned", str(sum(1 for item in capsules if not item.signed)), status="danger"),
        ),
        alerts=tuple(unsigned_capsule_alerts(capsules)),
        actions=actions,
        sections={"capsules": [capsule_summary_row(item) for item in capsules]},
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
            MetricCard("Running", str(sum(1 for item in instances if item.state == InstanceState.RUNNING))),
            MetricCard("Stopped", str(sum(1 for item in instances if item.state == InstanceState.STOPPED))),
            MetricCard("Blocked", str(sum(1 for item in instances if item.state == InstanceState.SECURITY_BLOCKED)), status="danger"),
        ),
        alerts=tuple(security_alerts_from_instances(instances)),
        actions=(PageAction(UiAction.CREATE_INSTANCE, "Create Instance", ActionIntent.PRIMARY),),
        sections={"instances": [instance_summary_row(item) for item in instances]},
        breadcrumbs=build_breadcrumbs(page, context),
    )


def instance_detail_page_model(
    instance: InstanceDetail,
    *,
    context: PageContext | None = None,
) -> PageRenderModel:
    page = get_page(PageId.INSTANCE_DETAIL)
    ctx = context or PageContext(selected_instance_id=instance.instance_id)

    actions = instance_actions(instance)

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
        subtitle=f"{instance.state.value} · {instance.network_profile.value} · {instance.exposure_mode.value}",
        metrics=(
            MetricCard("State", instance.state.value, status=status_level_for_instance(instance.state)),
            MetricCard("Security", instance.security_status.value if instance.security_status else "unknown", status=status_level_for_security(instance.security_status)),
            MetricCard("Network", instance.network_profile.value),
            MetricCard("Capsule", instance.capsule_version or instance.capsule_id or "unknown"),
        ),
        alerts=tuple(alerts),
        actions=actions,
        sections={
            "summary": instance_summary_row(instance),
            "services": [service_status_row(service) for service in instance.services],
            "variables": runtime_variables_table(instance.variables) if instance.variables else {},
            "health": instance.health.model_dump(mode="json") if instance.health else None,
            "security_gate": instance.security_gate.model_dump(mode="json") if instance.security_gate else None,
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
            MetricCard("Status", report.status.value, status=status_level_for_security(report.status)),
            MetricCard("Checks", str(len(report.results))),
            MetricCard("Blocking failures", str(len(failures)), status="danger" if failures else "ok"),
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
            "blocking_failures": [result.model_dump(mode="json") for result in failures],
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
            MetricCard("Exposure", instance.exposure_mode.value, status=status_level_for_exposure(instance.exposure_mode)),
            MetricCard("Public mode", "enabled" if instance.public_mode_enabled else "disabled", status="warning" if instance.public_mode_enabled else "ok"),
        ),
        alerts=tuple(alerts),
        actions=(
            PageAction(UiAction.SET_NETWORK_PROFILE, "Set Network Profile", ActionIntent.PRIMARY, payload={"instance_id": instance.instance_id}),
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
            MetricCard("Failed", str(len(failed)), status="danger" if failed else "ok"),
        ),
        alerts=tuple(backup_alerts(backups)),
        actions=(
            PageAction(UiAction.CREATE_BACKUP, "Create Backup", ActionIntent.PRIMARY, payload={"instance_id": instance.instance_id}),
            PageAction(UiAction.VERIFY_BACKUP, "Verify Backup", ActionIntent.SECONDARY),
        ),
        sections={"backups": [backup_summary_row(backup) for backup in backups]},
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
            MetricCard("Verified backups", str(len(verified_backups)), status="ok" if verified_backups else "warning"),
            MetricCard("Latest restore", latest_report.status.value if latest_report else "none", status=status_level_for_restore(latest_report.status if latest_report else None)),
        ),
        alerts=tuple(alerts),
        actions=(
            PageAction(UiAction.RESTORE_BACKUP_NEW, "Restore to New Instance", ActionIntent.PRIMARY, requires_confirmation=True),
            PageAction(UiAction.RESTORE_BACKUP, "Restore Same Instance", ActionIntent.DANGER, requires_confirmation=True),
        ),
        sections={
            "instance": instance_summary_row(instance),
            "verified_backups": [backup_summary_row(backup) for backup in verified_backups],
            "latest_report": latest_report.model_dump(mode="json") if latest_report else None,
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
        actions=(PageAction(UiAction.VIEW_LOGS, "Refresh Logs", ActionIntent.PRIMARY),),
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
        check for check in health.checks if check.status in {"unhealthy", "unknown"}
    ]

    return PageRenderModel(
        page=page,
        title="Health",
        subtitle=f"Instance {health.instance_id}",
        metrics=(
            MetricCard("Status", health.status, status="ok" if health.healthy else "danger"),
            MetricCard("Checks", str(len(health.checks))),
            MetricCard("Unhealthy/unknown", str(len(unhealthy)), status="danger" if unhealthy else "ok"),
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
        actions=(PageAction(UiAction.VIEW_HEALTH, "Refresh Health", ActionIntent.PRIMARY),),
        sections={"checks": [check.model_dump(mode="json") for check in health.checks]},
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
            MetricCard("Exposure", variables.kx_exposure_mode.value, status=status_level_for_exposure(variables.kx_exposure_mode)),
            MetricCard("Backups", "enabled" if variables.kx_backup_enabled else "disabled", status="ok" if variables.kx_backup_enabled else "warning"),
        ),
        sections={"variables": runtime_variables_table(variables)},
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
        sections={"product": product.model_dump(mode="json")},
        breadcrumbs=build_breadcrumbs(page, context),
    )


# ---------------------------------------------------------------------
# Row/table helpers
# ---------------------------------------------------------------------


def instance_summary_row(instance: InstanceSummary) -> dict[str, Any]:
    return {
        "instance_id": instance.instance_id,
        "state": instance.state.value,
        "state_status": status_level_for_instance(instance.state),
        "capsule_id": instance.capsule_id,
        "capsule_version": instance.capsule_version,
        "network_profile": instance.network_profile.value,
        "exposure_mode": instance.exposure_mode.value,
        "public_mode_enabled": instance.public_mode_enabled,
        "public_mode_expires_at": instance.public_mode_expires_at.isoformat()
        if instance.public_mode_expires_at
        else None,
        "url": instance.url,
        "security_status": instance.security_status.value if instance.security_status else None,
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
        "imported_at": capsule.imported_at.isoformat() if capsule.imported_at else None,
        "verified": capsule.verified,
        "signed": capsule.signed,
    }


def backup_summary_row(backup: BackupSummary) -> dict[str, Any]:
    return {
        "backup_id": backup.backup_id,
        "instance_id": backup.instance_id,
        "status": backup.status.value,
        "status_level": status_level_for_backup(backup.status),
        "backup_class": backup.backup_class,
        "path": str(backup.path) if backup.path else None,
        "size_bytes": backup.size_bytes,
        "created_at": backup.created_at.isoformat() if backup.created_at else None,
        "verified_at": backup.verified_at.isoformat() if backup.verified_at else None,
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
        "started_at": service.started_at.isoformat() if service.started_at else None,
        "message": service.message,
    }


def runtime_variables_table(variables: KxRuntimeVariables) -> dict[str, Any]:
    return {
        "KX_INSTANCE_ID": variables.kx_instance_id,
        "KX_CAPSULE_ID": variables.kx_capsule_id,
        "KX_CAPSULE_VERSION": variables.kx_capsule_version,
        "KX_APP_VERSION": variables.kx_app_version,
        "KX_PARAM_VERSION": variables.kx_param_version,
        "KX_NETWORK_PROFILE": variables.kx_network_profile.value,
        "KX_EXPOSURE_MODE": variables.kx_exposure_mode.value,
        "KX_PUBLIC_MODE_ENABLED": variables.kx_public_mode_enabled,
        "KX_PUBLIC_MODE_EXPIRES_AT": variables.kx_public_mode_expires_at.isoformat()
        if variables.kx_public_mode_expires_at
        else None,
        "KX_BACKUP_ENABLED": variables.kx_backup_enabled,
        "KX_BACKUP_ROOT": str(variables.kx_backup_root),
        "KX_HOST": variables.kx_host,
    }


# ---------------------------------------------------------------------
# Action helpers
# ---------------------------------------------------------------------


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
            reason_disabled="Instance is not in a startable state." if not can_start else "Security Gate is blocking startup.",
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


# ---------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------


def security_alerts_from_instances(instances: Iterable[InstanceSummary]) -> list[Alert]:
    alerts: list[Alert] = []

    for instance in instances:
        if instance.state == InstanceState.SECURITY_BLOCKED:
            alerts.append(
                Alert(
                    level="danger",
                    title="Instance security blocked",
                    message=f"Instance {instance.instance_id} is blocked by the Security Gate.",
                    details={"instance_id": instance.instance_id},
                )
            )
        elif instance.security_status == SecurityGateStatus.FAIL_BLOCKING:
            alerts.append(
                Alert(
                    level="danger",
                    title="Security Gate failure",
                    message=f"Instance {instance.instance_id} has a blocking Security Gate failure.",
                    details={"instance_id": instance.instance_id},
                )
            )
        elif instance.security_status == SecurityGateStatus.WARN:
            alerts.append(
                Alert(
                    level="warning",
                    title="Security warning",
                    message=f"Instance {instance.instance_id} has non-blocking security warnings.",
                    details={"instance_id": instance.instance_id},
                )
            )

    return alerts


def unsigned_capsule_alerts(capsules: Iterable[CapsuleSummary]) -> list[Alert]:
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
    alerts: list[Alert] = []

    for backup in backups:
        if backup.status == BackupStatus.FAILED:
            alerts.append(
                Alert(
                    level="danger",
                    title="Backup failed",
                    message=f"Backup {backup.backup_id} failed.",
                    details={"backup_id": backup.backup_id, "instance_id": backup.instance_id},
                )
            )
        elif backup.status == BackupStatus.QUARANTINED:
            alerts.append(
                Alert(
                    level="danger",
                    title="Backup quarantined",
                    message=f"Backup {backup.backup_id} was quarantined by a safety check.",
                    details={"backup_id": backup.backup_id, "instance_id": backup.instance_id},
                )
            )

    return alerts


# ---------------------------------------------------------------------
# Status display helpers
# ---------------------------------------------------------------------


def status_level_for_instance(state: InstanceState | None) -> str:
    if state is None:
        return "unknown"

    if state == InstanceState.RUNNING:
        return "ok"

    if state in {InstanceState.CREATED, InstanceState.READY, InstanceState.STOPPED}:
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

    if state in {InstanceState.FAILED, InstanceState.SECURITY_BLOCKED}:
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

    if status in {SecurityGateStatus.SKIPPED, SecurityGateStatus.UNKNOWN}:
        return "neutral"

    return "unknown"


def status_level_for_backup(status: BackupStatus | None) -> str:
    if status is None:
        return "unknown"

    if status == BackupStatus.VERIFIED:
        return "ok"

    if status in {BackupStatus.CREATED, BackupStatus.RUNNING, BackupStatus.VERIFYING}:
        return "info"

    if status in {BackupStatus.EXPIRED, BackupStatus.DELETED}:
        return "neutral"

    if status in {BackupStatus.FAILED, BackupStatus.QUARANTINED}:
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

    if status in {RestoreStatus.DEGRADED, RestoreStatus.ROLLED_BACK}:
        return "warning"

    if status == RestoreStatus.FAILED:
        return "danger"

    return "unknown"


def status_level_for_exposure(exposure: ExposureMode | None) -> str:
    if exposure is None:
        return "unknown"

    if exposure == ExposureMode.PRIVATE:
        return "ok"

    if exposure in {ExposureMode.LAN, ExposureMode.VPN}:
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
    "ActionIntent",
    "Alert",
    "MetricCard",
    "NavigationGroup",
    "PAGE_REGISTRY",
    "PageAction",
    "PageContext",
    "PageDefinition",
    "PageGroup",
    "PageId",
    "PageRenderModel",
    "UiAction",
    "about_page_model",
    "backup_alerts",
    "backup_summary_row",
    "backups_page_model",
    "build_breadcrumbs",
    "build_navigation",
    "capsule_summary_row",
    "capsules_page_model",
    "dashboard_page_model",
    "find_page_by_route",
    "get_page",
    "health_page_model",
    "instance_actions",
    "instance_detail_page_model",
    "instance_summary_row",
    "instances_page_model",
    "logs_page_model",
    "network_page_model",
    "normalize_route",
    "restore_page_model",
    "runtime_variables_table",
    "security_alerts_from_instances",
    "security_page_model",
    "service_status_row",
    "settings_page_model",
    "status_level_for_backup",
    "status_level_for_exposure",
    "status_level_for_instance",
    "status_level_for_restore",
    "status_level_for_security",
    "status_level_for_service",
    "unsigned_capsule_alerts",
]
