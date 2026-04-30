"""Network routes for Konnaxion Capsule Manager.

The Manager exposes user-facing network profile operations, but it must not
directly modify Docker, firewall, tunnels, host interfaces, or Traefik runtime
state. Profile validation can happen locally; applying a profile is delegated to
the Konnaxion Agent.

Canonical profile and exposure values come from the shared registry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from kx_shared.konnaxion_constants import (
    DEFAULT_EXPOSURE_MODE,
    DEFAULT_NETWORK_PROFILE,
    ExposureMode,
    NetworkProfile,
)

from kx_agent.network.profiles import (
    NetworkProfileError,
    allowed_entry_ports_for,
    forbidden_public_ports,
    get_network_profile,
    is_public_profile,
    profile_to_kx_env,
    validate_profile_selection,
)


router = APIRouter(prefix="/api/network", tags=["network"])


class NetworkProfileSummary(BaseModel):
    """Public profile description returned to the Manager UI."""

    profile: str
    exposure_mode: str
    public_mode_enabled: bool
    requires_expiration: bool
    requires_hardened_host: bool
    allowed_entry_ports: list[int]
    forbidden_public_ports: list[int]
    bind_hosts: list[str]
    notes: list[str]


class NetworkStatusResponse(BaseModel):
    """Current effective network status."""

    instance_id: str
    profile: str
    exposure_mode: str
    public_mode_enabled: bool
    public_mode_expires_at: str | None = None
    host: str | None = None
    allowed_entry_ports: list[int]
    forbidden_public_ports: list[int]


class SetNetworkProfileRequest(BaseModel):
    """Request to set an instance network profile."""

    instance_id: str = Field(..., min_length=1)
    profile: NetworkProfile
    exposure_mode: ExposureMode | None = None
    public_mode_enabled: bool | None = None
    public_mode_expires_at: str | None = None
    host: str | None = None
    dry_run: bool = False


class SetNetworkProfileResponse(BaseModel):
    """Response after validating or applying a network profile."""

    instance_id: str
    profile: str
    exposure_mode: str
    public_mode_enabled: bool
    public_mode_expires_at: str | None = None
    host: str | None = None
    dry_run: bool
    delegated_to_agent: bool
    status: str
    kx_env: dict[str, str]
    warnings: list[str] = Field(default_factory=list)


@router.get("/profiles", response_model=list[NetworkProfileSummary])
def list_network_profiles() -> list[NetworkProfileSummary]:
    """List canonical network profiles available to the Manager UI."""

    return [_profile_summary(profile) for profile in NetworkProfile]


@router.get("/profiles/{profile}", response_model=NetworkProfileSummary)
def get_network_profile_route(profile: NetworkProfile) -> NetworkProfileSummary:
    """Return details for one canonical network profile."""

    return _profile_summary(profile)


@router.get("/default", response_model=NetworkStatusResponse)
def get_default_network_profile() -> NetworkStatusResponse:
    """Return the canonical private-by-default network status."""

    spec = get_network_profile(DEFAULT_NETWORK_PROFILE)

    return NetworkStatusResponse(
        instance_id="",
        profile=spec.profile.value,
        exposure_mode=DEFAULT_EXPOSURE_MODE.value,
        public_mode_enabled=spec.public_mode_enabled,
        public_mode_expires_at=None,
        host=None,
        allowed_entry_ports=list(spec.allowed_entry_ports),
        forbidden_public_ports=list(forbidden_public_ports()),
    )


@router.post("/set-profile", response_model=SetNetworkProfileResponse)
def set_network_profile(request: SetNetworkProfileRequest) -> SetNetworkProfileResponse:
    """Validate and optionally apply a network profile to an instance.

    A dry run only validates the request and renders the canonical KX_* values.
    A non-dry-run request delegates the operation to the Agent client when that
    client is available. This route never performs host networking changes
    directly.
    """

    try:
        spec = validate_profile_selection(
            request.profile,
            exposure_mode=request.exposure_mode or get_network_profile(request.profile).exposure_mode,
            public_mode_enabled=(
                request.public_mode_enabled
                if request.public_mode_enabled is not None
                else get_network_profile(request.profile).public_mode_enabled
            ),
            public_mode_expires_at=request.public_mode_expires_at,
        )

        kx_env = profile_to_kx_env(
            spec.profile,
            public_mode_expires_at=request.public_mode_expires_at,
            host=request.host,
        )
    except NetworkProfileError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    warnings = _profile_warnings(
        profile=spec.profile,
        public_mode_expires_at=request.public_mode_expires_at,
    )

    if request.dry_run:
        return SetNetworkProfileResponse(
            instance_id=request.instance_id,
            profile=spec.profile.value,
            exposure_mode=spec.exposure_mode.value,
            public_mode_enabled=spec.public_mode_enabled,
            public_mode_expires_at=request.public_mode_expires_at,
            host=request.host,
            dry_run=True,
            delegated_to_agent=False,
            status="validated",
            kx_env=kx_env,
            warnings=warnings,
        )

    agent_response = _delegate_set_profile_to_agent(
        instance_id=request.instance_id,
        kx_env=kx_env,
        profile_payload={
            "profile": spec.profile.value,
            "exposure_mode": spec.exposure_mode.value,
            "public_mode_enabled": spec.public_mode_enabled,
            "public_mode_expires_at": request.public_mode_expires_at,
            "host": request.host,
        },
    )

    return SetNetworkProfileResponse(
        instance_id=request.instance_id,
        profile=spec.profile.value,
        exposure_mode=spec.exposure_mode.value,
        public_mode_enabled=spec.public_mode_enabled,
        public_mode_expires_at=request.public_mode_expires_at,
        host=request.host,
        dry_run=False,
        delegated_to_agent=agent_response.get("delegated_to_agent", False),
        status=str(agent_response.get("status", "pending")),
        kx_env=kx_env,
        warnings=warnings + list(agent_response.get("warnings", [])),
    )


@router.get("/{instance_id}/status", response_model=NetworkStatusResponse)
def get_instance_network_status(instance_id: str) -> NetworkStatusResponse:
    """Return network status for an instance.

    The Manager asks the Agent when available. If the Agent client is not wired
    yet, this returns the canonical default profile so the UI can still render a
    safe initial state.
    """

    if not instance_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="instance_id is required",
        )

    agent_status = _delegate_get_status_to_agent(instance_id)
    if agent_status:
        profile = NetworkProfile(agent_status.get("profile", DEFAULT_NETWORK_PROFILE.value))
        spec = get_network_profile(profile)
        return NetworkStatusResponse(
            instance_id=instance_id,
            profile=spec.profile.value,
            exposure_mode=str(agent_status.get("exposure_mode", spec.exposure_mode.value)),
            public_mode_enabled=bool(agent_status.get("public_mode_enabled", spec.public_mode_enabled)),
            public_mode_expires_at=agent_status.get("public_mode_expires_at"),
            host=agent_status.get("host"),
            allowed_entry_ports=list(allowed_entry_ports_for(spec.profile)),
            forbidden_public_ports=list(forbidden_public_ports()),
        )

    spec = get_network_profile(DEFAULT_NETWORK_PROFILE)
    return NetworkStatusResponse(
        instance_id=instance_id,
        profile=spec.profile.value,
        exposure_mode=spec.exposure_mode.value,
        public_mode_enabled=spec.public_mode_enabled,
        public_mode_expires_at=None,
        host=None,
        allowed_entry_ports=list(spec.allowed_entry_ports),
        forbidden_public_ports=list(forbidden_public_ports()),
    )


def register(app: Any) -> None:
    """Register this route module on a FastAPI app."""

    app.include_router(router)


def _profile_summary(profile: NetworkProfile) -> NetworkProfileSummary:
    spec = get_network_profile(profile)

    return NetworkProfileSummary(
        profile=spec.profile.value,
        exposure_mode=spec.exposure_mode.value,
        public_mode_enabled=spec.public_mode_enabled,
        requires_expiration=spec.requires_expiration,
        requires_hardened_host=spec.requires_hardened_host,
        allowed_entry_ports=list(spec.allowed_entry_ports),
        forbidden_public_ports=list(spec.forbidden_public_ports),
        bind_hosts=list(spec.bind_hosts),
        notes=list(spec.notes),
    )


def _profile_warnings(
    *,
    profile: NetworkProfile,
    public_mode_expires_at: str | None,
) -> list[str]:
    warnings: list[str] = []

    if is_public_profile(profile):
        warnings.append("Public exposure is explicit and must remain controlled.")

    if profile == NetworkProfile.PUBLIC_TEMPORARY:
        warnings.append("Temporary public mode must expire automatically.")

    if profile == NetworkProfile.PUBLIC_VPS:
        warnings.append("public_vps requires hardened host and firewall configuration.")

    if public_mode_expires_at and _expiration_is_in_past(public_mode_expires_at):
        warnings.append("Public mode expiration is in the past.")

    return warnings


def _expiration_is_in_past(value: str) -> bool:
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return False

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed <= datetime.now(timezone.utc)


def _delegate_set_profile_to_agent(
    *,
    instance_id: str,
    kx_env: Mapping[str, str],
    profile_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Delegate profile application to the Agent client when implemented.

    This intentionally imports lazily so the route can exist before the final
    Manager client implementation is complete.
    """

    try:
        from kx_manager.client import get_agent_client
    except (ImportError, AttributeError):
        return {
            "delegated_to_agent": False,
            "status": "validated_agent_client_missing",
            "warnings": [
                "Agent client is not wired yet; no host networking changes were applied."
            ],
        }

    client = get_agent_client()

    if not hasattr(client, "set_network_profile"):
        return {
            "delegated_to_agent": False,
            "status": "validated_agent_method_missing",
            "warnings": [
                "Agent client has no set_network_profile method; no host networking changes were applied."
            ],
        }

    return dict(
        client.set_network_profile(
            instance_id=instance_id,
            kx_env=dict(kx_env),
            profile_payload=dict(profile_payload),
        )
    )


def _delegate_get_status_to_agent(instance_id: str) -> dict[str, Any] | None:
    """Ask the Agent client for current network status when available."""

    try:
        from kx_manager.client import get_agent_client
    except (ImportError, AttributeError):
        return None

    client = get_agent_client()

    if not hasattr(client, "get_network_status"):
        return None

    result = client.get_network_status(instance_id=instance_id)
    return dict(result) if result else None
