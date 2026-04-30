"""
Rollback orchestration for Konnaxion instances.

Rollback is an Agent-owned operation because it changes the active capsule,
runtime state, and optionally data restored from backup artifacts.

This module keeps rollback conservative:

- Validate target capsule before switching pointers.
- Create or require a safety backup before destructive restore workflows.
- Stop runtime before repointing.
- Re-run Security Gate and healthchecks after rollback.
- Never execute shell strings; all commands are argv lists.
- Audit every state-changing operation.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from kx_agent.audit import (
    AuditCategory,
    AuditLogger,
    AuditOutcome,
    AuditSeverity,
    audit_agent_action,
    audit_instance_state_change,
    get_audit_logger,
)
from kx_shared.konnaxion_constants import (
    CAPSULE_EXTENSION,
    KX_CAPSULES_DIR,
    KX_INSTANCES_DIR,
    KX_ROOT,
    RollbackStatus,
    InstanceState,
    capsule_path,
    instance_compose_file,
    instance_root,
    instance_state_dir,
)
from kx_shared.types import (
    BackupID,
    CapsuleID,
    CapsuleVersion,
    InstanceID,
    RollbackID,
    RollbackPlan,
)


ROLLBACK_SCHEMA_VERSION = "kx-rollback/v1"

ROLLBACK_STATE_FILENAME = "rollback.json"
CURRENT_CAPSULE_POINTER = "current_capsule.json"
PREVIOUS_CAPSULE_POINTER = "previous_capsule.json"
ROLLBACK_HISTORY_FILENAME = "rollback-history.jsonl"

DEFAULT_COMMAND_TIMEOUT_SECONDS = 120


class RollbackError(RuntimeError):
    """Base rollback error."""


class RollbackSafetyError(RollbackError):
    """Rollback rejected by safety checks."""


class RollbackCommandError(RollbackError):
    """Rollback command failed."""


class RollbackStep(StrEnum):
    """Ordered rollback operation steps."""

    PREFLIGHT = "preflight"
    STOP_RUNTIME = "stop_runtime"
    REPOINT_CAPSULE = "repoint_capsule"
    RESTORE_DATA = "restore_data"
    START_RUNTIME = "start_runtime"
    RUN_MIGRATIONS = "run_migrations"
    RUN_SECURITY_GATE = "run_security_gate"
    RUN_HEALTHCHECKS = "run_healthchecks"
    FINALIZE = "finalize"


@dataclass(frozen=True, slots=True)
class CapsulePointer:
    """Pointer to the active or previous capsule for an instance."""

    capsule_id: CapsuleID
    capsule_version: CapsuleVersion
    capsule_file: Path
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RollbackCommand:
    """One safe command represented as argv, never as shell text."""

    argv: tuple[str, ...]
    description: str
    cwd: Path | None = None
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class RollbackCommandResult:
    """Result of running one rollback command."""

    command: RollbackCommand
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True, slots=True)
class RollbackStepResult:
    """Result of one rollback step."""

    step: RollbackStep
    status: RollbackStatus
    message: str
    started_at: datetime
    completed_at: datetime
    command_results: tuple[RollbackCommandResult, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RollbackContext:
    """Resolved filesystem and runtime context for a rollback."""

    rollback_id: RollbackID
    instance_id: InstanceID
    target_capsule_id: CapsuleID
    target_capsule_version: CapsuleVersion
    target_capsule_file: Path
    current_pointer_file: Path
    previous_pointer_file: Path
    rollback_state_file: Path
    rollback_history_file: Path
    compose_file: Path
    state_dir: Path
    restore_data: bool = False
    backup_id: BackupID | None = None
    requested_by: str = "system"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class RollbackResult:
    """Final rollback result."""

    rollback_id: RollbackID
    instance_id: InstanceID
    status: RollbackStatus
    target_capsule_id: CapsuleID
    target_capsule_version: CapsuleVersion
    started_at: datetime
    completed_at: datetime
    steps: tuple[RollbackStepResult, ...]
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == RollbackStatus.COMPLETED


SecurityGateRunner = Callable[[InstanceID], Any]
HealthcheckRunner = Callable[[InstanceID], Any]
DataRestoreRunner = Callable[[InstanceID, BackupID], Any]
MigrationRunner = Callable[[InstanceID], Any]


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""

    return datetime.now(UTC)


def new_rollback_id(instance_id: InstanceID | str) -> RollbackID:
    """Create a rollback id scoped to an instance."""

    timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return RollbackID(f"{instance_id}_{timestamp}_rollback_{suffix}")


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    return str(value)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        default=_json_default,
    )
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=str(path.parent),
        encoding="utf-8",
        prefix=f".{path.name}.",
    ) as tmp:
        tmp.write(encoded)
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)

    tmp_path.replace(path)


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        default=_json_default,
        separators=(",", ":"),
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RollbackError(f"invalid JSON object in {path}")
    return loaded


def _safe_resolve_under(path: Path, root: Path) -> Path:
    resolved_path = path.expanduser().resolve(strict=False)
    resolved_root = root.expanduser().resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise RollbackSafetyError(f"path must be under {resolved_root}: {resolved_path}") from exc
    return resolved_path


def validate_capsule_file(path: Path) -> Path:
    """Validate target capsule file path and extension."""

    resolved = _safe_resolve_under(path, KX_CAPSULES_DIR)
    if resolved.suffix != CAPSULE_EXTENSION:
        raise RollbackSafetyError(f"capsule file must end with {CAPSULE_EXTENSION}: {resolved}")
    if not resolved.exists():
        raise FileNotFoundError(f"target capsule does not exist: {resolved}")
    if not resolved.is_file():
        raise RollbackSafetyError(f"target capsule is not a file: {resolved}")
    return resolved


def resolve_target_capsule_file(
    capsule_id: CapsuleID | str,
    explicit_path: Path | str | None = None,
) -> Path:
    """Resolve the target capsule file from capsule id or explicit path."""

    if explicit_path is not None:
        return validate_capsule_file(Path(explicit_path))

    return validate_capsule_file(capsule_path(str(capsule_id)))


def pointer_to_dict(pointer: CapsulePointer) -> dict[str, Any]:
    """Serialize a capsule pointer."""

    return {
        "schema_version": ROLLBACK_SCHEMA_VERSION,
        "capsule_id": str(pointer.capsule_id),
        "capsule_version": str(pointer.capsule_version),
        "capsule_file": str(pointer.capsule_file),
        "updated_at": pointer.updated_at,
    }


def pointer_from_dict(payload: Mapping[str, Any]) -> CapsulePointer:
    """Deserialize a capsule pointer."""

    return CapsulePointer(
        capsule_id=CapsuleID(str(payload["capsule_id"])),
        capsule_version=CapsuleVersion(str(payload["capsule_version"])),
        capsule_file=Path(str(payload["capsule_file"])),
        updated_at=datetime.fromisoformat(str(payload["updated_at"]).replace("Z", "+00:00")),
    )


def read_capsule_pointer(path: Path) -> CapsulePointer | None:
    """Read a capsule pointer file if it exists."""

    payload = _read_json(path)
    if payload is None:
        return None
    return pointer_from_dict(payload)


def write_capsule_pointer(path: Path, pointer: CapsulePointer) -> None:
    """Write a capsule pointer atomically."""

    _atomic_write_json(path, pointer_to_dict(pointer))


def build_rollback_context(
    *,
    instance_id: InstanceID | str,
    target_capsule_id: CapsuleID | str,
    target_capsule_version: CapsuleVersion | str,
    target_capsule_file: Path | str | None = None,
    rollback_id: RollbackID | str | None = None,
    restore_data: bool = False,
    backup_id: BackupID | str | None = None,
    requested_by: str = "system",
) -> RollbackContext:
    """Build a fully resolved rollback context."""

    instance = InstanceID(str(instance_id))
    capsule = CapsuleID(str(target_capsule_id))
    capsule_version = CapsuleVersion(str(target_capsule_version))
    resolved_state_dir = instance_state_dir(str(instance))
    resolved_target_capsule_file = resolve_target_capsule_file(capsule, target_capsule_file)

    if restore_data and backup_id is None:
        raise RollbackSafetyError("restore_data rollback requires backup_id")

    return RollbackContext(
        rollback_id=RollbackID(str(rollback_id)) if rollback_id else new_rollback_id(instance),
        instance_id=instance,
        target_capsule_id=capsule,
        target_capsule_version=capsule_version,
        target_capsule_file=resolved_target_capsule_file,
        current_pointer_file=resolved_state_dir / CURRENT_CAPSULE_POINTER,
        previous_pointer_file=resolved_state_dir / PREVIOUS_CAPSULE_POINTER,
        rollback_state_file=resolved_state_dir / ROLLBACK_STATE_FILENAME,
        rollback_history_file=resolved_state_dir / ROLLBACK_HISTORY_FILENAME,
        compose_file=instance_compose_file(str(instance)),
        state_dir=resolved_state_dir,
        restore_data=restore_data,
        backup_id=BackupID(str(backup_id)) if backup_id is not None else None,
        requested_by=requested_by,
    )


def validate_rollback_context(context: RollbackContext) -> None:
    """Validate rollback context before running commands."""

    _safe_resolve_under(context.state_dir, KX_INSTANCES_DIR)
    _safe_resolve_under(context.current_pointer_file, KX_INSTANCES_DIR)
    _safe_resolve_under(context.previous_pointer_file, KX_INSTANCES_DIR)
    validate_capsule_file(context.target_capsule_file)

    if context.restore_data and context.backup_id is None:
        raise RollbackSafetyError("restore_data rollback requires backup_id")

    if str(context.target_capsule_id).strip() == "":
        raise RollbackSafetyError("target_capsule_id must not be empty")

    if str(context.target_capsule_version).strip() == "":
        raise RollbackSafetyError("target_capsule_version must not be empty")


def build_stop_runtime_commands(context: RollbackContext) -> tuple[RollbackCommand, ...]:
    """Build safe commands to stop the existing runtime."""

    if not context.compose_file.exists():
        return ()

    return (
        RollbackCommand(
            argv=("docker", "compose", "-f", str(context.compose_file), "down"),
            description="Stop current Konnaxion runtime",
            cwd=context.state_dir,
        ),
    )


def build_start_runtime_commands(context: RollbackContext) -> tuple[RollbackCommand, ...]:
    """Build safe commands to start the runtime after rollback."""

    if not context.compose_file.exists():
        return ()

    return (
        RollbackCommand(
            argv=("docker", "compose", "-f", str(context.compose_file), "up", "-d"),
            description="Start rolled-back Konnaxion runtime",
            cwd=context.state_dir,
        ),
    )


def run_command(command: RollbackCommand, *, dry_run: bool = False) -> RollbackCommandResult:
    """Run one rollback command without shell expansion."""

    if dry_run:
        return RollbackCommandResult(
            command=command,
            returncode=0,
            stdout="dry-run",
            stderr="",
        )

    completed = subprocess.run(
        command.argv,
        cwd=str(command.cwd) if command.cwd else None,
        check=False,
        capture_output=True,
        text=True,
        timeout=command.timeout_seconds,
    )
    return RollbackCommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_commands(
    commands: Sequence[RollbackCommand],
    *,
    dry_run: bool = False,
) -> tuple[RollbackCommandResult, ...]:
    """Run commands in order, stopping at first failure."""

    results: list[RollbackCommandResult] = []
    for command in commands:
        result = run_command(command, dry_run=dry_run)
        results.append(result)
        if not result.ok:
            raise RollbackCommandError(
                f"command failed: {' '.join(command.argv)}: {result.stderr.strip()}"
            )
    return tuple(results)


def write_rollback_state(
    context: RollbackContext,
    status: RollbackStatus,
    *,
    metadata: Mapping[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Write current rollback status to instance state directory."""

    payload = {
        "schema_version": ROLLBACK_SCHEMA_VERSION,
        "rollback_id": str(context.rollback_id),
        "instance_id": str(context.instance_id),
        "status": status,
        "target_capsule_id": str(context.target_capsule_id),
        "target_capsule_version": str(context.target_capsule_version),
        "target_capsule_file": str(context.target_capsule_file),
        "restore_data": context.restore_data,
        "backup_id": str(context.backup_id) if context.backup_id is not None else None,
        "requested_by": context.requested_by,
        "updated_at": utc_now(),
        "metadata": dict(metadata or {}),
        "error": error,
    }
    _atomic_write_json(context.rollback_state_file, payload)
    _append_jsonl(context.rollback_history_file, payload)


