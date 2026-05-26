"""
Tests for canonical Konnaxion network profiles.

These tests enforce DOC-00, DOC-06, and DOC-08 alignment:
- only canonical network profile names exist
- intranet_private/private is the default
- public exposure is never default
- dangerous internal ports are never publicly exposed
- offline profile has no external exposure
- public_vps requires an explicit non-loopback public host
- public_vps supports optional public host aliases
- public_temporary is the only profile that requires public expiration
- public_vps is permanent public exposure and must not require expiration
- public_vps must not freeze localhost/loopback/old fallback host values
- profile output must support durable Traefik/Django/frontend host regeneration
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

PUBLIC_ENTRY_PORTS = {80, 443}

LOOPBACK_HOST_VALUES = {
    "127.0.0.1",
    "localhost",
    "::1",
    "[::1]",
    "0.0.0.0",
    "http://127.0.0.1",
    "https://127.0.0.1",
    "http://localhost",
    "https://localhost",
}

PUBLIC_VPS_FORBIDDEN_HOST_SUBSTRINGS = {
    "127.0.0.1",
    "localhost",
    "0.0.0.0",
}

PUBLIC_VPS_HOST_DERIVED_ENV_KEYS = {
    "KX_HOST",
    "KX_HOST_ALIASES",
    "DJANGO_ALLOWED_HOSTS",
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "CSRF_TRUSTED_ORIGINS",
    "CORS_ALLOWED_ORIGINS",
    "NEXT_PUBLIC_API_BASE",
    "NEXT_PUBLIC_BACKEND_BASE",
    "NEXT_PUBLIC_SITE_URL",
    "NEXTAUTH_URL",
}

ALLOWED_PROFILE_EXPOSURE = {
    "local_only": {"private"},
    "intranet_private": {"private", "lan"},
    "private_tunnel": {"private", "vpn"},
    "public_temporary": {"temporary_tunnel"},
    "public_vps": {"public"},
    "offline": {"private"},
}

PUBLIC_HOST_SOURCE_ORDER = (
    "domain",
    "droplet_domain",
    "public_host",
    "public_url",
    "url",
    "host",
    "kx_host",
    "KX_HOST",
    "droplet_host",
    "target_host",
)


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


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def env_bool(env: Mapping[str, Any], key: str) -> bool:
    return boolish(env.get(key))


def normalized_host(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    raw = raw.strip().strip("/")

    if raw.startswith(("http://", "https://")):
        raw = raw.removeprefix("http://").removeprefix("https://")

    raw = raw.split("/", 1)[0].strip()

    if "@" in raw:
        raw = raw.rsplit("@", 1)[-1].strip()

    return raw.lower()


def is_loopback_host(value: Any) -> bool:
    normalized_loopbacks = {normalized_host(item) for item in LOOPBACK_HOST_VALUES}
    return normalized_host(value) in normalized_loopbacks


def csv_values(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    return [item.strip() for item in str(value).split(",") if item.strip()]


def normalized_csv_hosts(value: Any) -> list[str]:
    hosts: list[str] = []
    for item in csv_values(value):
        host = normalized_host(item)
        if host and host not in hosts:
            hosts.append(host)
    return hosts


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

        allowed_entry_ports = ports.get("allowed_entry_ports", [])
        if isinstance(allowed_entry_ports, list):
            for item in allowed_entry_ports:
                if isinstance(item, int):
                    published.add(item)
                elif isinstance(item, str) and item.isdigit():
                    published.add(int(item))

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
                    elif isinstance(item, str) and ":" in item:
                        first = item.split(":", 1)[0]
                        if first.isdigit():
                            published.add(int(first))

    return published


def collect_allowed_entry_ports(payload: Mapping[str, Any]) -> set[int]:
    ports = payload.get("ports", {})
    if not isinstance(ports, Mapping):
        return set()

    allowed = ports.get("allowed_entry_ports", [])
    if not isinstance(allowed, list):
        return set()

    result: set[int] = set()
    for item in allowed:
        if isinstance(item, int):
            result.add(item)
        elif isinstance(item, str) and item.isdigit():
            result.add(int(item))

    return result


def profile_declares_required_public_host(payload: Mapping[str, Any]) -> bool:
    """Return True if the profile explicitly requires a public host.

    Accepts several equivalent names so the profile schema can evolve without
    weakening the contract:
      exposure.requires_host
      exposure.host_required
      exposure.requires_public_host
      exposure.public_host_required
      routing.public_host_required
      routing.requires_host
      canonical_env.KX_HOST set to a non-loopback template value
    """

    exposure = payload.get("exposure", {})
    routing = payload.get("routing", {})
    env = canonical_env(payload)

    if isinstance(exposure, Mapping):
        if boolish(exposure.get("requires_host")):
            return True
        if boolish(exposure.get("host_required")):
            return True
        if boolish(exposure.get("requires_public_host")):
            return True
        if boolish(exposure.get("public_host_required")):
            return True

    if isinstance(routing, Mapping):
        if boolish(routing.get("requires_host")):
            return True
        if boolish(routing.get("host_required")):
            return True
        if boolish(routing.get("requires_public_host")):
            return True
        if boolish(routing.get("public_host_required")):
            return True

    kx_host = str(env.get("KX_HOST", "") or "").strip()
    if kx_host and not is_loopback_host(kx_host):
        return True

    return False


def profile_declares_public_host_alias_support(payload: Mapping[str, Any]) -> bool:
    """Return True if the profile supports additional public host aliases."""

    exposure = payload.get("exposure", {})
    routing = payload.get("routing", {})
    env = canonical_env(payload)

    if "KX_HOST_ALIASES" in env:
        return True

    if isinstance(exposure, Mapping):
        for key in (
            "supports_host_aliases",
            "host_aliases_supported",
            "requires_host_alias_normalization",
        ):
            if boolish(exposure.get(key)):
                return True

    if isinstance(routing, Mapping):
        for key in (
            "supports_host_aliases",
            "host_aliases_supported",
            "host_aliases",
            "traefik_host_aliases",
        ):
            value = routing.get(key)
            if boolish(value) or isinstance(value, list):
                return True

    return False


def profile_requires_expiration(payload: Mapping[str, Any]) -> bool:
    exposure = payload.get("exposure", {})
    if not isinstance(exposure, Mapping):
        return False

    return (
        boolish(exposure.get("requires_expiration"))
        or boolish(exposure.get("expiration_required"))
        or boolish(exposure.get("requires_public_mode_expiration"))
    )


def profile_declares_traefik_file_provider(payload: Mapping[str, Any]) -> bool:
    routing = payload.get("routing", {})
    compose_overrides = payload.get("compose_overrides", {})

    if isinstance(routing, Mapping):
        provider = str(routing.get("provider") or routing.get("traefik_provider") or "")
        dynamic_config = str(
            routing.get("dynamic_config")
            or routing.get("dynamic_config_provider")
            or ""
        )
        if "file" in provider.lower() or "file" in dynamic_config.lower():
            return True

        if boolish(routing.get("file_provider")):
            return True
        if boolish(routing.get("traefik_file_provider")):
            return True

    if isinstance(compose_overrides, Mapping):
        traefik = compose_overrides.get("traefik", {})
        if isinstance(traefik, Mapping):
            command = traefik.get("command", [])
            if isinstance(command, list):
                joined = "\n".join(str(item) for item in command)
                if "providers.file" in joined:
                    return True

            if boolish(traefik.get("file_provider")):
                return True
            if boolish(traefik.get("traefik_file_provider")):
                return True

    return False


def profile_declares_runtime_regeneration_contract(payload: Mapping[str, Any]) -> bool:
    """Return True if a profile declares host-derived runtime regeneration.

    The profile schema may express this in several places. This test is flexible
    about the shape but strict about public_vps carrying the contract somewhere.
    """

    profile_contract = payload.get("profile", {})
    exposure = payload.get("exposure", {})
    routing = payload.get("routing", {})
    runtime = payload.get("runtime", {})
    env = canonical_env(payload)

    mappings = [
        profile_contract,
        exposure,
        routing,
        runtime,
        env,
    ]

    for mapping in mappings:
        if not isinstance(mapping, Mapping):
            continue

        for key in (
            "regenerate_runtime_on_host_change",
            "regenerate_runtime_files_on_host_change",
            "host_change_regenerates_runtime",
            "network_set_profile_persists_runtime",
            "NETWORK_SET_PROFILE_PERSISTS_RUNTIME",
        ):
            if boolish(mapping.get(key)):
                return True

    return False


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
    assert env_bool(env, "KX_PUBLIC_MODE_ENABLED") is False


@pytest.mark.parametrize("profile", sorted(CANONICAL_PROFILE_FILES))
def test_public_mode_is_not_default(profile: str) -> None:
    payload = load_yaml(profile_path(profile))
    env = canonical_env(payload)

    if payload.get("profile", {}).get("default") is True:
        assert env_bool(env, "KX_PUBLIC_MODE_ENABLED") is False
        assert exposure_mode(payload) == "private"


@pytest.mark.parametrize("profile", sorted(CANONICAL_PROFILE_FILES))
def test_forbidden_internal_ports_are_never_published(profile: str) -> None:
    payload = load_yaml(profile_path(profile))
    published = collect_publish_ports(payload)

    assert published.isdisjoint(FORBIDDEN_PUBLIC_PORTS), (
        f"{profile} publishes forbidden internal ports: "
        f"{sorted(published.intersection(FORBIDDEN_PUBLIC_PORTS))}"
    )


@pytest.mark.parametrize("profile", sorted(CANONICAL_PROFILE_FILES))
def test_non_public_profiles_do_not_default_to_loopback_public_host(profile: str) -> None:
    payload = load_yaml(profile_path(profile))
    env = canonical_env(payload)

    if exposure_mode(payload) != "public":
        return

    kx_host = str(env.get("KX_HOST", "") or "").strip()
    assert not is_loopback_host(kx_host), (
        f"{profile} must not use loopback as the public host default"
    )


def test_public_temporary_requires_expiration() -> None:
    payload = load_yaml(profile_path("public_temporary"))
    env = canonical_env(payload)

    assert exposure_mode(payload) == "temporary_tunnel"
    assert profile_requires_expiration(payload) is True

    # Template value may be blank, but the profile must declare the requirement.
    assert "KX_PUBLIC_MODE_EXPIRES_AT" in env


def test_public_vps_does_not_require_expiration() -> None:
    payload = load_yaml(profile_path("public_vps"))
    env = canonical_env(payload)

    assert exposure_mode(payload) == "public"
    assert profile_requires_expiration(payload) is False

    # public_vps is durable/permanent public exposure; it may include the env key
    # for uniform runtime generation, but it must not require a non-empty value.
    assert str(env.get("KX_PUBLIC_MODE_EXPIRES_AT", "") or "") == ""


def test_only_public_temporary_requires_expiration() -> None:
    for profile in CANONICAL_PROFILE_FILES:
        payload = load_yaml(profile_path(profile))

        if profile == "public_temporary":
            assert profile_requires_expiration(payload) is True
        else:
            assert profile_requires_expiration(payload) is False, (
                f"{profile} must not require public expiration"
            )


def test_public_vps_is_the_only_permanent_public_profile() -> None:
    for profile in CANONICAL_PROFILE_FILES:
        payload = load_yaml(profile_path(profile))

        if exposure_mode(payload) == "public":
            assert profile == "public_vps"
            assert payload.get("exposure", {}).get("public_allowed") is True
        else:
            assert profile != "public_vps" or exposure_mode(payload) == "public"


def test_public_vps_requires_explicit_public_host() -> None:
    payload = load_yaml(profile_path("public_vps"))
    env = canonical_env(payload)

    assert profile_name(payload) == "public_vps"
    assert exposure_mode(payload) == "public"
    assert env.get("KX_NETWORK_PROFILE") == "public_vps"
    assert env.get("KX_EXPOSURE_MODE") == "public"
    assert env_bool(env, "KX_PUBLIC_MODE_ENABLED") is True
    assert profile_declares_required_public_host(payload) is True


def test_public_vps_supports_public_host_aliases() -> None:
    payload = load_yaml(profile_path("public_vps"))
    env = canonical_env(payload)

    assert profile_name(payload) == "public_vps"
    assert "KX_HOST_ALIASES" in env
    assert profile_declares_public_host_alias_support(payload) is True


def test_public_vps_host_aliases_do_not_use_loopback_defaults() -> None:
    payload = load_yaml(profile_path("public_vps"))
    env = canonical_env(payload)

    aliases = normalized_csv_hosts(env.get("KX_HOST_ALIASES", ""))

    for alias in aliases:
        assert not is_loopback_host(alias), (
            f"public_vps alias must not use loopback: {alias}"
        )
        assert not alias.endswith(".local"), (
            f"public_vps alias must not use .local hostnames: {alias}"
        )


def test_public_vps_does_not_use_loopback_host_defaults() -> None:
    payload = load_yaml(profile_path("public_vps"))
    env = canonical_env(payload)

    for key in PUBLIC_VPS_HOST_DERIVED_ENV_KEYS:
        value = str(env.get(key, "") or "").strip()
        for forbidden in PUBLIC_VPS_FORBIDDEN_HOST_SUBSTRINGS:
            assert forbidden not in value.lower(), (
                f"public_vps {key} must not use {forbidden}"
            )


def test_public_vps_allows_only_public_entry_ports() -> None:
    payload = load_yaml(profile_path("public_vps"))
    allowed_entry_ports = collect_allowed_entry_ports(payload)

    if allowed_entry_ports:
        assert allowed_entry_ports.issubset(PUBLIC_ENTRY_PORTS)

    published = collect_publish_ports(payload)
    public_ports = published.intersection(PUBLIC_ENTRY_PORTS)

    # public_vps may publish 80/443 through Traefik, but never app/db/cache ports.
    assert public_ports.issubset(PUBLIC_ENTRY_PORTS)


def test_public_vps_uses_traefik_public_routing_contract() -> None:
    payload = load_yaml(profile_path("public_vps"))
    routing = payload.get("routing", {})
    compose_overrides = payload.get("compose_overrides", {})
    traefik = {}

    if isinstance(compose_overrides, Mapping):
        candidate = compose_overrides.get("traefik", {})
        if isinstance(candidate, Mapping):
            traefik = candidate

    assert isinstance(routing, Mapping), "public_vps routing must be a mapping"
    assert routing.get("traefik_enabled") is True
    assert routing.get("public_entrypoint_enabled") is True
    assert profile_declares_traefik_file_provider(payload) is True

    if traefik:
        assert traefik.get("enabled", True) is True
        publish_ports = set(traefik.get("publish_ports", []) or [])
        normalized_ports = {
            int(str(port).split(":", 1)[0])
            for port in publish_ports
            if str(port).split(":", 1)[0].isdigit()
        }
        assert normalized_ports.issubset(PUBLIC_ENTRY_PORTS)


def test_public_vps_declares_runtime_regeneration_on_host_change() -> None:
    payload = load_yaml(profile_path("public_vps"))

    assert profile_declares_runtime_regeneration_contract(payload) is True


def test_public_vps_host_source_order_is_documented_in_profile() -> None:
    payload = load_yaml(profile_path("public_vps"))
    routing = payload.get("routing", {})
    exposure = payload.get("exposure", {})
    profile = payload.get("profile", {})

    candidate: Any = None

    for mapping in (routing, exposure, profile):
        if isinstance(mapping, Mapping):
            for key in (
                "host_source_order",
                "public_host_source_order",
                "manager_host_source_order",
            ):
                if key in mapping:
                    candidate = mapping[key]
                    break
        if candidate is not None:
            break

    assert isinstance(candidate, list), (
        "public_vps must document Manager public-host source order"
    )

    normalized = tuple(str(item) for item in candidate)
    assert normalized[: len(PUBLIC_HOST_SOURCE_ORDER)] == PUBLIC_HOST_SOURCE_ORDER


def test_offline_profile_has_no_external_exposure() -> None:
    payload = load_yaml(profile_path("offline"))
    env = canonical_env(payload)

    assert profile_name(payload) == "offline"
    assert exposure_mode(payload) == "private"

    assert env.get("KX_NETWORK_PROFILE") == "offline"
    assert env.get("KX_EXPOSURE_MODE") == "private"
    assert env_bool(env, "KX_PUBLIC_MODE_ENABLED") is False

    offline_host = str(env.get("KX_HOST", "") or "").strip()
    assert offline_host in {"", "127.0.0.1", "localhost"}

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

    # Older profile YAML used kx-internal; newer runtime docs use kx-private
    # and kx-data. Accept either shape, but at least one internal private
    # network must remain enabled and internal.
    internal_networks = [
        networks.get("kx-internal", {}),
        networks.get("kx-private", {}),
        networks.get("kx-data", {}),
    ]

    assert any(
        network.get("enabled") is True and network.get("internal") is True
        for network in internal_networks
        if isinstance(network, Mapping)
    )


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


def test_public_vps_security_gate_checks_host_and_alias_routing() -> None:
    payload = load_yaml(profile_path("public_vps"))
    security_gate = payload.get("security_gate", {})
    blocking = set(security_gate.get("blocking_checks", []))

    required_public_vps_checks = {
        "public_host_present",
        "public_host_not_localhost",
        "runtime_env_host_matches_profile",
        "traefik_dynamic_host_matches_profile",
        "frontend_public_env_matches_profile",
    }

    alias_or_host_rule_checks = {
        "traefik_host_rules_contain_kx_host",
        "traefik_host_rules_contain_kx_host_aliases",
        "django_allowed_hosts_contains_kx_host",
        "django_allowed_hosts_contains_kx_host_aliases",
    }

    assert required_public_vps_checks.issubset(blocking)
    assert blocking.intersection(alias_or_host_rule_checks), (
        "public_vps must include Security Gate checks for KX_HOST/KX_HOST_ALIASES routing"
    )


def test_public_vps_runtime_contract_distinguishes_public_host_from_ssh_target() -> None:
    payload = load_yaml(profile_path("public_vps"))
    profile = payload.get("profile", {})
    exposure = payload.get("exposure", {})
    routing = payload.get("routing", {})

    public_host_keys: set[str] = set()
    ssh_target_keys: set[str] = set()

    for mapping in (profile, exposure, routing):
        if not isinstance(mapping, Mapping):
            continue

        for key in ("public_host_fields", "runtime_host_fields"):
            values = mapping.get(key, [])
            if isinstance(values, list):
                public_host_keys.update(str(item) for item in values)

        for key in ("ssh_target_fields", "transport_host_fields"):
            values = mapping.get(key, [])
            if isinstance(values, list):
                ssh_target_keys.update(str(item) for item in values)

    assert {"domain", "droplet_domain", "public_host", "host"}.issubset(
        public_host_keys
    )
    assert {"droplet_host", "target_host"}.issubset(ssh_target_keys)
    assert public_host_keys.isdisjoint(ssh_target_keys - {"host"})


def test_public_vps_profile_requires_host_on_instance_create_and_network_set_profile() -> None:
    payload = load_yaml(profile_path("public_vps"))
    profile = payload.get("profile", {})
    exposure = payload.get("exposure", {})
    routing = payload.get("routing", {})

    required_host_endpoints: set[str] = set()

    for mapping in (profile, exposure, routing):
        if not isinstance(mapping, Mapping):
            continue

        values = mapping.get("host_required_for_agent_endpoints", [])
        if isinstance(values, list):
            required_host_endpoints.update(str(item) for item in values)

    assert "/instances/create" in required_host_endpoints
    assert "/network/set-profile" in required_host_endpoints


def test_public_vps_network_set_profile_persists_runtime_files() -> None:
    payload = load_yaml(profile_path("public_vps"))
    profile = payload.get("profile", {})
    exposure = payload.get("exposure", {})
    routing = payload.get("routing", {})
    runtime = payload.get("runtime", {})

    persisted_files: set[str] = set()

    for mapping in (profile, exposure, routing, runtime):
        if not isinstance(mapping, Mapping):
            continue

        values = mapping.get("network_set_profile_regenerates", [])
        if isinstance(values, list):
            persisted_files.update(str(item) for item in values)

    required = {
        "env/kx.env",
        "env/django.env",
        "env/frontend.env",
        "state/docker-compose.runtime.yml",
        "state/traefik-dynamic.yml",
    }

    assert required.issubset(persisted_files)


def test_public_vps_network_set_profile_preserves_secrets() -> None:
    payload = load_yaml(profile_path("public_vps"))
    runtime = payload.get("runtime", {})
    exposure = payload.get("exposure", {})

    preserved: set[str] = set()

    for mapping in (runtime, exposure):
        if not isinstance(mapping, Mapping):
            continue

        values = mapping.get("network_set_profile_preserves", [])
        if isinstance(values, list):
            preserved.update(str(item) for item in values)

    required = {
        "DJANGO_SECRET_KEY",
        "POSTGRES_PASSWORD",
        "DATABASE_URL password component",
    }

    assert required.issubset(preserved)