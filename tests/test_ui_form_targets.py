# tests/test_ui_form_targets.py

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from kx_manager.ui.form_errors import FormValidationError
from kx_manager.ui.form_targets import (
    BootstrapDropletAgentForm,
    CheckDropletAgentForm,
    CopyCapsuleToDropletForm,
    DeployDropletForm,
    DropletTargetForm,
    LocalTargetForm,
    StartDropletInstanceForm,
    parse_droplet_operation_form,
    parse_target_form,
)


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _valid_droplet_payload(tmp_path: Path) -> dict[str, Any]:
    source_dir = tmp_path / "Konnaxion"
    source_dir.mkdir(parents=True)

    capsule_dir = tmp_path / "runtime" / "capsules"
    capsule_dir.mkdir(parents=True)

    capsule_file = capsule_dir / "konnaxion-v14-demo-2026.05.04.kxcap"
    capsule_file.write_bytes(b"fake capsule for ui form target tests")

    ssh_key_path = tmp_path / "id_ed25519"
    ssh_key_path.write_text("not-a-real-private-key-for-tests\n", encoding="utf-8")

    return {
        "action": "set_target_droplet",
        "target_mode": "droplet",
        "network_profile": "public_vps",
        "exposure_mode": "public",
        "instance_id": "demo-001",
        "source_dir": str(source_dir),
        "capsule_file": str(capsule_file),
        "capsule_path": str(capsule_file),
        "capsule_id": "konnaxion-v14-demo-2026.05.04",
        "capsule_version": "2026.05.04-demo.1",
        "capsule_output_dir": str(capsule_dir),
        "droplet_name": "konnaxion-prod-01",
        "droplet_host": "203.0.113.10",
        "droplet_user": "root",
        "ssh_key_path": str(ssh_key_path),
        "ssh_port": "22",
        "remote_kx_root": "/opt/konnaxion",
        "remote_capsule_dir": "/opt/konnaxion/capsules",
        "domain": "app.example.com",
        # Blank remote_agent_url is the safe/default Droplet mode:
        # Manager reaches the private Agent through SSH-local curl.
        "remote_agent_url": "",
        "confirmed": "true",
    }


def test_droplet_target_form_accepts_valid_public_vps_payload(tmp_path: Path) -> None:
    payload = _valid_droplet_payload(tmp_path)

    form = DropletTargetForm.from_mapping(payload)
    result = form.to_payload()

    assert _value(form.target_mode) == "droplet"
    assert _value(form.network_profile) == "public_vps"
    assert _value(form.exposure_mode) == "public"
    assert form.instance_id == "demo-001"
    assert form.droplet_host == "203.0.113.10"
    assert form.droplet_user == "root"
    assert form.remote_kx_root == "/opt/konnaxion"
    assert form.remote_capsule_dir == "/opt/konnaxion/capsules"
    assert form.domain == "app.example.com"
    assert form.confirmed is True

    assert result["target_mode"] == "droplet"
    assert result["network_profile"] == "public_vps"
    assert result["exposure_mode"] == "public"

    # Public runtime host for Agent env/Traefik/Django.
    assert result["host"] == "app.example.com"
    assert result["public_host"] == "app.example.com"
    assert result["domain"] == "app.example.com"
    assert result["droplet_domain"] == "app.example.com"

    # SSH/Droplet connection target remains separate from public host.
    assert result["droplet_host"] == "203.0.113.10"
    assert result["target_host"] == "203.0.113.10"

    assert result["runtime_root"] == "/opt/konnaxion"
    assert result["capsule_dir"] == "/opt/konnaxion/capsules"
    assert result["remote_kx_root"] == "/opt/konnaxion"
    assert result["remote_capsule_dir"] == "/opt/konnaxion/capsules"
    assert result["public_mode_enabled"] is True
    assert result["confirmed"] is True

    # Blank means SSH-local Agent transport.
    assert result.get("remote_agent_url") in {"", None}


