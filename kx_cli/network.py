"""
Konnaxion CLI network commands.

Canonical public command:

    kx network set-profile

This module validates canonical network profiles and exposure modes before any
request is sent to the Manager/Agent layer. It does not directly change host
firewall rules, Docker Compose files, or running containers.

The actual privileged operation must be performed by the Konnaxion Agent through
the Manager/Agent client boundary.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Callable, Mapping, Protocol, Sequence

from kx_shared.konnaxion_constants import (
    DEFAULT_EXPOSURE_MODE,
    DEFAULT_INSTANCE_ID,
    DEFAULT_NETWORK_PROFILE,
    ExposureMode,
    NetworkProfile,
    is_canonical_exposure_mode,
    is_canonical_network_profile,
    is_public_mode,
    require_public_expiration,
)


# ---------------------------------------------------------------------------
# CLI constants
# ---------------------------------------------------------------------------

NETWORK_COMMAND_GROUP = "network"
SET_PROFILE_COMMAND = "set-profile"
LIST_PROFILES_COMMAND = "list-profiles"
VALIDATE_COMMAND = "validate"

DEFAULT_PUBLIC_TEMPORARY_DURATION_HOURS = 4


PROFILE_DEFAULT_EXPOSURE: dict[NetworkProfile, ExposureMode] = {
    NetworkProfile.LOCAL_ONLY: ExposureMode.PRIVATE,
    NetworkProfile.INTRANET_PRIVATE: ExposureMode.PRIVATE,
    NetworkProfile.PRIVATE_TUNNEL: ExposureMode.VPN,
    NetworkProfile.PUBLIC_TEMPORARY: ExposureMode.TEMPORARY_TUNNEL,
    NetworkProfile.PUBLIC_VPS: ExposureMode.PUBLIC,
    NetworkProfile.OFFLINE: ExposureMode.PRIVATE,
}

PROFILE_DESCRIPTIONS: dict[NetworkProfile, str] = {
    NetworkProfile.LOCAL_ONLY: "Accessible only from the local machine.",
    NetworkProfile.INTRANET_PRIVATE: "Accessible from the LAN only. Canonical default.",
    NetworkProfile.PRIVATE_TUNNEL: "Accessible through a private tunnel or VPN.",
    NetworkProfile.PUBLIC_TEMPORARY: "Temporarily exposed for demos; expiration required.",
    NetworkProfile.PUBLIC_VPS: "Public VPS deployment; only approved public profile.",
    NetworkProfile.OFFLINE: "No external network exposure.",
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class NetworkCliError(Exception):
    """Base class for CLI network errors."""


class NetworkValidationError(NetworkCliError):
    """Raised when network command arguments are invalid."""


class NetworkClientError(NetworkCliError):
    """Raised when a Manager/Agent client operation fails."""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class OutputFormat(StrEnum):
    """Supported CLI output formats."""

    TEXT = "text"
    JSON = "json"


@dataclass(frozen=True)
class NetworkProfileInfo:
    """Display information for a canonical network profile."""

    profile: NetworkProfile
    default_exposure_mode: ExposureMode
    description: str
    default: bool = False
    public: bool = False
    requires_expiration: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.value,
            "default_exposure_mode": self.default_exposure_mode.value,
            "description": self.description,
            "default": self.default,
            "public": self.public,
            "requires_expiration": self.requires_expiration,
        }


@dataclass(frozen=True)
class NetworkSetProfileRequest:
    """Validated request for kx network set-profile."""

    instance_id: str
    network_profile: NetworkProfile
    exposure_mode: ExposureMode
    public_mode_enabled: bool = False
    public_mode_expires_at: datetime | None = None
    host: str | None = None
    force: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        instance_id = require_non_empty(self.instance_id, field_name="instance_id")
        profile = normalize_network_profile(self.network_profile)
        exposure = normalize_exposure_mode(self.exposure_mode)
        public_mode_enabled = bool(self.public_mode_enabled or is_public_mode(profile, exposure))

        object.__setattr__(self, "instance_id", instance_id)
        object.__setattr__(self, "network_profile", profile)
        object.__setattr__(self, "exposure_mode", exposure)
        object.__setattr__(self, "public_mode_enabled", public_mode_enabled)

        validate_profile_exposure(
            network_profile=profile,
            exposure_mode=exposure,
            public_mode_enabled=public_mode_enabled,
            public_mode_expires_at=self.public_mode_expires_at,
            force=self.force,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "network_profile": self.network_profile.value,
            "exposure_mode": self.exposure_mode.value,
            "public_mode_enabled": self.public_mode_enabled,
            "public_mode_expires_at": datetime_to_iso(self.public_mode_expires_at),
            "host": self.host,
            "force": self.force,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class NetworkCommandResult:
    """Result returned by network command handlers."""

    ok: bool
    action: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "action": self.action,
            "message": self.message,
            "payload": dict(self.payload),
        }


class NetworkClient(Protocol):
    """Protocol implemented by Manager/Agent network clients."""

    def set_profile(self, request: NetworkSetProfileRequest) -> NetworkCommandResult:
        """Apply a validated network profile request."""
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def require_non_empty(value: str, *, field_name: str) -> str:
    """Require a non-empty string."""
    normalized = str(value).strip()
    if not normalized:
        raise NetworkValidationError(f"{field_name} is required.")
    return normalized


def datetime_to_iso(value: datetime | None) -> str | None:
    """Serialize datetime as UTC ISO-8601."""
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def datetime_from_iso(value: str | None) -> datetime | None:
    """Parse ISO-8601 datetime."""
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise NetworkValidationError(
            "Datetime values must be valid ISO-8601 strings, for example "
            "2026-04-30T18:00:00Z."
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed.astimezone(UTC)


def normalize_network_profile(value: str | NetworkProfile) -> NetworkProfile:
    """Return canonical NetworkProfile enum."""
    raw = getattr(value, "value", value)
    raw = str(raw).strip()

    if not is_canonical_network_profile(raw):
        valid = ", ".join(profile.value for profile in NetworkProfile)
        raise NetworkValidationError(f"Unknown network profile: {raw}. Valid: {valid}")

    return NetworkProfile(raw)


def normalize_exposure_mode(value: str | ExposureMode) -> ExposureMode:
    """Return canonical ExposureMode enum."""
    raw = getattr(value, "value", value)
    raw = str(raw).strip()

    if not is_canonical_exposure_mode(raw):
        valid = ", ".join(mode.value for mode in ExposureMode)
        raise NetworkValidationError(f"Unknown exposure mode: {raw}. Valid: {valid}")

    return ExposureMode(raw)


def default_exposure_for_profile(profile: str | NetworkProfile) -> ExposureMode:
    """Return canonical default exposure mode for a network profile."""
    normalized = normalize_network_profile(profile)
    return PROFILE_DEFAULT_EXPOSURE[normalized]


def default_public_expiration(*, hours: int = DEFAULT_PUBLIC_TEMPORARY_DURATION_HOURS) -> datetime:
    """Return default public temporary expiration."""
    if hours <= 0:
        raise NetworkValidationError("Public temporary duration must be greater than zero.")
    return datetime.now(UTC) + timedelta(hours=hours)


def validate_profile_exposure(
    *,
    network_profile: NetworkProfile,
    exposure_mode: ExposureMode,
    public_mode_enabled: bool,
    public_mode_expires_at: datetime | None,
    force: bool = False,
) -> None:
    """Validate canonical profile/exposure combinations."""
    if network_profile == NetworkProfile.PUBLIC_TEMPORARY:
        if exposure_mode != ExposureMode.TEMPORARY_TUNNEL:
            raise NetworkValidationError(
                "public_temporary profile requires temporary_tunnel exposure mode."
            )

        require_public_expiration(
            public_mode_enabled=True,
            expires_at=datetime_to_iso(public_mode_expires_at),
        )

    if exposure_mode == ExposureMode.TEMPORARY_TUNNEL:
        require_public_expiration(
            public_mode_enabled=True,
            expires_at=datetime_to_iso(public_mode_expires_at),
        )

    if exposure_mode == ExposureMode.PUBLIC and network_profile != NetworkProfile.PUBLIC_VPS:
        raise NetworkValidationError("public exposure mode requires public_vps network profile.")

    if network_profile == NetworkProfile.PUBLIC_VPS and exposure_mode != ExposureMode.PUBLIC:
        raise NetworkValidationError("public_vps profile requires public exposure mode.")

    if public_mode_enabled:
        require_public_expiration(
            public_mode_enabled=True,
            expires_at=datetime_to_iso(public_mode_expires_at),
        )

    if public_mode_expires_at is not None and public_mode_expires_at <= datetime.now(UTC):
        raise NetworkValidationError("public_mode_expires_at must be in the future.")

    if (
        network_profile in {NetworkProfile.PUBLIC_TEMPORARY, NetworkProfile.PUBLIC_VPS}
        and not force
    ):
        # Valid, but force makes the public intent explicit for the CLI caller.
        raise NetworkValidationError(
            f"{network_profile.value} is a public-capable profile. Re-run with --force."
        )


def get_profile_infos() -> tuple[NetworkProfileInfo, ...]:
    """Return canonical profile descriptions for CLI display."""
    return tuple(
        NetworkProfileInfo(
            profile=profile,
            default_exposure_mode=PROFILE_DEFAULT_EXPOSURE[profile],
            description=PROFILE_DESCRIPTIONS[profile],
            default=profile == DEFAULT_NETWORK_PROFILE,
            public=profile in {NetworkProfile.PUBLIC_TEMPORARY, NetworkProfile.PUBLIC_VPS},
            requires_expiration=profile == NetworkProfile.PUBLIC_TEMPORARY,
        )
        for profile in NetworkProfile
    )


def build_set_profile_request(
    *,
    instance_id: str,
    profile: str | NetworkProfile,
    exposure_mode: str | ExposureMode | None = None,
    public_mode_expires_at: str | datetime | None = None,
    duration_hours: int | None = None,
    host: str | None = None,
    force: bool = False,
) -> NetworkSetProfileRequest:
    """Build and validate a set-profile request."""
    network_profile = normalize_network_profile(profile)
    exposure = (
        normalize_exposure_mode(exposure_mode)
        if exposure_mode is not None
        else default_exposure_for_profile(network_profile)
    )

    expires_at: datetime | None
    if isinstance(public_mode_expires_at, datetime):
        expires_at = public_mode_expires_at
    else:
        expires_at = datetime_from_iso(public_mode_expires_at)

    if (
        expires_at is None
        and network_profile == NetworkProfile.PUBLIC_TEMPORARY
        and duration_hours is not None
    ):
        expires_at = default_public_expiration(hours=duration_hours)

    public_enabled = is_public_mode(network_profile, exposure)

    return NetworkSetProfileRequest(
        instance_id=instance_id,
        network_profile=network_profile,
        exposure_mode=exposure,
        public_mode_enabled=public_enabled,
        public_mode_expires_at=expires_at,
        host=host,
        force=force,
        metadata={
            "source": "kx_cli.network",
            "duration_hours": duration_hours,
        },
    )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def handle_list_profiles(*, output: OutputFormat = OutputFormat.TEXT) -> NetworkCommandResult:
    """Handle kx network list-profiles."""
    profiles = [profile.to_dict() for profile in get_profile_infos()]
    return NetworkCommandResult(
        ok=True,
        action="network.list_profiles",
        message="Canonical network profiles listed.",
        payload={"profiles": profiles, "output": output.value},
    )


def handle_validate(
    *,
    profile: str,
    exposure_mode: str | None = None,
    public_mode_expires_at: str | None = None,
    duration_hours: int | None = None,
    force: bool = False,
) -> NetworkCommandResult:
    """Validate a profile/exposure combination without applying it."""
    request = build_set_profile_request(
        instance_id=DEFAULT_INSTANCE_ID,
        profile=profile,
        exposure_mode=exposure_mode,
        public_mode_expires_at=public_mode_expires_at,
        duration_hours=duration_hours,
        force=force,
    )

    return NetworkCommandResult(
        ok=True,
        action="network.validate",
        message="Network profile request is valid.",
        payload={"request": request.to_dict()},
    )


def handle_set_profile(
    *,
    instance_id: str,
    profile: str,
    exposure_mode: str | None = None,
    public_mode_expires_at: str | None = None,
    duration_hours: int | None = None,
    host: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    client: NetworkClient | None = None,
) -> NetworkCommandResult:
    """Handle kx network set-profile."""
    request = build_set_profile_request(
        instance_id=instance_id,
        profile=profile,
        exposure_mode=exposure_mode,
        public_mode_expires_at=public_mode_expires_at,
        duration_hours=duration_hours,
        host=host,
        force=force,
    )

    if dry_run or client is None:
        return NetworkCommandResult(
            ok=True,
            action="network.set_profile.dry_run",
            message=(
                "Network profile request validated. "
                "No host changes were applied because no Manager/Agent client is configured."
            ),
            payload={"request": request.to_dict()},
        )

    try:
        return client.set_profile(request)
    except Exception as exc:  # pragma: no cover - client boundary
        raise NetworkClientError(f"Failed to set network profile: {exc}") from exc


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------

def render_result(result: NetworkCommandResult, *, output: OutputFormat = OutputFormat.TEXT) -> str:
    """Render command result."""
    if output == OutputFormat.JSON:
        return json.dumps(result.to_dict(), indent=2, sort_keys=True)

    if result.action == "network.list_profiles":
        return render_profile_table(result.payload.get("profiles", ()))

    lines = [
        result.message,
        "",
        json.dumps(result.payload, indent=2, sort_keys=True),
    ]
    return "\n".join(lines)


def render_profile_table(profiles: Sequence[Mapping[str, Any]]) -> str:
    """Render canonical network profiles as plain text."""
    if not profiles:
        return "No network profiles available."

    headers = ("Profile", "Default exposure", "Default", "Public", "Expiration", "Description")
    rows = [
        (
            str(profile["profile"]),
            str(profile["default_exposure_mode"]),
            "yes" if profile.get("default") else "no",
            "yes" if profile.get("public") else "no",
            "yes" if profile.get("requires_expiration") else "no",
            str(profile["description"]),
        )
        for profile in profiles
    ]

    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]

    def fmt(row: Sequence[str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    separator = "  ".join("-" * width for width in widths)
    return "\n".join([fmt(headers), separator, *(fmt(row) for row in rows)])


# ---------------------------------------------------------------------------
# argparse integration
# ---------------------------------------------------------------------------

def add_network_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    """Register the `network` command group on an existing argparse parser."""
    parser = subparsers.add_parser(
        NETWORK_COMMAND_GROUP,
        help="Manage Konnaxion network profiles.",
    )

    network_subparsers = parser.add_subparsers(dest="network_command", required=True)

    list_parser = network_subparsers.add_parser(
        LIST_PROFILES_COMMAND,
        help="List canonical network profiles.",
    )
    add_output_argument(list_parser)
    list_parser.set_defaults(func=run_list_profiles_from_args)

    validate_parser = network_subparsers.add_parser(
        VALIDATE_COMMAND,
        help="Validate a network profile request without applying it.",
    )
    add_profile_arguments(validate_parser, include_instance=False)
    add_output_argument(validate_parser)
    validate_parser.set_defaults(func=run_validate_from_args)

    set_parser = network_subparsers.add_parser(
        SET_PROFILE_COMMAND,
        help="Set the network profile for a Konnaxion Instance.",
    )
    add_profile_arguments(set_parser, include_instance=True)
    set_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the request without applying host changes.",
    )
    add_output_argument(set_parser)
    set_parser.set_defaults(func=run_set_profile_from_args)

    return parser


def add_profile_arguments(parser: argparse.ArgumentParser, *, include_instance: bool) -> None:
    """Add shared profile arguments to a parser."""
    if include_instance:
        parser.add_argument(
            "instance_id",
            nargs="?",
            default=DEFAULT_INSTANCE_ID,
            help=f"Konnaxion Instance ID. Default: {DEFAULT_INSTANCE_ID}",
        )

    parser.add_argument(
        "profile",
        choices=[profile.value for profile in NetworkProfile],
        help="Canonical network profile.",
    )
    parser.add_argument(
        "--exposure-mode",
        choices=[mode.value for mode in ExposureMode],
        default=None,
        help="Canonical exposure mode. Defaults from selected profile.",
    )
    parser.add_argument(
        "--public-mode-expires-at",
        default=None,
        help="ISO-8601 expiration for temporary public exposure.",
    )
    parser.add_argument(
        "--duration-hours",
        type=int,
        default=None,
        help=(
            "Generate public temporary expiration this many hours from now. "
            f"Recommended default: {DEFAULT_PUBLIC_TEMPORARY_DURATION_HOURS}."
        ),
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Optional generated/resolved host for the selected profile.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Required for public-capable profiles to make public intent explicit.",
    )


def add_output_argument(parser: argparse.ArgumentParser) -> None:
    """Add common output argument."""
    parser.add_argument(
        "--output",
        choices=[output.value for output in OutputFormat],
        default=OutputFormat.TEXT.value,
        help="Output format.",
    )


def run_list_profiles_from_args(args: argparse.Namespace) -> NetworkCommandResult:
    """argparse handler for list-profiles."""
    return handle_list_profiles(output=OutputFormat(args.output))


def run_validate_from_args(args: argparse.Namespace) -> NetworkCommandResult:
    """argparse handler for validate."""
    return handle_validate(
        profile=args.profile,
        exposure_mode=args.exposure_mode,
        public_mode_expires_at=args.public_mode_expires_at,
        duration_hours=args.duration_hours,
        force=args.force,
    )


def run_set_profile_from_args(args: argparse.Namespace) -> NetworkCommandResult:
    """argparse handler for set-profile."""
    return handle_set_profile(
        instance_id=args.instance_id,
        profile=args.profile,
        exposure_mode=args.exposure_mode,
        public_mode_expires_at=args.public_mode_expires_at,
        duration_hours=args.duration_hours,
        host=args.host,
        force=args.force,
        dry_run=args.dry_run,
        client=None,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build a standalone parser for this module."""
    parser = argparse.ArgumentParser(
        prog="kx network",
        description="Manage Konnaxion network profiles.",
    )
    subparsers = parser.add_subparsers(dest="network_command", required=True)

    list_parser = subparsers.add_parser(
        LIST_PROFILES_COMMAND,
        help="List canonical network profiles.",
    )
    add_output_argument(list_parser)
    list_parser.set_defaults(func=run_list_profiles_from_args)

    validate_parser = subparsers.add_parser(
        VALIDATE_COMMAND,
        help="Validate a network profile request.",
    )
    add_profile_arguments(validate_parser, include_instance=False)
    add_output_argument(validate_parser)
    validate_parser.set_defaults(func=run_validate_from_args)

    set_parser = subparsers.add_parser(
        SET_PROFILE_COMMAND,
        help="Set network profile.",
    )
    add_profile_arguments(set_parser, include_instance=True)
    set_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the request without applying host changes.",
    )
    add_output_argument(set_parser)
    set_parser.set_defaults(func=run_set_profile_from_args)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Standalone entrypoint for `python -m kx_cli.network`."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = args.func(args)
        output = OutputFormat(getattr(args, "output", OutputFormat.TEXT.value))
        print(render_result(result, output=output))
        return 0 if result.ok else 1
    except NetworkCliError as exc:
        print(f"network error: {exc}")
        return 2


