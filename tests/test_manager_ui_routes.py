from __future__ import annotations

import importlib
import sys
import tempfile
from collections.abc import Mapping, Sequence
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


REQUIRED_PAGE_ROUTES: tuple[str, ...] = (
    "/ui",
    "/ui/capsules",
    "/ui/instances",
    "/ui/security",
    "/ui/network",
    "/ui/backups",
    "/ui/restore",
    "/ui/logs",
    "/ui/health",
    "/ui/settings",
    "/ui/targets",
    "/ui/deploy",
    "/ui/about",
)


TARGET_ACTIONS: tuple[str, ...] = (
    "set_target_local",
    "set_target_intranet",
    "set_target_droplet",
    "set_target_temporary_public",
)


DEPLOYMENT_ACTIONS: tuple[str, ...] = (
    "deploy_local",
    "deploy_intranet",
    "bootstrap_droplet_agent",
    "check_droplet_agent",
    "copy_capsule_to_droplet",
    "deploy_droplet",
    "start_droplet_instance",
)


DROPLET_OPERATION_ACTIONS: tuple[str, ...] = (
    "bootstrap_droplet_agent",
    "check_droplet_agent",
    "copy_capsule_to_droplet",
    "deploy_droplet",
    "start_droplet_instance",
)


DROPLET_CAPSULE_REQUIRED_ACTIONS: tuple[str, ...] = (
    "copy_capsule_to_droplet",
    "deploy_droplet",
    "start_droplet_instance",
)


DROPLET_CAPSULE_NOT_REQUIRED_ACTIONS: tuple[str, ...] = (
    "bootstrap_droplet_agent",
    "check_droplet_agent",
)


REQUIRED_ACTION_ROUTES: dict[str, str] = {
    "/ui/actions/check-manager": "check_manager",
    "/ui/actions/check-agent": "check_agent",
    "/ui/actions/select-source-folder": "select_source_folder",
    "/ui/actions/select-capsule-output-folder": "select_capsule_output_folder",
    "/ui/actions/build-capsule": "build_capsule",
    "/ui/actions/rebuild-capsule": "rebuild_capsule",
    "/ui/actions/verify-capsule": "verify_capsule",
    "/ui/actions/import-capsule": "import_capsule",
    "/ui/actions/list-capsules": "list_capsules",
    "/ui/actions/view-capsule": "view_capsule",
    "/ui/actions/create-instance": "create_instance",
    "/ui/actions/update-instance": "update_instance",
    "/ui/actions/start-instance": "start_instance",
    "/ui/actions/stop-instance": "stop_instance",
    "/ui/actions/restart-instance": "restart_instance",
    "/ui/actions/instance-status": "instance_status",
    "/ui/actions/view-logs": "view_logs",
    "/ui/actions/view-health": "view_health",
    "/ui/actions/rollback-instance": "rollback_instance",
    "/ui/actions/create-backup": "create_backup",
    "/ui/actions/list-backups": "list_backups",
    "/ui/actions/verify-backup": "verify_backup",
    "/ui/actions/restore-backup": "restore_backup",
    "/ui/actions/restore-backup-new": "restore_backup_new",
    "/ui/actions/test-restore-backup": "test_restore_backup",
    "/ui/actions/run-security-check": "run_security_check",
    "/ui/actions/set-network-profile": "set_network_profile",
    "/ui/actions/disable-public-mode": "disable_public_mode",
    "/ui/actions/set-target-local": "set_target_local",
    "/ui/actions/set-target-intranet": "set_target_intranet",
    "/ui/actions/set-target-droplet": "set_target_droplet",
    "/ui/actions/set-target-temporary-public": "set_target_temporary_public",
    "/ui/actions/deploy-local": "deploy_local",
    "/ui/actions/deploy-intranet": "deploy_intranet",
    "/ui/actions/bootstrap-droplet-agent": "bootstrap_droplet_agent",
    "/ui/actions/check-droplet-agent": "check_droplet_agent",
    "/ui/actions/copy-capsule-to-droplet": "copy_capsule_to_droplet",
    "/ui/actions/deploy-droplet": "deploy_droplet",
    "/ui/actions/start-droplet-instance": "start_droplet_instance",
}


