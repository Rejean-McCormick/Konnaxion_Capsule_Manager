# kx_manager/ui/form_core.py

"""Core/simple form models for the Konnaxion Capsule Manager GUI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from kx_manager.ui.form_constants import DEFAULT_SOURCE_DIR
from kx_manager.ui.form_helpers import (
    _capsule_output_dir,
    _existing_dir,
    _payload,
)


@dataclass(frozen=True, slots=True)
class EmptyForm:
    """Form model for actions that need no submitted fields."""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EmptyForm":
        return cls()

    def to_payload(self) -> dict[str, Any]:
        return {}


@dataclass(frozen=True, slots=True)
class SourceFolderForm:
    """Form model for selecting the Konnaxion source folder."""

    source_dir: Path

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "SourceFolderForm":
        return cls(
            source_dir=_existing_dir(
                data,
                "source_dir",
                default=DEFAULT_SOURCE_DIR,
                field="source_dir",
            )
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


@dataclass(frozen=True, slots=True)
class CapsuleOutputFolderForm:
    """Form model for selecting the capsule output folder."""

    capsule_output_dir: Path

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CapsuleOutputFolderForm":
        return cls(capsule_output_dir=_capsule_output_dir(data))

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


__all__ = [
    "CapsuleOutputFolderForm",
    "EmptyForm",
    "SourceFolderForm",
]