"""
Tests for canonical Konnaxion network profiles.

These tests enforce DOC-00 alignment:
- only canonical network profile names exist
- intranet_private/private is the default
- public exposure is never default
- dangerous internal ports are never publicly exposed
- offline profile has no external exposure
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = PROJECT_ROOT / "profiles"

CANONICAL_PROFILE_FILES = {
    "local_only": "local_only.yaml",
    "intranet_private": "intranet_private.yaml",
    "private_tunnel": "private_tunnel.yaml",
    "public_temporary": "public_temporary.yaml",
    "public_vps": "public_vps.yaml",
    "offline": "offline.yaml",
}

FORBIDDEN_PUBLIC_PORTS = {3000, 5000, 5432, 6379, 5555, 8000}

ALLOWED_PROFILE_EXPOSURE = {
    "local_only": {"private"},
    "intranet_private": {"private", "lan"},
    "private_tunnel": {"private", "vpn"},
    "public_temporary": {"temporary_tunnel"},
    "public_vps": {"public"},
    "offline": {"private"},
}


def load_yaml(path: Path) -> dict[str, Any]:
    yaml = pytest.importorskip("yaml")
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    assert isinstance(payload, dict), f"{path} must contain a YAML object"
    return payload


def profile_path(profile_name: str) -> Path:
    return PROFILES_DIR / CANONICAL_PROFILE_FILES[profile_name]


def profile_name(payload: Mapping[str, Any]) -> str:
    return str(payload.get("profile", {}).get("name", ""))


def exposure_mode(payload: Mapping[str, Any]) -> str:
    return str(payload.get("exposure", {}).get("mode", ""))


def canonical_env(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    env = payload.get("canonical_env", {})
    assert isinstance(env, Mapping), "canonical_env must be a mapping"
    return env


def collect_publish_ports(payload: Mapping[str, Any]) -> set[int]:
    """Collect explicitly published ports from a profile.

    Supports both the canonical profile structure and likely future compact
    forms such as:
      ports.publish.http_80: true
      compose_overrides.services.<service>.publish_ports: [80]
    """

    published: set[int] = set()

    ports = payload.get("ports", {})
    if isinstance(ports, Mapping):
        publish = ports.get("publish", {})
        if isinstance(publish, Mapping):
            for key, enabled in publish.items():
                if not enabled:
                    continue

                # Examples: http_80, https_443, ssh_22
                parts = str(key).split("_")
                for part in parts:
                    if part.isdigit():
                        published.add(int(part))

        explicit = ports.get("publish_ports", [])
        if isinstance(explicit, list):
            published.update(int(port) for port in explicit)

    compose_overrides = payload.get("compose_overrides", {})
    if isinstance(compose_overrides, Mapping):
        services = compose_overrides.get("services", {})
        if isinstance(services, Mapping):
            for service_config in services.values():
                if not isinstance(service_config, Mapping):
                    continue

                publish_ports = service_config.get("publish_ports", [])
                if isinstance(publish_ports, list):
                    for item in publish_ports:
                        if isinstance(item, int):
                            published.add(item)
                        elif isinstance(item, str) and item.isdigit():
                            published.add(int(item))
                        elif isinstance(item, str) and ":" in item:
                            # Docker-style host:container; public host port is
                            # the first numeric section.
                            first = item.split(":", 1)[0]
                            if first.isdigit():
                                published.add(int(first))

        traefik = compose_overrides.get("traefik", {})
        if isinstance(traefik, Mapping):
            publish_ports = traefik.get("publish_ports", [])
            if isinstance(publish_ports, list):
                for item in publish_ports:
                    if isinstance(item, int):
                        published.add(item)
                    elif isinstance(item, str) and item.isdigit():
                        published.add(int(item))

    return published


def test_all_canonical_profile_files_exist() -> None:
    missing = [
        str(path.relative_to(PROJECT_ROOT))
        for path in map(profile_path, CANONICAL_PROFILE_FILES)
        if not path.exists()
    ]

    assert missing == []


def test_no_extra_profile_files_exist() -> None:
    actual = {path.name for path in PROFILES_DIR.glob("*.yaml")}
    expected = set(CANONICAL_PROFILE_FILES.values())

    assert actual == expected


@pytest.mark.parametrize("expected_name,filename", sorted(CANONICAL_PROFILE_FILES.items()))
def test_profile_file_name_matches_profile_name(expected_name: str, filename: str) -> None:
    payload = load_yaml(PROFILES_DIR / filename)

    assert profile_name(payload) == expected_name
    assert payload.get("schema_version") == "kx-network-profile/v1"


@pytest.mark.parametrize("profile", sorted(CANONICAL_PROFILE_FILES))
def test_canonical_env_matches_profile(profile: str) -> None:
    payload = load_yaml(profile_path(profile))
    env = canonical_env(payload)

    assert env.get("KX_NETWORK_PROFILE") == profile
    assert env.get("KX_EXPOSURE_MODE") == exposure_mode(payload)
    assert str(env.get("KX_PUBLIC_MODE_ENABLED", "")).lower() in {"true", "false"}


@pytest.mark.parametrize("profile", sorted(CANONICAL_PROFILE_FILES))
def test_profile_uses_allowed_exposure_mode(profile: str) -> None:
    payload = load_yaml(profile_path(profile))

    assert exposure_mode(payload) in ALLOWED_PROFILE_EXPOSURE[profile]


def test_default_profile_is_intranet_private_and_private() -> None:
    defaults = []

    for profile in CANONICAL_PROFILE_FILES:
        payload = load_yaml(profile_path(profile))
        if payload.get("profile", {}).get("default") is True:
            defaults.append(payload)

    assert len(defaults) == 1
    default = defaults[0]

    assert profile_name(default) == "intranet_private"
    assert exposure_mode(default) == "private"

    env = canonical_env(default)
    assert env.get("KX_NETWORK_PROFILE") == "intranet_private"
    assert env.get("KX_EXPOSURE_MODE") == "private"
    assert str(env.get("KX_PUBLIC_MODE_ENABLED", "")).lower() == "false"


@pytest.mark.parametrize("profile", sorted(CANONICAL_PROFILE_FILES))
def test_public_mode_is_not_default(profile: str) -> None:
    payload = load_yaml(profile_path(profile))
    env = canonical_env(payload)

    if payload.get("profile", {}).get("default") is True:
        assert str(env.get("KX_PUBLIC_MODE_ENABLED", "")).lower() == "false"
        assert exposure_mode(payload) == "private"


@pytest.mark.parametrize("profile", sorted(CANONICAL_PROFILE_FILES))
def test_forbidden_internal_ports_are_never_published(profile: str) -> None:
    payload = load_yaml(profile_path(profile))
    published = collect_publish_ports(payload)

    assert published.isdisjoint(FORBIDDEN_PUBLIC_PORTS), (
        f"{profile} publishes forbidden internal ports: "
        f"{sorted(published.intersection(FORBIDDEN_PUBLIC_PORTS))}"
    )


def test_public_temporary_requires_expiration() -> None:
    payload = load_yaml(profile_path("public_temporary"))
    env = canonical_env(payload)

    assert exposure_mode(payload) == "temporary_tunnel"
    assert payload.get("exposure", {}).get("requires_expiration") is True

    # Template value may be blank, but the profile must declare the requirement.
    assert "KX_PUBLIC_MODE_EXPIRES_AT" in env


def test_public_vps_is_the_only_permanent_public_profile() -> None:
    for profile in CANONICAL_PROFILE_FILES:
        payload = load_yaml(profile_path(profile))

        if exposure_mode(payload) == "public":
            assert profile == "public_vps"
            assert payload.get("exposure", {}).get("public_allowed") is True
        else:
            assert profile != "public_vps" or exposure_mode(payload) == "public"


def test_offline_profile_has_no_external_exposure() -> None:
    payload = load_yaml(profile_path("offline"))
    env = canonical_env(payload)

    assert profile_name(payload) == "offline"
    assert exposure_mode(payload) == "private"

    assert env.get("KX_NETWORK_PROFILE") == "offline"
    assert env.get("KX_EXPOSURE_MODE") == "private"
    assert str(env.get("KX_PUBLIC_MODE_ENABLED", "")).lower() == "false"
    assert env.get("KX_HOST") in {"", None}

    exposure = payload.get("exposure", {})
    assert exposure.get("public_allowed") is False
    assert exposure.get("lan_allowed") is False
    assert exposure.get("tunnel_allowed") is False
    assert exposure.get("temporary_public_allowed") is False

    routing = payload.get("routing", {})
    assert routing.get("traefik_enabled") is False
    assert routing.get("public_entrypoint_enabled") is False
    assert routing.get("allowed_external_paths") == []

    ports = payload.get("ports", {})
    assert ports.get("allowed_entry_ports") == []
    assert collect_publish_ports(payload) == set()


def test_offline_profile_disables_public_network_and_traefik_ports() -> None:
    payload = load_yaml(profile_path("offline"))
    compose_overrides = payload.get("compose_overrides", {})

    traefik = compose_overrides.get("traefik", {})
    assert traefik.get("enabled") is False
    assert traefik.get("publish_ports") == []

    networks = compose_overrides.get("networks", {})
    assert networks.get("kx-public", {}).get("enabled") is False
    assert networks.get("kx-internal", {}).get("enabled") is True
    assert networks.get("kx-internal", {}).get("internal") is True


@pytest.mark.parametrize(
    "profile,expected_exposure",
    [
        ("local_only", "private"),
        ("intranet_private", "private"),
        ("private_tunnel", "vpn"),
        ("public_temporary", "temporary_tunnel"),
        ("public_vps", "public"),
        ("offline", "private"),
    ],
)
def test_profile_expected_primary_exposure(profile: str, expected_exposure: str) -> None:
    payload = load_yaml(profile_path(profile))

    assert exposure_mode(payload) == expected_exposure


def test_security_gate_blocking_checks_present_in_all_profiles() -> None:
    required_blocking = {
        "capsule_signature",
        "image_checksums",
        "manifest_schema",
        "secrets_present",
        "secrets_not_default",
        "dangerous_ports_blocked",
        "postgres_not_public",
        "redis_not_public",
        "docker_socket_not_mounted",
        "no_privileged_containers",
        "no_host_network",
        "allowed_images_only",
    }

    for profile in CANONICAL_PROFILE_FILES:
        payload = load_yaml(profile_path(profile))
        security_gate = payload.get("security_gate", {})
        blocking = set(security_gate.get("blocking_checks", []))

        assert security_gate.get("required") is True
        assert required_blocking.issubset(blocking), profile
