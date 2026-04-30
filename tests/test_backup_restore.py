"""
Tests for Konnaxion backup/restore/rollback behavior.

This suite focuses on shared contracts and rollback orchestration because
rollback is the critical recovery path tying together backups, capsule pointers,
runtime stop/start, Security Gate, and healthchecks.

The tests use temporary filesystem roots and dry-run execution so they never
touch /opt/konnaxion, Docker, or the host firewall.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from kx_shared.konnaxion_constants import (
    CAPSULE_EXTENSION,
    RollbackStatus,
)
from kx_shared.types import (
    BackupID,
    CapsuleID,
    CapsuleVersion,
    InstanceID,
)

from kx_agent.backups import rollback as rb


@pytest.fixture()
def temp_kx_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Patch rollback filesystem helpers to use a temporary Konnaxion layout."""

    root = tmp_path / "opt" / "konnaxion"
    capsules_dir = root / "capsules"
    instances_dir = root / "instances"
    backups_dir = root / "backups"

    capsules_dir.mkdir(parents=True)
    instances_dir.mkdir(parents=True)
    backups_dir.mkdir(parents=True)

    def capsule_path(capsule_id: str) -> Path:
        return capsules_dir / f"{capsule_id}{CAPSULE_EXTENSION}"

    def instance_root(instance_id: str) -> Path:
        return instances_dir / instance_id

    def instance_state_dir(instance_id: str) -> Path:
        return instance_root(instance_id) / "state"

    def instance_compose_file(instance_id: str) -> Path:
        return instance_state_dir(instance_id) / "docker-compose.runtime.yml"

    monkeypatch.setattr(rb, "KX_ROOT", root)
    monkeypatch.setattr(rb, "KX_CAPSULES_DIR", capsules_dir)
    monkeypatch.setattr(rb, "KX_INSTANCES_DIR", instances_dir)
    monkeypatch.setattr(rb, "capsule_path", capsule_path)
    monkeypatch.setattr(rb, "instance_root", instance_root)
    monkeypatch.setattr(rb, "instance_state_dir", instance_state_dir)
    monkeypatch.setattr(rb, "instance_compose_file", instance_compose_file)

    return {
        "root": root,
        "capsules": capsules_dir,
        "instances": instances_dir,
        "backups": backups_dir,
    }


@pytest.fixture()
def instance_id() -> InstanceID:
    return InstanceID("demo-001")


@pytest.fixture()
def target_capsule_id() -> CapsuleID:
    return CapsuleID("konnaxion-v14-demo-2026.04.30")


@pytest.fixture()
def target_capsule_version() -> CapsuleVersion:
    return CapsuleVersion("2026.04.30-demo.1")


@pytest.fixture()
def target_capsule_file(
    temp_kx_layout: dict[str, Path],
    target_capsule_id: CapsuleID,
) -> Path:
    path = temp_kx_layout["capsules"] / f"{target_capsule_id}{CAPSULE_EXTENSION}"
    path.write_bytes(b"fake signed capsule for rollback tests")
    return path


@pytest.fixture()
def prepared_instance_state(
    temp_kx_layout: dict[str, Path],
    instance_id: InstanceID,
) -> Path:
    state_dir = temp_kx_layout["instances"] / str(instance_id) / "state"
    state_dir.mkdir(parents=True)

    compose_file = state_dir / "docker-compose.runtime.yml"
    compose_file.write_text(
        "services:\n"
        "  traefik:\n"
        "    image: traefik:test\n",
        encoding="utf-8",
    )

    return state_dir


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_new_rollback_id_is_instance_scoped(instance_id: InstanceID) -> None:
    rollback_id = rb.new_rollback_id(instance_id)

    assert str(rollback_id).startswith(f"{instance_id}_")
    assert "_rollback_" in str(rollback_id)


def test_create_rollback_plan_uses_canonical_status(
    instance_id: InstanceID,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
) -> None:
    plan = rb.create_rollback_plan(
        instance_id=instance_id,
        target_capsule_id=target_capsule_id,
        target_capsule_version=target_capsule_version,
    )

    assert plan.status == RollbackStatus.PLANNED
    assert plan.instance_id == instance_id
    assert plan.target_capsule_id == target_capsule_id
    assert plan.target_capsule_version == target_capsule_version
    assert plan.restore_data is False
    assert plan.backup_id is None


