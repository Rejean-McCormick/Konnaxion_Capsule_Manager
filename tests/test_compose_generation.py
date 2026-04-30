"""
Contract tests for Konnaxion Docker Compose runtime generation.

These tests define the expected behavior of ``kx_agent.runtime.compose``.
They intentionally verify the canonical service names, ports, routing,
security posture, env-file placement, and private-by-default runtime
rules that every generated compose file must follow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from kx_shared.konnaxion_constants import (
    DockerService,
    ExposureMode,
    FORBIDDEN_PUBLIC_PORTS,
    KX_BACKUPS_ROOT,
    NetworkProfile,
    ROUTES,
)


CANONICAL_REQUIRED_SERVICES = {
    DockerService.TRAEFIK.value,
    DockerService.FRONTEND_NEXT.value,
    DockerService.DJANGO_API.value,
    DockerService.POSTGRES.value,
    DockerService.REDIS.value,
    DockerService.CELERYWORKER.value,
    DockerService.CELERYBEAT.value,
    DockerService.MEDIA_NGINX.value,
}

OPTIONAL_CANONICAL_SERVICES = {
    DockerService.FLOWER.value,
}

FORBIDDEN_SERVICE_ALIASES = {
    "backend",
    "api",
    "web",
    "next",
    "frontend",
    "db",
    "database",
    "cache",
    "worker",
    "scheduler",
    "media",
    "agent",
}

FORBIDDEN_VOLUME_MOUNTS = {
    "/var/run/docker.sock",
    "/run/docker.sock",
}

ALLOWED_PUBLIC_PORTS = {
    "80",
    "443",
}


def test_generate_runtime_compose_returns_canonical_mapping(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)

    assert isinstance(compose, dict)
    assert compose["services"]
    assert set(compose["services"]).issuperset(CANONICAL_REQUIRED_SERVICES)


def test_generated_compose_uses_only_canonical_service_names(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)
    services = set(compose["services"])

    assert services.isdisjoint(FORBIDDEN_SERVICE_ALIASES)

    allowed = CANONICAL_REQUIRED_SERVICES | OPTIONAL_CANONICAL_SERVICES
    assert services.issubset(allowed)


def test_traefik_is_the_only_public_http_entrypoint(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)
    services = compose["services"]

    assert DockerService.TRAEFIK.value in services
    traefik = services[DockerService.TRAEFIK.value]

    public_ports = _published_host_ports(traefik)
    assert public_ports
    assert public_ports.issubset(ALLOWED_PUBLIC_PORTS)

    for service_name, service_def in services.items():
        if service_name == DockerService.TRAEFIK.value:
            continue
        assert _published_host_ports(service_def) == set(), (
            f"{service_name} must not publish host ports directly"
        )


@pytest.mark.parametrize("forbidden_port", sorted(FORBIDDEN_PUBLIC_PORTS))
def test_internal_ports_are_never_published(
    tmp_path: Path,
    forbidden_port: int,
) -> None:
    compose = _generate_compose(tmp_path)
    published = _all_published_host_ports(compose)

    assert str(forbidden_port) not in published


def test_required_internal_services_do_not_publish_ports(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)
    services = compose["services"]

    internal_services = {
        DockerService.FRONTEND_NEXT.value,
        DockerService.DJANGO_API.value,
        DockerService.POSTGRES.value,
        DockerService.REDIS.value,
        DockerService.CELERYWORKER.value,
        DockerService.CELERYBEAT.value,
        DockerService.MEDIA_NGINX.value,
    }

    for service_name in internal_services:
        assert service_name in services
        assert not _published_host_ports(services[service_name])


def test_no_service_uses_privileged_mode(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)

    for service_name, service_def in compose["services"].items():
        assert service_def.get("privileged") not in {True, "true", "True", "1"}, (
            f"{service_name} must not use privileged mode"
        )


def test_no_service_uses_host_network(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)

    for service_name, service_def in compose["services"].items():
        assert service_def.get("network_mode") != "host", (
            f"{service_name} must not use host networking"
        )


def test_no_service_mounts_docker_socket(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)

    for service_name, service_def in compose["services"].items():
        volumes = service_def.get("volumes") or []
        normalized = "\n".join(str(volume) for volume in volumes)

        for forbidden_mount in FORBIDDEN_VOLUME_MOUNTS:
            assert forbidden_mount not in normalized, (
                f"{service_name} must not mount {forbidden_mount}"
            )


def test_postgres_and_redis_are_internal_only(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)
    services = compose["services"]

    postgres = services[DockerService.POSTGRES.value]
    redis = services[DockerService.REDIS.value]

    assert not _published_host_ports(postgres)
    assert not _published_host_ports(redis)

    assert "ports" not in postgres or postgres["ports"] in (None, [])
    assert "ports" not in redis or redis["ports"] in (None, [])


def test_services_use_canonical_env_files(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)
    services = compose["services"]

    expected_env_files = {
        DockerService.DJANGO_API.value: "env/django.env",
        DockerService.POSTGRES.value: "env/postgres.env",
        DockerService.REDIS.value: "env/redis.env",
        DockerService.FRONTEND_NEXT.value: "env/frontend.env",
    }

    for service_name, expected_env_file in expected_env_files.items():
        env_files = _env_files(services[service_name])
        assert expected_env_file in env_files


def test_services_use_canonical_instance_volumes(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)
    services = compose["services"]

    postgres_volumes = _service_volume_strings(services[DockerService.POSTGRES.value])
    redis_volumes = _service_volume_strings(services[DockerService.REDIS.value])
    media_volumes = _service_volume_strings(services[DockerService.MEDIA_NGINX.value])

    assert any("/postgres" in volume for volume in postgres_volumes)
    assert any("/redis" in volume for volume in redis_volumes)
    assert any("/media" in volume for volume in media_volumes)


def test_routes_are_declared_for_traefik_labels(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)
    traefik = compose["services"][DockerService.TRAEFIK.value]
    labels = _labels_as_text(traefik)

    for route_path, service_name in ROUTES.items():
        assert route_path in labels
        assert service_name in labels


def test_private_by_default_profile_has_no_public_tunnel_vars(tmp_path: Path) -> None:
    compose = _generate_compose(
        tmp_path,
        network_profile=NetworkProfile.INTRANET_PRIVATE,
        exposure_mode=ExposureMode.PRIVATE,
    )
    serialized = yaml.safe_dump(compose)

    assert "KX_NETWORK_PROFILE=intranet_private" in serialized
    assert "KX_EXPOSURE_MODE=private" in serialized
    assert "KX_PUBLIC_MODE_ENABLED=true" not in serialized


def test_public_temporary_requires_expiration(tmp_path: Path) -> None:
    with pytest.raises((ValueError, RuntimeError)):
        _generate_compose(
            tmp_path,
            network_profile=NetworkProfile.PUBLIC_TEMPORARY,
            exposure_mode=ExposureMode.TEMPORARY_TUNNEL,
            public_mode_expires_at=None,
        )


def test_generated_compose_can_be_written_and_read_as_yaml(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)

    output_path = tmp_path / "docker-compose.runtime.yml"
    output_path.write_text(yaml.safe_dump(compose, sort_keys=False), encoding="utf-8")

    loaded = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    assert loaded == compose


def test_backup_root_is_not_mounted_as_mutable_app_volume(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)
    serialized = yaml.safe_dump(compose)

    # Backups are application recovery artifacts. They may be referenced by
    # backup tooling, but app runtime containers should not mount the full
    # canonical backup root as a general mutable volume.
    assert str(KX_BACKUPS_ROOT) not in serialized


def _generate_compose(
    tmp_path: Path,
    *,
    instance_id: str = "demo-001",
    capsule_id: str = "konnaxion-v14-demo-2026.04.30",
    network_profile: NetworkProfile = NetworkProfile.INTRANET_PRIVATE,
    exposure_mode: ExposureMode = ExposureMode.PRIVATE,
    public_mode_expires_at: str | None = None,
) -> dict[str, Any]:
    """Call the canonical compose generator.

    The implementation is expected in ``kx_agent.runtime.compose``. The
    tests accept either a function returning a dict or an object with a
    ``to_dict`` method.
    """

    from kx_agent.runtime.compose import generate_runtime_compose

    result = generate_runtime_compose(
        instance_id=instance_id,
        capsule_id=capsule_id,
        instance_root=tmp_path / "instances" / instance_id,
        network_profile=network_profile,
        exposure_mode=exposure_mode,
        public_mode_expires_at=public_mode_expires_at,
    )

    if hasattr(result, "to_dict"):
        result = result.to_dict()

    assert isinstance(result, dict)
    return result


def _published_host_ports(service_def: MappingLike) -> set[str]:
    ports = service_def.get("ports") or []
    result: set[str] = set()

    for port in ports:
        if isinstance(port, int):
            result.add(str(port))
            continue

        if isinstance(port, str):
            # Compose formats:
            #   "80:80"
            #   "127.0.0.1:80:80"
            #   "443"
            parts = port.split(":")
            if len(parts) == 1:
                result.add(parts[0].split("/")[0])
            elif len(parts) == 2:
                result.add(parts[0].split("/")[0])
            else:
                result.add(parts[-2].split("/")[0])
            continue

        if isinstance(port, dict):
            published = port.get("published")
            if published is not None:
                result.add(str(published))

    return result


def _all_published_host_ports(compose: MappingLike) -> set[str]:
    result: set[str] = set()
    for service_def in compose["services"].values():
        result.update(_published_host_ports(service_def))
    return result


def _env_files(service_def: MappingLike) -> set[str]:
    env_file = service_def.get("env_file") or []

    if isinstance(env_file, str):
        return {env_file}

    return {str(item) for item in env_file}


def _service_volume_strings(service_def: MappingLike) -> list[str]:
    return [str(volume) for volume in service_def.get("volumes") or []]


def _labels_as_text(service_def: MappingLike) -> str:
    labels = service_def.get("labels") or {}

    if isinstance(labels, dict):
        return yaml.safe_dump(labels, sort_keys=True)

    return "\n".join(str(label) for label in labels)


MappingLike = dict[str, Any]
