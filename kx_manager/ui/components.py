"""
Reusable UI components for Konnaxion Capsule Manager.

This module is intentionally dependency-light. It produces safe HTML fragments
and serializable component models that can be rendered by a simple web UI,
FastAPI/Jinja templates, Streamlit wrappers, or tests.

Rules:

- Display labels may be friendly.
- Stored values remain canonical enum/string values.
- HTML output is escaped by default.
- Components must not invent service names, states, profiles, exposure modes,
  security statuses, or action names.
"""

from __future__ import annotations

from dataclasses import dataclass, field, is_dataclass, asdict
from datetime import datetime
from enum import StrEnum
from html import escape
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from kx_shared.konnaxion_constants import (
    BackupStatus,
    DockerService,
    ExposureMode,
    InstanceState,
    NetworkProfile,
    RestoreStatus,
    RollbackStatus,
    SecurityGateStatus,
)
from kx_shared.types import (
    BackupRecord,
    CapsuleArtifact,
    InstanceID,
    InstanceRecord,
    RuntimeHealth,
    RuntimeEndpoint,
    SecurityGateFinding,
    SecurityGateResult,
    ServiceHealth,
)


# ---------------------------------------------------------------------
# Component primitives
# ---------------------------------------------------------------------

Html = str


class ComponentTone(StrEnum):
    """Visual tone for UI components."""

    DEFAULT = "default"
    SUCCESS = "success"
    WARNING = "warning"
    DANGER = "danger"
    INFO = "info"
    MUTED = "muted"


