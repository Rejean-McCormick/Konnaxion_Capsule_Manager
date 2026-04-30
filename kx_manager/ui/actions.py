"""
GUI action dispatcher for the Konnaxion Capsule Manager.

The UI layer must not control Docker, firewall rules, host paths, backups,
or runtime services directly. Every GUI action is dispatched through one of:

- Manager route
- KonnaxionAgentClient method
- Builder service wrapper
- Target service wrapper
- Deploy service wrapper
- Browser-link result

No arbitrary shell execution is allowed here.
"""

from __future__ import annotations

import importlib
import inspect
import os
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Sequence
from urllib.parse import quote

import httpx

try:
    from .pages import UiAction
except Exception:  # pragma: no cover - staged build compatibility
    from typing import Any as UiAction  # type: ignore

from kx_manager.client import (
    KonnaxionAgentClient,
    KonnaxionAgentClientError,
)

try:
    from kx_manager.ui.static import (
        ACTION_ALIASES,
        ACTION_LABELS,
        ACTION_ROUTES as STATIC_ACTION_ROUTES,
        BROWSER_LINK_ACTIONS,
        CONTRACT_ACTIONS,
        KNOWN_ACTIONS,
        normalize_payload_aliases,
    )

    BROWSER_LINK_ACTIONS: dict[str, str] = {
        "open_instance": "runtime_url",
        "open_manager_docs": "/docs",
        "open_agent_docs": "/docs",
    }

    BROWSER_ONLY_ACTIONS: frozenset[str] = frozenset(BROWSER_LINK_ACTIONS)

    ACTION_ROUTES: dict[str, str] = {
        action: f"/ui/actions/{action.replace('_', '-')}"
        for action in CONTRACT_ACTIONS
        if action not in BROWSER_ONLY_ACTIONS
    }
except Exception:  # pragma: no cover - staged build compatibility
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

    KNOWN_ACTIONS: frozenset[str] = frozenset(CONTRACT_ACTIONS) | frozenset(
        ACTION_ALIASES
    )

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

    ACTION_ROUTES: dict[str, str] = {
        action: f"/ui/actions/{action.replace('_', '-')}"
        for action in CONTRACT_ACTIONS
    }

    BROWSER_LINK_ACTIONS: dict[str, str] = {
        "open_instance": "runtime_url",
        "open_manager_docs": "/docs",
        "open_agent_docs": "/docs",
    }

    def normalize_payload_aliases(payload: Mapping[str, Any] | None) -> dict[str, Any]:
        data = dict(payload or {})

        if data.get("capsule_file") and not data.get("capsule_path"):
            data["capsule_path"] = data["capsule_file"]
        if data.get("capsule_path") and not data.get("capsule_file"):
            data["capsule_file"] = data["capsule_path"]

        if data.get("output_dir") and not data.get("capsule_output_dir"):
            data["capsule_output_dir"] = data["output_dir"]

        if data.get("target_host") and not data.get("host"):
            data["host"] = data["target_host"]
        if data.get("private_host") and not data.get("host"):
            data["host"] = data["private_host"]
        if data.get("public_host") and not data.get("host"):
            data["host"] = data["public_host"]

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

        if data.get("target_instance_id") and not data.get("new_instance_id"):
            data["new_instance_id"] = data["target_instance_id"]
        if data.get("new_instance_id") and not data.get("target_instance_id"):
            data["target_instance_id"] = data["new_instance_id"]

        if data.get("backup_id") and not data.get("source_backup_id"):
            data["source_backup_id"] = data["backup_id"]
        if data.get("from_backup_id") and not data.get("source_backup_id"):
            data["source_backup_id"] = data["from_backup_id"]

        if data.get("tail_lines") and not data.get("lines"):
            data["lines"] = data["tail_lines"]

        return data


JsonDict = dict[str, Any]


@dataclass(slots=True)
class GuiActionResult:
    ok: bool
    action: str
    message: str
    instance_id: str | None = None
    data: JsonDict = field(default_factory=dict)
    stdout: str | None = None
    stderr: str | None = None
    returncode: int | None = None

    def to_dict(self) -> JsonDict:
        return {
            "ok": self.ok,
            "action": self.action,
            "message": self.message,
            "instance_id": self.instance_id,
            "data": _json_safe(self.data),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
        }


AGENT_ENDPOINTS: dict[str, str] = {
    "check_agent": "GET /v1/health",
    "verify_capsule": "POST /v1/capsules/verify",
    "import_capsule": "POST /v1/capsules/import",
    "create_instance": "POST /v1/instances/create",
    "update_instance": "POST /v1/instances/update",
    "start_instance": "POST /v1/instances/start",
    "stop_instance": "POST /v1/instances/stop",
    "instance_status": "POST /v1/instances/status",
    "view_logs": "POST /v1/instances/logs",
    "view_health": "POST /v1/instances/health",
    "rollback_instance": "POST /v1/instances/rollback",
    "create_backup": "POST /v1/instances/backup",
    "restore_backup": "POST /v1/instances/restore",
    "restore_backup_new": "POST /v1/instances/restore-new",
    "run_security_check": "POST /v1/security/check",
    "set_network_profile": "POST /v1/network/set-profile",
    "disable_public_mode": "POST /v1/network/set-profile",
}


