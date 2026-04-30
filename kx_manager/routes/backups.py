"""
Backup and restore routes for Konnaxion Capsule Manager.

The Manager must not perform privileged filesystem, Docker, database, or restore
operations directly. This module validates user-facing API payloads and delegates
backup/restore work to the local Konnaxion Agent.

Route summary:
- GET    /backups
- GET    /instances/{instance_id}/backups
- POST   /instances/{instance_id}/backups
- GET    /backups/{backup_id}
- POST   /backups/{backup_id}/verify
- POST   /instances/{instance_id}/restore
- POST   /instances/restore-new
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Mapping

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from kx_manager.config import ManagerConfig, ManagerConfigError, load_config


router = APIRouter(tags=["backups"])


class BackupRouteError(RuntimeError):
    """Raised when a Manager backup route cannot complete."""


class BackupClass(StrEnum):
    """Backup class values used by Manager and Agent."""

    MANUAL = "manual"
    SCHEDULED_DAILY = "scheduled_daily"
    SCHEDULED_WEEKLY = "scheduled_weekly"
    SCHEDULED_MONTHLY = "scheduled_monthly"
    PRE_UPDATE = "pre_update"
    PRE_RESTORE = "pre_restore"


class BackupStatusValue(StrEnum):
    """Canonical backup resource statuses."""

    CREATED = "created"
    RUNNING = "running"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    FAILED = "failed"
    EXPIRED = "expired"
    DELETED = "deleted"
    QUARANTINED = "quarantined"


class RestoreStatusValue(StrEnum):
    """Canonical restore resource statuses."""

    PLANNED = "planned"
    PREFLIGHT = "preflight"
    CREATING_PRE_RESTORE_BACKUP = "creating_pre_restore_backup"
    RESTORING_DATABASE = "restoring_database"
    RESTORING_MEDIA = "restoring_media"
    RUNNING_MIGRATIONS = "running_migrations"
    RUNNING_SECURITY_GATE = "running_security_gate"
    RUNNING_HEALTHCHECKS = "running_healthchecks"
    RESTORED = "restored"
    DEGRADED = "degraded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class BackupCreateRequest(BaseModel):
    """Create a backup for an existing Konnaxion Instance."""

    backup_class: BackupClass = Field(default=BackupClass.MANUAL)
    label: str = Field(default="", max_length=120)
    include_database: bool = True
    include_media: bool = True
    include_env_fingerprint: bool = True
    verify_after_create: bool = True
    reason: str = Field(default="", max_length=500)

    @field_validator("label", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class BackupVerifyRequest(BaseModel):
    """Verify a backup artifact."""

    deep: bool = False
    reason: str = Field(default="", max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class RestoreRequest(BaseModel):
    """Restore an existing Konnaxion Instance from a backup."""

    backup_id: str = Field(min_length=1, max_length=160)
    create_pre_restore_backup: bool = True
    run_migrations: bool = True
    run_security_gate: bool = True
    run_healthchecks: bool = True
    reason: str = Field(default="", max_length=500)

    @field_validator("backup_id", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class RestoreNewRequest(BaseModel):
    """Restore a backup into a new Konnaxion Instance."""

    backup_id: str = Field(min_length=1, max_length=160)
    new_instance_id: str = Field(min_length=1, max_length=120)
    network_profile: str = Field(default="intranet_private", max_length=80)
    exposure_mode: str = Field(default="private", max_length=80)
    run_migrations: bool = True
    run_security_gate: bool = True
    run_healthchecks: bool = True
    reason: str = Field(default="", max_length=500)

    @field_validator(
        "backup_id",
        "new_instance_id",
        "network_profile",
        "exposure_mode",
        "reason",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class BackupSummary(BaseModel):
    """Backup summary returned to Manager UI/API clients."""

    backup_id: str
    instance_id: str
    backup_class: str
    status: str
    created_at: str = ""
    completed_at: str = ""
    size_bytes: int | None = None
    verified: bool = False
    label: str = ""
    path: str = ""


class BackupDetail(BaseModel):
    """Detailed backup metadata."""

    backup_id: str
    instance_id: str
    backup_class: str
    status: str
    created_at: str = ""
    completed_at: str = ""
    size_bytes: int | None = None
    verified: bool = False
    label: str = ""
    path: str = ""
    manifest: Mapping[str, Any] = Field(default_factory=dict)
    verification: Mapping[str, Any] = Field(default_factory=dict)


class BackupOperationResponse(BaseModel):
    """Generic response for backup operations."""

    ok: bool
    operation: str
    instance_id: str = ""
    backup_id: str = ""
    status: str = ""
    message: str = ""
    data: Mapping[str, Any] = Field(default_factory=dict)


class RestoreOperationResponse(BaseModel):
    """Generic response for restore operations."""

    ok: bool
    operation: str
    source_backup_id: str
    instance_id: str = ""
    new_instance_id: str = ""
    status: str = ""
    message: str = ""
    data: Mapping[str, Any] = Field(default_factory=dict)


class AgentErrorResponse(BaseModel):
    """Normalized Agent error payload."""

    ok: bool = False
    error: str
    detail: Any = None


class AgentClient:
    """Small HTTP client for Manager-to-Agent backup calls."""

    def __init__(self, config: ManagerConfig) -> None:
        self.config = config
        self.base_url = config.agent.base_url.rstrip("/")
        self.timeout = config.agent.timeout_seconds
        self.headers = self._headers(config)

    async def get(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(
        self,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
    ) -> Any:
        return await self._request("POST", path, json_body=json_body)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method,
                    url,
                    params=dict(params or {}),
                    json=dict(json_body or {}),
                    headers=self.headers,
                )
        except httpx.TimeoutException as exc:
            raise BackupRouteError("Konnaxion Agent request timed out.") from exc
        except httpx.HTTPError as exc:
            raise BackupRouteError(f"Cannot reach Konnaxion Agent: {exc}") from exc

        if response.status_code >= 400:
            raise http_exception_from_agent_response(response)

        if not response.content:
            return {}

        try:
            return response.json()
        except ValueError as exc:
            raise BackupRouteError("Konnaxion Agent returned invalid JSON.") from exc

    @staticmethod
    def _headers(config: ManagerConfig) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "konnaxion-manager/backup-routes",
        }

        if config.agent.token:
            headers["Authorization"] = f"Bearer {config.agent.token}"

        return headers


def get_manager_config() -> ManagerConfig:
    """FastAPI dependency that loads validated Manager config."""

    try:
        return load_config(ensure_paths=False, validate=True)
    except ManagerConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "ok": False,
                "error": "manager_config_error",
                "message": str(exc),
            },
        ) from exc


def get_agent_client(
    config: ManagerConfig = Depends(get_manager_config),
) -> AgentClient:
    """FastAPI dependency for a local Agent client."""

    return AgentClient(config)


@router.get(
    "/backups",
    response_model=list[BackupSummary],
    summary="List backups",
)
async def list_backups(
    instance_id: str | None = Query(default=None, max_length=120),
    status_filter: BackupStatusValue | None = Query(default=None, alias="status"),
    backup_class: BackupClass | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    agent: AgentClient = Depends(get_agent_client),
) -> list[BackupSummary]:
    """List backups known to the Agent."""

    payload = await agent.get(
        "/backups",
        params={
            "instance_id": instance_id or "",
            "status": status_filter.value if status_filter else "",
            "backup_class": backup_class.value if backup_class else "",
            "limit": limit,
        },
    )

    return [BackupSummary(**item) for item in as_list(payload)]


@router.get(
    "/instances/{instance_id}/backups",
    response_model=list[BackupSummary],
    summary="List backups for an instance",
)
async def list_instance_backups(
    instance_id: str,
    status_filter: BackupStatusValue | None = Query(default=None, alias="status"),
    backup_class: BackupClass | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    agent: AgentClient = Depends(get_agent_client),
) -> list[BackupSummary]:
    """List backups for one Konnaxion Instance."""

    assert_safe_identifier(instance_id, field_name="instance_id")

    payload = await agent.get(
        f"/instances/{instance_id}/backups",
        params={
            "status": status_filter.value if status_filter else "",
            "backup_class": backup_class.value if backup_class else "",
            "limit": limit,
        },
    )

    return [BackupSummary(**item) for item in as_list(payload)]


@router.post(
    "/instances/{instance_id}/backups",
    response_model=BackupOperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create backup",
)
async def create_backup(
    instance_id: str,
    request: BackupCreateRequest,
    agent: AgentClient = Depends(get_agent_client),
) -> BackupOperationResponse:
    """Request a backup through the local Agent."""

    assert_safe_identifier(instance_id, field_name="instance_id")

    payload = await agent.post(
        f"/instances/{instance_id}/backups",
        json_body=request.model_dump(mode="json"),
    )

    return BackupOperationResponse(**as_mapping(payload, default_operation="backup"))


@router.get(
    "/backups/{backup_id}",
    response_model=BackupDetail,
    summary="Get backup detail",
)
async def get_backup(
    backup_id: str,
    agent: AgentClient = Depends(get_agent_client),
) -> BackupDetail:
    """Fetch detailed metadata for one backup."""

    assert_safe_identifier(backup_id, field_name="backup_id")

    payload = await agent.get(f"/backups/{backup_id}")

    return BackupDetail(**as_mapping(payload))


@router.post(
    "/backups/{backup_id}/verify",
    response_model=BackupOperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Verify backup",
)
async def verify_backup(
    backup_id: str,
    request: BackupVerifyRequest,
    agent: AgentClient = Depends(get_agent_client),
) -> BackupOperationResponse:
    """Request backup verification through the local Agent."""

    assert_safe_identifier(backup_id, field_name="backup_id")

    payload = await agent.post(
        f"/backups/{backup_id}/verify",
        json_body=request.model_dump(mode="json"),
    )

    return BackupOperationResponse(
        **as_mapping(payload, default_operation="backup_verify")
    )


@router.post(
    "/instances/{instance_id}/restore",
    response_model=RestoreOperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Restore instance from backup",
)
async def restore_instance(
    instance_id: str,
    request: RestoreRequest,
    agent: AgentClient = Depends(get_agent_client),
) -> RestoreOperationResponse:
    """Request restore of an existing Konnaxion Instance."""

    assert_safe_identifier(instance_id, field_name="instance_id")
    assert_safe_identifier(request.backup_id, field_name="backup_id")

    payload = await agent.post(
        f"/instances/{instance_id}/restore",
        json_body=request.model_dump(mode="json"),
    )

    data = as_mapping(payload, default_operation="restore")
    data.setdefault("source_backup_id", request.backup_id)
    data.setdefault("instance_id", instance_id)

    return RestoreOperationResponse(**data)


@router.post(
    "/instances/restore-new",
    response_model=RestoreOperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Restore backup into a new instance",
)
async def restore_new_instance(
    request: RestoreNewRequest,
    agent: AgentClient = Depends(get_agent_client),
) -> RestoreOperationResponse:
    """Request restore of a backup into a new Konnaxion Instance."""

    assert_safe_identifier(request.backup_id, field_name="backup_id")
    assert_safe_identifier(request.new_instance_id, field_name="new_instance_id")

    payload = await agent.post(
        "/instances/restore-new",
        json_body=request.model_dump(mode="json"),
    )

    data = as_mapping(payload, default_operation="restore_new")
    data.setdefault("source_backup_id", request.backup_id)
    data.setdefault("new_instance_id", request.new_instance_id)

    return RestoreOperationResponse(**data)


def as_list(payload: Any) -> list[Mapping[str, Any]]:
    """Normalize Agent list responses."""

    if isinstance(payload, list):
        return [as_mapping(item) for item in payload]

    if isinstance(payload, dict):
        for key in ("backups", "items", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [as_mapping(item) for item in value]

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "ok": False,
            "error": "invalid_agent_response",
            "message": "Agent response did not contain a backup list.",
        },
    )


def as_mapping(payload: Any, *, default_operation: str = "") -> dict[str, Any]:
    """Normalize an Agent object response."""

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "ok": False,
                "error": "invalid_agent_response",
                "message": "Agent response was not a JSON object.",
            },
        )

    data = dict(payload)

    if default_operation:
        data.setdefault("operation", default_operation)

    return data


def http_exception_from_agent_response(response: httpx.Response) -> HTTPException:
    """Convert an Agent error response to a Manager API error."""

    try:
        payload = response.json()
    except ValueError:
        payload = {
            "ok": False,
            "error": "agent_error",
            "message": response.text,
        }

    status_code = response.status_code

    if status_code >= 500:
        manager_status = status.HTTP_502_BAD_GATEWAY
    elif status_code == 401:
        manager_status = status.HTTP_502_BAD_GATEWAY
    elif status_code == 403:
        manager_status = status.HTTP_403_FORBIDDEN
    elif status_code == 404:
        manager_status = status.HTTP_404_NOT_FOUND
    elif status_code == 409:
        manager_status = status.HTTP_409_CONFLICT
    elif status_code == 422:
        manager_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        manager_status = status.HTTP_400_BAD_REQUEST

    return HTTPException(
        status_code=manager_status,
        detail={
            "ok": False,
            "error": "agent_request_failed",
            "agent_status_code": status_code,
            "agent_detail": payload,
        },
    )


def assert_safe_identifier(value: str, *, field_name: str) -> None:
    """
    Reject identifiers that could be interpreted as paths or shell fragments.

    Backup and instance IDs are passed to Agent URLs only, but strict validation
    keeps route behavior deterministic.
    """

    if not value or not value.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "ok": False,
                "error": "invalid_identifier",
                "field": field_name,
                "message": f"{field_name} cannot be empty.",
            },
        )

    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")

    if any(char not in allowed_chars for char in value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "ok": False,
                "error": "invalid_identifier",
                "field": field_name,
                "message": (
                    f"{field_name} may only contain letters, numbers, dots, "
                    "underscores, and hyphens."
                ),
            },
        )

    forbidden_tokens = ("..", "/", "\\", "$", "`", ";", "|", "&", "\\x00")

    if any(token in value for token in forbidden_tokens):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "ok": False,
                "error": "invalid_identifier",
                "field": field_name,
                "message": f"{field_name} contains a forbidden token.",
            },
        )
