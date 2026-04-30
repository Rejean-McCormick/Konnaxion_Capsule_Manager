"""
Security routes for Konnaxion Capsule Manager.

The Manager exposes user-facing security endpoints, but it must not run
privileged host, Docker, firewall, or Security Gate operations directly.
All enforcement is delegated to the Konnaxion Agent through an injected client.

Framework:
- FastAPI APIRouter when FastAPI is installed.
- The module remains importable without FastAPI for tests/bootstrap.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Protocol

from kx_shared.konnaxion_constants import (
    BLOCKING_SECURITY_CHECKS,
    SecurityGateCheck,
    SecurityGateStatus,
)
from kx_shared.validation import (
    ValidationIssue,
    raise_if_issues,
    validate_identifier,
    validate_security_gate_check,
    validate_security_gate_results,
    validate_security_gate_status,
)


try:  # pragma: no cover - import fallback is for bootstrap/test environments.
    from fastapi import APIRouter, Depends, HTTPException, Query, status
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    Depends = None  # type: ignore[assignment]
    HTTPException = RuntimeError  # type: ignore[assignment]
    Query = None  # type: ignore[assignment]
    status = None  # type: ignore[assignment]


@dataclass(frozen=True)
class SecurityCheckResult:
    """One Security Gate check result."""

    check: str
    status: str
    message: str = ""
    blocking: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SecurityGateSummary:
    """Manager-facing Security Gate summary."""

    instance_id: str
    status: str
    checked_at: str
    results: tuple[SecurityCheckResult, ...]
    blocking_failures: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status == SecurityGateStatus.PASS.value and not self.blocking_failures


@dataclass(frozen=True)
class SecurityCheckRequest:
    """Request body for running the Security Gate."""

    force: bool = False
    include_warnings: bool = True


class AgentSecurityClient(Protocol):
    """Protocol expected from kx_manager.client security implementation."""

    def get_security_summary(self, instance_id: str) -> Mapping[str, Any]:
        """Return last known Security Gate summary for an instance."""

    def run_security_gate(
        self,
        instance_id: str,
        *,
        force: bool = False,
        include_warnings: bool = True,
    ) -> Mapping[str, Any]:
        """Run Security Gate checks through the privileged Agent."""

    def get_security_check_detail(self, instance_id: str, check: str) -> Mapping[str, Any]:
        """Return detail for one Security Gate check."""

    def acknowledge_security_warning(
        self,
        instance_id: str,
        check: str,
        *,
        note: str = "",
    ) -> Mapping[str, Any]:
        """Acknowledge a non-blocking warning through the Agent audit path."""


_agent_security_client: AgentSecurityClient | None = None


def set_agent_security_client(client: AgentSecurityClient) -> None:
    """Set the process-wide Agent security client used by FastAPI dependencies.

    Production code may instead override `get_agent_security_client` through
    FastAPI dependency overrides.
    """

    global _agent_security_client
    _agent_security_client = client


def get_agent_security_client() -> AgentSecurityClient:
    """FastAPI dependency for retrieving the Agent security client."""

    if _agent_security_client is None:
        raise RuntimeError("Agent security client is not configured.")
    return _agent_security_client


def normalize_security_summary(instance_id: str, payload: Mapping[str, Any]) -> SecurityGateSummary:
    """Normalize Agent security payload into Manager response shape."""

    issues: list[ValidationIssue] = []
    issues.extend(validate_identifier(instance_id, field="instance_id"))

    raw_results = payload.get("results", {})
    normalized_results: list[SecurityCheckResult] = []

    if isinstance(raw_results, Mapping):
        flat_statuses: dict[str, str] = {}

        for check, value in raw_results.items():
            check_name = str(check)
            issues.extend(validate_security_gate_check(check_name))

            if isinstance(value, Mapping):
                status_value = str(value.get("status", SecurityGateStatus.UNKNOWN.value))
                message = str(value.get("message", ""))
                details = value.get("details", {})
            else:
                status_value = str(value)
                message = ""
                details = {}

            issues.extend(validate_security_gate_status(status_value))
            flat_statuses[check_name] = status_value

            normalized_results.append(
                SecurityCheckResult(
                    check=check_name,
                    status=status_value,
                    message=message,
                    blocking=_is_blocking_check(check_name),
                    details=details if isinstance(details, Mapping) else {},
                )
            )

        issues.extend(validate_security_gate_results(flat_statuses))

    elif isinstance(raw_results, list):
        flat_statuses = {}

        for item in raw_results:
            if not isinstance(item, Mapping):
                issues.append(
                    ValidationIssue(
                        code="invalid_security_result",
                        message="Each security result list item must be a mapping.",
                        field="results",
                    )
                )
                continue

            check_name = str(item.get("check", ""))
            status_value = str(item.get("status", SecurityGateStatus.UNKNOWN.value))
            message = str(item.get("message", ""))
            details = item.get("details", {})

            issues.extend(validate_security_gate_check(check_name))
            issues.extend(validate_security_gate_status(status_value))

            if check_name:
                flat_statuses[check_name] = status_value

            normalized_results.append(
                SecurityCheckResult(
                    check=check_name,
                    status=status_value,
                    message=message,
                    blocking=_is_blocking_check(check_name),
                    details=details if isinstance(details, Mapping) else {},
                )
            )

        issues.extend(validate_security_gate_results(flat_statuses))

    else:
        issues.append(
            ValidationIssue(
                code="invalid_security_results",
                message="Security payload results must be a mapping or list.",
                field="results",
            )
        )

    explicit_status = payload.get("status")
    if explicit_status is not None:
        summary_status = str(explicit_status)
        issues.extend(validate_security_gate_status(summary_status))
    else:
        summary_status = _derive_status(normalized_results)

    raise_if_issues(issues)

    blocking_failures = tuple(
        result.check
        for result in normalized_results
        if result.blocking and result.status == SecurityGateStatus.FAIL_BLOCKING.value
    )

    warnings = tuple(
        result.check
        for result in normalized_results
        if result.status == SecurityGateStatus.WARN.value
    )

    checked_at = str(payload.get("checked_at") or _utc_now_iso())

    return SecurityGateSummary(
        instance_id=instance_id,
        status=summary_status,
        checked_at=checked_at,
        results=tuple(sorted(normalized_results, key=lambda result: result.check)),
        blocking_failures=blocking_failures,
        warnings=warnings,
    )


def serialize_security_summary(summary: SecurityGateSummary) -> dict[str, Any]:
    """Serialize dataclass summary for JSON responses."""

    return {
        "instance_id": summary.instance_id,
        "status": summary.status,
        "passed": summary.passed,
        "checked_at": summary.checked_at,
        "blocking_failures": list(summary.blocking_failures),
        "warnings": list(summary.warnings),
        "results": [asdict(result) for result in summary.results],
    }


def list_canonical_security_checks() -> dict[str, Any]:
    """Return canonical Security Gate check metadata for UI rendering."""

    checks = []
    blocking_values = {str(check.value if isinstance(check, Enum) else check) for check in BLOCKING_SECURITY_CHECKS}

    for check in SecurityGateCheck:
        checks.append(
            {
                "check": check.value,
                "blocking": check.value in blocking_values,
            }
        )

    return {
        "statuses": [status.value for status in SecurityGateStatus],
        "checks": checks,
    }


def create_router() -> Any:
    """Create the FastAPI router.

    Kept as a factory so tests can import this module without requiring app
    initialization side effects.
    """

    if APIRouter is None:  # pragma: no cover
        raise RuntimeError("FastAPI is required to create kx_manager.routes.security router.")

    router = APIRouter(prefix="/security", tags=["security"])

    @router.get("/checks")
    def get_security_checks() -> dict[str, Any]:
        """List canonical Security Gate checks and statuses."""

        return list_canonical_security_checks()

    @router.get("/{instance_id}")
    def get_security_summary(
        instance_id: str,
        client: AgentSecurityClient = Depends(get_agent_security_client),  # type: ignore[misc]
    ) -> dict[str, Any]:
        """Return last known Security Gate summary for an instance."""

        _raise_http_validation(validate_identifier(instance_id, field="instance_id"))

        try:
            payload = client.get_security_summary(instance_id)
            summary = normalize_security_summary(instance_id, payload)
            return serialize_security_summary(summary)
        except ValidationIssue as exc:  # pragma: no cover - defensive only.
            raise _http_error(500, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise _http_error(502, f"Could not retrieve Security Gate summary: {exc}") from exc

    @router.post("/{instance_id}/check")
    def run_security_check(
        instance_id: str,
        request: SecurityCheckRequest | None = None,
        client: AgentSecurityClient = Depends(get_agent_security_client),  # type: ignore[misc]
    ) -> dict[str, Any]:
        """Run Security Gate through the Agent and return normalized results."""

        _raise_http_validation(validate_identifier(instance_id, field="instance_id"))
        request = request or SecurityCheckRequest()

        try:
            payload = client.run_security_gate(
                instance_id,
                force=request.force,
                include_warnings=request.include_warnings,
            )
            summary = normalize_security_summary(instance_id, payload)
            return serialize_security_summary(summary)
        except Exception as exc:  # noqa: BLE001
            raise _http_error(502, f"Could not run Security Gate: {exc}") from exc

    @router.get("/{instance_id}/checks/{check}")
    def get_security_check_detail(
        instance_id: str,
        check: str,
        client: AgentSecurityClient = Depends(get_agent_security_client),  # type: ignore[misc]
    ) -> dict[str, Any]:
        """Return detail for one Security Gate check."""

        _raise_http_validation(validate_identifier(instance_id, field="instance_id"))
        _raise_http_validation(validate_security_gate_check(check))

        try:
            payload = client.get_security_check_detail(instance_id, check)
        except Exception as exc:  # noqa: BLE001
            raise _http_error(502, f"Could not retrieve Security Gate check detail: {exc}") from exc

        status_value = str(payload.get("status", SecurityGateStatus.UNKNOWN.value))
        _raise_http_validation(validate_security_gate_status(status_value))

        return {
            "instance_id": instance_id,
            "check": check,
            "status": status_value,
            "blocking": _is_blocking_check(check),
            "message": str(payload.get("message", "")),
            "details": payload.get("details", {}),
            "checked_at": str(payload.get("checked_at") or _utc_now_iso()),
        }

    @router.post("/{instance_id}/checks/{check}/acknowledge")
    def acknowledge_security_warning(
        instance_id: str,
        check: str,
        note: str = "",
        client: AgentSecurityClient = Depends(get_agent_security_client),  # type: ignore[misc]
    ) -> dict[str, Any]:
        """Acknowledge a non-blocking Security Gate warning.

        Blocking failures cannot be acknowledged away at the Manager layer.
        """

        _raise_http_validation(validate_identifier(instance_id, field="instance_id"))
        _raise_http_validation(validate_security_gate_check(check))

        if _is_blocking_check(check):
            raise _http_error(409, f"Blocking Security Gate check cannot be acknowledged: {check}")

        try:
            payload = client.acknowledge_security_warning(instance_id, check, note=note)
        except Exception as exc:  # noqa: BLE001
            raise _http_error(502, f"Could not acknowledge Security Gate warning: {exc}") from exc

        return {
            "instance_id": instance_id,
            "check": check,
            "acknowledged": bool(payload.get("acknowledged", True)),
            "note": note,
            "acknowledged_at": str(payload.get("acknowledged_at") or _utc_now_iso()),
        }

    return router


def _derive_status(results: list[SecurityCheckResult]) -> str:
    if any(result.status == SecurityGateStatus.FAIL_BLOCKING.value for result in results):
        return SecurityGateStatus.FAIL_BLOCKING.value
    if any(result.status == SecurityGateStatus.WARN.value for result in results):
        return SecurityGateStatus.WARN.value
    if results and all(result.status in {SecurityGateStatus.PASS.value, SecurityGateStatus.SKIPPED.value} for result in results):
        return SecurityGateStatus.PASS.value
    return SecurityGateStatus.UNKNOWN.value


def _is_blocking_check(check: str) -> bool:
    blocking_values = {str(item.value if isinstance(item, Enum) else item) for item in BLOCKING_SECURITY_CHECKS}
    return check in blocking_values


def _raise_http_validation(issues: list[ValidationIssue]) -> None:
    if not issues:
        return
    issue = issues[0]
    raise _http_error(422, issue.message)


def _http_error(status_code: int, detail: str) -> Exception:
    if APIRouter is None or status is None:  # pragma: no cover
        return RuntimeError(detail)
    return HTTPException(status_code=status_code, detail=detail)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


router = create_router() if APIRouter is not None else None


__all__ = [
    "AgentSecurityClient",
    "SecurityCheckRequest",
    "SecurityCheckResult",
    "SecurityGateSummary",
    "create_router",
    "get_agent_security_client",
    "list_canonical_security_checks",
    "normalize_security_summary",
    "router",
    "serialize_security_summary",
    "set_agent_security_client",
]
