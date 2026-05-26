"""
Contract tests for Konnaxion Docker Compose runtime generation.

These tests define the expected behavior of ``kx_agent.runtime.compose``.
They intentionally verify canonical service names, ports, routing, security
posture, env-file placement, private-by-default runtime rules, public VPS host
propagation, Traefik file-provider routing, healthchecks, and full runtime image
coverage for every generated Compose file.

Important runtime contract:

- Compose does not build Konnaxion app images.
- Compose does not pull Konnaxion app images from a registry.
- Konnaxion app images are capsule-owned/offline-loaded images.
- The Agent startup path must load capsule images before docker compose up.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
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

APP_IMAGE_SERVICES = {
    DockerService.FRONTEND_NEXT.value,
    DockerService.DJANGO_API.value,
    DockerService.CELERYWORKER.value,
    DockerService.CELERYBEAT.value,
    DockerService.FLOWER.value,
}

REQUIRED_APP_IMAGE_SERVICES = {
    DockerService.FRONTEND_NEXT.value,
    DockerService.DJANGO_API.value,
    DockerService.CELERYWORKER.value,
    DockerService.CELERYBEAT.value,
}

REQUIRED_RUNTIME_IMAGE_SERVICES = {
    DockerService.TRAEFIK.value,
    DockerService.FRONTEND_NEXT.value,
    DockerService.DJANGO_API.value,
    DockerService.POSTGRES.value,
    DockerService.REDIS.value,
    DockerService.CELERYWORKER.value,
    DockerService.CELERYBEAT.value,
    DockerService.MEDIA_NGINX.value,
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

FORBIDDEN_PUBLIC_URL_FRAGMENTS = {
    "http://localhost",
    "https://localhost",
    "http://127.0.0.1",
    "https://127.0.0.1",
    "http://0.0.0.0",
    "https://0.0.0.0",
    "api.konnaxion.com",
}

PUBLIC_TEST_HOST = "138.197.174.76.sslip.io"
PUBLIC_CUSTOM_DOMAIN = "konnxion.com"
PUBLIC_CUSTOM_DOMAIN_ALIASES = (
    "www.konnxion.com",
    PUBLIC_TEST_HOST,
)


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


def test_all_required_runtime_services_have_images(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)
    services = compose["services"]

    for service_name in sorted(REQUIRED_RUNTIME_IMAGE_SERVICES):
        assert service_name in services

        image = str(services[service_name].get("image") or "").strip()
        assert image, f"{service_name} must declare an image"
        assert _image_has_tag_or_digest(image), (
            f"{service_name} image must include an explicit tag or digest: {image!r}"
        )


def test_runtime_images_use_expected_canonical_repositories(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)
    services = compose["services"]

    expected_prefixes = {
        DockerService.TRAEFIK.value: ("traefik:", "traefik@"),
        DockerService.FRONTEND_NEXT.value: (
            "konnaxion/frontend-next:",
            "konnaxion/frontend-next@",
        ),
        DockerService.DJANGO_API.value: (
            "konnaxion/django-api:",
            "konnaxion/django-api@",
        ),
        DockerService.POSTGRES.value: ("postgres:", "postgres@"),
        DockerService.REDIS.value: ("redis:", "redis@"),
        DockerService.MEDIA_NGINX.value: ("nginx:", "nginx@"),
    }

    for service_name, prefixes in expected_prefixes.items():
        image = str(services[service_name].get("image") or "")
        assert image.startswith(prefixes), (
            f"{service_name} image {image!r} must start with one of {prefixes!r}"
        )

    django_image = services[DockerService.DJANGO_API.value]["image"]
    assert services[DockerService.CELERYWORKER.value]["image"] == django_image
    assert services[DockerService.CELERYBEAT.value]["image"] == django_image

    if DockerService.FLOWER.value in services:
        assert services[DockerService.FLOWER.value]["image"] == django_image


def test_konnaxion_app_images_never_pull_from_registry_at_runtime(
    tmp_path: Path,
) -> None:
    compose = _generate_compose(tmp_path)

    for service_name, service_def in compose["services"].items():
        image = str(service_def.get("image") or "")

        if not image.startswith("konnaxion/"):
            continue

        assert service_def.get("pull_policy") == "never", (
            f"{service_name} uses local/offline image {image!r} and must set "
            "pull_policy: never"
        )


def test_konnaxion_app_images_are_not_built_or_pulled_by_runtime_compose(
    tmp_path: Path,
) -> None:
    """Konnaxion app images must come from capsule-loaded OCI archives.

    This guards the bug class where a Droplet keeps an old local image tag or
    Compose tries to fetch/build app images instead of relying on Agent image
    loading from ``images/*.oci.tar``.
    """

    compose = _generate_compose(tmp_path)

    for service_name in sorted(REQUIRED_APP_IMAGE_SERVICES):
        service_def = compose["services"][service_name]
        image = str(service_def.get("image") or "")

        assert image.startswith("konnaxion/"), (
            f"{service_name} must use a capsule-owned konnaxion/* image"
        )
        assert service_def.get("pull_policy") == "never", (
            f"{service_name} must never pull {image!r} from a registry"
        )
        assert "build" not in service_def, (
            f"{service_name} must not define a Compose build context"
        )
        assert service_def.get("pull_policy") not in {
            "always",
            "missing",
            "if_not_present",
        }


def test_konnaxion_app_images_use_stable_tags_for_offline_replacement(
    tmp_path: Path,
) -> None:
    """Runtime app tags must be deterministic so docker load can replace them."""

    compose = _generate_compose(tmp_path)

    expected_images = {
        DockerService.FRONTEND_NEXT.value: "konnaxion/frontend-next:v14",
        DockerService.DJANGO_API.value: "konnaxion/django-api:v14",
        DockerService.CELERYWORKER.value: "konnaxion/django-api:v14",
        DockerService.CELERYBEAT.value: "konnaxion/django-api:v14",
    }

    for service_name, expected_image in expected_images.items():
        assert compose["services"][service_name]["image"] == expected_image


def test_external_runtime_images_have_explicit_registry_tags(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)
    services = compose["services"]

    external_services = {
        DockerService.TRAEFIK.value,
        DockerService.POSTGRES.value,
        DockerService.REDIS.value,
        DockerService.MEDIA_NGINX.value,
    }

    for service_name in sorted(external_services):
        image = str(services[service_name].get("image") or "")

        assert image
        assert _image_has_tag_or_digest(image), (
            f"{service_name} external image must be pinned with a tag or digest"
        )

        # Do not allow accidental use of floating implicit latest.
        assert not image.endswith(":latest"), (
            f"{service_name} should not use implicit/floating latest image tag"
        )


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
        env_files = _normalized_env_files(services[service_name])
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


def test_routes_are_declared_for_traefik_runtime_config(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)
    runtime_text = _traefik_runtime_text(compose)

    for route_path, service_name in ROUTES.items():
        assert route_path in runtime_text
        assert service_name in runtime_text


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
            host="demo.example.test",
        )


def test_public_vps_requires_host(tmp_path: Path) -> None:
    with pytest.raises((ValueError, RuntimeError)):
        _generate_compose(
            tmp_path,
            network_profile=NetworkProfile.PUBLIC_VPS,
            exposure_mode=ExposureMode.PUBLIC,
            host=None,
        )


@pytest.mark.parametrize(
    "bad_host",
    [
        "127.0.0.1",
        "localhost",
        "0.0.0.0",
        "::1",
    ],
)
def test_public_vps_rejects_loopback_or_unspecified_hosts(
    tmp_path: Path,
    bad_host: str,
) -> None:
    with pytest.raises((ValueError, RuntimeError)):
        _generate_compose(
            tmp_path,
            network_profile=NetworkProfile.PUBLIC_VPS,
            exposure_mode=ExposureMode.PUBLIC,
            host=bad_host,
        )


def test_public_vps_uses_public_host_not_loopback(tmp_path: Path) -> None:
    compose = _generate_compose(
        tmp_path,
        network_profile=NetworkProfile.PUBLIC_VPS,
        exposure_mode=ExposureMode.PUBLIC,
        host=PUBLIC_TEST_HOST,
    )
    serialized = yaml.safe_dump(compose, sort_keys=False)

    assert f"KX_HOST={PUBLIC_TEST_HOST}" in serialized
    assert "KX_NETWORK_PROFILE=public_vps" in serialized
    assert "KX_EXPOSURE_MODE=public" in serialized
    assert "KX_PUBLIC_MODE_ENABLED=true" in serialized

    assert "KX_HOST=127.0.0.1" not in serialized
    assert "Host(`127.0.0.1`)" not in serialized
    assert "https://127.0.0.1/api" not in serialized
    assert "https://127.0.0.1" not in serialized


def test_public_vps_compose_never_embeds_loopback_or_prod_domain_urls(
    tmp_path: Path,
) -> None:
    compose = _generate_compose(
        tmp_path,
        network_profile=NetworkProfile.PUBLIC_VPS,
        exposure_mode=ExposureMode.PUBLIC,
        host=PUBLIC_TEST_HOST,
    )
    serialized = yaml.safe_dump(compose, sort_keys=False)

    for forbidden in FORBIDDEN_PUBLIC_URL_FRAGMENTS:
        assert forbidden not in serialized


def test_public_vps_traefik_file_provider_is_enabled(tmp_path: Path) -> None:
    compose = _generate_compose(
        tmp_path,
        network_profile=NetworkProfile.PUBLIC_VPS,
        exposure_mode=ExposureMode.PUBLIC,
        host=PUBLIC_TEST_HOST,
    )

    traefik = compose["services"][DockerService.TRAEFIK.value]
    command_text = _command_as_text(traefik)
    volume_text = "\n".join(_service_volume_strings(traefik))

    assert "--providers.file" in command_text
    assert "/etc/traefik/dynamic" in command_text or "/etc/traefik/dynamic" in volume_text
    assert "/var/run/docker.sock" not in volume_text
    assert "/run/docker.sock" not in volume_text


def test_public_vps_traefik_routes_use_public_host(tmp_path: Path) -> None:
    compose = _generate_compose(
        tmp_path,
        network_profile=NetworkProfile.PUBLIC_VPS,
        exposure_mode=ExposureMode.PUBLIC,
        host=PUBLIC_TEST_HOST,
    )
    runtime_text = _traefik_runtime_text(compose)

    assert f"Host(`{PUBLIC_TEST_HOST}`)" in runtime_text
    assert "PathPrefix(`/`)" in runtime_text
    assert "PathPrefix(`/api/`)" in runtime_text
    assert "PathPrefix(`/admin/`)" in runtime_text

    assert DockerService.FRONTEND_NEXT.value in runtime_text
    assert DockerService.DJANGO_API.value in runtime_text
    assert "127.0.0.1" not in runtime_text


def test_public_vps_traefik_routes_include_custom_domain_aliases(
    tmp_path: Path,
) -> None:
    compose = _generate_compose(
        tmp_path,
        network_profile=NetworkProfile.PUBLIC_VPS,
        exposure_mode=ExposureMode.PUBLIC,
        host=PUBLIC_CUSTOM_DOMAIN,
        host_aliases=PUBLIC_CUSTOM_DOMAIN_ALIASES,
    )
    runtime_text = _traefik_runtime_text(compose)
    serialized = yaml.safe_dump(compose, sort_keys=False)

    assert f"KX_HOST={PUBLIC_CUSTOM_DOMAIN}" in serialized

    assert f"Host(`{PUBLIC_CUSTOM_DOMAIN}`)" in runtime_text
    assert "Host(`www.konnxion.com`)" in runtime_text
    assert f"Host(`{PUBLIC_TEST_HOST}`)" in runtime_text

    assert "PathPrefix(`/`)" in runtime_text
    assert "PathPrefix(`/api/`)" in runtime_text
    assert "PathPrefix(`/admin/`)" in runtime_text

    assert DockerService.FRONTEND_NEXT.value in runtime_text
    assert DockerService.DJANGO_API.value in runtime_text

    assert "Host(`127.0.0.1`)" not in runtime_text
    assert "Host(`localhost`)" not in runtime_text
    assert "api.konnaxion.com" not in runtime_text


def test_public_vps_traefik_routes_use_websecure_tls_entrypoint(
    tmp_path: Path,
) -> None:
    compose = _generate_compose(
        tmp_path,
        network_profile=NetworkProfile.PUBLIC_VPS,
        exposure_mode=ExposureMode.PUBLIC,
        host=PUBLIC_TEST_HOST,
    )
    runtime_text = _traefik_runtime_text(compose)

    assert "websecure" in runtime_text
    assert "tls" in runtime_text.lower()
    assert "--entrypoints.websecure.address=:443" in runtime_text


def test_public_vps_traefik_dynamic_routes_use_container_names(
    tmp_path: Path,
) -> None:
    instance_id = "demo-001"
    compose = _generate_compose(
        tmp_path,
        instance_id=instance_id,
        network_profile=NetworkProfile.PUBLIC_VPS,
        exposure_mode=ExposureMode.PUBLIC,
        host=PUBLIC_TEST_HOST,
    )
    runtime_text = _traefik_runtime_text(compose)

    assert f"http://kx-{instance_id}-frontend-next:3000" in runtime_text
    assert f"http://kx-{instance_id}-django-api:5000" in runtime_text


def test_public_vps_frontend_environment_uses_public_backend_urls(
    tmp_path: Path,
) -> None:
    compose = _generate_compose(
        tmp_path,
        network_profile=NetworkProfile.PUBLIC_VPS,
        exposure_mode=ExposureMode.PUBLIC,
        host=PUBLIC_TEST_HOST,
    )
    frontend = compose["services"][DockerService.FRONTEND_NEXT.value]
    env_text = _environment_as_text(frontend)
    serialized = yaml.safe_dump(compose, sort_keys=False)

    combined = env_text + "\n" + serialized

    assert f"NEXT_PUBLIC_API_BASE=https://{PUBLIC_TEST_HOST}/api" in combined
    assert f"NEXT_PUBLIC_BACKEND_BASE=https://{PUBLIC_TEST_HOST}" in combined
    assert "NEXT_PUBLIC_API_BASE=https://127.0.0.1/api" not in combined
    assert "NEXT_PUBLIC_BACKEND_BASE=https://127.0.0.1" not in combined
    assert "NEXT_PUBLIC_API_BASE=http://localhost:8000/api" not in combined
    assert "NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000/api" not in combined
    assert "api.konnaxion.com" not in combined


def test_public_vps_django_environment_allows_public_host(tmp_path: Path) -> None:
    compose = _generate_compose(
        tmp_path,
        network_profile=NetworkProfile.PUBLIC_VPS,
        exposure_mode=ExposureMode.PUBLIC,
        host=PUBLIC_TEST_HOST,
    )
    django = compose["services"][DockerService.DJANGO_API.value]
    env_text = _environment_as_text(django)
    serialized = yaml.safe_dump(compose, sort_keys=False)
    combined = env_text + "\n" + serialized

    assert "DJANGO_ALLOWED_HOSTS=" in combined
    assert PUBLIC_TEST_HOST in combined
    assert "localhost" in combined
    assert "127.0.0.1" in combined
    assert DockerService.DJANGO_API.value in combined


def test_django_healthcheck_uses_socket_probe_not_wget_or_host_header(
    tmp_path: Path,
) -> None:
    compose = _generate_compose(
        tmp_path,
        network_profile=NetworkProfile.PUBLIC_VPS,
        exposure_mode=ExposureMode.PUBLIC,
        host=PUBLIC_TEST_HOST,
    )
    django = compose["services"][DockerService.DJANGO_API.value]
    healthcheck_text = _healthcheck_as_text(django)

    assert "socket.create_connection" in healthcheck_text
    assert "127.0.0.1" in healthcheck_text
    assert "5000" in healthcheck_text

    assert "wget" not in healthcheck_text
    assert "curl" not in healthcheck_text
    assert "api/health" not in healthcheck_text
    assert '"api/health' not in healthcheck_text


def test_media_nginx_healthcheck_does_not_require_wget(tmp_path: Path) -> None:
    compose = _generate_compose(tmp_path)
    media = compose["services"][DockerService.MEDIA_NGINX.value]
    healthcheck_text = _healthcheck_as_text(media)

    assert "wget" not in healthcheck_text


def test_frontend_command_does_not_require_runtime_pnpm_or_corepack(
    tmp_path: Path,
) -> None:
    compose = _generate_compose(tmp_path)
    frontend = compose["services"][DockerService.FRONTEND_NEXT.value]
    command_text = _command_as_text(frontend)
    serialized = yaml.safe_dump(frontend, sort_keys=False)

    combined = command_text + "\n" + serialized

    assert "next" in combined.lower()
    assert "0.0.0.0" in combined
    assert "3000" in combined

    assert "pnpm start" not in combined
    assert '["pnpm", "start"]' not in combined
    assert "corepack" not in combined.lower()


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
    host: str | None = None,
    host_aliases: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Call the canonical compose generator.

    The implementation is expected in ``kx_agent.runtime.compose``. The tests
    accept either a function returning a dict or an object with a ``to_dict``
    method.

    Public profiles must receive an explicit public host. This is the value used
    for KX_HOST, Django allowed hosts, frontend public backend URLs, and Traefik
    Host(...) rules.

    ``host_aliases`` are additional public hosts that should route to the same
    instance through Traefik, for example ``www.<domain>`` and an ``sslip.io``
    fallback host.
    """

    from kx_agent.runtime.compose import generate_runtime_compose

    kwargs: dict[str, Any] = {
        "instance_id": instance_id,
        "capsule_id": capsule_id,
        "instance_root": tmp_path / "instances" / instance_id,
        "network_profile": network_profile,
        "exposure_mode": exposure_mode,
        "public_mode_expires_at": public_mode_expires_at,
    }

    if host is not None:
        kwargs["host"] = host

    if host_aliases:
        kwargs["host_aliases"] = host_aliases

    result = generate_runtime_compose(**kwargs)

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


def _normalized_env_files(service_def: MappingLike) -> set[str]:
    result: set[str] = set()

    for item in _env_files(service_def):
        normalized = str(PurePosixPath(item))
        while normalized.startswith("../"):
            normalized = normalized[3:]
        result.add(normalized)

    return result


def _service_volume_strings(service_def: MappingLike) -> list[str]:
    return [str(volume) for volume in service_def.get("volumes") or []]


def _labels_as_text(service_def: MappingLike) -> str:
    labels = service_def.get("labels") or {}

    if isinstance(labels, dict):
        return yaml.safe_dump(labels, sort_keys=True)

    return "\n".join(str(label) for label in labels)


def _command_as_text(service_def: MappingLike) -> str:
    command = service_def.get("command") or []
    entrypoint = service_def.get("entrypoint") or []

    parts: list[str] = []

    for value in (entrypoint, command):
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value:
            parts.append(str(value))

    return "\n".join(parts)


def _environment_as_text(service_def: MappingLike) -> str:
    environment = service_def.get("environment") or {}

    if isinstance(environment, dict):
        return "\n".join(f"{key}={value}" for key, value in sorted(environment.items()))

    if isinstance(environment, list):
        return "\n".join(str(item) for item in environment)

    return str(environment)


def _healthcheck_as_text(service_def: MappingLike) -> str:
    healthcheck = service_def.get("healthcheck") or {}
    if not healthcheck:
        return ""

    return yaml.safe_dump(healthcheck, sort_keys=True)


def _traefik_runtime_text(compose: MappingLike) -> str:
    """Return all routing-relevant text from generated compose.

    The canonical runtime should use Traefik file provider. During transition,
    this helper also includes labels and extension fields so tests can point at
    all possible routing declarations.
    """

    services = compose.get("services") or {}
    traefik = services.get(DockerService.TRAEFIK.value) or {}

    chunks = [
        _labels_as_text(traefik),
        _command_as_text(traefik),
        "\n".join(_service_volume_strings(traefik)),
    ]

    for service_name in (
        DockerService.FRONTEND_NEXT.value,
        DockerService.DJANGO_API.value,
        DockerService.MEDIA_NGINX.value,
    ):
        service_def = services.get(service_name) or {}
        chunks.append(_labels_as_text(service_def))

    for key, value in compose.items():
        if str(key).startswith("x-") or str(key) in {
            "traefik_dynamic",
            "traefik_dynamic_config",
            "dynamic_config",
        }:
            chunks.append(yaml.safe_dump({key: value}, sort_keys=True))

    chunks.append(yaml.safe_dump(compose, sort_keys=True))

    return "\n".join(chunks)


def _image_has_tag_or_digest(image: str) -> bool:
    """Return True when a Docker image reference is not implicitly latest."""

    value = image.strip()
    if not value:
        return False

    if "@" in value:
        return True

    # Docker references may include registry ports, so only inspect the final
    # path segment for a tag separator.
    final_segment = value.rsplit("/", 1)[-1]
    return ":" in final_segment and not final_segment.endswith(":")


MappingLike = dict[str, Any]