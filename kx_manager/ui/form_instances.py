# kx_manager/ui/form_instances.py

"""Instance, runtime, logs, and rollback form models for the Konnaxion Capsule
Manager GUI.

This module owns form parsing and validation only. It does not execute actions,
call Docker, run shell commands, or mutate host state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from kx_manager.ui.form_errors import FormValidationError
from kx_manager.ui.form_helpers import (
    _backup_id,
    _bool,
    _capsule_file,
    _capsule_id,
    _docker_service,
    _exposure_mode,
    _host,
    _instance_id,
    _int,
    _network_profile,
    _payload,
    _text,
    _validate_profile_exposure,
    normalize_form_data,
)


@dataclass(frozen=True, slots=True)
class CreateInstanceForm:
    instance_id: str
    capsule_id: str
    network_profile: Any
    exposure_mode: Any
    host: str | None = None
    domain: str | None = None
    public_mode_expires_at: str | None = None
    generate_secrets: bool = True
    confirmed: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CreateInstanceForm":
        network_profile = _network_profile(data)
        exposure_mode = _exposure_mode(data)
        confirmed = _bool(data, "confirmed", default=False)

        public_mode_expires_at = _text(
            data,
            "public_mode_expires_at",
            "expires_at",
            required=False,
            field="public_mode_expires_at",
        )

        host = _host(
            data,
            "host",
            "target_host",
            "private_host",
            "public_host",
            required=False,
            field="host",
        )
        domain = _host(data, "domain", required=False, field="domain")

        _validate_profile_exposure(
            network_profile=network_profile,
            exposure_mode=exposure_mode,
            public_mode_expires_at=public_mode_expires_at,
            confirmed=confirmed,
            host=host,
            domain=domain,
        )

        return cls(
            instance_id=_instance_id(data),
            capsule_id=_capsule_id(data),
            network_profile=network_profile,
            exposure_mode=exposure_mode,
            host=host,
            domain=domain,
            public_mode_expires_at=public_mode_expires_at,
            generate_secrets=_bool(data, "generate_secrets", default=True),
            confirmed=confirmed,
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


@dataclass(frozen=True, slots=True)
class UpdateInstanceForm:
    instance_id: str
    capsule_file: Path
    create_pre_update_backup: bool = True

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "UpdateInstanceForm":
        capsule_file = _capsule_file(
            data,
            "capsule_file",
            "capsule_path",
            required=True,
            must_exist=True,
            field="capsule_file",
        )
        assert capsule_file is not None

        return cls(
            instance_id=_instance_id(data),
            capsule_file=capsule_file,
            create_pre_update_backup=_bool(
                data,
                "create_pre_update_backup",
                default=True,
            ),
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


@dataclass(frozen=True, slots=True)
class InstanceActionForm:
    instance_id: str
    run_security_gate: bool = True
    timeout_seconds: int = 60
    confirmed: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "InstanceActionForm":
        return cls(
            instance_id=_instance_id(data),
            run_security_gate=_bool(data, "run_security_gate", default=True),
            timeout_seconds=_int(
                data,
                "timeout_seconds",
                default=60,
                minimum=1,
                maximum=3600,
            ),
            confirmed=_bool(data, "confirmed", default=False),
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


@dataclass(frozen=True, slots=True)
class ConfirmedInstanceActionForm(InstanceActionForm):
    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
    ) -> "ConfirmedInstanceActionForm":
        form = InstanceActionForm.from_mapping(data)

        if not form.confirmed:
            raise FormValidationError(
                "explicit confirmation is required.",
                field="confirmed",
            )

        return cls(
            instance_id=form.instance_id,
            run_security_gate=form.run_security_gate,
            timeout_seconds=form.timeout_seconds,
            confirmed=form.confirmed,
        )


@dataclass(frozen=True, slots=True)
class OpenInstanceForm:
    instance_id: str
    url: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "OpenInstanceForm":
        return cls(
            instance_id=_instance_id(data),
            url=_text(
                data,
                "url",
                "private_url",
                "public_url",
                required=False,
                field="url",
            ),
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


@dataclass(frozen=True, slots=True)
class LogsForm:
    instance_id: str
    service: Any | None = None
    lines: int = 200
    tail: bool = True

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "LogsForm":
        normalized = normalize_form_data(data)
        raw_tail = normalized.get("tail")

        tail_is_numeric_lines = (
            raw_tail is not None
            and not isinstance(raw_tail, bool)
            and str(raw_tail).strip().isdigit()
        )

        line_default = int(str(raw_tail).strip()) if tail_is_numeric_lines else 200

        return cls(
            instance_id=_instance_id(normalized),
            service=_docker_service(normalized, required=False),
            lines=_int(
                normalized,
                "lines",
                default=line_default,
                minimum=1,
                maximum=10000,
            ),
            tail=(
                True
                if tail_is_numeric_lines
                else _bool(normalized, "tail", default=True)
            ),
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


@dataclass(frozen=True, slots=True)
class RollbackForm:
    instance_id: str
    restore_data: bool = False
    backup_id: str | None = None
    confirmed: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "RollbackForm":
        restore_data = _bool(data, "restore_data", default=False)
        backup_id = _backup_id(data, required=restore_data)
        confirmed = _bool(data, "confirmed", default=False)

        if not confirmed:
            raise FormValidationError(
                "rollback requires explicit confirmation.",
                field="confirmed",
            )

        return cls(
            instance_id=_instance_id(data),
            restore_data=restore_data,
            backup_id=backup_id,
            confirmed=confirmed,
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


def parse_instance_form(data: Mapping[str, Any]) -> CreateInstanceForm:
    return CreateInstanceForm.from_mapping(normalize_form_data(data))


def parse_rollback_form(data: Mapping[str, Any]) -> RollbackForm:
    return RollbackForm.from_mapping(normalize_form_data(data))


__all__ = [
    "ConfirmedInstanceActionForm",
    "CreateInstanceForm",
    "InstanceActionForm",
    "LogsForm",
    "OpenInstanceForm",
    "RollbackForm",
    "UpdateInstanceForm",
    "parse_instance_form",
    "parse_rollback_form",
]