@pytest.mark.parametrize(
    ("alias_field", "alias_value"),
    [
        ("domain", "app.example.com"),
        ("droplet_domain", "app.example.com"),
        ("public_host", "app.example.com"),
    ],
)
def test_droplet_target_form_normalizes_public_host_aliases(
    tmp_path: Path,
    alias_field: str,
    alias_value: str,
) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload.pop("domain", None)
    payload.pop("droplet_domain", None)
    payload.pop("public_host", None)
    payload[alias_field] = alias_value

    form = DropletTargetForm.from_mapping(payload)
    result = form.to_payload()

    assert form.domain == "app.example.com"
    assert result["domain"] == "app.example.com"
    assert result["droplet_domain"] == "app.example.com"
    assert result["public_host"] == "app.example.com"
    assert result["host"] == "app.example.com"
    assert result["target_host"] == "203.0.113.10"


def test_droplet_target_form_requires_explicit_domain_not_host_fallback(
    tmp_path: Path,
) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload["domain"] = ""
    payload.pop("droplet_domain", None)
    payload.pop("public_host", None)

    with pytest.raises(FormValidationError) as exc_info:
        DropletTargetForm.from_mapping(payload)

    assert exc_info.value.field == "domain"


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
def test_droplet_target_form_requires_public_vps_fields(
    tmp_path: Path,
    missing_field: str,
) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload[missing_field] = ""

    with pytest.raises(Exception):
        DropletTargetForm.from_mapping(payload)


def test_droplet_target_form_accepts_blank_remote_agent_url_for_ssh_transport(
    tmp_path: Path,
) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload["remote_agent_url"] = ""

    form = DropletTargetForm.from_mapping(payload)
    result = form.to_payload()

    assert form.remote_agent_url in {"", None}
    assert result.get("remote_agent_url") in {"", None}


@pytest.mark.parametrize(
    "loopback_url",
    [
        "http://127.0.0.1:18765/v1",
        "http://localhost:18765/v1",
        "http://[::1]:18765/v1",
    ],
)
def test_droplet_target_form_normalizes_loopback_remote_agent_url_to_blank(
    tmp_path: Path,
    loopback_url: str,
) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload["remote_agent_url"] = loopback_url

    form = DropletTargetForm.from_mapping(payload)
    result = form.to_payload()

    # Loopback URLs are stale tunnel/local URLs in Droplet mode.
    # They must not force direct HTTP from Windows.
    assert form.remote_agent_url in {"", None}
    assert result.get("remote_agent_url") in {"", None}


def test_droplet_target_form_accepts_direct_remote_agent_url_on_same_droplet(
    tmp_path: Path,
) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload["remote_agent_url"] = "http://203.0.113.10:8765/v1"

    form = DropletTargetForm.from_mapping(payload)
    result = form.to_payload()

    assert form.remote_agent_url == "http://203.0.113.10:8765/v1"
    assert result["remote_agent_url"] == "http://203.0.113.10:8765/v1"


def test_droplet_target_form_rejects_direct_remote_agent_url_for_other_host(
    tmp_path: Path,
) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload["remote_agent_url"] = "http://198.51.100.25:8765/v1"

    with pytest.raises(FormValidationError) as exc_info:
        DropletTargetForm.from_mapping(payload)

    assert exc_info.value.field == "remote_agent_url"


def test_droplet_target_form_rejects_intranet_profile_drift(tmp_path: Path) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload["network_profile"] = "intranet_private"
    payload["exposure_mode"] = "private"

    with pytest.raises(FormValidationError) as exc_info:
        DropletTargetForm.from_mapping(payload)

    assert exc_info.value.field == "network_profile"


def test_droplet_remote_capsule_dir_must_be_inside_remote_root(
    tmp_path: Path,
) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload["remote_kx_root"] = "/opt/konnaxion"
    payload["remote_capsule_dir"] = "/tmp/capsules"

    with pytest.raises(FormValidationError) as exc_info:
        DropletTargetForm.from_mapping(payload)

    assert exc_info.value.field == "remote_capsule_dir"


@pytest.mark.parametrize(
    "form_model",
    [
        DeployDropletForm,
        CopyCapsuleToDropletForm,
        StartDropletInstanceForm,
    ],
)
def test_droplet_capsule_required_actions_reject_missing_capsule_file(
    tmp_path: Path,
    form_model: type[Any],
) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload.pop("capsule_file", None)
    payload.pop("capsule_path", None)

    with pytest.raises(FormValidationError) as exc_info:
        form_model.from_mapping(payload)

    assert exc_info.value.field == "capsule_file"


