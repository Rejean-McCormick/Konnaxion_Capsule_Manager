"""
Canonical constants for Konnaxion Capsule Manager.

This module is the code-level source of truth for names, paths, profiles,
ports, services, states, security checks, environment defaults, and CLI
commands used by the Konnaxion Capsule Manager, Agent, Builder, and CLI.

Generated from the Konnaxion canonical documentation.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Final


# ---------------------------------------------------------------------------
# Product identity
# ---------------------------------------------------------------------------

PRODUCT_NAME: Final[str] = "Konnaxion"
APP_VERSION: Final[str] = "v14"
PARAM_VERSION: Final[str] = "kx-param-2026.04.30"

CAPSULE_EXTENSION: Final[str] = ".kxcap"
CAPSULE_FILENAME_PATTERN: Final[str] = "konnaxion-v14-{channel}-{date}.kxcap"

DEFAULT_CHANNEL: Final[str] = "demo"
DEFAULT_INSTANCE_ID: Final[str] = "demo-001"
DEFAULT_RELEASE_ID: Final[str] = "20260430_173000"
DEFAULT_CAPSULE_ID: Final[str] = "konnaxion-v14-demo-2026.04.30"
DEFAULT_CAPSULE_VERSION: Final[str] = "2026.04.30-demo.1"

MANAGER_NAME: Final[str] = "Konnaxion Capsule Manager"
AGENT_NAME: Final[str] = "Konnaxion Agent"
BUILDER_NAME: Final[str] = "Konnaxion Capsule Builder"
BOX_NAME: Final[str] = "Konnaxion Box"
HOST_NAME: Final[str] = "Konnaxion Host"
INSTANCE_NAME: Final[str] = "Konnaxion Instance"
CAPSULE_NAME: Final[str] = "Konnaxion Capsule"


# ---------------------------------------------------------------------------
# Canonical paths
# ---------------------------------------------------------------------------

KX_ROOT: Final[Path] = Path("/opt/konnaxion")

KX_CAPSULES_DIR: Final[Path] = KX_ROOT / "capsules"
KX_INSTANCES_DIR: Final[Path] = KX_ROOT / "instances"
KX_SHARED_DIR: Final[Path] = KX_ROOT / "shared"
KX_RELEASES_DIR: Final[Path] = KX_ROOT / "releases"
KX_MANAGER_DIR: Final[Path] = KX_ROOT / "manager"
KX_AGENT_DIR: Final[Path] = KX_ROOT / "agent"
KX_BACKUPS_ROOT: Final[Path] = KX_ROOT / "backups"

LEGACY_VPS_ROOT: Final[Path] = Path("/home/deploy/apps/Konnaxion")
LEGACY_VPS_BACKEND: Final[Path] = LEGACY_VPS_ROOT / "backend"
LEGACY_VPS_FRONTEND: Final[Path] = LEGACY_VPS_ROOT / "frontend"

LEGACY_VPS_PATHS: Final[tuple[Path, ...]] = (
    LEGACY_VPS_ROOT,
    LEGACY_VPS_BACKEND,
    LEGACY_VPS_FRONTEND,
)


def instance_root(instance_id: str) -> Path:
    """Return the canonical root directory for an instance."""
    return KX_INSTANCES_DIR / instance_id


def instance_env_dir(instance_id: str) -> Path:
    """Return the canonical env directory for an instance."""
    return instance_root(instance_id) / "env"


def instance_postgres_dir(instance_id: str) -> Path:
    """Return the canonical Postgres data directory for an instance."""
    return instance_root(instance_id) / "postgres"


def instance_redis_dir(instance_id: str) -> Path:
    """Return the canonical Redis data directory for an instance."""
    return instance_root(instance_id) / "redis"


def instance_media_dir(instance_id: str) -> Path:
    """Return the canonical media directory for an instance."""
    return instance_root(instance_id) / "media"


def instance_logs_dir(instance_id: str) -> Path:
    """Return the canonical logs directory for an instance."""
    return instance_root(instance_id) / "logs"


def instance_local_backups_dir(instance_id: str) -> Path:
    """Return the optional instance-local backup pointer/cache/state directory."""
    return instance_root(instance_id) / "backups"


def instance_state_dir(instance_id: str) -> Path:
    """Return the canonical state directory for an instance."""
    return instance_root(instance_id) / "state"


def instance_compose_file(instance_id: str) -> Path:
    """Return the generated runtime Docker Compose file path for an instance."""
    return instance_state_dir(instance_id) / "docker-compose.runtime.yml"


def instance_backup_root(instance_id: str) -> Path:
    """Return the canonical backup storage root for an instance."""
    return KX_BACKUPS_ROOT / instance_id


def instance_backup_dir(instance_id: str, backup_class: str, backup_id: str) -> Path:
    """Return the canonical backup artifact directory."""
    return instance_backup_root(instance_id) / backup_class / backup_id


def release_root(release_id: str) -> Path:
    """Return the canonical release directory."""
    return KX_RELEASES_DIR / release_id


def capsule_path(capsule_id: str) -> Path:
    """Return the canonical on-host capsule path."""
    return KX_CAPSULES_DIR / f"{capsule_id}{CAPSULE_EXTENSION}"


# ---------------------------------------------------------------------------
# Capsule internal layout
# ---------------------------------------------------------------------------

CAPSULE_ROOT_FILES: Final[tuple[str, ...]] = (
    "manifest.yaml",
    "docker-compose.capsule.yml",
    "checksums.txt",
    "signature.sig",
)

CAPSULE_ROOT_DIRS: Final[tuple[str, ...]] = (
    "images",
    "profiles",
    "env-templates",
    "migrations",
    "seed-data",
    "healthchecks",
    "policies",
    "metadata",
)

CAPSULE_REQUIRED_ROOT_ENTRIES: Final[tuple[str, ...]] = (
    *CAPSULE_ROOT_FILES,
    *CAPSULE_ROOT_DIRS,
)

CAPSULE_FORBIDDEN_SECRET_LABELS: Final[tuple[str, ...]] = (
    "DJANGO_SECRET_KEY",
    "POSTGRES_PASSWORD",
    "DATABASE_URL",
    "SSH private key",
    "API token",
    "Git token",
    "provider token",
    "unencrypted production DB dump",
    "complete .env file containing secrets",
    "private certificate key",
)


# ---------------------------------------------------------------------------
# Network profiles and exposure modes
# ---------------------------------------------------------------------------

class NetworkProfile(StrEnum):
    """Canonical Konnaxion network profiles."""

    LOCAL_ONLY = "local_only"
    INTRANET_PRIVATE = "intranet_private"
    PRIVATE_TUNNEL = "private_tunnel"
    PUBLIC_TEMPORARY = "public_temporary"
    PUBLIC_VPS = "public_vps"
    OFFLINE = "offline"


class ExposureMode(StrEnum):
    """Canonical Konnaxion exposure modes."""

    PRIVATE = "private"
    LAN = "lan"
    VPN = "vpn"
    TEMPORARY_TUNNEL = "temporary_tunnel"
    PUBLIC = "public"


DEFAULT_NETWORK_PROFILE: Final[NetworkProfile] = NetworkProfile.INTRANET_PRIVATE
DEFAULT_EXPOSURE_MODE: Final[ExposureMode] = ExposureMode.PRIVATE
DEFAULT_PUBLIC_MODE_ENABLED: Final[bool] = False

CANONICAL_NETWORK_PROFILES: Final[tuple[str, ...]] = tuple(
    profile.value for profile in NetworkProfile
)

CANONICAL_EXPOSURE_MODES: Final[tuple[str, ...]] = tuple(
    mode.value for mode in ExposureMode
)


# ---------------------------------------------------------------------------
# Docker services
# ---------------------------------------------------------------------------

class DockerService(StrEnum):
    """Canonical Docker Compose service names."""

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


CANONICAL_DOCKER_SERVICES: Final[tuple[str, ...]] = tuple(
    service.value for service in DockerService
)

FORBIDDEN_SERVICE_ALIASES: Final[dict[str, str]] = {
    "backend": DockerService.DJANGO_API.value,
    "api": DockerService.DJANGO_API.value,
    "web": DockerService.FRONTEND_NEXT.value,
    "next": DockerService.FRONTEND_NEXT.value,
    "frontend": DockerService.FRONTEND_NEXT.value,
    "db": DockerService.POSTGRES.value,
    "database": DockerService.POSTGRES.value,
    "cache": DockerService.REDIS.value,
    "worker": DockerService.CELERYWORKER.value,
    "scheduler": DockerService.CELERYBEAT.value,
    "media": DockerService.MEDIA_NGINX.value,
    "agent": DockerService.KX_AGENT.value,
}


# ---------------------------------------------------------------------------
# Ports and public surfaces
# ---------------------------------------------------------------------------

ALLOWED_ENTRY_PORTS: Final[dict[str, int]] = {
    "https": 443,
    "http_redirect": 80,
    "ssh_admin_restricted": 22,
}

INTERNAL_ONLY_PORTS: Final[dict[str, int]] = {
    DockerService.FRONTEND_NEXT.value: 3000,
    DockerService.DJANGO_API.value: 5000,
    DockerService.POSTGRES.value: 5432,
    DockerService.REDIS.value: 6379,
    DockerService.FLOWER.value: 5555,
    "django_dev_server": 8000,
}

FORBIDDEN_PUBLIC_PORTS: Final[frozenset[int]] = frozenset(INTERNAL_ONLY_PORTS.values())

FORBIDDEN_PUBLIC_SURFACES: Final[tuple[str, ...]] = (
    "Next.js direct port",
    "Django direct port",
    "PostgreSQL",
    "Redis",
    "Flower/dashboard",
    "Docker daemon TCP socket",
    "Docker socket mount into app containers",
)


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

ROUTES: Final[dict[str, str]] = {
    "/": DockerService.FRONTEND_NEXT.value,
    "/api/": DockerService.DJANGO_API.value,
    "/admin/": DockerService.DJANGO_API.value,
    "/media/": DockerService.MEDIA_NGINX.value,
}


# ---------------------------------------------------------------------------
# Runtime environment variables
# ---------------------------------------------------------------------------

DJANGO_ENV_DEFAULTS: Final[dict[str, str]] = {
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "DJANGO_SECRET_KEY": "<GENERATED_ON_INSTALL>",
    "DJANGO_DEBUG": "False",
    "DJANGO_ALLOWED_HOSTS": "<GENERATED_FROM_PROFILE>",
    "DJANGO_ADMIN_URL": "admin/",
    "USE_DOCKER": "yes",
    "SENTRY_DSN": "",
}

DATABASE_ENV_DEFAULTS: Final[dict[str, str]] = {
    "DATABASE_URL": "postgres://konnaxion:<POSTGRES_PASSWORD>@postgres:5432/konnaxion",
    "POSTGRES_HOST": DockerService.POSTGRES.value,
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "konnaxion",
    "POSTGRES_USER": "konnaxion",
    "POSTGRES_PASSWORD": "<GENERATED_ON_INSTALL>",
}

REDIS_ENV_DEFAULTS: Final[dict[str, str]] = {
    "REDIS_URL": "redis://redis:6379/0",
    "CELERY_BROKER_URL": "redis://redis:6379/0",
    "CELERY_RESULT_BACKEND": "redis://redis:6379/0",
}

FRONTEND_ENV_DEFAULTS: Final[dict[str, str]] = {
    "NEXT_PUBLIC_API_BASE": "https://<PUBLIC_OR_PRIVATE_HOST>/api",
    "NEXT_PUBLIC_BACKEND_BASE": "https://<PUBLIC_OR_PRIVATE_HOST>",
    "NEXT_TELEMETRY_DISABLED": "1",
    "NODE_OPTIONS": "--max-old-space-size=4096",
}

KX_ENV_DEFAULTS: Final[dict[str, str]] = {
    "KX_INSTANCE_ID": DEFAULT_INSTANCE_ID,
    "KX_CAPSULE_ID": DEFAULT_CAPSULE_ID,
    "KX_CAPSULE_VERSION": DEFAULT_CAPSULE_VERSION,
    "KX_APP_VERSION": APP_VERSION,
    "KX_PARAM_VERSION": PARAM_VERSION,
    "KX_NETWORK_PROFILE": DEFAULT_NETWORK_PROFILE.value,
    "KX_EXPOSURE_MODE": DEFAULT_EXPOSURE_MODE.value,
    "KX_PUBLIC_MODE_ENABLED": "false",
    "KX_PUBLIC_MODE_DURATION_HOURS": "",
    "KX_PUBLIC_MODE_EXPIRES_AT": "",
    "KX_REQUIRE_SIGNED_CAPSULE": "true",
    "KX_GENERATE_SECRETS_ON_INSTALL": "true",
    "KX_ALLOW_UNKNOWN_IMAGES": "false",
    "KX_ALLOW_PRIVILEGED_CONTAINERS": "false",
    "KX_ALLOW_DOCKER_SOCKET_MOUNT": "false",
    "KX_ALLOW_HOST_NETWORK": "false",
    "KX_BACKUP_ENABLED": "true",
    "KX_BACKUP_ROOT": str(KX_BACKUPS_ROOT),
    "KX_BACKUP_RETENTION_DAYS": "14",
    "KX_DAILY_BACKUP_RETENTION_DAYS": "14",
    "KX_WEEKLY_BACKUP_RETENTION_WEEKS": "8",
    "KX_MONTHLY_BACKUP_RETENTION_MONTHS": "12",
    "KX_PRE_UPDATE_BACKUP_RETENTION_COUNT": "5",
    "KX_PRE_RESTORE_BACKUP_RETENTION_COUNT": "5",
    "KX_COMPOSE_FILE": str(instance_compose_file("<KX_INSTANCE_ID>")),
    "KX_BACKUP_DIR": str(
        KX_BACKUPS_ROOT / "<KX_INSTANCE_ID>" / "<BACKUP_CLASS>" / "<BACKUP_ID>"
    ),
    "KX_HOST": "<GENERATED_FROM_PROFILE>",
}

ALL_ENV_DEFAULTS: Final[dict[str, str]] = {
    **DJANGO_ENV_DEFAULTS,
    **DATABASE_ENV_DEFAULTS,
    **REDIS_ENV_DEFAULTS,
    **FRONTEND_ENV_DEFAULTS,
    **KX_ENV_DEFAULTS,
}


# ---------------------------------------------------------------------------
# Security Gate
# ---------------------------------------------------------------------------

class SecurityGateStatus(StrEnum):
    """Canonical Security Gate result statuses."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL_BLOCKING = "FAIL_BLOCKING"
    SKIPPED = "SKIPPED"
    UNKNOWN = "UNKNOWN"


