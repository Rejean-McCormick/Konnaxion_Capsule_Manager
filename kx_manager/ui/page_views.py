# kx_manager/ui/page_views.py

"""Page-level HTML views for the Konnaxion Capsule Manager GUI.

This module renders the local browser pages under `/ui`.

It is presentation-only:
- no Docker calls
- no shell execution
- no firewall/network mutation
- no backup/runtime mutation
- no direct Agent side effects

POST forms submit to canonical `/ui/actions/...` routes. Those routes delegate
to `kx_manager.ui.actions.dispatch_gui_action`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from fastapi.responses import HTMLResponse

from kx_manager.ui.form_constants import (
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_OUTPUT_DIR,
    DEFAULT_CAPSULE_VERSION,
    DEFAULT_CHANNEL,
    DEFAULT_INSTANCE_ID,
    DEFAULT_RUNTIME_ROOT,
    DEFAULT_SOURCE_DIR,
    DockerService,
    ExposureMode,
    NetworkProfile,
)
from kx_manager.ui.render import (
    FormField,
    SelectOption,
    attr,
    css_class,
    h,
    html_response,
    render_card,
    render_definition_list,
    render_empty_state,
    render_form,
    render_grid,
    render_hidden,
    render_json_block,
    render_link,
    render_metric,
    render_result_panel,
    render_section,
    render_table,
    safe_href,
)

try:
    from kx_manager.services.targets import TargetMode
except Exception:  # pragma: no cover - staged build compatibility
    TargetMode = None  # type: ignore[assignment]


try:
    from kx_manager.ui.static import (
        ACTION_LABELS,
        ACTION_ROUTES,
        APP_TITLE,
        NAV_ITEMS,
        PAGE_TITLES,
        UI_BASE_PATH,
        UI_PAGE_ROUTES,
        route_for_action,
        title_for_route,
    )
except Exception:  # pragma: no cover - staged build compatibility
    APP_TITLE = "Konnaxion Capsule Manager"
    UI_BASE_PATH = "/ui"

    UI_PAGE_ROUTES = (
        "/ui",
        "/ui/capsules",
        "/ui/instances",
        "/ui/security",
        "/ui/network",
        "/ui/backups",
        "/ui/restore",
        "/ui/logs",
        "/ui/health",
        "/ui/settings",
        "/ui/targets",
        "/ui/about",
    )

    PAGE_TITLES = {
        "/ui": "Dashboard",
        "/ui/capsules": "Capsules",
        "/ui/instances": "Instances",
        "/ui/security": "Security",
        "/ui/network": "Network",
        "/ui/backups": "Backups",
        "/ui/restore": "Restore",
        "/ui/logs": "Logs",
        "/ui/health": "Health",
        "/ui/settings": "Settings",
        "/ui/targets": "Targets",
        "/ui/about": "About",
    }

    NAV_ITEMS = (
        ("Dashboard", "/ui"),
        ("Capsules", "/ui/capsules"),
        ("Instances", "/ui/instances"),
        ("Targets", "/ui/targets"),
        ("Security", "/ui/security"),
        ("Network", "/ui/network"),
        ("Backups", "/ui/backups"),
        ("Restore", "/ui/restore"),
        ("Logs", "/ui/logs"),
        ("Health", "/ui/health"),
        ("Settings", "/ui/settings"),
        ("About", "/ui/about"),
    )

    ACTION_LABELS = {
        "check_manager": "Check Manager",
        "check_agent": "Check Agent",
        "select_source_folder": "Select Source Folder",
        "select_capsule_output_folder": "Select Output Folder",
        "build_capsule": "Build Capsule",
        "rebuild_capsule": "Rebuild Capsule",
        "verify_capsule": "Verify Capsule",
        "import_capsule": "Import Capsule",
        "list_capsules": "List Capsules",
        "view_capsule": "View Capsule",
        "create_instance": "Create Instance",
        "update_instance": "Update Instance",
        "start_instance": "Start Instance",
        "stop_instance": "Stop Instance",
        "restart_instance": "Restart Instance",
        "instance_status": "Instance Status",
        "view_logs": "View Logs",
        "view_health": "Instance Health",
        "open_instance": "Open Instance",
        "rollback_instance": "Rollback",
        "create_backup": "Create Backup",
        "list_backups": "List Backups",
        "verify_backup": "Verify Backup",
        "restore_backup": "Restore Backup",
        "restore_backup_new": "Restore Backup New",
        "test_restore_backup": "Test Restore Backup",
        "run_security_check": "Run Security Check",
        "set_network_profile": "Set Network Profile",
        "disable_public_mode": "Disable Public Mode",
        "set_target_local": "Set Local Target",
        "set_target_intranet": "Set Intranet Target",
        "set_target_droplet": "Set Droplet Target",
        "set_target_temporary_public": "Set Temporary Public Target",
        "deploy_local": "Deploy Local",
        "deploy_intranet": "Deploy Intranet",
        "deploy_droplet": "Deploy Droplet",
        "check_droplet_agent": "Check Droplet Agent",
        "copy_capsule_to_droplet": "Copy Capsule to Droplet",
        "start_droplet_instance": "Start Droplet Instance",
        "open_manager_docs": "Open Manager Docs",
        "open_agent_docs": "Open Agent Docs",
    }

    ACTION_ROUTES = {
        action: f"/ui/actions/{action.replace('_', '-')}"
        for action in ACTION_LABELS
    }

    def route_for_action(action: Any) -> str:
        action_value = str(getattr(action, "value", action)).strip()
        return ACTION_ROUTES.get(action_value, f"/ui/actions/{action_value.replace('_', '-')}")

    def title_for_route(route: str) -> str:
        return PAGE_TITLES.get(route, "Dashboard")


DEFAULT_CAPSULE_FILE = (
    f"{DEFAULT_CAPSULE_OUTPUT_DIR}\\{DEFAULT_CAPSULE_ID}.kxcap"
    if "\\" in DEFAULT_CAPSULE_OUTPUT_DIR
    else f"{DEFAULT_CAPSULE_OUTPUT_DIR}/{DEFAULT_CAPSULE_ID}.kxcap"
)

DEFAULT_PUBLIC_EXPIRATION = "2026-04-30T22:00:00Z"
DEFAULT_PRIVATE_HOST = "konnaxion.local"
DEFAULT_DROPLET_NAME = "konnaxion-droplet"
DEFAULT_DROPLET_USER = "root"
DEFAULT_REMOTE_KX_ROOT = "/opt/konnaxion"
DEFAULT_REMOTE_CAPSULE_DIR = "/opt/konnaxion/capsules"


PageBuilder = Callable[[Mapping[str, Any]], str]


@dataclass(frozen=True, slots=True)
class PageView:
    route: str
    title: str
    subtitle: str
    builder: PageBuilder


def render_page_response(
    route: str,
    *,
    context: Mapping[str, Any] | None = None,
    result: Any | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render a `/ui` route as a FastAPI HTMLResponse."""

    normalized_route = normalize_ui_route(route)
    page = get_page_view(normalized_route)
    data = dict(context or {})

    return html_response(
        page.title,
        page.builder(data),
        subtitle=page.subtitle,
        active_href=normalized_route,
        nav_items=_nav_items(normalized_route),
        result=result,
        status_code=status_code,
    )