def _make_step_result(
    step: RollbackStep,
    status: RollbackStatus,
    message: str,
    started_at: datetime,
    *,
    command_results: Sequence[RollbackCommandResult] = (),
    metadata: Mapping[str, Any] | None = None,
) -> RollbackStepResult:
    return RollbackStepResult(
        step=step,
        status=status,
        message=message,
        started_at=started_at,
        completed_at=utc_now(),
        command_results=tuple(command_results),
        metadata=dict(metadata or {}),
    )


def _audit(
    logger: AuditLogger,
    *,
    context: RollbackContext,
    outcome: AuditOutcome,
    message: str,
    severity: AuditSeverity = AuditSeverity.INFO,
    metadata: Mapping[str, Any] | None = None,
    error: BaseException | str | None = None,
) -> None:
    audit_agent_action(
        action="rollback_instance",
        category=AuditCategory.ROLLBACK,
        outcome=outcome,
        severity=severity,
        message=message,
        instance_id=context.instance_id,
        capsule_id=context.target_capsule_id,
        correlation_id=str(context.rollback_id),
        metadata={
            "rollback_id": str(context.rollback_id),
            "target_capsule_version": str(context.target_capsule_version),
            "restore_data": context.restore_data,
            "backup_id": str(context.backup_id) if context.backup_id is not None else None,
            **dict(metadata or {}),
        },
        error=error,
        logger=logger,
    )