class SecurityGateCheck(StrEnum):
    """Canonical Security Gate checks."""

    CAPSULE_SIGNATURE = "capsule_signature"
    IMAGE_CHECKSUMS = "image_checksums"
    MANIFEST_SCHEMA = "manifest_schema"
    SECRETS_PRESENT = "secrets_present"
    SECRETS_NOT_DEFAULT = "secrets_not_default"
    FIREWALL_ENABLED = "firewall_enabled"
    DANGEROUS_PORTS_BLOCKED = "dangerous_ports_blocked"
    POSTGRES_NOT_PUBLIC = "postgres_not_public"
    REDIS_NOT_PUBLIC = "redis_not_public"
    DOCKER_SOCKET_NOT_MOUNTED = "docker_socket_not_mounted"
    NO_PRIVILEGED_CONTAINERS = "no_privileged_containers"
    NO_HOST_NETWORK = "no_host_network"
    ALLOWED_IMAGES_ONLY = "allowed_images_only"
    ADMIN_SURFACE_PRIVATE = "admin_surface_private"
    BACKUP_CONFIGURED = "backup_configured"


CANONICAL_SECURITY_GATE_STATUSES: Final[tuple[str, ...]] = tuple(
    status.value for status in SecurityGateStatus
)

CANONICAL_SECURITY_GATE_CHECKS: Final[tuple[str, ...]] = tuple(
    check.value for check in SecurityGateCheck
)

