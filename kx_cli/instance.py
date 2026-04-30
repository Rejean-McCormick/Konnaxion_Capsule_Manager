"""
`kx instance` CLI commands for Konnaxion.

Canonical public/operator commands implemented here:

    kx instance create
    kx instance start
    kx instance stop
    kx instance status
    kx instance logs
    kx instance backup
    kx instance restore
    kx instance restore-new
    kx instance update
    kx instance rollback
    kx instance health

The CLI is an operator interface. It must not directly control Docker, firewall,
database services, backups, or host networking. It sends requests to the local
Konnaxion Capsule Manager, which delegates privileged operations to the
Konnaxion Agent.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from kx_shared.konnaxion_constants import (
    DEFAULT_EXPOSURE_MODE,
    DEFAULT_INSTANCE_ID,
    DEFAULT_NETWORK_PROFILE,
    InstanceState,
    NetworkProfile,
    ExposureMode,
)


class InstanceCliError(RuntimeError):
    """Raised when an instance CLI command fails."""


class OutputFormat(StrEnum):
    """Supported CLI output formats."""

    TEXT = "text"
    JSON = "json"


@dataclass(frozen=True)
class ManagerClientConfig:
    """Connection settings for the local Capsule Manager API."""

    base_url: str
    token: str = ""
    timeout_seconds: int = 30

    @classmethod
    def from_environment(cls) -> "ManagerClientConfig":
        host = os.getenv("KX_MANAGER_HOST", "127.0.0.1").strip() or "127.0.0.1"
        port = os.getenv("KX_MANAGER_PORT", "8780").strip() or "8780"
        scheme = os.getenv("KX_MANAGER_SCHEME", "http").strip() or "http"
        explicit_url = os.getenv("KX_MANAGER_URL", "").strip()

        base_url = explicit_url.rstrip("/") if explicit_url else f"{scheme}://{host}:{port}"

        return cls(
            base_url=base_url,
            token=os.getenv("KX_MANAGER_TOKEN", "").strip(),
            timeout_seconds=read_int_env("KX_CLI_TIMEOUT_SECONDS", 30),
        )


class ManagerClient:
    """Small standard-library HTTP client for Manager API calls."""

    def __init__(self, config: ManagerClientConfig) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")

    def get(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, *, body: Mapping[str, Any] | None = None) -> Any:
        return self.request("POST", path, body=body)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> Any:
        query = ""

        if params:
            clean_params = {
                key: value
                for key, value in params.items()
                if value is not None and value != ""
            }
            if clean_params:
                query = "?" + urlencode(clean_params)

        url = f"{self.base_url}{path}{query}"
        payload = None

        headers = {
            "Accept": "application/json",
            "User-Agent": "kx-cli/instance",
        }

        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"

        request = Request(url, data=payload, headers=headers, method=method)

        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise InstanceCliError(
                f"Manager API returned HTTP {exc.code}: {detail or exc.reason}"
            ) from exc
        except URLError as exc:
            raise InstanceCliError(f"Cannot reach Konnaxion Capsule Manager: {exc}") from exc
        except TimeoutError as exc:
            raise InstanceCliError("Konnaxion Capsule Manager request timed out.") from exc

        if not response_body:
            return {}

        try:
            return json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise InstanceCliError("Manager API returned invalid JSON.") from exc


def register_instance_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register `kx instance ...` commands on the root CLI parser."""

    parser = subparsers.add_parser(
        "instance",
        help="Manage Konnaxion Instances.",
    )

    parser.add_argument(
        "--manager-url",
        default=os.getenv("KX_MANAGER_URL", ""),
        help="Override Konnaxion Capsule Manager API URL.",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("KX_MANAGER_TOKEN", ""),
        help="Bearer token for Konnaxion Capsule Manager API.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=read_int_env("KX_CLI_TIMEOUT_SECONDS", 30),
        help="Manager API timeout in seconds.",
    )
    parser.add_argument(
        "--output",
        choices=[item.value for item in OutputFormat],
        default=OutputFormat.TEXT.value,
        help="Output format.",
    )

    instance_subparsers = parser.add_subparsers(dest="instance_command")

    create_parser = instance_subparsers.add_parser("create", help="Create a Konnaxion Instance.")
    create_parser.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    create_parser.add_argument("--capsule-id", default="")
    create_parser.add_argument(
        "--network",
        "--network-profile",
        dest="network_profile",
        default=DEFAULT_NETWORK_PROFILE.value,
        choices=[item.value for item in NetworkProfile],
    )
    create_parser.add_argument(
        "--exposure",
        "--exposure-mode",
        dest="exposure_mode",
        default=DEFAULT_EXPOSURE_MODE.value,
        choices=[item.value for item in ExposureMode],
    )
    create_parser.add_argument("--host", default="")
    create_parser.add_argument("--admin-email", default="")
    create_parser.add_argument("--generate-secrets", action=argparse.BooleanOptionalAction, default=True)
    create_parser.set_defaults(func=cmd_create)

    start_parser = instance_subparsers.add_parser("start", help="Start a Konnaxion Instance.")
    start_parser.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    start_parser.add_argument(
        "--network",
        "--network-profile",
        dest="network_profile",
        default="",
        choices=[""] + [item.value for item in NetworkProfile],
    )
    start_parser.add_argument(
        "--exposure",
        "--exposure-mode",
        dest="exposure_mode",
        default="",
        choices=[""] + [item.value for item in ExposureMode],
    )
    start_parser.add_argument("--host", default="")
    start_parser.add_argument("--public-mode-expires-at", default="")
    start_parser.add_argument("--wait", action="store_true")
    start_parser.set_defaults(func=cmd_start)

    stop_parser = instance_subparsers.add_parser("stop", help="Stop a Konnaxion Instance.")
    stop_parser.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    stop_parser.add_argument("--force", action="store_true")
    stop_parser.add_argument("--timeout-seconds", type=int, default=60)
    stop_parser.set_defaults(func=cmd_stop)

    status_parser = instance_subparsers.add_parser("status", help="Show Konnaxion Instance status.")
    status_parser.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    status_parser.set_defaults(func=cmd_status)

    logs_parser = instance_subparsers.add_parser("logs", help="Show Konnaxion Instance logs.")
    logs_parser.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    logs_parser.add_argument("--service", default="")
    logs_parser.add_argument("--tail", type=int, default=200)
    logs_parser.add_argument("--since", default="")
    logs_parser.add_argument("--follow", action="store_true")
    logs_parser.set_defaults(func=cmd_logs)

    backup_parser = instance_subparsers.add_parser("backup", help="Create an instance backup.")
    backup_parser.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    backup_parser.add_argument("--class", dest="backup_class", default="manual")
    backup_parser.add_argument("--label", default="")
    backup_parser.add_argument("--reason", default="")
    backup_parser.add_argument("--verify", action=argparse.BooleanOptionalAction, default=True)
    backup_parser.set_defaults(func=cmd_backup)

    restore_parser = instance_subparsers.add_parser("restore", help="Restore an instance from backup.")
    restore_parser.add_argument("instance_id")
    restore_parser.add_argument("--from", dest="backup_id", required=True)
    restore_parser.add_argument("--reason", default="")
    restore_parser.add_argument("--pre-restore-backup", action=argparse.BooleanOptionalAction, default=True)
    restore_parser.add_argument("--run-migrations", action=argparse.BooleanOptionalAction, default=True)
    restore_parser.add_argument("--run-security-gate", action=argparse.BooleanOptionalAction, default=True)
    restore_parser.add_argument("--run-healthchecks", action=argparse.BooleanOptionalAction, default=True)
    restore_parser.set_defaults(func=cmd_restore)

    restore_new_parser = instance_subparsers.add_parser(
        "restore-new",
        help="Restore a backup into a new Konnaxion Instance.",
    )
    restore_new_parser.add_argument("--from", dest="backup_id", required=True)
    restore_new_parser.add_argument("--new-instance-id", required=True)
    restore_new_parser.add_argument(
        "--network",
        "--network-profile",
        dest="network_profile",
        default=DEFAULT_NETWORK_PROFILE.value,
        choices=[item.value for item in NetworkProfile],
    )
    restore_new_parser.add_argument(
        "--exposure",
        "--exposure-mode",
        dest="exposure_mode",
        default=DEFAULT_EXPOSURE_MODE.value,
        choices=[item.value for item in ExposureMode],
    )
    restore_new_parser.add_argument("--reason", default="")
    restore_new_parser.set_defaults(func=cmd_restore_new)

    update_parser = instance_subparsers.add_parser("update", help="Update an instance to a new capsule.")
    update_parser.add_argument("instance_id")
    update_parser.add_argument("--capsule-id", required=True)
    update_parser.add_argument("--backup-first", action=argparse.BooleanOptionalAction, default=True)
    update_parser.add_argument("--run-migrations", action=argparse.BooleanOptionalAction, default=True)
    update_parser.add_argument("--run-security-gate", action=argparse.BooleanOptionalAction, default=True)
    update_parser.add_argument("--run-healthchecks", action=argparse.BooleanOptionalAction, default=True)
    update_parser.set_defaults(func=cmd_update)

    rollback_parser = instance_subparsers.add_parser("rollback", help="Rollback an instance.")
    rollback_parser.add_argument("instance_id")
    rollback_parser.add_argument("--to-capsule-id", default="")
    rollback_parser.add_argument("--from-backup-id", default="")
    rollback_parser.add_argument("--reason", default="")
    rollback_parser.set_defaults(func=cmd_rollback)

    health_parser = instance_subparsers.add_parser("health", help="Run instance healthchecks.")
    health_parser.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    health_parser.add_argument("--wait", action="store_true")
    health_parser.add_argument("--timeout-seconds", type=int, default=120)
    health_parser.set_defaults(func=cmd_health)

    parser.set_defaults(func=cmd_instance_help, instance_parser=parser)


