"""
HTTP API surface for the Konnaxion Agent.

The Agent API is intentionally narrow. It exposes explicit, allowlisted
operations for the Konnaxion Capsule Manager and never accepts arbitrary
shell commands, arbitrary Docker commands, arbitrary host paths, or
unvalidated service names.

The actual privileged work belongs in ``kx_agent.actions`` and related
modules. This file defines request/response contracts and routes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from kx_shared.konnaxion_constants import (
    AGENT_NAME,
    APP_VERSION,
    DEFAULT_EXPOSURE_MODE,
    DEFAULT_NETWORK_PROFILE,
    DockerService,
    ExposureMode,
    InstanceState,
    KX_ROOT,
    MANAGER_NAME,
    NetworkProfile,
    PARAM_VERSION,
    RestoreStatus,
    RollbackStatus,
    SecurityGateStatus,
)


API_VERSION = "v1"
API_PREFIX = f"/{API_VERSION}"


AgentActionName = Literal[
    "capsule_import",
    "capsule_verify",
    "instance_create",
    "instance_start",
    "instance_stop",
    "instance_status",
    "instance_logs",
    "instance_backup",
    "instance_restore",
    "instance_restore_new",
    "instance_update",
    "instance_rollback",
    "instance_health",
    "security_check",
    "network_set_profile",
]


class AgentAPIError(RuntimeError):
    """Raised when an Agent action cannot be completed."""


class AgentActionHandler(Protocol):
    """Interface implemented by the privileged Agent action dispatcher."""

    async def run(self, action: AgentActionName, payload: dict[str, Any]) -> dict[str, Any]:
        """Run a single allowlisted Agent action."""


class UnconfiguredActionHandler:
    """Default handler used until kx_agent.actions is wired in."""

    async def run(self, action: AgentActionName, payload: dict[str, Any]) -> dict[str, Any]:
        raise AgentAPIError(
            f"Agent action dispatcher is not configured for action: {action}"
        )


class APIModel(BaseModel):
    """Base Pydantic model for Agent API contracts."""

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
        str_strip_whitespace=True,
    )


class HealthResponse(APIModel):
    status: Literal["ok"]
    service: str
    api_version: str
    app_version: str
    param_version: str
    timestamp: datetime


class AgentInfoResponse(APIModel):
    service: str
    manager: str
    api_version: str
    app_version: str
    param_version: str
    root_path: str
    default_network_profile: NetworkProfile
    default_exposure_mode: ExposureMode
    allowed_services: list[str]


class ErrorResponse(APIModel):
    error: str
    detail: str | None = None


class InstanceRequest(APIModel):
    instance_id: str = Field(..., min_length=1, max_length=128)


class CapsuleImportRequest(APIModel):
    capsule_path: str = Field(..., min_length=1)
    instance_id: str = Field(..., min_length=1, max_length=128)
    network_profile: NetworkProfile = DEFAULT_NETWORK_PROFILE


class CapsuleVerifyRequest(APIModel):
    capsule_path: str = Field(..., min_length=1)


class InstanceCreateRequest(APIModel):
    instance_id: str = Field(..., min_length=1, max_length=128)
    capsule_id: str = Field(..., min_length=1, max_length=256)
    network_profile: NetworkProfile = DEFAULT_NETWORK_PROFILE
    exposure_mode: ExposureMode = DEFAULT_EXPOSURE_MODE
    generate_secrets: bool = True


class InstanceStartRequest(APIModel):
    instance_id: str = Field(..., min_length=1, max_length=128)
    run_security_gate: bool = True


class InstanceStopRequest(APIModel):
    instance_id: str = Field(..., min_length=1, max_length=128)
    timeout_seconds: int = Field(default=60, ge=5, le=600)


class InstanceStatusRequest(APIModel):
    instance_id: str = Field(..., min_length=1, max_length=128)


class InstanceLogsRequest(APIModel):
    instance_id: str = Field(..., min_length=1, max_length=128)
    service: DockerService | None = None
    tail: int = Field(default=200, ge=1, le=5000)


class InstanceBackupRequest(APIModel):
    instance_id: str = Field(..., min_length=1, max_length=128)
    backup_class: Literal["manual", "scheduled", "pre_update", "pre_restore"] = "manual"
    verify_after_create: bool = True


class InstanceRestoreRequest(APIModel):
    instance_id: str = Field(..., min_length=1, max_length=128)
    backup_id: str = Field(..., min_length=1, max_length=256)
    create_pre_restore_backup: bool = True


class InstanceRestoreNewRequest(APIModel):
    source_backup_id: str = Field(..., min_length=1, max_length=256)
    new_instance_id: str = Field(..., min_length=1, max_length=128)
    network_profile: NetworkProfile = DEFAULT_NETWORK_PROFILE


class InstanceUpdateRequest(APIModel):
    instance_id: str = Field(..., min_length=1, max_length=128)
    capsule_path: str = Field(..., min_length=1)
    create_pre_update_backup: bool = True


class InstanceRollbackRequest(APIModel):
    instance_id: str = Field(..., min_length=1, max_length=128)
    target_release_id: str | None = Field(default=None, max_length=256)
    restore_data: bool = True


class InstanceHealthRequest(APIModel):
    instance_id: str = Field(..., min_length=1, max_length=128)


class SecurityCheckRequest(APIModel):
    instance_id: str = Field(..., min_length=1, max_length=128)
    blocking: bool = True


class NetworkSetProfileRequest(APIModel):
    instance_id: str = Field(..., min_length=1, max_length=128)
    network_profile: NetworkProfile
    exposure_mode: ExposureMode = DEFAULT_EXPOSURE_MODE
    public_mode_expires_at: datetime | None = None


class ActionResponse(APIModel):
    ok: bool
    action: AgentActionName
    instance_id: str | None = None
    state: InstanceState | None = None
    security_status: SecurityGateStatus | None = None
    restore_status: RestoreStatus | None = None
    rollback_status: RollbackStatus | None = None
    message: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def get_action_handler(request: Request) -> AgentActionHandler:
    """Resolve the Agent action handler from FastAPI app state."""

    handler = getattr(request.app.state, "action_handler", None)
    if handler is None:
        return UnconfiguredActionHandler()
    return handler


async def run_agent_action(
    handler: AgentActionHandler,
    action: AgentActionName,
    payload: APIModel,
) -> ActionResponse:
    """Execute one allowlisted Agent action and normalize API errors."""

    try:
        result = await handler.run(action, payload.model_dump(mode="json", exclude_none=True))
    except AgentAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return ActionResponse(
        ok=bool(result.get("ok", True)),
        action=action,
        instance_id=result.get("instance_id"),
        state=result.get("state"),
        security_status=result.get("security_status"),
        restore_status=result.get("restore_status"),
        rollback_status=result.get("rollback_status"),
        message=result.get("message"),
        data=result.get("data", {}),
    )


router = APIRouter(prefix=API_PREFIX)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return basic Agent process health."""

    return HealthResponse(
        status="ok",
        service=AGENT_NAME,
        api_version=API_VERSION,
        app_version=APP_VERSION,
        param_version=PARAM_VERSION,
        timestamp=utc_now(),
    )


