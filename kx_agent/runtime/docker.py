"""
Controlled Docker / Docker Compose adapter for Konnaxion Agent.

This module is the only runtime layer that should invoke Docker from Agent code.
It intentionally exposes narrow, allowlisted operations instead of arbitrary
shell execution.

Responsibilities:
- locate a usable Docker Compose command
- validate canonical service names before targeted operations
- run compose lifecycle commands
- inspect services, containers, images, volumes, networks, and logs
- return structured command results for Manager/API/CLI layers

Non-responsibilities:
- generating docker-compose.runtime.yml
- deciding Security Gate policy
- performing arbitrary shell commands
- mounting Docker socket into Konnaxion app containers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
import json
import os
import shutil
import subprocess
from typing import Any, Iterable, Mapping, Sequence

from kx_shared.konnaxion_constants import (
    CANONICAL_DOCKER_SERVICES,
    DockerService,
    KX_ROOT,
    instance_compose_file,
)
from kx_shared.validation import (
    ValidationIssue,
    ValidationFailed,
    raise_if_issues,
    validate_service_name,
    validate_service_names,
    validate_path_under_root,
)


DEFAULT_COMMAND_TIMEOUT_SECONDS = 300
DEFAULT_LOG_LINES = 300


class DockerComposeBinary(StrEnum):
    """Supported Compose command forms."""

    DOCKER_PLUGIN = "docker compose"
    DOCKER_COMPOSE = "docker-compose"


class ComposeAction(StrEnum):
    """Allowlisted Compose lifecycle actions."""

    CONFIG = "config"
    PULL = "pull"
    UP = "up"
    DOWN = "down"
    START = "start"
    STOP = "stop"
    RESTART = "restart"
    PS = "ps"
    LOGS = "logs"
    RUN = "run"
    EXEC = "exec"


class ContainerHealth(StrEnum):
    """Normalized container health values."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    NONE = "none"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CommandResult:
    """Structured subprocess result."""

    args: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


@dataclass(frozen=True)
class DockerRuntimeConfig:
    """Configuration for DockerRuntime."""

    compose_file: Path
    project_name: str
    working_dir: Path = KX_ROOT
    env: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS
    compose_binary: DockerComposeBinary | None = None
    allow_outside_kx_root: bool = False


@dataclass(frozen=True)
class ComposeServiceStatus:
    """Normalized status for one Compose service."""

    service: str
    container_id: str | None = None
    name: str | None = None
    state: str | None = None
    status: str | None = None
    health: ContainerHealth = ContainerHealth.UNKNOWN
    image: str | None = None
    ports: tuple[str, ...] = ()


@dataclass(frozen=True)
class DockerImageInfo:
    """Minimal image metadata returned by docker image inspect."""

    image: str
    image_id: str | None = None
    repo_tags: tuple[str, ...] = ()
    repo_digests: tuple[str, ...] = ()
    created: str | None = None


class DockerRuntimeError(RuntimeError):
    """Raised when a Docker runtime command fails."""

    def __init__(self, message: str, result: CommandResult | None = None) -> None:
        self.result = result
        if result is not None:
            detail = result.stderr.strip() or result.stdout.strip()
            if detail:
                message = f"{message}: {detail}"
        super().__init__(message)