BROWSER_ONLY_ACTIONS: tuple[str, ...] = (
    "open_instance",
    "open_manager_docs",
    "open_agent_docs",
)


BROWSER_ACCEPT_HEADERS: dict[str, str] = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def import_ui_app_module() -> Any:
    return importlib.import_module("kx_manager.ui.app")


def make_app() -> FastAPI:
    ui_app = import_ui_app_module()
    app = FastAPI()
    ui_app.register(app)
    return app


def route_methods(app: FastAPI) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}

    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)

        if not path or not methods:
            continue

        result.setdefault(path, set()).update(methods)

    return result


def canonical_action_from_route(path: str) -> str:
    assert path.startswith("/ui/actions/")
    return path.removeprefix("/ui/actions/").replace("-", "_")


def _route_test_root(tmp_path: Path | None) -> Path:
    if tmp_path is not None:
        return tmp_path

    root = Path(tempfile.gettempdir()) / "konnaxion-ui-route-tests"
    root.mkdir(parents=True, exist_ok=True)
    return root


def action_payload(action: str, tmp_path: Path | None = None) -> dict[str, Any]:
    root = _route_test_root(tmp_path)

    source_dir = root / "Konnaxion"
    runtime_root = root / "runtime"
    capsule_output_dir = runtime_root / "capsules"
    capsule_file = capsule_output_dir / "konnaxion-v14-demo-2026.04.30.kxcap"
    ssh_key_path = root / "id_ed25519"

    source_dir.mkdir(parents=True, exist_ok=True)
    capsule_output_dir.mkdir(parents=True, exist_ok=True)
    capsule_file.write_bytes(b"fake capsule for route tests")
    ssh_key_path.write_text("not-a-real-key-for-route-tests\n", encoding="utf-8")

    base: dict[str, Any] = {
        "action": action,
        "source_dir": str(source_dir),
        "capsule_output_dir": str(capsule_output_dir),
        "capsule_id": "konnaxion-v14-demo-2026.04.30",
        "capsule_version": "2026.04.30-demo.1",
        "version": "2026.04.30-demo.1",
        "profile": "intranet_private",
        "instance_id": "demo-001",
        "backup_id": "demo-001_20260430_230000_manual",
        "source_backup_id": "demo-001_20260430_230000_manual",
        "new_instance_id": "demo-restore-001",
        "target_instance_id": "demo-restore-001",
        "target_release_id": "20260430_230000",
        "network_profile": "intranet_private",
        "exposure_mode": "private",
        "backup_class": "manual",
        "service": "django-api",
        "lines": "200",
        "tail": "true",
        "tail_lines": "200",
        "timeout_seconds": "60",
        "blocking": "true",
        "run_security_gate": "true",
        "verify_after_create": "true",
        "verify_after_build": "true",
        "create_pre_restore_backup": "true",
        "create_pre_update_backup": "true",
        "generate_secrets": "true",
        "restore_data": "true",
        "target_mode": "intranet",
        "runtime_root": str(runtime_root),
        "capsule_dir": str(capsule_output_dir),
        "host": "konnaxion.local",
        "domain": "",
        "public_mode_expires_at": "2026-04-30T22:00:00Z",
        "build": "true",
        "verify": "true",
        "copy": "true",
        "import_capsule": "true",
        "start": "true",
        "confirmed": "true",
        "confirm": "true",
    }

    if action in {
        "verify_capsule",
        "import_capsule",
        "update_instance",
        "copy_capsule_to_droplet",
        "deploy_droplet",
        "start_droplet_instance",
    }:
        base.update(
            {
                "output": str(capsule_file),
                "capsule_file": str(capsule_file),
                "capsule_path": str(capsule_file),
            }
        )

    if action in {"build_capsule", "rebuild_capsule"}:
        base.update(
            {
                "output": str(capsule_file),
                "capsule_file": str(capsule_file),
                "capsule_path": str(capsule_file),
            }
        )

    if action in {"set_target_local", "deploy_local"}:
        base.update(
            {
                "target_mode": "local",
                "network_profile": "local_only",
                "exposure_mode": "private",
                "host": "",
                "domain": "",
                "public_mode_expires_at": "",
                "confirmed": "",
            }
        )

    if action in {"set_target_intranet", "deploy_intranet"}:
        base.update(
            {
                "target_mode": "intranet",
                "network_profile": "intranet_private",
                "exposure_mode": "private",
                "host": "konnaxion.local",
                "domain": "",
                "public_mode_expires_at": "",
                "confirmed": "",
            }
        )

    if action == "set_target_temporary_public":
        base.update(
            {
                "target_mode": "temporary_public",
                "network_profile": "public_temporary",
                "exposure_mode": "temporary_tunnel",
                "host": "demo.example.com",
                "public_host": "demo.example.com",
                "public_mode_expires_at": "2026-04-30T22:00:00Z",
                "confirmed": "true",
            }
        )

    if action in {
        "set_target_droplet",
        "bootstrap_droplet_agent",
        "check_droplet_agent",
        "copy_capsule_to_droplet",
        "deploy_droplet",
        "start_droplet_instance",
    }:
        base.update(
            {
                "target_mode": "droplet",
                "network_profile": "public_vps",
                "exposure_mode": "public",
                "public_mode_enabled": "true",
                "droplet_name": "konnaxion-prod-01",
                "droplet_host": "203.0.113.10",
                "host": "203.0.113.10",
                "droplet_user": "root",
                "ssh_key_path": str(ssh_key_path),
                "ssh_port": "22",
                "remote_kx_root": "/opt/konnaxion",
                "runtime_root": "/opt/konnaxion",
                "remote_capsule_dir": "/opt/konnaxion/capsules",
                "capsule_dir": "/opt/konnaxion/capsules",
                "domain": "app.example.com",
                "droplet_domain": "app.example.com",
                "remote_agent_url": "",
                "confirmed": "true",
            }
        )

    if action == "disable_public_mode":
        base.update(
            {
                "network_profile": "intranet_private",
                "exposure_mode": "private",
                "public_mode_expires_at": "",
                "confirmed": "true",
            }
        )

    return base


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
                "inputs": {},
            }
            return

        if self._current is None:
            return

        if tag_name != "input":
            return

        name = attr_map.get("name")
        if not name:
            return

        value = attr_map.get("value", "")
        self._current["inputs"][name] = value

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