@router.get("/agent/info", response_model=AgentInfoResponse)
async def agent_info() -> AgentInfoResponse:
    """Return non-sensitive Agent metadata for the Manager."""

    return AgentInfoResponse(
        service=AGENT_NAME,
        manager=MANAGER_NAME,
        api_version=API_VERSION,
        app_version=APP_VERSION,
        param_version=PARAM_VERSION,
        root_path=str(KX_ROOT),
        default_network_profile=DEFAULT_NETWORK_PROFILE,
        default_exposure_mode=DEFAULT_EXPOSURE_MODE,
        allowed_services=[service.value for service in DockerService],
    )


@router.post("/capsules/import", response_model=ActionResponse)
async def import_capsule(
    payload: CapsuleImportRequest,
    handler: AgentActionHandler = Depends(get_action_handler),
) -> ActionResponse:
    return await run_agent_action(handler, "capsule_import", payload)


@router.post("/capsules/verify", response_model=ActionResponse)
async def verify_capsule(
    payload: CapsuleVerifyRequest,
    handler: AgentActionHandler = Depends(get_action_handler),
) -> ActionResponse:
    return await run_agent_action(handler, "capsule_verify", payload)


@router.post("/instances/create", response_model=ActionResponse)
async def create_instance(
    payload: InstanceCreateRequest,
    handler: AgentActionHandler = Depends(get_action_handler),
) -> ActionResponse:
    return await run_agent_action(handler, "instance_create", payload)


