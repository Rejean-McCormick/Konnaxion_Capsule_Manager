"""
Contract tests for Konnaxion Capsule Manager GUI target modes.

These tests enforce DOC-18 target mode behavior:

- target modes are canonical: local, intranet, temporary_public, droplet
- target mode determines canonical NetworkProfile and ExposureMode
- temporary public mode requires expiration and confirmation
- droplet mode requires host, user, existing SSH key, remote root, safe capsule dir,
  domain, public_vps profile, public exposure, and explicit confirmation
- droplet mode keeps the Agent private by default; remote_agent_url is optional
  and blank means SSH-local transport to the private Droplet Agent
- droplet public host/domain must not drift to localhost/loopback values
- droplet public host/domain must not drift to the raw Droplet IP when a domain is set
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
    build_target_config,
    target_env,
    validate_target_config,
)
from kx_shared.konnaxion_constants import ExposureMode, NetworkProfile


INSTANCE_ID = "demo-001"
LOCAL_RUNTIME_ROOT = r"C:\mycode\Konnaxion\runtime"
LOCAL_CAPSULE_DIR = r"C:\mycode\Konnaxion\runtime\capsules"
REMOTE_KX_ROOT = "/opt/konnaxion"
REMOTE_CAPSULE_DIR = "/opt/konnaxion/capsules"
PUBLIC_EXPIRES_AT = "2026-04-30T22:00:00Z"

DROPLET_HOST = "203.0.113.10"
DROPLET_DOMAIN = "app.example.com"
DROPLET_DOMAIN_ALIAS = "demo.example.net"
PUBLIC_HOST_ALIAS = "public.example.org"
DIRECT_REMOTE_AGENT_URL = "https://agent.example.com/v1"

LOOPBACK_HOSTS: tuple[str, ...] = (
    "127.0.0.1",
    "localhost",
    "0.0.0.0",
    "::1",
)

LOOPBACK_REMOTE_AGENT_URLS: tuple[str, ...] = (
    "http://127.0.0.1:18765/v1",
    "http://127.0.0.1:8765/v1",
    "http://localhost:18765/v1",
    "http://localhost:8765/v1",
    "http://0.0.0.0:8765/v1",
    "http://[::1]:8765/v1",
)


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


def assert_not_loopback(value: str | None) -> None:
    assert value not in {None, ""}
    assert value not in LOOPBACK_HOSTS
    assert not str(value).startswith("http://127.0.0.1")
    assert not str(value).startswith("https://127.0.0.1")
    assert not str(value).startswith("http://localhost")
    assert not str(value).startswith("https://localhost")


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
        # In Droplet/public mode, `host` is the public runtime host used by
        # frontend/env/Traefik/Django. The raw Droplet IP stays in `droplet_host`.
        "host": DROPLET_DOMAIN,
        "confirmed": True,
        "droplet_name": "konnaxion-demo-01",
        "droplet_host": DROPLET_HOST,
        "droplet_user": "root",
        "ssh_key_path": ssh_key_path,
        "remote_kx_root": REMOTE_KX_ROOT,
        "remote_capsule_dir": REMOTE_CAPSULE_DIR,
        "domain": DROPLET_DOMAIN,
        # Canonical Droplet mode keeps the Agent private on the VPS:
        # Manager -> SSH -> curl http://127.0.0.1:8765/v1/... on the Droplet.
        # A blank remote_agent_url means SSH-local transport.
        "remote_agent_url": "",
        "ssh_port": 22,
    }
    values.update(overrides)

    return DropletTargetConfig(**values)


def make_built_droplet_config(
    tmp_path: Path,
    *,
    host: str | None = DROPLET_HOST,
    domain: str | None = DROPLET_DOMAIN,
    droplet_domain: str | None = None,
    public_host: str | None = None,
    droplet_host: str | None = DROPLET_HOST,
    remote_agent_url: str | None = "",
    confirmed: bool = True,
) -> TargetConfig:
    ssh_key_path = tmp_path / "id_ed25519"
    ssh_key_path.write_text("fake-test-key", encoding="utf-8")

    extra: dict[str, Any] = {
        "droplet_name": "konnaxion-demo-01",
        "droplet_host": droplet_host,
        "droplet_user": "root",
        "ssh_key_path": ssh_key_path,
        "ssh_port": 22,
        "remote_kx_root": REMOTE_KX_ROOT,
        "remote_capsule_dir": REMOTE_CAPSULE_DIR,
        "remote_agent_url": remote_agent_url,
    }

    if domain is not None:
        extra["domain"] = domain
    if droplet_domain is not None:
        extra["droplet_domain"] = droplet_domain
    if public_host is not None:
        extra["public_host"] = public_host

    return build_target_config(
        target_mode=TargetMode.DROPLET,
        network_profile=NetworkProfile.PUBLIC_VPS,
        exposure_mode=ExposureMode.PUBLIC,
        instance_id=INSTANCE_ID,
        runtime_root=REMOTE_KX_ROOT,
        capsule_dir=REMOTE_CAPSULE_DIR,
        host=host,
        confirmed=confirmed,
        extra=extra,
    )


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


def test_droplet_allows_blank_remote_agent_url_for_ssh_local_transport(
    tmp_path: Path,
) -> None:
    config = make_droplet_config(
        tmp_path,
        remote_agent_url="",
    )

    assert_valid(config)
    assert config.remote_agent_url in {"", None}


def test_droplet_allows_explicit_non_loopback_remote_agent_url(
    tmp_path: Path,
) -> None:
    config = make_droplet_config(
        tmp_path,
        remote_agent_url=DIRECT_REMOTE_AGENT_URL,
    )

    assert_valid(config)
    assert config.remote_agent_url == DIRECT_REMOTE_AGENT_URL


@pytest.mark.parametrize("remote_agent_url", LOOPBACK_REMOTE_AGENT_URLS)
def test_droplet_rejects_loopback_remote_agent_url(
    tmp_path: Path,
    remote_agent_url: str,
) -> None:
    config = make_droplet_config(
        tmp_path,
        remote_agent_url=remote_agent_url,
    )

    assert_invalid(config)


def test_droplet_direct_config_uses_domain_as_public_runtime_host(
    tmp_path: Path,
) -> None:
    config = make_droplet_config(tmp_path)

    assert_valid(config)

    assert config.host == DROPLET_DOMAIN
    assert config.droplet_host == DROPLET_HOST
    assert config.domain == DROPLET_DOMAIN

    env = target_env(config)

    assert env["KX_TARGET_MODE"] == "droplet"
    assert env["KX_TARGET_PROFILE"] == "public_vps"
    assert env["KX_TARGET_EXPOSURE"] == "public"
    assert env["KX_TARGET_HOST"] == DROPLET_DOMAIN
    assert env["KX_DROPLET_DROPLET_HOST"] == DROPLET_HOST
    assert env["KX_DROPLET_DOMAIN"] == DROPLET_DOMAIN

    assert env["KX_TARGET_HOST"] != "127.0.0.1"
    assert env["KX_TARGET_HOST"] != "localhost"
    assert env["KX_TARGET_HOST"] != DROPLET_HOST


def test_build_target_config_uses_domain_as_canonical_public_host(
    tmp_path: Path,
) -> None:
    config = make_built_droplet_config(
        tmp_path,
        host=DROPLET_HOST,
        domain=DROPLET_DOMAIN,
        droplet_host=DROPLET_HOST,
    )

    assert_valid(config)
    assert isinstance(config, DropletTargetConfig)

    assert config.host == DROPLET_DOMAIN
    assert config.droplet_host == DROPLET_HOST
    assert config.domain == DROPLET_DOMAIN

    env = target_env(config)
    assert env["KX_TARGET_HOST"] == DROPLET_DOMAIN
    assert env["KX_DROPLET_DROPLET_HOST"] == DROPLET_HOST
    assert env["KX_DROPLET_DOMAIN"] == DROPLET_DOMAIN


def test_build_target_config_uses_droplet_domain_alias_as_public_host(
    tmp_path: Path,
) -> None:
    config = make_built_droplet_config(
        tmp_path,
        host=DROPLET_HOST,
        domain=None,
        droplet_domain=DROPLET_DOMAIN_ALIAS,
        droplet_host=DROPLET_HOST,
    )

    assert_valid(config)
    assert isinstance(config, DropletTargetConfig)

    assert config.host == DROPLET_DOMAIN_ALIAS
    assert config.domain == DROPLET_DOMAIN_ALIAS
    assert config.droplet_host == DROPLET_HOST

    env = target_env(config)
    assert env["KX_TARGET_HOST"] == DROPLET_DOMAIN_ALIAS
    assert env["KX_DROPLET_DOMAIN"] == DROPLET_DOMAIN_ALIAS


def test_build_target_config_uses_public_host_before_raw_host_or_droplet_host(
    tmp_path: Path,
) -> None:
    config = make_built_droplet_config(
        tmp_path,
        host=DROPLET_HOST,
        domain=None,
        droplet_domain=None,
        public_host=PUBLIC_HOST_ALIAS,
        droplet_host=DROPLET_HOST,
    )

    assert_valid(config)
    assert isinstance(config, DropletTargetConfig)

    assert config.host == PUBLIC_HOST_ALIAS
    assert config.domain == PUBLIC_HOST_ALIAS
    assert config.droplet_host == DROPLET_HOST

    env = target_env(config)
    assert env["KX_TARGET_HOST"] == PUBLIC_HOST_ALIAS
    assert env["KX_TARGET_HOST"] != DROPLET_HOST


def test_build_target_config_may_fall_back_to_host_when_no_public_alias_exists(
    tmp_path: Path,
) -> None:
    host = "demo-direct.example.com"

    config = make_built_droplet_config(
        tmp_path,
        host=host,
        domain=None,
        droplet_domain=None,
        public_host=None,
        droplet_host=DROPLET_HOST,
    )

    assert_valid(config)
    assert isinstance(config, DropletTargetConfig)

    assert config.host == host
    assert config.domain == host
    assert config.droplet_host == DROPLET_HOST

    env = target_env(config)
    assert env["KX_TARGET_HOST"] == host
    assert env["KX_DROPLET_DOMAIN"] == host


def test_target_env_for_public_vps_never_uses_loopback_when_domain_is_public(
    tmp_path: Path,
) -> None:
    config = make_built_droplet_config(
        tmp_path,
        host="127.0.0.1",
        domain=DROPLET_DOMAIN,
        droplet_host=DROPLET_HOST,
    )

    assert_valid(config)

    env = target_env(config)
    assert env["KX_TARGET_HOST"] == DROPLET_DOMAIN
    assert_not_loopback(env["KX_TARGET_HOST"])


@pytest.mark.parametrize(
    "domain",
    [
        "127.0.0.1",
        "localhost",
        "0.0.0.0",
        "::1",
        "http://127.0.0.1",
        "https://localhost",
    ],
)
def test_droplet_rejects_loopback_domain(tmp_path: Path, domain: str) -> None:
    config = make_droplet_config(
        tmp_path,
        host=domain,
        domain=domain,
    )

    assert_invalid(config)


@pytest.mark.parametrize(
    "public_host",
    [
        "127.0.0.1",
        "localhost",
        "0.0.0.0",
        "::1",
        "http://127.0.0.1",
        "https://localhost",
    ],
)
def test_build_target_config_rejects_loopback_public_host(
    tmp_path: Path,
    public_host: str,
) -> None:
    with pytest.raises(Exception):
        make_built_droplet_config(
            tmp_path,
            host=DROPLET_HOST,
            domain=None,
            public_host=public_host,
            droplet_host=DROPLET_HOST,
        )


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


def test_droplet_requires_domain(tmp_path: Path) -> None:
    config = make_droplet_config(
        tmp_path,
        host=DROPLET_HOST,
        domain="",
    )

    assert_invalid(config)


def test_droplet_requires_confirmation(tmp_path: Path) -> None:
    config = make_droplet_config(
        tmp_path,
        confirmed=False,
    )

    assert_invalid(config)


def test_droplet_rejects_private_profile(tmp_path: Path) -> None:
    config = make_droplet_config(
        tmp_path,
        network_profile=NetworkProfile.INTRANET_PRIVATE,
    )

    assert_invalid(config)


def test_droplet_rejects_private_exposure(tmp_path: Path) -> None:
    config = make_droplet_config(
        tmp_path,
        exposure_mode=ExposureMode.PRIVATE,
    )

    assert_invalid(config)


def test_droplet_rejects_temporary_tunnel_exposure(tmp_path: Path) -> None:
    config = make_droplet_config(
        tmp_path,
        exposure_mode=ExposureMode.TEMPORARY_TUNNEL,
        public_mode_expires_at=PUBLIC_EXPIRES_AT,
    )

    assert_invalid(config)


def test_droplet_remote_capsule_dir_must_be_under_remote_root(tmp_path: Path) -> None:
    config = make_droplet_config(
        tmp_path,
        remote_kx_root=REMOTE_KX_ROOT,
        remote_capsule_dir="/tmp/konnaxion-capsules",
    )

    assert_invalid(config)


def test_droplet_rejects_relative_remote_root(tmp_path: Path) -> None:
    config = make_droplet_config(
        tmp_path,
        remote_kx_root="opt/konnaxion",
        remote_capsule_dir="opt/konnaxion/capsules",
    )

    assert_invalid(config)


def test_droplet_rejects_bad_ssh_port_low(tmp_path: Path) -> None:
    config = make_droplet_config(
        tmp_path,
        ssh_port=0,
    )

    assert_invalid(config)


def test_droplet_rejects_bad_ssh_port_high(tmp_path: Path) -> None:
    config = make_droplet_config(
        tmp_path,
        ssh_port=65536,
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
        droplet_host=DROPLET_HOST,
        droplet_user="root",
        ssh_key_path=ssh_key_path,
        remote_kx_root=REMOTE_KX_ROOT,
        remote_capsule_dir=REMOTE_CAPSULE_DIR,
        domain=DROPLET_DOMAIN,
        remote_agent_url="",
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


def test_intranet_target_rejects_droplet_profile() -> None:
    config = make_target_config(
        target_mode=TargetMode.INTRANET,
        network_profile=NetworkProfile.PUBLIC_VPS,
        exposure_mode=ExposureMode.PUBLIC,
        host="konnaxion.local",
        confirmed=True,
    )

    assert_invalid(config)


def test_local_target_rejects_public_exposure() -> None:
    config = make_target_config(
        target_mode=TargetMode.LOCAL,
        network_profile=NetworkProfile.LOCAL_ONLY,
        exposure_mode=ExposureMode.PUBLIC,
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