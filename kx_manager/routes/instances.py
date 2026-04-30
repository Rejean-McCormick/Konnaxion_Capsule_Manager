"""
Konnaxion Capsule Manager instance routes.

Responsibilities:
- Expose Manager API endpoints for Konnaxion Instance lifecycle operations.
- Validate request payloads at the Manager boundary.
- Delegate privileged/system actions to Konnaxion Agent.
- Keep Docker, firewall, backup, restore, and runtime operations out of Manager.

The Manager must not:
- Start Docker directly.
- Write runtime Compose files directly.
- Open network ports directly.
- Generate or read secrets directly.
- Bypass Security Gate decisions.

Canonical API base example:
    /api/instances
"""

from __future__ import annotations

from enum import Enum, StrEnum
from typing import Any, Mapping, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

try:
    from kx_shared.konnaxion_constants import (
        DEFAULT_EXPOSURE_MODE,
        DEFAULT_NETWORK_PROFILE,
        ExposureMode,
        InstanceState,
        NetworkProfile,
    )
except ImportError:  # pragma: no cover - early scaffold fallback
    class NetworkProfile(StrEnum):
        LOCAL_ONLY = "local_only"
        INTRANET_PRIVATE = "intranet_private"
        PRIVATE_TUNNEL = "private_tunnel"
        PUBLIC_TEMPORARY = "public_temporary"
        PUBLIC_VPS = "public_vps"
        OFFLINE = "offline"

    class ExposureMode(StrEnum):
        PRIVATE = "private"
        LAN = "lan"
        VPN = "vpn"
        TEMPORARY_TUNNEL = "temporary_tunnel"
        PUBLIC = "public"

    class InstanceState(StrEnum):
        CREATED = "created"
        IMPORTING = "importing"
        VERIFYING = "verifying"
        READY = "ready"
        STARTING = "starting"
        RUNNING = "running"
        STOPPING = "stopping"
        STOPPED = "stopped"
        UPDATING = "updating"
        ROLLING_BACK = "rolling_back"
        DEGRADED = "degraded"
        FAILED = "failed"
        SECURITY_BLOCKED = "security_blocked"

    DEFAULT_NETWORK_PROFILE = NetworkProfile.INTRANET_PRIVATE
    DEFAULT_EXPOSURE_MODE = ExposureMode.PRIVATE

try:
    from kx_shared.paths import validate_safe_id
except ImportError:  # pragma: no cover - early scaffold fallback
    import re

    _SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

    def validate_safe_id(value: str, *, field_name: str = "id") -> str:
        if not isinstance(value, str) or not _SAFE_ID_RE.fullmatch(value):
            raise ValueError(f"invalid {field_name}: {value!r}")
        if "/" in value or "\\" in value or value in {".", ".."}:
            raise ValueError(f"invalid {field_name}: {value!r}")
        return value

try:
    from kx_manager.client import AgentClient, AgentClientError
except ImportError:  # pragma: no cover - early scaffold fallback
    class AgentClientError(RuntimeError):
        """Fallback Agent client error used before kx_manager.client exists."""

        def __init__(
            self,
            message: str,
            *,
            status_code: int = status.HTTP_502_BAD_GATEWAY,
            details: Any | None = None,
        ) -> None:
            super().__init__(message)
            self.status_code = status_code
            self.details = details

    class AgentClient:  # type: ignore[no-redef]
        """Fallback placeholder. Replace with real kx_manager.client.AgentClient."""

        @classmethod
        def from_env(cls) -> "AgentClient":
            return cls()

        async def request(self, method: str, path: str, json: Mapping[str, Any] | None = None) -> Any:
            raise AgentClientError(
                "kx_manager.client.AgentClient is not implemented",
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                details={"method": method, "path": path, "json": json},
            )


router = APIRouter(prefix="/instances", tags=["instances"])


class AgentClientProtocol(Protocol):
    """Protocol expected by this router from kx_manager.client.AgentClient."""

    async def request(
        self,
        method: str,
        path: str,
        json: Mapping[str, Any] | None = None,
    ) -> Any:
        ...


class ApiMessage(BaseModel):
    message: str
    details: Any | None = None


class InstanceSummary(BaseModel):
    instance_id: str
    state: str
    capsule_id: str | None = None
    capsule_version: str | None = None
    app_version: str | None = None
    network_profile: str | None = None
    exposure_mode: str | None = None
    public_mode_enabled: bool | None = None
    public_mode_expires_at: str | None = None
    host: str | None = None
    url: str | None = None
    security_status: str | None = None
    last_backup_id: str | None = None