def test_create_rollback_plan_can_reference_backup_for_data_restore(
    instance_id: InstanceID,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
) -> None:
    plan = rb.create_rollback_plan(
        instance_id=instance_id,
        target_capsule_id=target_capsule_id,
        target_capsule_version=target_capsule_version,
        restore_data=True,
        backup_id=BackupID("demo-001_20260430_230000_manual"),
    )

    assert plan.status == RollbackStatus.PLANNED
    assert plan.restore_data is True
    assert plan.backup_id == BackupID("demo-001_20260430_230000_manual")


def test_build_rollback_context_resolves_canonical_paths(
    prepared_instance_state: Path,
    target_capsule_file: Path,
    instance_id: InstanceID,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
) -> None:
    context = rb.build_rollback_context(
        instance_id=instance_id,
        target_capsule_id=target_capsule_id,
        target_capsule_version=target_capsule_version,
    )

    assert context.instance_id == instance_id
    assert context.target_capsule_id == target_capsule_id
    assert context.target_capsule_version == target_capsule_version
    assert context.target_capsule_file == target_capsule_file
    assert context.current_pointer_file == prepared_instance_state / rb.CURRENT_CAPSULE_POINTER
    assert context.previous_pointer_file == prepared_instance_state / rb.PREVIOUS_CAPSULE_POINTER
    assert context.rollback_state_file == prepared_instance_state / rb.ROLLBACK_STATE_FILENAME
    assert context.rollback_history_file == prepared_instance_state / rb.ROLLBACK_HISTORY_FILENAME
    assert context.compose_file == prepared_instance_state / "docker-compose.runtime.yml"


def test_build_rollback_context_requires_backup_when_restoring_data(
    prepared_instance_state: Path,
    target_capsule_file: Path,
    instance_id: InstanceID,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
) -> None:
    with pytest.raises(rb.RollbackSafetyError, match="restore_data rollback requires backup_id"):
        rb.build_rollback_context(
            instance_id=instance_id,
            target_capsule_id=target_capsule_id,
            target_capsule_version=target_capsule_version,
            restore_data=True,
        )


def test_validate_capsule_file_rejects_wrong_extension(
    temp_kx_layout: dict[str, Path],
) -> None:
    wrong_file = temp_kx_layout["capsules"] / "bad-capsule.zip"
    wrong_file.write_bytes(b"not a capsule")

    with pytest.raises(rb.RollbackSafetyError, match="must end with .kxcap"):
        rb.validate_capsule_file(wrong_file)


def test_validate_capsule_file_rejects_path_escape(tmp_path: Path) -> None:
    outside_file = tmp_path / "outside.kxcap"
    outside_file.write_bytes(b"outside")

    with pytest.raises(rb.RollbackSafetyError, match="path must be under"):
        rb.validate_capsule_file(outside_file)


def test_capsule_pointer_round_trip(
    prepared_instance_state: Path,
    target_capsule_file: Path,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
) -> None:
    pointer = rb.CapsulePointer(
        capsule_id=target_capsule_id,
        capsule_version=target_capsule_version,
        capsule_file=target_capsule_file,
        updated_at=datetime(2026, 4, 30, 13, 0, tzinfo=UTC),
    )
    pointer_file = prepared_instance_state / rb.CURRENT_CAPSULE_POINTER

    rb.write_capsule_pointer(pointer_file, pointer)
    loaded = rb.read_capsule_pointer(pointer_file)

    assert loaded == pointer


