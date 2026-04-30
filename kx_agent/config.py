"""Configuration loading for the Konnaxion Agent.

The Agent reads runtime settings from environment variables, while all
canonical defaults, paths, profiles, and policy flags come from
``kx_shared.konnaxion_constants``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from kx_shared.konnaxion_constants import (
    DEFAULT_EXPOSURE_MODE,
    DEFAULT_INSTANCE_ID,
    DEFAULT_NETWORK_PROFILE,
    DEFAULT_PUBLIC_MODE_ENABLED,
    KX_AGENT_DIR,
    KX_BACKUPS_ROOT,
    KX_CAPSULES_DIR,
    KX_ENV_DEFAULTS,
    KX_INSTANCES_DIR,
    NetworkProfile,
    ExposureMode,
    instance_backup_root,
    instance_compose_file,
    instance_env_dir,
    instance_root,
    instance_state_dir,
)


NonEmptyString = Annotated[str, Field(min_length=1)]


class AgentConfig(BaseSettings):
    """Validated Konnaxion Agent configuration.

    Values may be supplied through environment variables. Defaults are aligned
    with the canonical KX_* variables and target appliance paths.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Agent API
    # ------------------------------------------------------------------

    KX_AGENT_HOST: str = "127.0.0.1"
    KX_AGENT_PORT: int = Field(default=8714, ge=1, le=65535)
    KX_AGENT_LOG_LEVEL: str = "INFO"

    # ------------------------------------------------------------------
    # Canonical KX identity
    # ------------------------------------------------------------------

    KX_INSTANCE_ID: NonEmptyString = KX_ENV_DEFAULTS["KX_INSTANCE_ID"]
    KX_CAPSULE_ID: NonEmptyString = KX_ENV_DEFAULTS["KX_CAPSULE_ID"]
    KX_CAPSULE_VERSION: NonEmptyString = KX_ENV_DEFAULTS["KX_CAPSULE_VERSION"]
    KX_APP_VERSION: NonEmptyString = KX_ENV_DEFAULTS["KX_APP_VERSION"]
    KX_PARAM_VERSION: NonEmptyString = KX_ENV_DEFAULTS["KX_PARAM_VERSION"]

    # ------------------------------------------------------------------
    # Network and exposure
    # ------------------------------------------------------------------

    KX_NETWORK_PROFILE: NetworkProfile = DEFAULT_NETWORK_PROFILE
    KX_EXPOSURE_MODE: ExposureMode = DEFAULT_EXPOSURE_MODE
    KX_PUBLIC_MODE_ENABLED: bool = DEFAULT_PUBLIC_MODE_ENABLED
    KX_PUBLIC_MODE_EXPIRES_AT: str = ""

    # ------------------------------------------------------------------
    # Security policy
    # ------------------------------------------------------------------

    KX_REQUIRE_SIGNED_CAPSULE: bool = True
    KX_GENERATE_SECRETS_ON_INSTALL: bool = True
    KX_ALLOW_UNKNOWN_IMAGES: bool = False
    KX_ALLOW_PRIVILEGED_CONTAINERS: bool = False
    KX_ALLOW_DOCKER_SOCKET_MOUNT: bool = False
    KX_ALLOW_HOST_NETWORK: bool = False

    # ------------------------------------------------------------------
    # Backup policy
    # ------------------------------------------------------------------

    KX_BACKUP_ENABLED: bool = True
    KX_BACKUP_ROOT: Path = KX_BACKUPS_ROOT
    KX_BACKUP_RETENTION_DAYS: int = Field(default=14, ge=1)
    KX_DAILY_BACKUP_RETENTION_DAYS: int = Field(default=14, ge=1)
    KX_WEEKLY_BACKUP_RETENTION_WEEKS: int = Field(default=8, ge=1)
    KX_MONTHLY_BACKUP_RETENTION_MONTHS: int = Field(default=12, ge=1)
    KX_PRE_UPDATE_BACKUP_RETENTION_COUNT: int = Field(default=5, ge=1)
    KX_PRE_RESTORE_BACKUP_RETENTION_COUNT: int = Field(default=5, ge=1)

    # ------------------------------------------------------------------
    # Filesystem roots
    # ------------------------------------------------------------------

    KX_AGENT_DIR: Path = KX_AGENT_DIR
    KX_CAPSULES_DIR: Path = KX_CAPSULES_DIR
    KX_INSTANCES_DIR: Path = KX_INSTANCES_DIR

    # ------------------------------------------------------------------
    # Host and compose
    # ------------------------------------------------------------------

    KX_HOST: str = ""
    KX_COMPOSE_FILE: Path | None = None

    @field_validator("KX_AGENT_LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Normalize and validate the configured log level."""

        normalized = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            msg = f"KX_AGENT_LOG_LEVEL must be one of {sorted(allowed)}"
            raise ValueError(msg)
        return normalized

    @field_validator("KX_PUBLIC_MODE_EXPIRES_AT")
    @classmethod
    def validate_public_mode_expiry(cls, value: str) -> str:
        """Keep the raw timestamp string; lifecycle code validates semantics."""

        return value.strip()

    @property
    def instance_id(self) -> str:
        """Canonical active instance ID."""

        return self.KX_INSTANCE_ID or DEFAULT_INSTANCE_ID

    @property
    def is_public_mode(self) -> bool:
        """Whether this config enables any public-facing exposure mode."""

        return (
            self.KX_PUBLIC_MODE_ENABLED
            or self.KX_EXPOSURE_MODE == ExposureMode.PUBLIC
            or self.KX_NETWORK_PROFILE in {
                NetworkProfile.PUBLIC_TEMPORARY,
                NetworkProfile.PUBLIC_VPS,
            }
        )

    @property
    def capsule_file(self) -> Path:
        """Canonical stored capsule path for this config."""

        return self.KX_CAPSULES_DIR / f"{self.KX_CAPSULE_ID}.kxcap"

    @property
    def instance_root(self) -> Path:
        """Canonical instance root."""

        return instance_root(self.instance_id)

    @property
    def instance_env_dir(self) -> Path:
        """Canonical instance env directory."""

        return instance_env_dir(self.instance_id)

    @property
    def instance_state_dir(self) -> Path:
        """Canonical instance state directory."""

        return instance_state_dir(self.instance_id)

    @property
    def compose_file(self) -> Path:
        """Canonical runtime Docker Compose file path."""

        return self.KX_COMPOSE_FILE or instance_compose_file(self.instance_id)

    @property
    def backup_root(self) -> Path:
        """Canonical backup root for the active instance."""

        return instance_backup_root(self.instance_id)

    def require_public_expiry(self) -> None:
        """Raise when public temporary mode is enabled without an expiry."""

        if self.KX_NETWORK_PROFILE == NetworkProfile.PUBLIC_TEMPORARY:
            if not self.KX_PUBLIC_MODE_EXPIRES_AT:
                raise ValueError(
                    "KX_PUBLIC_MODE_EXPIRES_AT is required for public_temporary profile."
                )

    def validate_security_policy(self) -> None:
        """Reject unsafe policy combinations before lifecycle actions run."""

        unsafe_flags = {
            "KX_ALLOW_UNKNOWN_IMAGES": self.KX_ALLOW_UNKNOWN_IMAGES,
            "KX_ALLOW_PRIVILEGED_CONTAINERS": self.KX_ALLOW_PRIVILEGED_CONTAINERS,
            "KX_ALLOW_DOCKER_SOCKET_MOUNT": self.KX_ALLOW_DOCKER_SOCKET_MOUNT,
            "KX_ALLOW_HOST_NETWORK": self.KX_ALLOW_HOST_NETWORK,
        }

        enabled_unsafe_flags = [name for name, enabled in unsafe_flags.items() if enabled]
        if enabled_unsafe_flags:
            joined = ", ".join(enabled_unsafe_flags)
            raise ValueError(f"Unsafe Agent policy flags enabled: {joined}")

        if not self.KX_REQUIRE_SIGNED_CAPSULE:
            raise ValueError("KX_REQUIRE_SIGNED_CAPSULE must remain true.")

    def validate_for_startup(self) -> None:
        """Validate config before starting an instance."""

        self.require_public_expiry()
        self.validate_security_policy()

    def ensure_base_directories(self) -> None:
        """Create canonical Agent-managed directories if missing."""

        for directory in (
            self.KX_AGENT_DIR,
            self.KX_CAPSULES_DIR,
            self.KX_INSTANCES_DIR,
            self.instance_root,
            self.instance_env_dir,
            self.instance_state_dir,
            self.backup_root,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_agent_config() -> AgentConfig:
    """Return the cached Agent configuration."""

    return AgentConfig()


def reload_agent_config() -> AgentConfig:
    """Clear and reload the cached Agent configuration."""

    get_agent_config.cache_clear()
    return get_agent_config()