def cmd_instance_help(args: argparse.Namespace) -> int:
    """Print instance command help when no subcommand is selected."""

    parser = getattr(args, "instance_parser", None)
    if parser is not None:
        parser.print_help()
    return 2


def cmd_create(args: argparse.Namespace) -> int:
    client = build_client(args)

    payload = {
        "instance_id": args.instance_id,
        "capsule_id": args.capsule_id,
        "network_profile": args.network_profile,
        "exposure_mode": args.exposure_mode,
        "host": args.host,
        "admin_email": args.admin_email,
        "generate_secrets": args.generate_secrets,
    }

    response = client.post("/instances", body=payload)
    return print_response(response, args.output, title="Instance create requested")


def cmd_start(args: argparse.Namespace) -> int:
    client = build_client(args)

    payload = {
        "network_profile": args.network_profile,
        "exposure_mode": args.exposure_mode,
        "host": args.host,
        "public_mode_expires_at": args.public_mode_expires_at,
        "wait": args.wait,
    }

    response = client.post(f"/instances/{args.instance_id}/start", body=payload)
    return print_response(response, args.output, title="Instance start requested")


def cmd_stop(args: argparse.Namespace) -> int:
    client = build_client(args)

    payload = {
        "force": args.force,
        "timeout_seconds": args.timeout_seconds,
    }

    response = client.post(f"/instances/{args.instance_id}/stop", body=payload)
    return print_response(response, args.output, title="Instance stop requested")