def render_page_html(
    route: str,
    *,
    context: Mapping[str, Any] | None = None,
    result: Any | None = None,
) -> str:
    """Render a `/ui` route and return raw HTML text."""

    response = render_page_response(route, context=context, result=result)
    return response.body.decode(response.charset or "utf-8")


def render_ui_page(
    route: str,
    *,
    context: Mapping[str, Any] | None = None,
    result: Any | None = None,
) -> HTMLResponse:
    """Compatibility alias for route handlers."""

    return render_page_response(route, context=context, result=result)


def normalize_ui_route(route: str | None) -> str:
    value = (route or UI_BASE_PATH).strip() or UI_BASE_PATH

    if value == "/":
        return UI_BASE_PATH

    if value.endswith("/") and value != UI_BASE_PATH:
        value = value.rstrip("/")

    if value not in UI_PAGE_ROUTES:
        return UI_BASE_PATH

    return value


def get_page_view(route: str) -> PageView:
    return PAGE_VIEWS.get(normalize_ui_route(route), PAGE_VIEWS[UI_BASE_PATH])


def _nav_items(active_href: str) -> list[dict[str, Any]]:
    return [
        {
            "label": label,
            "href": href,
            "active": href == active_href,
        }
        for label, href in NAV_ITEMS
    ]