def test_repoint_capsule_writes_current_and_previous_pointers(
    prepared_instance_state: Path,
    target_capsule_file: Path,
    instance_id: InstanceID,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
) -> None:
    old_capsule_file = target_capsule_file.parent / "konnaxion-v14-demo-2026.04.20.kxcap"
    old_capsule_file.write_bytes(b"old capsule")

    context = rb.build_rollback_context(
        instance_id=instance_id,
        target_capsule_id=target_capsule_id,
        target_capsule_version=target_capsule_version,
    )

    old_pointer = rb.CapsulePointer(
        capsule_id=CapsuleID("konnaxion-v14-demo-2026.04.20"),
        capsule_version=CapsuleVersion("2026.04.20-demo.1"),
        capsule_file=old_capsule_file,
        updated_at=datetime(2026, 4, 20, 13, 0, tzinfo=UTC),
    )
    rb.write_capsule_pointer(context.current_pointer_file, old_pointer)

    step = rb.repoint_capsule(context)

    current = rb.read_capsule_pointer(context.current_pointer_file)
    previous = rb.read_capsule_pointer(context.previous_pointer_file)

    assert step.status == RollbackStatus.CAPSULE_REPOINTED
    assert current is not None
    assert previous is not None
    assert current.capsule_id == target_capsule_id
    assert current.capsule_version == target_capsule_version
    assert current.capsule_file == target_capsule_file
    assert previous.capsule_id == old_pointer.capsule_id
    assert previous.capsule_version == old_pointer.capsule_version


def test_repoint_capsule_dry_run_does_not_write_pointer(
    prepared_instance_state: Path,
    target_capsule_file: Path,
    instance_id: InstanceID,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
) -> None:
    context = rb.build_rollback_context(
        instance_id=instance_id,
        target_capsule_id=target_capsule_id,
        target_capsule_version=target_capsule_version,
    )

    step = rb.repoint_capsule(context, dry_run=True)

    assert step.status == RollbackStatus.CAPSULE_REPOINTED
    assert not context.current_pointer_file.exists()
    assert not context.previous_pointer_file.exists()


def test_write_rollback_state_and_history(
    prepared_instance_state: Path,
    target_capsule_file: Path,
    instance_id: InstanceID,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
) -> None:
    context = rb.build_rollback_context(
        instance_id=instance_id,
        target_capsule_id=target_capsule_id,
        target_capsule_version=target_capsule_version,
    )

    rb.write_rollback_state(
        context,
        RollbackStatus.RUNNING,
        metadata={"phase": "test"},
    )

    state = read_json(context.rollback_state_file)
    history_lines = context.rollback_history_file.read_text(encoding="utf-8").splitlines()

    assert state["schema_version"] == rb.ROLLBACK_SCHEMA_VERSION
    assert state["rollback_id"] == str(context.rollback_id)
    assert state["instance_id"] == str(instance_id)
    assert state["status"] == RollbackStatus.RUNNING.value
    assert state["metadata"]["phase"] == "test"
    assert len(history_lines) == 1


def test_latest_rollback_state_and_history(
    prepared_instance_state: Path,
    target_capsule_file: Path,
    instance_id: InstanceID,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
) -> None:
    context = rb.build_rollback_context(
        instance_id=instance_id,
        target_capsule_id=target_capsule_id,
        target_capsule_version=target_capsule_version,
    )
    rb.write_rollback_state(context, RollbackStatus.RUNNING)
    rb.write_rollback_state(context, RollbackStatus.COMPLETED)

    latest = rb.latest_rollback_state(instance_id)
    history = rb.rollback_history(instance_id)

    assert latest is not None
    assert latest["status"] == RollbackStatus.COMPLETED.value
    assert [entry["status"] for entry in history] == [
        RollbackStatus.RUNNING.value,
        RollbackStatus.COMPLETED.value,
    ]


def test_clear_failed_rollback_state_only_clears_failed_state(
    prepared_instance_state: Path,
    target_capsule_file: Path,
    instance_id: InstanceID,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
) -> None:
    context = rb.build_rollback_context(
        instance_id=instance_id,
        target_capsule_id=target_capsule_id,
        target_capsule_version=target_capsule_version,
    )

    rb.write_rollback_state(context, RollbackStatus.RUNNING)

    with pytest.raises(rb.RollbackSafetyError, match="only failed rollback state can be cleared"):
        rb.clear_failed_rollback_state(instance_id)

    rb.write_rollback_state(context, RollbackStatus.FAILED, error="test failure")
    rb.clear_failed_rollback_state(instance_id)

    assert rb.latest_rollback_state(instance_id) is None


