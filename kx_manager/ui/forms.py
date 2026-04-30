"""Form parsing and validation for the Konnaxion Capsule Manager GUI.

This module is now an orchestrator / compatibility facade.

It re-exports form constants, validation errors, helper functions, form models,
target-mode forms, action-form registry, and public parser functions from
smaller focused modules.

This module owns GUI form validation only. It does not execute actions, call
Docker, run shell commands, or mutate host state. Action execution belongs to
``kx_manager.ui.actions`` and Manager service wrappers.
"""

from __future__ import annotations

# ---------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------

from kx_manager.ui.form_errors import FormValidationError

# ---------------------------------------------------------------------
# Constants and canonical enum aliases
# ---------------------------------------------------------------------

from kx_manager.ui.form_constants import (
    CAPSULE_EXTENSION,
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_OUTPUT_DIR,
    DEFAULT_CAPSULE_VERSION,
    DEFAULT_CHANNEL,
    DEFAULT_INSTANCE_ID,
    DEFAULT_RUNTIME_ROOT,
    DEFAULT_SOURCE_DIR,
    DockerService,
    ExposureMode,
    FALSE_VALUES,
    NetworkProfile,
    SAFE_ID_CHARS,
    TRUE_VALUES,
)

# ---------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------

from kx_manager.ui.form_helpers import (
    _absolute_posix_path,
    _backup_id,
    _bool,
    _capsule_file,
    _capsule_id,
    _capsule_output_dir,
    _capsule_version,
    _coerce_enum,
    _computed_capsule_file,
    _creatable_dir,
    _docker_service,
    _enum_values,
    _existing_dir,
    _exposure_mode,
    _host,
    _instance_id,
    _int,
    _iso_datetime,
    _network_profile,
    _path,
    _payload,
    _raw,
    _reject_droplet_fields,
    _remote_capsule_dir_under_root,
    _safe_identifier,
    _target_mode,
    _text,
    _validate_profile_exposure,
    normalize_form_data,
)

# ---------------------------------------------------------------------
# Core/simple forms
# ---------------------------------------------------------------------

from kx_manager.ui.form_core import (
    CapsuleOutputFolderForm,
    EmptyForm,
    SourceFolderForm,
)

# ---------------------------------------------------------------------
# Capsule/build forms
# ---------------------------------------------------------------------

from kx_manager.ui.form_capsules import (
    BuildCapsuleForm,
    CapsuleLookupForm,
    ImportCapsuleForm,
    VerifyCapsuleForm,
    parse_build_form,
    parse_capsule_lookup_form,
    parse_import_capsule_form,
    parse_verify_capsule_form,
)

# ---------------------------------------------------------------------
# Instance/runtime forms
# ---------------------------------------------------------------------

from kx_manager.ui.form_instances import (
    ConfirmedInstanceActionForm,
    CreateInstanceForm,
    InstanceActionForm,
    LogsForm,
    OpenInstanceForm,
    RollbackForm,
    UpdateInstanceForm,
    parse_instance_form,
    parse_rollback_form,
)

# ---------------------------------------------------------------------
# Backup/restore forms
# ---------------------------------------------------------------------

from kx_manager.ui.form_backups import (
    BackupForm,
    BackupLookupForm,
    ListBackupsForm,
    RestoreForm,
    parse_backup_form,
    parse_restore_form,
)

# ---------------------------------------------------------------------
# Network forms
# ---------------------------------------------------------------------

from kx_manager.ui.form_network import (
    DisablePublicModeForm,
    NetworkProfileForm,
    parse_network_form,
)

# ---------------------------------------------------------------------
# Target/deploy forms
# ---------------------------------------------------------------------

from kx_manager.ui.form_targets import (
    DeployDropletForm,
    DeployIntranetForm,
    DeployLocalForm,
    DropletTargetForm,
    IntranetTargetForm,
    LocalTargetForm,
    TargetModeForm,
    TemporaryPublicTargetForm,
    parse_target_form,
)

# ---------------------------------------------------------------------
# Registry and public validation entrypoints
# ---------------------------------------------------------------------

from kx_manager.ui.form_registry import (
    ACTION_ALIASES,
    ACTION_FORM_MODELS,
    canonical_action_value,
    form_to_payload,
    is_known_action,
    parse_action_form,
    validate_action_payload,
)


__all__ = [
    # Errors
    "FormValidationError",

    # Constants and canonical enum aliases
    "CAPSULE_EXTENSION",
    "DEFAULT_CAPSULE_ID",
    "DEFAULT_CAPSULE_OUTPUT_DIR",
    "DEFAULT_CAPSULE_VERSION",
    "DEFAULT_CHANNEL",
    "DEFAULT_INSTANCE_ID",
    "DEFAULT_RUNTIME_ROOT",
    "DEFAULT_SOURCE_DIR",
    "DockerService",
    "ExposureMode",
    "FALSE_VALUES",
    "NetworkProfile",
    "SAFE_ID_CHARS",
    "TRUE_VALUES",

    # Public helpers
    "normalize_form_data",

    # Core/simple forms
    "CapsuleOutputFolderForm",
    "EmptyForm",
    "SourceFolderForm",

    # Capsule/build forms
    "BuildCapsuleForm",
    "CapsuleLookupForm",
    "ImportCapsuleForm",
    "VerifyCapsuleForm",
    "parse_build_form",
    "parse_capsule_lookup_form",
    "parse_import_capsule_form",
    "parse_verify_capsule_form",

    # Instance/runtime forms
    "ConfirmedInstanceActionForm",
    "CreateInstanceForm",
    "InstanceActionForm",
    "LogsForm",
    "OpenInstanceForm",
    "RollbackForm",
    "UpdateInstanceForm",
    "parse_instance_form",
    "parse_rollback_form",

    # Backup/restore forms
    "BackupForm",
    "BackupLookupForm",
    "ListBackupsForm",
    "RestoreForm",
    "parse_backup_form",
    "parse_restore_form",

    # Network forms
    "DisablePublicModeForm",
    "NetworkProfileForm",
    "parse_network_form",

    # Target/deploy forms
    "DeployDropletForm",
    "DeployIntranetForm",
    "DeployLocalForm",
    "DropletTargetForm",
    "IntranetTargetForm",
    "LocalTargetForm",
    "TargetModeForm",
    "TemporaryPublicTargetForm",
    "parse_target_form",

    # Registry / public validation
    "ACTION_ALIASES",
    "ACTION_FORM_MODELS",
    "canonical_action_value",
    "form_to_payload",
    "is_known_action",
    "parse_action_form",
    "validate_action_payload",
]