def _label(value: Any) -> str:
    text = str(getattr(value, "value", value))
    return text.replace("_", " ").replace("-", " ").title()


def _enum_options(enum_type: Any) -> list[tuple[str, str]]:
    try:
        return [(str(item.value), _label(item.value)) for item in enum_type]
    except TypeError:
        return []


def _target_mode_options() -> list[tuple[str, str]]:
    if TargetMode is None:
        return [
            ("local", "Local"),
            ("intranet", "Intranet"),
            ("temporary_public", "Temporary Public"),
            ("droplet", "Droplet"),
        ]

    return [(str(item.value), _label(item.value)) for item in TargetMode]


def _service_options() -> list[tuple[str, str]]:
    return [("", "All services")] + _enum_options(DockerService)


def _field(
    name: str,
    label: str,
    value: Any = "",
    *,
    field_type: str = "text",
    required: bool = False,
    placeholder: str = "",
    help_text: str = "",
    options: Sequence[SelectOption | tuple[str, str] | str] | None = None,
) -> FormField:
    return FormField(
        name=name,
        label=label,
        value=value,
        field_type=field_type,
        required=required,
        placeholder=placeholder,
        help_text=help_text,
        options=options,
    )


def _instance_id_field() -> FormField:
    return _field(
        "instance_id",
        "Instance ID",
        DEFAULT_INSTANCE_ID,
        required=True,
        help_text="Letters, numbers, dots, underscores, and hyphens only.",
    )


def _capsule_id_field() -> FormField:
    return _field(
        "capsule_id",
        "Capsule ID",
        DEFAULT_CAPSULE_ID,
        required=True,
    )


def _capsule_version_field() -> FormField:
    return _field(
        "capsule_version",
        "Capsule Version",
        DEFAULT_CAPSULE_VERSION,
        required=True,
    )


def _capsule_file_field(*, required: bool = True, must_exist_hint: bool = True) -> FormField:
    return _field(
        "capsule_file",
        "Capsule File",
        DEFAULT_CAPSULE_FILE,
        required=required,
        help_text=(
            "Path to a .kxcap file."
            if not must_exist_hint
            else "Path to an existing .kxcap file."
        ),
    )


def _source_dir_field() -> FormField:
    return _field(
        "source_dir",
        "Konnaxion Source Folder",
        DEFAULT_SOURCE_DIR,
        required=True,
    )


def _capsule_output_dir_field() -> FormField:
    return _field(
        "capsule_output_dir",
        "Capsule Output Folder",
        DEFAULT_CAPSULE_OUTPUT_DIR,
        required=True,
    )


def _network_profile_field(value: str = "intranet_private") -> FormField:
    return _field(
        "network_profile",
        "Network Profile",
        value,
        field_type="select",
        required=True,
        options=_enum_options(NetworkProfile),
    )


def _exposure_mode_field(value: str = "private") -> FormField:
    return _field(
        "exposure_mode",
        "Exposure Mode",
        value,
        field_type="select",
        required=True,
        options=_enum_options(ExposureMode),
    )


def _confirmed_field(label: str = "I confirm this action") -> FormField:
    return _field(
        "confirmed",
        label,
        True,
        field_type="checkbox",
        help_text="Required for destructive or public-exposure actions.",
    )


def _action_label(action: str) -> str:
    return ACTION_LABELS.get(action, _label(action))


def _action_path(action: str) -> str:
    return route_for_action(action)


def _action_form(
    action: str,
    fields: Sequence[FormField | Mapping[str, Any]] | str = "",
    *,
    submit_label: str | None = None,
    hidden: Mapping[str, Any] | None = None,
    extra_actions: str = "",
    classes: str = "",
) -> str:
    form_hidden = {
        "action": action,
        **dict(hidden or {}),
    }

    return render_form(
        _action_path(action),
        fields,
        method="post",
        submit_label=submit_label or _action_label(action),
        hidden=form_hidden,
        extra_actions=extra_actions,
        classes=classes,
    )