BLOCKING_SECURITY_CHECKS: Final[frozenset[SecurityGateCheck]] = frozenset(
    {
        SecurityGateCheck.CAPSULE_SIGNATURE,
        SecurityGateCheck.IMAGE_CHECKSUMS,
        SecurityGateCheck.MANIFEST_SCHEMA,
        SecurityGateCheck.SECRETS_PRESENT,
        SecurityGateCheck.SECRETS_NOT_DEFAULT,
        SecurityGateCheck.DANGEROUS_PORTS_BLOCKED,
        SecurityGateCheck.POSTGRES_NOT_PUBLIC,
        SecurityGateCheck.REDIS_NOT_PUBLIC,
        SecurityGateCheck.DOCKER_SOCKET_NOT_MOUNTED,
        SecurityGateCheck.NO_PRIVILEGED_CONTAINERS,
        SecurityGateCheck.NO_HOST_NETWORK,
        SecurityGateCheck.ALLOWED_IMAGES_ONLY,
    }
)


# ---------------------------------------------------------------------------
# Lifecycle states
# ---------------------------------------------------------------------------

class InstanceState(StrEnum):
    """Canonical Konnaxion Instance states."""

    CREATED = "created"
    IMPORTING = "importing"
    VERIFYING = "verifying"
    READY = "ready"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    UPDATING = "updating"
    ROLLING_BACK = "rolling_back"
    DEGRADED = "degraded"
    FAILED = "failed"
    SECURITY_BLOCKED = "security_blocked"