@router.post("/instances/start", response_model=ActionResponse)
async def start_instance(
    payload: InstanceStartRequest,
    handler: AgentActionHandler = Depends(get_action_handler),
) -> ActionResponse:
    return await run_agent_action(handler, "instance_start", payload)


@router.post("/instances/stop", response_model=ActionResponse)
async def stop_instance(
    payload: InstanceStopRequest,
    handler: AgentActionHandler = Depends(get_action_handler),
) -> ActionResponse:
    return await run_agent_action(handler, "instance_stop", payload)


@router.post("/instances/status", response_model=ActionResponse)
async def instance_status(
    payload: InstanceStatusRequest,
    handler: AgentActionHandler = Depends(get_action_handler),
) -> ActionResponse:
    return await run_agent_action(handler, "instance_status", payload)


@router.post("/instances/logs", response_model=ActionResponse)
async def instance_logs(
    payload: InstanceLogsRequest,
    handler: AgentActionHandler = Depends(get_action_handler),
) -> ActionResponse:
    return await run_agent_action(handler, "instance_logs", payload)


@router.post("/instances/backup", response_model=ActionResponse)
async def backup_instance(
    payload: InstanceBackupRequest,
    handler: AgentActionHandler = Depends(get_action_handler),
) -> ActionResponse:
    return await run_agent_action(handler, "instance_backup", payload)


@router.post("/instances/restore", response_model=ActionResponse)
async def restore_instance(
    payload: InstanceRestoreRequest,
    handler: AgentActionHandler = Depends(get_action_handler),
) -> ActionResponse:
    return await run_agent_action(handler, "instance_restore", payload)


@router.post("/instances/restore-new", response_model=ActionResponse)
async def restore_new_instance(
    payload: InstanceRestoreNewRequest,
    handler: AgentActionHandler = Depends(get_action_handler),
) -> ActionResponse:
    return await run_agent_action(handler, "instance_restore_new", payload)


@router.post("/instances/update", response_model=ActionResponse)
async def update_instance(
    payload: InstanceUpdateRequest,
    handler: AgentActionHandler = Depends(get_action_handler),
) -> ActionResponse:
    return await run_agent_action(handler, "instance_update", payload)


@router.post("/instances/rollback", response_model=ActionResponse)
async def rollback_instance(
    payload: InstanceRollbackRequest,
    handler: AgentActionHandler = Depends(get_action_handler),
) -> ActionResponse:
    return await run_agent_action(handler, "instance_rollback", payload)


@router.post("/instances/health", response_model=ActionResponse)
async def check_instance_health(
    payload: InstanceHealthRequest,
    handler: AgentActionHandler = Depends(get_action_handler),
) -> ActionResponse:
    return await run_agent_action(handler, "instance_health", payload)


@router.post("/security/check", response_model=ActionResponse)
async def security_check(
    payload: SecurityCheckRequest,
    handler: AgentActionHandler = Depends(get_action_handler),
) -> ActionResponse:
    return await run_agent_action(handler, "security_check", payload)


@router.post("/network/set-profile", response_model=ActionResponse)
async def set_network_profile(
    payload: NetworkSetProfileRequest,
    handler: AgentActionHandler = Depends(get_action_handler),
) -> ActionResponse:
    if (
        payload.exposure_mode == ExposureMode.TEMPORARY_TUNNEL
        and payload.public_mode_expires_at is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="public_mode_expires_at is required for temporary public exposure",
        )

    return await run_agent_action(handler, "network_set_profile", payload)


def create_agent_api(action_handler: AgentActionHandler | None = None) -> FastAPI:
    """Create the FastAPI app used by the Konnaxion Agent service."""

    app = FastAPI(
        title=AGENT_NAME,
        version=APP_VERSION,
        description=(
            "Constrained local API for Konnaxion Capsule Manager privileged actions."
        ),
        responses={
            400: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            501: {"model": ErrorResponse},
        },
    )
    app.state.action_handler = action_handler or UnconfiguredActionHandler()
    app.include_router(router)
    return app


app = create_agent_api()
