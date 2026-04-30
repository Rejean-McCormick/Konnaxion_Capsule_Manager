"""
Builder service wrapper for Konnaxion Capsule Manager.

The Manager GUI may request capsule build and verify operations, but it must
not execute arbitrary shell commands. This module provides a narrow,
allowlisted wrapper around the approved Konnaxion Capsule Builder commands.

Approved operations:
- uv run kx-builder capsule build ...
- uv run kx-builder capsule verify ...

This service is intentionally framework-independent so it can be used by:
- kx_manager/ui/actions.py
- kx_manager/routes/capsules.py
- tests
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


DEFAULT_BUILDER_TIMEOUT_SECONDS = 60 * 60
DEFAULT_VERIFY_TIMEOUT_SECONDS = 15 * 60

DEFAULT_CAPSULE_ID = "konnaxion-v14-demo-2026.04.30"
DEFAULT_CAPSULE_VERSION = "2026.04.30-demo.1"
DEFAULT_APP_VERSION = "v14"
DEFAULT_PARAM_VERSION = "kx-param-2026.04.30"
DEFAULT_NETWORK_PROFILE = "intranet_private"

DEFAULT_WINDOWS_SOURCE_DIR = Path(r"C:\mycode\Konnaxion\Konnaxion")
DEFAULT_WINDOWS_CAPSULE_OUTPUT_DIR = Path(r"C:\mycode\Konnaxion\runtime\capsules")


class BuilderServiceError(ValueError):
    """Raised when a builder request is invalid."""


@dataclass(frozen=True)
class BuildCapsuleRequest:
    """Request to build a Konnaxion Capsule."""

    source_dir: Path = DEFAULT_WINDOWS_SOURCE_DIR
    capsule_output_dir: Path = DEFAULT_WINDOWS_CAPSULE_OUTPUT_DIR
    capsule_file: Path | None = None
    capsule_id: str = DEFAULT_CAPSULE_ID
    capsule_version: str = DEFAULT_CAPSULE_VERSION
    app_version: str = DEFAULT_APP_VERSION
    param_version: str = DEFAULT_PARAM_VERSION
    network_profile: str = DEFAULT_NETWORK_PROFILE
    force: bool = False
    cwd: Path | None = None
    timeout_seconds: int = DEFAULT_BUILDER_TIMEOUT_SECONDS
    env: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BuilderCommandResult:
    """Normalized result for a Builder service command."""

    ok: bool
    operation: str
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    message: str
    started_at: str
    finished_at: str
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "operation": self.operation,
            "argv": list(self.argv),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "message": self.message,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "data": dict(self.data),
        }


@dataclass(frozen=True)
class BuildCapsuleResult:
    """Manager-facing build result."""

    ok: bool
    capsule_file: Path
    capsule_id: str
    capsule_version: str
    app_version: str
    param_version: str
    network_profile: str
    command: BuilderCommandResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "capsule_file": str(self.capsule_file),
            "capsule_id": self.capsule_id,
            "capsule_version": self.capsule_version,
            "app_version": self.app_version,
            "param_version": self.param_version,
            "network_profile": self.network_profile,
            "command": self.command.to_dict(),
        }


@dataclass(frozen=True)
class VerifyCapsuleResult:
    """Manager-facing verify result."""

    ok: bool
    capsule_file: Path
    command: BuilderCommandResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "capsule_file": str(self.capsule_file),
            "command": self.command.to_dict(),
        }


def build_capsule(request: BuildCapsuleRequest | None = None) -> BuildCapsuleResult:
    """Build a signed `.kxcap` capsule through the approved Builder command."""

    request = request or BuildCapsuleRequest()

    source_dir = _require_existing_dir(request.source_dir, "source_dir")
    capsule_output_dir = _ensure_dir(request.capsule_output_dir, "capsule_output_dir")
    capsule_file = _resolve_capsule_file(request, capsule_output_dir)

    argv = [
        "uv",
        "run",
        "kx-builder",
        "capsule",
        "build",
        "--source-dir",
        str(source_dir),
        "--output",
        str(capsule_file),
        "--capsule-id",
        request.capsule_id,
        "--version",
        request.capsule_version,
        "--app-version",
        request.app_version,
        "--param-version",
        request.param_version,
        "--profile",
        request.network_profile,
    ]

    if request.force:
        argv.append("--force")

    command = _run_approved_builder_command(
        operation="build_capsule",
        argv=argv,
        cwd=request.cwd,
        timeout_seconds=request.timeout_seconds,
        env=_builder_env(request),
    )

    ok = command.ok and capsule_file.exists()

    if not ok and command.ok:
        command = BuilderCommandResult(
            ok=False,
            operation=command.operation,
            argv=command.argv,
            returncode=command.returncode,
            stdout=command.stdout,
            stderr=command.stderr,
            message=f"Builder completed but capsule file was not created: {capsule_file}",
            started_at=command.started_at,
            finished_at=command.finished_at,
            data=command.data,
        )

    return BuildCapsuleResult(
        ok=ok,
        capsule_file=capsule_file,
        capsule_id=request.capsule_id,
        capsule_version=request.capsule_version,
        app_version=request.app_version,
        param_version=request.param_version,
        network_profile=request.network_profile,
        command=command,
    )


def rebuild_capsule(request: BuildCapsuleRequest | None = None) -> BuildCapsuleResult:
    """Delete the requested output capsule if it exists, then build again."""

    request = request or BuildCapsuleRequest()

    capsule_output_dir = _ensure_dir(request.capsule_output_dir, "capsule_output_dir")
    capsule_file = _resolve_capsule_file(request, capsule_output_dir)

    if capsule_file.exists():
        capsule_file.unlink()

    rebuild_request = BuildCapsuleRequest(
        source_dir=request.source_dir,
        capsule_output_dir=request.capsule_output_dir,
        capsule_file=capsule_file,
        capsule_id=request.capsule_id,
        capsule_version=request.capsule_version,
        app_version=request.app_version,
        param_version=request.param_version,
        network_profile=request.network_profile,
        force=True,
        cwd=request.cwd,
        timeout_seconds=request.timeout_seconds,
        env=request.env,
    )

    return build_capsule(rebuild_request)


def verify_capsule(
    capsule_file: Path,
    *,
    cwd: Path | None = None,
    timeout_seconds: int = DEFAULT_VERIFY_TIMEOUT_SECONDS,
    env: Mapping[str, str] | None = None,
) -> VerifyCapsuleResult:
    """Verify a `.kxcap` capsule through the approved Builder command."""

    capsule_file = _require_existing_file(capsule_file, "capsule_file")
    _require_kxcap(capsule_file, "capsule_file")

    argv = [
        "uv",
        "run",
        "kx-builder",
        "capsule",
        "verify",
        str(capsule_file),
    ]

    command = _run_approved_builder_command(
        operation="verify_capsule",
        argv=argv,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        env=env or {},
    )

    return VerifyCapsuleResult(
        ok=command.ok,
        capsule_file=capsule_file,
        command=command,
    )


def build_default_capsule() -> BuildCapsuleResult:
    """Build the default development capsule."""

    return build_capsule(BuildCapsuleRequest())


def verify_default_capsule() -> VerifyCapsuleResult:
    """Verify the default development capsule."""

    request = BuildCapsuleRequest()
    capsule_file = _resolve_capsule_file(
        request,
        _ensure_dir(request.capsule_output_dir, "capsule_output_dir"),
    )
    return verify_capsule(capsule_file)


def serialize_build_result(result: BuildCapsuleResult) -> dict[str, Any]:
    """Serialize build result for Manager routes or GUI actions."""

    return result.to_dict()


def serialize_verify_result(result: VerifyCapsuleResult) -> dict[str, Any]:
    """Serialize verify result for Manager routes or GUI actions."""

    return result.to_dict()


def _builder_env(request: BuildCapsuleRequest) -> dict[str, str]:
    env = {
        "KX_SOURCE_DIR": str(request.source_dir),
        "KX_CAPSULE_OUTPUT_DIR": str(request.capsule_output_dir),
        "KX_CAPSULE_ID": request.capsule_id,
        "KX_CAPSULE_VERSION": request.capsule_version,
        "KX_APP_VERSION": request.app_version,
        "KX_PARAM_VERSION": request.param_version,
        "KX_NETWORK_PROFILE": request.network_profile,
    }
    env.update({str(key): str(value) for key, value in request.env.items()})
    return env


def _resolve_capsule_file(
    request: BuildCapsuleRequest,
    capsule_output_dir: Path,
) -> Path:
    if request.capsule_file is not None:
        capsule_file = Path(request.capsule_file).expanduser()
        if not capsule_file.is_absolute():
            capsule_file = capsule_output_dir / capsule_file
    else:
        capsule_file = capsule_output_dir / f"{request.capsule_id}.kxcap"

    _require_kxcap(capsule_file, "capsule_file")
    return capsule_file.resolve()


def _run_approved_builder_command(
    *,
    operation: str,
    argv: list[str],
    cwd: Path | None,
    timeout_seconds: int,
    env: Mapping[str, str],
) -> BuilderCommandResult:
    if not argv:
        raise BuilderServiceError("argv must not be empty.")

    if timeout_seconds <= 0:
        raise BuilderServiceError("timeout_seconds must be greater than zero.")

    _raise_if_unapproved_builder_command(argv)

    run_cwd = None
    if cwd is not None:
        run_cwd = _require_existing_dir(cwd, "cwd")

    run_env = os.environ.copy()
    run_env.update({str(key): str(value) for key, value in env.items()})

    started_at = _utc_now_iso()

    try:
        completed = subprocess.run(
            argv,
            cwd=str(run_cwd) if run_cwd else None,
            env=run_env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        finished_at = _utc_now_iso()
        return BuilderCommandResult(
            ok=False,
            operation=operation,
            argv=tuple(argv),
            returncode=124,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            message=f"Builder command timed out after {timeout_seconds} seconds.",
            started_at=started_at,
            finished_at=finished_at,
            data={"timeout_seconds": timeout_seconds},
        )
    except FileNotFoundError as exc:
        finished_at = _utc_now_iso()
        return BuilderCommandResult(
            ok=False,
            operation=operation,
            argv=tuple(argv),
            returncode=127,
            stdout="",
            stderr=str(exc),
            message="Builder command could not be started. Is `uv` installed and on PATH?",
            started_at=started_at,
            finished_at=finished_at,
            data={},
        )

    finished_at = _utc_now_iso()
    ok = completed.returncode == 0

    return BuilderCommandResult(
        ok=ok,
        operation=operation,
        argv=tuple(argv),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        message="Builder command completed." if ok else "Builder command failed.",
        started_at=started_at,
        finished_at=finished_at,
        data={
            "cwd": str(run_cwd) if run_cwd else None,
        },
    )


def _raise_if_unapproved_builder_command(argv: list[str]) -> None:
    command_key = tuple(argv[:5])

    approved_prefixes = {
        ("uv", "run", "kx-builder", "capsule", "build"),
        ("uv", "run", "kx-builder", "capsule", "verify"),
    }

    if command_key not in approved_prefixes:
        raise BuilderServiceError(f"Unapproved builder command: {argv!r}")


def _require_existing_dir(value: Path, field_name: str) -> Path:
    path = Path(value).expanduser().resolve()

    if not path.exists():
        raise BuilderServiceError(f"{field_name} does not exist: {path}")

    if not path.is_dir():
        raise BuilderServiceError(f"{field_name} is not a directory: {path}")

    return path


def _ensure_dir(value: Path, field_name: str) -> Path:
    path = Path(value).expanduser().resolve()

    if path.exists() and not path.is_dir():
        raise BuilderServiceError(f"{field_name} is not a directory: {path}")

    path.mkdir(parents=True, exist_ok=True)
    return path


def _require_existing_file(value: Path, field_name: str) -> Path:
    path = Path(value).expanduser().resolve()

    if not path.exists():
        raise BuilderServiceError(f"{field_name} does not exist: {path}")

    if not path.is_file():
        raise BuilderServiceError(f"{field_name} is not a file: {path}")

    return path


def _require_kxcap(value: Path, field_name: str) -> None:
    if Path(value).suffix != ".kxcap":
        raise BuilderServiceError(f"{field_name} must end with .kxcap: {value}")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = [
    "BuildCapsuleRequest",
    "BuildCapsuleResult",
    "BuilderCommandResult",
    "BuilderServiceError",
    "VerifyCapsuleResult",
    "build_capsule",
    "build_default_capsule",
    "rebuild_capsule",
    "serialize_build_result",
    "serialize_verify_result",
    "verify_capsule",
    "verify_default_capsule",
]