def _button_form(
    action: str,
    label: str | None = None,
    *,
    payload: Mapping[str, Any] | None = None,
    variant: str = "secondary",
    disabled: bool = False,
) -> str:
    disabled_attr = " disabled" if disabled else ""
    button_class = css_class(
        "kx-button",
        "secondary" if variant == "secondary" else None,
        "danger" if variant == "danger" else None,
    )

    hidden = {
        "action": action,
        **dict(payload or {}),
    }
    hidden_html = "".join(render_hidden(key, value) for key, value in hidden.items())

    return (
        f'<form method="post" action="{safe_href(_action_path(action))}" style="display:inline">'
        f"{hidden_html}"
        f'<button class="{button_class}" type="submit"{disabled_attr}>{h(label or _action_label(action))}</button>'
        "</form>"
    )


def _action_bar(actions: Sequence[str]) -> str:
    return f'<div class="kx-actions">{"".join(actions)}</div>'


def _safety_note() -> str:
    return render_card(
        "Safety Boundary",
        (
            "<p>GUI pages only collect form input and submit canonical Manager actions. "
            "Privileged runtime work stays behind Manager services and the Konnaxion Agent.</p>"
        ),
    )


def _default_payload(context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "instance_id": context.get("instance_id", DEFAULT_INSTANCE_ID),
        "capsule_id": context.get("capsule_id", DEFAULT_CAPSULE_ID),
        "capsule_version": context.get("capsule_version", DEFAULT_CAPSULE_VERSION),
        "capsule_file": context.get("capsule_file", DEFAULT_CAPSULE_FILE),
        "source_dir": context.get("source_dir", DEFAULT_SOURCE_DIR),
        "capsule_output_dir": context.get("capsule_output_dir", DEFAULT_CAPSULE_OUTPUT_DIR),
        "target_mode": context.get("target_mode", "intranet"),
        "network_profile": context.get("network_profile", "intranet_private"),
        "exposure_mode": context.get("exposure_mode", "private"),
        "host": context.get("host", DEFAULT_PRIVATE_HOST),
    }


def dashboard_view(context: Mapping[str, Any]) -> str:
    payload = _default_payload(context)

    metrics = render_grid(
        [
            render_metric("Target", _label(payload["target_mode"]), hint="Selected deployment target"),
            render_metric("Profile", _label(payload["network_profile"]), hint="Canonical network profile"),
            render_metric("Exposure", _label(payload["exposure_mode"]), hint="Current exposure mode"),
            render_metric("Instance", payload["instance_id"], hint="Default working instance"),
        ]
    )

    quick_checks = render_card(
        "Checks",
        "<p>Confirm Manager and Agent reachability before capsule or runtime actions.</p>",
        footer=_action_bar(
            [
                _button_form("check_manager", "Check Manager"),
                _button_form("check_agent", "Check Agent"),
                _button_form("open_manager_docs", "Manager Docs"),
                _button_form("open_agent_docs", "Agent Docs"),
            ]
        ),
    )

    lifecycle = render_card(
        "Lifecycle Shortcuts",
        "<p>Build, verify, import, create, check, and start the default instance workflow.</p>",
        footer=_action_bar(
            [
                _button_form("build_capsule", payload=payload),
                _button_form("verify_capsule", payload=payload),
                _button_form("import_capsule", payload=payload),
                _button_form("create_instance", payload=payload),
                _button_form("run_security_check", payload=payload),
                _button_form("start_instance", payload=payload),
            ]
        ),
    )

    return metrics + render_grid([quick_checks, lifecycle, _safety_note()])


