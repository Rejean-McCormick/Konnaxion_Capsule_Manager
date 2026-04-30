"""
Capsule routes for Konnaxion Capsule Manager.

The Manager is the user-facing control layer. It must not directly unpack
capsules, load Docker images, modify firewall rules, or start runtime services.
Privileged capsule operations are delegated to the Konnaxion Agent through the
Agent client attached to ``request.app.state.agent_client``.

Canonical responsibilities exposed here:
- list imported Konnaxion Capsules
- inspect capsule metadata
- verify a capsule before import/start
- import a signed ``.kxcap`` file through the Agent
- delete or forget capsule records when the Agent allows it

Important implementation note:
This module intentionally does not use FastAPI ``File`` or ``UploadFile``.
Those require ``python-multipart`` at route-registration time. Instead, the
import route accepts the raw request body as bytes and reads the capsule
filename from query/header metadata.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from kx_shared.konnaxion_constants import (
    CAPSULE_EXTENSION,
    DEFAULT_CHANNEL,
    DEFAULT_EXPOSURE_MODE,
    DEFAULT_NETWORK_PROFILE,
    ExposureMode,
    NetworkProfile,
)


router = APIRouter(prefix="/capsules", tags=["capsules"])


SAFE_CAPSULE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
CONTENT_DISPOSITION_FILENAME_RE = re.compile(
    r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?',
    re.IGNORECASE,
)


def enum_value(value: Any) -> str:
    """Return `.value` for enum-like values, otherwise string."""

    return str(getattr(value, "value", value))


class AgentClientProtocol(Protocol):
    """Protocol expected from ``request.app.state.agent_client``."""

    async def list_capsules(self) -> list[Mapping[str, Any]]:
        """Return imported capsule summaries."""

    async def get_capsule(self, capsule_id: str) -> Mapping[str, Any]:
        """Return one capsule summary/detail."""

    async def verify_capsule_path(self, path: str) -> Mapping[str, Any]:
        """Verify a capsule already available to the Agent."""

    async def import_capsule_upload(
        self,
        *,
        filename: str,
        content: bytes,
        channel: str,
        network_profile: str,
        exposure_mode: str,
    ) -> Mapping[str, Any]:
        """Import an uploaded capsule through the Agent."""

    async def delete_capsule(self, capsule_id: str) -> Mapping[str, Any]:
        """Delete or forget an imported capsule through the Agent."""


class CapsuleSummary(BaseModel):
    """User-facing capsule summary returned by the Manager API."""

    model_config = ConfigDict(extra="allow")

    capsule_id: str = Field(..., min_length=1)
    capsule_version: str | None = None
    app_version: str | None = None
    channel: str | None = None
    filename: str | None = None
    imported_at: str | None = None
    verified: bool = False
    signature_status: str | None = None
    security_status: str | None = None


class CapsuleDetail(CapsuleSummary):
    """Detailed capsule metadata."""

    manifest: dict[str, Any] | None = None
    profiles: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CapsuleVerifyRequest(BaseModel):
    """Request to verify a capsule path known to the Agent."""

    capsule_path: str = Field(..., min_length=1)

    @field_validator("capsule_path")
    @classmethod
    def validate_capsule_path(cls, value: str) -> str:
        path = Path(value)
        if path.suffix != CAPSULE_EXTENSION:
            raise ValueError(f"Capsule path must end with {CAPSULE_EXTENSION}")
        return value


class CapsuleVerifyResponse(BaseModel):
    """Verification result returned by the Manager API."""

    model_config = ConfigDict(extra="allow")

    ok: bool = False
    valid: bool = False
    capsule_id: str | None = None
    capsule_version: str | None = None
    filename: str | None = None
    signed: bool | None = None
    checksums_valid: bool | None = None
    manifest_valid: bool | None = None
    security_status: str | None = None
    errors: list[Any] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CapsuleImportResponse(BaseModel):
    """Capsule import response returned by the Manager API."""

    model_config = ConfigDict(extra="allow")

    ok: bool = True
    capsule: CapsuleSummary | None = None
    capsule_id: str | None = None
    action_id: str | None = None
    message: str = "Capsule import accepted."
    data: dict[str, Any] = Field(default_factory=dict)


class CapsuleDeleteResponse(BaseModel):
    """Capsule delete/forget response."""

    model_config = ConfigDict(extra="allow")

    ok: bool = True
    capsule_id: str
    message: str = "Capsule delete accepted."
    data: dict[str, Any] = Field(default_factory=dict)


@router.get("", response_model=list[CapsuleSummary])
@router.get("/", response_model=list[CapsuleSummary])
async def list_capsules(request: Request) -> list[CapsuleSummary]:
    """List imported Konnaxion Capsules."""

    agent = get_agent_client(request)
    payload = await agent.list_capsules()

    if not isinstance(payload, list):
        raise agent_response_error("Agent list_capsules response must be a list.")

    return [CapsuleSummary(**as_mapping(item)) for item in payload]


@router.get("/{capsule_id}", response_model=CapsuleDetail)
async def get_capsule(
    capsule_id: str,
    request: Request,
) -> CapsuleDetail:
    """Return metadata for one imported Konnaxion Capsule."""

    capsule_id = validate_capsule_id(capsule_id)
    agent = get_agent_client(request)

    payload = await agent.get_capsule(capsule_id)
    return CapsuleDetail(**as_mapping(payload))


@router.post("/verify", response_model=CapsuleVerifyResponse)
async def verify_capsule(
    request_body: CapsuleVerifyRequest,
    request: Request,
) -> CapsuleVerifyResponse:
    """Verify a capsule path already available to the Agent."""

    agent = get_agent_client(request)
    payload = await agent.verify_capsule_path(request_body.capsule_path)

    data = as_mapping(payload)
    data.setdefault("ok", bool(data.get("valid", False)))
    data.setdefault("valid", bool(data.get("ok", False)))

    return CapsuleVerifyResponse(**data)


@router.post(
    "/import",
    response_model=CapsuleImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def import_capsule(
    request: Request,
    filename: str | None = Query(
        default=None,
        description=(
            "Capsule filename. Required unless X-KX-Filename or "
            "Content-Disposition filename is provided."
        ),
    ),
    channel: str = Query(default=DEFAULT_CHANNEL),
    network_profile: str = Query(default=enum_value(DEFAULT_NETWORK_PROFILE)),
    exposure_mode: str = Query(default=enum_value(DEFAULT_EXPOSURE_MODE)),
) -> CapsuleImportResponse:
    """
    Import an uploaded signed `.kxcap` through the Agent.

    The request body must be the raw `.kxcap` bytes.

    Filename resolution order:
    1. `filename` query parameter
    2. `X-KX-Filename` request header
    3. `Content-Disposition` filename
    """

    resolved_filename = resolve_upload_filename(request, filename)
    validate_capsule_filename(resolved_filename)

    normalized_channel = validate_channel(channel)
    normalized_network_profile = validate_network_profile(network_profile)
    normalized_exposure_mode = validate_exposure_mode(exposure_mode)

    content = await request.body()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "ok": False,
                "error": "empty_capsule_upload",
                "message": "Capsule import body cannot be empty.",
            },
        )

    agent = get_agent_client(request)

    payload = await agent.import_capsule_upload(
        filename=resolved_filename,
        content=content,
        channel=normalized_channel,
        network_profile=normalized_network_profile,
        exposure_mode=normalized_exposure_mode,
    )

    data = as_mapping(payload)
    data.setdefault("ok", True)
    data.setdefault("message", "Capsule import accepted.")

    if data.get("capsule") is not None and not isinstance(data["capsule"], CapsuleSummary):
        data["capsule"] = CapsuleSummary(**as_mapping(data["capsule"]))

    return CapsuleImportResponse(**data)


@router.delete("/{capsule_id}", response_model=CapsuleDeleteResponse)
async def delete_capsule(
    capsule_id: str,
    request: Request,
) -> CapsuleDeleteResponse:
    """Delete or forget an imported capsule through the Agent."""

    capsule_id = validate_capsule_id(capsule_id)
    agent = get_agent_client(request)

    payload = await agent.delete_capsule(capsule_id)
    data = as_mapping(payload)

    data.setdefault("ok", True)
    data.setdefault("capsule_id", capsule_id)
    data.setdefault("message", "Capsule delete accepted.")

    return CapsuleDeleteResponse(**data)


def get_agent_client(request: Request) -> AgentClientProtocol:
    """Return the Agent client attached to the FastAPI app state."""

    agent = getattr(request.app.state, "agent_client", None)

    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "ok": False,
                "error": "agent_client_missing",
                "message": (
                    "Konnaxion Agent client is not attached to "
                    "request.app.state.agent_client."
                ),
            },
        )

    return agent


def resolve_upload_filename(request: Request, explicit_filename: str | None) -> str:
    """Resolve a raw-body upload filename from query/header metadata."""

    if explicit_filename:
        return explicit_filename.strip()

    header_filename = request.headers.get("X-KX-Filename")
    if header_filename:
        return header_filename.strip()

    content_disposition = request.headers.get("Content-Disposition", "")
    match = CONTENT_DISPOSITION_FILENAME_RE.search(content_disposition)
    if match:
        return unquote(match.group(1)).strip()

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "ok": False,
            "error": "missing_capsule_filename",
            "message": (
                "Capsule filename is required. Provide ?filename=..., "
                "X-KX-Filename, or Content-Disposition filename."
            ),
        },
    )


def validate_capsule_filename(filename: str) -> str:
    """Validate a user-supplied capsule filename."""

    normalized = filename.strip().replace("\\", "/")
    basename = normalized.rsplit("/", maxsplit=1)[-1]

    if not basename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "ok": False,
                "error": "invalid_capsule_filename",
                "message": "Capsule filename cannot be empty.",
            },
        )

    if basename != filename.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "ok": False,
                "error": "invalid_capsule_filename",
                "message": "Capsule filename must not include directories.",
            },
        )

    if not basename.endswith(CAPSULE_EXTENSION):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "ok": False,
                "error": "invalid_capsule_extension",
                "message": f"Capsule filename must end with {CAPSULE_EXTENSION}.",
            },
        )

    forbidden_tokens = ("..", "/", "\\", "\x00", "$", "`", ";", "|", "&")
    if any(token in basename for token in forbidden_tokens):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "ok": False,
                "error": "unsafe_capsule_filename",
                "message": "Capsule filename contains a forbidden token.",
            },
        )

    return basename


def validate_capsule_id(capsule_id: str) -> str:
    """Validate a capsule ID used in route path parameters."""

    normalized = capsule_id.strip()

    if normalized.endswith(CAPSULE_EXTENSION):
        normalized = normalized[: -len(CAPSULE_EXTENSION)]

    if not SAFE_CAPSULE_ID_RE.fullmatch(normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "ok": False,
                "error": "invalid_capsule_id",
                "message": (
                    "Capsule ID may only contain letters, numbers, dots, "
                    "underscores, and hyphens."
                ),
            },
        )

    return normalized


def validate_channel(channel: str) -> str:
    """Validate a capsule channel value."""

    normalized = channel.strip() or DEFAULT_CHANNEL

    if not SAFE_CAPSULE_ID_RE.fullmatch(normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "ok": False,
                "error": "invalid_channel",
                "message": (
                    "Channel may only contain letters, numbers, dots, "
                    "underscores, and hyphens."
                ),
            },
        )

    return normalized


def validate_network_profile(value: str) -> str:
    """Validate a canonical network profile."""

    normalized = value.strip() or enum_value(DEFAULT_NETWORK_PROFILE)

    try:
        return NetworkProfile(normalized).value
    except ValueError as exc:
        allowed = ", ".join(item.value for item in NetworkProfile)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "ok": False,
                "error": "invalid_network_profile",
                "message": f"Invalid network profile. Allowed: {allowed}.",
            },
        ) from exc


def validate_exposure_mode(value: str) -> str:
    """Validate a canonical exposure mode."""

    normalized = value.strip() or enum_value(DEFAULT_EXPOSURE_MODE)

    try:
        return ExposureMode(normalized).value
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ExposureMode)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "ok": False,
                "error": "invalid_exposure_mode",
                "message": f"Invalid exposure mode. Allowed: {allowed}.",
            },
        ) from exc


def as_mapping(value: Any) -> dict[str, Any]:
    """Normalize an Agent response object into a dictionary."""

    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")

    if isinstance(value, Mapping):
        return dict(value)

    raise agent_response_error("Agent response must be a JSON object.")


def agent_response_error(message: str) -> HTTPException:
    """Return a 502 error for invalid Agent response contracts."""

    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "ok": False,
            "error": "invalid_agent_response",
            "message": message,
        },
    )


__all__ = [
    "AgentClientProtocol",
    "CapsuleDeleteResponse",
    "CapsuleDetail",
    "CapsuleImportResponse",
    "CapsuleSummary",
    "CapsuleVerifyRequest",
    "CapsuleVerifyResponse",
    "agent_response_error",
    "as_mapping",
    "delete_capsule",
    "enum_value",
    "get_agent_client",
    "get_capsule",
    "import_capsule",
    "list_capsules",
    "resolve_upload_filename",
    "router",
    "validate_capsule_filename",
    "validate_capsule_id",
    "validate_channel",
    "validate_exposure_mode",
    "validate_network_profile",
    "verify_capsule",
]