def cmd_status(args: argparse.Namespace) -> int:
    client = build_client(args)
    response = client.get(f"/instances/{args.instance_id}")
    return print_response(response, args.output, title="Instance status")


def cmd_logs(args: argparse.Namespace) -> int:
    client = build_client(args)

    response = client.get(
        f"/instances/{args.instance_id}/logs",
        params={
            "service": args.service,
            "tail": args.tail,
            "since": args.since,
            "follow": str(args.follow).lower(),
        },
    )

    if args.output == OutputFormat.JSON.value:
        return print_response(response, args.output)

    if isinstance(response, dict):
        logs = response.get("logs") or response.get("data") or response.get("text")
        if isinstance(logs, str):
            print(logs)
            return 0

    return print_response(response, args.output, title="Instance logs")


def cmd_backup(args: argparse.Namespace) -> int:
    client = build_client(args)

    payload = {
        "backup_class": args.backup_class,
        "label": args.label,
        "reason": args.reason,
        "verify_after_create": args.verify,
        "include_database": True,
        "include_media": True,
        "include_env_fingerprint": True,
    }

    response = client.post(f"/instances/{args.instance_id}/backups", body=payload)
    return print_response(response, args.output, title="Backup requested")


def cmd_restore(args: argparse.Namespace) -> int:
    client = build_client(args)

    payload = {
        "backup_id": args.backup_id,
        "create_pre_restore_backup": args.pre_restore_backup,
        "run_migrations": args.run_migrations,
        "run_security_gate": args.run_security_gate,
        "run_healthchecks": args.run_healthchecks,
        "reason": args.reason,
    }

    response = client.post(f"/instances/{args.instance_id}/restore", body=payload)
    return print_response(response, args.output, title="Restore requested")


def cmd_restore_new(args: argparse.Namespace) -> int:
    client = build_client(args)

    payload = {
        "backup_id": args.backup_id,
        "new_instance_id": args.new_instance_id,
        "network_profile": args.network_profile,
        "exposure_mode": args.exposure_mode,
        "reason": args.reason,
        "run_migrations": True,
        "run_security_gate": True,
        "run_healthchecks": True,
    }

    response = client.post("/instances/restore-new", body=payload)
    return print_response(response, args.output, title="Restore-new requested")