__all__ = [
    "DEFAULT_PUBLIC_TEMPORARY_DURATION_HOURS",
    "LIST_PROFILES_COMMAND",
    "NETWORK_COMMAND_GROUP",
    "PROFILE_DEFAULT_EXPOSURE",
    "PROFILE_DESCRIPTIONS",
    "SET_PROFILE_COMMAND",
    "VALIDATE_COMMAND",
    "NetworkCliError",
    "NetworkClient",
    "NetworkClientError",
    "NetworkCommandResult",
    "NetworkProfileInfo",
    "NetworkSetProfileRequest",
    "NetworkValidationError",
    "OutputFormat",
    "add_network_parser",
    "add_output_argument",
    "add_profile_arguments",
    "build_parser",
    "build_set_profile_request",
    "datetime_from_iso",
    "datetime_to_iso",
    "default_exposure_for_profile",
    "default_public_expiration",
    "get_profile_infos",
    "handle_list_profiles",
    "handle_set_profile",
    "handle_validate",
    "main",
    "normalize_exposure_mode",
    "normalize_network_profile",
    "render_profile_table",
    "render_result",
    "require_non_empty",
    "run_list_profiles_from_args",
    "run_set_profile_from_args",
    "run_validate_from_args",
    "validate_profile_exposure",
]