def preflight_rollback(context: RollbackContext) -> RollbackStepResult:
    """Run local rollback preflight checks."""

    started_at = utc_now()
    validate_rollback_context(context)

    current_pointer = read_capsule_pointer(context.current_pointer_file)

    metadata = {
        "target_capsule_file": str(context.target_capsule_file),
        "current_capsule_id": str(current_pointer.capsule_id) if current_pointer else None,
        "current_capsule_version": str(current_pointer.capsule_version) if current_pointer else None,
        "compose_file_exists": context.compose_file.exists(),
    }

    return _make_step_result(
        RollbackStep.PREFLIGHT,
        RollbackStatus.RUNNING,
        "Rollback preflight passed",
        started_at,
        metadata=metadata,
    )


def stop_runtime(context: RollbackContext, *, dry_run: bool = False) -> RollbackStepResult:
    """Stop the current runtime if a compose file exists."""

    started_at = utc_now()
    commands = build_stop_runtime_commands(context)
    results = run_commands(commands, dry_run=dry_run) if commands else ()

    return _make_step_result(
        RollbackStep.STOP_RUNTIME,
        RollbackStatus.RUNNING,
        "Runtime stopped" if commands else "No runtime compose file found; stop skipped",
        started_at,
        command_results=results,
        metadata={"commands": len(commands)},
    )


