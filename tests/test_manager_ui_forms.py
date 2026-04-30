"""Contract tests for kx_manager.ui.forms.

These tests define the required GUI form parsing and validation behavior for
the FastAPI Manager GUI. They intentionally test the public forms.py API rather
than route handlers, action dispatch, Agent calls, Docker, SSH, or shell logic.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping

import pytest

from kx_manager.ui import forms


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_function(name: str):
    fn = getattr(forms, name, None)
    assert callable(fn), f"kx_manager.ui.forms.{name} must exist and be callable"
    return fn


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value

    if is_dataclass(value):
        return asdict(value)

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        data = model_dump()
        assert isinstance(data, Mapping)
        return data

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
        assert isinstance(data, Mapping)
        return data

    if hasattr(value, "__dict__"):
        return vars(value)

    raise AssertionError(f"Object is not mapping-like: {value!r}")


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _field(value: Any, name: str) -> Any:
    data = _as_mapping(value)
    assert name in data, f"Expected field {name!r} in {data!r}"
    return data[name]


def _text_field(value: Any, name: str) -> str:
    raw = _value(_field(value, name))
    return "" if raw is None else str(raw)


def _bool_field(value: Any, name: str) -> bool:
    return bool(_field(value, name))


def _assert_invalid(fn, payload: Mapping[str, Any]) -> None:
    with pytest.raises(Exception):
        fn(payload)


def _valid_build_payload(tmp_path: Path) -> dict[str, Any]:
    source_dir = tmp_path / "Konnaxion"
    output_dir = tmp_path / "runtime" / "capsules"
    source_dir.mkdir(parents=True)
    output_dir.parent.mkdir(parents=True)

    return {
        "source_dir": str(source_dir),
        "capsule_output_dir": str(output_dir),
        "capsule_id": "konnaxion-v14-demo-2026.04.30",
        "capsule_version": "2026.04.30-demo.1",
    }


def _valid_instance_payload() -> dict[str, Any]:
    return {
        "instance_id": "demo-001",
        "capsule_id": "konnaxion-v14-demo-2026.04.30",
        "capsule_version": "2026.04.30-demo.1",
    }


def _valid_droplet_payload(tmp_path: Path) -> dict[str, Any]:
    ssh_key = tmp_path / "id_ed25519"
    ssh_key.write_text("not-a-real-key-for-tests\n", encoding="utf-8")

    return {
        "target_mode": "droplet",
        "network_profile": "public_vps",
        "exposure_mode": "public",
        "instance_id": "demo-001",
        "capsule_file": "konnaxion-v14-demo-2026.04.30.kxcap",
        "droplet_name": "demo-droplet",
        "droplet_host": "203.0.113.10",
        "droplet_user": "root",
        "ssh_key_path": str(ssh_key),
        "remote_kx_root": "/opt/konnaxion",
        "remote_capsule_dir": "/opt/konnaxion/capsules",
        "domain": "app.example.com",
        "confirmed": "true",
    }


# ---------------------------------------------------------------------------
# Contract surface
# ---------------------------------------------------------------------------

def test_forms_module_exposes_required_contract_surface() -> None:
    expected_functions = {
        "normalize_form_data",
        "parse_build_form",
        "parse_instance_form",
        "parse_network_form",
        "parse_backup_form",
        "parse_restore_form",
        "parse_rollback_form",
        "parse_target_form",
        "validate_action_payload",
    }

    missing = [name for name in sorted(expected_functions) if not callable(getattr(forms, name, None))]
    assert not missing, f"Missing required forms.py functions: {missing}"


def test_normalize_form_data_strips_strings_and_preserves_keys() -> None:
    normalize_form_data = _require_function("normalize_form_data")

    result = normalize_form_data(
        {
            "instance_id": "  demo-001  ",
            "network_profile": " intranet_private ",
            "confirmed": " true ",
        }
    )

    assert result["instance_id"] == "demo-001"
    assert result["network_profile"] == "intranet_private"
    assert result["confirmed"] == "true"


# ---------------------------------------------------------------------------
# Build/source/output folder forms
# ---------------------------------------------------------------------------

def test_build_form_accepts_text_folder_inputs(tmp_path: Path) -> None:
    parse_build_form = _require_function("parse_build_form")
    payload = _valid_build_payload(tmp_path)

    result = parse_build_form(payload)

    assert Path(_text_field(result, "source_dir")) == Path(payload["source_dir"])
    assert Path(_text_field(result, "capsule_output_dir")) == Path(payload["capsule_output_dir"])
    assert _text_field(result, "capsule_id") == "konnaxion-v14-demo-2026.04.30"
    assert _text_field(result, "capsule_version") == "2026.04.30-demo.1"


def test_build_form_rejects_missing_source_dir(tmp_path: Path) -> None:
    parse_build_form = _require_function("parse_build_form")
    payload = _valid_build_payload(tmp_path)
    payload["source_dir"] = ""

    _assert_invalid(parse_build_form, payload)


def test_build_form_rejects_nonexistent_source_dir(tmp_path: Path) -> None:
    parse_build_form = _require_function("parse_build_form")
    payload = _valid_build_payload(tmp_path)
    payload["source_dir"] = str(tmp_path / "does-not-exist")

    _assert_invalid(parse_build_form, payload)


def test_build_form_allows_creatable_output_dir(tmp_path: Path) -> None:
    parse_build_form = _require_function("parse_build_form")

    source_dir = tmp_path / "Konnaxion"
    source_dir.mkdir()

    output_dir = tmp_path / "runtime" / "capsules"

    result = parse_build_form(
        {
            "source_dir": str(source_dir),
            "capsule_output_dir": str(output_dir),
            "capsule_id": "konnaxion-v14-demo-2026.04.30",
            "capsule_version": "2026.04.30-demo.1",
        }
    )

    assert Path(_text_field(result, "capsule_output_dir")) == output_dir


# ---------------------------------------------------------------------------
# Instance, backup, restore, rollback forms
# ---------------------------------------------------------------------------

def test_instance_form_requires_instance_id_and_capsule_id() -> None:
    parse_instance_form = _require_function("parse_instance_form")

    result = parse_instance_form(_valid_instance_payload())

    assert _text_field(result, "instance_id") == "demo-001"
    assert _text_field(result, "capsule_id") == "konnaxion-v14-demo-2026.04.30"

    invalid = _valid_instance_payload()
    invalid["instance_id"] = ""
    _assert_invalid(parse_instance_form, invalid)

    invalid = _valid_instance_payload()
    invalid["capsule_id"] = ""
    _assert_invalid(parse_instance_form, invalid)


def test_backup_form_requires_instance_id() -> None:
    parse_backup_form = _require_function("parse_backup_form")

    result = parse_backup_form({"instance_id": "demo-001", "backup_class": "manual"})

    assert _text_field(result, "instance_id") == "demo-001"
    assert _text_field(result, "backup_class") == "manual"

    _assert_invalid(parse_backup_form, {"instance_id": "", "backup_class": "manual"})


def test_restore_form_requires_confirmation() -> None:
    parse_restore_form = _require_function("parse_restore_form")

    valid = {
        "instance_id": "demo-001",
        "backup_id": "demo-001_20260430_230000_manual",
        "confirmed": "true",
    }

    result = parse_restore_form(valid)

    assert _text_field(result, "instance_id") == "demo-001"
    assert _text_field(result, "backup_id") == "demo-001_20260430_230000_manual"
    assert _bool_field(result, "confirmed") is True

    invalid = dict(valid)
    invalid["confirmed"] = ""
    _assert_invalid(parse_restore_form, invalid)


def test_rollback_restore_data_requires_backup_id() -> None:
    parse_rollback_form = _require_function("parse_rollback_form")

    valid = {
        "instance_id": "demo-001",
        "restore_data": "true",
        "backup_id": "demo-001_20260430_230000_manual",
        "confirmed": "true",
    }

    result = parse_rollback_form(valid)

    assert _text_field(result, "instance_id") == "demo-001"
    assert _bool_field(result, "restore_data") is True
    assert _text_field(result, "backup_id") == "demo-001_20260430_230000_manual"

    invalid = dict(valid)
    invalid["backup_id"] = ""
    _assert_invalid(parse_rollback_form, invalid)


# ---------------------------------------------------------------------------
# Network profile forms
# ---------------------------------------------------------------------------

def test_network_form_accepts_canonical_private_profile() -> None:
    parse_network_form = _require_function("parse_network_form")

    result = parse_network_form(
        {
            "instance_id": "demo-001",
            "network_profile": "intranet_private",
            "exposure_mode": "private",
        }
    )

    assert _text_field(result, "instance_id") == "demo-001"
    assert _text_field(result, "network_profile") == "intranet_private"
    assert _text_field(result, "exposure_mode") == "private"


@pytest.mark.parametrize(
    ("network_profile", "exposure_mode"),
    [
        ("not_a_profile", "private"),
        ("intranet_private", "not_an_exposure"),
        ("intranet_private", "public"),
        ("public_vps", "private"),
        ("public_temporary", "private"),
    ],
)
def test_network_form_rejects_invalid_canonical_combinations(
    network_profile: str,
    exposure_mode: str,
) -> None:
    parse_network_form = _require_function("parse_network_form")

    _assert_invalid(
        parse_network_form,
        {
            "instance_id": "demo-001",
            "network_profile": network_profile,
            "exposure_mode": exposure_mode,
        },
    )


def test_network_form_public_temporary_requires_expiration_and_confirmation() -> None:
    parse_network_form = _require_function("parse_network_form")

    valid = {
        "instance_id": "demo-001",
        "network_profile": "public_temporary",
        "exposure_mode": "temporary_tunnel",
        "public_mode_expires_at": "2026-04-30T22:00:00Z",
        "confirmed": "true",
    }

    result = parse_network_form(valid)

    assert _text_field(result, "network_profile") == "public_temporary"
    assert _text_field(result, "exposure_mode") == "temporary_tunnel"
    assert _text_field(result, "public_mode_expires_at") == "2026-04-30T22:00:00Z"
    assert _bool_field(result, "confirmed") is True

    missing_expiration = dict(valid)
    missing_expiration["public_mode_expires_at"] = ""
    _assert_invalid(parse_network_form, missing_expiration)

    missing_confirmation = dict(valid)
    missing_confirmation["confirmed"] = ""
    _assert_invalid(parse_network_form, missing_confirmation)


def test_network_form_public_vps_requires_public_exposure_host_and_confirmation() -> None:
    parse_network_form = _require_function("parse_network_form")

    valid = {
        "instance_id": "demo-001",
        "network_profile": "public_vps",
        "exposure_mode": "public",
        "host": "app.example.com",
        "confirmed": "true",
    }

    result = parse_network_form(valid)

    assert _text_field(result, "network_profile") == "public_vps"
    assert _text_field(result, "exposure_mode") == "public"
    assert _text_field(result, "host") == "app.example.com"
    assert _bool_field(result, "confirmed") is True

    missing_host = dict(valid)
    missing_host["host"] = ""
    _assert_invalid(parse_network_form, missing_host)

    missing_confirmation = dict(valid)
    missing_confirmation["confirmed"] = ""
    _assert_invalid(parse_network_form, missing_confirmation)


# ---------------------------------------------------------------------------
# Target mode forms
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("target_mode", "network_profile", "exposure_mode"),
    [
        ("local", "local_only", "private"),
        ("intranet", "intranet_private", "private"),
        ("temporary_public", "public_temporary", "temporary_tunnel"),
        ("droplet", "public_vps", "public"),
    ],
)
def test_target_form_maps_modes_to_canonical_profile_and_exposure(
    tmp_path: Path,
    target_mode: str,
    network_profile: str,
    exposure_mode: str,
) -> None:
    parse_target_form = _require_function("parse_target_form")

    payload: dict[str, Any] = {
        "target_mode": target_mode,
        "network_profile": network_profile,
        "exposure_mode": exposure_mode,
        "instance_id": "demo-001",
        "capsule_id": "konnaxion-v14-demo-2026.04.30",
        "capsule_version": "2026.04.30-demo.1",
        "source_dir": str(tmp_path),
        "capsule_output_dir": str(tmp_path / "capsules"),
    }

    if target_mode == "temporary_public":
        payload.update(
            {
                "host": "demo.example.com",
                "public_mode_expires_at": "2026-04-30T22:00:00Z",
                "confirmed": "true",
            }
        )

    if target_mode == "droplet":
        payload.update(_valid_droplet_payload(tmp_path))

    result = parse_target_form(payload)

    assert _text_field(result, "target_mode") == target_mode
    assert _text_field(result, "network_profile") == network_profile
    assert _text_field(result, "exposure_mode") == exposure_mode


def test_target_form_rejects_invalid_target_mode() -> None:
    parse_target_form = _require_function("parse_target_form")

    _assert_invalid(
        parse_target_form,
        {
            "target_mode": "vps",
            "network_profile": "public_vps",
            "exposure_mode": "public",
            "instance_id": "demo-001",
        },
    )


def test_target_form_rejects_profile_exposure_drift() -> None:
    parse_target_form = _require_function("parse_target_form")

    _assert_invalid(
        parse_target_form,
        {
            "target_mode": "intranet",
            "network_profile": "public_vps",
            "exposure_mode": "public",
            "instance_id": "demo-001",
            "host": "app.example.com",
            "confirmed": "true",
        },
    )

    _assert_invalid(
        parse_target_form,
        {
            "target_mode": "droplet",
            "network_profile": "intranet_private",
            "exposure_mode": "private",
            "instance_id": "demo-001",
            "confirmed": "true",
        },
    )


def test_local_target_rejects_droplet_fields() -> None:
    parse_target_form = _require_function("parse_target_form")

    _assert_invalid(
        parse_target_form,
        {
            "target_mode": "local",
            "network_profile": "local_only",
            "exposure_mode": "private",
            "instance_id": "demo-001",
            "droplet_host": "203.0.113.10",
            "droplet_user": "root",
            "ssh_key_path": "/tmp/id_ed25519",
        },
    )


def test_intranet_target_allows_lan_but_rejects_public_exposure() -> None:
    parse_target_form = _require_function("parse_target_form")

    valid = {
        "target_mode": "intranet",
        "network_profile": "intranet_private",
        "exposure_mode": "lan",
        "instance_id": "demo-001",
        "host": "konnaxion.lan",
    }

    result = parse_target_form(valid)

    assert _text_field(result, "target_mode") == "intranet"
    assert _text_field(result, "network_profile") == "intranet_private"
    assert _text_field(result, "exposure_mode") == "lan"
    assert _text_field(result, "host") == "konnaxion.lan"

    invalid = dict(valid)
    invalid["exposure_mode"] = "public"
    _assert_invalid(parse_target_form, invalid)


def test_temporary_public_target_requires_expiration_and_confirmation() -> None:
    parse_target_form = _require_function("parse_target_form")

    valid = {
        "target_mode": "temporary_public",
        "network_profile": "public_temporary",
        "exposure_mode": "temporary_tunnel",
        "instance_id": "demo-001",
        "host": "demo.example.com",
        "public_mode_expires_at": "2026-04-30T22:00:00Z",
        "confirmed": "true",
    }

    result = parse_target_form(valid)

    assert _text_field(result, "target_mode") == "temporary_public"
    assert _text_field(result, "public_mode_expires_at") == "2026-04-30T22:00:00Z"
    assert _bool_field(result, "confirmed") is True

    missing_expiration = dict(valid)
    missing_expiration["public_mode_expires_at"] = ""
    _assert_invalid(parse_target_form, missing_expiration)

    missing_confirmation = dict(valid)
    missing_confirmation["confirmed"] = ""
    _assert_invalid(parse_target_form, missing_confirmation)


@pytest.mark.parametrize(
    "missing_field",
    [
        "droplet_host",
        "droplet_user",
        "ssh_key_path",
        "remote_kx_root",
        "remote_capsule_dir",
        "domain",
        "confirmed",
    ],
)
def test_droplet_target_requires_all_public_deploy_fields(
    tmp_path: Path,
    missing_field: str,
) -> None:
    parse_target_form = _require_function("parse_target_form")
    payload = _valid_droplet_payload(tmp_path)
    payload[missing_field] = ""

    _assert_invalid(parse_target_form, payload)


def test_droplet_target_requires_existing_ssh_key(tmp_path: Path) -> None:
    parse_target_form = _require_function("parse_target_form")
    payload = _valid_droplet_payload(tmp_path)
    payload["ssh_key_path"] = str(tmp_path / "missing_id_ed25519")

    _assert_invalid(parse_target_form, payload)


def test_droplet_remote_capsule_dir_must_be_under_remote_root(tmp_path: Path) -> None:
    parse_target_form = _require_function("parse_target_form")
    payload = _valid_droplet_payload(tmp_path)
    payload["remote_kx_root"] = "/opt/konnaxion"
    payload["remote_capsule_dir"] = "/tmp/capsules"

    _assert_invalid(parse_target_form, payload)


def test_droplet_target_accepts_valid_public_vps_configuration(tmp_path: Path) -> None:
    parse_target_form = _require_function("parse_target_form")
    payload = _valid_droplet_payload(tmp_path)

    result = parse_target_form(payload)

    assert _text_field(result, "target_mode") == "droplet"
    assert _text_field(result, "network_profile") == "public_vps"
    assert _text_field(result, "exposure_mode") == "public"
    assert _text_field(result, "droplet_host") == "203.0.113.10"
    assert _text_field(result, "droplet_user") == "root"
    assert _text_field(result, "remote_kx_root") == "/opt/konnaxion"
    assert _text_field(result, "remote_capsule_dir") == "/opt/konnaxion/capsules"
    assert _text_field(result, "domain") == "app.example.com"
    assert _bool_field(result, "confirmed") is True


# ---------------------------------------------------------------------------
# Action payload validation
# ---------------------------------------------------------------------------

def test_validate_action_payload_rejects_unknown_action() -> None:
    validate_action_payload = _require_function("validate_action_payload")

    _assert_invalid(validate_action_payload, {"action": "not_a_real_action"})


def test_validate_action_payload_accepts_known_action_with_valid_payload() -> None:
    validate_action_payload = _require_function("validate_action_payload")

    result = validate_action_payload(
        {
            "action": "set_network_profile",
            "instance_id": "demo-001",
            "network_profile": "intranet_private",
            "exposure_mode": "private",
        }
    )

    assert _text_field(result, "action") == "set_network_profile"
    assert _text_field(result, "instance_id") == "demo-001"
    assert _text_field(result, "network_profile") == "intranet_private"
    assert _text_field(result, "exposure_mode") == "private"


def test_validate_action_payload_rejects_invalid_canonical_network_values() -> None:
    validate_action_payload = _require_function("validate_action_payload")

    _assert_invalid(
        validate_action_payload,
        {
            "action": "set_network_profile",
            "instance_id": "demo-001",
            "network_profile": "public_vps",
            "exposure_mode": "private",
        },
    )