def cmd_update(args: argparse.Namespace) -> int:
    client = build_client(args)

    payload = {
        "capsule_id": args.capsule_id,
        "backup_first": args.backup_first,
        "run_migrations": args.run_migrations,
        "run_security_gate": args.run_security_gate,
        "run_healthchecks": args.run_healthchecks,
    }

    response = client.post(f"/instances/{args.instance_id}/update", body=payload)
    return print_response(response, args.output, title="Instance update requested")


def cmd_rollback(args: argparse.Namespace) -> int:
    client = build_client(args)

    if not args.to_capsule_id and not args.from_backup_id:
        raise InstanceCliError(
            "Rollback requires --to-capsule-id or --from-backup-id."
        )

    payload = {
        "to_capsule_id": args.to_capsule_id,
        "from_backup_id": args.from_backup_id,
        "reason": args.reason,
    }

    response = client.post(f"/instances/{args.instance_id}/rollback", body=payload)
    return print_response(response, args.output, title="Rollback requested")


def cmd_health(args: argparse.Namespace) -> int:
    client = build_client(args)

    response = client.get(
        f"/instances/{args.instance_id}/health",
        params={
            "wait": str(args.wait).lower(),
            "timeout_seconds": args.timeout_seconds,
        },
    )

    return print_response(response, args.output, title="Instance health")


def build_client(args: argparse.Namespace) -> ManagerClient:
    """Build Manager client from args and environment."""

    config = ManagerClientConfig.from_environment()

    if getattr(args, "manager_url", ""):
        config = ManagerClientConfig(
            base_url=args.manager_url.rstrip("/"),
            token=args.token or config.token,
            timeout_seconds=args.timeout,
        )
    else:
        config = ManagerClientConfig(
            base_url=config.base_url,
            token=args.token or config.token,
            timeout_seconds=args.timeout,
        )

    return ManagerClient(config)


def print_response(
    response: Any,
    output_format: str,
    *,
    title: str = "",
) -> int:
    """Print a Manager API response."""

    if output_format == OutputFormat.JSON.value:
        print(json.dumps(response, indent=2, sort_keys=True))
        return exit_code_from_response(response)

    if title:
        print(title)

    if isinstance(response, dict):
        print_mapping(response)
    elif isinstance(response, list):
        print_list(response)
    else:
        print(response)

    return exit_code_from_response(response)


def print_mapping(data: Mapping[str, Any], *, indent: int = 0) -> None:
    """Print a readable mapping."""

    prefix = " " * indent

    priority_keys = (
        "ok",
        "operation",
        "instance_id",
        "new_instance_id",
        "backup_id",
        "source_backup_id",
        "status",
        "state",
        "network_profile",
        "exposure_mode",
        "url",
        "host",
        "message",
    )

    printed = set()

    for key in priority_keys:
        if key in data:
            print(f"{prefix}{key}: {format_value(data[key])}")
            printed.add(key)

    for key in sorted(k for k in data.keys() if k not in printed):
        value = data[key]
        if isinstance(value, dict):
            print(f"{prefix}{key}:")
            print_mapping(value, indent=indent + 2)
        elif isinstance(value, list):
            print(f"{prefix}{key}:")
            print_list(value, indent=indent + 2)
        else:
            print(f"{prefix}{key}: {format_value(value)}")


def print_list(items: Sequence[Any], *, indent: int = 0) -> None:
    """Print a readable list."""

    prefix = " " * indent

    if not items:
        print(f"{prefix}[]")
        return

    for index, item in enumerate(items, start=1):
        if isinstance(item, dict):
            label = item.get("instance_id") or item.get("backup_id") or item.get("id") or index
            print(f"{prefix}- {label}")
            print_mapping(item, indent=indent + 2)
        else:
            print(f"{prefix}- {format_value(item)}")


def format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"

    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)

    return str(value)


def exit_code_from_response(response: Any) -> int:
    """Return a process exit code based on response content."""

    if isinstance(response, dict):
        ok = response.get("ok")
        if ok is False:
            return 1

        state = response.get("state") or response.get("status")

        if state in {
            InstanceState.FAILED.value,
            InstanceState.SECURITY_BLOCKED.value,
            "failed",
            "FAIL",
            "FAIL_BLOCKING",
        }:
            return 1

    return 0


def read_int_env(key: str, default: int) -> int:
    raw = os.getenv(key)

    if raw is None or raw.strip() == "":
        return default

    try:
        return int(raw)
    except ValueError:
        return default


def main(argv: Sequence[str] | None = None) -> int:
    """Standalone debug entrypoint for this module."""

    parser = argparse.ArgumentParser(prog="kx")
    subparsers = parser.add_subparsers(dest="command")
    register_instance_commands(subparsers)
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 2

    try:
        return int(args.func(args))
    except InstanceCliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