def repoint_capsule(context: RollbackContext, *, dry_run: bool = False) -> RollbackStepResult:
    """Repoint instance current capsule to target capsule."""

    started_at = utc_now()
    old_pointer = read_capsule_pointer(context.current_pointer_file)

    new_pointer = CapsulePointer(
        capsule_id=context.target_capsule_id,
        capsule_version=context.target_capsule_version,
        capsule_file=context.target_capsule_file,
        updated_at=utc_now(),
    )

    if not dry_run:
        if old_pointer is not None:
            write_capsule_pointer(context.previous_pointer_file, old_pointer)
        write_capsule_pointer(context.current_pointer_file, new_pointer)

    return _make_step_result(
        RollbackStep.REPOINT_CAPSULE,
        RollbackStatus.CAPSULE_REPOINTED,
        "Capsule pointer repointed",
        started_at,
        metadata={
            "old_capsule_id": str(old_pointer.capsule_id) if old_pointer else None,
            "old_capsule_version": str(old_pointer.capsule_version) if old_pointer else None,
            "new_capsule_id": str(new_pointer.capsule_id),
            "new_capsule_version": str(new_pointer.capsule_version),
            "dry_run": dry_run,
        },
    )


def restore_data(
    context: RollbackContext,
    *,
    restore_runner: DataRestoreRunner | None = None,
    dry_run: bool = False,
) -> RollbackStepResult:
    """Optionally restore instance data from backup."""

    started_at = utc_now()

    if not context.restore_data:
        return _make_step_result(
            RollbackStep.RESTORE_DATA,
            RollbackStatus.CAPSULE_REPOINTED,
            "Data restore skipped",
            started_at,
            metadata={"restore_data": False},
        )

    if context.backup_id is None:
        raise RollbackSafetyError("restore_data rollback requires backup_id")

    if restore_runner is not None and not dry_run:
        restore_runner(context.instance_id, context.backup_id)

    return _make_step_result(
        RollbackStep.RESTORE_DATA,
        RollbackStatus.DATA_RESTORED,
        "Data restored from backup" if not dry_run else "Data restore dry-run completed",
        started_at,
        metadata={
            "restore_data": True,
            "backup_id": str(context.backup_id),
            "runner_used": restore_runner is not None,
            "dry_run": dry_run,
        },
    )


