"""
Client for the Konnaxion Agent API.

The Konnaxion Capsule Manager must not control Docker, firewall rules,
host paths, backups, or runtime services directly. It communicates with
the local Konnaxion Agent through this constrained client.

This client mirrors the allowlisted API routes exposed by ``kx_agent.api``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from kx_shared.konnaxion_constants import (
    DEFAULT_EXPOSURE_MODE,
    DEFAULT_NETWORK_PROFILE,
    DockerService,
    ExposureMode,
    NetworkProfile,
)


DEFAULT_AGENT_BASE_URL = "http://127.0.0.1:8765/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0


class KonnaxionAgentClientError(RuntimeError):
    """Base error raised by the Manager's Agent API client."""


class KonnaxionAgentConnectionError(KonnaxionAgentClientError):
    """Raised when the Manager cannot reach the local Agent."""


class KonnaxionAgentResponseError(KonnaxionAgentClientError):
    """Raised when the Agent returns an error response."""

    def __init__(
        self,
        *,
        status_code: int,
        message: str,
        response_body: Any | None = None,
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.response_body = response_body
        super().__init__(f"Agent API error {status_code}: {message}")


@dataclass(frozen=True, slots=True)
class AgentClientConfig:
    """Connection settings for the local Konnaxion Agent."""

    base_url: str = DEFAULT_AGENT_BASE_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    token: str | None = None

    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")


class KonnaxionAgentClient:
    """Typed async client used by Konnaxion Capsule Manager."""

    def __init__(
        self,
        config: AgentClientConfig | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config or AgentClientConfig()
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=self.config.normalized_base_url(),
            timeout=self.config.timeout_seconds,
            headers=self._default_headers(),
        )

    async def __aenter__(self) -> "KonnaxionAgentClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client if this object owns it."""

        if self._owns_client:
            await self._client.aclose()

    def _default_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "konnaxion-capsule-manager",
        }
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        return headers

    async def _get(self, path: str) -> dict[str, Any]:
        try:
            response = await self._client.get(path)
        except httpx.ConnectError as exc:
            raise KonnaxionAgentConnectionError(
                "Unable to connect to the local Konnaxion Agent."
            ) from exc
        except httpx.TimeoutException as exc:
            raise KonnaxionAgentConnectionError(
                "Timed out while communicating with the local Konnaxion Agent."
            ) from exc
        return self._parse_response(response)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(path, json=strip_none(payload))
        except httpx.ConnectError as exc:
            raise KonnaxionAgentConnectionError(
                "Unable to connect to the local Konnaxion Agent."
            ) from exc
        except httpx.TimeoutException as exc:
            raise KonnaxionAgentConnectionError(
                "Timed out while communicating with the local Konnaxion Agent."
            ) from exc
        return self._parse_response(response)

    def _parse_response(self, response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError:
            body = {"detail": response.text}

        if response.is_error:
            message = extract_error_message(body)
            raise KonnaxionAgentResponseError(
                status_code=response.status_code,
                message=message,
                response_body=body,
            )

        if not isinstance(body, dict):
            raise KonnaxionAgentResponseError(
                status_code=response.status_code,
                message="Agent returned a non-object JSON response.",
                response_body=body,
            )

        return body

    async def health(self) -> dict[str, Any]:
        """Return basic Agent process health."""

        return await self._get("/health")

    async def info(self) -> dict[str, Any]:
        """Return non-sensitive Agent metadata."""

        return await self._get("/agent/info")

    async def import_capsule(
        self,
        *,
        capsule_path: str,
        instance_id: str,
        network_profile: NetworkProfile | str = DEFAULT_NETWORK_PROFILE,
    ) -> dict[str, Any]:
        return await self._post(
            "/capsules/import",
            {
                "capsule_path": capsule_path,
                "instance_id": instance_id,
                "network_profile": enum_value(network_profile),
            },
        )

    async def verify_capsule(self, *, capsule_path: str) -> dict[str, Any]:
        return await self._post(
            "/capsules/verify",
            {
                "capsule_path": capsule_path,
            },
        )

    async def create_instance(
        self,
        *,
        instance_id: str,
        capsule_id: str,
        network_profile: NetworkProfile | str = DEFAULT_NETWORK_PROFILE,
        exposure_mode: ExposureMode | str = DEFAULT_EXPOSURE_MODE,
        generate_secrets: bool = True,
    ) -> dict[str, Any]:
        return await self._post(
            "/instances/create",
            {
                "instance_id": instance_id,
                "capsule_id": capsule_id,
                "network_profile": enum_value(network_profile),
                "exposure_mode": enum_value(exposure_mode),
                "generate_secrets": generate_secrets,
            },
        )

    async def start_instance(
        self,
        *,
        instance_id: str,
        run_security_gate: bool = True,
    ) -> dict[str, Any]:
        return await self._post(
            "/instances/start",
            {
                "instance_id": instance_id,
                "run_security_gate": run_security_gate,
            },
        )

    async def stop_instance(
        self,
        *,
        instance_id: str,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        return await self._post(
            "/instances/stop",
            {
                "instance_id": instance_id,
                "timeout_seconds": timeout_seconds,
            },
        )

    async def instance_status(self, *, instance_id: str) -> dict[str, Any]:
        return await self._post(
            "/instances/status",
            {
                "instance_id": instance_id,
            },
        )

    async def instance_logs(
        self,
        *,
        instance_id: str,
        service: DockerService | str | None = None,
        tail: int = 200,
    ) -> dict[str, Any]:
        return await self._post(
            "/instances/logs",
            {
                "instance_id": instance_id,
                "service": enum_value(service) if service is not None else None,
                "tail": tail,
            },
        )

    async def backup_instance(
        self,
        *,
        instance_id: str,
        backup_class: str = "manual",
        verify_after_create: bool = True,
    ) -> dict[str, Any]:
        return await self._post(
            "/instances/backup",
            {
                "instance_id": instance_id,
                "backup_class": backup_class,
                "verify_after_create": verify_after_create,
            },
        )

    async def restore_instance(
        self,
        *,
        instance_id: str,
        backup_id: str,
        create_pre_restore_backup: bool = True,
    ) -> dict[str, Any]:
        return await self._post(
            "/instances/restore",
            {
                "instance_id": instance_id,
                "backup_id": backup_id,
                "create_pre_restore_backup": create_pre_restore_backup,
            },
        )

    async def restore_new_instance(
        self,
        *,
        source_backup_id: str,
        new_instance_id: str,
        network_profile: NetworkProfile | str = DEFAULT_NETWORK_PROFILE,
    ) -> dict[str, Any]:
        return await self._post(
            "/instances/restore-new",
            {
                "source_backup_id": source_backup_id,
                "new_instance_id": new_instance_id,
                "network_profile": enum_value(network_profile),
            },
        )

    async def update_instance(
        self,
        *,
        instance_id: str,
        capsule_path: str,
        create_pre_update_backup: bool = True,
    ) -> dict[str, Any]:
        return await self._post(
            "/instances/update",
            {
                "instance_id": instance_id,
                "capsule_path": capsule_path,
                "create_pre_update_backup": create_pre_update_backup,
            },
        )

    async def rollback_instance(
        self,
        *,
        instance_id: str,
        target_release_id: str | None = None,
        restore_data: bool = True,
    ) -> dict[str, Any]:
        return await self._post(
            "/instances/rollback",
            {
                "instance_id": instance_id,
                "target_release_id": target_release_id,
                "restore_data": restore_data,
            },
        )

    async def instance_health(self, *, instance_id: str) -> dict[str, Any]:
        return await self._post(
            "/instances/health",
            {
                "instance_id": instance_id,
            },
        )

    async def security_check(
        self,
        *,
        instance_id: str,
        blocking: bool = True,
    ) -> dict[str, Any]:
        return await self._post(
            "/security/check",
            {
                "instance_id": instance_id,
                "blocking": blocking,
            },
        )

    async def set_network_profile(
        self,
        *,
        instance_id: str,
        network_profile: NetworkProfile | str,
        exposure_mode: ExposureMode | str = DEFAULT_EXPOSURE_MODE,
        public_mode_expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        return await self._post(
            "/network/set-profile",
            {
                "instance_id": instance_id,
                "network_profile": enum_value(network_profile),
                "exposure_mode": enum_value(exposure_mode),
                "public_mode_expires_at": (
                    public_mode_expires_at.isoformat()
                    if public_mode_expires_at is not None
                    else None
                ),
            },
        )


def enum_value(value: Any) -> Any:
    """Return the string value for enum-like objects."""

    return getattr(value, "value", value)


def strip_none(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove None values from a JSON payload."""

    return {key: value for key, value in payload.items() if value is not None}


def extract_error_message(body: Any) -> str:
    """Extract a useful error message from an Agent error response."""

    if isinstance(body, dict):
        detail = body.get("detail") or body.get("error") or body.get("message")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, list):
            return "; ".join(str(item) for item in detail)
        if detail is not None:
            return str(detail)

    return "Unknown Agent API error."


__all__ = [
    "AgentClientConfig",
    "DEFAULT_AGENT_BASE_URL",
    "DEFAULT_TIMEOUT_SECONDS",
    "KonnaxionAgentClient",
    "KonnaxionAgentClientError",
    "KonnaxionAgentConnectionError",
    "KonnaxionAgentResponseError",
    "enum_value",
    "extract_error_message",
    "strip_none",
]