class BackupStatus(StrEnum):
    """Canonical backup resource statuses."""

    CREATED = "created"
    RUNNING = "running"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    FAILED = "failed"
    EXPIRED = "expired"
    DELETED = "deleted"
    QUARANTINED = "quarantined"


class RestoreStatus(StrEnum):
    """Canonical restore resource statuses."""

    PLANNED = "planned"
    PREFLIGHT = "preflight"
    CREATING_PRE_RESTORE_BACKUP = "creating_pre_restore_backup"
    RESTORING_DATABASE = "restoring_database"
    RESTORING_MEDIA = "restoring_media"
    RUNNING_MIGRATIONS = "running_migrations"
    RUNNING_SECURITY_GATE = "running_security_gate"
    RUNNING_HEALTHCHECKS = "running_healthchecks"
    RESTORED = "restored"
    DEGRADED = "degraded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class RollbackStatus(StrEnum):
    """Canonical rollback resource statuses."""

    PLANNED = "planned"
    RUNNING = "running"
    CAPSULE_REPOINTED = "capsule_repointed"
    DATA_RESTORED = "data_restored"
    HEALTHCHECKING = "healthchecking"
    COMPLETED = "completed"
    FAILED = "failed"


CANONICAL_INSTANCE_STATES: Final[tuple[str, ...]] = tuple(
    state.value for state in InstanceState
)

