"""
Security commands for the canonical ``kx`` CLI.

Public/operator command implemented here:

    kx security check <INSTANCE_ID>

The CLI does not run security checks itself. It asks the local
Konnaxion Agent to run the Security Gate through the constrained Agent
API client.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import typer

from kx_manager.client import (
    AgentClientConfig,
    KonnaxionAgentClient,
    KonnaxionAgentClientError,
)
from kx_shared.konnaxion_constants import SecurityGateStatus


app = typer.Typer(
    name="security",
    help="Run Konnaxion Security Gate checks.",
    no_args_is_help=True,
)


def _status_exit_code(status_value: str | None) -> int:
    """Map Security Gate status to process exit code."""

    if status_value == SecurityGateStatus.PASS.value:
        return 0
    if status_value == SecurityGateStatus.WARN.value:
        return 0
    if status_value == SecurityGateStatus.SKIPPED.value:
        return 0
    if status_value == SecurityGateStatus.FAIL_BLOCKING.value:
        return 2
    if status_value == SecurityGateStatus.UNKNOWN.value:
        return 3
    return 1


def _format_check(check: dict[str, Any]) -> str:
    """Format a single Security Gate check for terminal output."""

    name = str(check.get("check") or check.get("name") or "unknown")
    status = str(check.get("status") or "UNKNOWN")
    message = check.get("message") or check.get("detail") or ""

    if message:
        return f"{status:13} {name} - {message}"
    return f"{status:13} {name}"


def _print_human_response(response: dict[str, Any]) -> None:
    """Print an operator-friendly security result."""

    data = response.get("data") or {}
    instance_id = response.get("instance_id") or data.get("instance_id") or "-"
    status_value = (
        response.get("security_status")
        or data.get("security_status")
        or data.get("status")
        or "UNKNOWN"
    )

    typer.echo(f"Instance: {instance_id}")
    typer.echo(f"Security Gate: {status_value}")

    message = response.get("message") or data.get("message")
    if message:
        typer.echo(f"Message: {message}")

    checks = data.get("checks") or data.get("results") or []
    if isinstance(checks, list) and checks:
        typer.echo("")
        typer.echo("Checks:")
        for check in checks:
            if isinstance(check, dict):
                typer.echo(f"  {_format_check(check)}")
            else:
                typer.echo(f"  {check}")

    blocking_failures = data.get("blocking_failures") or []
    if isinstance(blocking_failures, list) and blocking_failures:
        typer.echo("")
        typer.echo("Blocking failures:")
        for failure in blocking_failures:
            typer.echo(f"  - {failure}")


async def _run_security_check(
    *,
    instance_id: str,
    agent_url: str,
    token: str | None,
    blocking: bool,
) -> dict[str, Any]:
    """Call the local Konnaxion Agent Security Gate endpoint."""

    config = AgentClientConfig(base_url=agent_url, token=token)
    async with KonnaxionAgentClient(config) as client:
        return await client.security_check(
            instance_id=instance_id,
            blocking=blocking,
        )


@app.command("check")
def check(
    instance_id: str = typer.Argument(
        ...,
        help="Canonical Konnaxion Instance ID, for example demo-001.",
    ),
    agent_url: str = typer.Option(
        "http://127.0.0.1:8765/v1",
        "--agent-url",
        envvar="KX_AGENT_URL",
        help="Base URL for the local Konnaxion Agent API.",
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        envvar="KX_AGENT_TOKEN",
        help="Optional bearer token for the local Konnaxion Agent API.",
    ),
    blocking: bool = typer.Option(
        True,
        "--blocking/--non-blocking",
        help="Run checks in startup-blocking mode.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print raw JSON response.",
    ),
) -> None:
    """Run the Security Gate for a Konnaxion Instance."""

    try:
        response = asyncio.run(
            _run_security_check(
                instance_id=instance_id,
                agent_url=agent_url,
                token=token,
                blocking=blocking,
            )
        )
    except KonnaxionAgentClientError as exc:
        typer.echo(f"Security check failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(response, indent=2, sort_keys=True))
    else:
        _print_human_response(response)

    status_value = (
        response.get("security_status")
        or (response.get("data") or {}).get("security_status")
        or (response.get("data") or {}).get("status")
    )
    raise typer.Exit(code=_status_exit_code(status_value))


__all__ = [
    "app",
    "check",
]