CLI_FALLBACKS: dict[str, dict[str, Any]] = {}


ACTION_DISPATCH_TABLE: dict[str, str] = {
    "check_manager": "manager_route",
    "check_agent": "agent_client",
    "select_source_folder": "ui_form",
    "select_capsule_output_folder": "ui_form",
    "build_capsule": "builder_service",
    "rebuild_capsule": "builder_service",
    "verify_capsule": "builder_or_agent_client",
    "import_capsule": "agent_client",
    "list_capsules": "manager_route",
    "view_capsule": "manager_route",
    "create_instance": "agent_client",
    "update_instance": "agent_client",
    "start_instance": "agent_client",
    "stop_instance": "agent_client",
    "restart_instance": "composed_agent_client",
    "instance_status": "agent_client",
    "view_logs": "agent_client",
    "view_health": "agent_client",
    "open_instance": "browser_link",
    "rollback_instance": "agent_client",
    "create_backup": "agent_client",
    "list_backups": "manager_route",
    "verify_backup": "manager_route",
    "restore_backup": "agent_client",
    "restore_backup_new": "agent_client",
    "test_restore_backup": "manager_route",
    "run_security_check": "agent_client",
    "set_network_profile": "agent_client",
    "disable_public_mode": "agent_client",
    "set_target_local": "target_service",
    "set_target_intranet": "target_service",
    "set_target_droplet": "target_service",
    "set_target_temporary_public": "target_service",
    "deploy_local": "deploy_service",
    "deploy_intranet": "deploy_service",
    "deploy_droplet": "deploy_service",
    "check_droplet_agent": "deploy_service",
    "copy_capsule_to_droplet": "deploy_service",
    "start_droplet_instance": "deploy_service",
    "open_manager_docs": "browser_link",
    "open_agent_docs": "browser_link",
}


TARGET_DEFAULTS: dict[str, JsonDict] = {
    "local": {
        "target_mode": "local",
        "network_profile": "local_only",
        "exposure_mode": "private",
        "public_mode_enabled": False,
        "public_mode_expires_at": None,
    },
    "intranet": {
        "target_mode": "intranet",
        "network_profile": "intranet_private",
        "exposure_mode": "private",
        "public_mode_enabled": False,
        "public_mode_expires_at": None,
    },
    "temporary_public": {
        "target_mode": "temporary_public",
        "network_profile": "public_temporary",
        "exposure_mode": "temporary_tunnel",
        "public_mode_enabled": True,
    },
    "droplet": {
        "target_mode": "droplet",
        "network_profile": "public_vps",
        "exposure_mode": "public",
        "public_mode_enabled": True,
        "public_mode_expires_at": None,
        "remote_kx_root": "/opt/konnaxion",
    },
}


async def dispatch_gui_action(
    action: UiAction,
    payload: Mapping[str, Any] | None = None,
) -> GuiActionResult:
    """Dispatch one GUI action to its approved backend path."""

    action_value = _action_value(action)
    canonical_action = ACTION_ALIASES.get(action_value, action_value)
    safe_payload = _normalize_payload(normalize_payload_aliases(payload))

    if canonical_action not in CONTRACT_ACTIONS:
        return GuiActionResult(
            ok=False,
            action=action_value,
            message=f"Unknown GUI action rejected: {action_value}",
            instance_id=_payload_instance_id(safe_payload),
            data={"known_actions": sorted(CONTRACT_ACTIONS)},
        )

    handler = ACTION_HANDLERS[canonical_action]

    try:
        result = await handler(canonical_action, safe_payload)
    except ValueError as exc:
        return GuiActionResult(
            ok=False,
            action=action_value,
            message=str(exc),
            instance_id=_payload_instance_id(safe_payload),
        )
    except KonnaxionAgentClientError as exc:
        return GuiActionResult(
            ok=False,
            action=action_value,
            message=str(exc),
            instance_id=_payload_instance_id(safe_payload),
            data={"status_code": exc.status_code, "details": exc.details},
            stderr=str(exc),
            returncode=exc.status_code,
        )
    except Exception as exc:
        return GuiActionResult(
            ok=False,
            action=action_value,
            message=f"Action failed: {exc}",
            instance_id=_payload_instance_id(safe_payload),
            stderr=str(exc),
        )

    if action_value != canonical_action:
        result.action = action_value

    return result


def is_known_gui_action(action: Any) -> bool:
    """Return whether an action is known to the GUI dispatcher."""

    action_value = _action_value(action)

    if action_value in KNOWN_ACTIONS:
        return True

    return ACTION_ALIASES.get(action_value, action_value) in CONTRACT_ACTIONS


