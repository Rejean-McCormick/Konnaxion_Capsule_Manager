# kx_manager/ui/form_backups.py

"""Backup and restore form models for the Konnaxion Capsule Manager GUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from kx_manager.ui.form_errors import FormValidationError
from kx_manager.ui.form_helpers import (
    _backup_id,
    _bool,
    _instance_id,
    _payload,
    _safe_identifier,
    _text,
    normalize_form_data,
)


@dataclass(frozen=True, slots=True)
class BackupForm:
    instance_id: str
    backup_class: str = "manual"
    verify_after_create: bool = True

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BackupForm":
        backup_class = _text(
            data,
            "backup_class",
            default="manual",
            required=True,
            field="backup_class",
        )
        assert backup_class is not None

        return cls(
            instance_id=_instance_id(data),
            backup_class=_safe_identifier(backup_class, "backup_class"),
            verify_after_create=_bool(data, "verify_after_create", default=True),
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


@dataclass(frozen=True, slots=True)
class ListBackupsForm:
    instance_id: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ListBackupsForm":
        value = _text(data, "instance_id", required=False, field="instance_id")
        return cls(
            instance_id=_safe_identifier(value, "instance_id") if value else None,
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


@dataclass(frozen=True, slots=True)
class BackupLookupForm:
    backup_id: str
    instance_id: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BackupLookupForm":
        backup_id = _backup_id(data, required=True)
        assert backup_id is not None

        instance_id = _text(data, "instance_id", required=False, field="instance_id")

        return cls(
            backup_id=backup_id,
            instance_id=_safe_identifier(instance_id, "instance_id")
            if instance_id
            else None,
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


@dataclass(frozen=True, slots=True)
class RestoreForm:
    instance_id: str
    backup_id: str
    target_instance_id: str | None = None
    restore_data: bool = True
    test_only: bool = False
    confirmed: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "RestoreForm":
        test_only = _bool(data, "test_only", default=False)
        confirmed = _bool(data, "confirmed", default=False)

        if not test_only and not confirmed:
            raise FormValidationError(
                "restore requires explicit confirmation.",
                field="confirmed",
            )

        backup_id = _backup_id(data, required=True)
        assert backup_id is not None

        target_instance_id = _text(
            data,
            "target_instance_id",
            "new_instance_id",
            required=False,
            field="target_instance_id",
        )

        if target_instance_id is not None:
            target_instance_id = _safe_identifier(
                target_instance_id,
                "target_instance_id",
            )

        return cls(
            instance_id=_instance_id(data),
            backup_id=backup_id,
            target_instance_id=target_instance_id,
            restore_data=_bool(data, "restore_data", default=True),
            test_only=test_only,
            confirmed=confirmed,
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


def parse_backup_form(data: Mapping[str, Any]) -> BackupForm:
    return BackupForm.from_mapping(normalize_form_data(data))


def parse_restore_form(data: Mapping[str, Any]) -> RestoreForm:
    return RestoreForm.from_mapping(normalize_form_data(data))


__all__ = [
    "BackupForm",
    "BackupLookupForm",
    "ListBackupsForm",
    "RestoreForm",
    "parse_backup_form",
    "parse_restore_form",
]