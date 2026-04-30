"""Log routes for Konnaxion Capsule Manager.

The Manager exposes operator-safe log endpoints and delegates actual runtime
log collection to the local Konnaxion Agent.
"""

from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel, Field, field_validator

from kx_manager.config import get_manager_config
from kx_shared.konnaxion_constants import (
    CANONICAL_DOCKER_SERVICES,
    DEFAULT_INSTANCE_ID,
    DockerService,
)


router = APIRouter(prefix="/logs", tags=["logs"])

DEFAULT_LOG_TAIL = 200
MAX_LOG_TAIL = 5000
AGENT_TIMEOUT_SECONDS = 60.0


class RuntimeLogsResponse(BaseModel):
    """Runtime log response returned by the Manager API."""

    instance_id: str
    services: list[str]
    output: str
    command: list[str] = Field(default_factory=list)
    collected_at: str | None = None


class PersistedLogsResponse(BaseModel):
    """Persisted log-file response returned by the Manager API."""

    instance_id: str
    files: dict[str, str]


class LogRequest(BaseModel):
    """Request body for bounded runtime log reads."""

    instance_id: str = DEFAULT_INSTANCE_ID
    services: list[str] = Field(default_factory=list)
    tail: int = Field(default=DEFAULT_LOG_TAIL, ge=1, le=MAX_LOG_TAIL)
    timestamps: bool = True

    @field_validator("services")
    @classmethod
    def validate_services(cls, services: list[str]) -> list[str]:
        """Reject non-canonical service names."""

        invalid = sorted(set(services) - set(CANONICAL_DOCKER_SERVICES))
        if invalid:
            allowed = ", ".join(CANONICAL_DOCKER_SERVICES)
            raise ValueError(
                f"Unknown Konnaxion runtime service(s): {', '.join(invalid)}. "
                f"Allowed services: {allowed}"
            )
        return services


@router.get("/services")
async def list_log_services() -> dict[str, list[str]]:
    """List canonical service names accepted by log endpoints."""

    return {"services": list(CANONICAL_DOCKER_SERVICES)}


@router.get("/runtime/{instance_id}", response_model=RuntimeLogsResponse)
async def get_runtime_logs(
    instance_id: Annotated[str, Path(min_length=1)],
    services: Annotated[
        list[str],
        Query(
            description=(
                "Optional canonical Docker Compose service names. "
                "Repeat the query parameter for multiple services."
            )
        ),
    ] = [],
    tail: Annotated[int, Query(ge=1, le=MAX_LOG_TAIL)] = DEFAULT_LOG_TAIL,
    timestamps: bool = True,
) -> RuntimeLogsResponse:
    """Return bounded Docker Compose logs for one Konnaxion Instance."""

    request = LogRequest(
        instance_id=instance_id,
        services=services,
        tail=tail,
        timestamps=timestamps,
    )

    payload = await _agent_get(
        f"/logs/runtime/{request.instance_id}",
        params={
            "services": request.services,
            "tail": request.tail,
            "timestamps": request.timestamps,
        },
    )

    return RuntimeLogsResponse.model_validate(payload)


@router.post("/runtime", response_model=RuntimeLogsResponse)
async def post_runtime_logs(request: LogRequest) -> RuntimeLogsResponse:
    """Return bounded Docker Compose logs using a JSON body."""

    payload = await _agent_post(
        "/logs/runtime",
        json=request.model_dump(),
    )

    return RuntimeLogsResponse.model_validate(payload)


@router.get("/service/{instance_id}/{service}", response_model=RuntimeLogsResponse)
async def get_service_logs(
    instance_id: Annotated[str, Path(min_length=1)],
    service: Annotated[str, Path(description="Canonical Docker Compose service name")],
    tail: Annotated[int, Query(ge=1, le=MAX_LOG_TAIL)] = DEFAULT_LOG_TAIL,
    timestamps: bool = True,
) -> RuntimeLogsResponse:
    """Return bounded logs for one canonical runtime service."""

    _validate_service(service)

    payload = await _agent_get(
        f"/logs/service/{instance_id}/{service}",
        params={
            "tail": tail,
            "timestamps": timestamps,
        },
    )

    return RuntimeLogsResponse.model_validate(payload)