CANONICAL_BACKUP_STATUSES: Final[tuple[str, ...]] = tuple(
    status.value for status in BackupStatus
)

CANONICAL_RESTORE_STATUSES: Final[tuple[str, ...]] = tuple(
    status.value for status in RestoreStatus
)

CANONICAL_ROLLBACK_STATUSES: Final[tuple[str, ...]] = tuple(
    status.value for status in RollbackStatus
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

CLI_NAME: Final[str] = "kx"

PUBLIC_CLI_COMMANDS: Final[tuple[str, ...]] = (
    "kx capsule build",
    "kx capsule verify",
    "kx capsule import",
    "kx instance create",
    "kx instance start",
    "kx instance stop",
    "kx instance status",
    "kx instance logs",
    "kx instance backup",
    "kx instance restore",
    "kx instance restore-new",
    "kx instance update",
    "kx instance rollback",
    "kx instance health",
    "kx backup list",
    "kx backup verify",
    "kx backup test-restore",
    "kx security check",
    "kx network set-profile",
)

INTERNAL_AGENT_COMMANDS: Final[tuple[str, ...]] = (
    "kx backup preflight",
    "kx backup postflight",
    "kx instance stop-services",
    "kx instance fix-permissions",
)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def is_canonical_network_profile(value: str) -> bool:
    """Return True if value is a canonical network profile."""
    return value in CANONICAL_NETWORK_PROFILES


def is_canonical_exposure_mode(value: str) -> bool:
    """Return True if value is a canonical exposure mode."""
    return value in CANONICAL_EXPOSURE_MODES


def is_canonical_service(value: str) -> bool:
    """Return True if value is a canonical Docker service name."""
    return value in CANONICAL_DOCKER_SERVICES


def is_forbidden_public_port(port: int) -> bool:
    """Return True if port must never be publicly exposed."""
    return port in FORBIDDEN_PUBLIC_PORTS


def is_public_mode(profile: NetworkProfile | str, exposure: ExposureMode | str) -> bool:
    """Return True if the profile or exposure implies public access."""
    profile_value = profile.value if isinstance(profile, NetworkProfile) else profile
    exposure_value = exposure.value if isinstance(exposure, ExposureMode) else exposure
    return (
        profile_value in {NetworkProfile.PUBLIC_TEMPORARY.value, NetworkProfile.PUBLIC_VPS.value}
        or exposure_value in {ExposureMode.TEMPORARY_TUNNEL.value, ExposureMode.PUBLIC.value}
    )


def normalize_service_name(value: str) -> str:
    """
    Normalize legacy/inconsistent service aliases to canonical service names.

    Unknown values are returned unchanged so callers can decide whether to reject them.
    """
    return FORBIDDEN_SERVICE_ALIASES.get(value, value)


def require_public_expiration(public_mode_enabled: bool, expires_at: str | None) -> None:
    """
    Validate that public mode has an expiration.

    Raises:
        ValueError: if public mode is enabled and expires_at is empty.
    """
    if public_mode_enabled and not expires_at:
        raise ValueError("KX_PUBLIC_MODE_EXPIRES_AT is mandatory when public mode is enabled.")


__all__ = [
    "AGENT_NAME",
    "ALL_ENV_DEFAULTS",
    "ALLOWED_ENTRY_PORTS",
    "APP_VERSION",
    "BLOCKING_SECURITY_CHECKS",
    "BOX_NAME",
    "BUILDER_NAME",
    "CANONICAL_BACKUP_STATUSES",
    "CANONICAL_DOCKER_SERVICES",
    "CANONICAL_EXPOSURE_MODES",
    "CANONICAL_INSTANCE_STATES",
    "CANONICAL_NETWORK_PROFILES",
    "CANONICAL_RESTORE_STATUSES",
    "CANONICAL_ROLLBACK_STATUSES",
    "CANONICAL_SECURITY_GATE_CHECKS",
    "CANONICAL_SECURITY_GATE_STATUSES",
    "CAPSULE_EXTENSION",
    "CAPSULE_FILENAME_PATTERN",
    "CAPSULE_FORBIDDEN_SECRET_LABELS",
    "CAPSULE_NAME",
    "CAPSULE_REQUIRED_ROOT_ENTRIES",
    "CAPSULE_ROOT_DIRS",
    "CAPSULE_ROOT_FILES",
    "CLI_NAME",
    "DATABASE_ENV_DEFAULTS",
    "DEFAULT_CAPSULE_ID",
    "DEFAULT_CAPSULE_VERSION",
    "DEFAULT_CHANNEL",
    "DEFAULT_EXPOSURE_MODE",
    "DEFAULT_INSTANCE_ID",
    "DEFAULT_NETWORK_PROFILE",
    "DEFAULT_PUBLIC_MODE_ENABLED",
    "DEFAULT_RELEASE_ID",
    "DJANGO_ENV_DEFAULTS",
    "DockerService",
    "ExposureMode",
    "FORBIDDEN_PUBLIC_PORTS",
    "FORBIDDEN_PUBLIC_SURFACES",
    "FORBIDDEN_SERVICE_ALIASES",
    "FRONTEND_ENV_DEFAULTS",
    "HOST_NAME",
    "INTERNAL_AGENT_COMMANDS",
    "INTERNAL_ONLY_PORTS",
    "INSTANCE_NAME",
    "InstanceState",
    "KX_AGENT_DIR",
    "KX_BACKUPS_ROOT",
    "KX_CAPSULES_DIR",
    "KX_ENV_DEFAULTS",
    "KX_INSTANCES_DIR",
    "KX_MANAGER_DIR",
    "KX_RELEASES_DIR",
    "KX_ROOT",
    "KX_SHARED_DIR",
    "LEGACY_VPS_BACKEND",
    "LEGACY_VPS_FRONTEND",
    "LEGACY_VPS_PATHS",
    "LEGACY_VPS_ROOT",
    "MANAGER_NAME",
    "NetworkProfile",
    "PARAM_VERSION",
    "PRODUCT_NAME",
    "PUBLIC_CLI_COMMANDS",
    "REDIS_ENV_DEFAULTS",
    "ROUTES",
    "RollbackStatus",
    "RestoreStatus",
    "SecurityGateCheck",
    "SecurityGateStatus",
    "BackupStatus",
    "capsule_path",
    "instance_backup_dir",
    "instance_backup_root",
    "instance_compose_file",
    "instance_env_dir",
    "instance_local_backups_dir",
    "instance_logs_dir",
    "instance_media_dir",
    "instance_postgres_dir",
    "instance_redis_dir",
    "instance_root",
    "instance_state_dir",
    "is_canonical_exposure_mode",
    "is_canonical_network_profile",
    "is_canonical_service",
    "is_forbidden_public_port",
    "is_public_mode",
    "normalize_service_name",
    "release_root",
    "require_public_expiration",
]
