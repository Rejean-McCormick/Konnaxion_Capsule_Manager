"""Temporary and private tunnel helpers for Konnaxion Agent.

The Konnaxion Agent does not run arbitrary tunnel commands from the UI.
Only allowlisted providers and profile-safe tunnel plans are accepted here.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

from kx_shared.errors import KonnaxionNetworkError
from kx_shared.konnaxion_constants import (
    ExposureMode,
    NetworkProfile,
)


DEFAULT_PUBLIC_TUNNEL_DURATION_HOURS: Final[int] = 2
MAX_PUBLIC_TUNNEL_DURATION_HOURS: Final[int] = 24

ALLOWED_TUNNEL_PROVIDERS: Final[frozenset[str]] = frozenset(
    {
        "cloudflared",
        "tailscale",
        "wireguard",
        "ssh-reverse",
    }
)

PRIVATE_TUNNEL_PROVIDERS: Final[frozenset[str]] = frozenset(
    {
        "tailscale",
        "wireguard",
        "ssh-reverse",
    }
)

TEMPORARY_PUBLIC_TUNNEL_PROVIDERS: Final[frozenset[str]] = frozenset(
    {
        "cloudflared",
    }
)


@dataclass(frozen=True)
class TunnelPlan:
    """Validated tunnel activation plan."""

    instance_id: str
    provider: str
    network_profile: NetworkProfile
    exposure_mode: ExposureMode
    local_url: str
    public_url: str | None = None
    expires_at: datetime | None = None
    config_file: Path | None = None

    @property
    def is_temporary_public(self) -> bool:
        """Return whether this tunnel exposes a temporary public URL."""

        return self.network_profile == NetworkProfile.PUBLIC_TEMPORARY

    @property
    def is_private_tunnel(self) -> bool:
        """Return whether this tunnel is private/VPN-style exposure."""

        return self.network_profile == NetworkProfile.PRIVATE_TUNNEL

    def validate(self) -> None:
        """Validate profile, provider, exposure, URL, and expiry alignment."""

        validate_tunnel_provider(self.provider)
        validate_local_url(self.local_url)

        if self.is_private_tunnel:
            if self.provider not in PRIVATE_TUNNEL_PROVIDERS:
                raise KonnaxionNetworkError(
                    f"Provider {self.provider!r} is not allowed for private_tunnel."
                )
            if self.exposure_mode != ExposureMode.VPN:
                raise KonnaxionNetworkError(
                    "private_tunnel requires KX_EXPOSURE_MODE=vpn."
                )

        elif self.is_temporary_public:
            if self.provider not in TEMPORARY_PUBLIC_TUNNEL_PROVIDERS:
                raise KonnaxionNetworkError(
                    f"Provider {self.provider!r} is not allowed for public_temporary."
                )
            if self.exposure_mode != ExposureMode.TEMPORARY_TUNNEL:
                raise KonnaxionNetworkError(
                    "public_temporary requires KX_EXPOSURE_MODE=temporary_tunnel."
                )
            if self.expires_at is None:
                raise KonnaxionNetworkError(
                    "public_temporary requires a mandatory expiration timestamp."
                )
            if self.expires_at <= datetime.now(UTC):
                raise KonnaxionNetworkError(
                    "public_temporary expiration must be in the future."
                )
            if self.public_url is not None:
                validate_public_url(self.public_url)

        else:
            raise KonnaxionNetworkError(
                "TunnelPlan only supports private_tunnel or public_temporary profiles."
            )


@dataclass(frozen=True)
class TunnelStatus:
    """Runtime tunnel status returned to Manager/API callers."""

    instance_id: str
    provider: str
    network_profile: NetworkProfile
    exposure_mode: ExposureMode
    active: bool
    local_url: str
    public_url: str | None = None
    expires_at: datetime | None = None
    checked_at: datetime | None = None
    detail: str = ""

    def as_dict(self) -> dict[str, str | bool | None]:
        """Return a JSON-serializable representation."""

        return {
            "instance_id": self.instance_id,
            "provider": self.provider,
            "network_profile": self.network_profile.value,
            "exposure_mode": self.exposure_mode.value,
            "active": self.active,
            "local_url": self.local_url,
            "public_url": self.public_url,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "checked_at": (self.checked_at or datetime.now(UTC)).isoformat(),
            "detail": self.detail,
        }


def build_private_tunnel_plan(
    *,
    instance_id: str,
    provider: str,
    local_url: str,
    config_file: Path | None = None,
) -> TunnelPlan:
    """Build a validated private tunnel plan."""

    plan = TunnelPlan(
        instance_id=instance_id,
        provider=provider,
        network_profile=NetworkProfile.PRIVATE_TUNNEL,
        exposure_mode=ExposureMode.VPN,
        local_url=local_url,
        config_file=config_file,
    )
    plan.validate()
    return plan


def build_temporary_public_tunnel_plan(
    *,
    instance_id: str,
    provider: str,
    local_url: str,
    duration_hours: int = DEFAULT_PUBLIC_TUNNEL_DURATION_HOURS,
    config_file: Path | None = None,
) -> TunnelPlan:
    """Build a validated temporary public tunnel plan with mandatory expiry."""

    if duration_hours < 1 or duration_hours > MAX_PUBLIC_TUNNEL_DURATION_HOURS:
        raise KonnaxionNetworkError(
            f"Temporary public tunnel duration must be between 1 and "
            f"{MAX_PUBLIC_TUNNEL_DURATION_HOURS} hours."
        )

    plan = TunnelPlan(
        instance_id=instance_id,
        provider=provider,
        network_profile=NetworkProfile.PUBLIC_TEMPORARY,
        exposure_mode=ExposureMode.TEMPORARY_TUNNEL,
        local_url=local_url,
        expires_at=datetime.now(UTC) + timedelta(hours=duration_hours),
        config_file=config_file,
    )
    plan.validate()
    return plan


def activate_tunnel(plan: TunnelPlan) -> TunnelStatus:
    """Activate an allowlisted tunnel plan.

    This function intentionally supports only known provider command shapes.
    It does not accept arbitrary shell fragments.
    """

    plan.validate()

    if plan.provider == "cloudflared":
        return _activate_cloudflared(plan)

    if plan.provider == "tailscale":
        return _activate_tailscale(plan)

    if plan.provider == "wireguard":
        return _activate_wireguard(plan)

    if plan.provider == "ssh-reverse":
        return _activate_ssh_reverse(plan)

    raise KonnaxionNetworkError(f"Unsupported tunnel provider: {plan.provider}")


def deactivate_tunnel(provider: str, *, config_file: Path | None = None) -> None:
    """Deactivate an allowlisted tunnel provider."""

    validate_tunnel_provider(provider)

    if provider == "cloudflared":
        _run_command(("pkill", "-f", "cloudflared tunnel"), allow_failure=True)
        return

    if provider == "tailscale":
        _run_command(("tailscale", "down"), allow_failure=True)
        return

    if provider == "wireguard":
        if config_file is None:
            raise KonnaxionNetworkError("WireGuard deactivation requires config_file.")
        _run_command(("wg-quick", "down", str(config_file)), allow_failure=True)
        return

    if provider == "ssh-reverse":
        _run_command(("pkill", "-f", "ssh -N -R"), allow_failure=True)
        return

    raise KonnaxionNetworkError(f"Unsupported tunnel provider: {provider}")


def tunnel_status(plan: TunnelPlan) -> TunnelStatus:
    """Return a lightweight status object for a tunnel plan."""

    plan.validate()

    if plan.expires_at and plan.expires_at <= datetime.now(UTC):
        return TunnelStatus(
            instance_id=plan.instance_id,
            provider=plan.provider,
            network_profile=plan.network_profile,
            exposure_mode=plan.exposure_mode,
            active=False,
            local_url=plan.local_url,
            public_url=plan.public_url,
            expires_at=plan.expires_at,
            checked_at=datetime.now(UTC),
            detail="Tunnel expired.",
        )

    return TunnelStatus(
        instance_id=plan.instance_id,
        provider=plan.provider,
        network_profile=plan.network_profile,
        exposure_mode=plan.exposure_mode,
        active=True,
        local_url=plan.local_url,
        public_url=plan.public_url,
        expires_at=plan.expires_at,
        checked_at=datetime.now(UTC),
        detail="Tunnel plan is valid. Provider health check not implemented.",
    )


def validate_tunnel_provider(provider: str) -> None:
    """Validate an allowlisted tunnel provider name."""

    if provider not in ALLOWED_TUNNEL_PROVIDERS:
        allowed = ", ".join(sorted(ALLOWED_TUNNEL_PROVIDERS))
        raise KonnaxionNetworkError(
            f"Unsupported tunnel provider: {provider!r}. Allowed providers: {allowed}"
        )


def validate_local_url(url: str) -> None:
    """Validate local target URL for tunnel forwarding."""

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise KonnaxionNetworkError("Tunnel local_url must use http or https.")

    if parsed.hostname not in {"127.0.0.1", "localhost", "0.0.0.0"}:
        raise KonnaxionNetworkError(
            "Tunnel local_url must target localhost, 127.0.0.1, or 0.0.0.0."
        )

    if parsed.port not in {80, 443}:
        raise KonnaxionNetworkError(
            "Tunnel local_url must target the canonical Traefik entrypoint on port 80 or 443."
        )


def validate_public_url(url: str) -> None:
    """Validate provider-returned public URL."""

    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise KonnaxionNetworkError("Tunnel public_url must use https.")

    if not parsed.hostname:
        raise KonnaxionNetworkError("Tunnel public_url must include a hostname.")


def _activate_cloudflared(plan: TunnelPlan) -> TunnelStatus:
    """Activate a temporary Cloudflare quick tunnel.

    The returned public URL is not parsed here because provider output varies.
    Manager/API code may update the resulting status once provider output is captured.
    """

    if not plan.is_temporary_public:
        raise KonnaxionNetworkError("cloudflared is only allowed for public_temporary.")

    command = (
        "cloudflared",
        "tunnel",
        "--url",
        plan.local_url,
        "--no-autoupdate",
    )
    _run_command(command, background=True)

    return TunnelStatus(
        instance_id=plan.instance_id,
        provider=plan.provider,
        network_profile=plan.network_profile,
        exposure_mode=plan.exposure_mode,
        active=True,
        local_url=plan.local_url,
        public_url=plan.public_url,
        expires_at=plan.expires_at,
        checked_at=datetime.now(UTC),
        detail="cloudflared tunnel process started.",
    )


def _activate_tailscale(plan: TunnelPlan) -> TunnelStatus:
    """Activate Tailscale for private tunnel profile."""

    if not plan.is_private_tunnel:
        raise KonnaxionNetworkError("tailscale is only allowed for private_tunnel.")

    _run_command(("tailscale", "up"))

    return TunnelStatus(
        instance_id=plan.instance_id,
        provider=plan.provider,
        network_profile=plan.network_profile,
        exposure_mode=plan.exposure_mode,
        active=True,
        local_url=plan.local_url,
        checked_at=datetime.now(UTC),
        detail="tailscale is up.",
    )


def _activate_wireguard(plan: TunnelPlan) -> TunnelStatus:
    """Activate WireGuard using an approved config file."""

    if not plan.is_private_tunnel:
        raise KonnaxionNetworkError("wireguard is only allowed for private_tunnel.")
    if plan.config_file is None:
        raise KonnaxionNetworkError("WireGuard activation requires config_file.")
    if not plan.config_file.exists():
        raise KonnaxionNetworkError(f"WireGuard config file does not exist: {plan.config_file}")

    _run_command(("wg-quick", "up", str(plan.config_file)))

    return TunnelStatus(
        instance_id=plan.instance_id,
        provider=plan.provider,
        network_profile=plan.network_profile,
        exposure_mode=plan.exposure_mode,
        active=True,
        local_url=plan.local_url,
        checked_at=datetime.now(UTC),
        detail="wireguard interface started.",
    )


def _activate_ssh_reverse(plan: TunnelPlan) -> TunnelStatus:
    """Validate SSH reverse tunnel plan.

    SSH reverse tunnels require operator-provided host/user/remote-port policy.
    This MVP helper intentionally refuses automatic activation until a stricter
    policy file is implemented.
    """

    if not plan.is_private_tunnel:
        raise KonnaxionNetworkError("ssh-reverse is only allowed for private_tunnel.")

    raise KonnaxionNetworkError(
        "ssh-reverse activation requires an explicit approved policy file and is not "
        "enabled in this MVP helper."
    )


def _run_command(
    command: tuple[str, ...],
    *,
    background: bool = False,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[str] | None:
    """Run a provider command without invoking a shell."""

    try:
        if background:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            return None

        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise KonnaxionNetworkError(f"Tunnel command was not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise KonnaxionNetworkError(
            f"Timed out while running tunnel command: {' '.join(command)}"
        ) from exc

    if completed.returncode != 0 and not allow_failure:
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        raise KonnaxionNetworkError(
            f"Tunnel command failed with exit code {completed.returncode}: {output}"
        )

    return completed
