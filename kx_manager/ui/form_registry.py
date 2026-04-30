# kx_manager/ui/form_registry.py

"""Action form registry for the Konnaxion Capsule Manager GUI.

This module maps canonical GUI action names to framework-neutral form models.

It validates and normalizes submitted GUI payloads only. It must not execute
actions, call Docker, run shell commands, mutate host state, or contact the
Agent. Action execution belongs to ``kx_manager.ui.actions`` and approved
Manager service wrappers.
"""

from __future__ import annotations

from typing import Any, Mapping

from kx_manager.ui.form_backups import (
    BackupForm,
    BackupLookupForm,
    ListBackupsForm,
    RestoreForm,
)
from kx_manager.ui.form_capsules import (
    BuildCapsuleForm,
    CapsuleLookupForm,
    ImportCapsuleForm,
    VerifyCapsuleForm,
)
from kx_manager.ui.form_core import (
    CapsuleOutputFolderForm,
    EmptyForm,
    SourceFolderForm,
)
from kx_manager.ui.form_errors import FormValidationError
from kx_manager.ui.form_helpers import _payload, normalize_form_data
from kx_manager.ui.form_instances import (
    ConfirmedInstanceActionForm,
    CreateInstanceForm,
    InstanceActionForm,
    LogsForm,
    OpenInstanceForm,
    RollbackForm,
    UpdateInstanceForm,
)
from kx_manager.ui.form_network import (
    DisablePublicModeForm,
    NetworkProfileForm,
)
from kx_manager.ui.form_targets import (
    DeployDropletForm,
    DeployIntranetForm,
    DeployLocalForm,
    DropletTargetForm,
    IntranetTargetForm,
    LocalTargetForm,
    TemporaryPublicTargetForm,
)


ACTION_ALIASES: dict[str, str] = {
    "open_runtime": "open_instance",
}


ACTION_FORM_MODELS: dict[str, type[Any]] = {
    "check_manager": EmptyForm,
    "check_agent": EmptyForm,
    "select_source_folder": SourceFolderForm,
    "select_capsule_output_folder": CapsuleOutputFolderForm,
    "build_capsule": BuildCapsuleForm,
    "rebuild_capsule": BuildCapsuleForm,
    "verify_capsule": VerifyCapsuleForm,
    "import_capsule": ImportCapsuleForm,
    "list_capsules": EmptyForm,
    "view_capsule": CapsuleLookupForm,
    "create_instance": CreateInstanceForm,
    "update_instance": UpdateInstanceForm,
    "start_instance": InstanceActionForm,
    "stop_instance": ConfirmedInstanceActionForm,
    "restart_instance": InstanceActionForm,
    "instance_status": InstanceActionForm,
    "view_logs": LogsForm,
    "view_health": InstanceActionForm,
    "open_instance": OpenInstanceForm,
    "rollback_instance": RollbackForm,
    "create_backup": BackupForm,
    "list_backups": ListBackupsForm,
    "verify_backup": BackupLookupForm,
    "restore_backup": RestoreForm,
    "restore_backup_new": RestoreForm,
    "test_restore_backup": RestoreForm,
    "run_security_check": InstanceActionForm,
    "set_network_profile": NetworkProfileForm,
    "disable_public_mode": DisablePublicModeForm,
    "set_target_local": LocalTargetForm,
    "set_target_intranet": IntranetTargetForm,
    "set_target_droplet": DropletTargetForm,
    "set_target_temporary_public": TemporaryPublicTargetForm,
    "deploy_local": DeployLocalForm,
    "deploy_intranet": DeployIntranetForm,
    "deploy_droplet": DeployDropletForm,
    "check_droplet_agent": DropletTargetForm,
    "copy_capsule_to_droplet": DeployDropletForm,
    "start_droplet_instance": DropletTargetForm,
    "open_manager_docs": EmptyForm,
    "open_agent_docs": EmptyForm,
}


def canonical_action_value(action: Any) -> str:
    """Return the canonical string value for a GUI action."""

    raw_value = str(getattr(action, "value", action)).strip()

    if not raw_value:
        raise FormValidationError("action is required.", field="action")

    return ACTION_ALIASES.get(raw_value, raw_value)


def is_known_action(action: Any) -> bool:
    """Return whether an action has a registered form model."""

    try:
        action_value = canonical_action_value(action)
    except FormValidationError:
        return False

    return action_value in ACTION_FORM_MODELS


def parse_action_form(action: Any, data: Mapping[str, Any] | None = None) -> Any:
    """Parse and validate a GUI action payload into the matching form model."""

    action_value = canonical_action_value(action)
    form_model = ACTION_FORM_MODELS.get(action_value)

    if form_model is None:
        raise FormValidationError(
            f"Unknown or unsupported GUI action: {action_value}",
            field="action",
        )

    normalized = normalize_form_data(data or {})
    return form_model.from_mapping(normalized)


def form_to_payload(form: Any) -> dict[str, Any]:
    """Convert a parsed form model to a JSON-safe action payload."""

    if hasattr(form, "to_payload"):
        payload = form.to_payload()
        if isinstance(payload, Mapping):
            return dict(payload)

    return _payload(form)


def validate_action_payload(
    action_or_data: Any,
    data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a GUI action payload.

    Supported call styles:

    ``validate_action_payload("set_network_profile", payload)``

    ``validate_action_payload({"action": "set_network_profile", ...})``
    """

    if data is None:
        if not isinstance(action_or_data, Mapping):
            raise FormValidationError(
                "action payload mapping is required.",
                field="action",
            )

        normalized = normalize_form_data(action_or_data)
        raw_action = normalized.get("action")

        if raw_action in {None, ""}:
            raise FormValidationError("action is required.", field="action")

        action_value = canonical_action_value(raw_action)
        payload_data = normalized
    else:
        action_value = canonical_action_value(action_or_data)
        payload_data = normalize_form_data(data)

    form = parse_action_form(action_value, payload_data)

    return {
        "action": action_value,
        **form_to_payload(form),
    }


__all__ = [
    "ACTION_ALIASES",
    "ACTION_FORM_MODELS",
    "canonical_action_value",
    "form_to_payload",
    "is_known_action",
    "parse_action_form",
    "validate_action_payload",
]