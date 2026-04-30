"""
Contract tests for Konnaxion Capsule Manager GUI target modes.

These tests enforce DOC-18 target mode behavior:

- target modes are canonical: local, intranet, temporary_public, droplet
- target mode determines canonical NetworkProfile and ExposureMode
- temporary public mode requires expiration and confirmation
- droplet mode requires host, user, existing SSH key, remote root, safe capsule dir,
  public_vps profile, public exposure, and explicit confirmation
- local/intranet modes must not drift into public or droplet behavior
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from kx_manager.services.targets import (
    TARGET_DEFAULT_EXPOSURE_MAP,
    TARGET_PROFILE_MAP,
    DropletTargetConfig,
    TargetConfig,
    TargetMode,
    validate_target_config,
)
from kx_shared.konnaxion_constants import ExposureMode, NetworkProfile


INSTANCE_ID = "demo-001"
LOCAL_RUNTIME_ROOT = r"C:\mycode\Konnaxion\runtime"
LOCAL_CAPSULE_DIR = r"C:\mycode\Konnaxion\runtime\capsules"
REMOTE_KX_ROOT = "/opt/konnaxion"
REMOTE_CAPSULE_DIR = "/opt/konnaxion/capsules"
PUBLIC_EXPIRES_AT = "2026-04-30T22:00:00Z"


def assert_valid(config: TargetConfig) -> None:
    """Assert a target config passes validation."""

    assert validate_target_config(config) is None


def assert_invalid(config: Any) -> None:
    """
    Assert a target config fails validation.

    The target service may raise ValueError directly or a project-specific
    validation exception, so this intentionally accepts any normal exception.
    """

    with pytest.raises(Exception):
        validate_target_config(config)


def make_target_config(
    *,
    target_mode: TargetMode = TargetMode.INTRANET,
    network_profile: NetworkProfile = NetworkProfile.INTRANET_PRIVATE,
    exposure_mode: ExposureMode = ExposureMode.PRIVATE,
    instance_id: str = INSTANCE_ID,
    runtime_root: str = LOCAL_RUNTIME_ROOT,
    capsule_dir: str = LOCAL_CAPSULE_DIR,
    host: str | None = None,
    public_mode_expires_at: str | None = None,
    confirmed: bool = False,
) -> TargetConfig:
    return TargetConfig(
        target_mode=target_mode,
        network_profile=network_profile,
        exposure_mode=exposure_mode,
        instance_id=instance_id,
        runtime_root=runtime_root,
        capsule_dir=capsule_dir,
        host=host,
        public_mode_expires_at=public_mode_expires_at,
        confirmed=confirmed,
    )


def make_droplet_config(
    tmp_path: Path,
    **overrides: Any,
) -> DropletTargetConfig:
    ssh_key_path = tmp_path / "id_ed25519"
    ssh_key_path.write_text("fake-test-key", encoding="utf-8")

    values: dict[str, Any] = {
        "target_mode": TargetMode.DROPLET,
        "network_profile": NetworkProfile.PUBLIC_VPS,
        "exposure_mode": ExposureMode.PUBLIC,
        "instance_id": INSTANCE_ID,
        "runtime_root": REMOTE_KX_ROOT,
        "capsule_dir": REMOTE_CAPSULE_DIR,
        "host": "203.0.113.10",
        "confirmed": True,
        "droplet_name": "konnaxion-demo-01",
        "droplet_host": "203.0.113.10",
        "droplet_user": "root",
        "ssh_key_path": ssh_key_path,
        "remote_kx_root": REMOTE_KX_ROOT,
        "remote_capsule_dir": REMOTE_CAPSULE_DIR,
        "domain": "app.example.com",
        "remote_agent_url": "http://203.0.113.10:8765/v1",
        "ssh_port": 22,
    }
    values.update(overrides)

    return DropletTargetConfig(**values)


def test_target_mode_enum_values() -> None:
    assert {mode.value for mode in TargetMode} == {
        "local",
        "intranet",
        "temporary_public",
        "droplet",
    }

    assert TargetMode("local") is TargetMode.LOCAL
    assert TargetMode("intranet") is TargetMode.INTRANET
    assert TargetMode("temporary_public") is TargetMode.TEMPORARY_PUBLIC
    assert TargetMode("droplet") is TargetMode.DROPLET


def test_local_target_maps_to_local_only_private() -> None:
    assert TARGET_PROFILE_MAP[TargetMode.LOCAL] == NetworkProfile.LOCAL_ONLY
    assert TARGET_DEFAULT_EXPOSURE_MAP[TargetMode.LOCAL] == ExposureMode.PRIVATE

    config = make_target_config(
        target_mode=TargetMode.LOCAL,
        network_profile=NetworkProfile.LOCAL_ONLY,
        exposure_mode=ExposureMode.PRIVATE,
    )

    assert_valid(config)


def test_intranet_target_maps_to_intranet_private_private() -> None:
    assert TARGET_PROFILE_MAP[TargetMode.INTRANET] == NetworkProfile.INTRANET_PRIVATE
    assert TARGET_DEFAULT_EXPOSURE_MAP[TargetMode.INTRANET] == ExposureMode.PRIVATE

    config = make_target_config(
        target_mode=TargetMode.INTRANET,
        network_profile=NetworkProfile.INTRANET_PRIVATE,
        exposure_mode=ExposureMode.PRIVATE,
        host="konnaxion.local",
    )

    assert_valid(config)


def test_intranet_target_allows_lan() -> None:
    config = make_target_config(
        target_mode=TargetMode.INTRANET,
        network_profile=NetworkProfile.INTRANET_PRIVATE,
        exposure_mode=ExposureMode.LAN,
        host="192.168.1.50",
    )

    assert_valid(config)


def test_temporary_public_maps_to_public_temporary_temporary_tunnel() -> None:
    assert TARGET_PROFILE_MAP[TargetMode.TEMPORARY_PUBLIC] == NetworkProfile.PUBLIC_TEMPORARY
    assert (
        TARGET_DEFAULT_EXPOSURE_MAP[TargetMode.TEMPORARY_PUBLIC]
        == ExposureMode.TEMPORARY_TUNNEL
    )

    config = make_target_config(
        target_mode=TargetMode.TEMPORARY_PUBLIC,
        network_profile=NetworkProfile.PUBLIC_TEMPORARY,
        exposure_mode=ExposureMode.TEMPORARY_TUNNEL,
        host="generated-demo.example",
        public_mode_expires_at=PUBLIC_EXPIRES_AT,
        confirmed=True,
    )

    assert_valid(config)


def test_temporary_public_requires_expiration() -> None:
    config = make_target_config(
        target_mode=TargetMode.TEMPORARY_PUBLIC,
        network_profile=NetworkProfile.PUBLIC_TEMPORARY,
        exposure_mode=ExposureMode.TEMPORARY_TUNNEL,
        host="generated-demo.example",
        public_mode_expires_at=None,
        confirmed=True,
    )

    assert_invalid(config)


def test_temporary_public_requires_confirmation() -> None:
    config = make_target_config(
        target_mode=TargetMode.TEMPORARY_PUBLIC,
        network_profile=NetworkProfile.PUBLIC_TEMPORARY,
        exposure_mode=ExposureMode.TEMPORARY_TUNNEL,
        host="generated-demo.example",
        public_mode_expires_at=PUBLIC_EXPIRES_AT,
        confirmed=False,
    )

    assert_invalid(config)


def test_droplet_maps_to_public_vps_public(tmp_path: Path) -> None:
    assert TARGET_PROFILE_MAP[TargetMode.DROPLET] == NetworkProfile.PUBLIC_VPS
    assert TARGET_DEFAULT_EXPOSURE_MAP[TargetMode.DROPLET] == ExposureMode.PUBLIC

    config = make_droplet_config(tmp_path)

    assert_valid(config)


def test_droplet_requires_host(tmp_path: Path) -> None:
    config = make_droplet_config(
        tmp_path,
        host=None,
        droplet_host="",
    )

    assert_invalid(config)


def test_droplet_requires_user(tmp_path: Path) -> None:
    config = make_droplet_config(
        tmp_path,
        droplet_user="",
    )

    assert_invalid(config)


def test_droplet_requires_ssh_key(tmp_path: Path) -> None:
    missing_key = tmp_path / "missing_id_ed25519"

    config = make_droplet_config(
        tmp_path,
        ssh_key_path=missing_key,
    )

    assert_invalid(config)


def test_droplet_requires_remote_root(tmp_path: Path) -> None:
    config = make_droplet_config(
        tmp_path,
        remote_kx_root="",
    )

    assert_invalid(config)


def test_droplet_remote_capsule_dir_must_be_under_remote_root(tmp_path: Path) -> None:
    config = make_droplet_config(
        tmp_path,
        remote_kx_root=REMOTE_KX_ROOT,
        remote_capsule_dir="/tmp/konnaxion-capsules",
    )

    assert_invalid(config)


def test_local_target_rejects_droplet_fields(tmp_path: Path) -> None:
    ssh_key_path = tmp_path / "id_ed25519"
    ssh_key_path.write_text("fake-test-key", encoding="utf-8")

    config = DropletTargetConfig(
        target_mode=TargetMode.LOCAL,
        network_profile=NetworkProfile.LOCAL_ONLY,
        exposure_mode=ExposureMode.PRIVATE,
        instance_id=INSTANCE_ID,
        runtime_root=LOCAL_RUNTIME_ROOT,
        capsule_dir=LOCAL_CAPSULE_DIR,
        host=None,
        confirmed=False,
        droplet_name="should-not-exist",
        droplet_host="203.0.113.10",
        droplet_user="root",
        ssh_key_path=ssh_key_path,
        remote_kx_root=REMOTE_KX_ROOT,
        remote_capsule_dir=REMOTE_CAPSULE_DIR,
        domain="app.example.com",
        remote_agent_url="http://203.0.113.10:8765/v1",
        ssh_port=22,
    )

    assert_invalid(config)


def test_intranet_target_rejects_public_exposure() -> None:
    config = make_target_config(
        target_mode=TargetMode.INTRANET,
        network_profile=NetworkProfile.INTRANET_PRIVATE,
        exposure_mode=ExposureMode.PUBLIC,
        host="konnaxion.local",
        confirmed=True,
    )

    assert_invalid(config)


def test_invalid_target_mode_rejected() -> None:
    with pytest.raises(ValueError):
        TargetMode("dev")

    config = make_target_config()
    invalid_config = TargetConfig(
        target_mode="dev",  # type: ignore[arg-type]
        network_profile=config.network_profile,
        exposure_mode=config.exposure_mode,
        instance_id=config.instance_id,
        runtime_root=config.runtime_root,
        capsule_dir=config.capsule_dir,
        host=config.host,
        public_mode_expires_at=config.public_mode_expires_at,
        confirmed=config.confirmed,
    )

    assert_invalid(invalid_config)