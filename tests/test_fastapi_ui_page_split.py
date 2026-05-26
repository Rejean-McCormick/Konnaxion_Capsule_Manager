# tests/test_fastapi_ui_page_split.py

from __future__ import annotations

import re
from pathlib import Path

import pytest


DROPLET_OPERATION_ACTIONS: tuple[str, ...] = (
    "bootstrap_droplet_agent",
    "check_droplet_agent",
    "copy_capsule_to_droplet",
    "deploy_droplet",
    "start_droplet_instance",
)

DROPLET_CAPSULE_REQUIRED_ACTIONS: tuple[str, ...] = (
    "deploy_droplet",
    "copy_capsule_to_droplet",
    "start_droplet_instance",
)

DROPLET_CAPSULE_OPTIONAL_ACTIONS: tuple[str, ...] = (
    "bootstrap_droplet_agent",
    "check_droplet_agent",
)

DROPLET_REQUIRED_PUBLIC_FIELDS: tuple[str, ...] = (
    "instance_id",
    "droplet_name",
    "droplet_host",
    "droplet_user",
    "ssh_key_path",
    "ssh_port",
    "remote_kx_root",
    "remote_capsule_dir",
    "domain",
)


def _form_for_action(html: str, action: str) -> str:
    route = f"/ui/actions/{action.replace('_', '-')}"
    match = re.search(
        rf'<form[^>]+action="{re.escape(route)}"[^>]*>.*?</form>',
        html,
        flags=re.DOTALL,
    )
    assert match, f"missing form for {action}"
    return match.group(0)


def _assert_no_form_for_action(html: str, action: str) -> None:
    route = f"/ui/actions/{action.replace('_', '-')}"
    assert f'action="{route}"' not in html, f"unexpected form for {action}"


def _control_for_name(form: str, name: str) -> str:
    match = re.search(
        rf'<(?:input|select|textarea)\b[^>]*\bname="{re.escape(name)}"[^>]*>',
        form,
        flags=re.DOTALL,
    )
    assert match, f"missing control {name!r} in form:\n{form}"
    return match.group(0)


def _assert_hidden_value(form: str, name: str, value: str) -> None:
    assert f'name="{name}" value="{value}"' in form


def _assert_visible_required_control(form: str, name: str) -> None:
    control = _control_for_name(form, name)
    assert 'type="hidden"' not in control, f"{name!r} must be visible, got: {control}"
    assert "required" in control, f"{name!r} must be required, got: {control}"


def _valid_droplet_payload(tmp_path: Path) -> dict[str, str]:
    ssh_key_path = tmp_path / "id_ed25519"
    ssh_key_path.write_text("not-a-real-key-for-validation-only", encoding="utf-8")

    source_dir = tmp_path / "source"
    source_dir.mkdir()

    capsule_file = tmp_path / "demo.kxcap"

    return {
        "action": "deploy_droplet",
        "target_mode": "droplet",
        "network_profile": "public_vps",
        "exposure_mode": "public",
        "confirmed": "true",
        "instance_id": "demo-001",
        "capsule_file": str(capsule_file),
        "source_dir": str(source_dir),
        "droplet_host": "203.0.113.10",
        "droplet_user": "konnaxion",
        "ssh_key_path": str(ssh_key_path),
        "remote_kx_root": "/opt/konnaxion",
        "remote_capsule_dir": "/opt/konnaxion/capsules",
        "domain": "demo.example.com",
    }


def _droplet_context() -> dict[str, str]:
    return {
        "instance_id": "demo-001",
        "capsule_file": "/tmp/demo.kxcap",
        "droplet_host": "203.0.113.10",
        "droplet_user": "konnaxion",
        "ssh_key_path": "/tmp/kx_test_key",
        "remote_kx_root": "/opt/konnaxion",
        "remote_capsule_dir": "/opt/konnaxion/capsules",
        "domain": "demo.example.com",
    }


def test_page_views_are_flat_page_part_orchestrator() -> None:
    from kx_manager.ui.page_parts import PAGE_PART_BUILDERS
    from kx_manager.ui.page_views import PAGE_ROUTES, PAGE_VIEWS
    from kx_manager.ui.static import UI_PAGE_ROUTES

    assert PAGE_ROUTES == UI_PAGE_ROUTES
    assert "/ui/deploy" in PAGE_ROUTES
    assert set(PAGE_VIEWS) == set(PAGE_ROUTES)
    assert set(PAGE_PART_BUILDERS) == set(PAGE_ROUTES)

    for route, page in PAGE_VIEWS.items():
        assert page.route == route
        assert page.builder.__module__.startswith("kx_manager.ui.page_parts.")
        assert page.builder.__name__ == "render"

    assert PAGE_VIEWS["/ui/deploy"].builder.__module__ == (
        "kx_manager.ui.page_parts.deploy"
    )