def capsules_view(context: Mapping[str, Any]) -> str:
    build_form = _action_form(
        "build_capsule",
        [
            _source_dir_field(),
            _capsule_output_dir_field(),
            _capsule_id_field(),
            _capsule_version_field(),
            _field("channel", "Channel", DEFAULT_CHANNEL, required=True),
            _field("force", "Overwrite existing capsule if needed", True, field_type="checkbox"),
            _field("delete_existing", "Delete existing capsule first", False, field_type="checkbox"),
            _field("verify_after_build", "Verify after build", False, field_type="checkbox"),
        ],
    )

    verify_form = _action_form(
        "verify_capsule",
        [_capsule_file_field(required=True)],
    )

    import_form = _action_form(
        "import_capsule",
        [
            _capsule_file_field(required=True),
            _instance_id_field(),
            _network_profile_field("intranet_private"),
        ],
    )

    lookup_form = _action_form(
        "view_capsule",
        [
            _capsule_id_field(),
            _capsule_file_field(required=False, must_exist_hint=False),
        ],
    )

    list_card = render_card(
        "Capsule Registry",
        "<p>List imported or known capsules from the Manager registry.</p>",
        footer=_action_bar([_button_form("list_capsules", "List Capsules")]),
    )

    return render_grid(
        [
            render_card("Build Capsule", build_form),
            render_card("Verify Capsule", verify_form),
            render_card("Import Capsule", import_form),
            render_card("View Capsule", lookup_form),
            list_card,
        ]
    )


def instances_view(context: Mapping[str, Any]) -> str:
    payload = _default_payload(context)

    create_form = _action_form(
        "create_instance",
        [
            _instance_id_field(),
            _capsule_id_field(),
            _network_profile_field("intranet_private"),
            _exposure_mode_field("private"),
            _field("host", "Host", DEFAULT_PRIVATE_HOST, required=False),
            _field("domain", "Domain", "", required=False),
            _field("generate_secrets", "Generate instance secrets", True, field_type="checkbox"),
        ],
    )

    update_form = _action_form(
        "update_instance",
        [
            _instance_id_field(),
            _capsule_file_field(required=True),
            _field("create_pre_update_backup", "Create pre-update backup", True, field_type="checkbox"),
        ],
    )

    runtime_form = _action_form(
        "instance_status",
        [
            _instance_id_field(),
            _field("run_security_gate", "Run Security Gate before action", True, field_type="checkbox"),
            _field("timeout_seconds", "Timeout Seconds", 60, field_type="number"),
        ],
        submit_label="Load Status",
        extra_actions=_action_bar(
            [
                _button_form("start_instance", payload=payload),
                _button_form("stop_instance", payload={**payload, "confirmed": "true"}, variant="danger"),
                _button_form("restart_instance", payload=payload),
                _button_form("view_health", payload=payload),
                _button_form("view_logs", payload=payload),
                _button_form("open_instance", payload=payload),
            ]
        ),
    )

    rollback_form = _action_form(
        "rollback_instance",
        [
            _instance_id_field(),
            _field("restore_data", "Restore data from backup", False, field_type="checkbox"),
            _field("backup_id", "Backup ID", "", required=False),
            _confirmed_field("I confirm rollback"),
        ],
        submit_label="Rollback Instance",
    )

    return render_grid(
        [
            render_card("Create Instance", create_form),
            render_card("Update Instance", update_form),
            render_card("Runtime Actions", runtime_form),
            render_card("Rollback", rollback_form, classes="kx-result warn"),
        ]
    )