def test_stop_and_start_runtime_build_docker_compose_commands(
    prepared_instance_state: Path,
    target_capsule_file: Path,
    instance_id: InstanceID,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
) -> None:
    context = rb.build_rollback_context(
        instance_id=instance_id,
        target_capsule_id=target_capsule_id,
        target_capsule_version=target_capsule_version,
    )

    stop_commands = rb.build_stop_runtime_commands(context)
    start_commands = rb.build_start_runtime_commands(context)

    assert stop_commands
    assert start_commands
    assert stop_commands[0].argv == (
        "docker",
        "compose",
        "-f",
        str(context.compose_file),
        "down",
    )
    assert start_commands[0].argv == (
        "docker",
        "compose",
        "-f",
        str(context.compose_file),
        "up",
        "-d",
    )


def test_run_commands_dry_run_never_calls_docker(
    prepared_instance_state: Path,
    target_capsule_file: Path,
    instance_id: InstanceID,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
) -> None:
    context = rb.build_rollback_context(
        instance_id=instance_id,
        target_capsule_id=target_capsule_id,
        target_capsule_version=target_capsule_version,
    )

    results = rb.run_commands(rb.build_stop_runtime_commands(context), dry_run=True)

    assert len(results) == 1
    assert results[0].ok
    assert results[0].stdout == "dry-run"


def test_restore_data_requires_backup_when_enabled(
    prepared_instance_state: Path,
    target_capsule_file: Path,
    instance_id: InstanceID,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
) -> None:
    context = rb.build_rollback_context(
        instance_id=instance_id,
        target_capsule_id=target_capsule_id,
        target_capsule_version=target_capsule_version,
        restore_data=True,
        backup_id=BackupID("demo-001_20260430_230000_manual"),
    )

    calls: list[tuple[InstanceID, BackupID]] = []

    def restore_runner(instance: InstanceID, backup: BackupID) -> None:
        calls.append((instance, backup))

    step = rb.restore_data(context, restore_runner=restore_runner)

    assert step.status == RollbackStatus.DATA_RESTORED
    assert calls == [(instance_id, BackupID("demo-001_20260430_230000_manual"))]


def test_restore_data_skips_when_restore_data_false(
    prepared_instance_state: Path,
    target_capsule_file: Path,
    instance_id: InstanceID,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
) -> None:
    context = rb.build_rollback_context(
        instance_id=instance_id,
        target_capsule_id=target_capsule_id,
        target_capsule_version=target_capsule_version,
    )

    step = rb.restore_data(context)

    assert step.step == rb.RollbackStep.RESTORE_DATA
    assert step.status == RollbackStatus.CAPSULE_REPOINTED
    assert step.metadata["restore_data"] is False


def test_rollback_instance_dry_run_completes_without_repointing(
    prepared_instance_state: Path,
    target_capsule_file: Path,
    instance_id: InstanceID,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
    tmp_path: Path,
) -> None:
    context = rb.build_rollback_context(
        instance_id=instance_id,
        target_capsule_id=target_capsule_id,
        target_capsule_version=target_capsule_version,
    )

    audit_logger = rb.get_audit_logger(tmp_path / "audit.jsonl")

    hook_calls: list[str] = []

    def migration_runner(instance: InstanceID) -> None:
        hook_calls.append(f"migration:{instance}")

    def security_gate_runner(instance: InstanceID) -> dict[str, str]:
        hook_calls.append(f"security:{instance}")
        return {"status": "PASS"}

    def healthcheck_runner(instance: InstanceID) -> dict[str, str]:
        hook_calls.append(f"health:{instance}")
        return {"status": "healthy"}

    result = rb.rollback_instance(
        context=context,
        migration_runner=migration_runner,
        security_gate_runner=security_gate_runner,
        healthcheck_runner=healthcheck_runner,
        audit_logger=audit_logger,
        dry_run=True,
    )

    assert result.ok
    assert result.status == RollbackStatus.COMPLETED
    assert result.error is None
    assert context.rollback_state_file.exists()
    assert read_json(context.rollback_state_file)["status"] == RollbackStatus.COMPLETED.value

    # Dry-run skips hook execution and pointer writes.
    assert hook_calls == []
    assert not context.current_pointer_file.exists()
    assert not context.previous_pointer_file.exists()