def test_droplet_payload_forces_public_vps_without_intranet_defaults() -> None:
    from kx_manager.ui.page_parts.common import droplet_payload

    payload = droplet_payload(
        {
            "instance_id": "demo-001",
            "host": "203.0.113.10",
            "capsule_path": "/tmp/demo.kxcap",
            "runtime_root": "/srv/incorrect-if-inherited",
            "capsule_dir": "/srv/incorrect-if-inherited/capsules",
        }
    )

    assert payload["target_mode"] == "droplet"
    assert payload["network_profile"] == "public_vps"
    assert payload["exposure_mode"] == "public"
    assert payload["confirmed"] == "true"
    assert payload["droplet_host"] == "203.0.113.10"
    assert payload["host"] == "203.0.113.10"
    assert payload["droplet_user"] == "konnaxion"
    assert payload["remote_kx_root"] == "/srv/incorrect-if-inherited"
    assert payload["remote_capsule_dir"] == "/srv/incorrect-if-inherited/capsules"


def test_droplet_payload_does_not_synthesize_domain_from_ip() -> None:
    from kx_manager.ui.page_parts.common import droplet_payload

    payload = droplet_payload(
        {
            "instance_id": "demo-001",
            "droplet_host": "203.0.113.10",
            "capsule_path": "/tmp/demo.kxcap",
        }
    )

    assert payload["target_mode"] == "droplet"
    assert payload["droplet_host"] == "203.0.113.10"
    assert payload["domain"] == ""
    assert payload["droplet_domain"] == ""


def test_droplet_payload_preserves_explicit_domain_aliases() -> None:
    from kx_manager.ui.page_parts.common import droplet_payload

    payload = droplet_payload(
        {
            "instance_id": "demo-001",
            "droplet_host": "203.0.113.10",
            "capsule_path": "/tmp/demo.kxcap",
            "domain": "demo.example.com",
        }
    )

    assert payload["domain"] == "demo.example.com"
    assert payload["droplet_domain"] == "demo.example.com"


def test_normalize_payload_aliases_does_not_synthesize_droplet_domain() -> None:
    from kx_manager.ui.static import normalize_payload_aliases

    payload = normalize_payload_aliases(
        {
            "target_mode": "droplet",
            "droplet_host": "203.0.113.10",
        }
    )

    assert payload["droplet_host"] == "203.0.113.10"
    assert payload["host"] == "203.0.113.10"
    assert payload.get("domain", "") == ""
    assert payload.get("droplet_domain", "") == ""


def test_targets_page_contains_target_configuration_forms_only() -> None:
    from kx_manager.ui.page_parts.targets import render

    html = render(_droplet_context())

    for action in (
        "set_target_local",
        "set_target_intranet",
        "set_target_temporary_public",
        "set_target_droplet",
    ):
        _form_for_action(html, action)

    for action in (
        "deploy_local",
        "deploy_intranet",
        *DROPLET_OPERATION_ACTIONS,
    ):
        _assert_no_form_for_action(html, action)


def test_targets_page_droplet_target_form_submits_canonical_values() -> None:
    from kx_manager.ui.page_parts.targets import render

    html = render(_droplet_context())
    form = _form_for_action(html, "set_target_droplet")

    _assert_hidden_value(form, "target_mode", "droplet")
    _assert_hidden_value(form, "network_profile", "public_vps")
    _assert_hidden_value(form, "exposure_mode", "public")
    _assert_hidden_value(form, "public_mode_enabled", "true")

    for field_name in DROPLET_REQUIRED_PUBLIC_FIELDS:
        _assert_visible_required_control(form, field_name)

    assert 'name="domain"' in form
    assert 'value="demo.example.com"' in form
    assert 'name="capsule_file"' not in form


def test_deploy_page_contains_deployment_operation_forms() -> None:
    from kx_manager.ui.page_parts.deploy import render

    html = render(_droplet_context())

    for action in (
        "deploy_local",
        "deploy_intranet",
        *DROPLET_OPERATION_ACTIONS,
    ):
        _form_for_action(html, action)

    for action in (
        "set_target_local",
        "set_target_intranet",
        "set_target_temporary_public",
        "set_target_droplet",
    ):
        _assert_no_form_for_action(html, action)


def test_deploy_page_droplet_cards_are_in_workflow_order() -> None:
    from kx_manager.ui.page_parts.deploy import render

    html = render(_droplet_context())

    positions = [
        html.index(f"/ui/actions/{action.replace('_', '-')}")
        for action in DROPLET_OPERATION_ACTIONS
    ]

    assert positions == sorted(positions)