def targets_view(context: Mapping[str, Any]) -> str:
    local_form = _action_form(
        "set_target_local",
        [
            _instance_id_field(),
            _field("runtime_root", "Runtime Root", DEFAULT_RUNTIME_ROOT, required=True),
            _field("capsule_dir", "Capsule Directory", f"{DEFAULT_RUNTIME_ROOT}\\capsules", required=True),
        ],
    )

    intranet_form = _action_form(
        "set_target_intranet",
        [
            _instance_id_field(),
            _field("runtime_root", "Runtime Root", DEFAULT_RUNTIME_ROOT, required=True),
            _field("capsule_dir", "Capsule Directory", f"{DEFAULT_RUNTIME_ROOT}\\capsules", required=True),
            _field("host", "Private Host", DEFAULT_PRIVATE_HOST, required=False),
            _field(
                "exposure_mode",
                "Exposure Mode",
                "private",
                field_type="select",
                required=True,
                options=[("private", "Private"), ("lan", "LAN")],
            ),
        ],
    )

    temporary_public_form = _action_form(
        "set_target_temporary_public",
        [
            _instance_id_field(),
            _field("runtime_root", "Runtime Root", DEFAULT_RUNTIME_ROOT, required=True),
            _field("capsule_dir", "Capsule Directory", f"{DEFAULT_RUNTIME_ROOT}\\capsules", required=True),
            _field("public_host", "Public Host", "", required=False),
            _field(
                "public_mode_expires_at",
                "Public Mode Expires At",
                DEFAULT_PUBLIC_EXPIRATION,
                required=True,
                help_text="ISO-8601 datetime.",
            ),
            _confirmed_field("I confirm temporary public exposure"),
        ],
    )

    droplet_form = _action_form(
        "set_target_droplet",
        [
            _instance_id_field(),
            _field("droplet_name", "Droplet Name", DEFAULT_DROPLET_NAME, required=True),
            _field("droplet_host", "Droplet Host / IP", "", required=True),
            _field("droplet_user", "SSH User", DEFAULT_DROPLET_USER, required=True),
            _field("ssh_key_path", "SSH Key Path", "", required=True),
            _field("ssh_port", "SSH Port", 22, field_type="number", required=True),
            _field("remote_kx_root", "Remote KX Root", DEFAULT_REMOTE_KX_ROOT, required=True),
            _field("remote_capsule_dir", "Remote Capsule Directory", DEFAULT_REMOTE_CAPSULE_DIR, required=True),
            _field("domain", "Domain", "", required=False),
            _field("remote_agent_url", "Remote Agent URL", "", required=False),
            _confirmed_field("I confirm public VPS target configuration"),
        ],
    )

    deploy_card = render_card(
        "Deployment Actions",
        "<p>Use target-specific deploy actions after selecting and validating a target.</p>",
        footer=_action_bar(
            [
                _button_form("deploy_local", payload=_default_payload(context)),
                _button_form("deploy_intranet", payload=_default_payload(context)),
                _button_form("deploy_droplet", payload={**_default_payload(context), "confirmed": "true"}, variant="danger"),
                _button_form("check_droplet_agent", payload={**_default_payload(context), "confirmed": "true"}),
                _button_form("copy_capsule_to_droplet", payload={**_default_payload(context), "confirmed": "true"}),
                _button_form("start_droplet_instance", payload={**_default_payload(context), "confirmed": "true"}),
            ]
        ),
    )

    return render_grid(
        [
            render_card("Local Target", local_form),
            render_card("Intranet Target", intranet_form),
            render_card("Temporary Public Target", temporary_public_form, classes="kx-result warn"),
            render_card("Droplet Target", droplet_form, classes="kx-result warn"),
            deploy_card,
        ]
    )


def security_view(context: Mapping[str, Any]) -> str:
    form = _action_form(
        "run_security_check",
        [
            _instance_id_field(),
            _field("run_security_gate", "Blocking Security Gate", True, field_type="checkbox"),
        ],
        submit_label="Run Security Gate",
    )

    return render_grid(
        [
            render_card("Security Gate", form),
            render_card(
                "Policy",
                (
                    "<p>Security Gate should run before starts, updates, public exposure, "
                    "restores, and deployment flows.</p>"
                ),
            ),
        ]
    )


def network_view(context: Mapping[str, Any]) -> str:
    set_form = _action_form(
        "set_network_profile",
        [
            _instance_id_field(),
            _network_profile_field("intranet_private"),
            _exposure_mode_field("private"),
            _field("host", "Host", DEFAULT_PRIVATE_HOST, required=False),
            _field("domain", "Domain", "", required=False),
            _field(
                "public_mode_expires_at",
                "Public Mode Expires At",
                "",
                required=False,
                help_text="Required for temporary public mode.",
            ),
            _field("confirmed", "I confirm public exposure if selected", False, field_type="checkbox"),
        ],
    )

    disable_form = _action_form(
        "disable_public_mode",
        [
            _instance_id_field(),
            _confirmed_field("I confirm disabling public mode"),
        ],
        submit_label="Disable Public Mode",
    )

    return render_grid(
        [
            render_card("Set Network Profile", set_form),
            render_card("Disable Public Mode", disable_form, classes="kx-result warn"),
        ]
    )