@pytest.mark.parametrize(
    "form_model,action",
    [
        (BootstrapDropletAgentForm, "bootstrap_droplet_agent"),
        (CheckDropletAgentForm, "check_droplet_agent"),
    ],
)
def test_droplet_non_capsule_actions_allow_missing_capsule_file(
    tmp_path: Path,
    form_model: type[Any],
    action: str,
) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload["action"] = action
    payload.pop("capsule_file", None)
    payload.pop("capsule_path", None)

    form = form_model.from_mapping(payload)

    assert form.capsule_file is None
    assert _value(form.target_mode) == "droplet"
    assert _value(form.network_profile) == "public_vps"
    assert _value(form.exposure_mode) == "public"


def test_check_droplet_agent_allows_missing_capsule_file(tmp_path: Path) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload["action"] = "check_droplet_agent"
    payload.pop("capsule_file", None)
    payload.pop("capsule_path", None)

    form = CheckDropletAgentForm.from_mapping(payload)

    assert form.capsule_file is None
    assert _value(form.target_mode) == "droplet"
    assert _value(form.network_profile) == "public_vps"
    assert _value(form.exposure_mode) == "public"


def test_bootstrap_droplet_agent_allows_missing_capsule_file(tmp_path: Path) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload["action"] = "bootstrap_droplet_agent"
    payload.pop("capsule_file", None)
    payload.pop("capsule_path", None)

    form = BootstrapDropletAgentForm.from_mapping(payload)

    assert form.capsule_file is None
    assert _value(form.target_mode) == "droplet"
    assert _value(form.network_profile) == "public_vps"
    assert _value(form.exposure_mode) == "public"


def test_parse_droplet_operation_form_routes_start_to_start_form(
    tmp_path: Path,
) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload["action"] = "start_droplet_instance"

    form = parse_droplet_operation_form(payload)

    assert isinstance(form, StartDropletInstanceForm)
    assert form.instance_id == "demo-001"
    assert form.capsule_file is not None
    assert str(form.capsule_file) == payload["capsule_file"]
    assert _value(form.target_mode) == "droplet"
    assert _value(form.network_profile) == "public_vps"
    assert _value(form.exposure_mode) == "public"


def test_start_droplet_instance_payload_preserves_capsule_and_public_runtime_host(
    tmp_path: Path,
) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload["action"] = "start_droplet_instance"

    form = parse_droplet_operation_form(payload)
    result = form.to_payload()

    assert isinstance(form, StartDropletInstanceForm)

    # The start action must carry the capsule path so downstream Agent code
    # can locate the imported capsule/images/*.oci.tar before compose up.
    assert "capsule_file" in result
    assert str(result["capsule_file"]) == payload["capsule_file"]

    # The public runtime host must remain the domain, not the SSH target IP.
    assert result["host"] == "app.example.com"
    assert result["domain"] == "app.example.com"
    assert result["droplet_domain"] == "app.example.com"
    assert result["public_host"] == "app.example.com"

    # The SSH target remains separate.
    assert result["droplet_host"] == "203.0.113.10"
    assert result["target_host"] == "203.0.113.10"

    # Runtime paths must remain available to deploy/start backends.
    assert result["runtime_root"] == "/opt/konnaxion"
    assert result["capsule_dir"] == "/opt/konnaxion/capsules"
    assert result["remote_kx_root"] == "/opt/konnaxion"
    assert result["remote_capsule_dir"] == "/opt/konnaxion/capsules"

    assert result["network_profile"] == "public_vps"
    assert result["exposure_mode"] == "public"
    assert result["confirmed"] is True
    assert result.get("remote_agent_url") in {"", None}


