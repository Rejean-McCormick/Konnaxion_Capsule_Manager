"""
Configuration for Konnaxion Capsule Manager.

The Manager is the user-facing control layer. It must not hardcode product paths,
service names, network profiles, exposure modes, ports, or KX_* defaults. Those
values come from `kx_shared.konnaxion_constants`.

This module:
- reads Manager process settings from environment variables
- exposes safe defaults for local Manager operation
- validates private-by-default posture
- builds the local Konnaxion Agent base URL
- centralizes filesystem locations used by Manager API/UI code
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from kx_shared.konnaxion_constants import (
    APP_VERSION,
    DEFAULT_EXPOSURE_MODE,
    DEFAULT_INSTANCE_ID,
    DEFAULT_NETWORK_PROFILE,
    KX_AGENT_DIR,
    KX_BACKUPS_ROOT,
    KX_CAPSULES_DIR,
    KX_ENV_DEFAULTS,
    KX_INSTANCES_DIR,
    KX_MANAGER_DIR,
    KX_ROOT,
    KX_SHARED_DIR,
    MANAGER_NAME,
    PARAM_VERSION,
)


class ManagerConfigError(ValueError):
    """Raised when Manager configuration is invalid or unsafe."""


class ManagerEnvironment(StrEnum):
    """Supported Manager runtime environments."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TEST = "test"


@dataclass(frozen=True)
class AgentClientConfig:
    """Local Konnaxion Agent client settings."""

    host: str = "127.0.0.1"
    port: int = 8765
    scheme: str = "http"
    timeout_seconds: int = 30
    token: str = ""

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    def safe_dict(self) -> dict[str, Any]:
        """Return log/UI-safe data without sensitive values."""

        return {
            "host": self.host,
            "port": self.port,
            "scheme": self.scheme,
            "timeout_seconds": self.timeout_seconds,
            "base_url": self.base_url,
            "token_configured": bool(self.token),
        }