def test_deploy_page_local_and_intranet_forms_submit_forced_values() -> None:
    from kx_manager.ui.page_parts.deploy import render

    html = render(_droplet_context())

    local_form = _form_for_action(html, "deploy_local")
    _assert_hidden_value(local_form, "target_mode", "local")
    _assert_hidden_value(local_form, "network_profile", "local_only")
    _assert_hidden_value(local_form, "exposure_mode", "private")

    intranet_form = _form_for_action(html, "deploy_intranet")
    _assert_hidden_value(intranet_form, "target_mode", "intranet")
    _assert_hidden_value(intranet_form, "network_profile", "intranet_private")
    _assert_hidden_value(intranet_form, "exposure_mode", "private")


def test_deploy_page_droplet_operation_forms_submit_droplet_values() -> None:
    from kx_manager.ui.page_parts.deploy import render

    html = render(_droplet_context())

    for action in DROPLET_OPERATION_ACTIONS:
        form = _form_for_action(html, action)

        _assert_hidden_value(form, "target_mode", "droplet")
        _assert_hidden_value(form, "network_profile", "public_vps")
        _assert_hidden_value(form, "exposure_mode", "public")
        _assert_hidden_value(form, "public_mode_enabled", "true")
        _assert_hidden_value(form, "confirmed", "true")

        assert 'name="droplet_host"' in form
        assert 'name="droplet_user"' in form
        assert 'name="ssh_key_path"' in form
        assert 'name="remote_kx_root"' in form
        assert 'name="remote_capsule_dir"' in form
        assert 'name="domain"' in form
        assert 'value="demo.example.com"' in form


def test_deploy_page_droplet_operation_forms_keep_required_public_fields_visible() -> None:
    from kx_manager.ui.page_parts.deploy import render

    html = render(_droplet_context())

    for action in DROPLET_OPERATION_ACTIONS:
        form = _form_for_action(html, action)

        for field_name in DROPLET_REQUIRED_PUBLIC_FIELDS:
            _assert_visible_required_control(form, field_name)

    for action in DROPLET_CAPSULE_OPTIONAL_ACTIONS:
        form = _form_for_action(html, action)
        assert 'name="capsule_file"' not in form

    for action in DROPLET_CAPSULE_REQUIRED_ACTIONS:
        form = _form_for_action(html, action)
        _assert_visible_required_control(form, "capsule_file")


def test_droplet_action_payload_validation_forces_canonical_values(tmp_path: Path) -> None:
    from kx_manager.ui.form_registry import validate_action_payload

    payload = _valid_droplet_payload(tmp_path)
    payload.update(
        {
            "target_mode": "intranet",
            "network_profile": "intranet_private",
            "exposure_mode": "private",
            "confirmed": "false",
        }
    )

    result = validate_action_payload(payload)

    assert result["action"] == "deploy_droplet"
    assert result["target_mode"] == "droplet"
    assert result["network_profile"] == "public_vps"
    assert result["exposure_mode"] == "public"
    assert result["confirmed"] is True
    assert result["droplet_host"] == "203.0.113.10"
    assert result["host"] == "203.0.113.10"
    assert result["domain"] == "demo.example.com"
    assert result["droplet_domain"] == "demo.example.com"
    assert result["capsule_path"] == payload["capsule_file"]


def test_bootstrap_droplet_agent_payload_validation_does_not_require_capsule_file(
    tmp_path: Path,
) -> None:
    from kx_manager.ui.form_registry import validate_action_payload

    payload = _valid_droplet_payload(tmp_path)
    payload["action"] = "bootstrap_droplet_agent"
    payload.pop("capsule_file")

    result = validate_action_payload(payload)

    assert result["action"] == "bootstrap_droplet_agent"
    assert result["target_mode"] == "droplet"
    assert result["network_profile"] == "public_vps"
    assert result["exposure_mode"] == "public"
    assert result["confirmed"] is True
    assert result["droplet_host"] == "203.0.113.10"
    assert result["domain"] == "demo.example.com"
    assert "capsule_file" not in result
    assert "capsule_path" not in result


def test_check_droplet_agent_payload_validation_does_not_require_capsule_file(
    tmp_path: Path,
) -> None:
    from kx_manager.ui.form_registry import validate_action_payload

    payload = _valid_droplet_payload(tmp_path)
    payload["action"] = "check_droplet_agent"
    payload.pop("capsule_file")

    result = validate_action_payload(payload)

    assert result["action"] == "check_droplet_agent"
    assert result["target_mode"] == "droplet"
    assert result["network_profile"] == "public_vps"
    assert result["exposure_mode"] == "public"
    assert result["confirmed"] is True
    assert result["droplet_host"] == "203.0.113.10"
    assert result["domain"] == "demo.example.com"
    assert "capsule_file" not in result
    assert "capsule_path" not in result


def test_droplet_action_payload_validation_rejects_missing_domain(tmp_path: Path) -> None:
    from kx_manager.ui.form_registry import validate_action_payload

    payload = _valid_droplet_payload(tmp_path)
    payload["domain"] = ""

    with pytest.raises(Exception):
        validate_action_payload(payload)