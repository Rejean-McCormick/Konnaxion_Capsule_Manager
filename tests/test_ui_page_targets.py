# tests/test_ui_page_targets.py

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html.parser import HTMLParser
from typing import Any

from kx_manager.ui.page_parts.targets import render


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
    "check_droplet_agent",
    "copy_capsule_to_droplet",
    "start_droplet_instance",
}


DROPLET_TARGET_ACTIONS: tuple[str, ...] = (
    "set_target_droplet",
)


DROPLET_REQUIRED_INPUTS: set[str] = {
    "action",
    "target_mode",
    "network_profile",
    "exposure_mode",
    "public_mode_enabled",
    "instance_id",
    "droplet_name",
    "droplet_host",
    "droplet_user",
    "ssh_key_path",
    "ssh_port",
    "remote_kx_root",
    "remote_capsule_dir",
    "domain",
    "remote_agent_url",
    "confirmed",
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
            }
            return

        if self._current is None:
            return

        if tag_name == "input":
            name = attr_map.get("name")
            if not name:
                return

            self._current["inputs"].append(attr_map)

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


def _input_attrs(form: Mapping[str, Any], name: str) -> list[Mapping[str, str]]:
    inputs = form.get("inputs", [])
    assert isinstance(inputs, Sequence)

    return [
        item
        for item in inputs
        if isinstance(item, Mapping) and item.get("name") == name
    ]


def _input_values(form: Mapping[str, Any], name: str) -> list[str]:
    return [str(item.get("value", "")) for item in _input_attrs(form, name)]


def _has_input(form: Mapping[str, Any], name: str) -> bool:
    return bool(_input_attrs(form, name))


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
    inputs = form.get("inputs", [])
    assert isinstance(inputs, Sequence)

    return {
        str(item.get("value", ""))
        for item in inputs
        if isinstance(item, Mapping)
    }


def test_targets_page_renders_all_required_target_actions() -> None:
    html = render({})
    forms = _forms_from_html(html)
    actions = {_form_action(form) for form in forms}

    assert TARGET_ACTIONS <= actions


def test_targets_page_does_not_render_deployment_action_forms() -> None:
    html = render({})
    forms = _forms_from_html(html)
    actions = {_form_action(form) for form in forms}

    assert DEPLOYMENT_ACTIONS.isdisjoint(actions)


def test_targets_page_uses_canonical_action_routes() -> None:
    html = render({})
    forms = _forms_from_html(html)

    for action in TARGET_ACTIONS:
        form = _form_for_action(forms, action)
        attrs = form["attrs"]

        assert attrs.get("method", "").lower() == "post"
        assert attrs.get("action") == f"/ui/actions/{action.replace('_', '-')}"


def test_droplet_target_form_submits_canonical_public_vps_values() -> None:
    html = render({})
    forms = _forms_from_html(html)

    for action in DROPLET_TARGET_ACTIONS:
        form = _form_for_action(forms, action)

        assert _has_input_value(form, "target_mode", "droplet"), action
        assert _has_input_value(form, "network_profile", "public_vps"), action
        assert _has_input_value(form, "exposure_mode", "public"), action
        assert _has_input_value(form, "public_mode_enabled", "true"), action
        assert _has_input_value(form, "confirmed", "true"), action


def test_droplet_target_form_includes_required_public_fields() -> None:
    html = render({})
    forms = _forms_from_html(html)
    form = _form_for_action(forms, "set_target_droplet")

    for name in DROPLET_REQUIRED_INPUTS:
        assert _has_input(form, name), f"set_target_droplet missing {name}"


def test_droplet_target_form_does_not_require_capsule_file() -> None:
    html = render({})
    forms = _forms_from_html(html)
    form = _form_for_action(forms, "set_target_droplet")

    assert not _has_input(form, "capsule_file")
    assert not _has_input(form, "capsule_path")


def test_droplet_target_form_does_not_submit_intranet_defaults() -> None:
    html = render({})
    forms = _forms_from_html(html)

    for action in DROPLET_TARGET_ACTIONS:
        form = _form_for_action(forms, action)
        values = _all_input_values(form)

        assert "intranet" not in values, action
        assert "intranet_private" not in values, action
        assert "konnaxion.local" not in values, action


def test_private_target_forms_do_not_submit_droplet_fields() -> None:
    html = render({})
    forms = _forms_from_html(html)

    for action in (
        "set_target_local",
        "set_target_intranet",
        "set_target_temporary_public",
    ):
        form = _form_for_action(forms, action)

        assert not _has_input(form, "droplet_name")
        assert not _has_input(form, "droplet_host")
        assert not _has_input(form, "droplet_user")
        assert not _has_input(form, "ssh_key_path")
        assert not _has_input(form, "remote_kx_root")
        assert not _has_input(form, "remote_capsule_dir")
        assert not _has_input(form, "droplet_domain")


def test_droplet_context_values_propagate_to_droplet_target_form() -> None:
    context = {
        "instance_id": "demo-prod-001",
        "capsule_file": "/tmp/konnaxion-prod.kxcap",
        "droplet_name": "konnaxion-prod-01",
        "droplet_host": "203.0.113.10",
        "droplet_user": "root",
        "ssh_key_path": "/tmp/id_ed25519",
        "ssh_port": "2222",
        "remote_kx_root": "/opt/konnaxion",
        "remote_capsule_dir": "/opt/konnaxion/capsules",
        "domain": "app.example.com",
        "remote_agent_url": "http://203.0.113.10:8765/v1",
    }

    html = render(context)
    forms = _forms_from_html(html)
    form = _form_for_action(forms, "set_target_droplet")

    assert _has_input_value(form, "instance_id", "demo-prod-001")
    assert _has_input_value(form, "droplet_name", "konnaxion-prod-01")
    assert _has_input_value(form, "droplet_host", "203.0.113.10")
    assert _has_input_value(form, "droplet_user", "root")
    assert _has_input_value(form, "ssh_key_path", "/tmp/id_ed25519")
    assert _has_input_value(form, "ssh_port", "2222")
    assert _has_input_value(form, "remote_kx_root", "/opt/konnaxion")
    assert _has_input_value(
        form,
        "remote_capsule_dir",
        "/opt/konnaxion/capsules",
    )
    assert _has_input_value(form, "domain", "app.example.com")
    assert _has_input_value(
        form,
        "remote_agent_url",
        "http://203.0.113.10:8765/v1",
    )
    assert not _has_input(form, "capsule_file")
    assert not _has_input(form, "capsule_path")