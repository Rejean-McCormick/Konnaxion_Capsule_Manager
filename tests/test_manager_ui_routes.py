from __future__ import annotations

import importlib
import sys
from collections.abc import Mapping
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
    "/ui/about",
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
    "/ui/actions/deploy-droplet": "deploy_droplet",
    "/ui/actions/check-droplet-agent": "check_droplet_agent",
    "/ui/actions/copy-capsule-to-droplet": "copy_capsule_to_droplet",
    "/ui/actions/start-droplet-instance": "start_droplet_instance",
}


BROWSER_ONLY_ACTIONS: tuple[str, ...] = (
    "open_instance",
    "open_manager_docs",
    "open_agent_docs",
)


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


def action_payload(action: str) -> dict[str, Any]:
    base: dict[str, Any] = {
        "source_dir": r"C:\mycode\Konnaxion\Konnaxion",
        "capsule_output_dir": r"C:\mycode\Konnaxion\runtime\capsules",
        "output": r"C:\mycode\Konnaxion\runtime\capsules\konnaxion-v14-demo-2026.04.30.kxcap",
        "capsule_file": r"C:\mycode\Konnaxion\runtime\capsules\konnaxion-v14-demo-2026.04.30.kxcap",
        "capsule_path": r"C:\mycode\Konnaxion\runtime\capsules\konnaxion-v14-demo-2026.04.30.kxcap",
        "capsule_id": "konnaxion-v14-demo-2026.04.30",
        "version": "2026.04.30-demo.1",
        "profile": "intranet_private",
        "instance_id": "demo-001",
        "backup_id": "demo-001_20260430_230000_manual",
        "source_backup_id": "demo-001_20260430_230000_manual",
        "new_instance_id": "demo-restore-001",
        "target_release_id": "20260430_230000",
        "network_profile": "intranet_private",
        "exposure_mode": "private",
        "backup_class": "manual",
        "service": "django-api",
        "tail": "200",
        "timeout_seconds": "60",
        "blocking": "true",
        "run_security_gate": "true",
        "verify_after_create": "true",
        "create_pre_restore_backup": "true",
        "create_pre_update_backup": "true",
        "generate_secrets": "true",
        "restore_data": "true",
        "target_mode": "intranet",
        "runtime_root": r"C:\mycode\Konnaxion\runtime",
        "host": "konnaxion.local",
        "public_mode_expires_at": "2026-04-30T22:00:00Z",
        "droplet_name": "konnaxion-prod-01",
        "droplet_host": "203.0.113.10",
        "droplet_user": "root",
        "ssh_key_path": r"C:\Users\user\.ssh\id_ed25519",
        "remote_kx_root": "/opt/konnaxion",
        "remote_capsule_dir": "/opt/konnaxion/capsules",
        "domain": "app.example.com",
        "remote_agent_url": "http://203.0.113.10:8765/v1",
        "build": "true",
        "verify": "true",
        "copy": "true",
        "import_capsule": "true",
        "start": "true",
        "confirmed": "true",
        "confirm": "true",
    }

    if action == "set_target_local" or action == "deploy_local":
        base.update(
            {
                "target_mode": "local",
                "network_profile": "local_only",
                "exposure_mode": "private",
            }
        )

    if action == "set_target_intranet" or action == "deploy_intranet":
        base.update(
            {
                "target_mode": "intranet",
                "network_profile": "intranet_private",
                "exposure_mode": "private",
                "host": "konnaxion.local",
            }
        )

    if action == "set_target_temporary_public":
        base.update(
            {
                "target_mode": "temporary_public",
                "network_profile": "public_temporary",
                "exposure_mode": "temporary_tunnel",
                "public_mode_expires_at": "2026-04-30T22:00:00Z",
                "confirmed": "true",
            }
        )

    if action in {
        "set_target_droplet",
        "deploy_droplet",
        "check_droplet_agent",
        "copy_capsule_to_droplet",
        "start_droplet_instance",
    }:
        base.update(
            {
                "target_mode": "droplet",
                "network_profile": "public_vps",
                "exposure_mode": "public",
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


def install_stub_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    actions_module = importlib.import_module("kx_manager.ui.actions")

    async def fake_dispatch_gui_action(action: Any, payload: Mapping[str, Any] | None = None) -> Any:
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

    monkeypatch.setattr(actions_module, "dispatch_gui_action", fake_dispatch_gui_action, raising=False)

    ui_app = import_ui_app_module()
    monkeypatch.setattr(ui_app, "dispatch_gui_action", fake_dispatch_gui_action, raising=False)


def post_action(client: TestClient, path: str, payload: dict[str, Any]) -> Any:
    response = client.post(path, data=payload, follow_redirects=False)

    if response.status_code in {415, 422}:
        response = client.post(path, json=payload, follow_redirects=False)

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
        assert path.startswith("/ui/actions"), f"UI POST action route must start with /ui/actions: {path}"


def test_action_route_names_map_to_canonical_action_values() -> None:
    for path, expected_action in REQUIRED_ACTION_ROUTES.items():
        assert canonical_action_from_route(path) == expected_action


def test_browser_only_actions_are_not_required_post_action_routes() -> None:
    route_actions = set(REQUIRED_ACTION_ROUTES.values())

    for action in BROWSER_ONLY_ACTIONS:
        assert action not in route_actions


@pytest.mark.parametrize("path, expected_action", REQUIRED_ACTION_ROUTES.items())
def test_action_routes_dispatch_without_agent_or_docker(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    expected_action: str,
) -> None:
    install_stub_dispatch(monkeypatch)

    app = make_app()
    client = TestClient(app)

    response = post_action(client, path, action_payload(expected_action))

    assert response.status_code in {200, 201, 202, 204, 302, 303, 307}, (
        f"Unexpected status for {path}: "
        f"{response.status_code} {response.text[:500]}"
    )


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