@dataclass(frozen=True)
class ManagerPaths:
    """Filesystem paths used by the Manager."""

    root_dir: Path
    manager_dir: Path
    agent_dir: Path
    instances_dir: Path
    capsules_dir: Path
    backups_root: Path
    shared_dir: Path
    data_dir: Path
    logs_dir: Path
    state_dir: Path

    @classmethod
    def from_environment(cls) -> "ManagerPaths":
        root_dir = Path(os.getenv("KX_ROOT", str(KX_ROOT)))
        manager_dir = Path(os.getenv("KX_MANAGER_DIR", str(KX_MANAGER_DIR)))

        return cls(
            root_dir=root_dir,
            manager_dir=manager_dir,
            agent_dir=Path(os.getenv("KX_AGENT_DIR", str(KX_AGENT_DIR))),
            instances_dir=Path(os.getenv("KX_INSTANCES_DIR", str(KX_INSTANCES_DIR))),
            capsules_dir=Path(os.getenv("KX_CAPSULES_DIR", str(KX_CAPSULES_DIR))),
            backups_root=Path(os.getenv("KX_BACKUP_ROOT", str(KX_BACKUPS_ROOT))),
            shared_dir=Path(os.getenv("KX_SHARED_DIR", str(KX_SHARED_DIR))),
            data_dir=Path(os.getenv("KX_MANAGER_DATA_DIR", str(manager_dir / "data"))),
            logs_dir=Path(os.getenv("KX_MANAGER_LOGS_DIR", str(manager_dir / "logs"))),
            state_dir=Path(os.getenv("KX_MANAGER_STATE_DIR", str(manager_dir / "state"))),
        )

    def ensure(self) -> None:
        """Create Manager-owned directories."""

        for path in (
            self.root_dir,
            self.manager_dir,
            self.data_dir,
            self.logs_dir,
            self.state_dir,
            self.capsules_dir,
            self.instances_dir,
            self.backups_root,
            self.shared_dir,
        ):
            try:
                path.mkdir(parents=True, exist_ok=True)
            except PermissionError as exc:
                raise ManagerConfigError(
                    f"Permission denied while creating Manager directory: {path}"
                ) from exc

    def safe_dict(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


@dataclass(frozen=True)
class ManagerSecurityConfig:
    """Manager security and exposure posture."""

    require_agent_token: bool
    allow_public_manager_bind: bool
    allow_agent_remote_host: bool
    require_signed_capsules: bool
    generate_secrets_on_install: bool
    allow_unknown_images: bool
    allow_privileged_containers: bool
    allow_docker_socket_mount: bool
    allow_host_network: bool

    @classmethod
    def from_environment(cls) -> "ManagerSecurityConfig":
        return cls(
            require_agent_token=read_bool_env("KX_MANAGER_REQUIRE_AGENT_TOKEN", True),
            allow_public_manager_bind=read_bool_env("KX_MANAGER_ALLOW_PUBLIC_BIND", False),
            allow_agent_remote_host=read_bool_env("KX_MANAGER_ALLOW_REMOTE_AGENT", False),
            require_signed_capsules=read_bool_env(
                "KX_REQUIRE_SIGNED_CAPSULE",
                read_bool(KX_ENV_DEFAULTS["KX_REQUIRE_SIGNED_CAPSULE"]),
            ),
            generate_secrets_on_install=read_bool_env(
                "KX_GENERATE_SECRETS_ON_INSTALL",
                read_bool(KX_ENV_DEFAULTS["KX_GENERATE_SECRETS_ON_INSTALL"]),
            ),
            allow_unknown_images=read_bool_env(
                "KX_ALLOW_UNKNOWN_IMAGES",
                read_bool(KX_ENV_DEFAULTS["KX_ALLOW_UNKNOWN_IMAGES"]),
            ),
            allow_privileged_containers=read_bool_env(
                "KX_ALLOW_PRIVILEGED_CONTAINERS",
                read_bool(KX_ENV_DEFAULTS["KX_ALLOW_PRIVILEGED_CONTAINERS"]),
            ),
            allow_docker_socket_mount=read_bool_env(
                "KX_ALLOW_DOCKER_SOCKET_MOUNT",
                read_bool(KX_ENV_DEFAULTS["KX_ALLOW_DOCKER_SOCKET_MOUNT"]),
            ),
            allow_host_network=read_bool_env(
                "KX_ALLOW_HOST_NETWORK",
                read_bool(KX_ENV_DEFAULTS["KX_ALLOW_HOST_NETWORK"]),
            ),
        )

    def validate(self) -> None:
        """Reject unsafe Manager posture."""

        if not self.require_signed_capsules:
            raise ManagerConfigError("KX_REQUIRE_SIGNED_CAPSULE must be true.")

        if not self.generate_secrets_on_install:
            raise ManagerConfigError("KX_GENERATE_SECRETS_ON_INSTALL must be true.")

        unsafe_true_flags = {
            "KX_ALLOW_UNKNOWN_IMAGES": self.allow_unknown_images,
            "KX_ALLOW_PRIVILEGED_CONTAINERS": self.allow_privileged_containers,
            "KX_ALLOW_DOCKER_SOCKET_MOUNT": self.allow_docker_socket_mount,
            "KX_ALLOW_HOST_NETWORK": self.allow_host_network,
        }

        enabled_unsafe = [name for name, enabled in unsafe_true_flags.items() if enabled]

        if enabled_unsafe:
            raise ManagerConfigError(
                "Unsafe Manager runtime flags enabled: " + ", ".join(enabled_unsafe)
            )

    def safe_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ManagerConfig:
    """Complete Konnaxion Capsule Manager configuration."""

    name: str
    app_version: str
    param_version: str
    environment: ManagerEnvironment
    host: str
    port: int
    debug: bool
    log_level: str
    instance_id: str
    network_profile: str
    exposure_mode: str
    public_mode_enabled: bool
    public_mode_expires_at: str
    kx_host: str
    paths: ManagerPaths
    agent: AgentClientConfig
    security: ManagerSecurityConfig
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def base_url(self) -> str:
        scheme = "http" if self.debug else "https"
        return f"{scheme}://{self.host}:{self.port}"

    @classmethod
    def from_environment(cls) -> "ManagerConfig":
        paths = ManagerPaths.from_environment()
        agent = read_agent_config()
        security = ManagerSecurityConfig.from_environment()

        return cls(
            name=MANAGER_NAME,
            app_version=APP_VERSION,
            param_version=PARAM_VERSION,
            environment=parse_environment(
                os.getenv("KX_MANAGER_ENV", ManagerEnvironment.PRODUCTION.value)
            ),
            host=os.getenv("KX_MANAGER_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=read_int_env("KX_MANAGER_PORT", 8780),
            debug=read_bool_env("KX_MANAGER_DEBUG", False),
            log_level=os.getenv("KX_MANAGER_LOG_LEVEL", "INFO").strip().upper() or "INFO",
            instance_id=os.getenv("KX_INSTANCE_ID", DEFAULT_INSTANCE_ID).strip()
            or DEFAULT_INSTANCE_ID,
            network_profile=os.getenv(
                "KX_NETWORK_PROFILE",
                DEFAULT_NETWORK_PROFILE.value,
            ).strip()
            or DEFAULT_NETWORK_PROFILE.value,
            exposure_mode=os.getenv(
                "KX_EXPOSURE_MODE",
                DEFAULT_EXPOSURE_MODE.value,
            ).strip()
            or DEFAULT_EXPOSURE_MODE.value,
            public_mode_enabled=read_bool_env("KX_PUBLIC_MODE_ENABLED", False),
            public_mode_expires_at=os.getenv("KX_PUBLIC_MODE_EXPIRES_AT", "").strip(),
            kx_host=os.getenv("KX_HOST", "").strip(),
            paths=paths,
            agent=agent,
            security=security,
        )

    def validate(self) -> None:
        """Validate Manager configuration before API/UI startup."""

        if not self.host:
            raise ManagerConfigError("KX_MANAGER_HOST cannot be empty.")

        if not 1 <= self.port <= 65535:
            raise ManagerConfigError("KX_MANAGER_PORT must be between 1 and 65535.")

        if self.host not in {"127.0.0.1", "localhost", "::1"}:
            if not self.security.allow_public_manager_bind:
                raise ManagerConfigError(
                    "Manager must bind to localhost unless "
                    "KX_MANAGER_ALLOW_PUBLIC_BIND=true is explicitly set."
                )

        if self.agent.host not in {"127.0.0.1", "localhost", "::1"}:
            if not self.security.allow_agent_remote_host:
                raise ManagerConfigError(
                    "Manager may only talk to a local Agent unless "
                    "KX_MANAGER_ALLOW_REMOTE_AGENT=true is explicitly set."
                )

        if self.security.require_agent_token and not self.agent.token:
            raise ManagerConfigError(
                "KX_AGENT_TOKEN is required when "
                "KX_MANAGER_REQUIRE_AGENT_TOKEN=true."
            )

        if self.public_mode_enabled and not self.public_mode_expires_at:
            if self.network_profile == "public_temporary":
                raise ManagerConfigError(
                    "KX_PUBLIC_MODE_EXPIRES_AT is mandatory for temporary public mode."
                )

        self.security.validate()

    def ensure_paths(self) -> None:
        self.paths.ensure()

    def safe_dict(self) -> dict[str, Any]:
        """Return configuration data safe for logs/status endpoints."""

        return {
            "name": self.name,
            "app_version": self.app_version,
            "param_version": self.param_version,
            "environment": self.environment.value,
            "host": self.host,
            "port": self.port,
            "debug": self.debug,
            "log_level": self.log_level,
            "instance_id": self.instance_id,
            "network_profile": self.network_profile,
            "exposure_mode": self.exposure_mode,
            "public_mode_enabled": self.public_mode_enabled,
            "public_mode_expires_at": self.public_mode_expires_at,
            "kx_host": self.kx_host,
            "base_url": self.base_url,
            "paths": self.paths.safe_dict(),
            "agent": self.agent.safe_dict(),
            "security": self.security.safe_dict(),
            "extra": dict(self.extra),
        }


def load_config(*, ensure_paths: bool = False, validate: bool = True) -> ManagerConfig:
    """Load Manager configuration from the current process environment."""

    config = ManagerConfig.from_environment()

    if validate:
        config.validate()

    if ensure_paths:
        config.ensure_paths()

    return config


def read_agent_config() -> AgentClientConfig:
    """Read local Agent connection settings."""

    explicit_url = os.getenv("KX_AGENT_URL", "").strip()

    if explicit_url:
        parsed = urlparse(explicit_url)

        if not parsed.scheme or not parsed.hostname:
            raise ManagerConfigError("KX_AGENT_URL must include scheme and host.")

        return AgentClientConfig(
            host=parsed.hostname,
            port=parsed.port or default_port_for_scheme(parsed.scheme),
            scheme=parsed.scheme,
            timeout_seconds=read_int_env("KX_AGENT_TIMEOUT_SECONDS", 30),
            token=os.getenv("KX_AGENT_TOKEN", "").strip(),
        )

    return AgentClientConfig(
        host=os.getenv("KX_AGENT_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=read_int_env("KX_AGENT_PORT", 8765),
        scheme=os.getenv("KX_AGENT_SCHEME", "http").strip() or "http",
        timeout_seconds=read_int_env("KX_AGENT_TIMEOUT_SECONDS", 30),
        token=os.getenv("KX_AGENT_TOKEN", "").strip(),
    )


def default_port_for_scheme(scheme: str) -> int:
    normalized = scheme.strip().lower()

    if normalized == "https":
        return 443

    if normalized == "http":
        return 80

    raise ManagerConfigError(f"Unsupported Agent URL scheme: {scheme!r}")


def parse_environment(value: str) -> ManagerEnvironment:
    try:
        return ManagerEnvironment(value.strip().lower())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ManagerEnvironment)
        raise ManagerConfigError(
            f"Invalid KX_MANAGER_ENV={value!r}. Allowed: {allowed}."
        ) from exc


def read_int_env(key: str, default: int) -> int:
    raw = os.getenv(key)

    if raw is None or raw.strip() == "":
        return default

    try:
        return int(raw)
    except ValueError as exc:
        raise ManagerConfigError(f"{key} must be an integer.") from exc


def read_bool_env(key: str, default: bool) -> bool:
    raw = os.getenv(key)

    if raw is None or raw.strip() == "":
        return default

    return read_bool(raw, key=key)


def read_bool(value: str | bool, *, key: str = "value") -> bool:
    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()

    if normalized in {"1", "true", "yes", "y", "on"}:
        return True

    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    raise ManagerConfigError(f"{key} must be a boolean value.")


def env_template(config: ManagerConfig | None = None) -> dict[str, str]:
    """
    Return a Manager `.env` template with canonical safe defaults.

    Secrets are intentionally blank. Operators or installers should inject
    `KX_AGENT_TOKEN` through a local secret mechanism.
    """

    cfg = config or ManagerConfig.from_environment()

    return {
        "KX_MANAGER_ENV": cfg.environment.value,
        "KX_MANAGER_HOST": cfg.host,
        "KX_MANAGER_PORT": str(cfg.port),
        "KX_MANAGER_DEBUG": "true" if cfg.debug else "false",
        "KX_MANAGER_LOG_LEVEL": cfg.log_level,
        "KX_MANAGER_REQUIRE_AGENT_TOKEN": "true"
        if cfg.security.require_agent_token
        else "false",
        "KX_MANAGER_ALLOW_PUBLIC_BIND": "true"
        if cfg.security.allow_public_manager_bind
        else "false",
        "KX_MANAGER_ALLOW_REMOTE_AGENT": "true"
        if cfg.security.allow_agent_remote_host
        else "false",
        "KX_AGENT_HOST": cfg.agent.host,
        "KX_AGENT_PORT": str(cfg.agent.port),
        "KX_AGENT_SCHEME": cfg.agent.scheme,
        "KX_AGENT_TIMEOUT_SECONDS": str(cfg.agent.timeout_seconds),
        "KX_AGENT_TOKEN": "",
        "KX_INSTANCE_ID": cfg.instance_id,
        "KX_NETWORK_PROFILE": cfg.network_profile,
        "KX_EXPOSURE_MODE": cfg.exposure_mode,
        "KX_PUBLIC_MODE_ENABLED": "true" if cfg.public_mode_enabled else "false",
        "KX_PUBLIC_MODE_EXPIRES_AT": cfg.public_mode_expires_at,
        "KX_HOST": cfg.kx_host,
        "KX_ROOT": str(cfg.paths.root_dir),
        "KX_MANAGER_DIR": str(cfg.paths.manager_dir),
        "KX_AGENT_DIR": str(cfg.paths.agent_dir),
        "KX_INSTANCES_DIR": str(cfg.paths.instances_dir),
        "KX_CAPSULES_DIR": str(cfg.paths.capsules_dir),
        "KX_BACKUP_ROOT": str(cfg.paths.backups_root),
        "KX_SHARED_DIR": str(cfg.paths.shared_dir),
        "KX_REQUIRE_SIGNED_CAPSULE": "true",
        "KX_GENERATE_SECRETS_ON_INSTALL": "true",
        "KX_ALLOW_UNKNOWN_IMAGES": "false",
        "KX_ALLOW_PRIVILEGED_CONTAINERS": "false",
        "KX_ALLOW_DOCKER_SOCKET_MOUNT": "false",
        "KX_ALLOW_HOST_NETWORK": "false",
    }