def start_runtime(context: RollbackContext, *, dry_run: bool = False) -> RollbackStepResult:
    """Start runtime after capsule repoint."""

    started_at = utc_now()
    commands = build_start_runtime_commands(context)
    results = run_commands(commands, dry_run=dry_run) if commands else ()

    return _make_step_result(
        RollbackStep.START_RUNTIME,
        RollbackStatus.HEALTHCHECKING,
        "Runtime started" if commands else "No runtime compose file found; start skipped",
        started_at,
        command_results=results,
        metadata={"commands": len(commands)},
    )


def run_migrations(
    context: RollbackContext,
    *,
    migration_runner: MigrationRunner | None = None,
    dry_run: bool = False,
) -> RollbackStepResult:
    """Run migration hook after rollback if provided."""

    started_at = utc_now()

    if migration_runner is not None and not dry_run:
        migration_runner(context.instance_id)

    return _make_step_result(
        RollbackStep.RUN_MIGRATIONS,
        RollbackStatus.HEALTHCHECKING,
        "Migration hook completed" if migration_runner else "Migration hook skipped",
        started_at,
        metadata={"runner_used": migration_runner is not None, "dry_run": dry_run},
    )


def run_security_gate(
    context: RollbackContext,
    *,
    security_gate_runner: SecurityGateRunner | None = None,
    dry_run: bool = False,
) -> RollbackStepResult:
    """Run Security Gate hook after rollback if provided."""

    started_at = utc_now()
    result: Any = None

    if security_gate_runner is not None and not dry_run:
        result = security_gate_runner(context.instance_id)

    return _make_step_result(
        RollbackStep.RUN_SECURITY_GATE,
        RollbackStatus.HEALTHCHECKING,
        "Security Gate hook completed" if security_gate_runner else "Security Gate hook skipped",
        started_at,
        metadata={
            "runner_used": security_gate_runner is not None,
            "dry_run": dry_run,
            "result": result,
        },
    )


