# kx_manager/ui/form_targets.py

"""Target-mode and deployment form parsing for the Konnaxion Manager GUI."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from kx_manager.services.targets import (
    DropletTargetConfig,
    TargetConfig,
    TargetMode,
    exposure_mode_for_target,
    network_profile_for_target,
    validate_target_config,
)

from kx_manager.ui.form_constants import (
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_OUTPUT_DIR,
    DEFAULT_CAPSULE_VERSION,
    DEFAULT_RUNTIME_ROOT,
    DEFAULT_SOURCE_DIR,
    ExposureMode,
    NetworkProfile,
)
from kx_manager.ui.form_errors import FormValidationError
from kx_manager.ui.form_helpers import (
    _absolute_posix_path,
    _bool,
    _capsule_file,
    _capsule_id,
    _capsule_version,
    _coerce_enum,
    _exposure_mode,
    _host,
    _instance_id,
    _int,
    _iso_datetime,
    _network_profile,
    _path,
    _payload,
    _raw,
    _reject_droplet_fields,
    _remote_capsule_dir_under_root,
    _target_mode,
    _text,
    normalize_form_data,
)


@dataclass(frozen=True, slots=True)
class TargetModeForm:
    target_mode: TargetMode
    instance_id: str
    network_profile: Any
    exposure_mode: Any
    runtime_root: str
    capsule_dir: str
    source_dir: Path | None = None
    capsule_output_dir: Path | None = None
    host: str | None = None
    public_mode_expires_at: str | None = None
    confirmed: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "TargetModeForm":
        normalized = normalize_form_data(data)

        target_mode = _target_mode(normalized)
        default_profile = network_profile_for_target(target_mode)
        default_exposure = exposure_mode_for_target(target_mode)

        network_profile = _coerce_enum(
            NetworkProfile,
            _raw(
                normalized,
                "network_profile",
                "profile",
                default=default_profile.value,
            ),
            "network_profile",
        )
        exposure_mode = _coerce_enum(
            ExposureMode,
            _raw(normalized, "exposure_mode", default=default_exposure.value),
            "exposure_mode",
        )

        if network_profile != default_profile:
            raise FormValidationError(
                f"{target_mode.value} target requires "
                f"network_profile={default_profile.value}.",
                field="network_profile",
            )

        if target_mode == TargetMode.INTRANET:
            allowed_intranet_exposure = {
                _coerce_enum(ExposureMode, "private", "exposure_mode"),
                _coerce_enum(ExposureMode, "lan", "exposure_mode"),
            }
            if exposure_mode not in allowed_intranet_exposure:
                raise FormValidationError(
                    "intranet target allows only private or lan exposure.",
                    field="exposure_mode",
                )
        elif exposure_mode != default_exposure:
            raise FormValidationError(
                f"{target_mode.value} target requires "
                f"exposure_mode={default_exposure.value}.",
                field="exposure_mode",
            )

        public_mode_expires_at = _iso_datetime(
            normalized,
            "public_mode_expires_at",
            required=target_mode == TargetMode.TEMPORARY_PUBLIC,
        )
        confirmed = _bool(normalized, "confirmed", default=False)

        if target_mode == TargetMode.TEMPORARY_PUBLIC and not confirmed:
            raise FormValidationError(
                "temporary_public target requires explicit confirmation.",
                field="confirmed",
            )

        if target_mode in {
            TargetMode.LOCAL,
            TargetMode.INTRANET,
            TargetMode.TEMPORARY_PUBLIC,
        }:
            _reject_droplet_fields(normalized, target_mode.value)

        runtime_root = _text(
            normalized,
            "runtime_root",
            "target_runtime_root",
            default=DEFAULT_RUNTIME_ROOT,
            required=True,
            field="runtime_root",
        )
        assert runtime_root is not None

        capsule_dir = _text(
            normalized,
            "capsule_dir",
            "target_capsule_dir",
            default=str(Path(runtime_root) / "capsules"),
            required=True,
            field="capsule_dir",
        )
        assert capsule_dir is not None

        form = cls(
            target_mode=target_mode,
            instance_id=_instance_id(normalized),
            network_profile=network_profile,
            exposure_mode=exposure_mode,
            runtime_root=runtime_root,
            capsule_dir=capsule_dir,
            source_dir=_path(
                normalized,
                "source_dir",
                default=DEFAULT_SOURCE_DIR or None,
                required=False,
                must_exist=True,
                must_be_dir=True,
                field="source_dir",
            ),
            capsule_output_dir=_path(
                normalized,
                "capsule_output_dir",
                "output_dir",
                default=DEFAULT_CAPSULE_OUTPUT_DIR,
                required=False,
                must_be_dir=True,
                field="capsule_output_dir",
            ),
            host=_host(
                normalized,
                "host",
                "target_host",
                "private_host",
                "public_host",
                required=False,
                field="host",
            ),
            public_mode_expires_at=public_mode_expires_at,
            confirmed=confirmed,
        )

        validate_target_config(form.to_target_config())
        return form

    def to_target_config(self) -> TargetConfig:
        return TargetConfig(
            target_mode=self.target_mode,
            network_profile=self.network_profile,
            exposure_mode=self.exposure_mode,
            instance_id=self.instance_id,
            runtime_root=self.runtime_root,
            capsule_dir=self.capsule_dir,
            host=self.host,
            public_mode_expires_at=self.public_mode_expires_at,
            confirmed=self.confirmed,
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


@dataclass(frozen=True, slots=True)
class LocalTargetForm(TargetModeForm):
    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "LocalTargetForm":
        merged = normalize_form_data(data)
        merged["target_mode"] = TargetMode.LOCAL.value
        merged["network_profile"] = "local_only"
        merged["exposure_mode"] = "private"

        base = TargetModeForm.from_mapping(merged)
        return cls(**asdict(base))


@dataclass(frozen=True, slots=True)
class IntranetTargetForm(TargetModeForm):
    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "IntranetTargetForm":
        merged = normalize_form_data(data)
        merged["target_mode"] = TargetMode.INTRANET.value
        merged["network_profile"] = "intranet_private"

        if "exposure_mode" not in merged or not merged["exposure_mode"]:
            merged["exposure_mode"] = "private"

        base = TargetModeForm.from_mapping(merged)

        return cls(**asdict(base))


@dataclass(frozen=True, slots=True)
class TemporaryPublicTargetForm(TargetModeForm):
    public_host: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "TemporaryPublicTargetForm":
        merged = normalize_form_data(data)
        merged["target_mode"] = TargetMode.TEMPORARY_PUBLIC.value
        merged["network_profile"] = "public_temporary"
        merged["exposure_mode"] = "temporary_tunnel"

        public_host = _host(
            merged,
            "public_host",
            "host",
            required=True,
            field="public_host",
        )

        base = TargetModeForm.from_mapping(merged)

        return cls(
            **asdict(base),
            public_host=public_host,
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


@dataclass(frozen=True, slots=True)
class DropletTargetForm:
    target_mode: TargetMode
    instance_id: str
    source_dir: Path | None
    capsule_file: Path | None
    network_profile: Any
    exposure_mode: Any
    droplet_name: str
    droplet_host: str
    droplet_user: str
    ssh_key_path: Path
    ssh_port: int
    remote_kx_root: str
    remote_capsule_dir: str
    domain: str
    remote_agent_url: str | None = None
    confirmed: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "DropletTargetForm":
        normalized = normalize_form_data(data)

        target_mode = _target_mode(
            normalized,
            default=TargetMode.DROPLET.value,
        )

        if target_mode != TargetMode.DROPLET:
            raise FormValidationError(
                "droplet form requires target_mode=droplet.",
                field="target_mode",
            )

        network_profile = _network_profile(
            normalized,
            default="public_vps",
        )
        exposure_mode = _exposure_mode(
            normalized,
            default="public",
        )

        if network_profile != _coerce_enum(
            NetworkProfile,
            "public_vps",
            "network_profile",
        ):
            raise FormValidationError(
                "droplet target requires network_profile=public_vps.",
                field="network_profile",
            )

        if exposure_mode != _coerce_enum(
            ExposureMode,
            "public",
            "exposure_mode",
        ):
            raise FormValidationError(
                "droplet target requires exposure_mode=public.",
                field="exposure_mode",
            )

        confirmed = _bool(normalized, "confirmed", default=False)
        if not confirmed:
            raise FormValidationError(
                "droplet target requires explicit confirmation.",
                field="confirmed",
            )

        droplet_name = _text(
            normalized,
            "droplet_name",
            default="konnaxion-droplet",
            required=True,
            field="droplet_name",
        )
        droplet_host = _host(
            normalized,
            "droplet_host",
            "host",
            required=True,
            field="droplet_host",
        )
        droplet_user = _text(
            normalized,
            "droplet_user",
            "ssh_user",
            default="root",
            required=True,
            field="droplet_user",
        )

        assert droplet_name is not None
        assert droplet_host is not None
        assert droplet_user is not None

        ssh_key_path = _path(
            normalized,
            "ssh_key_path",
            "droplet_ssh_key",
            required=True,
            must_exist=True,
            must_be_file=True,
            field="ssh_key_path",
        )
        assert ssh_key_path is not None

        remote_kx_root_raw = _text(
            normalized,
            "remote_kx_root",
            "droplet_kx_root",
            default="/opt/konnaxion",
            required=True,
            field="remote_kx_root",
        )
        remote_capsule_dir_raw = _text(
            normalized,
            "remote_capsule_dir",
            "droplet_capsule_dir",
            default="/opt/konnaxion/capsules",
            required=True,
            field="remote_capsule_dir",
        )

        assert remote_kx_root_raw is not None
        assert remote_capsule_dir_raw is not None

        remote_kx_root = _absolute_posix_path(
            remote_kx_root_raw,
            "remote_kx_root",
        )
        remote_capsule_dir = _absolute_posix_path(
            remote_capsule_dir_raw,
            "remote_capsule_dir",
        )
        _remote_capsule_dir_under_root(remote_kx_root, remote_capsule_dir)

        domain = _host(
            normalized,
            "domain",
            "droplet_domain",
            required=True,
            field="domain",
        )
        assert domain is not None

        form = cls(
            target_mode=target_mode,
            instance_id=_instance_id(normalized),
            source_dir=_path(
                normalized,
                "source_dir",
                default=DEFAULT_SOURCE_DIR or None,
                required=False,
                must_exist=True,
                must_be_dir=True,
                field="source_dir",
            ),
            capsule_file=_capsule_file(
                normalized,
                "capsule_file",
                "capsule_path",
                required=False,
                must_exist=False,
                field="capsule_file",
            ),
            network_profile=network_profile,
            exposure_mode=exposure_mode,
            droplet_name=droplet_name,
            droplet_host=droplet_host,
            droplet_user=droplet_user,
            ssh_key_path=ssh_key_path,
            ssh_port=_int(
                normalized,
                "ssh_port",
                default=22,
                minimum=1,
                maximum=65535,
            ),
            remote_kx_root=remote_kx_root,
            remote_capsule_dir=remote_capsule_dir,
            domain=domain,
            remote_agent_url=_text(
                normalized,
                "remote_agent_url",
                "droplet_agent_url",
                required=False,
            ),
            confirmed=confirmed,
        )

        validate_target_config(form.to_target_config())
        return form

    def to_target_config(self) -> DropletTargetConfig:
        return DropletTargetConfig(
            target_mode=self.target_mode,
            network_profile=self.network_profile,
            exposure_mode=self.exposure_mode,
            instance_id=self.instance_id,
            runtime_root=self.remote_kx_root,
            capsule_dir=self.remote_capsule_dir,
            host=self.droplet_host,
            public_mode_expires_at=None,
            confirmed=self.confirmed,
            droplet_name=self.droplet_name,
            droplet_host=self.droplet_host,
            droplet_user=self.droplet_user,
            ssh_key_path=self.ssh_key_path,
            remote_kx_root=self.remote_kx_root,
            remote_capsule_dir=self.remote_capsule_dir,
            domain=self.domain,
            remote_agent_url=self.remote_agent_url,
            ssh_port=self.ssh_port,
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


@dataclass(frozen=True, slots=True)
class DeployLocalForm(LocalTargetForm):
    capsule_id: str = DEFAULT_CAPSULE_ID
    capsule_version: str = DEFAULT_CAPSULE_VERSION

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "DeployLocalForm":
        normalized = normalize_form_data(data)
        base = LocalTargetForm.from_mapping(normalized)

        return cls(
            **asdict(base),
            capsule_id=_capsule_id(normalized),
            capsule_version=_capsule_version(normalized),
        )


@dataclass(frozen=True, slots=True)
class DeployIntranetForm(IntranetTargetForm):
    capsule_id: str = DEFAULT_CAPSULE_ID
    capsule_version: str = DEFAULT_CAPSULE_VERSION

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "DeployIntranetForm":
        normalized = normalize_form_data(data)
        base = IntranetTargetForm.from_mapping(normalized)

        return cls(
            **asdict(base),
            capsule_id=_capsule_id(normalized),
            capsule_version=_capsule_version(normalized),
        )


@dataclass(frozen=True, slots=True)
class DeployDropletForm(DropletTargetForm):
    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "DeployDropletForm":
        normalized = normalize_form_data(data)
        base = DropletTargetForm.from_mapping(normalized)

        if base.capsule_file is None:
            raise FormValidationError(
                "deploy_droplet requires capsule_file.",
                field="capsule_file",
            )

        return cls(**asdict(base))


def parse_target_form(data: Mapping[str, Any]) -> Any:
    normalized = normalize_form_data(data)
    target_mode = _target_mode(normalized)

    if target_mode == TargetMode.LOCAL:
        return LocalTargetForm.from_mapping(normalized)

    if target_mode == TargetMode.INTRANET:
        return IntranetTargetForm.from_mapping(normalized)

    if target_mode == TargetMode.TEMPORARY_PUBLIC:
        return TemporaryPublicTargetForm.from_mapping(normalized)

    if target_mode == TargetMode.DROPLET:
        return DropletTargetForm.from_mapping(normalized)

    raise FormValidationError(
        f"Unsupported target mode: {target_mode!r}",
        field="target_mode",
    )


__all__ = [
    "DeployDropletForm",
    "DeployIntranetForm",
    "DeployLocalForm",
    "DropletTargetForm",
    "IntranetTargetForm",
    "LocalTargetForm",
    "TargetModeForm",
    "TemporaryPublicTargetForm",
    "parse_target_form",
]