"""Capsule and build form models for the Konnaxion Capsule Manager GUI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from kx_manager.ui.form_constants import (
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_OUTPUT_DIR,
    DEFAULT_CAPSULE_VERSION,
    DEFAULT_CHANNEL,
    DEFAULT_INSTANCE_ID,
    DEFAULT_SOURCE_DIR,
)
from kx_manager.ui.form_helpers import (
    _bool,
    _capsule_file,
    _capsule_id,
    _capsule_output_dir,
    _capsule_version,
    _computed_capsule_file,
    _existing_dir,
    _instance_id,
    _network_profile,
    _payload,
    _text,
    normalize_form_data,
)


@dataclass(frozen=True, slots=True)
class BuildCapsuleForm:
    source_dir: Path
    capsule_output_dir: Path
    capsule_id: str
    capsule_version: str
    capsule_file: Path
    channel: str = DEFAULT_CHANNEL
    force: bool = True
    delete_existing: bool = False
    verify_after_build: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BuildCapsuleForm":
        source_dir = _existing_dir(
            data,
            "source_dir",
            default=DEFAULT_SOURCE_DIR,
            field="source_dir",
        )
        capsule_output_dir = _capsule_output_dir(data)
        capsule_id = _capsule_id(data)
        capsule_file = _capsule_file(
            data,
            "capsule_file",
            "output",
            required=False,
            must_exist=False,
            field="capsule_file",
        ) or _computed_capsule_file(capsule_output_dir, capsule_id)

        channel = _text(
            data,
            "channel",
            default=DEFAULT_CHANNEL,
            required=True,
            field="channel",
        )
        assert channel is not None

        return cls(
            source_dir=source_dir,
            capsule_output_dir=capsule_output_dir,
            capsule_id=capsule_id,
            capsule_version=_capsule_version(data),
            capsule_file=capsule_file,
            channel=channel,
            force=_bool(data, "force", default=True),
            delete_existing=_bool(data, "delete_existing", default=False),
            verify_after_build=_bool(data, "verify_after_build", default=False),
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


@dataclass(frozen=True, slots=True)
class VerifyCapsuleForm:
    capsule_file: Path

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "VerifyCapsuleForm":
        capsule_file = _capsule_file(
            data,
            "capsule_file",
            "capsule_path",
            "path",
            required=True,
            must_exist=True,
            field="capsule_file",
        )
        assert capsule_file is not None
        return cls(capsule_file=capsule_file)

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


@dataclass(frozen=True, slots=True)
class ImportCapsuleForm:
    capsule_file: Path
    instance_id: str
    network_profile: Any

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ImportCapsuleForm":
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
            capsule_file=capsule_file,
            instance_id=_instance_id(data, default=DEFAULT_INSTANCE_ID),
            network_profile=_network_profile(data),
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


@dataclass(frozen=True, slots=True)
class CapsuleLookupForm:
    capsule_id: str
    capsule_file: Path | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CapsuleLookupForm":
        return cls(
            capsule_id=_capsule_id(data, default=DEFAULT_CAPSULE_ID),
            capsule_file=_capsule_file(
                data,
                "capsule_file",
                "capsule_path",
                required=False,
                must_exist=False,
                field="capsule_file",
            ),
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


def parse_build_form(data: Mapping[str, Any]) -> BuildCapsuleForm:
    return BuildCapsuleForm.from_mapping(normalize_form_data(data))


def parse_verify_capsule_form(data: Mapping[str, Any]) -> VerifyCapsuleForm:
    return VerifyCapsuleForm.from_mapping(normalize_form_data(data))


def parse_import_capsule_form(data: Mapping[str, Any]) -> ImportCapsuleForm:
    return ImportCapsuleForm.from_mapping(normalize_form_data(data))


def parse_capsule_lookup_form(data: Mapping[str, Any]) -> CapsuleLookupForm:
    return CapsuleLookupForm.from_mapping(normalize_form_data(data))


__all__ = [
    "BuildCapsuleForm",
    "CapsuleLookupForm",
    "ImportCapsuleForm",
    "VerifyCapsuleForm",
    "parse_build_form",
    "parse_capsule_lookup_form",
    "parse_import_capsule_form",
    "parse_verify_capsule_form",
]