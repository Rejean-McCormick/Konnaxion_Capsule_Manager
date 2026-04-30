"""Backup commands for the canonical ``kx`` CLI.

This module exposes operator-facing backup commands and delegates privileged
backup/restore work to the local Konnaxion Agent through the Manager/Agent API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from kx_shared.konnaxion_constants import DEFAULT_INSTANCE_ID


app = typer.Typer(
    name="backup",
    help="List, verify, export, and test Konnaxion Instance backups.",
    no_args_is_help=True,
)

console = Console()

DEFAULT_AGENT_URL = "http://127.0.0.1:8714"
REQUEST_TIMEOUT_SECONDS = 120.0


@app.command("list")
def list_backups(
    instance_id: str = typer.Argument(
        DEFAULT_INSTANCE_ID,
        help="Canonical Konnaxion Instance ID.",
    ),
    agent_url: str = typer.Option(
        DEFAULT_AGENT_URL,
        "--agent-url",
        envvar="KX_AGENT_BASE_URL",
        help="Local Konnaxion Agent base URL.",
    ),
    output_json: bool = typer.Option(
        False,
        "--json",
        help="Print raw JSON output.",
    ),
) -> None:
    """List backups for a Konnaxion Instance."""

    payload = _agent_get(
        agent_url,
        f"/backups/{instance_id}",
    )

    if output_json:
        console.print_json(data=payload)
        return

    backups = _extract_list(payload, "backups")
    table = Table(title=f"Konnaxion backups for {instance_id}")
    table.add_column("Backup ID")
    table.add_column("Class")
    table.add_column("Status")
    table.add_column("Created")
    table.add_column("Size")

    for item in backups:
        table.add_row(
            str(item.get("backup_id", "")),
            str(item.get("backup_class", item.get("class", ""))),
            str(item.get("status", "")),
            str(item.get("created_at", "")),
            str(item.get("size_bytes", "")),
        )

    console.print(table)


@app.command("verify")
def verify_backup(
    backup_id: str = typer.Argument(
        ...,
        help="Backup ID to verify.",
    ),
    instance_id: str = typer.Option(
        DEFAULT_INSTANCE_ID,
        "--instance-id",
        "-i",
        help="Canonical Konnaxion Instance ID.",
    ),
    agent_url: str = typer.Option(
        DEFAULT_AGENT_URL,
        "--agent-url",
        envvar="KX_AGENT_BASE_URL",
        help="Local Konnaxion Agent base URL.",
    ),
    output_json: bool = typer.Option(
        False,
        "--json",
        help="Print raw JSON output.",
    ),
) -> None:
    """Verify a backup integrity record."""

    payload = _agent_post(
        agent_url,
        f"/backups/{instance_id}/{backup_id}/verify",
        json={},
    )

    if output_json:
        console.print_json(data=payload)
        return

    status = payload.get("status", "unknown")
    if status == "verified":
        console.print(f"[green]Backup verified:[/green] {backup_id}")
    else:
        console.print(f"[yellow]Backup verification status:[/yellow] {status}")


@app.command("test-restore")
def test_restore_backup(
    backup_id: str = typer.Argument(
        ...,
        help="Backup ID to test restore.",
    ),
    instance_id: str = typer.Option(
        DEFAULT_INSTANCE_ID,
        "--instance-id",
        "-i",
        help="Source Konnaxion Instance ID.",
    ),
    new_instance_id: str = typer.Option(
        ...,
        "--new-instance-id",
        help="Temporary restore target instance ID.",
    ),
    agent_url: str = typer.Option(
        DEFAULT_AGENT_URL,
        "--agent-url",
        envvar="KX_AGENT_BASE_URL",
        help="Local Konnaxion Agent base URL.",
    ),
    output_json: bool = typer.Option(
        False,
        "--json",
        help="Print raw JSON output.",
    ),
) -> None:
    """Run a non-destructive restore test into a new instance."""

    payload = _agent_post(
        agent_url,
        f"/backups/{instance_id}/{backup_id}/test-restore",
        json={"new_instance_id": new_instance_id},
    )

    if output_json:
        console.print_json(data=payload)
        return

    status = payload.get("status", "unknown")
    console.print(
        f"[bold]Test restore[/bold] {backup_id} -> {new_instance_id}: {status}"
    )


@app.command("create")
def create_backup(
    instance_id: str = typer.Argument(
        DEFAULT_INSTANCE_ID,
        help="Canonical Konnaxion Instance ID.",
    ),
    backup_class: str = typer.Option(
        "manual",
        "--class",
        "backup_class_",
        help="Backup class, usually manual, scheduled, pre_update, or pre_restore.",
    ),
    agent_url: str = typer.Option(
        DEFAULT_AGENT_URL,
        "--agent-url",
        envvar="KX_AGENT_BASE_URL",
        help="Local Konnaxion Agent base URL.",
    ),
    output_json: bool = typer.Option(
        False,
        "--json",
        help="Print raw JSON output.",
    ),
) -> None:
    """Create a manual backup for a Konnaxion Instance."""

    payload = _agent_post(
        agent_url,
        f"/instances/{instance_id}/backup",
        json={"backup_class": backup_class},
    )

    if output_json:
        console.print_json(data=payload)
        return

    backup_id = payload.get("backup_id", "")
    status = payload.get("status", "unknown")
    console.print(f"[green]Backup requested:[/green] {backup_id} ({status})")


@app.command("export")
def export_backup(
    backup_id: str = typer.Argument(
        ...,
        help="Backup ID to export.",
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Destination file for exported backup metadata/archive.",
    ),
    instance_id: str = typer.Option(
        DEFAULT_INSTANCE_ID,
        "--instance-id",
        "-i",
        help="Canonical Konnaxion Instance ID.",
    ),
    agent_url: str = typer.Option(
        DEFAULT_AGENT_URL,
        "--agent-url",
        envvar="KX_AGENT_BASE_URL",
        help="Local Konnaxion Agent base URL.",
    ),
) -> None:
    """Export a backup archive from the local Agent."""

    content = _agent_download(
        agent_url,
        f"/backups/{instance_id}/{backup_id}/export",
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)

    console.print(f"[green]Backup exported:[/green] {output}")


@app.command("delete")
def delete_backup(
    backup_id: str = typer.Argument(
        ...,
        help="Backup ID to delete.",
    ),
    instance_id: str = typer.Option(
        DEFAULT_INSTANCE_ID,
        "--instance-id",
        "-i",
        help="Canonical Konnaxion Instance ID.",
    ),
    agent_url: str = typer.Option(
        DEFAULT_AGENT_URL,
        "--agent-url",
        envvar="KX_AGENT_BASE_URL",
        help="Local Konnaxion Agent base URL.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Confirm deletion without prompting.",
    ),
) -> None:
    """Delete a backup record/archive through the Agent."""

    if not yes:
        confirmed = typer.confirm(f"Delete backup {backup_id} for {instance_id}?")
        if not confirmed:
            raise typer.Exit(code=1)

    payload = _agent_delete(
        agent_url,
        f"/backups/{instance_id}/{backup_id}",
    )

    status = payload.get("status", "deleted")
    console.print(f"[green]Backup deletion status:[/green] {backup_id} ({status})")


def _agent_get(agent_url: str, path: str) -> dict[str, Any]:
    """Send a GET request to the Agent."""

    return _agent_request("GET", agent_url, path)


def _agent_post(agent_url: str, path: str, *, json: dict[str, Any]) -> dict[str, Any]:
    """Send a POST request to the Agent."""

    return _agent_request("POST", agent_url, path, json=json)


def _agent_delete(agent_url: str, path: str) -> dict[str, Any]:
    """Send a DELETE request to the Agent."""

    return _agent_request("DELETE", agent_url, path)


def _agent_request(
    method: str,
    agent_url: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call the local Agent and return parsed JSON."""

    try:
        with httpx.Client(
            base_url=agent_url.rstrip("/"),
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as client:
            response = client.request(method, path, json=json)
    except httpx.TimeoutException as exc:
        raise typer.BadParameter("Timed out while contacting Konnaxion Agent.") from exc
    except httpx.HTTPError as exc:
        raise typer.BadParameter(f"Unable to contact Konnaxion Agent: {exc}") from exc

    if response.status_code >= 400:
        detail = _extract_error_detail(response)
        raise typer.BadParameter(detail)

    try:
        payload = response.json()
    except ValueError as exc:
        raise typer.BadParameter("Konnaxion Agent returned invalid JSON.") from exc

    if not isinstance(payload, dict):
        raise typer.BadParameter("Konnaxion Agent returned an invalid payload.")

    return payload


def _agent_download(agent_url: str, path: str) -> bytes:
    """Download binary content from the Agent."""

    try:
        with httpx.Client(
            base_url=agent_url.rstrip("/"),
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as client:
            response = client.get(path)
    except httpx.TimeoutException as exc:
        raise typer.BadParameter("Timed out while downloading from Konnaxion Agent.") from exc
    except httpx.HTTPError as exc:
        raise typer.BadParameter(f"Unable to contact Konnaxion Agent: {exc}") from exc

    if response.status_code >= 400:
        detail = _extract_error_detail(response)
        raise typer.BadParameter(detail)

    return response.content


def _extract_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """Extract a list of dictionaries from a response payload."""

    value = payload.get(key, [])
    if not isinstance(value, list):
        return []

    return [item for item in value if isinstance(item, dict)]


def _extract_error_detail(response: httpx.Response) -> str:
    """Extract a readable Agent error from JSON or text."""

    try:
        payload = response.json()
    except ValueError:
        return response.text or "Konnaxion Agent request failed."

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                return message

        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail

    return "Konnaxion Agent request failed."
