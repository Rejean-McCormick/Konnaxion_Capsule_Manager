"""Target mode configuration for Konnaxion Capsule Manager.

Target modes answer where a capsule should run. They are not cosmetic UI
labels: each target mode controls the canonical network profile, exposure mode,
required fields, deployment flow, and safety requirements used by the Manager UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping

from kx_shared.konnaxion_constants import ExposureMode, NetworkProfile


class TargetMode(StrEnum):
    """Canonical GUI target modes."""

    LOCAL = "local"
    INTRANET = "intranet"
    TEMPORARY_PUBLIC = "temporary_public"
    DROPLET = "droplet"


DEFAULT_TARGET_MODE = TargetMode.INTRANET


class TargetConfigError(ValueError):
    """Raised when a target configuration violates the target mode contract."""


@dataclass(frozen=True, slots=True)
class TargetConfig:
    """Validated target configuration used by UI, services, and deploy flows."""

    target_mode: TargetMode
    network_profile: NetworkProfile
    exposure_mode: ExposureMode
    instance_id: str
    runtime_root: str
    capsule_dir: str
    host: str | None = None
    public_mode_expires_at: str | None = None
    confirmed: bool = False
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DropletTargetConfig(TargetConfig):
    """Validated Droplet/VPS target configuration."""

    droplet_name: str | None = None
    droplet_host: str | None = None
    droplet_user: str | None = None
    ssh_key_path: str | Path | None = None
    remote_kx_root: str | None = None
    remote_capsule_dir: str | None = None
    domain: str | None = None
    remote_agent_url: str | None = None
    ssh_port: int = 22


INSTANCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


TARGET_PROFILE_MAP: dict[TargetMode, NetworkProfile] = {
    TargetMode.LOCAL: NetworkProfile.LOCAL_ONLY,
    TargetMode.INTRANET: NetworkProfile.INTRANET_PRIVATE,
    TargetMode.TEMPORARY_PUBLIC: NetworkProfile.PUBLIC_TEMPORARY,
    TargetMode.DROPLET: NetworkProfile.PUBLIC_VPS,
}


TARGET_DEFAULT_EXPOSURE_MAP: dict[TargetMode, ExposureMode] = {
    TargetMode.LOCAL: ExposureMode.PRIVATE,
    TargetMode.INTRANET: ExposureMode.PRIVATE,
    TargetMode.TEMPORARY_PUBLIC: ExposureMode.TEMPORARY_TUNNEL,
    TargetMode.DROPLET: ExposureMode.PUBLIC,
}


TARGET_ALLOWED_EXPOSURE_MAP: dict[TargetMode, tuple[ExposureMode, ...]] = {
    TargetMode.LOCAL: (ExposureMode.PRIVATE,),
    TargetMode.INTRANET: (
        ExposureMode.PRIVATE,
        ExposureMode.LAN,
    ),
    TargetMode.TEMPORARY_PUBLIC: (ExposureMode.TEMPORARY_TUNNEL,),
    TargetMode.DROPLET: (ExposureMode.PUBLIC,),
}


TARGET_LABELS: dict[TargetMode, str] = {
    TargetMode.LOCAL: "Local",
    TargetMode.INTRANET: "Intranet",
    TargetMode.TEMPORARY_PUBLIC: "Temporary Public",
    TargetMode.DROPLET: "Droplet",
}


def normalize_target_mode(value: str | TargetMode | None) -> TargetMode:
    """Return a canonical target mode."""

    if value is None or value == "":
        return DEFAULT_TARGET_MODE

    if isinstance(value, TargetMode):
        return value

    try:
        return TargetMode(str(value))
    except ValueError as exc:
        raise TargetConfigError(f"Invalid target mode: {value!r}") from exc


def normalize_network_profile(value: str | NetworkProfile) -> NetworkProfile:
    """Return a canonical network profile."""

    if isinstance(value, NetworkProfile):
        return value

    try:
        return NetworkProfile(str(value))
    except ValueError as exc:
        raise TargetConfigError(f"Invalid network profile: {value!r}") from exc


def normalize_exposure_mode(value: str | ExposureMode) -> ExposureMode:
    """Return a canonical exposure mode."""

    if isinstance(value, ExposureMode):
        return value

    try:
        return ExposureMode(str(value))
    except ValueError as exc:
        raise TargetConfigError(f"Invalid exposure mode: {value!r}") from exc


def network_profile_for_target(target_mode: str | TargetMode | None) -> NetworkProfile:
    """Return the required network profile for a target mode."""

    mode = normalize_target_mode(target_mode)
    return TARGET_PROFILE_MAP[mode]


def exposure_mode_for_target(target_mode: str | TargetMode | None) -> ExposureMode:
    """Return the default exposure mode for a target mode."""

    mode = normalize_target_mode(target_mode)
    return TARGET_DEFAULT_EXPOSURE_MAP[mode]


def allowed_exposure_modes_for_target(
    target_mode: str | TargetMode | None,
) -> tuple[ExposureMode, ...]:
    """Return exposure modes allowed for a target mode."""

    mode = normalize_target_mode(target_mode)
    return TARGET_ALLOWED_EXPOSURE_MAP[mode]


def target_mode_label(target_mode: str | TargetMode | None) -> str:
    """Return a human-readable label for a target mode."""

    mode = normalize_target_mode(target_mode)
    return TARGET_LABELS[mode]


def build_target_config(
    *,
    target_mode: str | TargetMode | None = DEFAULT_TARGET_MODE,
    instance_id: str,
    runtime_root: str,
    capsule_dir: str,
    host: str | None = None,
    network_profile: str | NetworkProfile | None = None,
    exposure_mode: str | ExposureMode | None = None,
    public_mode_expires_at: str | None = None,
    confirmed: bool = False,
    **extra: Any,
) -> TargetConfig:
    """Build and validate a target configuration.

    Explicit profile and exposure values are accepted only when they are valid
    for the selected target mode.
    """

    mode = normalize_target_mode(target_mode)

    profile = (
        normalize_network_profile(network_profile)
        if network_profile is not None
        else network_profile_for_target(mode)
    )

    exposure = (
        normalize_exposure_mode(exposure_mode)
        if exposure_mode is not None
        else exposure_mode_for_target(mode)
    )

    if mode == TargetMode.DROPLET:
        config: TargetConfig = DropletTargetConfig(
            target_mode=mode,
            network_profile=profile,
            exposure_mode=exposure,
            instance_id=instance_id,
            runtime_root=runtime_root,
            capsule_dir=capsule_dir,
            host=host,
            public_mode_expires_at=public_mode_expires_at,
            confirmed=confirmed,
            extra=dict(extra),
            droplet_name=_optional_str(extra.get("droplet_name")),
            droplet_host=_optional_str(extra.get("droplet_host") or host),
            droplet_user=_optional_str(extra.get("droplet_user")),
            ssh_key_path=extra.get("ssh_key_path"),
            remote_kx_root=_optional_str(extra.get("remote_kx_root") or runtime_root),
            remote_capsule_dir=_optional_str(extra.get("remote_capsule_dir") or capsule_dir),
            domain=_optional_str(extra.get("domain")),
            remote_agent_url=_optional_str(extra.get("remote_agent_url")),
            ssh_port=int(extra.get("ssh_port") or 22),
        )
    else:
        config = TargetConfig(
            target_mode=mode,
            network_profile=profile,
            exposure_mode=exposure,
            instance_id=instance_id,
            runtime_root=runtime_root,
            capsule_dir=capsule_dir,
            host=host,
            public_mode_expires_at=public_mode_expires_at,
            confirmed=confirmed,
            extra=dict(extra),
        )

    validate_target_config(config)
    return config


def validate_target_config(config: TargetConfig) -> None:
    """Validate a target configuration against canonical target mode rules."""

    mode = normalize_target_mode(config.target_mode)
    profile = normalize_network_profile(config.network_profile)
    exposure = normalize_exposure_mode(config.exposure_mode)

    expected_profile = network_profile_for_target(mode)
    if profile != expected_profile:
        raise TargetConfigError(
            f"Target mode {mode.value!r} requires network profile "
            f"{expected_profile.value!r}, got {profile.value!r}."
        )

    allowed_exposures = allowed_exposure_modes_for_target(mode)
    if exposure not in allowed_exposures:
        allowed = ", ".join(item.value for item in allowed_exposures)
        raise TargetConfigError(
            f"Target mode {mode.value!r} does not allow exposure mode "
            f"{exposure.value!r}. Allowed: {allowed}."
        )

    _validate_common_fields(config)

    if mode == TargetMode.LOCAL:
        _validate_local(config)
    elif mode == TargetMode.INTRANET:
        _validate_intranet(config)
    elif mode == TargetMode.TEMPORARY_PUBLIC:
        _validate_temporary_public(config)
    elif mode == TargetMode.DROPLET:
        _validate_droplet(config)
    else:
        raise TargetConfigError(f"Unsupported target mode: {mode.value!r}")


def target_env(config: TargetConfig) -> dict[str, str]:
    """Return canonical KX_TARGET_* environment values for a target."""

    validate_target_config(config)

    env = {
        "KX_TARGET_MODE": config.target_mode.value,
        "KX_TARGET_PROFILE": config.network_profile.value,
        "KX_TARGET_EXPOSURE": config.exposure_mode.value,
        "KX_TARGET_NAME": target_mode_label(config.target_mode),
        "KX_TARGET_RUNTIME_ROOT": config.runtime_root,
        "KX_TARGET_CAPSULE_DIR": config.capsule_dir,
        "KX_TARGET_INSTANCE_ID": config.instance_id,
    }

    if config.host:
        env["KX_TARGET_HOST"] = config.host

    if config.public_mode_expires_at:
        env["KX_PUBLIC_MODE_EXPIRES_AT"] = config.public_mode_expires_at

    for key in (
        "droplet_name",
        "droplet_host",
        "droplet_user",
        "ssh_key_path",
        "ssh_port",
        "remote_kx_root",
        "remote_capsule_dir",
        "domain",
        "remote_agent_url",
    ):
        value = _target_field(config, key)
        if value is None or value == "":
            continue
        env[_extra_env_key(key)] = str(value)

    for key, value in config.extra.items():
        if value is None or value == "":
            continue

        env_key = _extra_env_key(key)
        env[env_key] = str(value)

    return env


def target_summary(config: TargetConfig) -> dict[str, Any]:
    """Return a UI-safe summary of the selected target."""

    validate_target_config(config)

    summary: dict[str, Any] = {
        "target_mode": config.target_mode.value,
        "target_label": target_mode_label(config.target_mode),
        "network_profile": config.network_profile.value,
        "exposure_mode": config.exposure_mode.value,
        "instance_id": config.instance_id,
        "runtime_root": config.runtime_root,
        "capsule_dir": config.capsule_dir,
        "host": config.host,
        "public_mode_enabled": config.target_mode
        in {TargetMode.TEMPORARY_PUBLIC, TargetMode.DROPLET},
        "public_mode_expires_at": config.public_mode_expires_at,
        "confirmed": config.confirmed,
    }

    if normalize_target_mode(config.target_mode) == TargetMode.DROPLET:
        summary.update(
            {
                "droplet_name": _target_field(config, "droplet_name"),
                "droplet_host": _target_field(config, "droplet_host", config.host),
                "droplet_user": _target_field(config, "droplet_user"),
                "ssh_key_path": str(_target_field(config, "ssh_key_path") or ""),
                "ssh_port": _target_field(config, "ssh_port", 22),
                "remote_kx_root": _target_field(config, "remote_kx_root"),
                "remote_capsule_dir": _target_field(config, "remote_capsule_dir"),
                "domain": _target_field(config, "domain"),
                "remote_agent_url": _target_field(config, "remote_agent_url"),
            }
        )

    return summary


def _validate_common_fields(config: TargetConfig) -> None:
    if not config.instance_id or not INSTANCE_ID_PATTERN.fullmatch(config.instance_id):
        raise TargetConfigError(
            "instance_id must be 1-128 characters and contain only letters, "
            "numbers, dots, underscores, and hyphens."
        )

    if not str(config.runtime_root).strip():
        raise TargetConfigError("runtime_root is required.")

    if not str(config.capsule_dir).strip():
        raise TargetConfigError("capsule_dir is required.")


def _validate_local(config: TargetConfig) -> None:
    if config.public_mode_expires_at:
        raise TargetConfigError("local target must not set public_mode_expires_at.")

    if config.confirmed:
        raise TargetConfigError("local target must not require public confirmation.")

    _reject_droplet_fields(config)


def _validate_intranet(config: TargetConfig) -> None:
    if config.public_mode_expires_at:
        raise TargetConfigError("intranet target must not set public_mode_expires_at.")

    if config.confirmed:
        raise TargetConfigError("intranet target must not require public confirmation.")

    _reject_droplet_fields(config)


def _validate_temporary_public(config: TargetConfig) -> None:
    if not config.public_mode_expires_at:
        raise TargetConfigError(
            "temporary_public target requires public_mode_expires_at."
        )

    if not config.confirmed:
        raise TargetConfigError("temporary_public target requires confirmation.")

    _reject_droplet_fields(config)


def _validate_droplet(config: TargetConfig) -> None:
    if not config.confirmed:
        raise TargetConfigError("droplet target requires confirmation.")

    droplet_host = str(_target_field(config, "droplet_host", config.host) or "").strip()
    droplet_user = str(_target_field(config, "droplet_user") or "").strip()
    ssh_key_path = _target_field(config, "ssh_key_path")
    remote_kx_root = str(_target_field(config, "remote_kx_root") or "").strip()
    remote_capsule_dir = str(_target_field(config, "remote_capsule_dir") or "").strip()

    if not droplet_host:
        raise TargetConfigError("droplet target requires droplet_host or host.")

    if not droplet_user:
        raise TargetConfigError("droplet target requires droplet_user.")

    if not ssh_key_path:
        raise TargetConfigError("droplet target requires ssh_key_path.")

    ssh_path = Path(str(ssh_key_path)).expanduser()
    if not ssh_path.exists() or not ssh_path.is_file():
        raise TargetConfigError("droplet target requires an existing ssh_key_path file.")

    if not remote_kx_root:
        raise TargetConfigError("droplet target requires remote_kx_root.")

    if not remote_capsule_dir:
        raise TargetConfigError("droplet target requires remote_capsule_dir.")

    if not _is_posix_path_under(remote_capsule_dir, remote_kx_root):
        raise TargetConfigError("remote_capsule_dir must be inside remote_kx_root.")

    ssh_port = int(_target_field(config, "ssh_port", 22) or 22)
    if not 1 <= ssh_port <= 65535:
        raise TargetConfigError("ssh_port must be between 1 and 65535.")


def _reject_droplet_fields(config: TargetConfig) -> None:
    forbidden = {
        "droplet_name",
        "droplet_host",
        "droplet_user",
        "ssh_key_path",
        "ssh_port",
        "remote_kx_root",
        "remote_capsule_dir",
        "domain",
        "remote_agent_url",
    }

    present = sorted(
        key
        for key in forbidden
        if _target_field(config, key) not in {None, ""}
    )

    if present:
        raise TargetConfigError(
            f"{config.target_mode.value} target must not include Droplet fields: "
            f"{', '.join(present)}."
        )


def _target_field(config: TargetConfig, key: str, default: Any = None) -> Any:
    value = getattr(config, key, None)

    if value is not None and value != "":
        return value

    return config.extra.get(key, default)


def _is_posix_path_under(child: str, parent: str) -> bool:
    child_path = PurePosixPath(child)
    parent_path = PurePosixPath(parent)

    try:
        child_path.relative_to(parent_path)
    except ValueError:
        return False

    return True


def _extra_env_key(key: str) -> str:
    normalized = key.strip().upper().replace("-", "_")

    if normalized.startswith("KX_TARGET_") or normalized.startswith("KX_DROPLET_"):
        return normalized

    droplet_keys = {
        "DROPLET_NAME",
        "DROPLET_HOST",
        "DROPLET_USER",
        "SSH_KEY_PATH",
        "SSH_PORT",
        "REMOTE_KX_ROOT",
        "REMOTE_CAPSULE_DIR",
        "DOMAIN",
        "REMOTE_AGENT_URL",
    }

    if normalized in droplet_keys:
        return f"KX_DROPLET_{normalized}"

    return f"KX_TARGET_{normalized}"


def _optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def path_from_optional(value: Any) -> Path | None:
    """Return a Path for optional path-like values."""

    if value is None or value == "":
        return None

    if isinstance(value, Path):
        return value

    return Path(str(value))


__all__ = [
    "DEFAULT_TARGET_MODE",
    "INSTANCE_ID_PATTERN",
    "TARGET_ALLOWED_EXPOSURE_MAP",
    "TARGET_DEFAULT_EXPOSURE_MAP",
    "TARGET_LABELS",
    "TARGET_PROFILE_MAP",
    "DropletTargetConfig",
    "TargetConfig",
    "TargetConfigError",
    "TargetMode",
    "allowed_exposure_modes_for_target",
    "build_target_config",
    "exposure_mode_for_target",
    "network_profile_for_target",
    "normalize_exposure_mode",
    "normalize_network_profile",
    "normalize_target_mode",
    "path_from_optional",
    "target_env",
    "target_mode_label",
    "target_summary",
    "validate_target_config",
]