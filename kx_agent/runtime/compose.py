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

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
import os
import tempfile
from typing import Any, Mapping, MutableMapping

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    yaml = None  # type: ignore[assignment]
    _YAML_IMPORT_ERROR = exc
else:
    _YAML_IMPORT_ERROR = None

from kx_shared.paths import (
    KonnaxionPathError,
    assert_under_root,
    ensure_dir,
    instance_compose_file,
    instance_env_file,
    instance_logs_dir,
    instance_media_dir,
    instance_postgres_dir,
    instance_redis_dir,
    instance_state_dir,
    validate_safe_id,
)

try:
    from kx_shared.konnaxion_constants import (
        ALLOWED_ENTRY_PORTS,
        CANONICAL_DOCKER_SERVICES,
        DEFAULT_EXPOSURE_MODE,
        DEFAULT_NETWORK_PROFILE,
        DockerService,
        ExposureMode,
        FORBIDDEN_PUBLIC_PORTS,
        INTERNAL_ONLY_PORTS,
        NetworkProfile,
        ROUTES,
    )
except ImportError:  # pragma: no cover - early scaffold fallback
    class DockerService(str, Enum):
        TRAEFIK = "traefik"
        FRONTEND_NEXT = "frontend-next"
        DJANGO_API = "django-api"
        POSTGRES = "postgres"
        REDIS = "redis"
        CELERYWORKER = "celeryworker"
        CELERYBEAT = "celerybeat"
        FLOWER = "flower"
        MEDIA_NGINX = "media-nginx"
        KX_AGENT = "kx-agent"

    class NetworkProfile(str, Enum):
        LOCAL_ONLY = "local_only"
        INTRANET_PRIVATE = "intranet_private"
        PRIVATE_TUNNEL = "private_tunnel"
        PUBLIC_TEMPORARY = "public_temporary"
        PUBLIC_VPS = "public_vps"
        OFFLINE = "offline"

    class ExposureMode(str, Enum):
        PRIVATE = "private"
        LAN = "lan"
        VPN = "vpn"
        TEMPORARY_TUNNEL = "temporary_tunnel"
        PUBLIC = "public"

    ALLOWED_ENTRY_PORTS = {"https": 443, "http_redirect": 80, "ssh_admin_restricted": 22}
    FORBIDDEN_PUBLIC_PORTS = frozenset({3000, 5000, 5432, 6379, 5555, 8000})
    INTERNAL_ONLY_PORTS = {
        DockerService.FRONTEND_NEXT: 3000,
        DockerService.DJANGO_API: 5000,
        DockerService.POSTGRES: 5432,
        DockerService.REDIS: 6379,
        DockerService.FLOWER: 5555,
        "django_dev_server": 8000,
    }
    ROUTES = {
        "/": DockerService.FRONTEND_NEXT.value,
        "/api/": DockerService.DJANGO_API.value,
        "/admin/": DockerService.DJANGO_API.value,
        "/media/": DockerService.MEDIA_NGINX.value,
    }
    CANONICAL_DOCKER_SERVICES = tuple(service.value for service in DockerService)
    DEFAULT_NETWORK_PROFILE = NetworkProfile.INTRANET_PRIVATE
    DEFAULT_EXPOSURE_MODE = ExposureMode.PRIVATE


class ComposeRenderError(RuntimeError):
    """Raised when a runtime Compose file cannot be rendered safely."""


class ComposeValidationError(RuntimeError):
    """Raised when a Compose spec violates Konnaxion runtime policy."""


