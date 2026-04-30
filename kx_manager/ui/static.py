"""Canonical UI constants, routes, action names, and payload aliases."""

from __future__ import annotations

from typing import Any, Mapping


APP_TITLE = "Konnaxion Capsule Manager"
APP_ICON = "◈"
DEFAULT_REFRESH_SECONDS = 5

UI_BASE_PATH = "/ui"
ACTION_BASE_PATH = "/ui/actions"


UI_PAGE_ROUTES: tuple[str, ...] = (
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


PAGE_TITLES: dict[str, str] = {
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


CONTRACT_ACTIONS: tuple[str, ...] = (
    "check_manager",
    "check_agent",
    "select_source_folder",
    "select_capsule_output_folder",
    "build_capsule",
    "rebuild_capsule",
    "verify_capsule",
    "import_capsule",
    "list_capsules",
    "view_capsule",
    "create_instance",
    "update_instance",
    "start_instance",
    "stop_instance",
    "restart_instance",
    "instance_status",
    "view_logs",
    "view_health",
    "open_instance",
    "rollback_instance",
    "create_backup",
    "list_backups",
    "verify_backup",
    "restore_backup",
    "restore_backup_new",
    "test_restore_backup",
    "run_security_check",
    "set_network_profile",
    "disable_public_mode",
    "set_target_local",
    "set_target_intranet",
    "set_target_droplet",
    "set_target_temporary_public",
    "deploy_local",
    "deploy_intranet",
    "deploy_droplet",
    "check_droplet_agent",
    "copy_capsule_to_droplet",
    "start_droplet_instance",
    "open_manager_docs",
    "open_agent_docs",
)


ACTION_ALIASES: dict[str, str] = {
    "open_runtime": "open_instance",
}


KNOWN_ACTIONS: frozenset[str] = frozenset(CONTRACT_ACTIONS) | frozenset(ACTION_ALIASES)


ACTION_LABELS: dict[str, str] = {
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


BROWSER_LINK_ACTIONS: dict[str, str] = {
    "open_instance": "runtime_url",
    "open_manager_docs": "/docs",
    "open_agent_docs": "/docs",
}


BROWSER_ONLY_ACTIONS: frozenset[str] = frozenset(BROWSER_LINK_ACTIONS)


ACTION_ROUTES: dict[str, str] = {
    action: f"{ACTION_BASE_PATH}/{action.replace('_', '-')}"
    for action in CONTRACT_ACTIONS
    if action not in BROWSER_ONLY_ACTIONS
}


NAV_ITEMS: tuple[tuple[str, str], ...] = (
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


def canonical_action(action: Any) -> str:
    value = str(getattr(action, "value", action)).strip()
    return ACTION_ALIASES.get(value, value)


def route_for_action(action: Any) -> str:
    action_value = canonical_action(action)

    if action_value in BROWSER_ONLY_ACTIONS:
        raise KeyError(f"Browser-only action has no POST route: {action_value}")

    return ACTION_ROUTES[action_value]


def browser_link_for_action(action: Any) -> str:
    action_value = canonical_action(action)
    return BROWSER_LINK_ACTIONS[action_value]


def title_for_route(route: str) -> str:
    return PAGE_TITLES.get(route, "Dashboard")


def normalize_payload_aliases(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(payload or {})

    # Capsule path aliases.
    if data.get("capsule_file") and not data.get("capsule_path"):
        data["capsule_path"] = data["capsule_file"]
    if data.get("capsule_path") and not data.get("capsule_file"):
        data["capsule_file"] = data["capsule_path"]

    # Output aliases.
    if data.get("output_dir") and not data.get("capsule_output_dir"):
        data["capsule_output_dir"] = data["output_dir"]

    # Target host aliases.
    if data.get("target_host") and not data.get("host"):
        data["host"] = data["target_host"]
    if data.get("public_host") and not data.get("host"):
        data["host"] = data["public_host"]
    if data.get("private_host") and not data.get("host"):
        data["host"] = data["private_host"]

    # Droplet aliases.
    if data.get("droplet_ssh_key") and not data.get("ssh_key_path"):
        data["ssh_key_path"] = data["droplet_ssh_key"]
    if data.get("ssh_key") and not data.get("ssh_key_path"):
        data["ssh_key_path"] = data["ssh_key"]
    if data.get("ssh_user") and not data.get("droplet_user"):
        data["droplet_user"] = data["ssh_user"]
    if data.get("user") and not data.get("droplet_user"):
        data["droplet_user"] = data["user"]
    if data.get("droplet_kx_root") and not data.get("remote_kx_root"):
        data["remote_kx_root"] = data["droplet_kx_root"]
    if data.get("remote_root") and not data.get("remote_kx_root"):
        data["remote_kx_root"] = data["remote_root"]
    if data.get("droplet_capsule_dir") and not data.get("remote_capsule_dir"):
        data["remote_capsule_dir"] = data["droplet_capsule_dir"]
    if data.get("droplet_domain") and not data.get("domain"):
        data["domain"] = data["droplet_domain"]
    if data.get("droplet_agent_url") and not data.get("remote_agent_url"):
        data["remote_agent_url"] = data["droplet_agent_url"]

    # Restore aliases.
    if data.get("target_instance_id") and not data.get("new_instance_id"):
        data["new_instance_id"] = data["target_instance_id"]
    if data.get("new_instance_id") and not data.get("target_instance_id"):
        data["target_instance_id"] = data["new_instance_id"]

    if data.get("backup_id") and not data.get("source_backup_id"):
        data["source_backup_id"] = data["backup_id"]
    if data.get("from_backup_id") and not data.get("source_backup_id"):
        data["source_backup_id"] = data["from_backup_id"]

    # Logs aliases.
    if data.get("tail_lines") and not data.get("lines"):
        data["lines"] = data["tail_lines"]

    return data


__all__ = [
    "ACTION_ALIASES",
    "ACTION_BASE_PATH",
    "ACTION_LABELS",
    "ACTION_ROUTES",
    "APP_ICON",
    "APP_TITLE",
    "BROWSER_LINK_ACTIONS",
    "BROWSER_ONLY_ACTIONS",
    "CONTRACT_ACTIONS",
    "DEFAULT_REFRESH_SECONDS",
    "KNOWN_ACTIONS",
    "NAV_ITEMS",
    "PAGE_TITLES",
    "UI_BASE_PATH",
    "UI_PAGE_ROUTES",
    "browser_link_for_action",
    "canonical_action",
    "normalize_payload_aliases",
    "route_for_action",
    "title_for_route",
]