class InstanceDetail(InstanceSummary):
    services: dict[str, Any] = Field(default_factory=dict)
    health: dict[str, Any] = Field(default_factory=dict)
    security_gate: dict[str, Any] = Field(default_factory=dict)
    backups: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateInstanceRequest(BaseModel):
    capsule_id: str = Field(..., min_length=1)
    instance_id: str | None = Field(default=None, min_length=1)
    network_profile: str = Field(default_factory=lambda: enum_value(DEFAULT_NETWORK_PROFILE))
    exposure_mode: str = Field(default_factory=lambda: enum_value(DEFAULT_EXPOSURE_MODE))
    host: str | None = None
    generate_secrets: bool = True
    run_security_gate: bool = True


class StartInstanceRequest(BaseModel):
    network_profile: str | None = None
    exposure_mode: str | None = None
    host: str | None = None
    run_security_gate: bool = True


class StopInstanceRequest(BaseModel):
    timeout_seconds: int = Field(default=60, ge=1, le=600)


class SetNetworkProfileRequest(BaseModel):
    network_profile: str
    exposure_mode: str | None = None
    host: str | None = None
    public_mode_expires_at: str | None = None
    run_security_gate: bool = True


class BackupInstanceRequest(BaseModel):
    backup_class: str = Field(default="manual", min_length=1)
    note: str | None = None
    verify_after_create: bool = True


class RestoreInstanceRequest(BaseModel):
    backup_id: str
    backup_class: str = Field(default="manual", min_length=1)
    create_pre_restore_backup: bool = True
    run_migrations: bool = True
    run_security_gate: bool = True
    run_healthchecks: bool = True


class RestoreNewInstanceRequest(BaseModel):
    from_backup_id: str
    from_backup_class: str = Field(default="manual", min_length=1)
    new_instance_id: str
    network_profile: str = Field(default_factory=lambda: enum_value(DEFAULT_NETWORK_PROFILE))
    exposure_mode: str = Field(default_factory=lambda: enum_value(DEFAULT_EXPOSURE_MODE))
    host: str | None = None


class UpdateInstanceRequest(BaseModel):
    capsule_id: str
    backup_before_update: bool = True
    run_migrations: bool = True
    run_security_gate: bool = True
    run_healthchecks: bool = True


class RollbackInstanceRequest(BaseModel):
    target_capsule_id: str | None = None
    backup_id: str | None = None
    backup_class: str | None = None
    run_security_gate: bool = True
    run_healthchecks: bool = True


class LogsQuery(BaseModel):
    service: str | None = None
    tail: int = Field(default=200, ge=1, le=5000)
    since: str | None = None


class InstanceActionResponse(BaseModel):
    accepted: bool = True
    instance_id: str
    action: str
    status: str | None = None
    message: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)


def enum_value(value: Any) -> str:
    """Return the string value for Enum/StrEnum/string values."""
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def validate_instance_id(instance_id: str) -> str:
    """Validate instance id before passing it to Agent."""
    try:
        return validate_safe_id(instance_id, field_name="instance_id")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid instance_id: {instance_id!r}",
        ) from exc


def validate_capsule_id(capsule_id: str) -> str:
    """Validate capsule id before passing it to Agent."""
    try:
        return validate_safe_id(capsule_id, field_name="capsule_id")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid capsule_id: {capsule_id!r}",
        ) from exc


def validate_profile(profile: str) -> str:
    value = enum_value(profile)
    allowed = {enum_value(item) for item in NetworkProfile}
    if value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "invalid network_profile", "allowed": sorted(allowed), "value": value},
        )
    return value


def validate_exposure_mode(mode: str) -> str:
    value = enum_value(mode)
    allowed = {enum_value(item) for item in ExposureMode}
    if value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "invalid exposure_mode", "allowed": sorted(allowed), "value": value},
        )
    return value


def model_dump(model: BaseModel) -> dict[str, Any]:
    """Pydantic v1/v2 compatible dump."""
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=True)  # type: ignore[attr-defined]
    return model.dict(exclude_none=True)


def normalize_agent_result(value: Any) -> dict[str, Any]:
    """Normalize Agent client return value into a JSON-serializable dict."""
    if value is None:
        return {}

    if isinstance(value, BaseModel):
        return model_dump(value)

    if isinstance(value, Mapping):
        return dict(value)

    if hasattr(value, "to_dict") and callable(value.to_dict):
        result = value.to_dict()
        if isinstance(result, Mapping):
            return dict(result)

    return {"value": value}


