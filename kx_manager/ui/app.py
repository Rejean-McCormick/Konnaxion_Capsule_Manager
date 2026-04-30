"""
Konnaxion Capsule Manager UI entrypoint.

This module provides a lightweight Streamlit-based UI for the Konnaxion Capsule
Manager. It renders canonical Manager models only; it does not directly control
Docker, firewall rules, host services, or backups. Privileged work must remain
behind the Konnaxion Agent API/client.

Run locally:

    streamlit run kx_manager/ui/app.py

The UI can be wired to a real Manager API/client later by replacing
load_manager_state() and action handler stubs.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Iterable, Mapping

from kx_shared.konnaxion_constants import (
    CANONICAL_DOCKER_SERVICES,
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_VERSION,
    DEFAULT_INSTANCE_ID,
    DEFAULT_NETWORK_PROFILE,
    DockerService,
    ExposureMode,
    InstanceState,
    NetworkProfile,
    SecurityGateStatus,
)

from kx_manager.models import (
    AgentConnectionStatus,
    AgentStatus,
    BackupSummary,
    CapsuleSummary,
    HealthView,
    InstanceSummary,
    ManagerState,
    ManagerView,
    NETWORK_PROFILE_OPTIONS,
    NetworkProfileChangeRequest,
    NetworkState,
    Notification,
    NotificationLevel,
    ProductInfo,
    SecurityGateView,
    ServiceView,
    create_canonical_service_views,
    create_default_manager_state,
    datetime_to_iso,
    normalize_network_profile,
)


# ---------------------------------------------------------------------------
# Optional Streamlit import
# ---------------------------------------------------------------------------

def _load_streamlit() -> Any:
    """
    Import Streamlit lazily so this file remains importable in non-UI test runs.
    """
    try:
        import streamlit as st  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Streamlit is required to run the Manager UI. "
            "Install it with: pip install streamlit"
        ) from exc
    return st


# ---------------------------------------------------------------------------
# UI constants
# ---------------------------------------------------------------------------

APP_TITLE = "Konnaxion Capsule Manager"
APP_ICON = "◈"
DEFAULT_REFRESH_SECONDS = 5

STATE_BADGE_LABELS: dict[InstanceState, str] = {
    InstanceState.CREATED: "Created",
    InstanceState.IMPORTING: "Importing",
    InstanceState.VERIFYING: "Verifying",
    InstanceState.READY: "Ready",
    InstanceState.STARTING: "Starting",
    InstanceState.RUNNING: "Running",
    InstanceState.STOPPING: "Stopping",
    InstanceState.STOPPED: "Stopped",
    InstanceState.UPDATING: "Updating",
    InstanceState.ROLLING_BACK: "Rolling back",
    InstanceState.DEGRADED: "Degraded",
    InstanceState.FAILED: "Failed",
    InstanceState.SECURITY_BLOCKED: "Security blocked",
}

SECURITY_BADGE_LABELS: dict[SecurityGateStatus, str] = {
    SecurityGateStatus.PASS: "PASS",
    SecurityGateStatus.WARN: "WARN",
    SecurityGateStatus.FAIL_BLOCKING: "FAIL_BLOCKING",
    SecurityGateStatus.SKIPPED: "SKIPPED",
    SecurityGateStatus.UNKNOWN: "UNKNOWN",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_manager_state() -> ManagerState:
    """
    Load Manager state.

    Replace this function with a Manager API/client call when the API layer is
    available. The current implementation provides a safe demo snapshot using
    canonical models and values.
    """
    now = datetime.now(UTC)

    security_gate = SecurityGateView(
        status=SecurityGateStatus.UNKNOWN,
        checks=tuple(),
        checked_at=None,
    )

    health = HealthView(
        healthy=False,
        ready=False,
        services=create_canonical_service_views(),
        message="Waiting for Agent status.",
        checked_at=now,
    )

    instance = InstanceSummary(
        instance_id=DEFAULT_INSTANCE_ID,
        state=InstanceState.CREATED,
        capsule_id=DEFAULT_CAPSULE_ID,
        capsule_version=DEFAULT_CAPSULE_VERSION,
        network=NetworkState(
            profile=DEFAULT_NETWORK_PROFILE,
            exposure_mode=ExposureMode.PRIVATE,
            public_mode_enabled=False,
            host="konnaxion.local",
            url="https://konnaxion.local",
        ),
        health=health,
        security_gate=security_gate,
        created_at=now,
        updated_at=now,
    )

    capsule = CapsuleSummary(
        capsule_id=DEFAULT_CAPSULE_ID,
        capsule_version=DEFAULT_CAPSULE_VERSION,
        channel="demo",
        imported=False,
        signature_verified=False,
        checksum_verified=False,
        created_at=now,
    )

    return ManagerState(
        product=ProductInfo(),
        agent=AgentStatus(
            connection=AgentConnectionStatus.UNKNOWN,
            local_only=True,
            last_seen_at=None,
            message="Agent client not configured.",
        ),
        capsules=(capsule,),
        instances=(instance,),
        backups=tuple(),
        notifications=(
            Notification(
                id="ui-demo-state",
                level=NotificationLevel.INFO,
                message="Manager UI is running with a local placeholder state.",
                created_at=now,
            ),
        ),
        active_view=ManagerView.DASHBOARD,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Action stubs
# ---------------------------------------------------------------------------

def start_instance(instance_id: str) -> None:
    """Request instance startup through the Agent client."""
    raise NotImplementedError("Wire this to kx_manager.client once the Agent client is implemented.")


def stop_instance(instance_id: str) -> None:
    """Request instance shutdown through the Agent client."""
    raise NotImplementedError("Wire this to kx_manager.client once the Agent client is implemented.")


def create_backup(instance_id: str) -> None:
    """Request a manual backup through the Agent client."""
    raise NotImplementedError("Wire this to kx_manager.client once the Agent client is implemented.")


def run_security_check(instance_id: str) -> None:
    """Request a Security Gate check through the Agent client."""
    raise NotImplementedError("Wire this to kx_manager.client once the Agent client is implemented.")


def set_network_profile(request: NetworkProfileChangeRequest) -> None:
    """Request a network profile change through the Agent client."""
    raise NotImplementedError("Wire this to kx_manager.client once the Agent client is implemented.")


def import_capsule() -> None:
    """Request capsule import through the Agent client."""
    raise NotImplementedError("Wire this to kx_manager.client once the Agent client is implemented.")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    return datetime_to_iso(value) or "—"


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "—"

    units = ("B", "KB", "MB", "GB", "TB")
    size = float(value)

    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{value} B"


def _state_label(state: InstanceState) -> str:
    return STATE_BADGE_LABELS.get(state, state.value)


def _security_label(status: SecurityGateStatus) -> str:
    return SECURITY_BADGE_LABELS.get(status, status.value)


def _notification_method(st: Any, level: NotificationLevel) -> Callable[[str], Any]:
    if level == NotificationLevel.ERROR:
        return st.error
    if level == NotificationLevel.WARNING:
        return st.warning
    if level == NotificationLevel.SUCCESS:
        return st.success
    return st.info


def _safe_action(st: Any, action: Callable[[], None]) -> None:
    try:
        action()
    except NotImplementedError as exc:
        st.warning(str(exc))
    except Exception as exc:  # pragma: no cover - defensive UI boundary
        st.error(f"Action failed: {exc}")


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def configure_page(st: Any) -> None:
    """Configure Streamlit page."""
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=APP_ICON,
        layout="wide",
        initial_sidebar_state="expanded",
    )


def render_sidebar(st: Any, state: ManagerState) -> ManagerView:
    """Render the sidebar and return selected view."""
    st.sidebar.title(APP_TITLE)

    st.sidebar.caption(f"{state.product.product_name} {state.product.app_version}")
    st.sidebar.caption(f"Parameters: {state.product.param_version}")

    st.sidebar.divider()

    view_labels = {
        ManagerView.DASHBOARD: "Dashboard",
        ManagerView.CAPSULES: "Capsules",
        ManagerView.INSTANCE_DETAIL: "Instances",
        ManagerView.NETWORK: "Network",
        ManagerView.SECURITY: "Security",
        ManagerView.BACKUPS: "Backups",
        ManagerView.LOGS: "Logs",
        ManagerView.SETTINGS: "Settings",
    }

    selected_label = st.sidebar.radio(
        "View",
        options=[view_labels[view] for view in ManagerView],
        index=list(ManagerView).index(state.active_view)
        if state.active_view in list(ManagerView)
        else 0,
    )

    selected_view = next(
        view for view, label in view_labels.items() if label == selected_label
    )

    st.sidebar.divider()
    render_agent_sidebar_status(st, state.agent)

    st.sidebar.divider()
    auto_refresh = st.sidebar.checkbox("Auto-refresh", value=False)
    if auto_refresh:
        refresh_seconds = st.sidebar.number_input(
            "Refresh seconds",
            min_value=2,
            max_value=300,
            value=DEFAULT_REFRESH_SECONDS,
            step=1,
        )
        st.sidebar.caption(f"Refresh requested every {refresh_seconds}s.")
        # Streamlit's built-in rerun timer is intentionally not used here to
        # avoid adding third-party components. Wire refresh in the runtime app
        # shell if needed.

    return selected_view


def render_agent_sidebar_status(st: Any, agent: AgentStatus) -> None:
    """Render Agent status in the sidebar."""
    st.sidebar.subheader("Agent")

    if agent.connection == AgentConnectionStatus.CONNECTED:
        st.sidebar.success("Connected")
    elif agent.connection == AgentConnectionStatus.UNAUTHORIZED:
        st.sidebar.error("Unauthorized")
    elif agent.connection == AgentConnectionStatus.DISCONNECTED:
        st.sidebar.warning("Disconnected")
    elif agent.connection == AgentConnectionStatus.ERROR:
        st.sidebar.error("Error")
    else:
        st.sidebar.info("Unknown")

    st.sidebar.caption(f"Local-only: {'yes' if agent.local_only else 'no'}")
    st.sidebar.caption(f"Last seen: {_format_dt(agent.last_seen_at)}")

    if agent.message:
        st.sidebar.caption(agent.message)


def render_notifications(st: Any, notifications: Iterable[Notification]) -> None:
    """Render Manager notifications."""
    for notification in notifications:
        method = _notification_method(st, notification.level)
        method(notification.message)


def render_header(st: Any, state: ManagerState) -> None:
    """Render page header."""
    st.title(APP_TITLE)
    st.caption(
        f"{state.product.product_name} {state.product.app_version} · "
        f"{state.product.param_version} · Updated {_format_dt(state.updated_at)}"
    )

    render_notifications(st, state.notifications)


def render_metric_row(st: Any, state: ManagerState) -> None:
    """Render top-level Manager metrics."""
    running = len(state.running_instances)
    blocked = len(state.security_blocked_instances)
    capsules = len(state.capsules)
    backups = len(state.backups)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Running instances", running)
    col2.metric("Security blocked", blocked)
    col3.metric("Capsules", capsules)
    col4.metric("Backups", backups)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def render_dashboard(st: Any, state: ManagerState) -> None:
    """Render dashboard view."""
    render_metric_row(st, state)

    st.subheader("Instances")
    if not state.instances:
        st.info("No Konnaxion Instance exists yet.")
        return

    for instance in state.instances:
        render_instance_card(st, instance)


def render_instance_card(st: Any, instance: InstanceSummary) -> None:
    """Render a compact instance card."""
    with st.container(border=True):
        top = st.columns([2, 1, 1, 1])
        top[0].markdown(f"### {instance.instance_id}")
        top[1].metric("State", _state_label(instance.state))
        top[2].metric("Network", instance.network.profile.value)
        top[3].metric("Security", _security_label(instance.security_gate.status))

        st.caption(
            f"Capsule: {instance.capsule_id} · "
            f"Version: {instance.capsule_version} · "
            f"URL: {instance.network.url or '—'}"
        )

        health_cols = st.columns(3)
        health_cols[0].metric("Healthy", "yes" if instance.health.healthy else "no")
        health_cols[1].metric("Ready", "yes" if instance.health.ready else "no")
        health_cols[2].metric("Public", "yes" if instance.network.is_public else "no")

        action_cols = st.columns(5)

        action_cols[0].button(
            "Start",
            key=f"start-{instance.instance_id}",
            disabled=not instance.can_start,
            on_click=lambda instance_id=instance.instance_id: _safe_action(
                st, lambda: start_instance(instance_id)
            ),
        )
        action_cols[1].button(
            "Stop",
            key=f"stop-{instance.instance_id}",
            disabled=not instance.can_stop,
            on_click=lambda instance_id=instance.instance_id: _safe_action(
                st, lambda: stop_instance(instance_id)
            ),
        )
        action_cols[2].button(
            "Backup",
            key=f"backup-{instance.instance_id}",
            disabled=not instance.can_backup,
            on_click=lambda instance_id=instance.instance_id: _safe_action(
                st, lambda: create_backup(instance_id)
            ),
        )
        action_cols[3].button(
            "Security check",
            key=f"security-{instance.instance_id}",
            on_click=lambda instance_id=instance.instance_id: _safe_action(
                st, lambda: run_security_check(instance_id)
            ),
        )
        action_cols[4].link_button(
            "Open",
            url=instance.network.url or "https://konnaxion.local",
            disabled=not bool(instance.network.url),
        )


# ---------------------------------------------------------------------------
# Capsules
# ---------------------------------------------------------------------------

def render_capsules(st: Any, state: ManagerState) -> None:
    """Render capsule management view."""
    st.subheader("Capsules")

    st.button(
        "Import capsule",
        key="import-capsule",
        on_click=lambda: _safe_action(st, import_capsule),
    )

    if not state.capsules:
        st.info("No capsules imported.")
        return

    rows = [
        {
            "Capsule ID": capsule.capsule_id,
            "Version": capsule.capsule_version,
            "Channel": capsule.channel,
            "Imported": capsule.imported,
            "Signature": capsule.signature_verified,
            "Checksum": capsule.checksum_verified,
            "Size": _format_bytes(capsule.size_bytes),
            "Path": capsule.local_path,
        }
        for capsule in state.capsules
    ]

    st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Instances
# ---------------------------------------------------------------------------

def render_instances(st: Any, state: ManagerState) -> None:
    """Render detailed instances view."""
    st.subheader("Instances")

    if not state.instances:
        st.info("No instances available.")
        return

    for instance in state.instances:
        with st.expander(f"{instance.instance_id} · {_state_label(instance.state)}", expanded=True):
            render_instance_detail(st, instance)


def render_instance_detail(st: Any, instance: InstanceSummary) -> None:
    """Render detailed information for one instance."""
    st.markdown("#### Runtime")
    runtime_cols = st.columns(4)
    runtime_cols[0].metric("State", _state_label(instance.state))
    runtime_cols[1].metric("Health", "healthy" if instance.health.healthy else "not healthy")
    runtime_cols[2].metric("Ready", "yes" if instance.health.ready else "no")
    runtime_cols[3].metric("Security", _security_label(instance.security_gate.status))

    st.markdown("#### Paths")
    st.code(
        "\n".join(
            [
                f"root={instance.root_path}",
                f"compose_file={instance.compose_file}",
                f"backup_root={instance.backup_root}",
            ]
        ),
        language="text",
    )

    st.markdown("#### Services")
    render_services_table(st, instance.health.services)


def render_services_table(st: Any, services: Sequence[ServiceView]) -> None:
    """Render service status table."""
    if not services:
        st.info("No service data available.")
        return

    rows = [
        {
            "Service": service.service.value,
            "Desired": service.desired,
            "Running": service.running,
            "Healthy": service.healthy,
            "Status": service.status_label,
            "Ports": ", ".join(str(port) for port in service.ports) or "—",
            "Image": service.image or "—",
            "Message": service.message or "—",
        }
        for service in services
    ]

    st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

def render_network(st: Any, state: ManagerState) -> None:
    """Render network profile view."""
    st.subheader("Network")

    if not state.instances:
        st.info("No instances available.")
        return

    instance_ids = [instance.instance_id for instance in state.instances]
    selected_instance_id = st.selectbox("Instance", instance_ids)
    instance = state.find_instance(selected_instance_id)

    if instance is None:
        st.error("Selected instance was not found.")
        return

    st.markdown("#### Current network")
    cols = st.columns(4)
    cols[0].metric("Profile", instance.network.profile.value)
    cols[1].metric("Exposure", instance.network.exposure_mode.value)
    cols[2].metric("Public", "yes" if instance.network.is_public else "no")
    cols[3].metric("URL", instance.network.url or "—")

    st.markdown("#### Change profile")
    profile_values = [option.value.value for option in NETWORK_PROFILE_OPTIONS]
    selected_profile = st.selectbox(
        "Network profile",
        profile_values,
        index=profile_values.index(instance.network.profile.value)
        if instance.network.profile.value in profile_values
        else profile_values.index(DEFAULT_NETWORK_PROFILE.value),
    )

    exposure_values = [mode.value for mode in ExposureMode]
    selected_exposure = st.selectbox(
        "Exposure mode",
        exposure_values,
        index=exposure_values.index(instance.network.exposure_mode.value)
        if instance.network.exposure_mode.value in exposure_values
        else exposure_values.index(ExposureMode.PRIVATE.value),
    )

    expires_at = None
    if selected_profile == NetworkProfile.PUBLIC_TEMPORARY.value:
        expires_at = st.datetime_input(
            "Public mode expires at",
            value=datetime.now(UTC) + timedelta(hours=4),
        )

    if st.button("Apply network profile"):
        def action() -> None:
            request = NetworkProfileChangeRequest(
                instance_id=instance.instance_id,
                network_profile=NetworkProfile(selected_profile),
                exposure_mode=ExposureMode(selected_exposure),
                public_mode_expires_at=expires_at,
            )
            set_network_profile(request)

        _safe_action(st, action)

    st.markdown("#### Available profiles")
    profile_rows = [option.to_dict() for option in NETWORK_PROFILE_OPTIONS]
    st.dataframe(profile_rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

def render_security(st: Any, state: ManagerState) -> None:
    """Render Security Gate view."""
    st.subheader("Security Gate")

    if not state.instances:
        st.info("No instances available.")
        return

    for instance in state.instances:
        with st.container(border=True):
            st.markdown(f"### {instance.instance_id}")
            cols = st.columns(3)
            cols[0].metric("Gate status", _security_label(instance.security_gate.status))
            cols[1].metric("Passed", "yes" if instance.security_gate.passed else "no")
            cols[2].metric("Blocking failures", len(instance.security_gate.blocking_failures))

            st.button(
                "Run Security Gate",
                key=f"run-security-{instance.instance_id}",
                on_click=lambda instance_id=instance.instance_id: _safe_action(
                    st, lambda: run_security_check(instance_id)
                ),
            )

            if not instance.security_gate.checks:
                st.info("No Security Gate results yet.")
                continue

            rows = [
                {
                    "Check": check.check.value,
                    "Status": check.status.value,
                    "Blocking": check.blocking,
                    "Blocks startup": check.blocks_startup,
                    "Message": check.message or "—",
                    "Checked at": _format_dt(check.checked_at),
                }
                for check in instance.security_gate.checks
            ]

            st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------

def render_backups(st: Any, state: ManagerState) -> None:
    """Render backup view."""
    st.subheader("Backups")

    if state.instances:
        instance_ids = [instance.instance_id for instance in state.instances]
        selected_instance_id = st.selectbox("Instance", instance_ids, key="backup-instance-select")
        selected_instance = state.find_instance(selected_instance_id)

        st.button(
            "Create manual backup",
            key="create-manual-backup",
            disabled=not selected_instance.can_backup if selected_instance else True,
            on_click=lambda instance_id=selected_instance_id: _safe_action(
                st, lambda: create_backup(instance_id)
            ),
        )

    if not state.backups:
        st.info("No backups available.")
        return

    rows = [
        {
            "Backup ID": backup.backup_id,
            "Instance": backup.instance_id,
            "Class": backup.backup_class,
            "Status": backup.status.value,
            "Usable": backup.usable_for_restore,
            "Size": _format_bytes(backup.size_bytes),
            "Created": _format_dt(backup.created_at),
            "Verified": _format_dt(backup.verified_at),
            "Path": backup.display_path,
            "Error": backup.error or "—",
        }
        for backup in state.backups
    ]

    st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

def render_logs(st: Any, state: ManagerState) -> None:
    """Render logs placeholder view."""
    st.subheader("Logs")

    if not state.instances:
        st.info("No instances available.")
        return

    instance_id = st.selectbox("Instance", [instance.instance_id for instance in state.instances])
    service_options = ["all", *CANONICAL_DOCKER_SERVICES]
    service = st.selectbox("Service", service_options)

    st.info(
        "Log streaming is not wired yet. "
        f"Selected instance={instance_id}, service={service}."
    )

    st.code(
        "\n".join(
            [
                "Expected Agent operation:",
                "kx instance logs <INSTANCE_ID>",
                "",
                f"INSTANCE_ID={instance_id}",
                f"SERVICE={service}",
            ]
        ),
        language="text",
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def render_settings(st: Any, state: ManagerState) -> None:
    """Render settings and canonical values."""
    st.subheader("Settings")

    st.markdown("#### Product")
    st.json(state.product.to_dict())

    st.markdown("#### Canonical Docker services")
    st.code("\n".join(CANONICAL_DOCKER_SERVICES), language="text")

    st.markdown("#### Canonical network profiles")
    st.code("\n".join(option.value.value for option in NETWORK_PROFILE_OPTIONS), language="text")

    st.markdown("#### Agent")
    st.json(state.agent.to_dict())


# ---------------------------------------------------------------------------
# App entrypoint
# ---------------------------------------------------------------------------

def render_app(state: ManagerState | None = None) -> None:
    """Render the Konnaxion Capsule Manager UI."""
    st = _load_streamlit()
    configure_page(st)

    current_state = state or load_manager_state()

    selected_view = render_sidebar(st, current_state)
    render_header(st, current_state)

    if selected_view == ManagerView.DASHBOARD:
        render_dashboard(st, current_state)
    elif selected_view == ManagerView.CAPSULES:
        render_capsules(st, current_state)
    elif selected_view == ManagerView.INSTANCE_DETAIL:
        render_instances(st, current_state)
    elif selected_view == ManagerView.NETWORK:
        render_network(st, current_state)
    elif selected_view == ManagerView.SECURITY:
        render_security(st, current_state)
    elif selected_view == ManagerView.BACKUPS:
        render_backups(st, current_state)
    elif selected_view == ManagerView.LOGS:
        render_logs(st, current_state)
    elif selected_view == ManagerView.SETTINGS:
        render_settings(st, current_state)
    else:
        st.error(f"Unknown Manager view: {selected_view}")


def main() -> None:
    """Console entrypoint."""
    render_app()


if __name__ == "__main__":
    main()


__all__ = [
    "APP_ICON",
    "APP_TITLE",
    "DEFAULT_REFRESH_SECONDS",
    "SECURITY_BADGE_LABELS",
    "STATE_BADGE_LABELS",
    "configure_page",
    "create_backup",
    "import_capsule",
    "load_manager_state",
    "main",
    "render_agent_sidebar_status",
    "render_app",
    "render_backups",
    "render_capsules",
    "render_dashboard",
    "render_header",
    "render_instance_card",
    "render_instance_detail",
    "render_instances",
    "render_logs",
    "render_metric_row",
    "render_network",
    "render_notifications",
    "render_security",
    "render_services_table",
    "render_settings",
    "render_sidebar",
    "run_security_check",
    "set_network_profile",
    "start_instance",
    "stop_instance",
]
