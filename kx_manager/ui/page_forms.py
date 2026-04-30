# kx_manager/ui/page_forms.py

"""HTML form fragments for Konnaxion Capsule Manager GUI pages.

This module is presentation-only.

It renders canonical GUI forms that submit to allowlisted FastAPI action routes.
It must not dispatch actions, call Docker, execute shell commands, mutate host
state, contact the Agent, or perform backup/runtime operations.

POST handling belongs to ``kx_manager.ui.app`` and
``kx_manager.ui.actions.dispatch_gui_action``.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from kx_manager.services.targets import TargetMode
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
    render_action_bar,
    render_card,
    render_form,
    render_grid,
    render_link,
    render_section,
)

try:
    from kx_manager.ui.static import ACTION_LABELS, ACTION_ROUTES, route_for_action
except Exception:  # pragma: no cover - staged generation compatibility
    from kx_manager.ui.actions import ACTION_LABELS, ACTION_ROUTES

    def route_for_action(action: Any) -> str:
        action_value = str(getattr(action, "value", action)).strip()
        return ACTION_ROUTES.get(
            action_value,
            f"/ui/actions/{action_value.replace('_', '-')}",
        )


BACKUP_CLASS_OPTIONS: tuple[str, ...] = (
    "manual",
    "scheduled_daily",
    "scheduled_weekly",
    "scheduled_monthly",
    "pre_update",
    "pre_restore",
)

TARGET_MODE_OPTIONS: tuple[str, ...] = (
    TargetMode.LOCAL.value,
    TargetMode.INTRANET.value,
    TargetMode.TEMPORARY_PUBLIC.value,
    TargetMode.DROPLET.value,
)


def render_page_forms(route: str, data: Mapping[str, Any] | None = None) -> str:
    """Render page-local forms for a ``/ui`` route."""

    state = _state(data)

    if route == "/ui":
        return render_dashboard_forms(state)

    if route == "/ui/capsules":
        return render_capsule_forms(state)

    if route == "/ui/instances":
        return render_instance_forms(state)

    if route == "/ui/security":
        return render_security_forms(state)

    if route == "/ui/network":
        return render_network_forms(state)

    if route == "/ui/backups":
        return render_backup_forms(state)

    if route == "/ui/restore":
        return render_restore_forms(state)

    if route == "/ui/logs":
        return render_logs_forms(state)

    if route == "/ui/health":
        return render_health_forms(state)

    if route == "/ui/settings":
        return render_settings_forms(state)

    if route == "/ui/targets":
        return render_target_forms(state)

    if route == "/ui/about":
        return render_about_forms(state)

    return ""


def render_dashboard_forms(data: Mapping[str, Any] | None = None) -> str:
    """Render dashboard quick-action forms."""

    state = _state(data)

    cards = [
        _simple_action_card(
            "Manager",
            "Check local Manager and Agent connectivity.",
            (
                "check_manager",
                "check_agent",
                "open_manager_docs",
                "open_agent_docs",
            ),
        ),
        render_card(
            "Build and import",
            _select_source_folder_form(state)
            + _select_capsule_output_folder_form(state)
            + _build_capsule_form(state, compact=True)
            + _verify_capsule_form(state, compact=True)
            + _import_capsule_form(state, compact=True),
        ),
        render_card(
            "Instance lifecycle",
            _create_instance_form(state, compact=True)
            + _instance_action_form("start_instance", state, compact=True)
            + _instance_action_form("instance_status", state, compact=True)
            + _instance_action_form("view_health", state, compact=True),
        ),
        render_card(
            "Safety",
            _instance_action_form("run_security_check", state, compact=True)
            + _backup_form(state, compact=True)
            + _logs_form(state, compact=True),
        ),
    ]

    return render_section(
        "Dashboard actions",
        render_grid(cards),
        intro="Common local Manager workflows.",
    )


def render_capsule_forms(data: Mapping[str, Any] | None = None) -> str:
    """Render capsule build, verify, import, and lookup forms."""

    state = _state(data)

    cards = [
        render_card("Build capsule", _build_capsule_form(state)),
        render_card("Rebuild capsule", _rebuild_capsule_form(state)),
        render_card("Verify capsule", _verify_capsule_form(state)),
        render_card("Import capsule", _import_capsule_form(state)),
        render_card("View capsule", _capsule_lookup_form(state)),
        _simple_action_card("Capsule inventory", "List imported capsules.", ("list_capsules",)),
    ]

    return render_section(
        "Capsules",
        render_grid(cards),
        intro="Build, verify, import, and inspect signed .kxcap capsules.",
    )


def render_instance_forms(data: Mapping[str, Any] | None = None) -> str:
    """Render instance lifecycle forms."""

    state = _state(data)

    cards = [
        render_card("Create instance", _create_instance_form(state)),
        render_card("Update instance", _update_instance_form(state)),
        render_card(
            "Lifecycle",
            _instance_action_form("start_instance", state)
            + _confirmed_instance_action_form("stop_instance", state)
            + _instance_action_form("restart_instance", state)
            + _instance_action_form("instance_status", state),
        ),
        render_card(
            "Runtime views",
            _instance_action_form("view_health", state)
            + _logs_form(state, compact=True)
            + _open_instance_form(state),
        ),
        render_card("Rollback", _rollback_form(state)),
    ]

    return render_section(
        "Instances",
        render_grid(cards),
        intro="Create, update, start, stop, inspect, and rollback instances.",
    )


def render_security_forms(data: Mapping[str, Any] | None = None) -> str:
    """Render Security Gate forms."""

    state = _state(data)

    return render_section(
        "Security",
        render_grid(
            [
                render_card(
                    "Run Security Gate",
                    _instance_action_form("run_security_check", state),
                ),
                render_card(
                    "Health check",
                    _instance_action_form("view_health", state),
                ),
            ]
        ),
        intro="Run allowlisted Security Gate and runtime-health checks.",
    )


def render_network_forms(data: Mapping[str, Any] | None = None) -> str:
    """Render network-profile forms."""

    state = _state(data)

    cards = [
        render_card("Set network profile", _network_profile_form(state)),
        render_card("Disable public mode", _disable_public_mode_form(state)),
    ]

    return render_section(
        "Network",
        render_grid(cards),
        intro="Configure canonical private, LAN, tunnel, or public exposure settings.",
    )


def render_backup_forms(data: Mapping[str, Any] | None = None) -> str:
    """Render backup list/create/verify forms."""

    state = _state(data)

    cards = [
        render_card("Create backup", _backup_form(state)),
        render_card("List backups", _list_backups_form(state)),
        render_card("Verify backup", _backup_lookup_form("verify_backup", state)),
    ]

    return render_section(
        "Backups",
        render_grid(cards),
        intro="Create, list, and verify instance backups.",
    )


def render_restore_forms(data: Mapping[str, Any] | None = None) -> str:
    """Render restore, restore-new, test-restore, and rollback forms."""

    state = _state(data)

    cards = [
        render_card("Restore backup", _restore_form("restore_backup", state)),
        render_card("Restore into new instance", _restore_form("restore_backup_new", state)),
        render_card("Test restore", _restore_form("test_restore_backup", state, test_only=True)),
        render_card("Rollback instance", _rollback_form(state)),
    ]

    return render_section(
        "Restore",
        render_grid(cards),
        intro="Restore backup data, test restore integrity, or rollback an instance.",
    )


def render_logs_forms(data: Mapping[str, Any] | None = None) -> str:
    """Render log-view forms."""

    state = _state(data)

    return render_section(
        "Logs",
        render_grid([render_card("View logs", _logs_form(state))]),
        intro="Read runtime logs through approved Manager/Agent boundaries.",
    )


def render_health_forms(data: Mapping[str, Any] | None = None) -> str:
    """Render health/status forms."""

    state = _state(data)

    cards = [
        render_card("Instance status", _instance_action_form("instance_status", state)),
        render_card("Instance health", _instance_action_form("view_health", state)),
        render_card("Manager / Agent", _check_forms()),
    ]

    return render_section(
        "Health",
        render_grid(cards),
        intro="Check Manager, Agent, instance, and runtime health.",
    )


def render_settings_forms(data: Mapping[str, Any] | None = None) -> str:
    """Render local path/settings forms."""

    state = _state(data)

    cards = [
        render_card("Source folder", _select_source_folder_form(state)),
        render_card("Capsule output folder", _select_capsule_output_folder_form(state)),
        render_card("Default build settings", _build_defaults_form(state)),
    ]

    return render_section(
        "Settings",
        render_grid(cards),
        intro="Set local folders and default capsule metadata for GUI submissions.",
    )


def render_target_forms(data: Mapping[str, Any] | None = None) -> str:
    """Render target-mode and deployment forms."""

    state = _state(data)

    cards = [
        render_card("Target mode selector", _target_mode_selector_form(state)),
        render_card("Local target", _local_target_form(state)),
        render_card("Intranet target", _intranet_target_form(state)),
        render_card("Temporary public target", _temporary_public_target_form(state)),
        render_card("Droplet target", _droplet_target_form(state)),
        render_card("Deploy local", _deploy_local_form(state)),
        render_card("Deploy intranet", _deploy_intranet_form(state)),
        render_card("Deploy droplet", _deploy_droplet_form(state)),
        render_card("Droplet operations", _droplet_operation_forms(state)),
    ]

    return render_section(
        "Targets",
        render_grid(cards),
        intro="Configure where the capsule should run and submit deployment actions.",
    )


def render_about_forms(data: Mapping[str, Any] | None = None) -> str:
    """Render documentation/action links."""

    return render_section(
        "About",
        render_grid(
            [
                _simple_action_card(
                    "API documentation",
                    "Open local Manager or Agent API docs.",
                    ("open_manager_docs", "open_agent_docs"),
                ),
                _simple_action_card(
                    "Connectivity",
                    "Check Manager and Agent availability.",
                    ("check_manager", "check_agent"),
                ),
            ]
        ),
    )


def form_for_action(action: str, data: Mapping[str, Any] | None = None) -> str:
    """Render the canonical form for one GUI action."""

    state = _state(data)

    mapping = {
        "check_manager": lambda: _single_button_form("check_manager"),
        "check_agent": lambda: _single_button_form("check_agent"),
        "select_source_folder": lambda: _select_source_folder_form(state),
        "select_capsule_output_folder": lambda: _select_capsule_output_folder_form(state),
        "build_capsule": lambda: _build_capsule_form(state),
        "rebuild_capsule": lambda: _rebuild_capsule_form(state),
        "verify_capsule": lambda: _verify_capsule_form(state),
        "import_capsule": lambda: _import_capsule_form(state),
        "list_capsules": lambda: _single_button_form("list_capsules"),
        "view_capsule": lambda: _capsule_lookup_form(state),
        "create_instance": lambda: _create_instance_form(state),
        "update_instance": lambda: _update_instance_form(state),
        "start_instance": lambda: _instance_action_form("start_instance", state),
        "stop_instance": lambda: _confirmed_instance_action_form("stop_instance", state),
        "restart_instance": lambda: _instance_action_form("restart_instance", state),
        "instance_status": lambda: _instance_action_form("instance_status", state),
        "view_logs": lambda: _logs_form(state),
        "view_health": lambda: _instance_action_form("view_health", state),
        "open_instance": lambda: _open_instance_form(state),
        "rollback_instance": lambda: _rollback_form(state),
        "create_backup": lambda: _backup_form(state),
        "list_backups": lambda: _list_backups_form(state),
        "verify_backup": lambda: _backup_lookup_form("verify_backup", state),
        "restore_backup": lambda: _restore_form("restore_backup", state),
        "restore_backup_new": lambda: _restore_form("restore_backup_new", state),
        "test_restore_backup": lambda: _restore_form("test_restore_backup", state, test_only=True),
        "run_security_check": lambda: _instance_action_form("run_security_check", state),
        "set_network_profile": lambda: _network_profile_form(state),
        "disable_public_mode": lambda: _disable_public_mode_form(state),
        "set_target_local": lambda: _local_target_form(state),
        "set_target_intranet": lambda: _intranet_target_form(state),
        "set_target_droplet": lambda: _droplet_target_form(state),
        "set_target_temporary_public": lambda: _temporary_public_target_form(state),
        "deploy_local": lambda: _deploy_local_form(state),
        "deploy_intranet": lambda: _deploy_intranet_form(state),
        "deploy_droplet": lambda: _deploy_droplet_form(state),
        "check_droplet_agent": lambda: _droplet_operation_form("check_droplet_agent", state),
        "copy_capsule_to_droplet": lambda: _droplet_operation_form("copy_capsule_to_droplet", state),
        "start_droplet_instance": lambda: _droplet_operation_form("start_droplet_instance", state),
        "open_manager_docs": lambda: _single_button_form("open_manager_docs"),
        "open_agent_docs": lambda: _single_button_form("open_agent_docs"),
    }

    builder = mapping.get(str(action))
    if builder is None:
        return ""

    return builder()


# ---------------------------------------------------------------------------
# Core form builders
# ---------------------------------------------------------------------------


def _select_source_folder_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "select_source_folder",
        [
            _field(
                "source_dir",
                "Konnaxion source folder",
                _value(data, "source_dir", default=DEFAULT_SOURCE_DIR),
                required=True,
                help_text="Folder containing the Konnaxion source tree.",
            ),
        ],
    )


def _select_capsule_output_folder_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "select_capsule_output_folder",
        [
            _field(
                "capsule_output_dir",
                "Capsule output folder",
                _value(
                    data,
                    "capsule_output_dir",
                    "output_dir",
                    default=DEFAULT_CAPSULE_OUTPUT_DIR,
                ),
                required=True,
                help_text="Folder where built .kxcap files are written.",
            ),
        ],
    )


def _build_capsule_form(
    data: Mapping[str, Any],
    *,
    compact: bool = False,
    action: str = "build_capsule",
) -> str:
    fields: list[FormField] = [
        _field("source_dir", "Source folder", _value(data, "source_dir", default=DEFAULT_SOURCE_DIR), required=True),
        _field(
            "capsule_output_dir",
            "Output folder",
            _value(data, "capsule_output_dir", "output_dir", default=DEFAULT_CAPSULE_OUTPUT_DIR),
            required=True,
        ),
        _field("capsule_id", "Capsule ID", _value(data, "capsule_id", default=DEFAULT_CAPSULE_ID), required=True),
        _field(
            "capsule_version",
            "Capsule version",
            _value(data, "capsule_version", "version", default=DEFAULT_CAPSULE_VERSION),
            required=True,
        ),
    ]

    if not compact:
        fields.extend(
            [
                _field(
                    "capsule_file",
                    "Capsule file",
                    _value(data, "capsule_file", "capsule_path"),
                    placeholder=f"{DEFAULT_CAPSULE_ID}.kxcap",
                    help_text="Optional explicit output path. Must end with .kxcap.",
                ),
                _field("channel", "Channel", _value(data, "channel", default=DEFAULT_CHANNEL), required=True),
            ]
        )

    fields.extend(
        [
            _checkbox("force", "Force overwrite", _bool_value(data, "force", default=True)),
            _checkbox("delete_existing", "Delete existing before build", _bool_value(data, "delete_existing")),
            _checkbox(
                "verify_after_build",
                "Verify after build",
                _bool_value(data, "verify_after_build"),
            ),
        ]
    )

    return _action_form(action, fields)


def _rebuild_capsule_form(data: Mapping[str, Any]) -> str:
    return _build_capsule_form(data, action="rebuild_capsule")


def _verify_capsule_form(data: Mapping[str, Any], *, compact: bool = False) -> str:
    fields = [
        _field(
            "capsule_file",
            "Capsule file",
            _value(data, "capsule_file", "capsule_path"),
            required=True,
            placeholder=r"C:\mycode\Konnaxion\runtime\capsules\demo.kxcap",
        )
    ]

    return _action_form("verify_capsule", fields)


def _import_capsule_form(data: Mapping[str, Any], *, compact: bool = False) -> str:
    fields = [
        _field(
            "capsule_file",
            "Capsule file",
            _value(data, "capsule_file", "capsule_path"),
            required=True,
        ),
        _field("instance_id", "Instance ID", _value(data, "instance_id", default=DEFAULT_INSTANCE_ID), required=True),
    ]

    if not compact:
        fields.append(
            _select(
                "network_profile",
                "Network profile",
                _enum_options(NetworkProfile, _value(data, "network_profile", default="intranet_private")),
                required=True,
            )
        )
    else:
        fields.append(
            _field(
                "network_profile",
                "Network profile",
                _value(data, "network_profile", default="intranet_private"),
                required=True,
            )
        )

    return _action_form("import_capsule", fields)


def _capsule_lookup_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "view_capsule",
        [
            _field("capsule_id", "Capsule ID", _value(data, "capsule_id", default=DEFAULT_CAPSULE_ID), required=True),
            _field("capsule_file", "Capsule file", _value(data, "capsule_file", "capsule_path")),
        ],
    )


def _create_instance_form(data: Mapping[str, Any], *, compact: bool = False) -> str:
    fields: list[FormField] = [
        _field("instance_id", "Instance ID", _value(data, "instance_id", default=DEFAULT_INSTANCE_ID), required=True),
        _field("capsule_id", "Capsule ID", _value(data, "capsule_id", default=DEFAULT_CAPSULE_ID), required=True),
        _select(
            "network_profile",
            "Network profile",
            _enum_options(NetworkProfile, _value(data, "network_profile", default="intranet_private")),
            required=True,
        ),
        _select(
            "exposure_mode",
            "Exposure mode",
            _enum_options(ExposureMode, _value(data, "exposure_mode", default="private")),
            required=True,
        ),
    ]

    if not compact:
        fields.extend(
            [
                _field("host", "Host", _value(data, "host", "target_host", "private_host", "public_host")),
                _field("domain", "Domain", _value(data, "domain")),
                _field(
                    "public_mode_expires_at",
                    "Public mode expires at",
                    _value(data, "public_mode_expires_at", "expires_at"),
                    placeholder="2026-04-30T22:00:00Z",
                ),
            ]
        )

    fields.extend(
        [
            _checkbox(
                "generate_secrets",
                "Generate secrets",
                _bool_value(data, "generate_secrets", default=True),
            ),
            _checkbox("confirmed", "Confirm public exposure if applicable", _bool_value(data, "confirmed")),
        ]
    )

    return _action_form("create_instance", fields)


def _update_instance_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "update_instance",
        [
            _field("instance_id", "Instance ID", _value(data, "instance_id", default=DEFAULT_INSTANCE_ID), required=True),
            _field("capsule_file", "Capsule file", _value(data, "capsule_file", "capsule_path"), required=True),
            _checkbox(
                "create_pre_update_backup",
                "Create pre-update backup",
                _bool_value(data, "create_pre_update_backup", default=True),
            ),
        ],
    )


def _instance_action_form(
    action: str,
    data: Mapping[str, Any],
    *,
    compact: bool = False,
) -> str:
    fields: list[FormField] = [
        _field("instance_id", "Instance ID", _value(data, "instance_id", default=DEFAULT_INSTANCE_ID), required=True)
    ]

    if action in {"start_instance", "restart_instance", "run_security_check"} and not compact:
        fields.append(
            _checkbox(
                "run_security_gate",
                "Run Security Gate",
                _bool_value(data, "run_security_gate", default=True),
            )
        )

    if action in {"stop_instance", "restart_instance"} and not compact:
        fields.append(
            _field(
                "timeout_seconds",
                "Timeout seconds",
                _value(data, "timeout_seconds", default="60"),
                field_type="number",
            )
        )

    return _action_form(action, fields)


def _confirmed_instance_action_form(action: str, data: Mapping[str, Any]) -> str:
    return _action_form(
        action,
        [
            _field("instance_id", "Instance ID", _value(data, "instance_id", default=DEFAULT_INSTANCE_ID), required=True),
            _field(
                "timeout_seconds",
                "Timeout seconds",
                _value(data, "timeout_seconds", default="60"),
                field_type="number",
            ),
            _checkbox("confirmed", "Confirm this action", _bool_value(data, "confirmed")),
        ],
    )


def _open_instance_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "open_instance",
        [
            _field("instance_id", "Instance ID", _value(data, "instance_id", default=DEFAULT_INSTANCE_ID), required=True),
            _field(
                "url",
                "URL",
                _value(data, "url", "private_url", "public_url", "runtime_url"),
                placeholder="https://konnaxion.local",
            ),
        ],
    )


def _logs_form(data: Mapping[str, Any], *, compact: bool = False) -> str:
    fields: list[FormField] = [
        _field("instance_id", "Instance ID", _value(data, "instance_id", default=DEFAULT_INSTANCE_ID), required=True),
    ]

    if not compact:
        fields.extend(
            [
                _select(
                    "service",
                    "Service",
                    [SelectOption("", "All services")]
                    + _enum_options(DockerService, _value(data, "service")),
                ),
                _field(
                    "lines",
                    "Lines",
                    _value(data, "lines", "tail_lines", default="200"),
                    field_type="number",
                ),
                _checkbox("tail", "Tail latest lines", _bool_value(data, "tail", default=True)),
            ]
        )

    return _action_form("view_logs", fields)


def _backup_form(data: Mapping[str, Any], *, compact: bool = False) -> str:
    fields: list[FormField] = [
        _field("instance_id", "Instance ID", _value(data, "instance_id", default=DEFAULT_INSTANCE_ID), required=True),
        _select(
            "backup_class",
            "Backup class",
            _string_options(BACKUP_CLASS_OPTIONS, _value(data, "backup_class", default="manual")),
            required=True,
        ),
        _checkbox(
            "verify_after_create",
            "Verify after create",
            _bool_value(data, "verify_after_create", default=True),
        ),
    ]

    return _action_form("create_backup", fields)


def _list_backups_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "list_backups",
        [
            _field(
                "instance_id",
                "Instance ID",
                _value(data, "instance_id"),
                help_text="Optional. Leave blank to list all known backups.",
            )
        ],
    )


def _backup_lookup_form(action: str, data: Mapping[str, Any]) -> str:
    return _action_form(
        action,
        [
            _field("backup_id", "Backup ID", _value(data, "backup_id"), required=True),
            _field("instance_id", "Instance ID", _value(data, "instance_id")),
        ],
    )


def _restore_form(
    action: str,
    data: Mapping[str, Any],
    *,
    test_only: bool = False,
) -> str:
    fields: list[FormField] = [
        _field("instance_id", "Instance ID", _value(data, "instance_id", default=DEFAULT_INSTANCE_ID), required=True),
        _field("backup_id", "Backup ID", _value(data, "backup_id"), required=True),
    ]

    if action == "restore_backup_new":
        fields.append(
            _field(
                "target_instance_id",
                "Target / new instance ID",
                _value(data, "target_instance_id", "new_instance_id"),
                required=True,
            )
        )

    fields.extend(
        [
            _checkbox("restore_data", "Restore data", _bool_value(data, "restore_data", default=True)),
            _checkbox("test_only", "Test only", test_only or _bool_value(data, "test_only")),
            _checkbox("confirmed", "Confirm restore action", test_only or _bool_value(data, "confirmed")),
        ]
    )

    return _action_form(action, fields)


def _rollback_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "rollback_instance",
        [
            _field("instance_id", "Instance ID", _value(data, "instance_id", default=DEFAULT_INSTANCE_ID), required=True),
            _checkbox("restore_data", "Restore backup data during rollback", _bool_value(data, "restore_data")),
            _field(
                "backup_id",
                "Backup ID",
                _value(data, "backup_id"),
                help_text="Required when restore_data is enabled.",
            ),
            _checkbox("confirmed", "Confirm rollback", _bool_value(data, "confirmed")),
        ],
    )


def _network_profile_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "set_network_profile",
        [
            _field("instance_id", "Instance ID", _value(data, "instance_id", default=DEFAULT_INSTANCE_ID), required=True),
            _select(
                "network_profile",
                "Network profile",
                _enum_options(NetworkProfile, _value(data, "network_profile", default="intranet_private")),
                required=True,
            ),
            _select(
                "exposure_mode",
                "Exposure mode",
                _enum_options(ExposureMode, _value(data, "exposure_mode", default="private")),
                required=True,
            ),
            _field("host", "Host", _value(data, "host", "target_host", "public_host", "private_host")),
            _field("domain", "Domain", _value(data, "domain")),
            _field(
                "public_mode_expires_at",
                "Public mode expires at",
                _value(data, "public_mode_expires_at", "expires_at"),
                placeholder="2026-04-30T22:00:00Z",
            ),
            _checkbox("confirmed", "Confirm public exposure", _bool_value(data, "confirmed")),
        ],
    )


def _disable_public_mode_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "disable_public_mode",
        [
            _field("instance_id", "Instance ID", _value(data, "instance_id", default=DEFAULT_INSTANCE_ID), required=True),
            _checkbox("confirmed", "Confirm disabling public mode", _bool_value(data, "confirmed")),
        ],
    )


def _target_mode_selector_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "set_target_intranet",
        [
            _select(
                "target_mode",
                "Target mode",
                _string_options(TARGET_MODE_OPTIONS, _value(data, "target_mode", default=TargetMode.INTRANET.value)),
                required=True,
            ),
            _field("instance_id", "Instance ID", _value(data, "instance_id", default=DEFAULT_INSTANCE_ID), required=True),
        ],
        submit_label="Prepare selected target",
    )


def _local_target_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "set_target_local",
        _base_target_fields(data, target_mode=TargetMode.LOCAL.value)
        + [
            _hidden("network_profile", "local_only"),
            _hidden("exposure_mode", "private"),
        ],
    )


def _intranet_target_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "set_target_intranet",
        _base_target_fields(data, target_mode=TargetMode.INTRANET.value)
        + [
            _hidden("network_profile", "intranet_private"),
            _select(
                "exposure_mode",
                "Exposure mode",
                _string_options(("private", "lan"), _value(data, "exposure_mode", default="private")),
                required=True,
            ),
            _field(
                "host",
                "Intranet host",
                _value(data, "host", "target_host", "private_host"),
                required=True,
                placeholder="konnaxion.local",
            ),
        ],
    )


def _temporary_public_target_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "set_target_temporary_public",
        _base_target_fields(data, target_mode=TargetMode.TEMPORARY_PUBLIC.value)
        + [
            _hidden("network_profile", "public_temporary"),
            _hidden("exposure_mode", "temporary_tunnel"),
            _field(
                "public_host",
                "Public host",
                _value(data, "public_host", "host"),
                placeholder="temporary-demo.example.com",
            ),
            _field(
                "public_mode_expires_at",
                "Public mode expires at",
                _value(data, "public_mode_expires_at", "expires_at"),
                required=True,
                placeholder="2026-04-30T22:00:00Z",
            ),
            _checkbox("confirmed", "Confirm temporary public exposure", _bool_value(data, "confirmed")),
        ],
    )


def _droplet_target_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "set_target_droplet",
        _droplet_fields(data, require_capsule=False),
    )


def _deploy_local_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "deploy_local",
        _base_target_fields(data, target_mode=TargetMode.LOCAL.value)
        + _deploy_capsule_metadata_fields(data)
        + [
            _hidden("network_profile", "local_only"),
            _hidden("exposure_mode", "private"),
        ],
    )


def _deploy_intranet_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "deploy_intranet",
        _base_target_fields(data, target_mode=TargetMode.INTRANET.value)
        + _deploy_capsule_metadata_fields(data)
        + [
            _hidden("network_profile", "intranet_private"),
            _select(
                "exposure_mode",
                "Exposure mode",
                _string_options(("private", "lan"), _value(data, "exposure_mode", default="private")),
                required=True,
            ),
            _field("host", "Intranet host", _value(data, "host", "target_host"), required=True),
        ],
    )


def _deploy_droplet_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "deploy_droplet",
        _droplet_fields(data, require_capsule=True),
    )


def _droplet_operation_forms(data: Mapping[str, Any]) -> str:
    return (
        _droplet_operation_form("check_droplet_agent", data)
        + _droplet_operation_form("copy_capsule_to_droplet", data, require_capsule=True)
        + _droplet_operation_form("start_droplet_instance", data)
    )


def _droplet_operation_form(
    action: str,
    data: Mapping[str, Any],
    *,
    require_capsule: bool = False,
) -> str:
    fields = _droplet_fields(data, require_capsule=require_capsule, compact=True)
    return _action_form(action, fields)


def _base_target_fields(data: Mapping[str, Any], *, target_mode: str) -> list[FormField]:
    return [
        _hidden("target_mode", target_mode),
        _field("instance_id", "Instance ID", _value(data, "instance_id", default=DEFAULT_INSTANCE_ID), required=True),
        _field(
            "runtime_root",
            "Runtime root",
            _value(data, "runtime_root", "target_runtime_root", default=DEFAULT_RUNTIME_ROOT),
            required=True,
        ),
        _field(
            "capsule_dir",
            "Capsule directory",
            _value(data, "capsule_dir", "target_capsule_dir", default=f"{DEFAULT_RUNTIME_ROOT}\\capsules"),
            required=True,
        ),
        _field("source_dir", "Source folder", _value(data, "source_dir", default=DEFAULT_SOURCE_DIR)),
        _field(
            "capsule_output_dir",
            "Capsule output folder",
            _value(data, "capsule_output_dir", "output_dir", default=DEFAULT_CAPSULE_OUTPUT_DIR),
        ),
    ]


def _deploy_capsule_metadata_fields(data: Mapping[str, Any]) -> list[FormField]:
    return [
        _field("capsule_id", "Capsule ID", _value(data, "capsule_id", default=DEFAULT_CAPSULE_ID), required=True),
        _field(
            "capsule_version",
            "Capsule version",
            _value(data, "capsule_version", "version", default=DEFAULT_CAPSULE_VERSION),
            required=True,
        ),
        _field("capsule_file", "Capsule file", _value(data, "capsule_file", "capsule_path")),
    ]


def _droplet_fields(
    data: Mapping[str, Any],
    *,
    require_capsule: bool,
    compact: bool = False,
) -> list[FormField]:
    fields: list[FormField] = [
        _hidden("target_mode", TargetMode.DROPLET.value),
        _hidden("network_profile", "public_vps"),
        _hidden("exposure_mode", "public"),
        _field("instance_id", "Instance ID", _value(data, "instance_id", default=DEFAULT_INSTANCE_ID), required=True),
        _field(
            "droplet_name",
            "Droplet name",
            _value(data, "droplet_name", default="konnaxion-droplet"),
            required=True,
        ),
        _field("droplet_host", "Droplet host / IP", _value(data, "droplet_host", "host"), required=True),
        _field("droplet_user", "SSH user", _value(data, "droplet_user", "ssh_user", default="root"), required=True),
        _field("ssh_key_path", "SSH key path", _value(data, "ssh_key_path", "droplet_ssh_key"), required=True),
        _field("ssh_port", "SSH port", _value(data, "ssh_port", default="22"), field_type="number"),
        _field(
            "remote_kx_root",
            "Remote KX root",
            _value(data, "remote_kx_root", "droplet_kx_root", default="/opt/konnaxion"),
            required=True,
        ),
        _field(
            "remote_capsule_dir",
            "Remote capsule directory",
            _value(data, "remote_capsule_dir", "droplet_capsule_dir", default="/opt/konnaxion/capsules"),
            required=True,
        ),
    ]

    if require_capsule:
        fields.append(
            _field("capsule_file", "Capsule file", _value(data, "capsule_file", "capsule_path"), required=True)
        )

    if not compact:
        fields.extend(
            [
                _field("source_dir", "Source folder", _value(data, "source_dir", default=DEFAULT_SOURCE_DIR)),
                _field("domain", "Domain", _value(data, "domain", "droplet_domain")),
                _field("remote_agent_url", "Remote Agent URL", _value(data, "remote_agent_url", "droplet_agent_url")),
            ]
        )

    fields.append(_checkbox("confirmed", "Confirm public Droplet/VPS target", _bool_value(data, "confirmed")))

    return fields


def _build_defaults_form(data: Mapping[str, Any]) -> str:
    return _action_form(
        "build_capsule",
        [
            _field("source_dir", "Source folder", _value(data, "source_dir", default=DEFAULT_SOURCE_DIR), required=True),
            _field(
                "capsule_output_dir",
                "Capsule output folder",
                _value(data, "capsule_output_dir", "output_dir", default=DEFAULT_CAPSULE_OUTPUT_DIR),
                required=True,
            ),
            _field("capsule_id", "Capsule ID", _value(data, "capsule_id", default=DEFAULT_CAPSULE_ID), required=True),
            _field(
                "capsule_version",
                "Capsule version",
                _value(data, "capsule_version", "version", default=DEFAULT_CAPSULE_VERSION),
                required=True,
            ),
            _field("channel", "Channel", _value(data, "channel", default=DEFAULT_CHANNEL), required=True),
        ],
        submit_label="Save by building",
    )


def _check_forms() -> str:
    return _single_button_form("check_manager") + _single_button_form("check_agent")


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _action_form(
    action: str,
    fields: Sequence[FormField],
    *,
    submit_label: str | None = None,
) -> str:
    action_value = str(action)
    label = submit_label or ACTION_LABELS.get(action_value, action_value.replace("_", " ").title())

    return render_form(
        route_for_action(action_value),
        fields,
        submit_label=label,
        hidden={"action": action_value},
    )


def _single_button_form(action: str) -> str:
    return render_form(
        route_for_action(action),
        "",
        submit_label=ACTION_LABELS.get(action, action.replace("_", " ").title()),
        hidden={"action": action},
    )


def _simple_action_card(title: str, intro: str, actions: Sequence[str]) -> str:
    forms = [_single_button_form(action) for action in actions]
    return render_card(
        title,
        f'<p class="kx-muted">{_escape_text(intro)}</p>' + render_action_bar(forms),
    )


def _field(
    name: str,
    label: str,
    value: Any = "",
    *,
    field_type: str = "text",
    required: bool = False,
    placeholder: str = "",
    help_text: str = "",
) -> FormField:
    return FormField(
        name=name,
        label=label,
        value=value,
        field_type=field_type,
        required=required,
        placeholder=placeholder,
        help_text=help_text,
    )


def _hidden(name: str, value: Any) -> FormField:
    return FormField(name=name, label="", value=value, field_type="hidden")


def _checkbox(name: str, label: str, checked: bool, *, help_text: str = "") -> FormField:
    return FormField(
        name=name,
        label=label,
        value=checked,
        field_type="checkbox",
        help_text=help_text,
    )


def _select(
    name: str,
    label: str,
    options: Sequence[SelectOption],
    *,
    required: bool = False,
    help_text: str = "",
) -> FormField:
    return FormField(
        name=name,
        label=label,
        field_type="select",
        required=required,
        options=options,
        help_text=help_text,
    )


def _enum_options(enum_type: type[Any], selected: Any = "") -> list[SelectOption]:
    selected_value = str(getattr(selected, "value", selected) or "")

    return [
        SelectOption(
            value=str(item.value),
            label=_humanize(str(item.value)),
            selected=str(item.value) == selected_value,
        )
        for item in enum_type
    ]


def _string_options(values: Sequence[str], selected: Any = "") -> list[SelectOption]:
    selected_value = str(getattr(selected, "value", selected) or "")

    return [
        SelectOption(
            value=str(value),
            label=_humanize(str(value)),
            selected=str(value) == selected_value,
        )
        for value in values
    ]


def _state(data: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(data or {})


def _value(data: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return getattr(value, "value", value)

    return getattr(default, "value", default)


def _bool_value(
    data: Mapping[str, Any],
    key: str,
    *,
    default: bool = False,
) -> bool:
    value = data.get(key)

    if value in (None, ""):
        return default

    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
        "checked",
        "confirmed",
    }


def _humanize(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").strip().title()


def _escape_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


__all__ = [
    "BACKUP_CLASS_OPTIONS",
    "TARGET_MODE_OPTIONS",
    "form_for_action",
    "render_about_forms",
    "render_backup_forms",
    "render_capsule_forms",
    "render_dashboard_forms",
    "render_health_forms",
    "render_instance_forms",
    "render_logs_forms",
    "render_network_forms",
    "render_page_forms",
    "render_restore_forms",
    "render_security_forms",
    "render_settings_forms",
    "render_target_forms",
]