def backups_view(context: Mapping[str, Any]) -> str:
    create_form = _action_form(
        "create_backup",
        [
            _instance_id_field(),
            _field("backup_class", "Backup Class", "manual", required=True),
            _field("verify_after_create", "Verify after create", True, field_type="checkbox"),
        ],
    )

    list_form = _action_form(
        "list_backups",
        [
            _field("instance_id", "Instance ID", DEFAULT_INSTANCE_ID, required=False),
        ],
    )

    verify_form = _action_form(
        "verify_backup",
        [
            _field("backup_id", "Backup ID", "", required=True),
            _field("instance_id", "Instance ID", DEFAULT_INSTANCE_ID, required=False),
        ],
    )

    return render_grid(
        [
            render_card("Create Backup", create_form),
            render_card("List Backups", list_form),
            render_card("Verify Backup", verify_form),
        ]
    )


def restore_view(context: Mapping[str, Any]) -> str:
    restore_form = _action_form(
        "restore_backup",
        [
            _instance_id_field(),
            _field("backup_id", "Backup ID", "", required=True),
            _field("restore_data", "Restore data", True, field_type="checkbox"),
            _field("test_only", "Test only", False, field_type="checkbox"),
            _confirmed_field("I confirm restore"),
        ],
    )

    restore_new_form = _action_form(
        "restore_backup_new",
        [
            _instance_id_field(),
            _field("backup_id", "Backup ID", "", required=True),
            _field("target_instance_id", "New Instance ID", "demo-restore-001", required=True),
            _field("restore_data", "Restore data", True, field_type="checkbox"),
            _confirmed_field("I confirm restore into a new instance"),
        ],
    )

    test_restore_form = _action_form(
        "test_restore_backup",
        [
            _instance_id_field(),
            _field("backup_id", "Backup ID", "", required=True),
            _field("test_only", "Test only", True, field_type="checkbox"),
        ],
        submit_label="Test Restore",
    )

    return render_grid(
        [
            render_card("Restore Backup", restore_form, classes="kx-result warn"),
            render_card("Restore Into New Instance", restore_new_form, classes="kx-result warn"),
            render_card("Test Restore Backup", test_restore_form),
        ]
    )


def logs_view(context: Mapping[str, Any]) -> str:
    form = _action_form(
        "view_logs",
        [
            _instance_id_field(),
            _field(
                "service",
                "Service",
                "",
                field_type="select",
                required=False,
                options=_service_options(),
            ),
            _field("lines", "Lines", 200, field_type="number"),
            _field("tail", "Tail logs", True, field_type="checkbox"),
        ],
        submit_label="View Logs",
    )

    return render_grid(
        [
            render_card("Logs", form),
            render_card(
                "Log Scope",
                "<p>Select a service or leave blank to request all available instance logs.</p>",
            ),
        ]
    )


def health_view(context: Mapping[str, Any]) -> str:
    payload = _default_payload(context)

    body = _action_form(
        "view_health",
        [_instance_id_field()],
        submit_label="View Health",
        extra_actions=_action_bar(
            [
                _button_form("instance_status", payload=payload),
                _button_form("check_agent", payload=payload),
                _button_form("check_manager", payload=payload),
            ]
        ),
    )

    return render_grid(
        [
            render_card("Health", body),
            render_card(
                "Health Checks",
                "<p>Use this page to inspect Manager, Agent, instance, and runtime health signals.</p>",
            ),
        ]
    )


def settings_view(context: Mapping[str, Any]) -> str:
    source_form = _action_form(
        "select_source_folder",
        [_source_dir_field()],
    )

    output_form = _action_form(
        "select_capsule_output_folder",
        [_capsule_output_dir_field()],
    )

    defaults = render_definition_list(
        {
            "Default instance": DEFAULT_INSTANCE_ID,
            "Default capsule": DEFAULT_CAPSULE_ID,
            "Default capsule version": DEFAULT_CAPSULE_VERSION,
            "Default channel": DEFAULT_CHANNEL,
            "Default runtime root": DEFAULT_RUNTIME_ROOT,
            "Default source folder": DEFAULT_SOURCE_DIR,
            "Default capsule output folder": DEFAULT_CAPSULE_OUTPUT_DIR,
        }
    )

    return render_grid(
        [
            render_card("Source Folder", source_form),
            render_card("Capsule Output Folder", output_form),
            render_card("Current Defaults", defaults),
        ]
    )