@router.get("/persisted/{instance_id}", response_model=PersistedLogsResponse)
async def get_persisted_logs(
    instance_id: Annotated[str, Path(min_length=1)],
    max_files: Annotated[int, Query(ge=1, le=100)] = 50,
    max_bytes_per_file: Annotated[int, Query(ge=1, le=1_000_000)] = 250_000,
) -> PersistedLogsResponse:
    """Return persisted log files from the canonical instance logs directory."""

    payload = await _agent_get(
        f"/logs/persisted/{instance_id}",
        params={
            "max_files": max_files,
            "max_bytes_per_file": max_bytes_per_file,
        },
    )

    if "files" not in payload:
        payload = {
            "instance_id": instance_id,
            "files": payload,
        }

    return PersistedLogsResponse.model_validate(payload)


@router.get("/tail/{instance_id}")
async def tail_logs(
    instance_id: Annotated[str, Path(min_length=1)],
    service: Annotated[str | None, Query()] = None,
    tail: Annotated[int, Query(ge=1, le=MAX_LOG_TAIL)] = DEFAULT_LOG_TAIL,
) -> RuntimeLogsResponse:
    """Compatibility endpoint for quick UI tail views."""

    services = [service] if service else []
    request = LogRequest(instance_id=instance_id, services=services, tail=tail)

    payload = await _agent_get(
        f"/logs/runtime/{request.instance_id}",
        params={
            "services": request.services,
            "tail": request.tail,
            "timestamps": True,
        },
    )

    return RuntimeLogsResponse.model_validate(payload)


def _validate_service(service: str | DockerService) -> str:
    """Return a canonical service name or raise an HTTP 422 error."""

    service_name = service.value if isinstance(service, DockerService) else service

    if service_name not in CANONICAL_DOCKER_SERVICES:
        allowed = ", ".join(CANONICAL_DOCKER_SERVICES)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unknown Konnaxion runtime service: {service_name!r}. "
                f"Allowed services: {allowed}"
            ),
        )

    return service_name


async def _agent_get(path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Proxy a GET request to the local Konnaxion Agent."""

    return await _agent_request("GET", path, params=params)


async def _agent_post(path: str, *, json: dict[str, Any]) -> dict[str, Any]:
    """Proxy a POST request to the local Konnaxion Agent."""

    return await _agent_request("POST", path, json=json)


async def _agent_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a request to the Agent and normalize errors for Manager callers."""

    base_url = _agent_base_url()

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=AGENT_TIMEOUT_SECONDS) as client:
            response = await client.request(method, path, params=params, json=json)
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Timed out while requesting logs from Konnaxion Agent.",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to contact Konnaxion Agent for logs: {exc}",
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=_extract_error_detail(response),
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Konnaxion Agent returned invalid JSON for logs.",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Konnaxion Agent returned an invalid logs payload.",
        )

    return payload


def _agent_base_url() -> str:
    """Resolve the configured local Agent base URL."""

    config = get_manager_config()

    explicit = getattr(config, "KX_AGENT_BASE_URL", None) or getattr(config, "agent_base_url", None)
    if explicit:
        return str(explicit).rstrip("/")

    host = getattr(config, "KX_AGENT_HOST", "127.0.0.1")
    port = getattr(config, "KX_AGENT_PORT", 8714)
    return f"http://{host}:{port}"


def _extract_error_detail(response: httpx.Response) -> str:
    """Extract a readable error message from an Agent response."""

    try:
        payload = response.json()
    except ValueError:
        return response.text or "Konnaxion Agent log request failed."

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                return message

        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail

    return "Konnaxion Agent log request failed."