def run_healthchecks(
    context: RollbackContext,
    *,
    healthcheck_runner: HealthcheckRunner | None = None,
    dry_run: bool = False,
) -> RollbackStepResult:
    """Run healthcheck hook after rollback if provided."""

    started_at = utc_now()
    result: Any = None

    if healthcheck_runner is not None and not dry_run:
        result = healthcheck_runner(context.instance_id)

    return _make_step_result(
        RollbackStep.RUN_HEALTHCHECKS,
        RollbackStatus.COMPLETED,
        "Healthcheck hook completed" if healthcheck_runner else "Healthcheck hook skipped",
        started_at,
        metadata={
            "runner_used": healthcheck_runner is not None,
            "dry_run": dry_run,
            "result": result,
        },
    )


def rollback_instance(
    *,
    context: RollbackContext,
    restore_runner: DataRestoreRunner | None = None,
    migration_runner: MigrationRunner | None = None,
    security_gate_runner: SecurityGateRunner | None = None,
    healthcheck_runner: HealthcheckRunner | None = None,
    audit_logger: AuditLogger | None = None,
    dry_run: bool = False,
) -> RollbackResult:
    """Execute a full rollback workflow."""

    logger = audit_logger or get_audit_logger()
    started_at = utc_now()
    steps: list[RollbackStepResult] = []

    _audit(
        logger,
        context=context,
        outcome=AuditOutcome.STARTED,
        message="Rollback started",
        metadata={"dry_run": dry_run},
    )
    write_rollback_state(context, RollbackStatus.RUNNING, metadata={"dry_run": dry_run})

    try:
        audit_instance_state_change(
            instance_id=context.instance_id,
            from_state=InstanceState.RUNNING,
            to_state=InstanceState.ROLLING_BACK,
            reason="rollback started",
            logger=logger,
        )

        steps.append(preflight_rollback(context))
        steps.append(stop_runtime(context, dry_run=dry_run))

        repoint_step = repoint_capsule(context, dry_run=dry_run)
        steps.append(repoint_step)
        write_rollback_state(
            context,
            RollbackStatus.CAPSULE_REPOINTED,
            metadata=repoint_step.metadata,
        )

        data_step = restore_data(context, restore_runner=restore_runner, dry_run=dry_run)
        steps.append(data_step)
        if data_step.status == RollbackStatus.DATA_RESTORED:
            write_rollback_state(context, RollbackStatus.DATA_RESTORED, metadata=data_step.metadata)

        steps.append(start_runtime(context, dry_run=dry_run))
        steps.append(run_migrations(context, migration_runner=migration_runner, dry_run=dry_run))
        steps.append(run_security_gate(context, security_gate_runner=security_gate_runner, dry_run=dry_run))
        steps.append(run_healthchecks(context, healthcheck_runner=healthcheck_runner, dry_run=dry_run))

        result = RollbackResult(
            rollback_id=context.rollback_id,
            instance_id=context.instance_id,
            status=RollbackStatus.COMPLETED,
            target_capsule_id=context.target_capsule_id,
            target_capsule_version=context.target_capsule_version,
            started_at=started_at,
            completed_at=utc_now(),
            steps=tuple(steps),
            metadata={"dry_run": dry_run},
        )

        write_rollback_state(context, RollbackStatus.COMPLETED, metadata={"dry_run": dry_run})
        audit_instance_state_change(
            instance_id=context.instance_id,
            from_state=InstanceState.ROLLING_BACK,
            to_state=InstanceState.RUNNING,
            reason="rollback completed",
            logger=logger,
        )
        _audit(
            logger,
            context=context,
            outcome=AuditOutcome.SUCCEEDED,
            message="Rollback completed",
            metadata={"dry_run": dry_run},
        )
        return result

    except Exception as exc:
        write_rollback_state(
            context,
            RollbackStatus.FAILED,
            metadata={"dry_run": dry_run},
            error=str(exc),
        )
        _audit(
            logger,
            context=context,
            outcome=AuditOutcome.FAILED,
            severity=AuditSeverity.ERROR,
            message="Rollback failed",
            metadata={"dry_run": dry_run},
            error=exc,
        )

        return RollbackResult(
            rollback_id=context.rollback_id,
            instance_id=context.instance_id,
            status=RollbackStatus.FAILED,
            target_capsule_id=context.target_capsule_id,
            target_capsule_version=context.target_capsule_version,
            started_at=started_at,
            completed_at=utc_now(),
            steps=tuple(steps),
            error=str(exc),
            metadata={"dry_run": dry_run},
        )


