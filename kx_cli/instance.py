"""
`kx instance` command handlers for the canonical Konnaxion CLI.

This module is imported by ``kx_cli.main``. It does not own the root parser;
``kx_cli.main`` parses canonical public commands and dispatches here with
``handler(args=args, context=context)``.

The CLI must not execute Docker, firewall, database, backup, restore, or host
networking operations directly. Every operation below calls the local
Konnaxion Agent API and returns a structured mapping that ``kx_cli.main`` can
normalize into a ``CliResult``.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Sequence

import httpx

from kx_shared.konnaxion_constants import (
    DEFAULT_CAPSULE_ID,
    DEFAULT_EXPOSURE_MODE,
    DEFAULT_INSTANCE_ID,
    DEFAULT_NETWORK_PROFILE,
    InstanceState,
)


DEFAULT_AGENT_URL = "http://127.0.0.1:8765"
REQUEST_TIMEOUT_SECONDS = 120.0


class InstanceCliError(RuntimeError):
    """Raised when an instance CLI operation fails."""


class OutputFormat(StrEnum):
    """Standalone compatibility output formats."""

    TEXT = "text"
    JSON = "json"


@dataclass(frozen=True)
class InstanceCommandResult:
    """Structured result returned to ``kx_cli.main``."""

    ok: bool
    command: str
    message: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)
    issues: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentRequestConfig:
    """Connection settings for the local Konnaxion Agent API."""

    base_url: str = DEFAULT_AGENT_URL
    timeout_seconds: float = REQUEST_TIMEOUT_SECONDS
    token: str = ""

    @classmethod
    def from_context(cls, context: Any | None = None) -> "AgentRequestConfig":
        context_url = str(getattr(context, "agent_url", "") or "").strip()
        env_url = os.getenv("KX_AGENT_URL", "").strip()
        base_url = context_url or env_url or DEFAULT_AGENT_URL

        return cls(
            base_url=base_url.rstrip("/"),
            timeout_seconds=_read_float_env(
                "KX_CLI_TIMEOUT_SECONDS",
                REQUEST_TIMEOUT_SECONDS,
            ),
            token=os.getenv("KX_AGENT_TOKEN", "").strip(),
        )


# ---------------------------------------------------------------------------
# Handlers called by kx_cli.main
# ---------------------------------------------------------------------------


def create_instance(*, args: argparse.Namespace, context: Any) -> InstanceCommandResult:
    """Handle ``kx instance create``."""

    payload = {
        "instance_id": args.instance_id,
        "capsule_id": getattr(args, "capsule_id", DEFAULT_CAPSULE_ID),
        "network_profile": getattr(args, "profile", DEFAULT_NETWORK_PROFILE.value),
        "exposure_mode": getattr(args, "exposure", DEFAULT_EXPOSURE_MODE.value),
        "generate_secrets": True,
    }

    response = _agent_post(context, "/v1/instances/create", payload)
    return _result(
        "instance create",
        response,
        fallback_message=f"Create requested for instance {args.instance_id}.",
    )


def start_instance(*, args: argparse.Namespace, context: Any) -> InstanceCommandResult:
    """Handle ``kx instance start``."""

    payload = {
        "instance_id": args.instance_id,
        "run_security_gate": True,
    }

    # The current Agent API does not accept profile/exposure on start. Profile
    # changes should go through ``kx network set-profile`` before startup.
    response = _agent_post(context, "/v1/instances/start", payload)
    return _result(
        "instance start",
        response,
        fallback_message=f"Start requested for instance {args.instance_id}.",
    )


def stop_instance(*, args: argparse.Namespace, context: Any) -> InstanceCommandResult:
    """Handle ``kx instance stop``."""

    payload = {
        "instance_id": args.instance_id,
        "timeout_seconds": int(getattr(args, "timeout", None) or 60),
    }

    response = _agent_post(context, "/v1/instances/stop", payload)
    return _result(
        "instance stop",
        response,
        fallback_message=f"Stop requested for instance {args.instance_id}.",
    )


def instance_status(*, args: argparse.Namespace, context: Any) -> InstanceCommandResult:
    """Handle ``kx instance status``."""

    response = _agent_post(
        context,
        "/v1/instances/status",
        {"instance_id": args.instance_id},
    )
    return _result(
        "instance status",
        response,
        fallback_message=f"Status loaded for instance {args.instance_id}.",
    )


def instance_logs(*, args: argparse.Namespace, context: Any) -> InstanceCommandResult:
    """Handle ``kx instance logs``."""

    services = _normalize_services(getattr(args, "service", None))

    if len(services) <= 1:
        payload = {
            "instance_id": args.instance_id,
            "service": services[0] if services else None,
            "tail": int(getattr(args, "lines", 300)),
        }
        response = _agent_post(context, "/v1/instances/logs", payload)
        return _result(
            "instance logs",
            response,
            fallback_message=f"Logs loaded for instance {args.instance_id}.",
        )

    responses: dict[str, Any] = {}
    for service in services:
        responses[service] = _agent_post(
            context,
            "/v1/instances/logs",
            {
                "instance_id": args.instance_id,
                "service": service,
                "tail": int(getattr(args, "lines", 300)),
            },
        )

    return InstanceCommandResult(
        ok=all(_response_ok(item) for item in responses.values()),
        command="instance logs",
        message=f"Logs loaded for {len(responses)} service(s).",
        data={"instance_id": args.instance_id, "services": responses},
    )


def backup_instance(*, args: argparse.Namespace, context: Any) -> InstanceCommandResult:
    """Handle ``kx instance backup``."""

    payload = {
        "instance_id": args.instance_id,
        "backup_class": getattr(args, "backup_class", "manual"),
        "verify_after_create": True,
    }

    response = _agent_post(context, "/v1/instances/backup", payload)
    return _result(
        "instance backup",
        response,
        fallback_message=f"Backup requested for instance {args.instance_id}.",
    )


def restore_instance(*, args: argparse.Namespace, context: Any) -> InstanceCommandResult:
    """Handle ``kx instance restore``."""

    payload = {
        "instance_id": args.instance_id,
        "backup_id": args.backup_id,
        "create_pre_restore_backup": not bool(getattr(args, "force", False)),
    }

    response = _agent_post(context, "/v1/instances/restore", payload)
    return _result(
        "instance restore",
        response,
        fallback_message=f"Restore requested for instance {args.instance_id}.",
    )


def restore_new_instance(*, args: argparse.Namespace, context: Any) -> InstanceCommandResult:
    """Handle ``kx instance restore-new``."""

    payload = {
        "source_backup_id": args.backup_id,
        "new_instance_id": args.new_instance_id,
        "network_profile": DEFAULT_NETWORK_PROFILE.value,
    }

    response = _agent_post(context, "/v1/instances/restore-new", payload)
    return _result(
        "instance restore-new",
        response,
        fallback_message=f"Restore-new requested for instance {args.new_instance_id}.",
    )


def update_instance(*, args: argparse.Namespace, context: Any) -> InstanceCommandResult:
    """Handle ``kx instance update``."""

    capsule_path = Path(args.capsule)
    payload = {
        "instance_id": args.instance_id,
        "capsule_path": str(capsule_path),
        "create_pre_update_backup": not bool(getattr(args, "skip_backup", False)),
    }

    response = _agent_post(context, "/v1/instances/update", payload)
    return _result(
        "instance update",
        response,
        fallback_message=f"Update requested for instance {args.instance_id}.",
    )


def rollback_instance(*, args: argparse.Namespace, context: Any) -> InstanceCommandResult:
    """Handle ``kx instance rollback``."""

    payload = {
        "instance_id": args.instance_id,
        "target_release_id": getattr(args, "to_capsule_id", None),
        "restore_data": bool(getattr(args, "force", False)),
    }

    response = _agent_post(context, "/v1/instances/rollback", payload)
    return _result(
        "instance rollback",
        response,
        fallback_message=f"Rollback requested for instance {args.instance_id}.",
    )


def instance_health(*, args: argparse.Namespace, context: Any) -> InstanceCommandResult:
    """Handle ``kx instance health``."""

    response = _agent_post(
        context,
        "/v1/instances/health",
        {"instance_id": args.instance_id},
    )
    return _result(
        "instance health",
        response,
        fallback_message=f"Health loaded for instance {args.instance_id}.",
    )


# ---------------------------------------------------------------------------
# Optional standalone compatibility parser
# ---------------------------------------------------------------------------


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register ``kx instance`` commands for standalone argparse use."""

    parser = subparsers.add_parser("instance", help="Manage Konnaxion Instances.")
    parser.add_argument("--agent-url", default=DEFAULT_AGENT_URL)
    parser.add_argument("--json", action="store_true")
    instance_sub = parser.add_subparsers(dest="instance_command", required=True)

    create = instance_sub.add_parser("create")
    create.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    create.add_argument("--capsule-id", default=DEFAULT_CAPSULE_ID)
    create.add_argument("--network", dest="profile", default=DEFAULT_NETWORK_PROFILE.value)
    create.add_argument("--exposure", default=DEFAULT_EXPOSURE_MODE.value)
    create.set_defaults(func=create_instance)

    start = instance_sub.add_parser("start")
    start.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    start.add_argument("--network", dest="profile", default=None)
    start.add_argument("--force-security-check", action="store_true")
    start.set_defaults(func=start_instance)

    stop = instance_sub.add_parser("stop")
    stop.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    stop.add_argument("--timeout", type=int, default=None)
    stop.set_defaults(func=stop_instance)

    status = instance_sub.add_parser("status")
    status.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    status.set_defaults(func=instance_status)

    logs = instance_sub.add_parser("logs")
    logs.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    logs.add_argument("--service", action="append", default=None)
    logs.add_argument("--lines", type=int, default=300)
    logs.add_argument("--no-timestamps", action="store_true")
    logs.set_defaults(func=instance_logs)

    backup = instance_sub.add_parser("backup")
    backup.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    backup.add_argument("--class", dest="backup_class", default="manual")
    backup.add_argument("--note", default="")
    backup.set_defaults(func=backup_instance)

    restore = instance_sub.add_parser("restore")
    restore.add_argument("instance_id")
    restore.add_argument("--from", dest="backup_id", required=True)
    restore.add_argument("--force", action="store_true")
    restore.set_defaults(func=restore_instance)

    restore_new = instance_sub.add_parser("restore-new")
    restore_new.add_argument("--from", dest="backup_id", required=True)
    restore_new.add_argument("--new-instance-id", required=True)
    restore_new.set_defaults(func=restore_new_instance)

    update = instance_sub.add_parser("update")
    update.add_argument("instance_id")
    update.add_argument("--capsule", type=Path, required=True)
    update.add_argument("--skip-backup", action="store_true")
    update.set_defaults(func=update_instance)

    rollback = instance_sub.add_parser("rollback")
    rollback.add_argument("instance_id")
    rollback.add_argument("--to-capsule-id", default=None)
    rollback.add_argument("--force", action="store_true")
    rollback.set_defaults(func=rollback_instance)

    health = instance_sub.add_parser("health")
    health.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    health.set_defaults(func=instance_health)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kx")
    subparsers = parser.add_subparsers(dest="group", required=True)
    register(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    context = argparse.Namespace(
        agent_url=getattr(args, "agent_url", DEFAULT_AGENT_URL),
        json_output=bool(getattr(args, "json", False)),
        verbose=False,
    )

    handler = getattr(args, "func", None)
    if handler is None:
        parser.print_help()
        return 2

    try:
        result = handler(args=args, context=context)
    except InstanceCliError as exc:
        if context.json_output:
            print(json.dumps({"ok": False, "message": str(exc)}, indent=2))
        else:
            print(f"ERROR: {exc}")
        return 1

    payload = result.to_dict() if isinstance(result, InstanceCommandResult) else result
    if context.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(payload.get("message") or payload.get("command") or "Command completed.")
    return 0 if bool(payload.get("ok", True)) else 1


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _agent_post(context: Any, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    config = AgentRequestConfig.from_context(context)
    url = _join_agent_url(config.base_url, path)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "kx-cli/instance",
    }

    if config.token:
        headers["Authorization"] = f"Bearer {config.token}"

    try:
        with httpx.Client(timeout=config.timeout_seconds, headers=headers) as client:
            response = client.post(url, json=_clean_payload(payload))
    except httpx.TimeoutException as exc:
        raise InstanceCliError("Timed out while contacting Konnaxion Agent.") from exc
    except httpx.HTTPError as exc:
        raise InstanceCliError(f"Unable to contact Konnaxion Agent: {exc}") from exc

    if response.status_code >= 400:
        raise InstanceCliError(_extract_error_detail(response))

    try:
        data = response.json()
    except ValueError as exc:
        raise InstanceCliError("Konnaxion Agent returned invalid JSON.") from exc

    if not isinstance(data, dict):
        raise InstanceCliError("Konnaxion Agent returned an invalid payload.")

    return data


def _join_agent_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    clean_path = "/" + path.lstrip("/")

    if base.endswith("/v1") and clean_path.startswith("/v1/"):
        clean_path = clean_path[3:]

    return f"{base}{clean_path}"


def _clean_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _jsonable(value)
        for key, value in payload.items()
        if value is not None and value != ""
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    return value


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or f"Konnaxion Agent returned HTTP {response.status_code}."

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail

        error = payload.get("error")
        if isinstance(error, str):
            return error
        if isinstance(error, Mapping):
            message = error.get("message")
            if isinstance(message, str):
                return message

        message = payload.get("message")
        if isinstance(message, str):
            return message

    return f"Konnaxion Agent returned HTTP {response.status_code}."


def _result(command: str, response: Mapping[str, Any], *, fallback_message: str) -> InstanceCommandResult:
    data = dict(response)
    ok = _response_ok(data)
    message = str(data.get("message") or fallback_message)

    return InstanceCommandResult(
        ok=ok,
        command=command,
        message=message,
        data=data,
    )


def _response_ok(response: Mapping[str, Any]) -> bool:
    if response.get("ok") is False:
        return False

    status_value = str(
        response.get("status")
        or response.get("state")
        or response.get("security_status")
        or response.get("restore_status")
        or response.get("rollback_status")
        or ""
    )

    if status_value in {
        InstanceState.FAILED.value,
        InstanceState.SECURITY_BLOCKED.value,
        "failed",
        "FAIL",
        "FAIL_BLOCKING",
    }:
        return False

    return True


def _normalize_services(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value if str(item).strip())
    return (str(value),)


def _read_float_env(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# Backward-compatible alias for the older generated file name.
register_instance_commands = register


__all__ = [
    "AgentRequestConfig",
    "InstanceCliError",
    "InstanceCommandResult",
    "OutputFormat",
    "backup_instance",
    "build_parser",
    "create_instance",
    "instance_health",
    "instance_logs",
    "instance_status",
    "main",
    "register",
    "register_instance_commands",
    "restore_instance",
    "restore_new_instance",
    "rollback_instance",
    "start_instance",
    "stop_instance",
    "update_instance",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
