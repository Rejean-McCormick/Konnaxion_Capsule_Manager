# kx_manager/ui/form_network.py

"""Network form models for the Konnaxion Capsule Manager GUI.

This module validates network-profile form payloads only. It does not execute
network changes, call Docker, mutate firewall rules, or contact the Agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from kx_manager.ui.form_constants import ExposureMode, NetworkProfile
from kx_manager.ui.form_errors import FormValidationError
from kx_manager.ui.form_helpers import (
    _bool,
    _coerce_enum,
    _exposure_mode,
    _host,
    _instance_id,
    _iso_datetime,
    _network_profile,
    _payload,
    _validate_profile_exposure,
    normalize_form_data,
)


@dataclass(frozen=True, slots=True)
class NetworkProfileForm:
    """Form model for setting an instance network profile."""

    instance_id: str
    network_profile: Any
    exposure_mode: Any
    host: str | None = None
    domain: str | None = None
    public_mode_expires_at: str | None = None
    confirmed: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "NetworkProfileForm":
        normalized = normalize_form_data(data)

        network_profile = _network_profile(normalized)
        exposure_mode = _exposure_mode(normalized)
        public_mode_expires_at = _iso_datetime(
            normalized,
            "public_mode_expires_at",
            required=False,
        )
        confirmed = _bool(normalized, "confirmed", default=False)
        host = _host(
            normalized,
            "host",
            "target_host",
            "public_host",
            "private_host",
            required=False,
            field="host",
        )
        domain = _host(
            normalized,
            "domain",
            required=False,
            field="domain",
        )

        _validate_profile_exposure(
            network_profile=network_profile,
            exposure_mode=exposure_mode,
            public_mode_expires_at=public_mode_expires_at,
            confirmed=confirmed,
            host=host,
            domain=domain,
        )

        return cls(
            instance_id=_instance_id(normalized),
            network_profile=network_profile,
            exposure_mode=exposure_mode,
            host=host,
            domain=domain,
            public_mode_expires_at=public_mode_expires_at,
            confirmed=confirmed,
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


@dataclass(frozen=True, slots=True)
class DisablePublicModeForm:
    """Form model for disabling public mode on an instance."""

    instance_id: str
    network_profile: Any
    exposure_mode: Any
    confirmed: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "DisablePublicModeForm":
        normalized = normalize_form_data(data)
        confirmed = _bool(normalized, "confirmed", default=False)

        if not confirmed:
            raise FormValidationError(
                "disable_public_mode requires explicit confirmation.",
                field="confirmed",
            )

        return cls(
            instance_id=_instance_id(normalized),
            network_profile=_coerce_enum(
                NetworkProfile,
                "intranet_private",
                "network_profile",
            ),
            exposure_mode=_coerce_enum(
                ExposureMode,
                "private",
                "exposure_mode",
            ),
            confirmed=confirmed,
        )

    def to_payload(self) -> dict[str, Any]:
        return _payload(self)


def parse_network_form(data: Mapping[str, Any]) -> NetworkProfileForm:
    """Parse and validate a network profile form payload."""

    return NetworkProfileForm.from_mapping(data)


__all__ = [
    "DisablePublicModeForm",
    "NetworkProfileForm",
    "parse_network_form",
]