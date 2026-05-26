# tests/test_ui_page_deploy.py

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html.parser import HTMLParser
from typing import Any

from kx_manager.ui.page_parts.deploy import render


TARGET_ACTIONS: set[str] = {
    "set_target_local",
    "set_target_intranet",
    "set_target_temporary_public",
    "set_target_droplet",
}


DEPLOYMENT_ACTIONS: set[str] = {
    "deploy_local",
    "deploy_intranet",
    "deploy_droplet",
    "bootstrap_droplet_agent",
    "check_droplet_agent",
    "copy_capsule_to_droplet",
    "start_droplet_instance",
}


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
)


DROPLET_CAPSULE_NOT_REQUIRED_ACTIONS: tuple[str, ...] = (
    "bootstrap_droplet_agent",
    "check_droplet_agent",
    "start_droplet_instance",
)


DROPLET_REQUIRED_VISIBLE_FIELDS: tuple[str, ...] = (
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


DROPLET_VISIBLE_OPTIONAL_FIELDS: tuple[str, ...] = (
    "remote_agent_url",
    "confirmed",
)


DROPLET_CANONICAL_VALUES: dict[str, str] = {
    "target_mode": "droplet",
    "network_profile": "public_vps",
    "exposure_mode": "public",
    "public_mode_enabled": "true",
    "public_mode_expires_at": "",
    "confirmed": "true",
}


LOOPBACK_REMOTE_AGENT_URLS: tuple[str, ...] = (
    "http://127.0.0.1:18765/v1",
    "http://127.0.0.1:8765/v1",
    "http://localhost:18765/v1",
    "http://localhost:8765/v1",
)


DOCUMENTATION_REMOTE_AGENT_URLS: set[str] = {
    "http://203.0.113.10:8765/v1",
    "http://192.0.2.10:8765/v1",
    "http://198.51.100.10:8765/v1",
}


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag_name = tag.lower()
        attr_map = {key: value or "" for key, value in attrs}

        if tag_name == "form":
            self._current = {
                "attrs": attr_map,
                "inputs": [],
                "selects": [],
            }
            return

        if self._current is None:
            return

        if tag_name == "input":
            name = attr_map.get("name")
            if not name:
                return
            self._current["inputs"].append(attr_map)
            return

        if tag_name == "select":
            name = attr_map.get("name")
            if not name:
                return
            self._current["selects"].append(attr_map)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "form" or self._current is None:
            return

        self.forms.append(self._current)
        self._current = None


def _forms_from_html(html: str) -> list[dict[str, Any]]:
    parser = _FormParser()
    parser.feed(html)
    return parser.forms


def _controls(form: Mapping[str, Any]) -> list[Mapping[str, str]]:
    inputs = form.get("inputs", [])
    selects = form.get("selects", [])

    assert isinstance(inputs, Sequence)
    assert isinstance(selects, Sequence)

    return [
        item
        for item in [*inputs, *selects]
        if isinstance(item, Mapping)
    ]


def _input_attrs(form: Mapping[str, Any], name: str) -> list[Mapping[str, str]]:
    return [item for item in _controls(form) if item.get("name") == name]


def _visible_input_attrs(form: Mapping[str, Any], name: str) -> list[Mapping[str, str]]:
    return [
        item
        for item in _input_attrs(form, name)
        if str(item.get("type", "")).lower() != "hidden"
    ]


def _input_values(form: Mapping[str, Any], name: str) -> list[str]:
    return [str(item.get("value", "")) for item in _input_attrs(form, name)]


def _has_input(form: Mapping[str, Any], name: str) -> bool:
    return bool(_input_attrs(form, name))


def _has_visible_input(form: Mapping[str, Any], name: str) -> bool:
    return bool(_visible_input_attrs(form, name))


def _has_input_value(form: Mapping[str, Any], name: str, value: str) -> bool:
    return value in _input_values(form, name)


def _first_input_value(form: Mapping[str, Any], name: str) -> str:
    values = _input_values(form, name)
    assert values, f"missing input {name!r} in form {form!r}"
    return values[0]


def _form_action(form: Mapping[str, Any]) -> str:
    return _first_input_value(form, "action")


def _form_for_action(
    forms: Sequence[Mapping[str, Any]],
    action: str,
) -> Mapping[str, Any]:
    matches = [form for form in forms if _form_action(form) == action]
    assert matches, f"missing form for action={action!r}"
    return matches[0]


def _all_input_values(form: Mapping[str, Any]) -> set[str]:
    return {
        str(item.get("value", ""))
        for item in _controls(form)
    }


def _assert_visible_required_control(
    form: Mapping[str, Any],
    name: str,
) -> None:
    controls = _visible_input_attrs(form, name)
    assert controls, f"missing visible control {name!r}"

    assert any("required" in item for item in controls), (
        f"visible control {name!r} is not required"
    )


def test_deploy_page_renders_all_required_deployment_actions() -> None:
    html = render({})
    forms = _forms_from_html(html)
    actions = {_form_action(form) for form in forms}

    assert DEPLOYMENT_ACTIONS <= actions


def test_deploy_page_does_not_render_target_configuration_actions() -> None:
    html = render({})
    forms = _forms_from_html(html)
    actions = {_form_action(form) for form in forms}

    assert TARGET_ACTIONS.isdisjoint(actions)


def test_deploy_page_uses_canonical_action_routes() -> None:
    html = render({})
    forms = _forms_from_html(html)

    for action in DEPLOYMENT_ACTIONS:
        form = _form_for_action(forms, action)
        attrs = form["attrs"]

        assert attrs.get("method", "").lower() == "post"
        assert attrs.get("action") == f"/ui/actions/{action.replace('_', '-')}"


def test_deploy_page_renders_droplet_actions_in_workflow_order() -> None:
    html = render({})
    forms = _forms_from_html(html)

    actual_order = [
        _form_action(form)
        for form in forms
        if _form_action(form) in DROPLET_OPERATION_ACTIONS
    ]

    assert actual_order == list(DROPLET_OPERATION_ACTIONS)


def test_deploy_page_renders_bootstrap_before_droplet_deploy() -> None:
    html = render({})
    forms = _forms_from_html(html)

    droplet_actions = [
        _form_action(form)
        for form in forms
        if _form_action(form) in DROPLET_OPERATION_ACTIONS
    ]

    assert droplet_actions.index("bootstrap_droplet_agent") < droplet_actions.index(
        "check_droplet_agent"
    )
    assert droplet_actions.index("bootstrap_droplet_agent") < droplet_actions.index(
        "deploy_droplet"
    )


def test_local_and_intranet_deploy_forms_submit_canonical_target_values() -> None:
    html = render({})
    forms = _forms_from_html(html)

    local_form = _form_for_action(forms, "deploy_local")
    assert _has_input_value(local_form, "target_mode", "local")
    assert _has_input_value(local_form, "network_profile", "local_only")
    assert _has_input_value(local_form, "exposure_mode", "private")
    assert not _has_input_value(local_form, "confirmed", "true")

    intranet_form = _form_for_action(forms, "deploy_intranet")
    assert _has_input_value(intranet_form, "target_mode", "intranet")
    assert _has_input_value(intranet_form, "network_profile", "intranet_private")
    assert _has_input_value(intranet_form, "exposure_mode", "private")
    assert not _has_input_value(intranet_form, "confirmed", "true")


def test_private_deploy_forms_do_not_submit_droplet_fields() -> None:
    html = render({})
    forms = _forms_from_html(html)

    for action in ("deploy_local", "deploy_intranet"):
        form = _form_for_action(forms, action)

        assert not _has_input(form, "droplet_name"), action
        assert not _has_input(form, "droplet_host"), action
        assert not _has_input(form, "droplet_user"), action
        assert not _has_input(form, "ssh_key_path"), action
        assert not _has_input(form, "remote_kx_root"), action
        assert not _has_input(form, "remote_capsule_dir"), action
        assert not _has_input(form, "droplet_domain"), action
        assert not _has_input_value(form, "network_profile", "public_vps"), action
        assert not _has_input_value(form, "exposure_mode", "public"), action


def test_droplet_operation_forms_submit_canonical_public_vps_values() -> None:
    html = render({})
    forms = _forms_from_html(html)

    for action in DROPLET_OPERATION_ACTIONS:
        form = _form_for_action(forms, action)

        for name, value in DROPLET_CANONICAL_VALUES.items():
            assert _has_input_value(form, name, value), action


def test_droplet_operation_forms_keep_required_public_fields_visible() -> None:
    html = render(
        {
            "instance_id": "demo-001",
            "capsule_file": "/tmp/demo.kxcap",
            "droplet_host": "203.0.113.10",
            "droplet_user": "konnaxion",
            "ssh_key_path": "/tmp/kx_test_key",
            "remote_kx_root": "/opt/konnaxion",
            "remote_capsule_dir": "/opt/konnaxion/capsules",
            "domain": "demo.example.com",
        }
    )
    forms = _forms_from_html(html)

    for action in DROPLET_OPERATION_ACTIONS:
        form = _form_for_action(forms, action)

        for field_name in DROPLET_REQUIRED_VISIBLE_FIELDS:
            _assert_visible_required_control(form, field_name)

        for field_name in DROPLET_VISIBLE_OPTIONAL_FIELDS:
            assert _has_visible_input(form, field_name), (
                f"{action} missing visible {field_name!r}"
            )


def test_droplet_capsule_actions_include_visible_capsule_file() -> None:
    html = render({"capsule_file": "/tmp/demo.kxcap"})
    forms = _forms_from_html(html)

    for action in DROPLET_CAPSULE_REQUIRED_ACTIONS:
        form = _form_for_action(forms, action)

        _assert_visible_required_control(form, "capsule_file")
        assert _has_input_value(form, "capsule_file", "/tmp/demo.kxcap"), action


def test_non_capsule_droplet_actions_do_not_include_capsule_file() -> None:
    html = render({"capsule_file": "/tmp/demo.kxcap"})
    forms = _forms_from_html(html)

    for action in DROPLET_CAPSULE_NOT_REQUIRED_ACTIONS:
        form = _form_for_action(forms, action)

        assert not _has_input(form, "capsule_file"), action
        assert not _has_input(form, "capsule_path"), action


def test_start_droplet_instance_does_not_require_capsule_file() -> None:
    html = render({"capsule_file": "/tmp/demo.kxcap"})
    forms = _forms_from_html(html)
    form = _form_for_action(forms, "start_droplet_instance")

    assert not _has_input(form, "capsule_file")
    assert not _has_input(form, "capsule_path")
    assert _has_input(form, "instance_id")


def test_droplet_operation_forms_do_not_submit_intranet_payload() -> None:
    html = render({})
    forms = _forms_from_html(html)

    for action in DROPLET_OPERATION_ACTIONS:
        form = _form_for_action(forms, action)
        values = _all_input_values(form)

        assert "intranet" not in values, action
        assert "intranet_private" not in values, action
        assert "private" not in values, action
        assert "konnaxion.local" not in values, action


def test_droplet_context_values_propagate_to_operation_forms() -> None:
    context = {
        "instance_id": "demo-prod-001",
        "capsule_file": "/tmp/konnaxion-prod.kxcap",
        "droplet_name": "konnaxion-prod-01",
        "droplet_host": "138.197.174.76",
        "droplet_user": "root",
        "ssh_key_path": "/tmp/id_ed25519",
        "ssh_port": "2222",
        "remote_kx_root": "/opt/konnaxion",
        "remote_capsule_dir": "/opt/konnaxion/capsules",
        "domain": "app.example.com",
        "remote_agent_url": "",
    }

    html = render(context)
    forms = _forms_from_html(html)

    for action in DROPLET_OPERATION_ACTIONS:
        form = _form_for_action(forms, action)

        assert _has_input_value(form, "instance_id", "demo-prod-001"), action
        assert _has_input_value(form, "droplet_name", "konnaxion-prod-01"), action
        assert _has_input_value(form, "droplet_host", "138.197.174.76"), action
        assert _has_input_value(form, "droplet_user", "root"), action
        assert _has_input_value(form, "ssh_key_path", "/tmp/id_ed25519"), action
        assert _has_input_value(form, "ssh_port", "2222"), action
        assert _has_input_value(form, "remote_kx_root", "/opt/konnaxion"), action
        assert _has_input_value(
            form,
            "remote_capsule_dir",
            "/opt/konnaxion/capsules",
        ), action
        assert _has_input_value(form, "domain", "app.example.com"), action
        assert _has_input_value(form, "droplet_domain", "app.example.com"), action
        assert _has_input_value(form, "remote_agent_url", ""), action


def test_droplet_domain_alias_propagates_to_operation_forms() -> None:
    context = {
        "droplet_host": "138.197.174.76",
        "droplet_domain": "app.example.com",
    }

    html = render(context)
    forms = _forms_from_html(html)

    for action in DROPLET_OPERATION_ACTIONS:
        form = _form_for_action(forms, action)

        assert _has_input_value(form, "domain", "app.example.com"), action
        assert _has_input_value(form, "droplet_domain", "app.example.com"), action


def test_public_host_alias_propagates_to_operation_forms() -> None:
    context = {
        "droplet_host": "138.197.174.76",
        "public_host": "public.example.com",
    }

    html = render(context)
    forms = _forms_from_html(html)

    for action in DROPLET_OPERATION_ACTIONS:
        form = _form_for_action(forms, action)

        assert _has_input_value(form, "domain", "public.example.com"), action
        assert _has_input_value(form, "droplet_domain", "public.example.com"), action


def test_droplet_operation_forms_preserve_explicit_non_loopback_remote_agent_url() -> None:
    context = {
        "droplet_host": "138.197.174.76",
        "remote_agent_url": "http://138.197.174.76:8765/v1",
    }

    html = render(context)
    forms = _forms_from_html(html)

    for action in DROPLET_OPERATION_ACTIONS:
        form = _form_for_action(forms, action)

        assert _has_input_value(
            form,
            "remote_agent_url",
            "http://138.197.174.76:8765/v1",
        ), action


def test_droplet_operation_forms_default_remote_agent_url_to_blank() -> None:
    html = render({})
    forms = _forms_from_html(html)

    for action in DROPLET_OPERATION_ACTIONS:
        form = _form_for_action(forms, action)

        assert _has_input(form, "remote_agent_url"), action
        assert _has_input_value(form, "remote_agent_url", ""), action


def test_droplet_operation_forms_blank_loopback_remote_agent_urls() -> None:
    for remote_agent_url in LOOPBACK_REMOTE_AGENT_URLS:
        html = render(
            {
                "droplet_host": "138.197.174.76",
                "remote_agent_url": remote_agent_url,
            }
        )
        forms = _forms_from_html(html)

        for action in DROPLET_OPERATION_ACTIONS:
            form = _form_for_action(forms, action)

            assert _has_input(form, "remote_agent_url"), action
            assert _has_input_value(form, "remote_agent_url", ""), action
            assert not _has_input_value(form, "remote_agent_url", remote_agent_url), (
                action,
                remote_agent_url,
            )


def test_deploy_page_does_not_invent_domain_from_droplet_host() -> None:
    html = render({"droplet_host": "138.197.174.76"})
    forms = _forms_from_html(html)

    for action in DROPLET_OPERATION_ACTIONS:
        form = _form_for_action(forms, action)

        assert _has_input_value(form, "droplet_host", "138.197.174.76"), action
        assert _has_input_value(form, "domain", ""), action
        assert _has_input_value(form, "droplet_domain", ""), action
        assert not _has_input_value(form, "domain", "138.197.174.76"), action
        assert not _has_input_value(form, "droplet_domain", "138.197.174.76"), action


def test_deploy_page_does_not_invent_remote_agent_url_from_droplet_host() -> None:
    html = render({"droplet_host": "138.197.174.76"})
    forms = _forms_from_html(html)

    invented_url = "http://138.197.174.76:8765/v1"

    for action in DROPLET_OPERATION_ACTIONS:
        form = _form_for_action(forms, action)

        assert _has_input_value(form, "droplet_host", "138.197.174.76"), action
        assert _has_input_value(form, "remote_agent_url", ""), action
        assert not _has_input_value(form, "remote_agent_url", invented_url), action


def test_deploy_page_does_not_default_to_documentation_placeholder_agent_url() -> None:
    html = render({})
    forms = _forms_from_html(html)

    for action in DROPLET_OPERATION_ACTIONS:
        form = _form_for_action(forms, action)
        values = _all_input_values(form)

        assert DOCUMENTATION_REMOTE_AGENT_URLS.isdisjoint(values), action


def test_droplet_operation_forms_keep_public_vps_expiration_blank() -> None:
    html = render({})
    forms = _forms_from_html(html)

    for action in DROPLET_OPERATION_ACTIONS:
        form = _form_for_action(forms, action)

        assert _has_input(form, "public_mode_expires_at"), action
        assert _has_input_value(form, "public_mode_expires_at", ""), action