class DockerRuntime:
    """Safe adapter around Docker and Docker Compose for one instance."""

    def __init__(self, config: DockerRuntimeConfig) -> None:
        self.config = config
        self._validate_config()
        self._compose_cmd = self._resolve_compose_command(config.compose_binary)

    @classmethod
    def for_instance(
        cls,
        instance_id: str,
        *,
        project_name: str | None = None,
        timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    ) -> "DockerRuntime":
        """Create a DockerRuntime using the canonical instance compose path."""

        return cls(
            DockerRuntimeConfig(
                compose_file=instance_compose_file(instance_id),
                project_name=project_name or f"konnaxion-{instance_id}",
                timeout_seconds=timeout_seconds,
            )
        )

    def validate_available(self) -> None:
        """Raise if Docker or Docker Compose are not available."""

        docker_result = self._run(["docker", "version", "--format", "json"], timeout=30)
        if not docker_result.ok:
            raise DockerRuntimeError("Docker daemon is not available", docker_result)

        compose_result = self._run([*self._compose_cmd, "version"], timeout=30)
        if not compose_result.ok:
            raise DockerRuntimeError("Docker Compose is not available", compose_result)

    def compose_config(self) -> CommandResult:
        """Validate and render the Compose configuration."""

        return self._compose(ComposeAction.CONFIG)

    def up(
        self,
        *,
        detach: bool = True,
        services: Iterable[str] | None = None,
        build: bool = False,
        remove_orphans: bool = True,
    ) -> CommandResult:
        """Start the Compose stack or selected canonical services."""

        service_list = self._validate_services(services)
        args = [ComposeAction.UP.value]

        if detach:
            args.append("-d")
        if build:
            args.append("--build")
        if remove_orphans:
            args.append("--remove-orphans")

        args.extend(service_list)
        return self._compose_args(args)

    def down(
        self,
        *,
        remove_orphans: bool = True,
        volumes: bool = False,
        timeout_seconds: int | None = None,
    ) -> CommandResult:
        """Stop and remove the Compose stack.

        `volumes=False` by default to preserve Konnaxion instance data.
        """

        args = [ComposeAction.DOWN.value]

        if remove_orphans:
            args.append("--remove-orphans")
        if volumes:
            args.append("--volumes")
        if timeout_seconds is not None:
            args.extend(["--timeout", str(timeout_seconds)])

        return self._compose_args(args)

    def start(self, services: Iterable[str] | None = None) -> CommandResult:
        """Start existing stopped Compose services."""

        service_list = self._validate_services(services)
        return self._compose_args([ComposeAction.START.value, *service_list])

    def stop(
        self,
        services: Iterable[str] | None = None,
        *,
        timeout_seconds: int | None = None,
    ) -> CommandResult:
        """Stop running Compose services."""

        service_list = self._validate_services(services)
        args = [ComposeAction.STOP.value]
        if timeout_seconds is not None:
            args.extend(["--timeout", str(timeout_seconds)])
        args.extend(service_list)
        return self._compose_args(args)

    def restart(self, services: Iterable[str] | None = None) -> CommandResult:
        """Restart Compose services."""

        service_list = self._validate_services(services)
        return self._compose_args([ComposeAction.RESTART.value, *service_list])

    def ps(self) -> tuple[ComposeServiceStatus, ...]:
        """Return normalized Compose service status."""

        result = self._compose_args([ComposeAction.PS.value, "--format", "json"])
        self._raise_on_failure("Could not inspect Compose services", result)

        rows = self._parse_json_lines_or_array(result.stdout)
        statuses: list[ComposeServiceStatus] = []

        for row in rows:
            if not isinstance(row, Mapping):
                continue

            service = str(row.get("Service") or row.get("service") or "")
            if service:
                raise_if_issues(validate_service_name(service))

            ports = row.get("Publishers") or row.get("Ports") or ()
            statuses.append(
                ComposeServiceStatus(
                    service=service,
                    container_id=_optional_str(row.get("ID") or row.get("ContainerID")),
                    name=_optional_str(row.get("Name")),
                    state=_optional_str(row.get("State")),
                    status=_optional_str(row.get("Status")),
                    health=self._normalize_health(row),
                    image=_optional_str(row.get("Image")),
                    ports=self._normalize_ports(ports),
                )
            )

        return tuple(statuses)

    def logs(
        self,
        services: Iterable[str] | None = None,
        *,
        lines: int = DEFAULT_LOG_LINES,
        timestamps: bool = True,
    ) -> CommandResult:
        """Read recent Compose logs."""

        if lines < 1:
            raise ValueError("lines must be >= 1")

        service_list = self._validate_services(services)
        args = [ComposeAction.LOGS.value, "--tail", str(lines)]
        if timestamps:
            args.append("--timestamps")
        args.extend(service_list)
        return self._compose_args(args)

    def run_one_off(
        self,
        service: str,
        command: Sequence[str],
        *,
        no_deps: bool = False,
        remove: bool = True,
        env: Mapping[str, str] | None = None,
        workdir: str | None = None,
    ) -> CommandResult:
        """Run an allowlisted one-off command inside a canonical service.

        The command is passed as argv, never through a shell.
        """

        raise_if_issues(validate_service_name(service))
        if not command:
            raise ValueError("command must not be empty")

        args = [ComposeAction.RUN.value]
        if remove:
            args.append("--rm")
        if no_deps:
            args.append("--no-deps")
        if workdir:
            args.extend(["--workdir", workdir])
        for key, value in sorted((env or {}).items()):
            args.extend(["--env", f"{key}={value}"])

        args.append(service)
        args.extend(str(part) for part in command)
        return self._compose_args(args)

    def exec(
        self,
        service: str,
        command: Sequence[str],
        *,
        user: str | None = None,
        env: Mapping[str, str] | None = None,
        workdir: str | None = None,
    ) -> CommandResult:
        """Execute a command inside a running canonical service.

        This is still narrow: caller must provide argv; no shell string is accepted.
        """

        raise_if_issues(validate_service_name(service))
        if not command:
            raise ValueError("command must not be empty")

        args = [ComposeAction.EXEC.value, "-T"]
        if user:
            args.extend(["--user", user])
        if workdir:
            args.extend(["--workdir", workdir])
        for key, value in sorted((env or {}).items()):
            args.extend(["--env", f"{key}={value}"])

        args.append(service)
        args.extend(str(part) for part in command)
        return self._compose_args(args)

    def migrate_django(self) -> CommandResult:
        """Run the canonical Django migration command."""

        return self.run_one_off(
            DockerService.DJANGO_API.value,
            ["python", "manage.py", "migrate", "--noinput"],
            no_deps=False,
            remove=True,
        )

    def collectstatic_django(self) -> CommandResult:
        """Run Django collectstatic for production static assets."""

        return self.run_one_off(
            DockerService.DJANGO_API.value,
            ["python", "manage.py", "collectstatic", "--noinput"],
            no_deps=False,
            remove=True,
        )

    def health(self) -> Mapping[str, ContainerHealth]:
        """Return health by canonical service name."""

        return {status.service: status.health for status in self.ps() if status.service}

    def is_stack_running(self) -> bool:
        """Return true if at least one canonical service is running."""

        return any((status.state or "").lower() == "running" for status in self.ps())

    def wait_for_healthy(
        self,
        *,
        required_services: Iterable[str] | None = None,
        attempts: int = 30,
        interval_seconds: float = 2.0,
    ) -> Mapping[str, ContainerHealth]:
        """Poll Compose service health until required services are healthy or running.

        Services without Docker healthchecks are treated as acceptable when their
        state is running and health is none/unknown.
        """

        import time

        required = set(self._validate_services(required_services)) if required_services else set(CANONICAL_DOCKER_SERVICES)
        last_health: dict[str, ContainerHealth] = {}

        for _ in range(attempts):
            statuses = {status.service: status for status in self.ps() if status.service}
            last_health = {service: statuses.get(service, ComposeServiceStatus(service=service)).health for service in required}

            all_ready = True
            for service in required:
                status = statuses.get(service)
                if status is None:
                    all_ready = False
                    break

                state = (status.state or "").lower()
                if status.health == ContainerHealth.UNHEALTHY:
                    all_ready = False
                    break
                if status.health in {ContainerHealth.HEALTHY, ContainerHealth.NONE, ContainerHealth.UNKNOWN} and state == "running":
                    continue
                all_ready = False
                break

            if all_ready:
                return last_health

            time.sleep(interval_seconds)

        return last_health

    def image_inspect(self, image: str) -> DockerImageInfo:
        """Inspect one Docker image."""

        if not image or any(ch.isspace() for ch in image):
            raise ValueError("image must be a non-empty image reference without whitespace")

        result = self._run(["docker", "image", "inspect", image])
        self._raise_on_failure(f"Could not inspect Docker image {image}", result)

        try:
            rows = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise DockerRuntimeError(f"Could not parse docker image inspect output for {image}: {exc}", result) from exc

        row = rows[0] if rows else {}
        return DockerImageInfo(
            image=image,
            image_id=_optional_str(row.get("Id")),
            repo_tags=tuple(str(item) for item in row.get("RepoTags") or ()),
            repo_digests=tuple(str(item) for item in row.get("RepoDigests") or ()),
            created=_optional_str(row.get("Created")),
        )

    def load_image_archive(self, archive_path: str | Path) -> CommandResult:
        """Load an OCI/Docker image archive into the local Docker daemon."""

        path = Path(archive_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Image archive does not exist: {path}")

        return self._run(["docker", "load", "--input", str(path)])

    def create_network(self, name: str, *, driver: str = "bridge", internal: bool = False) -> CommandResult:
        """Create a Docker network if it does not already exist."""

        self._validate_docker_name(name, field="network")
        inspect = self._run(["docker", "network", "inspect", name], timeout=30)
        if inspect.ok:
            return inspect

        args = ["docker", "network", "create", "--driver", driver]
        if internal:
            args.append("--internal")
        args.append(name)
        return self._run(args)

    def create_volume(self, name: str) -> CommandResult:
        """Create a Docker volume if it does not already exist."""

        self._validate_docker_name(name, field="volume")
        inspect = self._run(["docker", "volume", "inspect", name], timeout=30)
        if inspect.ok:
            return inspect

        return self._run(["docker", "volume", "create", name])

    def prune_stopped_project_containers(self) -> CommandResult:
        """Remove stopped containers belonging to this Compose project only."""

        return self._run(
            [
                "docker",
                "container",
                "prune",
                "--force",
                "--filter",
                f"label=com.docker.compose.project={self.config.project_name}",
            ]
        )

    def _compose(self, action: ComposeAction) -> CommandResult:
        return self._compose_args([action.value])

    def _compose_args(self, args: Sequence[str]) -> CommandResult:
        full_args = [
            *self._compose_cmd,
            "--project-name",
            self.config.project_name,
            "--file",
            str(self.config.compose_file),
            *args,
        ]
        return self._run(full_args)

    def _run(
        self,
        args: Sequence[str],
        *,
        timeout: int | None = None,
        extra_env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        if not args:
            raise ValueError("args must not be empty")

        if any(not isinstance(arg, str) or arg == "" for arg in args):
            raise ValueError("all command args must be non-empty strings")

        env = os.environ.copy()
        env.update({str(key): str(value) for key, value in self.config.env.items()})
        env.update({str(key): str(value) for key, value in (extra_env or {}).items()})

        try:
            proc = subprocess.run(
                list(args),
                cwd=str(self.config.working_dir),
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout or self.config.timeout_seconds,
                check=False,
            )
            return CommandResult(
                args=tuple(args),
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                args=tuple(args),
                returncode=124,
                stdout=exc.stdout or "",
                stderr=exc.stderr or f"Command timed out after {timeout or self.config.timeout_seconds} seconds.",
                timed_out=True,
            )

    def _validate_config(self) -> None:
        issues: list[ValidationIssue] = []

        if not self.config.compose_file.exists():
            issues.append(
                ValidationIssue(
                    code="compose_file_missing",
                    message=f"Compose file does not exist: {self.config.compose_file}",
                    field="compose_file",
                )
            )

        if not self.config.project_name:
            issues.append(
                ValidationIssue(
                    code="project_name_missing",
                    message="Docker Compose project_name must not be empty.",
                    field="project_name",
                )
            )

        self._validate_docker_name(self.config.project_name, field="project_name")

        if not self.config.allow_outside_kx_root:
            issues.extend(validate_path_under_root(self.config.working_dir, KX_ROOT))
            if self.config.compose_file.exists():
                issues.extend(validate_path_under_root(self.config.compose_file, KX_ROOT))

        raise_if_issues(issues)

    def _resolve_compose_command(self, preference: DockerComposeBinary | None) -> tuple[str, ...]:
        if preference == DockerComposeBinary.DOCKER_COMPOSE:
            if shutil.which("docker-compose"):
                return ("docker-compose",)
            raise DockerRuntimeError("docker-compose binary was requested but not found")

        if preference == DockerComposeBinary.DOCKER_PLUGIN:
            if shutil.which("docker"):
                return ("docker", "compose")
            raise DockerRuntimeError("docker compose plugin was requested but docker was not found")

        if shutil.which("docker"):
            probe = subprocess.run(
                ["docker", "compose", "version"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if probe.returncode == 0:
                return ("docker", "compose")

        if shutil.which("docker-compose"):
            return ("docker-compose",)

        raise DockerRuntimeError("Neither docker compose nor docker-compose is available")

    def _validate_services(self, services: Iterable[str] | None) -> list[str]:
        if services is None:
            return []

        service_list = [str(service) for service in services]
        raise_if_issues(validate_service_names(service_list))
        return service_list

    def _validate_docker_name(self, name: str, *, field: str) -> None:
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")
        if not name or any(ch not in allowed for ch in name):
            raise ValidationFailed(
                (
                    ValidationIssue(
                        code="invalid_docker_name",
                        message=f"{field} contains unsupported characters: {name!r}",
                        field=field,
                    ),
                )
            )

    def _parse_json_lines_or_array(self, stdout: str) -> list[Any]:
        text = stdout.strip()
        if not text:
            return []

        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
            return [parsed]
        except json.JSONDecodeError:
            rows: list[Any] = []
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return rows

    def _normalize_health(self, row: Mapping[str, Any]) -> ContainerHealth:
        raw = (
            row.get("Health")
            or row.get("health")
            or row.get("HealthStatus")
            or row.get("health_status")
            or ""
        )
        text = str(raw).strip().lower()

        if text in {"healthy", "(healthy)"}:
            return ContainerHealth.HEALTHY
        if text in {"unhealthy", "(unhealthy)"}:
            return ContainerHealth.UNHEALTHY
        if text in {"starting", "(health: starting)"}:
            return ContainerHealth.STARTING
        if text in {"", "none", "null"}:
            return ContainerHealth.NONE

        status = str(row.get("Status") or row.get("status") or "").lower()
        if "unhealthy" in status:
            return ContainerHealth.UNHEALTHY
        if "healthy" in status:
            return ContainerHealth.HEALTHY
        if "starting" in status:
            return ContainerHealth.STARTING

        return ContainerHealth.UNKNOWN

    def _normalize_ports(self, ports: Any) -> tuple[str, ...]:
        if not ports:
            return ()

        if isinstance(ports, str):
            return tuple(part.strip() for part in ports.split(",") if part.strip())

        if isinstance(ports, Sequence) and not isinstance(ports, (str, bytes)):
            normalized: list[str] = []
            for item in ports:
                if isinstance(item, Mapping):
                    target = item.get("TargetPort") or item.get("target")
                    published = item.get("PublishedPort") or item.get("published")
                    protocol = item.get("Protocol") or item.get("protocol") or "tcp"
                    if published and target:
                        normalized.append(f"{published}->{target}/{protocol}")
                    elif target:
                        normalized.append(f"{target}/{protocol}")
                    else:
                        normalized.append(str(item))
                else:
                    normalized.append(str(item))
            return tuple(normalized)

        return (str(ports),)

    def _raise_on_failure(self, message: str, result: CommandResult) -> None:
        if not result.ok:
            raise DockerRuntimeError(message, result)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def runtime_for_instance(instance_id: str, *, project_name: str | None = None) -> DockerRuntime:
    """Convenience factory for the canonical instance runtime."""

    return DockerRuntime.for_instance(instance_id, project_name=project_name)


__all__ = [
    "DEFAULT_COMMAND_TIMEOUT_SECONDS",
    "DEFAULT_LOG_LINES",
    "DockerComposeBinary",
    "ComposeAction",
    "ContainerHealth",
    "CommandResult",
    "DockerRuntimeConfig",
    "ComposeServiceStatus",
    "DockerImageInfo",
    "DockerRuntimeError",
    "DockerRuntime",
    "runtime_for_instance",
]