def create_rollback_plan(
    *,
    instance_id: InstanceID | str,
    target_capsule_id: CapsuleID | str,
    target_capsule_version: CapsuleVersion | str,
    restore_data: bool = False,
    backup_id: BackupID | str | None = None,
) -> RollbackPlan:
    """Create a typed rollback plan for API/CLI use."""

    return RollbackPlan(
        rollback_id=new_rollback_id(instance_id),
        instance_id=InstanceID(str(instance_id)),
        status=RollbackStatus.PLANNED,
        target_capsule_id=CapsuleID(str(target_capsule_id)),
        target_capsule_version=CapsuleVersion(str(target_capsule_version)),
        created_at=utc_now(),
        restore_data=restore_data,
        backup_id=BackupID(str(backup_id)) if backup_id is not None else None,
    )


def result_to_dict(result: RollbackResult) -> dict[str, Any]:
    """Serialize rollback result for API responses or state files."""

    return json.loads(json.dumps(asdict(result), default=_json_default))


def latest_rollback_state(instance_id: InstanceID | str) -> dict[str, Any] | None:
    """Read the latest rollback state for an instance."""

    path = instance_state_dir(str(instance_id)) / ROLLBACK_STATE_FILENAME
    return _read_json(path)


def rollback_history(instance_id: InstanceID | str) -> list[dict[str, Any]]:
    """Read rollback history entries for an instance."""

    path = instance_state_dir(str(instance_id)) / ROLLBACK_HISTORY_FILENAME
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        loaded = json.loads(line)
        if isinstance(loaded, dict):
            entries.append(loaded)
    return entries


def clear_failed_rollback_state(instance_id: InstanceID | str) -> None:
    """Remove failed rollback marker after operator review."""

    state_file = instance_state_dir(str(instance_id)) / ROLLBACK_STATE_FILENAME
    state = _read_json(state_file)
    if not state:
        return
    if state.get("status") != RollbackStatus.FAILED.value:
        raise RollbackSafetyError("only failed rollback state can be cleared")
    state_file.unlink(missing_ok=True)


__all__ = [
    "CURRENT_CAPSULE_POINTER",
    "DEFAULT_COMMAND_TIMEOUT_SECONDS",
    "PREVIOUS_CAPSULE_POINTER",
    "ROLLBACK_HISTORY_FILENAME",
    "ROLLBACK_SCHEMA_VERSION",
    "ROLLBACK_STATE_FILENAME",
    "CapsulePointer",
    "DataRestoreRunner",
    "HealthcheckRunner",
    "MigrationRunner",
    "RollbackCommand",
    "RollbackCommandError",
    "RollbackCommandResult",
    "RollbackContext",
    "RollbackError",
    "RollbackResult",
    "RollbackSafetyError",
    "RollbackStep",
    "RollbackStepResult",
    "SecurityGateRunner",
    "build_rollback_context",
    "build_start_runtime_commands",
    "build_stop_runtime_commands",
    "clear_failed_rollback_state",
    "create_rollback_plan",
    "latest_rollback_state",
    "new_rollback_id",
    "pointer_from_dict",
    "pointer_to_dict",
    "preflight_rollback",
    "read_capsule_pointer",
    "repoint_capsule",
    "resolve_target_capsule_file",
    "restore_data",
    "result_to_dict",
    "rollback_history",
    "rollback_instance",
    "run_command",
    "run_commands",
    "run_healthchecks",
    "run_migrations",
    "run_security_gate",
    "start_runtime",
    "stop_runtime",
    "utc_now",
    "validate_capsule_file",
    "validate_rollback_context",
    "write_capsule_pointer",
    "write_rollback_state",
]