def _form_for_action(
    forms: Sequence[Mapping[str, Any]],
    action: str,
) -> Mapping[str, Any]:
    matches = [
        form
        for form in forms
        if isinstance(form.get("inputs"), Mapping)
        and form["inputs"].get("action") == action
    ]

    assert matches, f"Missing form with hidden action={action!r}"
    return matches[0]


def _assert_no_form_for_action(
    forms: Sequence[Mapping[str, Any]],
    action: str,
) -> None:
    matches = [
        form
        for form in forms
        if isinstance(form.get("inputs"), Mapping)
        and form["inputs"].get("action") == action
    ]

    assert not matches, f"Unexpected form with hidden action={action!r}"


def install_stub_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    actions_module = importlib.import_module("kx_manager.ui.actions")

    async def fake_dispatch_gui_action(
        action: Any,
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        action_value = getattr(action, "value", action)
        payload_dict = dict(payload or {})

        result_class = getattr(actions_module, "GuiActionResult", None)

        if result_class is not None:
            return result_class(
                ok=True,
                action=str(action_value),
                message="stubbed ui action",
                instance_id=payload_dict.get("instance_id"),
                data={"payload": payload_dict},
            )

        return {
            "ok": True,
            "action": str(action_value),
            "message": "stubbed ui action",
            "instance_id": payload_dict.get("instance_id"),
            "data": {"payload": payload_dict},
        }

    def fake_validated_payload(
        action: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        del action
        return dict(payload)

    monkeypatch.setattr(
        actions_module,
        "dispatch_gui_action",
        fake_dispatch_gui_action,
        raising=False,
    )

    ui_app = import_ui_app_module()
    monkeypatch.setattr(
        ui_app,
        "dispatch_gui_action",
        fake_dispatch_gui_action,
        raising=False,
    )
    monkeypatch.setattr(
        ui_app,
        "_validated_payload",
        fake_validated_payload,
        raising=False,
    )


def post_action(
    client: TestClient,
    path: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
) -> Any:
    response = client.post(path, data=payload, headers=headers, follow_redirects=False)

    if response.status_code in {415, 422}:
        response = client.post(
            path,
            json=payload,
            headers=headers,
            follow_redirects=False,
        )

    return response


def test_fastapi_ui_register_exists() -> None:
    ui_app = import_ui_app_module()

    assert hasattr(ui_app, "register")
    assert callable(ui_app.register)


def test_fastapi_ui_import_does_not_require_streamlit() -> None:
    sys.modules.pop("kx_manager.ui.app", None)
    sys.modules.pop("streamlit", None)

    ui_app = import_ui_app_module()

    assert hasattr(ui_app, "register")
    assert "streamlit" not in sys.modules


def test_register_adds_required_page_routes() -> None:
    app = make_app()
    routes = route_methods(app)

    for path in REQUIRED_PAGE_ROUTES:
        assert path in routes, f"Missing page route: GET {path}"
        assert "GET" in routes[path], f"Missing GET method for page route: {path}"


def test_register_adds_required_action_routes() -> None:
    app = make_app()
    routes = route_methods(app)

    for path in REQUIRED_ACTION_ROUTES:
        assert path in routes, f"Missing action route: POST {path}"
        assert "POST" in routes[path], f"Missing POST method for action route: {path}"


def test_all_ui_page_routes_start_with_ui() -> None:
    app = make_app()
    routes = route_methods(app)

    ui_routes = [
        path
        for path in routes
        if path.startswith("/ui") and not path.startswith("/ui/actions")
    ]

    assert ui_routes

    for path in ui_routes:
        assert path == "/ui" or path.startswith("/ui/")


def test_all_post_action_routes_start_with_ui_actions() -> None:
    app = make_app()
    routes = route_methods(app)

    post_action_routes = [
        path
        for path, methods in routes.items()
        if "POST" in methods and path.startswith("/ui")
    ]

    assert post_action_routes

    for path in post_action_routes:
        assert path.startswith("/ui/actions"), (
            f"UI POST action route must start with /ui/actions: {path}"
        )


def test_action_route_names_map_to_canonical_action_values() -> None:
    for path, expected_action in REQUIRED_ACTION_ROUTES.items():
        assert canonical_action_from_route(path) == expected_action


def test_browser_only_actions_are_not_required_post_action_routes() -> None:
    route_actions = set(REQUIRED_ACTION_ROUTES.values())

    for action in BROWSER_ONLY_ACTIONS:
        assert action not in route_actions


def test_targets_page_contains_target_configuration_forms_only() -> None:
    app = make_app()
    client = TestClient(app)

    response = client.get("/ui/targets", headers=BROWSER_ACCEPT_HEADERS)

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/html")

    forms = _forms_from_html(response.text)

    for action in TARGET_ACTIONS:
        _form_for_action(forms, action)

    for action in DEPLOYMENT_ACTIONS:
        _assert_no_form_for_action(forms, action)


def test_deploy_page_contains_deployment_operation_forms_only() -> None:
    app = make_app()
    client = TestClient(app)

    response = client.get("/ui/deploy", headers=BROWSER_ACCEPT_HEADERS)

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/html")

    forms = _forms_from_html(response.text)

    for action in DEPLOYMENT_ACTIONS:
        _form_for_action(forms, action)

    for action in TARGET_ACTIONS:
        _assert_no_form_for_action(forms, action)


def test_deploy_page_bootstrap_droplet_agent_form_uses_droplet_payload() -> None:
    app = make_app()
    client = TestClient(app)

    response = client.get("/ui/deploy", headers=BROWSER_ACCEPT_HEADERS)

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/html")

    forms = _forms_from_html(response.text)
    form = _form_for_action(forms, "bootstrap_droplet_agent")
    attrs = form["attrs"]
    inputs = form["inputs"]

    assert attrs.get("method", "").lower() == "post"
    assert attrs.get("action") == "/ui/actions/bootstrap-droplet-agent"

    assert inputs.get("action") == "bootstrap_droplet_agent"
    assert inputs.get("target_mode") == "droplet"
    assert inputs.get("network_profile") == "public_vps"
    assert inputs.get("exposure_mode") == "public"
    assert inputs.get("confirmed") == "true"

    assert inputs.get("remote_kx_root") == "/opt/konnaxion"
    assert inputs.get("remote_capsule_dir") == "/opt/konnaxion/capsules"


def test_deploy_page_copy_capsule_to_droplet_form_uses_droplet_payload() -> None:
    app = make_app()
    client = TestClient(app)

    response = client.get("/ui/deploy", headers=BROWSER_ACCEPT_HEADERS)

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/html")

    forms = _forms_from_html(response.text)
    form = _form_for_action(forms, "copy_capsule_to_droplet")
    attrs = form["attrs"]
    inputs = form["inputs"]

    assert attrs.get("method", "").lower() == "post"
    assert attrs.get("action") == "/ui/actions/copy-capsule-to-droplet"

    assert inputs.get("action") == "copy_capsule_to_droplet"
    assert inputs.get("target_mode") == "droplet"
    assert inputs.get("network_profile") == "public_vps"
    assert inputs.get("exposure_mode") == "public"
    assert inputs.get("confirmed") == "true"

    assert inputs.get("remote_kx_root") == "/opt/konnaxion"
    assert inputs.get("remote_capsule_dir") == "/opt/konnaxion/capsules"

    capsule_path = inputs.get("capsule_file") or inputs.get("capsule_path")
    assert capsule_path
    assert str(capsule_path).endswith(".kxcap")


def test_deploy_page_droplet_operation_forms_do_not_submit_intranet_payload() -> None:
    app = make_app()
    client = TestClient(app)

    response = client.get("/ui/deploy", headers=BROWSER_ACCEPT_HEADERS)

    assert response.status_code == 200

    forms = _forms_from_html(response.text)

    for action in DROPLET_OPERATION_ACTIONS:
        form = _form_for_action(forms, action)
        inputs = form["inputs"]

        assert inputs.get("target_mode") == "droplet", action
        assert inputs.get("network_profile") == "public_vps", action
        assert inputs.get("exposure_mode") == "public", action
        assert inputs.get("confirmed") == "true", action
        assert inputs.get("host") != "konnaxion.local", action

        remote_root = inputs.get("remote_kx_root") or inputs.get("runtime_root")
        remote_capsules = inputs.get("remote_capsule_dir") or inputs.get("capsule_dir")

        assert remote_root == "/opt/konnaxion", action
        assert remote_capsules == "/opt/konnaxion/capsules", action


def test_deploy_page_bootstrap_and_check_forms_do_not_require_capsule_file() -> None:
    app = make_app()
    client = TestClient(app)

    response = client.get("/ui/deploy", headers=BROWSER_ACCEPT_HEADERS)

    assert response.status_code == 200

    forms = _forms_from_html(response.text)

    for action in DROPLET_CAPSULE_NOT_REQUIRED_ACTIONS:
        form = _form_for_action(forms, action)
        inputs = form["inputs"]

        assert "capsule_file" not in inputs, action
        assert "capsule_path" not in inputs, action


def test_deploy_page_capsule_operations_include_capsule_file() -> None:
    app = make_app()
    client = TestClient(app)

    response = client.get("/ui/deploy", headers=BROWSER_ACCEPT_HEADERS)

    assert response.status_code == 200

    forms = _forms_from_html(response.text)

    for action in DROPLET_CAPSULE_REQUIRED_ACTIONS:
        form = _form_for_action(forms, action)
        inputs = form["inputs"]

        capsule_path = inputs.get("capsule_file") or inputs.get("capsule_path")
        assert capsule_path, action
        assert str(capsule_path).endswith(".kxcap"), action


def test_targets_page_droplet_target_form_does_not_autofill_domain_from_host_context() -> None:
    from kx_manager.ui.page_parts.targets import render

    html = render(
        {
            "instance_id": "demo-001",
            "capsule_file": "/tmp/demo.kxcap",
            "droplet_host": "203.0.113.10",
            "droplet_user": "konnaxion",
            "ssh_key_path": "/tmp/id_ed25519",
            "remote_kx_root": "/opt/konnaxion",
            "remote_capsule_dir": "/opt/konnaxion/capsules",
            "domain": "",
            "droplet_domain": "",
        }
    )

    forms = _forms_from_html(html)
    form = _form_for_action(forms, "set_target_droplet")
    inputs = form["inputs"]

    assert inputs.get("target_mode") == "droplet"
    assert inputs.get("network_profile") == "public_vps"
    assert inputs.get("exposure_mode") == "public"
    assert inputs.get("droplet_host") == "203.0.113.10"
    assert inputs.get("domain", "") == ""
    assert inputs.get("droplet_domain", "") == ""

    for action in DEPLOYMENT_ACTIONS:
        _assert_no_form_for_action(forms, action)


def test_deploy_page_droplet_operation_forms_do_not_autofill_domain_from_host_context() -> None:
    from kx_manager.ui.page_parts.deploy import render

    html = render(
        {
            "instance_id": "demo-001",
            "capsule_file": "/tmp/demo.kxcap",
            "droplet_host": "203.0.113.10",
            "droplet_user": "konnaxion",
            "ssh_key_path": "/tmp/id_ed25519",
            "remote_kx_root": "/opt/konnaxion",
            "remote_capsule_dir": "/opt/konnaxion/capsules",
            "domain": "",
            "droplet_domain": "",
        }
    )

    forms = _forms_from_html(html)

    for action in DROPLET_OPERATION_ACTIONS:
        form = _form_for_action(forms, action)
        inputs = form["inputs"]

        assert inputs.get("target_mode") == "droplet", action
        assert inputs.get("network_profile") == "public_vps", action
        assert inputs.get("exposure_mode") == "public", action
        assert inputs.get("droplet_host") == "203.0.113.10", action
        assert inputs.get("domain", "") == "", action
        assert inputs.get("droplet_domain", "") == "", action


@pytest.mark.parametrize(
    ("path", "expected_action"),
    [
        ("/ui/actions/set-target-droplet", "set_target_droplet"),
        ("/ui/actions/bootstrap-droplet-agent", "bootstrap_droplet_agent"),
        ("/ui/actions/check-droplet-agent", "check_droplet_agent"),
        ("/ui/actions/copy-capsule-to-droplet", "copy_capsule_to_droplet"),
        ("/ui/actions/deploy-droplet", "deploy_droplet"),
        ("/ui/actions/start-droplet-instance", "start_droplet_instance"),
    ],
)
def test_droplet_action_routes_reject_missing_domain_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path: str,
    expected_action: str,
) -> None:
    called = {"dispatch": False}

    async def fake_dispatch_gui_action(
        action: Any,
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        called["dispatch"] = True
        return {
            "ok": True,
            "action": str(getattr(action, "value", action)),
            "message": "dispatch should not run for invalid droplet payload",
            "instance_id": dict(payload or {}).get("instance_id"),
            "data": {"payload": dict(payload or {})},
        }

    ui_app = import_ui_app_module()
    monkeypatch.setattr(
        ui_app,
        "dispatch_gui_action",
        fake_dispatch_gui_action,
        raising=False,
    )

    app = make_app()
    client = TestClient(app)

    payload = action_payload(expected_action, tmp_path)
    payload["domain"] = ""
    payload["droplet_domain"] = ""

    response = post_action(
        client,
        path,
        payload,
        headers=BROWSER_ACCEPT_HEADERS,
    )

    assert response.status_code == 200
    assert called["dispatch"] is False
    assert "domain" in response.text.lower()


@pytest.mark.parametrize("path, expected_action", REQUIRED_ACTION_ROUTES.items())
def test_action_routes_dispatch_without_agent_or_docker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path: str,
    expected_action: str,
) -> None:
    install_stub_dispatch(monkeypatch)

    app = make_app()
    client = TestClient(app)

    response = post_action(client, path, action_payload(expected_action, tmp_path))

    assert response.status_code in {200, 201, 202, 204, 302, 303, 307}, (
        f"Unexpected status for {path}: "
        f"{response.status_code} {response.text[:500]}"
    )


@pytest.mark.parametrize("path, expected_action", REQUIRED_ACTION_ROUTES.items())
def test_browser_action_routes_return_html_not_raw_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path: str,
    expected_action: str,
) -> None:
    install_stub_dispatch(monkeypatch)

    app = make_app()
    client = TestClient(app)

    response = post_action(
        client,
        path,
        action_payload(expected_action, tmp_path),
        headers=BROWSER_ACCEPT_HEADERS,
    )

    assert response.status_code == 200, (
        f"Browser action route should render an HTML result page for {path}, "
        f"got {response.status_code}: {response.text[:500]}"
    )

    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("text/html"), (
        f"Browser action route must return HTML, not raw JSON, for {path}. "
        f"content-type={content_type!r}, body={response.text[:500]}"
    )

    assert "stubbed ui action" in response.text
    assert not response.text.lstrip().startswith("{"), (
        f"Browser action route leaked raw JSON for {path}: {response.text[:500]}"
    )