class ComponentSize(StrEnum):
    """Visual size hint for UI components."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


@dataclass(frozen=True, slots=True)
class ComponentAction:
    """A UI action description.

    The action_name should map to Manager/API operations, not arbitrary shell
    commands.
    """

    label: str
    action_name: str
    method: str = "POST"
    href: str | None = None
    disabled: bool = False
    danger: bool = False
    confirm: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Metric:
    """Small metric tile."""

    label: str
    value: str
    tone: ComponentTone = ComponentTone.DEFAULT
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class TableColumn:
    """Table column definition."""

    key: str
    label: str
    align: str = "left"


@dataclass(frozen=True, slots=True)
class EmptyState:
    """Empty state model."""

    title: str
    message: str
    action: ComponentAction | None = None


# ---------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------

def html_attrs(attrs: Mapping[str, Any]) -> str:
    """Serialize HTML attributes with escaping."""

    parts: list[str] = []
    for key, value in attrs.items():
        if value is None or value is False:
            continue
        normalized_key = key.rstrip("_").replace("_", "-")
        if value is True:
            parts.append(escape(normalized_key))
        else:
            parts.append(f'{escape(normalized_key)}="{escape(str(value), quote=True)}"')
    return " ".join(parts)


def tag(name: str, content: str = "", **attrs: Any) -> Html:
    """Build a simple escaped-attribute HTML tag."""

    attr_text = html_attrs(attrs)
    if attr_text:
        return f"<{name} {attr_text}>{content}</{name}>"
    return f"<{name}>{content}</{name}>"


def div(content: str = "", **attrs: Any) -> Html:
    return tag("div", content, **attrs)


def span(content: str = "", **attrs: Any) -> Html:
    return tag("span", content, **attrs)


def p(content: str = "", **attrs: Any) -> Html:
    return tag("p", content, **attrs)


def h(level: int, content: str = "", **attrs: Any) -> Html:
    if level < 1 or level > 6:
        raise ValueError("heading level must be between 1 and 6")
    return tag(f"h{level}", content, **attrs)


def button(label: str, *, disabled: bool = False, danger: bool = False, **attrs: Any) -> Html:
    """Render a button."""

    classes = ["kx-button"]
    if danger:
        classes.append("kx-button-danger")
    if disabled:
        classes.append("kx-button-disabled")
    attrs = {"type": "button", "disabled": disabled, "class_": " ".join(classes), **attrs}
    return tag("button", escape(label), **attrs)


def link(label: str, href: str, **attrs: Any) -> Html:
    """Render a safe link."""

    return tag("a", escape(label), href=href, **attrs)


def format_datetime(value: datetime | str | None) -> str:
    """Format datetime-like values for display."""

    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def format_bytes(size_bytes: int | None) -> str:
    """Format bytes for human display."""

    if size_bytes is None:
        return "—"

    units = ("B", "KB", "MB", "GB", "TB")
    size = float(size_bytes)
    unit = units[0]

    for unit in units:
        if size < 1024 or unit == units[-1]:
            break
        size /= 1024

    if unit == "B":
        return f"{int(size)} {unit}"
    return f"{size:.1f} {unit}"


def humanize(value: str | StrEnum | None) -> str:
    """Convert canonical values to readable labels without changing storage."""

    if value is None:
        return "—"
    raw = value.value if isinstance(value, StrEnum) else str(value)
    return raw.replace("_", " ").replace("-", " ").title()


def as_mapping(value: Any) -> Mapping[str, Any]:
    """Convert known object types to mappings for generic components."""

    if isinstance(value, Mapping):
        return value
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    raise TypeError(f"cannot convert {type(value).__name__} to mapping")


# ---------------------------------------------------------------------
# Tone mapping
# ---------------------------------------------------------------------

def tone_for_instance_state(state: InstanceState | str) -> ComponentTone:
    state_value = InstanceState(state)
    return {
        InstanceState.RUNNING: ComponentTone.SUCCESS,
        InstanceState.READY: ComponentTone.INFO,
        InstanceState.CREATED: ComponentTone.MUTED,
        InstanceState.IMPORTING: ComponentTone.INFO,
        InstanceState.VERIFYING: ComponentTone.INFO,
        InstanceState.STARTING: ComponentTone.INFO,
        InstanceState.STOPPING: ComponentTone.WARNING,
        InstanceState.STOPPED: ComponentTone.MUTED,
        InstanceState.UPDATING: ComponentTone.INFO,
        InstanceState.ROLLING_BACK: ComponentTone.WARNING,
        InstanceState.DEGRADED: ComponentTone.WARNING,
        InstanceState.FAILED: ComponentTone.DANGER,
        InstanceState.SECURITY_BLOCKED: ComponentTone.DANGER,
    }[state_value]


def tone_for_security_status(status: SecurityGateStatus | str) -> ComponentTone:
    status_value = SecurityGateStatus(status)
    return {
        SecurityGateStatus.PASS: ComponentTone.SUCCESS,
        SecurityGateStatus.WARN: ComponentTone.WARNING,
        SecurityGateStatus.FAIL_BLOCKING: ComponentTone.DANGER,
        SecurityGateStatus.SKIPPED: ComponentTone.MUTED,
        SecurityGateStatus.UNKNOWN: ComponentTone.WARNING,
    }[status_value]


def tone_for_backup_status(status: BackupStatus | str) -> ComponentTone:
    status_value = BackupStatus(status)
    return {
        BackupStatus.CREATED: ComponentTone.MUTED,
        BackupStatus.RUNNING: ComponentTone.INFO,
        BackupStatus.VERIFYING: ComponentTone.INFO,
        BackupStatus.VERIFIED: ComponentTone.SUCCESS,
        BackupStatus.FAILED: ComponentTone.DANGER,
        BackupStatus.EXPIRED: ComponentTone.MUTED,
        BackupStatus.DELETED: ComponentTone.MUTED,
        BackupStatus.QUARANTINED: ComponentTone.DANGER,
    }[status_value]


def tone_for_restore_status(status: RestoreStatus | str) -> ComponentTone:
    status_value = RestoreStatus(status)
    return {
        RestoreStatus.PLANNED: ComponentTone.MUTED,
        RestoreStatus.PREFLIGHT: ComponentTone.INFO,
        RestoreStatus.CREATING_PRE_RESTORE_BACKUP: ComponentTone.INFO,
        RestoreStatus.RESTORING_DATABASE: ComponentTone.INFO,
        RestoreStatus.RESTORING_MEDIA: ComponentTone.INFO,
        RestoreStatus.RUNNING_MIGRATIONS: ComponentTone.INFO,
        RestoreStatus.RUNNING_SECURITY_GATE: ComponentTone.INFO,
        RestoreStatus.RUNNING_HEALTHCHECKS: ComponentTone.INFO,
        RestoreStatus.RESTORED: ComponentTone.SUCCESS,
        RestoreStatus.DEGRADED: ComponentTone.WARNING,
        RestoreStatus.FAILED: ComponentTone.DANGER,
        RestoreStatus.ROLLED_BACK: ComponentTone.WARNING,
    }[status_value]


def tone_for_rollback_status(status: RollbackStatus | str) -> ComponentTone:
    status_value = RollbackStatus(status)
    return {
        RollbackStatus.PLANNED: ComponentTone.MUTED,
        RollbackStatus.RUNNING: ComponentTone.INFO,
        RollbackStatus.CAPSULE_REPOINTED: ComponentTone.INFO,
        RollbackStatus.DATA_RESTORED: ComponentTone.INFO,
        RollbackStatus.HEALTHCHECKING: ComponentTone.INFO,
        RollbackStatus.COMPLETED: ComponentTone.SUCCESS,
        RollbackStatus.FAILED: ComponentTone.DANGER,
    }[status_value]


def tone_for_profile(profile: NetworkProfile | str) -> ComponentTone:
    profile_value = NetworkProfile(profile)
    return {
        NetworkProfile.LOCAL_ONLY: ComponentTone.MUTED,
        NetworkProfile.INTRANET_PRIVATE: ComponentTone.SUCCESS,
        NetworkProfile.PRIVATE_TUNNEL: ComponentTone.SUCCESS,
        NetworkProfile.PUBLIC_TEMPORARY: ComponentTone.WARNING,
        NetworkProfile.PUBLIC_VPS: ComponentTone.WARNING,
        NetworkProfile.OFFLINE: ComponentTone.MUTED,
    }[profile_value]


def tone_for_exposure(exposure_mode: ExposureMode | str) -> ComponentTone:
    exposure_value = ExposureMode(exposure_mode)
    return {
        ExposureMode.PRIVATE: ComponentTone.SUCCESS,
        ExposureMode.LAN: ComponentTone.SUCCESS,
        ExposureMode.VPN: ComponentTone.SUCCESS,
        ExposureMode.TEMPORARY_TUNNEL: ComponentTone.WARNING,
        ExposureMode.PUBLIC: ComponentTone.WARNING,
    }[exposure_value]


def tone_for_service_health(status: str) -> ComponentTone:
    return {
        "healthy": ComponentTone.SUCCESS,
        "unhealthy": ComponentTone.DANGER,
        "starting": ComponentTone.INFO,
        "unknown": ComponentTone.WARNING,
        "not_running": ComponentTone.MUTED,
    }.get(status, ComponentTone.WARNING)


# ---------------------------------------------------------------------
# Basic components
# ---------------------------------------------------------------------

def badge(label: str, *, tone: ComponentTone = ComponentTone.DEFAULT, title: str | None = None) -> Html:
    """Render a status badge."""

    return span(
        escape(label),
        class_=f"kx-badge kx-badge-{tone.value}",
        title=title,
    )


def status_badge(value: str | StrEnum, *, tone: ComponentTone | None = None) -> Html:
    """Render a generic canonical-value badge."""

    resolved_tone = tone or ComponentTone.DEFAULT
    return badge(humanize(value), tone=resolved_tone, title=str(value.value if isinstance(value, StrEnum) else value))


def instance_state_badge(state: InstanceState | str) -> Html:
    state_value = InstanceState(state)
    return status_badge(state_value, tone=tone_for_instance_state(state_value))


def security_status_badge(status: SecurityGateStatus | str) -> Html:
    status_value = SecurityGateStatus(status)
    return status_badge(status_value, tone=tone_for_security_status(status_value))


def backup_status_badge(status: BackupStatus | str) -> Html:
    status_value = BackupStatus(status)
    return status_badge(status_value, tone=tone_for_backup_status(status_value))


def network_profile_badge(profile: NetworkProfile | str) -> Html:
    profile_value = NetworkProfile(profile)
    return status_badge(profile_value, tone=tone_for_profile(profile_value))


def exposure_mode_badge(exposure_mode: ExposureMode | str) -> Html:
    exposure_value = ExposureMode(exposure_mode)
    return status_badge(exposure_value, tone=tone_for_exposure(exposure_value))


def service_badge(service: DockerService | str) -> Html:
    service_value = DockerService(service)
    return status_badge(service_value, tone=ComponentTone.MUTED)


def card(title: str, body: str, *, footer: str | None = None, tone: ComponentTone = ComponentTone.DEFAULT) -> Html:
    """Render a card."""

    parts = [
        h(3, escape(title), class_="kx-card-title"),
        div(body, class_="kx-card-body"),
    ]
    if footer is not None:
        parts.append(div(footer, class_="kx-card-footer"))
    return div("".join(parts), class_=f"kx-card kx-card-{tone.value}")


def metric_tile(metric: Metric) -> Html:
    """Render a metric tile."""

    detail = p(escape(metric.detail), class_="kx-metric-detail") if metric.detail else ""
    body = (
        div(escape(metric.label), class_="kx-metric-label")
        + div(escape(metric.value), class_="kx-metric-value")
        + detail
    )
    return div(body, class_=f"kx-metric kx-metric-{metric.tone.value}")


def metrics_grid(metrics: Sequence[Metric]) -> Html:
    """Render a grid of metric tiles."""

    return div("".join(metric_tile(metric) for metric in metrics), class_="kx-metrics-grid")


def action_button(action: ComponentAction) -> Html:
    """Render a declarative UI action as a button or link."""

    attrs = {
        "data_action": action.action_name,
        "data_method": action.method,
        "data_confirm": action.confirm,
    }

    if action.href:
        classes = "kx-action-link"
        if action.disabled:
            classes += " kx-action-disabled"
        if action.danger:
            classes += " kx-action-danger"
        return link(action.label, action.href, class_=classes, **attrs)

    return button(
        action.label,
        disabled=action.disabled,
        danger=action.danger,
        **attrs,
    )


def action_bar(actions: Sequence[ComponentAction]) -> Html:
    """Render an action row."""

    return div("".join(action_button(action) for action in actions), class_="kx-action-bar")


def empty_state(state: EmptyState) -> Html:
    """Render an empty state."""

    action_html = action_button(state.action) if state.action else ""
    return div(
        h(3, escape(state.title)) + p(escape(state.message)) + action_html,
        class_="kx-empty-state",
    )


def definition_list(items: Mapping[str, Any]) -> Html:
    """Render key/value details."""

    children: list[str] = []
    for key, value in items.items():
        children.append(tag("dt", escape(humanize(key))))
        children.append(tag("dd", escape(str(value if value is not None else "—"))))
    return tag("dl", "".join(children), class_="kx-definition-list")


def table(columns: Sequence[TableColumn], rows: Sequence[Mapping[str, Any]]) -> Html:
    """Render a simple escaped table."""

    thead = tag(
        "thead",
        tag(
            "tr",
            "".join(
                tag("th", escape(column.label), style=f"text-align:{escape(column.align)}")
                for column in columns
            ),
        ),
    )

    body_rows: list[str] = []
    for row in rows:
        cells = []
        for column in columns:
            value = row.get(column.key, "—")
            rendered = value if isinstance(value, SafeHtml) else escape(str(value))
            cells.append(tag("td", str(rendered), style=f"text-align:{escape(column.align)}"))
        body_rows.append(tag("tr", "".join(cells)))

    tbody = tag("tbody", "".join(body_rows))
    return tag("table", thead + tbody, class_="kx-table")


class SafeHtml(str):
    """Marker type for already-rendered safe component HTML."""


def safe_html(value: str) -> SafeHtml:
    """Mark component-generated HTML as safe for table rendering."""

    return SafeHtml(value)


# ---------------------------------------------------------------------
# Domain components
# ---------------------------------------------------------------------

def endpoint_panel(endpoint: RuntimeEndpoint | None) -> Html:
    """Render runtime endpoint details."""

    if endpoint is None:
        return card(
            "Endpoint",
            p("No endpoint is currently available.", class_="kx-muted"),
            tone=ComponentTone.MUTED,
        )

    body = definition_list(
        {
            "host": endpoint.host,
            "url": endpoint.url,
            "profile": humanize(endpoint.profile),
            "exposure": humanize(endpoint.exposure_mode),
            "public": "yes" if endpoint.is_public else "no",
            "expires_at": format_datetime(endpoint.expires_at),
        }
    )
    return card("Endpoint", body, tone=tone_for_exposure(endpoint.exposure_mode))


def instance_summary_metrics(instance: InstanceRecord) -> tuple[Metric, ...]:
    """Build summary metrics for an instance."""

    return (
        Metric("Instance", str(instance.instance_id), ComponentTone.DEFAULT),
        Metric("State", humanize(instance.state), tone_for_instance_state(instance.state)),
        Metric("Network", humanize(instance.network_profile), tone_for_profile(instance.network_profile)),
        Metric("Exposure", humanize(instance.exposure_mode), tone_for_exposure(instance.exposure_mode)),
        Metric("Capsule", str(instance.capsule_version), ComponentTone.INFO),
        Metric("Updated", format_datetime(instance.updated_at), ComponentTone.MUTED),
    )


def instance_card(instance: InstanceRecord, *, actions: Sequence[ComponentAction] = ()) -> Html:
    """Render one instance summary card."""

    header = (
        span(escape(str(instance.instance_id)), class_="kx-instance-id")
        + " "
        + instance_state_badge(instance.state)
    )
    body = (
        div(header, class_="kx-instance-header")
        + metrics_grid(instance_summary_metrics(instance))
    )
    if instance.endpoint:
        body += endpoint_panel(instance.endpoint)
    footer = action_bar(actions) if actions else None
    return card("Konnaxion Instance", body, footer=footer, tone=tone_for_instance_state(instance.state))


def instance_table(instances: Sequence[InstanceRecord]) -> Html:
    """Render a table of instances."""

    columns = (
        TableColumn("instance_id", "Instance"),
        TableColumn("state", "State"),
        TableColumn("network_profile", "Network"),
        TableColumn("exposure_mode", "Exposure"),
        TableColumn("capsule_version", "Capsule"),
        TableColumn("updated_at", "Updated"),
    )

    rows = [
        {
            "instance_id": instance.instance_id,
            "state": safe_html(instance_state_badge(instance.state)),
            "network_profile": safe_html(network_profile_badge(instance.network_profile)),
            "exposure_mode": safe_html(exposure_mode_badge(instance.exposure_mode)),
            "capsule_version": instance.capsule_version,
            "updated_at": format_datetime(instance.updated_at),
        }
        for instance in instances
    ]

    if not rows:
        return empty_state(
            EmptyState(
                title="No instances",
                message="Import a capsule and create an instance to begin.",
            )
        )

    return table(columns, rows)


def capsule_table(capsules: Sequence[CapsuleArtifact]) -> Html:
    """Render imported capsule artifacts."""

    columns = (
        TableColumn("capsule_id", "Capsule"),
        TableColumn("capsule_version", "Version"),
        TableColumn("path", "Path"),
        TableColumn("checksum", "Checksum"),
        TableColumn("imported_at", "Imported"),
    )

    rows = [
        {
            "capsule_id": capsule.capsule_id,
            "capsule_version": capsule.capsule_version,
            "path": capsule.path,
            "checksum": capsule.checksum or "—",
            "imported_at": format_datetime(capsule.imported_at),
        }
        for capsule in capsules
    ]

    if not rows:
        return empty_state(
            EmptyState(
                title="No capsules",
                message="Import a signed .kxcap file to create or update an instance.",
            )
        )

    return table(columns, rows)


def security_finding_table(findings: Sequence[SecurityGateFinding]) -> Html:
    """Render Security Gate findings."""

    columns = (
        TableColumn("check", "Check"),
        TableColumn("status", "Status"),
        TableColumn("blocking", "Blocking"),
        TableColumn("message", "Message"),
        TableColumn("remediation", "Remediation"),
    )

    rows = [
        {
            "check": humanize(finding.check),
            "status": safe_html(security_status_badge(finding.status)),
            "blocking": "yes" if finding.blocking else "no",
            "message": finding.message,
            "remediation": finding.remediation or "—",
        }
        for finding in findings
    ]

    if not rows:
        return empty_state(
            EmptyState(
                title="No Security Gate findings",
                message="Security Gate has not produced any findings for this instance.",
            )
        )

    return table(columns, rows)


def security_gate_panel(result: SecurityGateResult | None) -> Html:
    """Render Security Gate status and findings."""

    if result is None:
        return card(
            "Security Gate",
            p("Security Gate has not run yet.", class_="kx-muted"),
            tone=ComponentTone.MUTED,
        )

    metrics = metrics_grid(
        (
            Metric("Status", humanize(result.status), tone_for_security_status(result.status)),
            Metric("Findings", str(len(result.findings)), ComponentTone.DEFAULT),
            Metric("Blocking", str(len(result.blocking_failures)), ComponentTone.DANGER if result.blocking_failures else ComponentTone.SUCCESS),
            Metric("Checked", format_datetime(result.checked_at), ComponentTone.MUTED),
        )
    )
    return card(
        "Security Gate",
        metrics + security_finding_table(result.findings),
        tone=tone_for_security_status(result.status),
    )


def service_health_table(services: Sequence[ServiceHealth]) -> Html:
    """Render service health rows."""

    columns = (
        TableColumn("service", "Service"),
        TableColumn("status", "Status"),
        TableColumn("checked_at", "Checked"),
        TableColumn("detail", "Detail"),
    )

    rows = [
        {
            "service": safe_html(service_badge(service.service)),
            "status": safe_html(badge(humanize(service.status), tone=tone_for_service_health(service.status))),
            "checked_at": format_datetime(service.checked_at),
            "detail": service.detail or "—",
        }
        for service in services
    ]

    if not rows:
        return empty_state(
            EmptyState(
                title="No service health",
                message="Service health has not been checked yet.",
            )
        )

    return table(columns, rows)


def runtime_health_panel(health: RuntimeHealth | None) -> Html:
    """Render runtime health panel."""

    if health is None:
        return card(
            "Runtime Health",
            p("Runtime health is unavailable.", class_="kx-muted"),
            tone=ComponentTone.MUTED,
        )

    body = metrics_grid(
        (
            Metric("Instance", str(health.instance_id), ComponentTone.DEFAULT),
            Metric("State", humanize(health.state), tone_for_instance_state(health.state)),
            Metric("Services", str(len(health.services)), ComponentTone.INFO),
            Metric("Checked", format_datetime(health.checked_at), ComponentTone.MUTED),
        )
    )
    body += service_health_table(health.services)
    return card("Runtime Health", body, tone=tone_for_instance_state(health.state))


def backup_table(backups: Sequence[BackupRecord]) -> Html:
    """Render backups."""

    columns = (
        TableColumn("backup_id", "Backup"),
        TableColumn("status", "Status"),
        TableColumn("class", "Class"),
        TableColumn("capsule_version", "Capsule"),
        TableColumn("size", "Size"),
        TableColumn("created_at", "Created"),
        TableColumn("verified_at", "Verified"),
    )

    rows = [
        {
            "backup_id": backup.backup_id,
            "status": safe_html(backup_status_badge(backup.status)),
            "class": backup.backup_class,
            "capsule_version": backup.capsule_version,
            "size": format_bytes(backup.size_bytes),
            "created_at": format_datetime(backup.created_at),
            "verified_at": format_datetime(backup.verified_at),
        }
        for backup in backups
    ]

    if not rows:
        return empty_state(
            EmptyState(
                title="No backups",
                message="Create a manual backup before updates, restores, or rollback testing.",
            )
        )

    return table(columns, rows)


def logs_panel(
    lines: Sequence[str],
    *,
    title: str = "Logs",
    max_lines: int = 500,
) -> Html:
    """Render log output safely."""

    selected = list(lines)[-max_lines:]
    body = tag(
        "pre",
        escape("\n".join(selected)),
        class_="kx-logs",
    )
    return card(title, body, tone=ComponentTone.DEFAULT)


# ---------------------------------------------------------------------
# Canonical actions
# ---------------------------------------------------------------------

def instance_actions(instance: InstanceRecord) -> tuple[ComponentAction, ...]:
    """Return canonical actions for an instance state."""

    state = instance.state
    instance_id = str(instance.instance_id)

    actions: list[ComponentAction] = [
        ComponentAction("Status", "instance_status", method="GET", href=f"/instances/{instance_id}"),
        ComponentAction("Logs", "instance_logs", method="GET", href=f"/instances/{instance_id}/logs"),
        ComponentAction("Backup", "instance_backup", payload={"instance_id": instance_id}),
        ComponentAction("Health", "instance_health", method="GET", href=f"/instances/{instance_id}/health"),
    ]

    if state in (InstanceState.CREATED, InstanceState.READY, InstanceState.STOPPED, InstanceState.DEGRADED):
        actions.insert(0, ComponentAction("Start", "instance_start", payload={"instance_id": instance_id}))

    if state in (InstanceState.RUNNING, InstanceState.DEGRADED):
        actions.insert(
            0,
            ComponentAction(
                "Stop",
                "instance_stop",
                danger=True,
                confirm="Stop this Konnaxion instance?",
                payload={"instance_id": instance_id},
            ),
        )

    if state in (InstanceState.RUNNING, InstanceState.STOPPED, InstanceState.DEGRADED):
        actions.append(
            ComponentAction(
                "Rollback",
                "instance_rollback",
                danger=True,
                confirm="Rollback this Konnaxion instance?",
                payload={"instance_id": instance_id},
            )
        )

    if state == InstanceState.SECURITY_BLOCKED:
        actions.append(
            ComponentAction(
                "Security Check",
                "security_check",
                payload={"instance_id": instance_id},
            )
        )

    return tuple(actions)


def global_actions() -> tuple[ComponentAction, ...]:
    """Return canonical global Manager actions."""

    return (
        ComponentAction("Import Capsule", "capsule_import", href="/capsules/import"),
        ComponentAction("Create Instance", "instance_create", href="/instances/create"),
        ComponentAction("Security Check", "security_check", href="/security"),
        ComponentAction("Backups", "backup_list", href="/backups"),
        ComponentAction("Network Profiles", "network_profiles", href="/network"),
    )


# ---------------------------------------------------------------------
# Page-level composites
# ---------------------------------------------------------------------

def dashboard(
    *,
    instances: Sequence[InstanceRecord],
    capsules: Sequence[CapsuleArtifact] = (),
    latest_security: SecurityGateResult | None = None,
    latest_health: RuntimeHealth | None = None,
) -> Html:
    """Render a complete Manager dashboard fragment."""

    parts = [
        div(
            h(1, "Konnaxion Capsule Manager")
            + action_bar(global_actions()),
            class_="kx-dashboard-header",
        ),
        instance_table(instances),
        capsule_table(capsules),
        security_gate_panel(latest_security),
        runtime_health_panel(latest_health),
    ]
    return div("".join(parts), class_="kx-dashboard")


def instance_detail(
    *,
    instance: InstanceRecord,
    security: SecurityGateResult | None = None,
    health: RuntimeHealth | None = None,
    backups: Sequence[BackupRecord] = (),
    logs: Sequence[str] = (),
) -> Html:
    """Render a full instance detail fragment."""

    parts = [
        instance_card(instance, actions=instance_actions(instance)),
        security_gate_panel(security),
        runtime_health_panel(health),
        backup_table(backups),
    ]

    if logs:
        parts.append(logs_panel(logs))

    return div("".join(parts), class_="kx-instance-detail")


def stylesheet() -> Html:
    """Return minimal CSS for rendered components.

    A production UI can replace this with bundled assets.
    """

    css = """