def test_rollback_instance_executes_hooks_when_not_dry_run(
    prepared_instance_state: Path,
    target_capsule_file: Path,
    instance_id: InstanceID,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
    tmp_path: Path,
) -> None:
    context = rb.build_rollback_context(
        instance_id=instance_id,
        target_capsule_id=target_capsule_id,
        target_capsule_version=target_capsule_version,
    )

    audit_logger = rb.get_audit_logger(tmp_path / "audit.jsonl")
    hook_calls: list[str] = []

    def migration_runner(instance: InstanceID) -> None:
        hook_calls.append(f"migration:{instance}")

    def security_gate_runner(instance: InstanceID) -> dict[str, str]:
        hook_calls.append(f"security:{instance}")
        return {"status": "PASS"}

    def healthcheck_runner(instance: InstanceID) -> dict[str, str]:
        hook_calls.append(f"health:{instance}")
        return {"status": "healthy"}

    result = rb.rollback_instance(
        context=context,
        migration_runner=migration_runner,
        security_gate_runner=security_gate_runner,
        healthcheck_runner=healthcheck_runner,
        audit_logger=audit_logger,
        dry_run=False,
    )

    assert result.ok
    assert hook_calls == [
        f"migration:{instance_id}",
        f"security:{instance_id}",
        f"health:{instance_id}",
    ]
    assert rb.read_capsule_pointer(context.current_pointer_file) is not None


def test_rollback_instance_records_failed_status_on_exception(
    prepared_instance_state: Path,
    target_capsule_file: Path,
    instance_id: InstanceID,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
    tmp_path: Path,
) -> None:
    context = rb.build_rollback_context(
        instance_id=instance_id,
        target_capsule_id=target_capsule_id,
        target_capsule_version=target_capsule_version,
    )
    audit_logger = rb.get_audit_logger(tmp_path / "audit.jsonl")

    def failing_healthcheck(instance: InstanceID) -> None:
        raise RuntimeError("healthcheck failed")

    result = rb.rollback_instance(
        context=context,
        healthcheck_runner=failing_healthcheck,
        audit_logger=audit_logger,
    )

    assert not result.ok
    assert result.status == RollbackStatus.FAILED
    assert "healthcheck failed" in (result.error or "")

    state = read_json(context.rollback_state_file)
    assert state["status"] == RollbackStatus.FAILED.value
    assert "healthcheck failed" in state["error"]


def test_result_to_dict_is_json_serializable(
    prepared_instance_state: Path,
    target_capsule_file: Path,
    instance_id: InstanceID,
    target_capsule_id: CapsuleID,
    target_capsule_version: CapsuleVersion,
    tmp_path: Path,
) -> None:
    context = rb.build_rollback_context(
        instance_id=instance_id,
        target_capsule_id=target_capsule_id,
        target_capsule_version=target_capsule_version,
    )
    result = rb.rollback_instance(
        context=context,
        audit_logger=rb.get_audit_logger(tmp_path / "audit.jsonl"),
        dry_run=True,
    )

    payload = rb.result_to_dict(result)

    assert payload["rollback_id"] == str(result.rollback_id)
    assert payload["status"] == RollbackStatus.COMPLETED.value
    assert payload["target_capsule_id"] == str(target_capsule_id)
    assert payload["target_capsule_version"] == str(target_capsule_version)
    json.dumps(payload)


def test_backup_restore_status_contracts_are_resource_statuses() -> None:
    """Backup/restore/rollback statuses must remain distinct from instance states."""

    assert RollbackStatus.PLANNED.value == "planned"
    assert RollbackStatus.RUNNING.value == "running"
    assert RollbackStatus.CAPSULE_REPOINTED.value == "capsule_repointed"
    assert RollbackStatus.DATA_RESTORED.value == "data_restored"
    assert RollbackStatus.HEALTHCHECKING.value == "healthchecking"
    assert RollbackStatus.COMPLETED.value == "completed"
    assert RollbackStatus.FAILED.value == "failed"
