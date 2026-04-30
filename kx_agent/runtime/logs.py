"""Runtime log collection helpers for Konnaxion Agent.

This module centralizes log access for Konnaxion Instance services. It uses
canonical Docker Compose service names and canonical instance paths only.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Sequence

from kx_shared.errors import KonnaxionRuntimeError
from kx_shared.konnaxion_constants import (
    CANONICAL_DOCKER_SERVICES,
    DockerService,
    instance_compose_file,
    instance_root,
)


DEFAULT_LOG_TAIL = 200
MAX_LOG_TAIL = 5000


@dataclass(frozen=True)
class RuntimeLogRequest:
    """Request for logs from one or more runtime services."""

    instance_id: str
    services: tuple[str, ...] = ()
    tail: int = DEFAULT_LOG_TAIL
    follow: bool = False
    timestamps: bool = True
    compose_file: Path | None = None

    def normalized_services(self) -> tuple[str, ...]:
        """Return validated canonical service names."""

        if not self.services:
            return ()

        invalid = sorted(set(self.services) - set(CANONICAL_DOCKER_SERVICES))
        if invalid:
            allowed = ", ".join(CANONICAL_DOCKER_SERVICES)
            raise KonnaxionRuntimeError(
                f"Unknown Konnaxion runtime service(s): {', '.join(invalid)}. "
                f"Allowed services: {allowed}"
            )

        return self.services

    def normalized_tail(self) -> int:
        """Return a safe log tail count."""

        if self.tail < 1:
            raise KonnaxionRuntimeError("Log tail must be greater than or equal to 1.")
        return min(self.tail, MAX_LOG_TAIL)

    @property
    def resolved_compose_file(self) -> Path:
        """Return the runtime compose file for this request."""

        return self.compose_file or instance_compose_file(self.instance_id)


@dataclass(frozen=True)
class RuntimeLogResult:
    """Captured runtime logs from Docker Compose."""

    instance_id: str
    services: tuple[str, ...]
    output: str
    command: tuple[str, ...]
    collected_at: datetime

    def as_dict(self) -> dict[str, str | list[str]]:
        """Return a JSON-serializable representation."""

        return {
            "instance_id": self.instance_id,
            "services": list(self.services),
            "output": self.output,
            "command": list(self.command),
            "collected_at": self.collected_at.isoformat(),
        }


def build_compose_logs_command(request: RuntimeLogRequest) -> tuple[str, ...]:
    """Build a safe ``docker compose logs`` command."""

    compose_file = request.resolved_compose_file
    if not compose_file.exists():
        raise KonnaxionRuntimeError(f"Missing runtime compose file: {compose_file}")

    command: list[str] = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "logs",
        "--tail",
        str(request.normalized_tail()),
    ]

    if request.timestamps:
        command.append("--timestamps")

    if request.follow:
        command.append("--follow")

    command.extend(request.normalized_services())
    return tuple(command)


def collect_runtime_logs(request: RuntimeLogRequest) -> RuntimeLogResult:
    """Collect logs from Docker Compose and return them as text.

    This function is intended for bounded log reads. For streaming logs, use
    ``stream_runtime_logs``.
    """

    if request.follow:
        raise KonnaxionRuntimeError(
            "collect_runtime_logs does not support follow=True. "
            "Use stream_runtime_logs for streaming logs."
        )

    command = build_compose_logs_command(request)

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise KonnaxionRuntimeError("Docker CLI was not found on this host.") from exc
    except subprocess.TimeoutExpired as exc:
        raise KonnaxionRuntimeError("Timed out while collecting runtime logs.") from exc

    output = completed.stdout
    if completed.stderr:
        output = f"{output}\n{completed.stderr}".strip()

    if completed.returncode != 0:
        raise KonnaxionRuntimeError(
            f"Failed to collect runtime logs with exit code {completed.returncode}: "
            f"{output}"
        )

    return RuntimeLogResult(
        instance_id=request.instance_id,
        services=request.normalized_services(),
        output=output,
        command=command,
        collected_at=datetime.now(UTC),
    )


def stream_runtime_logs(request: RuntimeLogRequest) -> Iterable[str]:
    """Yield runtime log lines from Docker Compose.

    The caller owns cancellation/termination. The process is terminated when
    the iterator exits.
    """

    command = build_compose_logs_command(
        RuntimeLogRequest(
            instance_id=request.instance_id,
            services=request.services,
            tail=request.tail,
            follow=True,
            timestamps=request.timestamps,
            compose_file=request.compose_file,
        )
    )

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError as exc:
        raise KonnaxionRuntimeError("Docker CLI was not found on this host.") from exc

    try:
        if process.stdout is None:
            raise KonnaxionRuntimeError("Unable to open Docker logs stream.")

        for line in process.stdout:
            yield line.rstrip("\n")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def collect_service_logs(
    instance_id: str,
    service: DockerService | str,
    *,
    tail: int = DEFAULT_LOG_TAIL,
    compose_file: Path | None = None,
) -> RuntimeLogResult:
    """Collect bounded logs for one canonical service."""

    service_name = service.value if isinstance(service, DockerService) else service
    return collect_runtime_logs(
        RuntimeLogRequest(
            instance_id=instance_id,
            services=(service_name,),
            tail=tail,
            compose_file=compose_file,
        )
    )


def collect_all_runtime_logs(
    instance_id: str,
    *,
    tail: int = DEFAULT_LOG_TAIL,
    compose_file: Path | None = None,
) -> RuntimeLogResult:
    """Collect bounded logs for all services in a Konnaxion Instance."""

    return collect_runtime_logs(
        RuntimeLogRequest(
            instance_id=instance_id,
            services=(),
            tail=tail,
            compose_file=compose_file,
        )
    )


def list_log_files(instance_id: str) -> tuple[Path, ...]:
    """List persisted log files under the canonical instance log directory."""

    logs_dir = instance_root(instance_id) / "logs"
    if not logs_dir.exists():
        return ()

    return tuple(
        sorted(
            path
            for path in logs_dir.rglob("*")
            if path.is_file()
        )
    )


def read_log_file(path: Path, *, max_bytes: int = 1_000_000) -> str:
    """Read a persisted log file with a hard byte cap."""

    if max_bytes < 1:
        raise KonnaxionRuntimeError("max_bytes must be greater than or equal to 1.")

    if not path.exists() or not path.is_file():
        raise KonnaxionRuntimeError(f"Log file does not exist: {path}")

    with path.open("rb") as handle:
        data = handle.read(max_bytes + 1)

    if len(data) > max_bytes:
        data = data[:max_bytes] + b"\n...[truncated]\n"

    return data.decode("utf-8", errors="replace")


def collect_persisted_logs(
    instance_id: str,
    *,
    max_files: int = 50,
    max_bytes_per_file: int = 250_000,
) -> dict[str, str]:
    """Read persisted instance logs from the canonical logs directory."""

    if max_files < 1:
        raise KonnaxionRuntimeError("max_files must be greater than or equal to 1.")

    files = list_log_files(instance_id)[:max_files]
    return {
        str(path): read_log_file(path, max_bytes=max_bytes_per_file)
        for path in files
    }


def normalize_log_services(services: Sequence[DockerService | str] | None) -> tuple[str, ...]:
    """Normalize a service sequence to canonical Docker Compose service names."""

    if not services:
        return ()

    normalized = tuple(
        service.value if isinstance(service, DockerService) else service
        for service in services
    )

    invalid = sorted(set(normalized) - set(CANONICAL_DOCKER_SERVICES))
    if invalid:
        allowed = ", ".join(CANONICAL_DOCKER_SERVICES)
        raise KonnaxionRuntimeError(
            f"Unknown Konnaxion runtime service(s): {', '.join(invalid)}. "
            f"Allowed services: {allowed}"
        )

    return normalized