@pytest.mark.parametrize(
    "action",
    [
        "deploy_droplet",
        "bootstrap_droplet_agent",
        "check_droplet_agent",
        "copy_capsule_to_droplet",
        "start_droplet_instance",
    ],
)
def test_droplet_operation_actions_force_canonical_public_vps_values(
    tmp_path: Path,
    action: str,
) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload.update(
        {
            "action": action,
            "target_mode": "intranet",
            "network_profile": "intranet_private",
            "exposure_mode": "private",
            "confirmed": "false",
        }
    )

    form = parse_droplet_operation_form(payload)
    result = form.to_payload()

    assert result["target_mode"] == "droplet"
    assert result["network_profile"] == "public_vps"
    assert result["exposure_mode"] == "public"
    assert result["confirmed"] is True

    # Droplet host is the SSH target.
    assert result["droplet_host"] == "203.0.113.10"
    assert result["target_host"] == "203.0.113.10"

    # Domain is the public runtime host that Agent must receive as host.
    assert result["domain"] == "app.example.com"
    assert result["droplet_domain"] == "app.example.com"
    assert result["public_host"] == "app.example.com"
    assert result["host"] == "app.example.com"

    # Remote runtime paths must remain stable for Droplet Agent operations.
    assert result["runtime_root"] == "/opt/konnaxion"
    assert result["capsule_dir"] == "/opt/konnaxion/capsules"
    assert result["remote_kx_root"] == "/opt/konnaxion"
    assert result["remote_capsule_dir"] == "/opt/konnaxion/capsules"


@pytest.mark.parametrize(
    "action",
    [
        "deploy_droplet",
        "bootstrap_droplet_agent",
        "check_droplet_agent",
        "copy_capsule_to_droplet",
        "start_droplet_instance",
    ],
)
def test_droplet_operation_actions_treat_loopback_remote_agent_url_as_blank(
    tmp_path: Path,
    action: str,
) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload["action"] = action
    payload["remote_agent_url"] = "http://127.0.0.1:18765/v1"

    form = parse_droplet_operation_form(payload)
    result = form.to_payload()

    assert result.get("remote_agent_url") in {"", None}


def test_parse_droplet_operation_form_routes_bootstrap_to_bootstrap_form(
    tmp_path: Path,
) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload["action"] = "bootstrap_droplet_agent"
    payload.pop("capsule_file", None)
    payload.pop("capsule_path", None)

    form = parse_droplet_operation_form(payload)

    assert isinstance(form, BootstrapDropletAgentForm)
    assert form.capsule_file is None
    assert _value(form.target_mode) == "droplet"
    assert _value(form.network_profile) == "public_vps"
    assert _value(form.exposure_mode) == "public"


def test_parse_target_form_routes_droplet_mode_to_droplet_form(tmp_path: Path) -> None:
    payload = _valid_droplet_payload(tmp_path)

    form = parse_target_form(payload)

    assert isinstance(form, DropletTargetForm)
    assert _value(form.target_mode) == "droplet"
    assert _value(form.network_profile) == "public_vps"
    assert _value(form.exposure_mode) == "public"


def test_local_target_rejects_droplet_fields(tmp_path: Path) -> None:
    payload = {
        "target_mode": "local",
        "network_profile": "local_only",
        "exposure_mode": "private",
        "instance_id": "demo-001",
        "runtime_root": str(tmp_path / "runtime"),
        "capsule_dir": str(tmp_path / "runtime" / "capsules"),
        "droplet_host": "203.0.113.10",
        "droplet_user": "root",
        "ssh_key_path": str(tmp_path / "id_ed25519"),
    }

    with pytest.raises(Exception):
        LocalTargetForm.from_mapping(payload)


def test_parse_target_form_rejects_private_target_with_droplet_fields(
    tmp_path: Path,
) -> None:
    payload = {
        "target_mode": "intranet",
        "network_profile": "intranet_private",
        "exposure_mode": "private",
        "instance_id": "demo-001",
        "runtime_root": str(tmp_path / "runtime"),
        "capsule_dir": str(tmp_path / "runtime" / "capsules"),
        "host": "konnaxion.local",
        "droplet_host": "203.0.113.10",
        "droplet_user": "root",
    }

    with pytest.raises(Exception):
        parse_target_form(payload)


def test_parse_target_form_rejects_droplet_mode_with_private_values(
    tmp_path: Path,
) -> None:
    payload = _valid_droplet_payload(tmp_path)
    payload["target_mode"] = "droplet"
    payload["network_profile"] = "intranet_private"
    payload["exposure_mode"] = "private"

    with pytest.raises(FormValidationError):
        parse_target_form(payload)