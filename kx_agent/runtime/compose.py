"""
Konnaxion Docker Compose runtime renderer and validator.

Responsibilities:
- Render docker-compose.runtime.yml for a Konnaxion Instance.
- Render Traefik dynamic routing config without mounting the Docker socket.
- Use canonical service names, ports, env files, volumes, and networks.
- Validate that generated compose does not expose internal services.
- Write generated files atomically under the canonical instance state path.

This module does not:
- Start or stop Docker Compose.
- Import capsules.
- Generate secrets.
- Run migrations.
- Modify firewall rules.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    yaml = None  # type: ignore[assignment]
    _YAML_IMPORT_ERROR = exc
else:
    _YAML_IMPORT_ERROR = None

from kx_shared.konnaxion_constants import (
    ALLOWED_ENTRY_PORTS,
    APP_VERSION,
    CANONICAL_DOCKER_SERVICES,
    DEFAULT_CAPSULE_ID,
    DEFAULT_EXPOSURE_MODE,
    DEFAULT_NETWORK_PROFILE,
    DEFAULT_PUBLIC_MODE_ENABLED,
    DockerService,
    ExposureMode,
    FORBIDDEN_PUBLIC_PORTS,
    INTERNAL_ONLY_PORTS,
    NetworkProfile,
    PARAM_VERSION,
)
from kx_shared.paths import (
    assert_under_root,
    ensure_dir,
    instance_compose_file,
    instance_state_dir,
    validate_safe_id,
)


COMPOSE_FILENAME = "docker-compose.runtime.yml"
TRAEFIK_DYNAMIC_FILENAME = "traefik-dynamic.yml"

PUBLIC_NETWORK = "kx-public"
PRIVATE_NETWORK = "kx-private"
DATA_NETWORK = "kx-data"

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

DEFAULT_IMAGES = {
    DockerService.TRAEFIK.value: "traefik:v3.1",
    DockerService.FRONTEND_NEXT.value: "konnaxion/frontend-next:v14",
    DockerService.DJANGO_API.value: "konnaxion/django-api:v14",
    DockerService.POSTGRES.value: "postgres:16",
    DockerService.REDIS.value: "redis:7",
    DockerService.CELERYWORKER.value: "konnaxion/django-api:v14",
    DockerService.CELERYBEAT.value: "konnaxion/django-api:v14",
    DockerService.FLOWER.value: "konnaxion/django-api:v14",
    DockerService.MEDIA_NGINX.value: "nginx:stable",
}


class ComposeRenderError(RuntimeError):
    """Raised when runtime Compose rendering cannot continue."""


class ComposeValidationError(ValueError):
    """Raised when generated Compose violates Konnaxion runtime policy."""


def enum_value(value: Any) -> str:
    """Return the string value for StrEnum/Enum/string inputs.

    This helper must be defined before dataclass defaults that call it.
    """

    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def path_text(path: str | Path) -> str:
    """Return stable POSIX-style path text for generated Compose YAML."""

    return Path(path).as_posix()


def require_yaml() -> None:
    """Require PyYAML before YAML rendering/reading."""

    if yaml is None:  # pragma: no cover
        raise ComposeRenderError(
            "PyYAML is required to render docker-compose.runtime.yml"
        ) from _YAML_IMPORT_ERROR


def yaml_dump(data: Mapping[str, Any]) -> str:
    """Return deterministic YAML for generated runtime files."""

    require_yaml()
    return yaml.safe_dump(  # type: ignore[union-attr]
        data,
        sort_keys=False,
        default_flow_style=False,
        indent=2,
        width=120,
    )


def atomic_write_text(path: str | Path, content: str, *, mode: int = 0o640) -> Path:
    """Atomically write text under the canonical Konnaxion root."""

    target = assert_under_root(path)
    ensure_dir(target.parent)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
        text=True,
    )
    tmp_path = Path(tmp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(tmp_path, target)
        target.chmod(mode)
        return target
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class ComposeImageSet:
    """Images used by the generated Docker Compose runtime."""

    traefik: str = DEFAULT_IMAGES[DockerService.TRAEFIK.value]
    frontend_next: str = DEFAULT_IMAGES[DockerService.FRONTEND_NEXT.value]
    django_api: str = DEFAULT_IMAGES[DockerService.DJANGO_API.value]
    postgres: str = DEFAULT_IMAGES[DockerService.POSTGRES.value]
    redis: str = DEFAULT_IMAGES[DockerService.REDIS.value]
    celeryworker: str = DEFAULT_IMAGES[DockerService.CELERYWORKER.value]
    celerybeat: str = DEFAULT_IMAGES[DockerService.CELERYBEAT.value]
    flower: str = DEFAULT_IMAGES[DockerService.FLOWER.value]
    media_nginx: str = DEFAULT_IMAGES[DockerService.MEDIA_NGINX.value]

    @classmethod
    def from_mapping(cls, image_map: Mapping[str, str] | None = None) -> "ComposeImageSet":
        """Create an image set from a canonical service-name mapping."""

        if not image_map:
            return cls()

        allowed = {
            DockerService.TRAEFIK.value: "traefik",
            DockerService.FRONTEND_NEXT.value: "frontend_next",
            DockerService.DJANGO_API.value: "django_api",
            DockerService.POSTGRES.value: "postgres",
            DockerService.REDIS.value: "redis",
            DockerService.CELERYWORKER.value: "celeryworker",
            DockerService.CELERYBEAT.value: "celerybeat",
            DockerService.FLOWER.value: "flower",
            DockerService.MEDIA_NGINX.value: "media_nginx",
        }

        kwargs: dict[str, str] = {}

        for service_name, image in image_map.items():
            if service_name not in allowed:
                raise ComposeRenderError(f"unknown image service name: {service_name}")

            if not isinstance(image, str) or not image.strip():
                raise ComposeRenderError(f"image for {service_name} must be a non-empty string")

            kwargs[allowed[service_name]] = image.strip()

        return cls(**kwargs)

    def for_service(self, service: DockerService | str) -> str:
        """Return the image for a canonical Docker service."""

        service_value = enum_value(service)
        mapping = {
            DockerService.TRAEFIK.value: self.traefik,
            DockerService.FRONTEND_NEXT.value: self.frontend_next,
            DockerService.DJANGO_API.value: self.django_api,
            DockerService.POSTGRES.value: self.postgres,
            DockerService.REDIS.value: self.redis,
            DockerService.CELERYWORKER.value: self.celeryworker,
            DockerService.CELERYBEAT.value: self.celerybeat,
            DockerService.FLOWER.value: self.flower,
            DockerService.MEDIA_NGINX.value: self.media_nginx,
        }

        try:
            return mapping[service_value]
        except KeyError as exc:
            raise ComposeRenderError(f"non-canonical service name: {service_value}") from exc


@dataclass(frozen=True)
class ComposeRenderOptions:
    """Inputs required to render a safe Konnaxion runtime Compose spec."""

    instance_id: str
    host: str
    capsule_id: str = DEFAULT_CAPSULE_ID
    instance_root: Path | None = None
    network_profile: str = enum_value(DEFAULT_NETWORK_PROFILE)
    exposure_mode: str = enum_value(DEFAULT_EXPOSURE_MODE)
    public_mode_enabled: bool = DEFAULT_PUBLIC_MODE_ENABLED
    public_mode_expires_at: str | None = None
    image_map: Mapping[str, str] | None = None
    include_flower: bool = False
    bind_http: bool = True
    bind_https: bool = True
    allow_http_on_local_only: bool = False

    def normalized(self) -> "ComposeRenderOptions":
        """Return validated normalized render options."""

        instance_id = validate_safe_id(self.instance_id, field_name="instance_id")
        network_profile = enum_value(self.network_profile)
        exposure_mode = enum_value(self.exposure_mode)
        host = str(self.host).strip()
        capsule_id = str(self.capsule_id).strip() or DEFAULT_CAPSULE_ID

        if network_profile not in {enum_value(item) for item in NetworkProfile}:
            raise ComposeRenderError(f"invalid network_profile: {network_profile}")

        if exposure_mode not in {enum_value(item) for item in ExposureMode}:
            raise ComposeRenderError(f"invalid exposure_mode: {exposure_mode}")

        if not host:
            raise ComposeRenderError("host must not be empty")

        if network_profile == NetworkProfile.PUBLIC_TEMPORARY.value:
            if exposure_mode != ExposureMode.TEMPORARY_TUNNEL.value:
                raise ComposeRenderError(
                    "public_temporary requires exposure_mode=temporary_tunnel"
                )

            if not self.public_mode_expires_at:
                raise ComposeRenderError(
                    "public_mode_expires_at is required for public_temporary"
                )

        if exposure_mode == ExposureMode.TEMPORARY_TUNNEL.value and not self.public_mode_expires_at:
            raise ComposeRenderError(
                "public_mode_expires_at is required for temporary_tunnel exposure"
            )

        public_mode_enabled = bool(
            self.public_mode_enabled
            or network_profile in {
                NetworkProfile.PUBLIC_TEMPORARY.value,
                NetworkProfile.PUBLIC_VPS.value,
            }
            or exposure_mode in {
                ExposureMode.TEMPORARY_TUNNEL.value,
                ExposureMode.PUBLIC.value,
            }
        )

        return ComposeRenderOptions(
            instance_id=instance_id,
            host=host,
            capsule_id=capsule_id,
            instance_root=self.instance_root,
            network_profile=network_profile,
            exposure_mode=exposure_mode,
            public_mode_enabled=public_mode_enabled,
            public_mode_expires_at=self.public_mode_expires_at,
            image_map=self.image_map,
            include_flower=self.include_flower,
            bind_http=self.bind_http,
            bind_https=self.bind_https,
            allow_http_on_local_only=self.allow_http_on_local_only,
        )


@dataclass(frozen=True)
class ComposeWriteResult:
    """Result returned after rendering/writing runtime Compose files."""

    instance_id: str
    compose_file: str
    traefik_dynamic_file: str
    network_profile: str
    exposure_mode: str
    services: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def generated_instance_root(options: ComposeRenderOptions) -> Path:
    """Return the instance root used for generated volume paths."""

    if options.instance_root is not None:
        return Path(options.instance_root)

    return Path("/opt/konnaxion") / "instances" / options.instance_id


def generated_env_file(filename: str) -> str:
    """Return canonical relative env-file path for Compose."""

    return f"env/{filename}"


def generated_volume_path(options: ComposeRenderOptions, name: str) -> str:
    """Return a stable POSIX-style instance volume path."""

    return path_text(generated_instance_root(options) / name)


def container_name(instance_id: str, service: DockerService | str) -> str:
    """Return a deterministic container name."""

    instance_id = validate_safe_id(instance_id, field_name="instance_id")
    service_name = enum_value(service)

    if service_name not in CANONICAL_DOCKER_SERVICES:
        raise ComposeRenderError(f"non-canonical service name: {service_name}")

    return f"kx-{instance_id}-{service_name}"


def env_file_path(instance_id: str, filename: str) -> str:
    """Return canonical relative env-file path.

    The instance_id argument is retained for API compatibility.
    """

    validate_safe_id(instance_id, field_name="instance_id")
    return generated_env_file(filename)


def service_log_dir(instance_id: str, service: DockerService | str) -> str:
    """Return stable service log directory text."""

    validate_safe_id(instance_id, field_name="instance_id")
    service_name = enum_value(service)
    return f"/opt/konnaxion/instances/{instance_id}/logs/{service_name}"


def traefik_dynamic_file(instance_id: str) -> Path:
    """Return canonical Traefik dynamic config path."""

    return assert_under_root(instance_state_dir(instance_id) / TRAEFIK_DYNAMIC_FILENAME)


def runtime_environment(options: ComposeRenderOptions) -> list[str]:
    """Return canonical KX_* runtime environment entries."""

    options = options.normalized()

    return [
        f"KX_INSTANCE_ID={options.instance_id}",
        f"KX_CAPSULE_ID={options.capsule_id}",
        f"KX_APP_VERSION={APP_VERSION}",
        f"KX_PARAM_VERSION={PARAM_VERSION}",
        f"KX_NETWORK_PROFILE={options.network_profile}",
        f"KX_EXPOSURE_MODE={options.exposure_mode}",
        f"KX_PUBLIC_MODE_ENABLED={str(options.public_mode_enabled).lower()}",
        f"KX_PUBLIC_MODE_EXPIRES_AT={options.public_mode_expires_at or ''}",
        "KX_REQUIRE_SIGNED_CAPSULE=true",
        "KX_GENERATE_SECRETS_ON_INSTALL=true",
        "KX_ALLOW_UNKNOWN_IMAGES=false",
        "KX_ALLOW_PRIVILEGED_CONTAINERS=false",
        "KX_ALLOW_DOCKER_SOCKET_MOUNT=false",
        "KX_ALLOW_HOST_NETWORK=false",
        "KX_BACKUP_ENABLED=true",
        f"KX_HOST={options.host}",
    ]


def port_bindings_for_profile(options: ComposeRenderOptions) -> list[str]:
    """Return safe Traefik port bindings for the selected network profile.

    Only 80/443 are ever returned. Internal service ports are never published.
    """

    options = options.normalized()

    http_port = int(ALLOWED_ENTRY_PORTS["http_redirect"])
    https_port = int(ALLOWED_ENTRY_PORTS["https"])

    bindings: list[str] = []

    if options.network_profile == NetworkProfile.OFFLINE.value:
        return bindings

    if options.network_profile == NetworkProfile.LOCAL_ONLY.value:
        if options.allow_http_on_local_only and options.bind_http:
            bindings.append(f"127.0.0.1:{http_port}:{http_port}")
        if options.bind_https:
            bindings.append(f"127.0.0.1:{https_port}:{https_port}")
        return bindings

    if options.network_profile in {
        NetworkProfile.INTRANET_PRIVATE.value,
        NetworkProfile.PUBLIC_VPS.value,
    }:
        if options.bind_http:
            bindings.append(f"{http_port}:{http_port}")
        if options.bind_https:
            bindings.append(f"{https_port}:{https_port}")
        return bindings

    if options.network_profile in {
        NetworkProfile.PRIVATE_TUNNEL.value,
        NetworkProfile.PUBLIC_TEMPORARY.value,
    }:
        if options.bind_https:
            bindings.append(f"127.0.0.1:{https_port}:{https_port}")
        return bindings

    raise ComposeRenderError(f"unsupported network_profile: {options.network_profile}")


def base_service_defaults(instance_id: str, service: DockerService | str) -> dict[str, Any]:
    """Return safe defaults common to Konnaxion runtime containers."""

    service_name = enum_value(service)

    return {
        "container_name": container_name(instance_id, service_name),
        "restart": "unless-stopped",
        "security_opt": ["no-new-privileges:true"],
        "read_only": False,
        "privileged": False,
        "networks": [PRIVATE_NETWORK],
        "logging": {
            "driver": "json-file",
            "options": {
                "max-size": "10m",
                "max-file": "5",
            },
        },
    }


def traefik_labels(host: str) -> list[str]:
    """Return Traefik labels used by tests and operator inspection."""

    return [
        "traefik.enable=true",
        f"traefik.http.routers.kx-frontend.rule=Host(`{host}`) && PathPrefix(`/`)",
        "traefik.http.routers.kx-frontend.entrypoints=websecure",
        "traefik.http.routers.kx-frontend.tls=true",
        "traefik.http.routers.kx-frontend.service=frontend-next",
        "traefik.http.services.frontend-next.loadbalancer.server.port=3000",
        f"traefik.http.routers.kx-api.rule=Host(`{host}`) && PathPrefix(`/api/`)",
        "traefik.http.routers.kx-api.entrypoints=websecure",
        "traefik.http.routers.kx-api.tls=true",
        "traefik.http.routers.kx-api.service=django-api",
        "traefik.http.services.django-api.loadbalancer.server.port=5000",
        f"traefik.http.routers.kx-admin.rule=Host(`{host}`) && PathPrefix(`/admin/`)",
        "traefik.http.routers.kx-admin.entrypoints=websecure",
        "traefik.http.routers.kx-admin.tls=true",
        "traefik.http.routers.kx-admin.service=django-api",
        f"traefik.http.routers.kx-media.rule=Host(`{host}`) && PathPrefix(`/media/`)",
        "traefik.http.routers.kx-media.entrypoints=websecure",
        "traefik.http.routers.kx-media.tls=true",
        "traefik.http.routers.kx-media.service=media-nginx",
        "traefik.http.services.media-nginx.loadbalancer.server.port=80",
    ]


def render_traefik_dynamic_config(host: str) -> dict[str, Any]:
    """Render Traefik file-provider dynamic routing config."""

    if not host:
        raise ComposeRenderError("host must not be empty")

    return {
        "http": {
            "routers": {
                "kx-frontend": {
                    "rule": f"Host(`{host}`) && PathPrefix(`/`)",
                    "entryPoints": ["websecure"],
                    "service": "frontend-next",
                    "tls": {},
                    "priority": 10,
                },
                "kx-api": {
                    "rule": f"Host(`{host}`) && PathPrefix(`/api/`)",
                    "entryPoints": ["websecure"],
                    "service": "django-api",
                    "tls": {},
                    "priority": 100,
                },
                "kx-admin": {
                    "rule": f"Host(`{host}`) && PathPrefix(`/admin/`)",
                    "entryPoints": ["websecure"],
                    "service": "django-api",
                    "tls": {},
                    "priority": 100,
                },
                "kx-media": {
                    "rule": f"Host(`{host}`) && PathPrefix(`/media/`)",
                    "entryPoints": ["websecure"],
                    "service": "media-nginx",
                    "tls": {},
                    "priority": 100,
                },
            },
            "services": {
                "frontend-next": {
                    "loadBalancer": {
                        "servers": [
                            {"url": f"http://{DockerService.FRONTEND_NEXT.value}:3000"}
                        ]
                    }
                },
                "django-api": {
                    "loadBalancer": {
                        "servers": [
                            {"url": f"http://{DockerService.DJANGO_API.value}:5000"}
                        ]
                    }
                },
                "media-nginx": {
                    "loadBalancer": {
                        "servers": [
                            {"url": f"http://{DockerService.MEDIA_NGINX.value}:80"}
                        ]
                    }
                },
            },
            "middlewares": {
                "secure-headers": {
                    "headers": {
                        "browserXssFilter": True,
                        "contentTypeNosniff": True,
                        "frameDeny": True,
                    }
                }
            },
        }
    }


def render_compose_spec(options: ComposeRenderOptions) -> dict[str, Any]:
    """Render the canonical Konnaxion Docker Compose runtime spec."""

    options = options.normalized()
    images = ComposeImageSet.from_mapping(options.image_map)
    environment = runtime_environment(options)
    services: dict[str, Any] = {}

    traefik = base_service_defaults(options.instance_id, DockerService.TRAEFIK)
    traefik.update(
        {
            "image": images.for_service(DockerService.TRAEFIK),
            "command": [
                "--providers.file.filename=/etc/traefik/dynamic/traefik-dynamic.yml",
                "--providers.file.watch=true",
                "--entrypoints.web.address=:80",
                "--entrypoints.websecure.address=:443",
                "--entrypoints.web.http.redirections.entrypoint.to=websecure",
                "--entrypoints.web.http.redirections.entrypoint.scheme=https",
                "--api.dashboard=false",
            ],
            "ports": port_bindings_for_profile(options),
            "volumes": [
                f"{path_text(generated_instance_root(options) / 'state' / TRAEFIK_DYNAMIC_FILENAME)}:/etc/traefik/dynamic/traefik-dynamic.yml:ro",
                f"{generated_volume_path(options, 'logs')}/traefik:/var/log/traefik",
            ],
            "labels": traefik_labels(options.host),
            "networks": [PUBLIC_NETWORK, PRIVATE_NETWORK],
            "environment": environment,
        }
    )
    services[DockerService.TRAEFIK.value] = traefik

    frontend = base_service_defaults(options.instance_id, DockerService.FRONTEND_NEXT)
    frontend.update(
        {
            "image": images.for_service(DockerService.FRONTEND_NEXT),
            "expose": [str(INTERNAL_ONLY_PORTS[DockerService.FRONTEND_NEXT])],
            "env_file": [generated_env_file("frontend.env")],
            "environment": environment,
            "depends_on": [DockerService.DJANGO_API.value],
        }
    )
    services[DockerService.FRONTEND_NEXT.value] = frontend

    django = base_service_defaults(options.instance_id, DockerService.DJANGO_API)
    django.update(
        {
            "image": images.for_service(DockerService.DJANGO_API),
            "command": "/start",
            "expose": [str(INTERNAL_ONLY_PORTS[DockerService.DJANGO_API])],
            "env_file": [
                generated_env_file("kx.env"),
                generated_env_file("django.env"),
                generated_env_file("postgres.env"),
                generated_env_file("redis.env"),
            ],
            "environment": environment,
            "depends_on": {
                DockerService.POSTGRES.value: {"condition": "service_healthy"},
                DockerService.REDIS.value: {"condition": "service_healthy"},
            },
            "volumes": [
                f"{generated_volume_path(options, 'media')}:/app/media",
                f"{generated_volume_path(options, 'logs')}/django-api:/app/logs",
            ],
            "healthcheck": {
                "test": [
                    "CMD-SHELL",
                    "wget -qO- http://127.0.0.1:5000/api/health/ >/dev/null 2>&1 || exit 1",
                ],
                "interval": "30s",
                "timeout": "5s",
                "retries": 10,
            },
        }
    )
    services[DockerService.DJANGO_API.value] = django

    postgres = base_service_defaults(options.instance_id, DockerService.POSTGRES)
    postgres.update(
        {
            "image": images.for_service(DockerService.POSTGRES),
            "expose": [str(INTERNAL_ONLY_PORTS[DockerService.POSTGRES])],
            "env_file": [generated_env_file("postgres.env")],
            "environment": environment,
            "volumes": [
                f"{generated_volume_path(options, 'postgres')}:/var/lib/postgresql/data",
            ],
            "networks": [DATA_NETWORK],
            "healthcheck": {
                "test": ["CMD-SHELL", "pg_isready -U konnaxion -d konnaxion"],
                "interval": "30s",
                "timeout": "5s",
                "retries": 10,
            },
        }
    )
    services[DockerService.POSTGRES.value] = postgres

    redis = base_service_defaults(options.instance_id, DockerService.REDIS)
    redis.update(
        {
            "image": images.for_service(DockerService.REDIS),
            "command": ["redis-server", "--appendonly", "yes"],
            "expose": [str(INTERNAL_ONLY_PORTS[DockerService.REDIS])],
            "env_file": [generated_env_file("redis.env")],
            "environment": environment,
            "volumes": [
                f"{generated_volume_path(options, 'redis')}:/data",
            ],
            "networks": [DATA_NETWORK],
            "healthcheck": {
                "test": ["CMD", "redis-cli", "ping"],
                "interval": "30s",
                "timeout": "5s",
                "retries": 10,
            },
        }
    )
    services[DockerService.REDIS.value] = redis

    celeryworker = base_service_defaults(options.instance_id, DockerService.CELERYWORKER)
    celeryworker.update(
        {
            "image": images.for_service(DockerService.CELERYWORKER),
            "command": "/start-celeryworker",
            "env_file": [
                generated_env_file("kx.env"),
                generated_env_file("django.env"),
                generated_env_file("postgres.env"),
                generated_env_file("redis.env"),
            ],
            "environment": environment,
            "depends_on": {
                DockerService.DJANGO_API.value: {"condition": "service_healthy"},
                DockerService.REDIS.value: {"condition": "service_healthy"},
            },
            "volumes": [
                f"{generated_volume_path(options, 'media')}:/app/media",
                f"{generated_volume_path(options, 'logs')}/celeryworker:/app/logs",
            ],
        }
    )
    services[DockerService.CELERYWORKER.value] = celeryworker

    celerybeat = base_service_defaults(options.instance_id, DockerService.CELERYBEAT)
    celerybeat.update(
        {
            "image": images.for_service(DockerService.CELERYBEAT),
            "command": "/start-celerybeat",
            "env_file": [
                generated_env_file("kx.env"),
                generated_env_file("django.env"),
                generated_env_file("postgres.env"),
                generated_env_file("redis.env"),
            ],
            "environment": environment,
            "depends_on": {
                DockerService.DJANGO_API.value: {"condition": "service_healthy"},
                DockerService.REDIS.value: {"condition": "service_healthy"},
            },
            "volumes": [
                f"{generated_volume_path(options, 'logs')}/celerybeat:/app/logs",
            ],
        }
    )
    services[DockerService.CELERYBEAT.value] = celerybeat

    if options.include_flower:
        flower = base_service_defaults(options.instance_id, DockerService.FLOWER)
        flower.update(
            {
                "image": images.for_service(DockerService.FLOWER),
                "command": "/start-flower",
                "profiles": ["observability"],
                "expose": [str(INTERNAL_ONLY_PORTS[DockerService.FLOWER])],
                "env_file": [
                    generated_env_file("kx.env"),
                    generated_env_file("django.env"),
                    generated_env_file("redis.env"),
                ],
                "environment": environment,
                "depends_on": {
                    DockerService.REDIS.value: {"condition": "service_healthy"},
                },
                "networks": [PRIVATE_NETWORK, DATA_NETWORK],
            }
        )
        services[DockerService.FLOWER.value] = flower

    media = base_service_defaults(options.instance_id, DockerService.MEDIA_NGINX)
    media.update(
        {
            "image": images.for_service(DockerService.MEDIA_NGINX),
            "expose": ["80"],
            "environment": environment,
            "volumes": [
                f"{generated_volume_path(options, 'media')}:/usr/share/nginx/html/media:ro",
                f"{generated_volume_path(options, 'logs')}/media-nginx:/var/log/nginx",
            ],
            "healthcheck": {
                "test": [
                    "CMD-SHELL",
                    "wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1",
                ],
                "interval": "30s",
                "timeout": "5s",
                "retries": 5,
            },
        }
    )
    services[DockerService.MEDIA_NGINX.value] = media

    compose: dict[str, Any] = {
        "name": f"konnaxion-{options.instance_id}",
        "services": services,
        "networks": {
            PUBLIC_NETWORK: {
                "name": f"kx-{options.instance_id}-public",
                "driver": "bridge",
            },
            PRIVATE_NETWORK: {
                "name": f"kx-{options.instance_id}-private",
                "driver": "bridge",
                "internal": True,
            },
            DATA_NETWORK: {
                "name": f"kx-{options.instance_id}-data",
                "driver": "bridge",
                "internal": True,
            },
        },
    }

    for service_name in (
        DockerService.DJANGO_API.value,
        DockerService.CELERYWORKER.value,
        DockerService.CELERYBEAT.value,
    ):
        compose["services"][service_name]["networks"] = [PRIVATE_NETWORK, DATA_NETWORK]

    validate_compose_spec(compose)
    return compose


def generate_runtime_compose(
    *,
    instance_id: str,
    capsule_id: str = DEFAULT_CAPSULE_ID,
    instance_root: str | Path | None = None,
    host: str = "konnaxion.local",
    network_profile: NetworkProfile | str = DEFAULT_NETWORK_PROFILE,
    exposure_mode: ExposureMode | str = DEFAULT_EXPOSURE_MODE,
    public_mode_enabled: bool | None = None,
    public_mode_expires_at: str | None = None,
    image_map: Mapping[str, str] | None = None,
    include_flower: bool = False,
) -> dict[str, Any]:
    """Compatibility wrapper used by tests and Agent actions."""

    profile_value = enum_value(network_profile)
    exposure_value = enum_value(exposure_mode)

    inferred_public_mode = profile_value in {
        NetworkProfile.PUBLIC_TEMPORARY.value,
        NetworkProfile.PUBLIC_VPS.value,
    } or exposure_value in {
        ExposureMode.TEMPORARY_TUNNEL.value,
        ExposureMode.PUBLIC.value,
    }

    options = ComposeRenderOptions(
        instance_id=instance_id,
        host=host,
        capsule_id=capsule_id,
        instance_root=Path(instance_root) if instance_root is not None else None,
        network_profile=profile_value,
        exposure_mode=exposure_value,
        public_mode_enabled=inferred_public_mode if public_mode_enabled is None else public_mode_enabled,
        public_mode_expires_at=public_mode_expires_at,
        image_map=image_map,
        include_flower=include_flower,
    )

    return render_compose_spec(options)


def validate_compose_spec(compose: Mapping[str, Any]) -> None:
    """Validate generated Compose policy before writing."""

    services = compose.get("services")
    if not isinstance(services, Mapping):
        raise ComposeValidationError("compose must contain a services mapping")

    service_names = set(services.keys())
    canonical = set(CANONICAL_DOCKER_SERVICES)

    forbidden_aliases = service_names & FORBIDDEN_SERVICE_ALIASES
    if forbidden_aliases:
        raise ComposeValidationError(
            f"forbidden non-canonical service names: {sorted(forbidden_aliases)}"
        )

    unknown = service_names - canonical
    if unknown:
        raise ComposeValidationError(f"unknown non-canonical service names: {sorted(unknown)}")

    required = {
        DockerService.TRAEFIK.value,
        DockerService.FRONTEND_NEXT.value,
        DockerService.DJANGO_API.value,
        DockerService.POSTGRES.value,
        DockerService.REDIS.value,
        DockerService.CELERYWORKER.value,
        DockerService.CELERYBEAT.value,
        DockerService.MEDIA_NGINX.value,
    }

    missing = required - service_names
    if missing:
        raise ComposeValidationError(f"missing required services: {sorted(missing)}")

    for service_name, service in services.items():
        if not isinstance(service, Mapping):
            raise ComposeValidationError(f"service {service_name} must be a mapping")

        if service.get("privileged") is True:
            raise ComposeValidationError(f"service {service_name} must not be privileged")

        if service.get("network_mode") == "host":
            raise ComposeValidationError(f"service {service_name} must not use host networking")

        for volume in service.get("volumes", []) or []:
            volume_text = str(volume)
            if "/var/run/docker.sock" in volume_text or "/run/docker.sock" in volume_text:
                raise ComposeValidationError(
                    f"service {service_name} must not mount Docker socket"
                )

        ports = service.get("ports", []) or []
        if service_name != DockerService.TRAEFIK.value and ports:
            raise ComposeValidationError(
                f"only traefik may publish ports; {service_name} publishes {ports}"
            )

        for port in ports:
            published, target = parse_compose_port(port)
            unsafe = {published, target} & set(int(item) for item in FORBIDDEN_PUBLIC_PORTS)

            if unsafe:
                raise ComposeValidationError(
                    f"service {service_name} exposes forbidden public port(s): {sorted(unsafe)}"
                )

            if target not in {
                int(ALLOWED_ENTRY_PORTS["http_redirect"]),
                int(ALLOWED_ENTRY_PORTS["https"]),
            }:
                raise ComposeValidationError(
                    f"service {service_name} exposes non-entrypoint target port: {target}"
                )

    networks = compose.get("networks", {})
    if not isinstance(networks, Mapping):
        raise ComposeValidationError("compose networks must be a mapping")

    for internal_network in (PRIVATE_NETWORK, DATA_NETWORK):
        network_spec = networks.get(internal_network)
        if not isinstance(network_spec, Mapping) or network_spec.get("internal") is not True:
            raise ComposeValidationError(f"{internal_network} must be an internal network")


def parse_compose_port(port: Any) -> tuple[int, int]:
    """Parse Compose short-form port syntax."""

    if isinstance(port, Mapping):
        return int(port.get("published")), int(port.get("target"))

    text = str(port)
    parts = text.split(":")

    if len(parts) == 1:
        value = int(parts[0])
        return value, value

    if len(parts) == 2:
        return int(parts[0]), int(parts[1])

    if len(parts) == 3:
        return int(parts[1]), int(parts[2])

    raise ComposeValidationError(f"unsupported compose port syntax: {port!r}")


def render_runtime_files(options: ComposeRenderOptions) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    """Render Compose YAML and Traefik dynamic YAML."""

    options = options.normalized()
    compose_spec = render_compose_spec(options)
    traefik_spec = render_traefik_dynamic_config(options.host)
    return yaml_dump(compose_spec), yaml_dump(traefik_spec), compose_spec, traefik_spec


def write_runtime_compose(options: ComposeRenderOptions) -> ComposeWriteResult:
    """Render and write docker-compose.runtime.yml and traefik-dynamic.yml."""

    options = options.normalized()
    ensure_dir(instance_state_dir(options.instance_id))

    compose_yaml, traefik_yaml, compose_spec, _traefik_spec = render_runtime_files(options)

    compose_path = atomic_write_text(instance_compose_file(options.instance_id), compose_yaml)
    traefik_path = atomic_write_text(traefik_dynamic_file(options.instance_id), traefik_yaml)

    services = tuple(compose_spec["services"].keys())
    warnings: list[str] = []

    if options.network_profile in {
        NetworkProfile.PRIVATE_TUNNEL.value,
        NetworkProfile.PUBLIC_TEMPORARY.value,
    }:
        warnings.append(
            "tunnel profile rendered with localhost-only Traefik binding; "
            "a separate approved tunnel adapter must provide remote access"
        )

    if options.network_profile == NetworkProfile.OFFLINE.value:
        warnings.append("offline profile rendered with no published ports")

    return ComposeWriteResult(
        instance_id=options.instance_id,
        compose_file=str(compose_path),
        traefik_dynamic_file=str(traefik_path),
        network_profile=options.network_profile,
        exposure_mode=options.exposure_mode,
        services=services,
        warnings=tuple(warnings),
    )


def read_compose_file(path: str | Path) -> dict[str, Any]:
    """Read a Compose YAML file and return its mapping."""

    require_yaml()
    safe_path = assert_under_root(path)

    with safe_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)  # type: ignore[union-attr]

    if not isinstance(loaded, dict):
        raise ComposeValidationError(f"compose file did not contain a mapping: {safe_path}")

    return loaded


def validate_compose_file(path: str | Path) -> None:
    """Load and validate a generated runtime Compose file."""

    validate_compose_spec(read_compose_file(path))


class ComposeRenderer:
    """Service object used by Agent actions and tests."""

    def render(self, options: ComposeRenderOptions) -> dict[str, Any]:
        return render_compose_spec(options)

    def render_files(self, options: ComposeRenderOptions) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
        return render_runtime_files(options)

    def write(self, options: ComposeRenderOptions) -> ComposeWriteResult:
        return write_runtime_compose(options)

    def validate(self, compose: Mapping[str, Any]) -> None:
        validate_compose_spec(compose)


__all__ = [
    "COMPOSE_FILENAME",
    "DATA_NETWORK",
    "DEFAULT_IMAGES",
    "FORBIDDEN_SERVICE_ALIASES",
    "PRIVATE_NETWORK",
    "PUBLIC_NETWORK",
    "TRAEFIK_DYNAMIC_FILENAME",
    "ComposeImageSet",
    "ComposeRenderError",
    "ComposeRenderOptions",
    "ComposeRenderer",
    "ComposeValidationError",
    "ComposeWriteResult",
    "atomic_write_text",
    "base_service_defaults",
    "container_name",
    "enum_value",
    "env_file_path",
    "generate_runtime_compose",
    "parse_compose_port",
    "port_bindings_for_profile",
    "read_compose_file",
    "render_compose_spec",
    "render_runtime_files",
    "render_traefik_dynamic_config",
    "runtime_environment",
    "service_log_dir",
    "traefik_dynamic_file",
    "validate_compose_file",
    "validate_compose_spec",
    "write_runtime_compose",
]