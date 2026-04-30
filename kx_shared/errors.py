"""
Canonical exception hierarchy for Konnaxion Capsule Manager.

This module is intentionally dependency-light so it can be imported by
kx_shared, kx_agent, kx_manager, kx_builder, and kx_cli without creating
circular imports.

All public errors expose:
- code: stable machine-readable error code
- message: operator/developer readable message
- details: optional structured context
- exit_code: suggested CLI/process exit code
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping


@dataclass(slots=True)
class KonnaxionError(Exception):
    """Base class for all expected Konnaxion errors."""

    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    code: ClassVar[str] = "KX_ERROR"
    exit_code: ClassVar[int] = 1
    http_status: ClassVar[int] = 500

    def __str__(self) -> str:
        if not self.details:
            return f"{self.code}: {self.message}"
        return f"{self.code}: {self.message} | details={dict(self.details)}"

    def to_dict(self) -> dict[str, Any]:
        """Return a stable API/CLI-safe representation of the error."""

        return {
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
            "exit_code": self.exit_code,
            "http_status": self.http_status,
        }


# ---------------------------------------------------------------------
# Configuration and validation
# ---------------------------------------------------------------------


@dataclass(slots=True)
class KonnaxionConfigError(KonnaxionError):
    """Invalid or missing Konnaxion configuration."""

    code: ClassVar[str] = "KX_CONFIG_ERROR"
    exit_code: ClassVar[int] = 2
    http_status: ClassVar[int] = 400


@dataclass(slots=True)
class MissingRequiredVariableError(KonnaxionConfigError):
    """A required environment/configuration variable is missing."""

    code: ClassVar[str] = "KX_MISSING_REQUIRED_VARIABLE"


@dataclass(slots=True)
class InvalidVariableError(KonnaxionConfigError):
    """A variable exists but has an invalid value."""

    code: ClassVar[str] = "KX_INVALID_VARIABLE"


@dataclass(slots=True)
class ValidationError(KonnaxionError):
    """Generic validation failure."""

    code: ClassVar[str] = "KX_VALIDATION_ERROR"
    exit_code: ClassVar[int] = 3
    http_status: ClassVar[int] = 422


@dataclass(slots=True)
class SchemaValidationError(ValidationError):
    """A document failed schema validation."""

    code: ClassVar[str] = "KX_SCHEMA_VALIDATION_ERROR"


# ---------------------------------------------------------------------
# Filesystem and paths
# ---------------------------------------------------------------------


@dataclass(slots=True)
class KonnaxionPathError(KonnaxionError):
    """Filesystem path error."""

    code: ClassVar[str] = "KX_PATH_ERROR"
    exit_code: ClassVar[int] = 4
    http_status: ClassVar[int] = 400


@dataclass(slots=True)
class UnsafePathError(KonnaxionPathError):
    """A path escapes an allowed Konnaxion root or is otherwise unsafe."""

    code: ClassVar[str] = "KX_UNSAFE_PATH"


@dataclass(slots=True)
class FileMissingError(KonnaxionPathError):
    """An expected file or directory does not exist."""

    code: ClassVar[str] = "KX_FILE_MISSING"
    http_status: ClassVar[int] = 404


@dataclass(slots=True)
class FileAlreadyExistsError(KonnaxionPathError):
    """A file or directory already exists and overwrite is not allowed."""

    code: ClassVar[str] = "KX_FILE_ALREADY_EXISTS"
    http_status: ClassVar[int] = 409


# ---------------------------------------------------------------------
# Capsules
# ---------------------------------------------------------------------


@dataclass(slots=True)
class CapsuleError(KonnaxionError):
    """Base class for capsule-related failures."""

    code: ClassVar[str] = "KX_CAPSULE_ERROR"
    exit_code: ClassVar[int] = 10
    http_status: ClassVar[int] = 400


@dataclass(slots=True)
class CapsuleFormatError(CapsuleError):
    """The capsule format, extension, archive, or root layout is invalid."""

    code: ClassVar[str] = "KX_CAPSULE_FORMAT_ERROR"


@dataclass(slots=True)
class CapsuleManifestError(CapsuleError):
    """The capsule manifest is missing, malformed, or inconsistent."""

    code: ClassVar[str] = "KX_CAPSULE_MANIFEST_ERROR"


@dataclass(slots=True)
class CapsuleChecksumError(CapsuleError):
    """Capsule checksums are missing or do not match."""

    code: ClassVar[str] = "KX_CAPSULE_CHECKSUM_ERROR"


@dataclass(slots=True)
class CapsuleSignatureError(CapsuleError):
    """Capsule signature verification failed."""

    code: ClassVar[str] = "KX_CAPSULE_SIGNATURE_ERROR"


@dataclass(slots=True)
class UnsignedCapsuleError(CapsuleSignatureError):
    """Unsigned capsules are not allowed."""

    code: ClassVar[str] = "KX_UNSIGNED_CAPSULE"


@dataclass(slots=True)
class CapsuleImportError(CapsuleError):
    """Capsule import failed."""

    code: ClassVar[str] = "KX_CAPSULE_IMPORT_ERROR"


# ---------------------------------------------------------------------
# Instances and lifecycle
# ---------------------------------------------------------------------


@dataclass(slots=True)
class InstanceError(KonnaxionError):
    """Base class for Konnaxion Instance failures."""

    code: ClassVar[str] = "KX_INSTANCE_ERROR"
    exit_code: ClassVar[int] = 20
    http_status: ClassVar[int] = 400


@dataclass(slots=True)
class InstanceNotFoundError(InstanceError):
    """The requested instance does not exist."""

    code: ClassVar[str] = "KX_INSTANCE_NOT_FOUND"
    http_status: ClassVar[int] = 404


@dataclass(slots=True)
class InstanceAlreadyExistsError(InstanceError):
    """The requested instance already exists."""

    code: ClassVar[str] = "KX_INSTANCE_ALREADY_EXISTS"
    http_status: ClassVar[int] = 409


@dataclass(slots=True)
class InvalidInstanceStateError(InstanceError):
    """An operation is not valid for the current instance state."""

    code: ClassVar[str] = "KX_INVALID_INSTANCE_STATE"
    http_status: ClassVar[int] = 409


@dataclass(slots=True)
class InstanceStartError(InstanceError):
    """Instance startup failed."""

    code: ClassVar[str] = "KX_INSTANCE_START_ERROR"


@dataclass(slots=True)
class InstanceStopError(InstanceError):
    """Instance stop failed."""

    code: ClassVar[str] = "KX_INSTANCE_STOP_ERROR"


@dataclass(slots=True)
class InstanceUpdateError(InstanceError):
    """Instance update failed."""

    code: ClassVar[str] = "KX_INSTANCE_UPDATE_ERROR"


# ---------------------------------------------------------------------
# Security Gate and runtime policy
# ---------------------------------------------------------------------


@dataclass(slots=True)
class SecurityError(KonnaxionError):
    """Base class for security-related failures."""

    code: ClassVar[str] = "KX_SECURITY_ERROR"
    exit_code: ClassVar[int] = 30
    http_status: ClassVar[int] = 403


@dataclass(slots=True)
class SecurityGateError(SecurityError):
    """Security Gate failed or could not complete."""

    code: ClassVar[str] = "KX_SECURITY_GATE_ERROR"


@dataclass(slots=True)
class SecurityGateBlockingError(SecurityGateError):
    """A blocking Security Gate check failed and startup must stop."""

    code: ClassVar[str] = "KX_SECURITY_GATE_BLOCKING"
    exit_code: ClassVar[int] = 31


@dataclass(slots=True)
class RuntimePolicyError(SecurityError):
    """Runtime policy validation failed."""

    code: ClassVar[str] = "KX_RUNTIME_POLICY_ERROR"


@dataclass(slots=True)
class ForbiddenPublicPortError(RuntimePolicyError):
    """A forbidden internal service port would be exposed."""

    code: ClassVar[str] = "KX_FORBIDDEN_PUBLIC_PORT"


@dataclass(slots=True)
class ForbiddenDockerSocketMountError(RuntimePolicyError):
    """A container attempts to mount the Docker socket."""

    code: ClassVar[str] = "KX_FORBIDDEN_DOCKER_SOCKET_MOUNT"


@dataclass(slots=True)
class ForbiddenPrivilegedContainerError(RuntimePolicyError):
    """A container attempts to run in privileged mode."""

    code: ClassVar[str] = "KX_FORBIDDEN_PRIVILEGED_CONTAINER"


@dataclass(slots=True)
class ForbiddenHostNetworkError(RuntimePolicyError):
    """A container attempts to use host networking."""

    code: ClassVar[str] = "KX_FORBIDDEN_HOST_NETWORK"


@dataclass(slots=True)
class UnknownImageError(RuntimePolicyError):
    """A runtime image is not present in the allowed image set."""

    code: ClassVar[str] = "KX_UNKNOWN_IMAGE"


# ---------------------------------------------------------------------
# Network profiles and exposure
# ---------------------------------------------------------------------


@dataclass(slots=True)
class NetworkError(KonnaxionError):
    """Base class for network-profile failures."""

    code: ClassVar[str] = "KX_NETWORK_ERROR"
    exit_code: ClassVar[int] = 40
    http_status: ClassVar[int] = 400


@dataclass(slots=True)
class InvalidNetworkProfileError(NetworkError):
    """The requested network profile is not canonical or not supported."""

    code: ClassVar[str] = "KX_INVALID_NETWORK_PROFILE"


@dataclass(slots=True)
class InvalidExposureModeError(NetworkError):
    """The requested exposure mode is not canonical or not supported."""

    code: ClassVar[str] = "KX_INVALID_EXPOSURE_MODE"


@dataclass(slots=True)
class PublicExposureRequiresExpirationError(NetworkError):
    """Temporary public exposure was requested without an expiration."""

    code: ClassVar[str] = "KX_PUBLIC_EXPOSURE_REQUIRES_EXPIRATION"


# ---------------------------------------------------------------------
# Docker Compose runtime
# ---------------------------------------------------------------------


@dataclass(slots=True)
class RuntimeError(KonnaxionError):
    """Base class for Docker Compose runtime failures."""

    code: ClassVar[str] = "KX_RUNTIME_ERROR"
    exit_code: ClassVar[int] = 50
    http_status: ClassVar[int] = 500


@dataclass(slots=True)
class ComposeGenerationError(RuntimeError):
    """Runtime docker-compose generation failed."""

    code: ClassVar[str] = "KX_COMPOSE_GENERATION_ERROR"


@dataclass(slots=True)
class DockerCommandError(RuntimeError):
    """A controlled Docker command failed."""

    code: ClassVar[str] = "KX_DOCKER_COMMAND_ERROR"


@dataclass(slots=True)
class MigrationError(RuntimeError):
    """Application migration failed."""

    code: ClassVar[str] = "KX_MIGRATION_ERROR"


@dataclass(slots=True)
class HealthcheckError(RuntimeError):
    """One or more healthchecks failed."""

    code: ClassVar[str] = "KX_HEALTHCHECK_ERROR"


# ---------------------------------------------------------------------
# Backups, restores, and rollbacks
# ---------------------------------------------------------------------


@dataclass(slots=True)
class BackupError(KonnaxionError):
    """Base class for backup-related failures."""

    code: ClassVar[str] = "KX_BACKUP_ERROR"
    exit_code: ClassVar[int] = 60
    http_status: ClassVar[int] = 500


@dataclass(slots=True)
class BackupCreateError(BackupError):
    """Backup creation failed."""

    code: ClassVar[str] = "KX_BACKUP_CREATE_ERROR"


@dataclass(slots=True)
class BackupVerifyError(BackupError):
    """Backup verification failed."""

    code: ClassVar[str] = "KX_BACKUP_VERIFY_ERROR"


@dataclass(slots=True)
class BackupNotFoundError(BackupError):
    """The requested backup does not exist."""

    code: ClassVar[str] = "KX_BACKUP_NOT_FOUND"
    http_status: ClassVar[int] = 404


@dataclass(slots=True)
class RestoreError(KonnaxionError):
    """Base class for restore-related failures."""

    code: ClassVar[str] = "KX_RESTORE_ERROR"
    exit_code: ClassVar[int] = 70
    http_status: ClassVar[int] = 500


@dataclass(slots=True)
class RestorePreflightError(RestoreError):
    """Restore preflight failed."""

    code: ClassVar[str] = "KX_RESTORE_PREFLIGHT_ERROR"


@dataclass(slots=True)
class RestoreApplyError(RestoreError):
    """Restore application failed."""

    code: ClassVar[str] = "KX_RESTORE_APPLY_ERROR"


@dataclass(slots=True)
class RollbackError(KonnaxionError):
    """Base class for rollback-related failures."""

    code: ClassVar[str] = "KX_ROLLBACK_ERROR"
    exit_code: ClassVar[int] = 80
    http_status: ClassVar[int] = 500


@dataclass(slots=True)
class RollbackApplyError(RollbackError):
    """Rollback application failed."""

    code: ClassVar[str] = "KX_ROLLBACK_APPLY_ERROR"


# ---------------------------------------------------------------------
# Agent and Manager API
# ---------------------------------------------------------------------


@dataclass(slots=True)
class AgentError(KonnaxionError):
    """Base class for Konnaxion Agent failures."""

    code: ClassVar[str] = "KX_AGENT_ERROR"
    exit_code: ClassVar[int] = 90
    http_status: ClassVar[int] = 500


@dataclass(slots=True)
class AgentUnavailableError(AgentError):
    """Konnaxion Agent is unavailable."""

    code: ClassVar[str] = "KX_AGENT_UNAVAILABLE"
    http_status: ClassVar[int] = 503


@dataclass(slots=True)
class AgentActionNotAllowedError(AgentError):
    """The requested Agent action is not allowlisted."""

    code: ClassVar[str] = "KX_AGENT_ACTION_NOT_ALLOWED"
    http_status: ClassVar[int] = 403


@dataclass(slots=True)
class ManagerApiError(KonnaxionError):
    """Base class for Konnaxion Capsule Manager API failures."""

    code: ClassVar[str] = "KX_MANAGER_API_ERROR"
    exit_code: ClassVar[int] = 100
    http_status: ClassVar[int] = 500


@dataclass(slots=True)
class AuthenticationError(ManagerApiError):
    """Authentication failed."""

    code: ClassVar[str] = "KX_AUTHENTICATION_ERROR"
    http_status: ClassVar[int] = 401


@dataclass(slots=True)
class AuthorizationError(ManagerApiError):
    """Authorization failed."""

    code: ClassVar[str] = "KX_AUTHORIZATION_ERROR"
    http_status: ClassVar[int] = 403


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def as_error_payload(error: BaseException) -> dict[str, Any]:
    """Convert expected and unexpected exceptions to a stable payload."""

    if isinstance(error, KonnaxionError):
        return error.to_dict()

    return {
        "code": "KX_UNEXPECTED_ERROR",
        "message": str(error) or error.__class__.__name__,
        "details": {"type": error.__class__.__name__},
        "exit_code": 1,
        "http_status": 500,
    }


def exit_code_for(error: BaseException) -> int:
    """Return the CLI/process exit code for an exception."""

    if isinstance(error, KonnaxionError):
        return error.exit_code
    return 1


__all__ = [
    "AgentActionNotAllowedError",
    "AgentError",
    "AgentUnavailableError",
    "AuthenticationError",
    "AuthorizationError",
    "BackupCreateError",
    "BackupError",
    "BackupNotFoundError",
    "BackupVerifyError",
    "CapsuleChecksumError",
    "CapsuleError",
    "CapsuleFormatError",
    "CapsuleImportError",
    "CapsuleManifestError",
    "CapsuleSignatureError",
    "ComposeGenerationError",
    "DockerCommandError",
    "FileAlreadyExistsError",
    "FileMissingError",
    "ForbiddenDockerSocketMountError",
    "ForbiddenHostNetworkError",
    "ForbiddenPrivilegedContainerError",
    "ForbiddenPublicPortError",
    "HealthcheckError",
    "InstanceAlreadyExistsError",
    "InstanceError",
    "InstanceNotFoundError",
    "InstanceStartError",
    "InstanceStopError",
    "InstanceUpdateError",
    "InvalidExposureModeError",
    "InvalidInstanceStateError",
    "InvalidNetworkProfileError",
    "InvalidVariableError",
    "KonnaxionConfigError",
    "KonnaxionError",
    "KonnaxionPathError",
    "ManagerApiError",
    "MigrationError",
    "MissingRequiredVariableError",
    "NetworkError",
    "PublicExposureRequiresExpirationError",
    "RestoreApplyError",
    "RestoreError",
    "RestorePreflightError",
    "RollbackApplyError",
    "RollbackError",
    "RuntimeError",
    "RuntimePolicyError",
    "SchemaValidationError",
    "SecurityError",
    "SecurityGateBlockingError",
    "SecurityGateError",
    "UnknownImageError",
    "UnsafePathError",
    "ValidationError",
    "as_error_payload",
    "exit_code_for",
    "UnsignedCapsuleError",
]
