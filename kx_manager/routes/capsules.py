"""Capsule routes for Konnaxion Capsule Manager.

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
    DEFAULT_INSTANCE_ID,
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

    async def list_capsules(self) -> Any:
        """Return imported/local capsule summaries."""

    async def get_capsule(self, capsule_id: str) -> Mapping[str, Any]:
        """Return one capsule summary/detail."""

    async def verify_capsule(self, *, capsule_path: str) -> Mapping[str, Any]:
        """Verify a capsule already available to the Agent."""

    async def verify_capsule_path(self, path: str) -> Mapping[str, Any]:
        """Compatibility method for older route/client contracts."""

    async def import_capsule(
        self,
        *,
        capsule_path: str,
        instance_id: str,
        network_profile: str,
    ) -> Mapping[str, Any]:
        """Import a capsule path through the Agent."""

    async def import_capsule_upload(
        self,
        *,
        filename: str,
        content: bytes,
        channel: str,
        network_profile: str,
        exposure_mode: str,
    ) -> Mapping[str, Any]:
        """Compatibility method for raw upload imports."""

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
    """List imported or locally available Konnaxion Capsules."""

    agent = get_agent_client(request)
    payload = await agent.list_capsules()
    items = normalize_capsule_list_response(payload)

    return [CapsuleSummary(**normalize_capsule_summary(item)) for item in items]


@router.get("/{capsule_id}", response_model=CapsuleDetail)
async def get_capsule(
    capsule_id: str,
    request: Request,
) -> CapsuleDetail:
    """Return metadata for one imported Konnaxion Capsule."""

    capsule_id = validate_capsule_id(capsule_id)
    agent = get_agent_client(request)

    get_capsule_method = getattr(agent, "get_capsule", None)
    if callable(get_capsule_method):
        payload = await get_capsule_method(capsule_id)
        return CapsuleDetail(**normalize_capsule_summary(as_mapping(payload)))

    payload = await agent.list_capsules()
    items = normalize_capsule_list_response(payload)

    for item in items:
        data = normalize_capsule_summary(item)
        if data.get("capsule_id") == capsule_id or data.get("id") == capsule_id:
            return CapsuleDetail(**data)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "ok": False,
            "error": "capsule_not_found",
            "message": f"Capsule not found: {capsule_id}",
        },
    )


@router.post("/verify", response_model=CapsuleVerifyResponse)
async def verify_capsule(
    request_body: CapsuleVerifyRequest,
    request: Request,
) -> CapsuleVerifyResponse:
    """Verify a capsule path already available to the Agent."""

    agent = get_agent_client(request)

    verify_capsule_path_method = getattr(agent, "verify_capsule_path", None)
    if callable(verify_capsule_path_method):
        payload = await verify_capsule_path_method(request_body.capsule_path)
    else:
        verify_capsule_method = getattr(agent, "verify_capsule", None)
        if not callable(verify_capsule_method):
            raise agent_response_error("Agent client does not support capsule verification.")
        payload = await verify_capsule_method(capsule_path=request_body.capsule_path)

    data = as_mapping(payload)
    data.setdefault("ok", bool(data.get("valid", False)))
    data.setdefault("valid", bool(data.get("ok", False)))

    if data.get("filename") is None:
        data["filename"] = Path(request_body.capsule_path).name

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
    capsule_path: str | None = Query(
        default=None,
        description="Existing local capsule path. If provided, raw upload body is optional.",
    ),
    instance_id: str = Query(default=enum_value(DEFAULT_INSTANCE_ID)),
    channel: str = Query(default=DEFAULT_CHANNEL),
    network_profile: str = Query(default=enum_value(DEFAULT_NETWORK_PROFILE)),
    exposure_mode: str = Query(default=enum_value(DEFAULT_EXPOSURE_MODE)),
) -> CapsuleImportResponse:
    """
    Import a signed `.kxcap` through the Agent.

    Supported forms:
    1. Existing path: POST /capsules/import?capsule_path=C:/.../file.kxcap
    2. Raw upload body with filename metadata.

    Filename resolution order for raw uploads:
    1. `filename` query parameter
    2. `X-KX-Filename` request header
    3. `Content-Disposition` filename
    """

    normalized_channel = validate_channel(channel)
    normalized_network_profile = validate_network_profile(network_profile)
    normalized_exposure_mode = validate_exposure_mode(exposure_mode)
    normalized_instance_id = validate_capsule_id(instance_id)

    agent = get_agent_client(request)

    if capsule_path:
        path = validate_capsule_path_string(capsule_path)

        import_capsule_method = getattr(agent, "import_capsule", None)
        if not callable(import_capsule_method):
            raise agent_response_error("Agent client does not support capsule import.")

        payload = await import_capsule_method(
            capsule_path=path,
            instance_id=normalized_instance_id,
            network_profile=normalized_network_profile,
        )

        return build_import_response(
            payload,
            default_capsule_id=Path(path).stem,
            default_filename=Path(path).name,
        )

    resolved_filename = resolve_upload_filename(request, filename)
    resolved_filename = validate_capsule_filename(resolved_filename)

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

    import_capsule_upload_method = getattr(agent, "import_capsule_upload", None)
    if callable(import_capsule_upload_method):
        payload = await import_capsule_upload_method(
            filename=resolved_filename,
            content=content,
            channel=normalized_channel,
            network_profile=normalized_network_profile,
            exposure_mode=normalized_exposure_mode,
        )

        return build_import_response(
            payload,
            default_capsule_id=Path(resolved_filename).stem,
            default_filename=resolved_filename,
        )

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "ok": False,
            "error": "raw_upload_import_not_supported",
            "message": (
                "The current Agent client does not support raw capsule upload import. "
                "Build the capsule to disk and call /capsules/import with capsule_path."
            ),
        },
    )


@router.delete("/{capsule_id}", response_model=CapsuleDeleteResponse)
async def delete_capsule(
    capsule_id: str,
    request: Request,
) -> CapsuleDeleteResponse:
    """Delete or forget an imported capsule through the Agent if supported."""

    capsule_id = validate_capsule_id(capsule_id)
    agent = get_agent_client(request)

    delete_capsule_method = getattr(agent, "delete_capsule", None)
    if not callable(delete_capsule_method):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "ok": False,
                "error": "delete_capsule_not_supported",
                "message": "The current Agent client does not support capsule deletion.",
            },
        )

    payload = await delete_capsule_method(capsule_id)
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


def normalize_capsule_list_response(payload: Any) -> list[dict[str, Any]]:
    """Accept both list and wrapper-object capsule inventory responses."""

    if isinstance(payload, list):
        return [as_mapping(item) for item in payload]

    if isinstance(payload, Mapping):
        data = dict(payload)

        for key in ("capsules", "items", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return [as_mapping(item) for item in value]

        nested_data = data.get("data")
        if isinstance(nested_data, list):
            return [as_mapping(item) for item in nested_data]

        if isinstance(nested_data, Mapping):
            for key in ("capsules", "items", "results"):
                value = nested_data.get(key)
                if isinstance(value, list):
                    return [as_mapping(item) for item in value]

    raise agent_response_error(
        "Agent list_capsules response must be a list or an object containing capsules/items."
    )


def normalize_capsule_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize varied capsule inventory keys into CapsuleSummary fields."""

    data = dict(item)

    capsule_id = (
        data.get("capsule_id")
        or data.get("id")
        or data.get("name")
        or data.get("capsule_name")
    )

    filename = data.get("filename")
    path_value = data.get("path") or data.get("capsule_file") or data.get("capsule_path")

    if not capsule_id and filename:
        capsule_id = Path(str(filename)).stem

    if not capsule_id and path_value:
        capsule_id = Path(str(path_value)).stem

    if not filename and path_value:
        filename = Path(str(path_value)).name

    if not capsule_id:
        raise agent_response_error("Capsule summary is missing capsule_id/id/name.")

    data["capsule_id"] = str(capsule_id)
    data.setdefault("filename", str(filename) if filename else None)
    data.setdefault("verified", bool(data.get("valid", data.get("verified", False))))

    return data