FORBIDDEN_SERVICE_ALIASES = frozenset(
    {
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
)

DEFAULT_IMAGES = {
    DockerService.TRAEFIK.value: "traefik:v3.2",
    DockerService.FRONTEND_NEXT.value: "konnaxion/frontend-next:v14",
    DockerService.DJANGO_API.value: "konnaxion/django-api:v14",
    DockerService.POSTGRES.value: "postgres:16-alpine",
    DockerService.REDIS.value: "redis:7-alpine",
    DockerService.CELERYWORKER.value: "konnaxion/django-api:v14",
    DockerService.CELERYBEAT.value: "konnaxion/django-api:v14",
    DockerService.FLOWER.value: "konnaxion/django-api:v14",
    DockerService.MEDIA_NGINX.value: "nginx:1.27-alpine",
}

COMPOSE_FILENAME = "docker-compose.runtime.yml"
TRAEFIK_DYNAMIC_FILENAME = "traefik-dynamic.yml"

PUBLIC_NETWORK = "kx-public"
PRIVATE_NETWORK = "kx-private"
DATA_NETWORK = "kx-data"


@dataclass(frozen=True)
class ComposeImageSet:
    """Image names used in the runtime Compose spec."""

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
            if not image or not isinstance(image, str):
                raise ComposeRenderError(f"image for {service_name} must be a non-empty string")
            kwargs[allowed[service_name]] = image

        return cls(**kwargs)

    def for_service(self, service: DockerService | str) -> str:
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
        return mapping[service_value]


@dataclass(frozen=True)
class ComposeRenderOptions:
    """Inputs required to render a safe Konnaxion runtime Compose spec."""

    instance_id: str
    host: str
    network_profile: str = enum_value(DEFAULT_NETWORK_PROFILE)
    exposure_mode: str = enum_value(DEFAULT_EXPOSURE_MODE)
    public_mode_enabled: bool = False
    public_mode_expires_at: str | None = None
    image_map: Mapping[str, str] | None = None
    include_flower: bool = False
    bind_http: bool = True
    bind_https: bool = True
    allow_http_on_local_only: bool = False

    def normalized(self) -> "ComposeRenderOptions":
        instance_id = validate_safe_id(self.instance_id, field_name="instance_id")
        network_profile = enum_value(self.network_profile)
        exposure_mode = enum_value(self.exposure_mode)

        if network_profile not in {enum_value(item) for item in NetworkProfile}:
            raise ComposeRenderError(f"invalid network_profile: {network_profile}")

        if exposure_mode not in {enum_value(item) for item in ExposureMode}:
            raise ComposeRenderError(f"invalid exposure_mode: {exposure_mode}")

        if self.public_mode_enabled and not self.public_mode_expires_at:
            raise ComposeRenderError(
                "public_mode_expires_at is required when public_mode_enabled=True"
            )

        if not self.host:
            raise ComposeRenderError("host must not be empty")

        return ComposeRenderOptions(
            instance_id=instance_id,
            host=self.host,
            network_profile=network_profile,
            exposure_mode=exposure_mode,
            public_mode_enabled=self.public_mode_enabled,
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


def enum_value(value: Any) -> str:
    """Return the string value for StrEnum/Enum/string inputs."""
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def require_yaml() -> None:
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


def container_name(instance_id: str, service: DockerService | str) -> str:
    """Return a deterministic container name."""
    instance_id = validate_safe_id(instance_id, field_name="instance_id")
    service_name = enum_value(service)
    if service_name not in CANONICAL_DOCKER_SERVICES:
        raise ComposeRenderError(f"non-canonical service name: {service_name}")
    return f"kx-{instance_id}-{service_name}"


def env_file_path(instance_id: str, filename: str) -> str:
    return str(instance_env_file(instance_id, filename))


def service_log_dir(instance_id: str, service: DockerService | str) -> str:
    service_name = enum_value(service)
    return str(assert_under_root(instance_logs_dir(instance_id) / service_name))


def traefik_dynamic_file(instance_id: str) -> Path:
    return assert_under_root(instance_state_dir(instance_id) / TRAEFIK_DYNAMIC_FILENAME)


def port_bindings_for_profile(options: ComposeRenderOptions) -> list[str]:
    """
    Return safe Traefik port bindings for the selected network profile.

    Only 80/443 are ever returned. Internal service ports are never published.
    """
    options = options.normalized()

    http_port = int(ALLOWED_ENTRY_PORTS["http_redirect"])
    https_port = int(ALLOWED_ENTRY_PORTS["https"])

    bindings: list[str] = []

    if options.network_profile == NetworkProfile.OFFLINE.value:
        return bindings

    if options.network_profile == NetworkProfile.LOCAL_ONLY.value:
        if options.bind_http and options.allow_http_on_local_only:
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
        # Tunnel implementations should connect to Traefik over the private
        # Docker network or localhost-only adapter. Do not publish arbitrary
        # public ports from Compose here.
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
                        "servers": [{"url": f"http://{DockerService.FRONTEND_NEXT.value}:3000"}]
                    }
                },
                "django-api": {
                    "loadBalancer": {
                        "servers": [{"url": f"http://{DockerService.DJANGO_API.value}:5000"}]
                    }
                },
                "media-nginx": {
                    "loadBalancer": {
                        "servers": [{"url": f"http://{DockerService.MEDIA_NGINX.value}:80"}]
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

    state_dir = str(instance_state_dir(options.instance_id))
    media_dir = str(instance_media_dir(options.instance_id))
    postgres_dir = str(instance_postgres_dir(options.instance_id))
    redis_dir = str(instance_redis_dir(options.instance_id))

    services: dict[str, Any] = {}

    traefik = base_service_defaults(options.instance_id, DockerService.TRAEFIK)
    traefik.update(
        {
            "image": images.for_service(DockerService.TRAEFIK),
            "command": [
                "--api.dashboard=false",
                "--providers.docker=false",
                "--providers.file.directory=/etc/traefik/dynamic",
                "--providers.file.watch=true",
                "--entrypoints.web.address=:80",
                "--entrypoints.websecure.address=:443",
                "--entrypoints.web.http.redirections.entrypoint.to=websecure",
                "--entrypoints.web.http.redirections.entrypoint.scheme=https",
                "--log.level=INFO",
            ],
            "ports": port_bindings_for_profile(options),
            "volumes": [
                f"{traefik_dynamic_file(options.instance_id)}:/etc/traefik/dynamic/konnaxion.yml:ro",
                f"{state_dir}/certs:/certs:ro",
            ],
            "networks": [PUBLIC_NETWORK, PRIVATE_NETWORK],
            "depends_on": [
                DockerService.FRONTEND_NEXT.value,
                DockerService.DJANGO_API.value,
                DockerService.MEDIA_NGINX.value,
            ],
            "healthcheck": {
                "test": ["CMD", "traefik", "healthcheck", "--ping"],
                "interval": "30s",
                "timeout": "5s",
                "retries": 5,
            },
        }
    )
    services[DockerService.TRAEFIK.value] = traefik

    frontend = base_service_defaults(options.instance_id, DockerService.FRONTEND_NEXT)
    frontend.update(
        {
            "image": images.for_service(DockerService.FRONTEND_NEXT),
            "env_file": [env_file_path(options.instance_id, "frontend.env")],
            "expose": ["3000"],
            "depends_on": [DockerService.DJANGO_API.value],
            "healthcheck": {
                "test": ["CMD-SHELL", "wget -qO- http://127.0.0.1:3000/ >/dev/null 2>&1 || exit 1"],
                "interval": "30s",
                "timeout": "5s",
                "retries": 5,
            },
        }
    )
    services[DockerService.FRONTEND_NEXT.value] = frontend

    django = base_service_defaults(options.instance_id, DockerService.DJANGO_API)
    django.update(
        {
            "image": images.for_service(DockerService.DJANGO_API),
            "env_file": [
                env_file_path(options.instance_id, "django.env"),
                env_file_path(options.instance_id, "postgres.env"),
                env_file_path(options.instance_id, "redis.env"),
            ],
            "expose": ["5000"],
            "volumes": [
                f"{media_dir}:/app/media",
                f"{service_log_dir(options.instance_id, DockerService.DJANGO_API)}:/app/logs",
            ],
            "depends_on": {
                DockerService.POSTGRES.value: {"condition": "service_healthy"},
                DockerService.REDIS.value: {"condition": "service_healthy"},
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "curl -fsS http://127.0.0.1:5000/api/health/ || exit 1"],
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
            "env_file": [env_file_path(options.instance_id, "postgres.env")],
            "expose": ["5432"],
            "volumes": [f"{postgres_dir}:/var/lib/postgresql/data"],
            "networks": [DATA_NETWORK],
            "healthcheck": {
                "test": ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER:-konnaxion} -d $${POSTGRES_DB:-konnaxion}"],
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
            "expose": ["6379"],
            "volumes": [f"{redis_dir}:/data"],
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
            "command": ["celery", "-A", "config.celery_app", "worker", "-l", "INFO"],
            "env_file": [
                env_file_path(options.instance_id, "django.env"),
                env_file_path(options.instance_id, "postgres.env"),
                env_file_path(options.instance_id, "redis.env"),
            ],
            "volumes": [
                f"{media_dir}:/app/media",
                f"{service_log_dir(options.instance_id, DockerService.CELERYWORKER)}:/app/logs",
            ],
            "depends_on": {
                DockerService.POSTGRES.value: {"condition": "service_healthy"},
                DockerService.REDIS.value: {"condition": "service_healthy"},
            },
        }
    )
    services[DockerService.CELERYWORKER.value] = celeryworker

    celerybeat = base_service_defaults(options.instance_id, DockerService.CELERYBEAT)
    celerybeat.update(
        {
            "image": images.for_service(DockerService.CELERYBEAT),
            "command": ["celery", "-A", "config.celery_app", "beat", "-l", "INFO"],
            "env_file": [
                env_file_path(options.instance_id, "django.env"),
                env_file_path(options.instance_id, "postgres.env"),
                env_file_path(options.instance_id, "redis.env"),
            ],
            "volumes": [
                f"{service_log_dir(options.instance_id, DockerService.CELERYBEAT)}:/app/logs",
            ],
            "depends_on": {
                DockerService.POSTGRES.value: {"condition": "service_healthy"},
                DockerService.REDIS.value: {"condition": "service_healthy"},
            },
        }
    )
    services[DockerService.CELERYBEAT.value] = celerybeat

    if options.include_flower:
        flower = base_service_defaults(options.instance_id, DockerService.FLOWER)
        flower.update(
            {
                "image": images.for_service(DockerService.FLOWER),
                "command": ["celery", "-A", "config.celery_app", "flower", "--port=5555"],
                "env_file": [
                    env_file_path(options.instance_id, "django.env"),
                    env_file_path(options.instance_id, "redis.env"),
                ],
                "expose": ["5555"],
                "depends_on": [DockerService.REDIS.value],
                "profiles": ["private-tools"],
            }
        )
        services[DockerService.FLOWER.value] = flower

    media = base_service_defaults(options.instance_id, DockerService.MEDIA_NGINX)
    media.update(
        {
            "image": images.for_service(DockerService.MEDIA_NGINX),
            "expose": ["80"],
            "volumes": [
                f"{media_dir}:/usr/share/nginx/html/media:ro",
            ],
            "healthcheck": {
                "test": ["CMD-SHELL", "wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1"],
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

    # django-api/celery need access to postgres/redis through the data network.
    for service_name in (
        DockerService.DJANGO_API.value,
        DockerService.CELERYWORKER.value,
        DockerService.CELERYBEAT.value,
    ):
        compose["services"][service_name]["networks"] = [PRIVATE_NETWORK, DATA_NETWORK]

    validate_compose_spec(compose)
    return compose


def validate_compose_spec(compose: Mapping[str, Any]) -> None:
    """
    Validate generated Compose policy before writing.

    Security Gate performs deeper validation later. This local validator catches
    renderer mistakes immediately.
    """
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
            if "/var/run/docker.sock" in volume_text:
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
            unsafe = {published, target} & set(int(p) for p in FORBIDDEN_PUBLIC_PORTS)
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
    """
    Parse Compose short-form port syntax.

    Supported examples:
        "443:443"
        "127.0.0.1:443:443"
        {"published": 443, "target": 443}
    """
    if isinstance(port, Mapping):
        return int(port.get("published")), int(port.get("target"))

    text = str(port)
    parts = text.split(":")

    if len(parts) == 2:
        return int(parts[0]), int(parts[1])

    if len(parts) == 3:
        return int(parts[1]), int(parts[2])

    raise ComposeValidationError(f"unsupported compose port syntax: {port!r}")


def render_runtime_files(options: ComposeRenderOptions) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    """
    Render Compose YAML and Traefik dynamic YAML.

    Returns:
        compose_yaml, traefik_dynamic_yaml, compose_spec, traefik_dynamic_spec
    """
    options = options.normalized()
    compose_spec = render_compose_spec(options)
    traefik_spec = render_traefik_dynamic_config(options.host)
    return yaml_dump(compose_spec), yaml_dump(traefik_spec), compose_spec, traefik_spec


def write_runtime_compose(options: ComposeRenderOptions) -> ComposeWriteResult:
    """
    Render and write docker-compose.runtime.yml and traefik-dynamic.yml.

    Files written:
        /opt/konnaxion/instances/<INSTANCE_ID>/state/docker-compose.runtime.yml
        /opt/konnaxion/instances/<INSTANCE_ID>/state/traefik-dynamic.yml
    """
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
    "env_file_path",
    "parse_compose_port",
    "port_bindings_for_profile",
    "read_compose_file",
    "render_compose_spec",
    "render_runtime_files",
    "render_traefik_dynamic_config",
    "service_log_dir",
    "traefik_dynamic_file",
    "validate_compose_file",
    "validate_compose_spec",
    "write_runtime_compose",
]
