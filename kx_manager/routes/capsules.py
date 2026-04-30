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
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from kx_shared.konnaxion_constants import (
    CAPSULE_EXTENSION,
    DEFAULT_CHANNEL,
    DEFAULT_NETWORK_PROFILE,
    DEFAULT_EXPOSURE_MODE,
    NetworkProfile,
)


router = APIRouter(prefix="/capsules", tags=["capsules"])


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

    path: str = Field(..., min_length=1)

    @field_validator("path")
    @classmethod
    def validate_capsule_extension(cls, value: str) -> str:
        """Require the canonical ``.kxcap`` extension."""

        if not value.endswith(CAPSULE_EXTENSION):
            raise ValueError(f"capsule path must end with {CAPSULE_EXTENSION}")
        return value


class CapsuleVerifyResponse(BaseModel):
    """Verification result returned by the Agent."""

    ok: bool
    capsule_id: str | None = None
    capsule_version: str | None = None
    signature_status: str | None = None
    checksum_status: str | None = None
    manifest_status: str | None = None
    security_status: str | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CapsuleImportResponse(BaseModel):
    """Import result returned after Agent-side capsule import."""

    ok: bool
    capsule_id: str
    capsule_version: str | None = None
    imported: bool = True
    verified: bool = True
    message: str | None = None
    warnings: list[str] = Field(default_factory=list)


class CapsuleDeleteResponse(BaseModel):
    """Delete/forget result."""

    ok: bool
    capsule_id: str
    deleted: bool = False
    message: str | None = None


class CapsuleImportOptions(BaseModel):
    """Import options normalized by the route layer."""

    channel: str = DEFAULT_CHANNEL
    network_profile: str = Field(default_factory=lambda: DEFAULT_NETWORK_PROFILE.value)
    exposure_mode: str = Field(default_factory=lambda: DEFAULT_EXPOSURE_MODE.value)

    @field_validator("network_profile")
    @classmethod
    def validate_network_profile(cls, value: str) -> str:
        """Require a canonical network profile."""

        allowed = {profile.value for profile in NetworkProfile}
        if value not in allowed:
            raise ValueError(
                f"network_profile must be one of: {', '.join(sorted(allowed))}"
            )
        return value


def _agent(request: Request) -> AgentClientProtocol:
    """Return the configured Agent client or raise a clear API error."""

    client = getattr(request.app.state, "agent_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Konnaxion Agent client is not configured",
        )
    return client


def _ensure_kxcap_filename(filename: str | None) -> str:
    """Validate uploaded capsule filename."""

    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="capsule filename is required",
        )

    clean_name = Path(filename).name
    if not clean_name.endswith(CAPSULE_EXTENSION):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"capsule file must use the canonical {CAPSULE_EXTENSION} extension",
        )

    return clean_name


def _agent_error(exc: Exception) -> HTTPException:
    """Convert lower-level Agent/client failures to HTTP errors."""

    message = str(exc) or exc.__class__.__name__
    lowered = message.lower()

    if "not found" in lowered:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)

    if "signature" in lowered or "checksum" in lowered or "security" in lowered:
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=message,
        )

    if "forbidden" in lowered or "not allowed" in lowered:
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)

    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Konnaxion Agent request failed: {message}",
    )


@router.get("", response_model=list[CapsuleSummary])
async def list_capsules(request: Request) -> list[Mapping[str, Any]]:
    """List capsules already imported into the local Manager/Agent state."""

    try:
        return await _agent(request).list_capsules()
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - boundary wrapper
        raise _agent_error(exc) from exc


@router.get("/{capsule_id}", response_model=CapsuleDetail)
async def get_capsule(capsule_id: str, request: Request) -> Mapping[str, Any]:
    """Return details for one imported capsule."""

    try:
        return await _agent(request).get_capsule(capsule_id)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - boundary wrapper
        raise _agent_error(exc) from exc


@router.post("/verify", response_model=CapsuleVerifyResponse)
async def verify_capsule(
    payload: CapsuleVerifyRequest,
    request: Request,
) -> Mapping[str, Any]:
    """Verify a capsule path already readable by the Agent.

    Upload verification should use ``POST /capsules/import`` because uploaded
    bytes must be handed to the Agent before verification.
    """

    try:
        return await _agent(request).verify_capsule_path(payload.path)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - boundary wrapper
        raise _agent_error(exc) from exc


@router.post("/import", response_model=CapsuleImportResponse)
async def import_capsule(
    request: Request,
    file: UploadFile = File(...),
    channel: str = DEFAULT_CHANNEL,
    network_profile: str = DEFAULT_NETWORK_PROFILE.value,
    exposure_mode: str = DEFAULT_EXPOSURE_MODE.value,
) -> Mapping[str, Any]:
    """Import a signed ``.kxcap`` upload through the Konnaxion Agent."""

    filename = _ensure_kxcap_filename(file.filename)

    try:
        options = CapsuleImportOptions(
            channel=channel,
            network_profile=network_profile,
            exposure_mode=exposure_mode,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="uploaded capsule is empty",
        )

    try:
        return await _agent(request).import_capsule_upload(
            filename=filename,
            content=content,
            channel=options.channel,
            network_profile=options.network_profile,
            exposure_mode=options.exposure_mode,
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - boundary wrapper
        raise _agent_error(exc) from exc


@router.delete("/{capsule_id}", response_model=CapsuleDeleteResponse)
async def delete_capsule(capsule_id: str, request: Request) -> Mapping[str, Any]:
    """Delete or forget an imported capsule through the Agent."""

    try:
        return await _agent(request).delete_capsule(capsule_id)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - boundary wrapper
        raise _agent_error(exc) from exc


__all__ = [
    "CapsuleDeleteResponse",
    "CapsuleDetail",
    "CapsuleImportOptions",
    "CapsuleImportResponse",
    "CapsuleSummary",
    "CapsuleVerifyRequest",
    "CapsuleVerifyResponse",
    "router",
]
