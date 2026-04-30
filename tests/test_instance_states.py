"""
Tests for canonical Konnaxion instance and resource states.

These tests prevent drift between:
- kx_shared.konnaxion_constants
- kx_agent.instances.model
- Manager/UI/API expectations

They intentionally check exact canonical values.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kx_shared.konnaxion_constants import (
    BackupStatus,
    InstanceState,
    RestoreStatus,
    RollbackStatus,
    SecurityGateCheck,
    SecurityGateStatus,
)

from kx_agent.instances.model import (
    HealthSummary,
    InstanceModel,
    SecurityGateCheckResult,
    SecurityGateSummary,
    ServiceStatus,
    create_default_instance,
)


EXPECTED_INSTANCE_STATES = (
    "created",
    "importing",
    "verifying",
    "ready",
    "starting",
    "running",
    "stopping",
    "stopped",
    "updating",
    "rolling_back",
    "degraded",
    "failed",
    "security_blocked",
)

EXPECTED_BACKUP_STATUSES = (
    "created",
    "running",
    "verifying",
    "verified",
    "failed",
    "expired",
    "deleted",
    "quarantined",
)

EXPECTED_RESTORE_STATUSES = (
    "planned",
    "preflight",
    "creating_pre_restore_backup",
    "restoring_database",
    "restoring_media",
    "running_migrations",
    "running_security_gate",
    "running_healthchecks",
    "restored",
    "degraded",
    "failed",
    "rolled_back",
)

EXPECTED_ROLLBACK_STATUSES = (
    "planned",
    "running",
    "capsule_repointed",
    "data_restored",
    "healthchecking",
    "completed",
    "failed",
)

EXPECTED_SECURITY_GATE_STATUSES = (
    "PASS",
    "WARN",
    "FAIL_BLOCKING",
    "SKIPPED",
    "UNKNOWN",
)


def test_instance_state_values_are_canonical() -> None:
    assert tuple(state.value for state in InstanceState) == EXPECTED_INSTANCE_STATES


def test_backup_status_values_are_canonical() -> None:
    assert tuple(status.value for status in BackupStatus) == EXPECTED_BACKUP_STATUSES


def test_restore_status_values_are_canonical() -> None:
    assert tuple(status.value for status in RestoreStatus) == EXPECTED_RESTORE_STATUSES


def test_rollback_status_values_are_canonical() -> None:
    assert tuple(status.value for status in RollbackStatus) == EXPECTED_ROLLBACK_STATUSES


def test_security_gate_status_values_are_canonical() -> None:
    assert tuple(status.value for status in SecurityGateStatus) == EXPECTED_SECURITY_GATE_STATUSES


def test_default_instance_starts_in_created_state() -> None:
    instance = create_default_instance("demo-001")

    assert instance.instance_id == "demo-001"
    assert instance.state == InstanceState.CREATED
    assert instance.can_start is True
    assert instance.is_running is False
    assert instance.is_terminal_failure is False


@pytest.mark.parametrize(
    ("initial_state", "expected_can_start"),
    (
        (InstanceState.CREATED, True),
        (InstanceState.READY, True),
        (InstanceState.STOPPED, True),
        (InstanceState.DEGRADED, True),
        (InstanceState.IMPORTING, False),
        (InstanceState.VERIFYING, False),
        (InstanceState.STARTING, False),
        (InstanceState.RUNNING, False),
        (InstanceState.STOPPING, False),
        (InstanceState.UPDATING, False),
        (InstanceState.ROLLING_BACK, False),
        (InstanceState.FAILED, False),
        (InstanceState.SECURITY_BLOCKED, False),
    ),
)
def test_can_start_is_allowed_only_for_safe_states(
    initial_state: InstanceState,
    expected_can_start: bool,
) -> None:
    instance = InstanceModel(instance_id="demo-001", state=initial_state)

    assert instance.can_start is expected_can_start


def test_transition_to_running_sets_started_at() -> None:
    instance = InstanceModel(instance_id="demo-001", state=InstanceState.READY)

    running = instance.transition(InstanceState.RUNNING)

    assert running.state == InstanceState.RUNNING
    assert running.is_running is True
    assert running.started_at is not None
    assert running.stopped_at is None
    assert running.updated_at >= instance.updated_at


def test_transition_to_stopped_sets_stopped_at() -> None:
    running = InstanceModel(instance_id="demo-001", state=InstanceState.RUNNING).transition(
        InstanceState.RUNNING
    )

    stopped = running.transition(InstanceState.STOPPED)

    assert stopped.state == InstanceState.STOPPED
    assert stopped.is_running is False
    assert stopped.stopped_at is not None
    assert stopped.updated_at >= running.updated_at


def test_transition_accepts_canonical_state_strings() -> None:
    instance = InstanceModel(instance_id="demo-001", state="created")

    ready = instance.transition("ready")

    assert ready.state == InstanceState.READY


def test_unknown_instance_state_is_rejected() -> None:
    with pytest.raises(ValueError):
        InstanceModel(instance_id="demo-001", state="booting")


def test_security_gate_blocking_failure_sets_security_blocked_state() -> None:
    instance = InstanceModel(instance_id="demo-001", state=InstanceState.READY)

    gate = SecurityGateSummary(
        status=SecurityGateStatus.UNKNOWN,
        checks=(
            SecurityGateCheckResult(
                check=SecurityGateCheck.CAPSULE_SIGNATURE,
                status=SecurityGateStatus.FAIL_BLOCKING,
                message="Capsule signature invalid.",
                blocking=True,
                checked_at=datetime.now(UTC),
            ),
        ),
        checked_at=datetime.now(UTC),
    )

    updated = instance.with_security_gate(gate)

    assert updated.state == InstanceState.SECURITY_BLOCKED
    assert updated.security_gate.status == SecurityGateStatus.FAIL_BLOCKING
    assert len(updated.security_gate.blocking_failures) == 1
    assert updated.can_start is False
    assert updated.is_terminal_failure is True


def test_security_gate_pass_does_not_block_ready_instance() -> None:
    instance = InstanceModel(instance_id="demo-001", state=InstanceState.READY)

    gate = SecurityGateSummary(
        status=SecurityGateStatus.UNKNOWN,
        checks=(
            SecurityGateCheckResult(
                check=SecurityGateCheck.CAPSULE_SIGNATURE,
                status=SecurityGateStatus.PASS,
                message="Capsule signature valid.",
                blocking=True,
                checked_at=datetime.now(UTC),
            ),
            SecurityGateCheckResult(
                check=SecurityGateCheck.IMAGE_CHECKSUMS,
                status=SecurityGateStatus.PASS,
                message="Image checksums valid.",
                blocking=True,
                checked_at=datetime.now(UTC),
            ),
        ),
        checked_at=datetime.now(UTC),
    )

    updated = instance.with_security_gate(gate)

    assert updated.state == InstanceState.READY
    assert updated.security_gate.status == SecurityGateStatus.PASS
    assert updated.security_gate.passed is True
    assert updated.can_start is True


def test_running_instance_with_unhealthy_health_becomes_degraded() -> None:
    instance = InstanceModel(instance_id="demo-001", state=InstanceState.RUNNING)

    health = HealthSummary(
        healthy=False,
        ready=False,
        services=(
            ServiceStatus(
                service="django-api",
                desired=True,
                running=True,
                healthy=False,
                message="Healthcheck failed.",
                checked_at=datetime.now(UTC),
            ),
        ),
        message="One service is unhealthy.",
        checked_at=datetime.now(UTC),
    )

    updated = instance.with_health(health)

    assert updated.state == InstanceState.DEGRADED
    assert updated.health.healthy is False
    assert updated.can_start is True


def test_running_instance_with_healthy_health_remains_running() -> None:
    instance = InstanceModel(instance_id="demo-001", state=InstanceState.RUNNING)

    health = HealthSummary(
        healthy=True,
        ready=True,
        services=(
            ServiceStatus(
                service="django-api",
                desired=True,
                running=True,
                healthy=True,
                checked_at=datetime.now(UTC),
            ),
        ),
        checked_at=datetime.now(UTC),
    )

    updated = instance.with_health(health)

    assert updated.state == InstanceState.RUNNING
    assert updated.health.healthy is True
    assert updated.health.ready is True


def test_last_backup_id_updates_without_changing_state() -> None:
    instance = InstanceModel(instance_id="demo-001", state=InstanceState.RUNNING)

    updated = instance.with_last_backup("demo-001_20260430_230000_manual")

    assert updated.state == InstanceState.RUNNING
    assert updated.last_backup_id == "demo-001_20260430_230000_manual"


def test_instance_model_round_trip_serialization_preserves_state_values() -> None:
    instance = (
        InstanceModel(instance_id="demo-001", state=InstanceState.READY)
        .transition(InstanceState.RUNNING)
        .with_last_backup("demo-001_20260430_230000_manual")
    )

    payload = instance.to_dict()
    restored = InstanceModel.from_dict(payload)

    assert payload["state"] == "running"
    assert restored.instance_id == instance.instance_id
    assert restored.state == InstanceState.RUNNING
    assert restored.last_backup_id == "demo-001_20260430_230000_manual"
    assert restored.paths.compose_file.name == "docker-compose.runtime.yml"


def test_serialized_instance_paths_are_canonical() -> None:
    instance = InstanceModel(instance_id="demo-001")

    paths = instance.to_dict()["paths"]

    assert paths["root"] == "/opt/konnaxion/instances/demo-001"
    assert paths["env"] == "/opt/konnaxion/instances/demo-001/env"
    assert paths["postgres"] == "/opt/konnaxion/instances/demo-001/postgres"
    assert paths["redis"] == "/opt/konnaxion/instances/demo-001/redis"
    assert paths["media"] == "/opt/konnaxion/instances/demo-001/media"
    assert paths["logs"] == "/opt/konnaxion/instances/demo-001/logs"
    assert paths["local_backups"] == "/opt/konnaxion/instances/demo-001/backups"
    assert paths["state"] == "/opt/konnaxion/instances/demo-001/state"
    assert paths["compose_file"] == (
        "/opt/konnaxion/instances/demo-001/state/docker-compose.runtime.yml"
    )
    assert paths["backup_root"] == "/opt/konnaxion/backups/demo-001"


@pytest.mark.parametrize(
    "invalid_state",
    (
        "booting",
        "paused",
        "installed",
        "rollback",
        "security_failed",
        "blocked",
    ),
)
def test_non_canonical_instance_states_are_rejected(invalid_state: str) -> None:
    with pytest.raises(ValueError):
        InstanceModel(instance_id="demo-001", state=invalid_state)