def about_view(context: Mapping[str, Any]) -> str:
    body = render_definition_list(
        {
            "Product": "Konnaxion",
            "Manager": APP_TITLE,
            "Capsule extension": ".kxcap",
            "Default instance": DEFAULT_INSTANCE_ID,
            "Default target": "intranet",
            "UI base path": UI_BASE_PATH,
        }
    )

    docs = _action_bar(
        [
            render_link("FastAPI Docs", "/docs", button=True),
            render_link("OpenAPI", "/openapi.json", button=True),
            _button_form("open_manager_docs", "Manager Docs"),
            _button_form("open_agent_docs", "Agent Docs"),
        ]
    )

    return render_grid(
        [
            render_card("About", body, footer=docs),
            _safety_note(),
        ]
    )


def not_found_view(context: Mapping[str, Any]) -> str:
    return render_empty_state(
        "Unknown UI page.",
        detail="Use the top navigation to choose a known Manager GUI page.",
    )


PAGE_VIEWS: dict[str, PageView] = {
    "/ui": PageView(
        route="/ui",
        title=title_for_route("/ui"),
        subtitle="Local capsule, instance, security, network, backup, and deployment control.",
        builder=dashboard_view,
    ),
    "/ui/capsules": PageView(
        route="/ui/capsules",
        title=title_for_route("/ui/capsules"),
        subtitle="Build, verify, import, list, and inspect Konnaxion Capsules.",
        builder=capsules_view,
    ),
    "/ui/instances": PageView(
        route="/ui/instances",
        title=title_for_route("/ui/instances"),
        subtitle="Create, update, start, stop, inspect, and rollback instances.",
        builder=instances_view,
    ),
    "/ui/security": PageView(
        route="/ui/security",
        title=title_for_route("/ui/security"),
        subtitle="Run Security Gate checks before risky lifecycle operations.",
        builder=security_view,
    ),
    "/ui/network": PageView(
        route="/ui/network",
        title=title_for_route("/ui/network"),
        subtitle="Set private-by-default network profiles and disable public exposure.",
        builder=network_view,
    ),
    "/ui/backups": PageView(
        route="/ui/backups",
        title=title_for_route("/ui/backups"),
        subtitle="Create, list, and verify backups.",
        builder=backups_view,
    ),
    "/ui/restore": PageView(
        route="/ui/restore",
        title=title_for_route("/ui/restore"),
        subtitle="Restore backups safely, including test restore and restore-new flows.",
        builder=restore_view,
    ),
    "/ui/logs": PageView(
        route="/ui/logs",
        title=title_for_route("/ui/logs"),
        subtitle="View instance runtime logs.",
        builder=logs_view,
    ),
    "/ui/health": PageView(
        route="/ui/health",
        title=title_for_route("/ui/health"),
        subtitle="Inspect Manager, Agent, instance, and runtime health.",
        builder=health_view,
    ),
    "/ui/settings": PageView(
        route="/ui/settings",
        title=title_for_route("/ui/settings"),
        subtitle="Set local source and capsule output folders.",
        builder=settings_view,
    ),
    "/ui/targets": PageView(
        route="/ui/targets",
        title=title_for_route("/ui/targets"),
        subtitle="Choose where this capsule should run: local, intranet, temporary public, or Droplet.",
        builder=targets_view,
    ),
    "/ui/about": PageView(
        route="/ui/about",
        title=title_for_route("/ui/about"),
        subtitle="Konnaxion Capsule Manager information and safety boundary.",
        builder=about_view,
    ),
}


__all__ = [
    "PAGE_VIEWS",
    "PageView",
    "about_view",
    "backups_view",
    "capsules_view",
    "dashboard_view",
    "get_page_view",
    "health_view",
    "instances_view",
    "logs_view",
    "network_view",
    "normalize_ui_route",
    "not_found_view",
    "render_page_html",
    "render_page_response",
    "render_ui_page",
    "restore_view",
    "security_view",
    "settings_view",
    "targets_view",
]