async def _handle_check_manager(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    return await _manager_request_first(
        action=action,
        payload=payload,
        attempts=(("GET", "/health"), ("GET", "/v1/health")),
        success_message="Manager is reachable.",
        failure_message="Manager health check failed.",
    )


async def _handle_check_agent(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    async with KonnaxionAgentClient.from_env() as client:
        outcome = await client.health()

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message="Agent is reachable.",
    )


async def _handle_select_source_folder(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    source_dir = _require_text(payload, "source_dir", "kx_source_dir", "KX_SOURCE_DIR")
    return GuiActionResult(
        ok=True,
        action=action,
        message="Konnaxion source folder selected.",
        data={"source_dir": source_dir},
    )


async def _handle_select_capsule_output_folder(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    output_dir = _require_text(
        payload,
        "capsule_output_dir",
        "output_dir",
        "kx_capsule_output_dir",
        "KX_CAPSULE_OUTPUT_DIR",
    )
    return GuiActionResult(
        ok=True,
        action=action,
        message="Capsule output folder selected.",
        data={"capsule_output_dir": output_dir},
    )


async def _handle_build_capsule(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    builder = _import_module("kx_manager.services.builder")
    function_name = "rebuild_capsule" if action == "rebuild_capsule" else "build_capsule"
    function = getattr(builder, function_name, None)

    if function is None and action == "rebuild_capsule":
        function = getattr(builder, "build_capsule", None)
        payload = {**payload, "rebuild": True, "force": True}

    if function is None:
        return _missing_backend(action, f"kx_manager.services.builder.{function_name}")

    outcome = await _call_service_function(
        function,
        payload,
        request_module=builder,
        request_class_name="BuildCapsuleRequest",
    )

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message="Capsule build completed.",
    )


async def _handle_verify_capsule(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    builder = _try_import_module("kx_manager.services.builder")

    if builder is not None and hasattr(builder, "verify_capsule"):
        function = getattr(builder, "verify_capsule")
        outcome = await _call_service_function(
            function,
            payload,
            request_module=builder,
            request_class_name="VerifyCapsuleRequest",
        )
        return _result_from_backend(
            action=action,
            outcome=outcome,
            payload=payload,
            default_message="Capsule verification completed.",
        )

    capsule_path = _require_text(payload, "capsule_path", "capsule_file")
    async with KonnaxionAgentClient.from_env() as client:
        outcome = await client.verify_capsule(capsule_path=capsule_path)

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message="Capsule verification completed.",
    )


async def _handle_import_capsule(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    capsule_path = _require_text(payload, "capsule_path", "capsule_file")
    instance_id = _require_text(payload, "instance_id")
    network_profile = str(payload.get("network_profile") or "intranet_private")

    async with KonnaxionAgentClient.from_env() as client:
        outcome = await client.import_capsule(
            capsule_path=capsule_path,
            instance_id=instance_id,
            network_profile=network_profile,
        )

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message="Capsule imported.",
    )


async def _handle_create_instance(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    async with KonnaxionAgentClient.from_env() as client:
        outcome = await client.create_instance(
            instance_id=_require_text(payload, "instance_id"),
            capsule_id=_require_text(payload, "capsule_id"),
            network_profile=str(payload.get("network_profile") or "intranet_private"),
            exposure_mode=str(payload.get("exposure_mode") or "private"),
            generate_secrets=_bool(payload.get("generate_secrets"), default=True),
        )

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message="Instance created.",
    )


async def _handle_update_instance(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    async with KonnaxionAgentClient.from_env() as client:
        outcome = await client.update_instance(
            instance_id=_require_text(payload, "instance_id"),
            capsule_path=_require_text(payload, "capsule_path", "capsule_file"),
            create_pre_update_backup=_bool(
                payload.get("create_pre_update_backup"),
                default=True,
            ),
        )

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message="Instance updated.",
    )


async def _handle_start_instance(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    async with KonnaxionAgentClient.from_env() as client:
        outcome = await client.start_instance(
            instance_id=_require_text(payload, "instance_id"),
            run_security_gate=_bool(payload.get("run_security_gate"), default=True),
        )

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message="Instance started.",
    )


async def _handle_stop_instance(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    async with KonnaxionAgentClient.from_env() as client:
        outcome = await client.stop_instance(
            instance_id=_require_text(payload, "instance_id"),
            timeout_seconds=_int(payload.get("timeout_seconds"), default=60),
        )

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message="Instance stopped.",
    )


async def _handle_restart_instance(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    stop_result = await _handle_stop_instance("stop_instance", payload)

    if not stop_result.ok:
        return GuiActionResult(
            ok=False,
            action=action,
            message="Restart failed while stopping the instance.",
            instance_id=stop_result.instance_id,
            data={"stop": stop_result.to_dict()},
            stderr=stop_result.stderr,
            returncode=stop_result.returncode,
        )

    start_result = await _handle_start_instance("start_instance", payload)

    return GuiActionResult(
        ok=start_result.ok,
        action=action,
        message=(
            "Instance restarted."
            if start_result.ok
            else "Restart failed while starting the instance."
        ),
        instance_id=start_result.instance_id,
        data={"stop": stop_result.to_dict(), "start": start_result.to_dict()},
        stdout=start_result.stdout,
        stderr=start_result.stderr,
        returncode=start_result.returncode,
    )


async def _handle_instance_status(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    async with KonnaxionAgentClient.from_env() as client:
        outcome = await client.instance_status(
            instance_id=_require_text(payload, "instance_id")
        )

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message="Instance status loaded.",
    )


async def _handle_view_logs(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    raw_tail = payload.get("lines", payload.get("tail_lines", payload.get("tail", 200)))

    if isinstance(raw_tail, bool):
        raw_tail = 200

    async with KonnaxionAgentClient.from_env() as client:
        outcome = await client.instance_logs(
            instance_id=_require_text(payload, "instance_id"),
            service=payload.get("service"),
            tail=_int(raw_tail, default=200),
        )

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message="Instance logs loaded.",
    )


async def _handle_view_health(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    async with KonnaxionAgentClient.from_env() as client:
        outcome = await client.instance_health(
            instance_id=_require_text(payload, "instance_id")
        )

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message="Instance health loaded.",
    )


async def _handle_rollback_instance(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    async with KonnaxionAgentClient.from_env() as client:
        outcome = await client.rollback_instance(
            instance_id=_require_text(payload, "instance_id"),
            target_release_id=_optional_text(
                payload,
                "target_release_id",
                "target_capsule_id",
            ),
            restore_data=_bool(payload.get("restore_data"), default=True),
        )

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message="Instance rollback completed.",
    )


async def _handle_create_backup(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    async with KonnaxionAgentClient.from_env() as client:
        outcome = await client.backup_instance(
            instance_id=_require_text(payload, "instance_id"),
            backup_class=str(payload.get("backup_class") or "manual"),
            verify_after_create=_bool(payload.get("verify_after_create"), default=True),
        )

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message="Backup created.",
    )


async def _handle_restore_backup(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    async with KonnaxionAgentClient.from_env() as client:
        outcome = await client.restore_instance(
            instance_id=_require_text(payload, "instance_id"),
            backup_id=_require_text(payload, "backup_id"),
            create_pre_restore_backup=_bool(
                payload.get("create_pre_restore_backup"),
                default=True,
            ),
        )

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message="Backup restored.",
    )


async def _handle_restore_backup_new(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    source_backup_id = _require_text(
        payload,
        "source_backup_id",
        "from_backup_id",
        "backup_id",
    )
    new_instance_id = _require_text(
        payload,
        "new_instance_id",
        "target_instance_id",
    )

    async with KonnaxionAgentClient.from_env() as client:
        outcome = await client.restore_new_instance(
            source_backup_id=source_backup_id,
            new_instance_id=new_instance_id,
            network_profile=str(payload.get("network_profile") or "intranet_private"),
        )

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message="Backup restored into new instance.",
    )


async def _handle_run_security_check(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    async with KonnaxionAgentClient.from_env() as client:
        outcome = await client.security_check(
            instance_id=_require_text(payload, "instance_id"),
            blocking=_bool(payload.get("blocking"), default=True),
        )

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message="Security Gate check completed.",
    )


async def _handle_set_network_profile(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    async with KonnaxionAgentClient.from_env() as client:
        outcome = await client.set_network_profile(
            instance_id=_require_text(payload, "instance_id"),
            network_profile=_require_text(payload, "network_profile"),
            exposure_mode=str(payload.get("exposure_mode") or "private"),
            public_mode_expires_at=payload.get("public_mode_expires_at"),
        )

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message="Network profile updated.",
    )


async def _handle_disable_public_mode(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    safe_payload = {
        **payload,
        "network_profile": "intranet_private",
        "exposure_mode": "private",
        "public_mode_enabled": False,
        "public_mode_expires_at": None,
    }

    result = await _handle_set_network_profile("set_network_profile", safe_payload)
    result.action = action

    if result.ok:
        result.message = "Public mode disabled."

    return result


async def _handle_manager_capsule_action(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    if action == "list_capsules":
        return await _manager_request_first(
            action=action,
            payload=payload,
            attempts=(("GET", "/v1/capsules"), ("GET", "/capsules")),
            success_message="Capsules listed.",
            failure_message="Unable to list capsules.",
        )

    capsule_id = _require_text(payload, "capsule_id", "capsule_path", "capsule_file", "id")
    quoted = quote(capsule_id, safe="")

    return await _manager_request_first(
        action=action,
        payload=payload,
        attempts=(("GET", f"/v1/capsules/{quoted}"), ("GET", f"/capsules/{quoted}")),
        success_message="Capsule loaded.",
        failure_message="Unable to load capsule.",
    )


async def _handle_manager_backup_action(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    if action == "list_backups":
        instance_id = str(payload.get("instance_id") or "").strip()
        query = f"?instance_id={quote(instance_id)}" if instance_id else ""

        return await _manager_request_first(
            action=action,
            payload=payload,
            attempts=(("GET", f"/v1/backups{query}"), ("GET", f"/backups{query}")),
            success_message="Backups listed.",
            failure_message="Unable to list backups.",
        )

    if action == "verify_backup":
        return await _manager_request_first(
            action=action,
            payload=payload,
            attempts=(("POST", "/v1/backups/verify"), ("POST", "/backups/verify")),
            success_message="Backup verification completed.",
            failure_message="Backup verification failed.",
        )

    if action == "test_restore_backup":
        return await _manager_request_first(
            action=action,
            payload=payload,
            attempts=(
                ("POST", "/v1/backups/test-restore"),
                ("POST", "/backups/test-restore"),
            ),
            success_message="Backup test restore completed.",
            failure_message="Backup test restore failed.",
        )

    return GuiActionResult(
        ok=False,
        action=action,
        message=f"Unsupported backup action: {action}",
    )


async def _handle_set_target(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    target_mode = action.removeprefix("set_target_")

    if target_mode not in TARGET_DEFAULTS:
        return GuiActionResult(
            ok=False,
            action=action,
            message=f"Unsupported target mode: {target_mode}",
        )

    config = {**payload, **TARGET_DEFAULTS[target_mode], "target_mode": target_mode}

    if target_mode == "intranet":
        exposure_mode = str(payload.get("exposure_mode") or "private")
        if exposure_mode not in {"private", "lan"}:
            raise ValueError("Intranet target only allows exposure_mode private or lan.")
        config["exposure_mode"] = exposure_mode

    if target_mode == "temporary_public":
        _require_text(payload, "public_mode_expires_at")
        if not _truthy(payload.get("confirmed")):
            raise ValueError("Temporary public target requires explicit confirmation.")

    if target_mode == "droplet":
        _require_text(payload, "droplet_host", "target_host", "host")
        _require_text(payload, "droplet_user", "ssh_user", "user")
        _require_text(payload, "ssh_key_path", "ssh_key", "droplet_ssh_key")
        _require_text(payload, "remote_kx_root", "remote_root", "droplet_kx_root")
        if not _truthy(payload.get("confirmed")):
            raise ValueError("Droplet target requires explicit confirmation.")

    service_data = await _validate_target_config(config)

    return GuiActionResult(
        ok=True,
        action=action,
        message=_target_message(target_mode),
        instance_id=_payload_instance_id(payload),
        data={**config, **service_data},
    )


async def _handle_deploy(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    deploy = _import_module("kx_manager.services.deploy")

    function_name = {
        "deploy_local": "deploy_local",
        "deploy_intranet": "deploy_intranet",
        "deploy_droplet": "deploy_droplet",
    }[action]

    if action == "deploy_droplet":
        _require_text(payload, "droplet_host", "target_host", "host")
        _require_text(payload, "droplet_user", "ssh_user", "user")
        _require_text(payload, "ssh_key_path", "ssh_key", "droplet_ssh_key")
        _require_text(payload, "remote_kx_root", "remote_root", "droplet_kx_root")
        if not _truthy(payload.get("confirmed")):
            raise ValueError("Droplet deploy requires explicit confirmation.")

    function = getattr(deploy, function_name, None)

    if function is None:
        return _missing_backend(action, f"kx_manager.services.deploy.{function_name}")

    request_class = {
        "deploy_local": "LocalDeployRequest",
        "deploy_intranet": "IntranetDeployRequest",
        "deploy_droplet": "DropletDeployRequest",
    }[action]

    outcome = await _call_service_function(
        function,
        payload,
        request_module=deploy,
        request_class_name=request_class,
    )

    return _result_from_backend(
        action=action,
        outcome=outcome,
        payload=payload,
        default_message=f"{action} completed.",
    )


async def _handle_droplet_step(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    deploy = _try_import_module("kx_manager.services.deploy")

    names_by_action = {
        "check_droplet_agent": ("check_droplet_agent", "check_remote_agent"),
        "copy_capsule_to_droplet": ("copy_capsule_to_droplet", "copy_capsule_remote"),
        "start_droplet_instance": ("start_droplet_instance", "start_remote_instance"),
    }

    if deploy is not None:
        for function_name in names_by_action[action]:
            function = getattr(deploy, function_name, None)
            if function is not None:
                outcome = await _call_service_function(
                    function,
                    payload,
                    request_module=deploy,
                    request_class_name="DropletDeployRequest",
                )
                return _result_from_backend(
                    action=action,
                    outcome=outcome,
                    payload=payload,
                    default_message=f"{action} completed.",
                )

    if action == "check_droplet_agent":
        host = _require_text(payload, "droplet_host", "target_host", "host")
        url = str(payload.get("remote_agent_url") or f"http://{host}:8765/v1/health")
        if not url.endswith("/health"):
            url = url.rstrip("/") + "/health"

        data = await _http_json_request("GET", url)
        return _result_from_backend(
            action=action,
            outcome=data,
            payload=payload,
            default_message="Droplet Agent health check completed.",
            ok_default=False,
        )

    return _missing_backend(
        action,
        f"kx_manager.services.deploy.{names_by_action[action][0]}",
    )


async def _handle_open_instance(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    url = str(
        payload.get("url")
        or payload.get("public_url")
        or payload.get("private_url")
        or payload.get("runtime_url")
        or "http://127.0.0.1"
    ).strip()

    return GuiActionResult(
        ok=True,
        action=action,
        message="Runtime URL ready.",
        instance_id=_payload_instance_id(payload),
        data={"url": url, "kind": "browser_link"},
    )


async def _handle_open_manager_docs(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    return GuiActionResult(
        ok=True,
        action=action,
        message="Manager API docs URL ready.",
        data={"url": _manager_base_url().rstrip("/") + "/docs", "kind": "browser_link"},
    )


async def _handle_open_agent_docs(
    action: str,
    payload: Mapping[str, Any],
) -> GuiActionResult:
    base = _agent_base_url().removesuffix("/v1")
    return GuiActionResult(
        ok=True,
        action=action,
        message="Agent API docs URL ready.",
        data={"url": base.rstrip("/") + "/docs", "kind": "browser_link"},
    )


ACTION_HANDLERS: dict[str, Callable[[str, Mapping[str, Any]], Awaitable[GuiActionResult]]] = {
    "check_manager": _handle_check_manager,
    "check_agent": _handle_check_agent,
    "select_source_folder": _handle_select_source_folder,
    "select_capsule_output_folder": _handle_select_capsule_output_folder,
    "build_capsule": _handle_build_capsule,
    "rebuild_capsule": _handle_build_capsule,
    "verify_capsule": _handle_verify_capsule,
    "import_capsule": _handle_import_capsule,
    "list_capsules": _handle_manager_capsule_action,
    "view_capsule": _handle_manager_capsule_action,
    "create_instance": _handle_create_instance,
    "update_instance": _handle_update_instance,
    "start_instance": _handle_start_instance,
    "stop_instance": _handle_stop_instance,
    "restart_instance": _handle_restart_instance,
    "instance_status": _handle_instance_status,
    "view_logs": _handle_view_logs,
    "view_health": _handle_view_health,
    "open_instance": _handle_open_instance,
    "rollback_instance": _handle_rollback_instance,
    "create_backup": _handle_create_backup,
    "list_backups": _handle_manager_backup_action,
    "verify_backup": _handle_manager_backup_action,
    "restore_backup": _handle_restore_backup,
    "restore_backup_new": _handle_restore_backup_new,
    "test_restore_backup": _handle_manager_backup_action,
    "run_security_check": _handle_run_security_check,
    "set_network_profile": _handle_set_network_profile,
    "disable_public_mode": _handle_disable_public_mode,
    "set_target_local": _handle_set_target,
    "set_target_intranet": _handle_set_target,
    "set_target_droplet": _handle_set_target,
    "set_target_temporary_public": _handle_set_target,
    "deploy_local": _handle_deploy,
    "deploy_intranet": _handle_deploy,
    "deploy_droplet": _handle_deploy,
    "check_droplet_agent": _handle_droplet_step,
    "copy_capsule_to_droplet": _handle_droplet_step,
    "start_droplet_instance": _handle_droplet_step,
    "open_manager_docs": _handle_open_manager_docs,
    "open_agent_docs": _handle_open_agent_docs,
}


def _normalize_payload(payload: JsonDict) -> JsonDict:
    normalized = dict(payload)

    if "source_backup_id" not in normalized:
        for key in ("from_backup_id", "backup_id"):
            if normalized.get(key):
                normalized["source_backup_id"] = normalized[key]
                break

    return normalized


def _action_value(action: Any) -> str:
    value = getattr(action, "value", action)
    return str(value).strip()


def _payload_instance_id(payload: Mapping[str, Any]) -> str | None:
    value = payload.get("instance_id") or payload.get("KX_INSTANCE_ID")
    return str(value) if value not in (None, "") else None


def _require_text(payload: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if value not in (None, ""):
            return str(value).strip()

    joined = ", ".join(names)
    raise ValueError(f"Missing required field: {joined}")


def _optional_text(payload: Mapping[str, Any], *names: str) -> str | None:
    for name in names:
        value = payload.get(name)
        if value not in (None, ""):
            return str(value).strip()
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    return str(value or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
        "confirmed",
    }


def _bool(value: Any, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default

    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(value: Any, *, default: int) -> int:
    if value is None or value == "":
        return default

    if isinstance(value, bool):
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _target_message(target_mode: str) -> str:
    return {
        "local": "Local target configured.",
        "intranet": "Intranet target configured.",
        "temporary_public": "Temporary public target configured.",
        "droplet": "Droplet target configured.",
    }[target_mode]


def _missing_backend(action: str, backend: str) -> GuiActionResult:
    return GuiActionResult(
        ok=False,
        action=action,
        message=f"Required backend is not available: {backend}",
        data={"backend": backend},
    )


def _manager_base_url() -> str:
    if os.getenv("KX_MANAGER_URL"):
        return os.environ["KX_MANAGER_URL"].rstrip("/")

    host = os.getenv("KX_MANAGER_HOST", "127.0.0.1")
    port = os.getenv("KX_MANAGER_PORT", "8714")
    scheme = os.getenv("KX_MANAGER_SCHEME", "http")
    return f"{scheme}://{host}:{port}"


def _agent_base_url() -> str:
    if os.getenv("KX_AGENT_URL"):
        return os.environ["KX_AGENT_URL"].rstrip("/")

    host = os.getenv("KX_AGENT_HOST", "127.0.0.1")
    port = os.getenv("KX_AGENT_PORT", "8765")
    scheme = os.getenv("KX_AGENT_SCHEME", "http")
    prefix = os.getenv("KX_AGENT_API_PREFIX", "/v1").strip() or "/v1"
    return f"{scheme}://{host}:{port}/{prefix.strip('/')}"


def _http_timeout_seconds() -> float:
    raw = (
        os.getenv("KX_AGENT_TIMEOUT_SECONDS")
        or os.getenv("KX_MANAGER_TIMEOUT_SECONDS")
        or "30.0"
    )
    try:
        return float(raw)
    except ValueError:
        return 30.0


async def _http_json_request(
    method: str,
    url: str,
    payload: Mapping[str, Any] | None = None,
) -> JsonDict:
    async with httpx.AsyncClient(timeout=_http_timeout_seconds()) as client:
        try:
            response = await client.request(
                method.upper(),
                url,
                json=(
                    dict(payload or {})
                    if payload is not None and method.upper() != "GET"
                    else None
                ),
            )
        except httpx.HTTPError as exc:
            return {"ok": False, "message": str(exc), "url": url}

    try:
        body: Any = response.json() if response.content else {}
    except ValueError:
        body = {"body": response.text}

    if isinstance(body, dict):
        result = dict(body)
    else:
        result = {"items": body}

    result.setdefault("ok", 200 <= response.status_code < 300)
    result.setdefault("status_code", response.status_code)
    result.setdefault("url", url)

    if response.is_error:
        result["ok"] = False
        result.setdefault(
            "message",
            result.get("detail") or f"HTTP {response.status_code}",
        )

    return result


async def _manager_request_first(
    *,
    action: str,
    payload: Mapping[str, Any],
    attempts: Sequence[tuple[str, str]],
    success_message: str,
    failure_message: str,
) -> GuiActionResult:
    last: JsonDict | None = None

    for method, path in attempts:
        url = _manager_base_url().rstrip("/") + path
        result = await _http_json_request(
            method,
            url,
            payload if method.upper() != "GET" else None,
        )
        last = result

        if result.get("ok") is True:
            return _result_from_backend(
                action=action,
                outcome=result,
                payload=payload,
                default_message=success_message,
                ok_default=True,
            )

    return _result_from_backend(
        action=action,
        outcome=last or {},
        payload=payload,
        default_message=failure_message,
        ok_default=False,
    )


async def _validate_target_config(config: Mapping[str, Any]) -> JsonDict:
    targets = _try_import_module("kx_manager.services.targets")

    if targets is None:
        return {}

    data: JsonDict = {}
    target_config: Any = None

    build = getattr(targets, "build_target_config", None)
    if callable(build):
        target_config = await _call_callable_with_best_effort(build, config)

    if target_config is None:
        request_class = (
            "DropletTargetConfig"
            if str(config.get("target_mode")) == "droplet"
            else "TargetConfig"
        )
        target_config = _request_object(targets, request_class, config)

    validate = getattr(targets, "validate_target_config", None)
    if callable(validate) and target_config is not None:
        await _call_callable_with_best_effort(
            validate,
            {},
            preferred_args=(target_config,),
        )

    summary = getattr(targets, "target_summary", None)
    if callable(summary) and target_config is not None:
        value = await _call_callable_with_best_effort(
            summary,
            {},
            preferred_args=(target_config,),
        )
        if isinstance(value, Mapping):
            data.update(_json_safe(value))

    profile_for_target = getattr(targets, "network_profile_for_target", None)
    if callable(profile_for_target):
        profile = await _call_callable_with_best_effort(
            profile_for_target,
            {"target_mode": config["target_mode"]},
            preferred_args=(config["target_mode"],),
        )
        data["network_profile"] = _enum_value(profile)

    exposure_for_target = getattr(targets, "exposure_mode_for_target", None)
    if callable(exposure_for_target):
        exposure = await _call_callable_with_best_effort(
            exposure_for_target,
            {"target_mode": config["target_mode"]},
            preferred_args=(config["target_mode"],),
        )
        if config["target_mode"] == "intranet" and config.get("exposure_mode") == "lan":
            data["exposure_mode"] = "lan"
        else:
            data["exposure_mode"] = _enum_value(exposure)

    return data


async def _call_service_function(
    function: Callable[..., Any],
    payload: Mapping[str, Any],
    *,
    request_module: Any | None = None,
    request_class_name: str | None = None,
) -> Any:
    preferred_args: tuple[Any, ...] = ()

    if request_module is not None and request_class_name:
        request_object = _request_object(request_module, request_class_name, payload)
        if request_object is not None:
            preferred_args = (request_object,)

    return await _call_callable_with_best_effort(
        function,
        payload,
        preferred_args=preferred_args,
    )


async def _call_callable_with_best_effort(
    function: Callable[..., Any],
    payload: Mapping[str, Any],
    *,
    preferred_args: Sequence[Any] = (),
) -> Any:
    attempts: list[tuple[tuple[Any, ...], JsonDict]] = []

    if preferred_args:
        attempts.append((tuple(preferred_args), {}))

    attempts.append(((), _filtered_kwargs(function, payload)))
    attempts.append(((dict(payload),), {}))
    attempts.append(((), dict(payload)))
    attempts.append(((), {}))

    errors: list[str] = []

    for args, kwargs in attempts:
        try:
            result = function(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result
        except TypeError as exc:
            errors.append(str(exc))
            continue

    raise TypeError("; ".join(errors) or f"Could not call backend function {function!r}")


def _filtered_kwargs(
    function: Callable[..., Any],
    payload: Mapping[str, Any],
) -> JsonDict:
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return dict(payload)

    parameters = list(signature.parameters.values())

    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return dict(payload)

    allowed = {
        parameter.name
        for parameter in parameters
        if parameter.kind
        in {
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }
    }

    return {key: value for key, value in payload.items() if key in allowed}


def _request_object(
    module: Any,
    class_name: str,
    payload: Mapping[str, Any],
) -> Any | None:
    request_class = getattr(module, class_name, None)

    if request_class is None:
        return None

    data = dict(payload)

    if hasattr(request_class, "__dataclass_fields__"):
        allowed = set(request_class.__dataclass_fields__)
        unknown = {key: value for key, value in data.items() if key not in allowed}
        data = {key: value for key, value in data.items() if key in allowed}

        if "extra" in allowed and "extra" not in data and unknown:
            data["extra"] = unknown

    try:
        return request_class(**data)
    except TypeError:
        try:
            return request_class(dict(payload))
        except TypeError:
            return None


def _result_from_backend(
    *,
    action: str,
    outcome: Any,
    payload: Mapping[str, Any],
    default_message: str,
    ok_default: bool = True,
) -> GuiActionResult:
    if isinstance(outcome, GuiActionResult):
        return outcome

    data = _normalize_backend_outcome(outcome)
    stdout = _pop_optional_str(data, "stdout")
    stderr = _pop_optional_str(data, "stderr")
    returncode = _pop_optional_int(data, "returncode")

    ok = bool(data.pop("ok", ok_default))

    if returncode not in (None, 0):
        ok = False

    message = str(
        data.pop(
            "message",
            data.pop("detail", default_message),
        )
    )

    instance_id = (
        data.get("instance_id")
        or data.get("KX_INSTANCE_ID")
        or _payload_instance_id(payload)
    )

    if instance_id is not None:
        instance_id = str(instance_id)

    return GuiActionResult(
        ok=ok,
        action=action,
        message=message,
        instance_id=instance_id,
        data=_json_safe(data),
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
    )


def _normalize_backend_outcome(outcome: Any) -> JsonDict:
    if outcome is None:
        return {}

    if isinstance(outcome, GuiActionResult):
        return outcome.to_dict()

    if isinstance(outcome, Mapping):
        return dict(outcome)

    if is_dataclass(outcome):
        return _json_safe(asdict(outcome))

    model_dump = getattr(outcome, "model_dump", None)
    if callable(model_dump):
        value = model_dump()
        return _json_safe(value if isinstance(value, Mapping) else {"result": value})

    dict_method = getattr(outcome, "dict", None)
    if callable(dict_method):
        value = dict_method()
        return _json_safe(value if isinstance(value, Mapping) else {"result": value})

    if isinstance(outcome, (list, tuple)):
        return {"items": _json_safe(list(outcome))}

    return {"result": _json_safe(outcome)}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)

    if hasattr(value, "value"):
        return value.value

    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}

    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]

    if isinstance(value, list):
        return [_json_safe(item) for item in value]

    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)

    if is_dataclass(value):
        return _json_safe(asdict(value))

    return value


def _pop_optional_str(data: JsonDict, key: str) -> str | None:
    value = data.pop(key, None)
    return None if value is None else str(value)


def _pop_optional_int(data: JsonDict, key: str) -> int | None:
    value = data.pop(key, None)

    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _import_module(module_name: str) -> Any:
    return importlib.import_module(module_name)


def _try_import_module(module_name: str) -> Any | None:
    try:
        return _import_module(module_name)
    except Exception:
        return None


__all__ = [
    "ACTION_ALIASES",
    "ACTION_DISPATCH_TABLE",
    "ACTION_HANDLERS",
    "ACTION_LABELS",
    "ACTION_ROUTES",
    "AGENT_ENDPOINTS",
    "BROWSER_LINK_ACTIONS",
    "BROWSER_ONLY_ACTIONS",
    "CLI_FALLBACKS",
    "CONTRACT_ACTIONS",
    "GuiActionResult",
    "KNOWN_ACTIONS",
    "dispatch_gui_action",
    "is_known_gui_action",
]