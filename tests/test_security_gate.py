"""Security Gate tests for Konnaxion Agent.

These tests enforce the canonical Security Gate contract:
- mandatory checks exist
- blocking failures stop startup
- public/internal port exposure is rejected
- unsafe Docker runtime options are rejected
- signed capsules and checksums are blocking requirements
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

import pytest

from kx_shared.konnaxion_constants import (
    BLOCKING_SECURITY_CHECKS,
    FORBIDDEN_PUBLIC_PORTS,
    SecurityGateCheck,
    SecurityGateStatus,
)


MANDATORY_CHECKS = {
    SecurityGateCheck.CAPSULE_SIGNATURE,
    SecurityGateCheck.IMAGE_CHECKSUMS,
    SecurityGateCheck.MANIFEST_SCHEMA,
    SecurityGateCheck.SECRETS_PRESENT,
    SecurityGateCheck.SECRETS_NOT_DEFAULT,
    SecurityGateCheck.FIREWALL_ENABLED,
    SecurityGateCheck.DANGEROUS_PORTS_BLOCKED,
    SecurityGateCheck.POSTGRES_NOT_PUBLIC,
    SecurityGateCheck.REDIS_NOT_PUBLIC,
    SecurityGateCheck.DOCKER_SOCKET_NOT_MOUNTED,
    SecurityGateCheck.NO_PRIVILEGED_CONTAINERS,
    SecurityGateCheck.NO_HOST_NETWORK,
    SecurityGateCheck.ALLOWED_IMAGES_ONLY,
    SecurityGateCheck.ADMIN_SURFACE_PRIVATE,
    SecurityGateCheck.BACKUP_CONFIGURED,
}


@dataclass(frozen=True)
class FakeSecurityCheckResult:
    """Fallback test fixture matching the expected SecurityCheckResult shape."""

    check: SecurityGateCheck
    status: SecurityGateStatus
    message: str = ""


def test_security_gate_status_values_are_canonical() -> None:
    """Security Gate statuses must remain aligned with DOC-00."""

    assert {status.value for status in SecurityGateStatus} == {
        "PASS",
        "WARN",
        "FAIL_BLOCKING",
        "SKIPPED",
        "UNKNOWN",
    }


def test_mandatory_security_gate_checks_are_canonical() -> None:
    """All canonical Security Gate checks must be present."""

    assert {check.value for check in MANDATORY_CHECKS} == {
        "capsule_signature",
        "image_checksums",
        "manifest_schema",
        "secrets_present",
        "secrets_not_default",
        "firewall_enabled",
        "dangerous_ports_blocked",
        "postgres_not_public",
        "redis_not_public",
        "docker_socket_not_mounted",
        "no_privileged_containers",
        "no_host_network",
        "allowed_images_only",
        "admin_surface_private",
        "backup_configured",
    }


def test_blocking_security_gate_checks_are_canonical() -> None:
    """Critical checks must block startup when they fail."""

    assert BLOCKING_SECURITY_CHECKS == frozenset(
        {
            SecurityGateCheck.CAPSULE_SIGNATURE,
            SecurityGateCheck.IMAGE_CHECKSUMS,
            SecurityGateCheck.MANIFEST_SCHEMA,
            SecurityGateCheck.SECRETS_PRESENT,
            SecurityGateCheck.SECRETS_NOT_DEFAULT,
            SecurityGateCheck.DANGEROUS_PORTS_BLOCKED,
            SecurityGateCheck.POSTGRES_NOT_PUBLIC,
            SecurityGateCheck.REDIS_NOT_PUBLIC,
            SecurityGateCheck.DOCKER_SOCKET_NOT_MOUNTED,
            SecurityGateCheck.NO_PRIVILEGED_CONTAINERS,
            SecurityGateCheck.NO_HOST_NETWORK,
            SecurityGateCheck.ALLOWED_IMAGES_ONLY,
        }
    )


def test_forbidden_public_ports_are_canonical() -> None:
    """Internal service ports must never be exposed publicly."""

    assert FORBIDDEN_PUBLIC_PORTS == frozenset({3000, 5000, 5432, 6379, 5555, 8000})


@pytest.mark.parametrize(
    ("check", "expected_blocking"),
    [
        (SecurityGateCheck.CAPSULE_SIGNATURE, True),
        (SecurityGateCheck.IMAGE_CHECKSUMS, True),
        (SecurityGateCheck.MANIFEST_SCHEMA, True),
        (SecurityGateCheck.SECRETS_PRESENT, True),
        (SecurityGateCheck.SECRETS_NOT_DEFAULT, True),
        (SecurityGateCheck.FIREWALL_ENABLED, False),
        (SecurityGateCheck.DANGEROUS_PORTS_BLOCKED, True),
        (SecurityGateCheck.POSTGRES_NOT_PUBLIC, True),
        (SecurityGateCheck.REDIS_NOT_PUBLIC, True),
        (SecurityGateCheck.DOCKER_SOCKET_NOT_MOUNTED, True),
        (SecurityGateCheck.NO_PRIVILEGED_CONTAINERS, True),
        (SecurityGateCheck.NO_HOST_NETWORK, True),
        (SecurityGateCheck.ALLOWED_IMAGES_ONLY, True),
        (SecurityGateCheck.ADMIN_SURFACE_PRIVATE, False),
        (SecurityGateCheck.BACKUP_CONFIGURED, False),
    ],
)
def test_blocking_check_membership(
    check: SecurityGateCheck,
    expected_blocking: bool,
) -> None:
    """Each check must have the expected blocking behavior."""

    assert (check in BLOCKING_SECURITY_CHECKS) is expected_blocking


def test_security_gate_module_exports_expected_api() -> None:
    """kx_agent.security.gate must expose the expected public functions/classes."""

    gate = importlib.import_module("kx_agent.security.gate")

    for name in (
        "SecurityGateResult",
        "SecurityCheckResult",
        "run_security_gate",
        "is_security_gate_passing",
        "assert_security_gate_passing",
    ):
        assert hasattr(gate, name), f"kx_agent.security.gate missing {name}"


def test_security_checks_module_exports_expected_api() -> None:
    """kx_agent.security.checks must expose individual check helpers."""

    checks = importlib.import_module("kx_agent.security.checks")

    for name in (
        "check_capsule_signature",
        "check_image_checksums",
        "check_manifest_schema",
        "check_secrets_present",
        "check_secrets_not_default",
        "check_dangerous_ports_blocked",
        "check_postgres_not_public",
        "check_redis_not_public",
        "check_docker_socket_not_mounted",
        "check_no_privileged_containers",
        "check_no_host_network",
        "check_allowed_images_only",
    ):
        assert hasattr(checks, name), f"kx_agent.security.checks missing {name}"


def test_security_gate_passes_when_all_checks_pass() -> None:
    """A gate with only PASS/WARN/SKIPPED checks should be considered passing."""

    gate = importlib.import_module("kx_agent.security.gate")

    results = [
        _make_check_result(
            gate,
            SecurityGateCheck.CAPSULE_SIGNATURE,
            SecurityGateStatus.PASS,
        ),
        _make_check_result(
            gate,
            SecurityGateCheck.FIREWALL_ENABLED,
            SecurityGateStatus.WARN,
        ),
        _make_check_result(
            gate,
            SecurityGateCheck.ADMIN_SURFACE_PRIVATE,
            SecurityGateStatus.SKIPPED,
        ),
    ]

    gate_result = _make_gate_result(gate, results)

    assert gate.is_security_gate_passing(gate_result) is True


def test_security_gate_fails_when_blocking_check_fails() -> None:
    """A FAIL_BLOCKING result for a blocking check must fail the gate."""

    gate = importlib.import_module("kx_agent.security.gate")

    results = [
        _make_check_result(
            gate,
            SecurityGateCheck.CAPSULE_SIGNATURE,
            SecurityGateStatus.FAIL_BLOCKING,
            "unsigned capsule",
        )
    ]

    gate_result = _make_gate_result(gate, results)

    assert gate.is_security_gate_passing(gate_result) is False

    with pytest.raises(Exception):
        gate.assert_security_gate_passing(gate_result)


def test_security_gate_fails_when_blocking_check_is_unknown() -> None:
    """UNKNOWN on a blocking check should not allow startup."""

    gate = importlib.import_module("kx_agent.security.gate")

    results = [
        _make_check_result(
            gate,
            SecurityGateCheck.IMAGE_CHECKSUMS,
            SecurityGateStatus.UNKNOWN,
            "checksum state unavailable",
        )
    ]

    gate_result = _make_gate_result(gate, results)

    assert gate.is_security_gate_passing(gate_result) is False


def test_security_gate_allows_warning_on_nonblocking_check() -> None:
    """WARN on a non-blocking check should not fail the entire gate."""

    gate = importlib.import_module("kx_agent.security.gate")

    results = [
        _make_check_result(
            gate,
            SecurityGateCheck.CAPSULE_SIGNATURE,
            SecurityGateStatus.PASS,
        ),
        _make_check_result(
            gate,
            SecurityGateCheck.FIREWALL_ENABLED,
            SecurityGateStatus.WARN,
            "firewall status could not be fully confirmed",
        ),
    ]

    gate_result = _make_gate_result(gate, results)

    assert gate.is_security_gate_passing(gate_result) is True


@pytest.mark.parametrize(
    "port",
    [3000, 5000, 5432, 6379, 5555, 8000],
)
def test_dangerous_public_ports_are_rejected(port: int) -> None:
    """Dangerous public ports must be rejected by port policy checks."""

    ports = importlib.import_module("kx_agent.security.ports")

    assert hasattr(ports, "is_forbidden_public_port")
    assert ports.is_forbidden_public_port(port) is True


@pytest.mark.parametrize(
    "port",
    [80, 443],
)
def test_entry_ports_are_not_dangerous_public_ports(port: int) -> None:
    """Canonical entry ports may be exposed through Traefik."""

    ports = importlib.import_module("kx_agent.security.ports")

    assert hasattr(ports, "is_forbidden_public_port")
    assert ports.is_forbidden_public_port(port) is False


def test_security_policy_rejects_docker_socket_mount() -> None:
    """Security policy checks must reject Docker socket mounts."""

    policies = importlib.import_module("kx_agent.security.policies")

    assert hasattr(policies, "validate_runtime_policy")

    unsafe_policy = {
        "services": {
            "django-api": {
                "volumes": [
                    "/var/run/docker.sock:/var/run/docker.sock",
                ],
            },
        },
    }

    with pytest.raises(Exception):
        policies.validate_runtime_policy(unsafe_policy)


def test_security_policy_rejects_privileged_containers() -> None:
    """Security policy checks must reject privileged containers."""

    policies = importlib.import_module("kx_agent.security.policies")

    unsafe_policy = {
        "services": {
            "django-api": {
                "privileged": True,
            },
        },
    }

    with pytest.raises(Exception):
        policies.validate_runtime_policy(unsafe_policy)


def test_security_policy_rejects_host_network() -> None:
    """Security policy checks must reject host networking."""

    policies = importlib.import_module("kx_agent.security.policies")

    unsafe_policy = {
        "services": {
            "django-api": {
                "network_mode": "host",
            },
        },
    }

    with pytest.raises(Exception):
        policies.validate_runtime_policy(unsafe_policy)


def _make_check_result(
    gate_module: Any,
    check: SecurityGateCheck,
    status_: SecurityGateStatus,
    message: str = "",
) -> Any:
    """Build a SecurityCheckResult using the project class when available."""

    result_class = getattr(gate_module, "SecurityCheckResult", None)
    if result_class is None:
        return FakeSecurityCheckResult(check=check, status=status_, message=message)

    try:
        return result_class(check=check, status=status_, message=message)
    except TypeError:
        return result_class(check.value, status_.value, message)


def _make_gate_result(gate_module: Any, results: list[Any]) -> Any:
    """Build a SecurityGateResult using the project class when available."""

    gate_result_class = getattr(gate_module, "SecurityGateResult", None)
    if gate_result_class is None:
        return {"results": results}

    try:
        return gate_result_class(results=results)
    except TypeError:
        return gate_result_class(checks=results)