def action_response(instance_id: str, action: str, result: Any) -> InstanceActionResponse:
    """Build a consistent action response."""
    normalized = normalize_agent_result(result)
    accepted = bool(normalized.get("accepted", True))
    status_value = normalized.get("status") or normalized.get("state")
    message = normalized.get("message")

    return InstanceActionResponse(
        accepted=accepted,
        instance_id=instance_id,
        action=action,
        status=str(status_value) if status_value is not None else None,
        message=str(message) if message is not None else None,
        result=normalized,
    )


def translate_agent_error(exc: Exception) -> HTTPException:
    """Convert Agent/client exceptions to HTTP responses."""
    status_code = getattr(exc, "status_code", status.HTTP_502_BAD_GATEWAY)
    details = getattr(exc, "details", None)

    return HTTPException(
        status_code=int(status_code),
        detail={
            "message": str(exc),
            "details": details,
        },
    )


async def get_agent_client(request: Request) -> AgentClientProtocol:
    """
    Resolve Agent client from app state or create one from environment.

    Recommended app setup:
        app.state.agent_client = AgentClient(...)
    """
    client = getattr(request.app.state, "agent_client", None)
    if client is not None:
        return client

    return AgentClient.from_env()


async def agent_request(
    client: AgentClientProtocol,
    method: str,
    path: str,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Perform an Agent request and normalize errors/results."""
    try:
        result = await client.request(method, path, json=payload)
    except AgentClientError as exc:
        raise translate_agent_error(exc) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "Agent request failed", "details": str(exc)},
        ) from exc

    return normalize_agent_result(result)


@router.get("", response_model=list[InstanceSummary])
@router.get("/", response_model=list[InstanceSummary], include_in_schema=False)
async def list_instances(
    state_filter: str | None = Query(default=None, alias="state"),
    network_profile: str | None = None,
    client: AgentClientProtocol = Depends(get_agent_client),
) -> list[dict[str, Any]]:
    """List Konnaxion Instances known by the Agent."""
    if state_filter is not None:
        allowed_states = {enum_value(item) for item in InstanceState}
        if state_filter not in allowed_states:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "invalid state", "allowed": sorted(allowed_states), "value": state_filter},
            )

    if network_profile is not None:
        network_profile = validate_profile(network_profile)

    result = await agent_request(
        client,
        "GET",
        "/instances",
        {
            "state": state_filter,
            "network_profile": network_profile,
        },
    )
    instances = result.get("instances", result if isinstance(result, list) else [])
    if not isinstance(instances, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Agent returned invalid instances list",
        )
    return instances


@router.post("", response_model=InstanceActionResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=InstanceActionResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_instance(
    body: CreateInstanceRequest,
    client: AgentClientProtocol = Depends(get_agent_client),
) -> InstanceActionResponse:
    """Create a Konnaxion Instance from an imported capsule."""
    payload = model_dump(body)
    payload["capsule_id"] = validate_capsule_id(body.capsule_id)

    if body.instance_id:
        payload["instance_id"] = validate_instance_id(body.instance_id)

    payload["network_profile"] = validate_profile(body.network_profile)
    payload["exposure_mode"] = validate_exposure_mode(body.exposure_mode)

    result = await agent_request(client, "POST", "/instances", payload)
    instance_id = str(result.get("instance_id") or payload.get("instance_id") or "")
    if not instance_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Agent did not return instance_id",
        )

    return action_response(instance_id, "create", result)


@router.get("/{instance_id}", response_model=InstanceDetail)
async def get_instance(
    instance_id: str,
    client: AgentClientProtocol = Depends(get_agent_client),
) -> dict[str, Any]:
    """Return detailed instance status."""
    instance_id = validate_instance_id(instance_id)
    return await agent_request(client, "GET", f"/instances/{instance_id}")


@router.post("/{instance_id}/start", response_model=InstanceActionResponse)
async def start_instance(
    instance_id: str,
    body: StartInstanceRequest | None = None,
    client: AgentClientProtocol = Depends(get_agent_client),
) -> InstanceActionResponse:
    """Start an instance through the Agent."""
    instance_id = validate_instance_id(instance_id)
    body = body or StartInstanceRequest()
    payload = model_dump(body)

    if "network_profile" in payload:
        payload["network_profile"] = validate_profile(payload["network_profile"])

    if "exposure_mode" in payload:
        payload["exposure_mode"] = validate_exposure_mode(payload["exposure_mode"])

    result = await agent_request(client, "POST", f"/instances/{instance_id}/start", payload)
    return action_response(instance_id, "start", result)


@router.post("/{instance_id}/stop", response_model=InstanceActionResponse)
async def stop_instance(
    instance_id: str,
    body: StopInstanceRequest | None = None,
    client: AgentClientProtocol = Depends(get_agent_client),
) -> InstanceActionResponse:
    """Stop an instance through the Agent."""
    instance_id = validate_instance_id(instance_id)
    payload = model_dump(body or StopInstanceRequest())
    result = await agent_request(client, "POST", f"/instances/{instance_id}/stop", payload)
    return action_response(instance_id, "stop", result)


@router.get("/{instance_id}/status", response_model=InstanceDetail)
async def get_instance_status(
    instance_id: str,
    client: AgentClientProtocol = Depends(get_agent_client),
) -> dict[str, Any]:
    """Return instance status alias used by UI polling."""
    instance_id = validate_instance_id(instance_id)
    return await agent_request(client, "GET", f"/instances/{instance_id}/status")


@router.get("/{instance_id}/health")
async def get_instance_health(
    instance_id: str,
    client: AgentClientProtocol = Depends(get_agent_client),
) -> dict[str, Any]:
    """Return healthcheck result for an instance."""
    instance_id = validate_instance_id(instance_id)
    return await agent_request(client, "GET", f"/instances/{instance_id}/health")


@router.get("/{instance_id}/security")
async def get_instance_security(
    instance_id: str,
    client: AgentClientProtocol = Depends(get_agent_client),
) -> dict[str, Any]:
    """Return latest Security Gate report for an instance."""
    instance_id = validate_instance_id(instance_id)
    return await agent_request(client, "GET", f"/instances/{instance_id}/security")


@router.post("/{instance_id}/security/check", response_model=InstanceActionResponse)
async def run_instance_security_check(
    instance_id: str,
    client: AgentClientProtocol = Depends(get_agent_client),
) -> InstanceActionResponse:
    """Run Security Gate for an instance."""
    instance_id = validate_instance_id(instance_id)
    result = await agent_request(client, "POST", f"/instances/{instance_id}/security/check")
    return action_response(instance_id, "security.check", result)


@router.get("/{instance_id}/logs")
async def get_instance_logs(
    instance_id: str,
    service: str | None = None,
    tail: int = Query(default=200, ge=1, le=5000),
    since: str | None = None,
    client: AgentClientProtocol = Depends(get_agent_client),
) -> dict[str, Any]:
    """Return logs for an instance or a specific canonical service."""
    instance_id = validate_instance_id(instance_id)

    payload = model_dump(LogsQuery(service=service, tail=tail, since=since))
    return await agent_request(client, "GET", f"/instances/{instance_id}/logs", payload)


@router.post("/{instance_id}/backup", response_model=InstanceActionResponse)
async def create_instance_backup(
    instance_id: str,
    body: BackupInstanceRequest | None = None,
    client: AgentClientProtocol = Depends(get_agent_client),
) -> InstanceActionResponse:
    """Create an instance backup through the Agent."""
    instance_id = validate_instance_id(instance_id)
    payload = model_dump(body or BackupInstanceRequest())
    validate_safe_id(payload["backup_class"], field_name="backup_class")
    result = await agent_request(client, "POST", f"/instances/{instance_id}/backup", payload)
    return action_response(instance_id, "backup", result)


@router.get("/{instance_id}/backups")
async def list_instance_backups(
    instance_id: str,
    backup_class: str | None = None,
    client: AgentClientProtocol = Depends(get_agent_client),
) -> dict[str, Any]:
    """List backups for an instance."""
    instance_id = validate_instance_id(instance_id)

    payload: dict[str, Any] = {}
    if backup_class:
        payload["backup_class"] = validate_safe_id(backup_class, field_name="backup_class")

    return await agent_request(client, "GET", f"/instances/{instance_id}/backups", payload)


@router.post("/{instance_id}/restore", response_model=InstanceActionResponse)
async def restore_instance(
    instance_id: str,
    body: RestoreInstanceRequest,
    client: AgentClientProtocol = Depends(get_agent_client),
) -> InstanceActionResponse:
    """Restore an existing instance from a backup."""
    instance_id = validate_instance_id(instance_id)
    payload = model_dump(body)
    payload["backup_id"] = validate_safe_id(payload["backup_id"], field_name="backup_id")
    payload["backup_class"] = validate_safe_id(payload["backup_class"], field_name="backup_class")

    result = await agent_request(client, "POST", f"/instances/{instance_id}/restore", payload)
    return action_response(instance_id, "restore", result)


@router.post("/{instance_id}/restore-new", response_model=InstanceActionResponse)
async def restore_new_instance(
    instance_id: str,
    body: RestoreNewInstanceRequest,
    client: AgentClientProtocol = Depends(get_agent_client),
) -> InstanceActionResponse:
    """Create a new instance from an existing instance backup."""
    source_instance_id = validate_instance_id(instance_id)
    payload = model_dump(body)
    payload["source_instance_id"] = source_instance_id
    payload["from_backup_id"] = validate_safe_id(payload["from_backup_id"], field_name="backup_id")
    payload["from_backup_class"] = validate_safe_id(payload["from_backup_class"], field_name="backup_class")
    payload["new_instance_id"] = validate_instance_id(payload["new_instance_id"])
    payload["network_profile"] = validate_profile(payload["network_profile"])
    payload["exposure_mode"] = validate_exposure_mode(payload["exposure_mode"])

    result = await agent_request(client, "POST", f"/instances/{source_instance_id}/restore-new", payload)
    return action_response(payload["new_instance_id"], "restore-new", result)


@router.post("/{instance_id}/update", response_model=InstanceActionResponse)
async def update_instance(
    instance_id: str,
    body: UpdateInstanceRequest,
    client: AgentClientProtocol = Depends(get_agent_client),
) -> InstanceActionResponse:
    """Update an instance to a new capsule."""
    instance_id = validate_instance_id(instance_id)
    payload = model_dump(body)
    payload["capsule_id"] = validate_capsule_id(payload["capsule_id"])

    result = await agent_request(client, "POST", f"/instances/{instance_id}/update", payload)
    return action_response(instance_id, "update", result)


@router.post("/{instance_id}/rollback", response_model=InstanceActionResponse)
async def rollback_instance(
    instance_id: str,
    body: RollbackInstanceRequest | None = None,
    client: AgentClientProtocol = Depends(get_agent_client),
) -> InstanceActionResponse:
    """Rollback an instance to a previous capsule and/or backup."""
    instance_id = validate_instance_id(instance_id)
    payload = model_dump(body or RollbackInstanceRequest())

    if "target_capsule_id" in payload:
        payload["target_capsule_id"] = validate_capsule_id(payload["target_capsule_id"])

    if "backup_id" in payload:
        payload["backup_id"] = validate_safe_id(payload["backup_id"], field_name="backup_id")

    if "backup_class" in payload:
        payload["backup_class"] = validate_safe_id(payload["backup_class"], field_name="backup_class")

    result = await agent_request(client, "POST", f"/instances/{instance_id}/rollback", payload)
    return action_response(instance_id, "rollback", result)


@router.post("/{instance_id}/network", response_model=InstanceActionResponse)
async def set_instance_network_profile(
    instance_id: str,
    body: SetNetworkProfileRequest,
    client: AgentClientProtocol = Depends(get_agent_client),
) -> InstanceActionResponse:
    """Set an instance network profile through the Agent."""
    instance_id = validate_instance_id(instance_id)
    payload = model_dump(body)
    payload["network_profile"] = validate_profile(payload["network_profile"])

    if "exposure_mode" in payload:
        payload["exposure_mode"] = validate_exposure_mode(payload["exposure_mode"])

    result = await agent_request(client, "POST", f"/instances/{instance_id}/network", payload)
    return action_response(instance_id, "network.set-profile", result)


@router.delete("/{instance_id}", response_model=InstanceActionResponse)
async def delete_instance(
    instance_id: str,
    remove_data: bool = Query(default=False),
    client: AgentClientProtocol = Depends(get_agent_client),
) -> InstanceActionResponse:
    """
    Delete/de-register an instance through the Agent.

    remove_data defaults to false to avoid destructive data deletion from a
    casual UI action.
    """
    instance_id = validate_instance_id(instance_id)
    result = await agent_request(
        client,
        "DELETE",
        f"/instances/{instance_id}",
        {"remove_data": remove_data},
    )
    return action_response(instance_id, "delete", result)


__all__ = [
    "ApiMessage",
    "BackupInstanceRequest",
    "CreateInstanceRequest",
    "InstanceActionResponse",
    "InstanceDetail",
    "InstanceSummary",
    "LogsQuery",
    "RestoreInstanceRequest",
    "RestoreNewInstanceRequest",
    "RollbackInstanceRequest",
    "SetNetworkProfileRequest",
    "StartInstanceRequest",
    "StopInstanceRequest",
    "UpdateInstanceRequest",
    "action_response",
    "agent_request",
    "enum_value",
    "get_agent_client",
    "model_dump",
    "normalize_agent_result",
    "router",
    "translate_agent_error",
    "validate_capsule_id",
    "validate_exposure_mode",
    "validate_instance_id",
    "validate_profile",
]