.kx-dashboard,.kx-instance-detail{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.4;color:#111827}
.kx-dashboard-header{display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-bottom:1rem}
.kx-card{border:1px solid #d1d5db;border-radius:0.75rem;padding:1rem;margin:1rem 0;background:#fff}
.kx-card-title{margin:0 0 0.75rem 0;font-size:1.1rem}
.kx-card-body{display:block}
.kx-card-footer{margin-top:1rem}
.kx-card-success{border-color:#86efac}
.kx-card-warning{border-color:#facc15}
.kx-card-danger{border-color:#fca5a5}
.kx-card-info{border-color:#93c5fd}
.kx-card-muted{background:#f9fafb}
.kx-badge{display:inline-block;padding:0.15rem 0.5rem;border-radius:999px;font-size:0.85rem;border:1px solid #d1d5db;background:#f9fafb}
.kx-badge-success{background:#dcfce7;border-color:#86efac}
.kx-badge-warning{background:#fef9c3;border-color:#facc15}
.kx-badge-danger{background:#fee2e2;border-color:#fca5a5}
.kx-badge-info{background:#dbeafe;border-color:#93c5fd}
.kx-badge-muted{background:#f3f4f6;border-color:#d1d5db;color:#4b5563}
.kx-metrics-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(9rem,1fr));gap:0.75rem}
.kx-metric{border:1px solid #e5e7eb;border-radius:0.5rem;padding:0.75rem;background:#fff}
.kx-metric-label{font-size:0.8rem;color:#6b7280}
.kx-metric-value{font-size:1rem;font-weight:700}
.kx-metric-detail{margin:0.25rem 0 0 0;color:#6b7280}
.kx-table{width:100%;border-collapse:collapse;margin:1rem 0}
.kx-table th,.kx-table td{border-bottom:1px solid #e5e7eb;padding:0.5rem;vertical-align:top}
.kx-table th{font-weight:700;background:#f9fafb}
.kx-action-bar{display:flex;gap:0.5rem;flex-wrap:wrap}
.kx-button,.kx-action-link{display:inline-block;border:1px solid #d1d5db;border-radius:0.5rem;padding:0.4rem 0.75rem;background:#fff;text-decoration:none;color:#111827}
.kx-button-danger,.kx-action-danger{border-color:#fca5a5;background:#fee2e2}
.kx-button-disabled,.kx-action-disabled{opacity:.5;pointer-events:none}
.kx-empty-state{border:1px dashed #d1d5db;border-radius:0.75rem;padding:1rem;color:#4b5563;background:#f9fafb}
.kx-definition-list{display:grid;grid-template-columns:minmax(8rem,14rem) 1fr;gap:0.35rem 1rem}
.kx-definition-list dt{font-weight:700;color:#374151}
.kx-definition-list dd{margin:0}
.kx-logs{white-space:pre-wrap;overflow:auto;max-height:30rem;background:#111827;color:#f9fafb;padding:1rem;border-radius:0.5rem}
.kx-muted{color:#6b7280}
"""
    return tag("style", css.strip())


__all__ = [
    "ComponentAction",
    "ComponentSize",
    "ComponentTone",
    "EmptyState",
    "Html",
    "Metric",
    "SafeHtml",
    "TableColumn",
    "action_bar",
    "action_button",
    "as_mapping",
    "backup_status_badge",
    "backup_table",
    "badge",
    "button",
    "card",
    "capsule_table",
    "dashboard",
    "definition_list",
    "div",
    "empty_state",
    "endpoint_panel",
    "exposure_mode_badge",
    "format_bytes",
    "format_datetime",
    "global_actions",
    "h",
    "html_attrs",
    "humanize",
    "instance_actions",
    "instance_card",
    "instance_detail",
    "instance_state_badge",
    "instance_summary_metrics",
    "instance_table",
    "link",
    "logs_panel",
    "metric_tile",
    "metrics_grid",
    "network_profile_badge",
    "p",
    "runtime_health_panel",
    "safe_html",
    "security_finding_table",
    "security_gate_panel",
    "security_status_badge",
    "service_badge",
    "service_health_table",
    "span",
    "status_badge",
    "stylesheet",
    "table",
    "tag",
    "tone_for_backup_status",
    "tone_for_exposure",
    "tone_for_instance_state",
    "tone_for_profile",
    "tone_for_restore_status",
    "tone_for_rollback_status",
    "tone_for_security_status",
    "tone_for_service_health",
]