def test_verify_capsule_browser_error_renders_html_not_raw_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    actions_module = importlib.import_module("kx_manager.ui.actions")

    async def fake_failed_verify(
        action: Any,
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        del payload
        action_value = getattr(action, "value", action)

        result_class = getattr(actions_module, "GuiActionResult", None)

        if result_class is not None:
            return result_class(
                ok=False,
                action=str(action_value),
                message=(
                    "capsule_file does not exist: "
                    r"C:\mycode\Konnaxion\runtime\capsules\konnaxion-v14-demo-2026.04.30.kxcap"
                ),
                instance_id=None,
                data={"field": "capsule_file"},
                stderr=(
                    "capsule_file does not exist: "
                    r"C:\mycode\Konnaxion\runtime\capsules\konnaxion-v14-demo-2026.04.30.kxcap"
                ),
            )

        return {
            "ok": False,
            "action": str(action_value),
            "message": (
                "capsule_file does not exist: "
                r"C:\mycode\Konnaxion\runtime\capsules\konnaxion-v14-demo-2026.04.30.kxcap"
            ),
            "instance_id": None,
            "data": {"field": "capsule_file"},
            "stderr": (
                "capsule_file does not exist: "
                r"C:\mycode\Konnaxion\runtime\capsules\konnaxion-v14-demo-2026.04.30.kxcap"
            ),
        }

    monkeypatch.setattr(
        actions_module,
        "dispatch_gui_action",
        fake_failed_verify,
        raising=False,
    )

    ui_app = import_ui_app_module()
    monkeypatch.setattr(
        ui_app,
        "dispatch_gui_action",
        fake_failed_verify,
        raising=False,
    )

    app = make_app()
    client = TestClient(app)

    response = post_action(
        client,
        "/ui/actions/verify-capsule",
        action_payload("verify_capsule", tmp_path),
        headers=BROWSER_ACCEPT_HEADERS,
    )

    assert response.status_code == 200

    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("text/html")
    assert "capsule_file does not exist" in response.text
    assert "verify_capsule" in response.text or "Verify" in response.text
    assert not response.text.lstrip().startswith("{")


def test_unknown_action_route_is_not_registered_as_static_route() -> None:
    app = make_app()
    routes = route_methods(app)

    assert "/ui/actions/not-a-real-action" not in routes


def test_ui_routes_do_not_register_open_docs_as_post_actions() -> None:
    app = make_app()
    routes = route_methods(app)

    forbidden_post_routes = {
        "/ui/actions/open-instance",
        "/ui/actions/open-manager-docs",
        "/ui/actions/open-agent-docs",
    }

    for path in forbidden_post_routes:
        assert path not in routes