def build_import_response(
    payload: Any,
    *,
    default_capsule_id: str,
    default_filename: str,
) -> CapsuleImportResponse:
    """Normalize Agent import response into CapsuleImportResponse."""

    data = as_mapping(payload)
    data.setdefault("ok", True)
    data.setdefault("message", "Capsule import accepted.")

    capsule_data: dict[str, Any] | None = None

    if isinstance(data.get("capsule"), BaseModel):
        capsule_data = data["capsule"].model_dump(mode="json")
    elif isinstance(data.get("capsule"), Mapping):
        capsule_data = dict(data["capsule"])
    else:
        capsule_data = {
            "capsule_id": data.get("capsule_id") or default_capsule_id,
            "capsule_version": data.get("capsule_version"),
            "app_version": data.get("app_version"),
            "channel": data.get("channel"),
            "filename": data.get("filename") or default_filename,
            "verified": bool(data.get("valid", data.get("verified", True))),
        }

    capsule_data = normalize_capsule_summary(capsule_data)

    data["capsule"] = CapsuleSummary(**capsule_data)
    data.setdefault("capsule_id", capsule_data["capsule_id"])

    return CapsuleImportResponse(**data)


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


def validate_capsule_path_string(value: str) -> str:
    """Validate an existing capsule path string."""

    normalized = value.strip()

    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "ok": False,
                "error": "invalid_capsule_path",
                "message": "Capsule path cannot be empty.",
            },
        )

    if Path(normalized).suffix != CAPSULE_EXTENSION:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "ok": False,
                "error": "invalid_capsule_extension",
                "message": f"Capsule path must end with {CAPSULE_EXTENSION}.",
            },
        )

    if "\x00" in normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "ok": False,
                "error": "unsafe_capsule_path",
                "message": "Capsule path contains a forbidden token.",
            },
        )

    return normalized


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
    "build_import_response",
    "delete_capsule",
    "enum_value",
    "get_agent_client",
    "get_capsule",
    "import_capsule",
    "list_capsules",
    "normalize_capsule_list_response",
    "normalize_capsule_summary",
    "resolve_upload_filename",
    "router",
    "validate_capsule_filename",
    "validate_capsule_id",
    "validate_capsule_path_string",
    "validate_channel",
    "validate_exposure_mode",
    "validate_network_profile",
    "verify_capsule",
]