# tests/test_fastapi_ui_routes.py

from __future__ import annotations

import importlib
import sys
from collections.abc import Mapping
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


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


def install_stub_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    ok: bool = True,
    message: str = "stubbed ui action",
) -> list[tuple[str, dict[str, Any]]]:
    """Install a dispatcher stub and return captured calls."""

    ui_app = import_ui_app_module()
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_dispatch_gui_action(
        action: Any,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        action_value = str(getattr(action, "value", action))
        payload_dict = dict(payload or {})
        calls.append((action_value, payload_dict))

        return {
            "ok": ok,
            "action": action_value,
            "message": message,
            "instance_id": payload_dict.get("instance_id"),
            "data": {"payload": payload_dict},
            "stdout": None,
            "stderr": None if ok else message,
            "returncode": None,
        }

    monkeypatch.setattr(
        ui_app,
        "dispatch_gui_action",
        fake_dispatch_gui_action,
        raising=False,
    )

    return calls


def install_identity_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass form-model validation so these tests cover FastAPI route behavior only."""

    ui_app = import_ui_app_module()

    def fake_validated_payload(
        action: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        del action
        return dict(payload)

    monkeypatch.setattr(
        ui_app,
        "_validated_payload",
        fake_validated_payload,
        raising=True,
    )


def test_fastapi_ui_app_import_does_not_require_streamlit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sys.modules.pop("kx_manager.ui.app", None)
    sys.modules.pop("streamlit", None)

    ui_app = import_ui_app_module()

    assert callable(getattr(ui_app, "register", None))
    assert "streamlit" not in sys.modules


def test_register_adds_static_page_and_action_route_sets() -> None:
    from kx_manager.ui.static import ACTION_ROUTES, BROWSER_LINK_ACTIONS, UI_PAGE_ROUTES

    app = make_app()
    routes = route_methods(app)

    for route in UI_PAGE_ROUTES:
        assert route in routes, f"missing UI page route: GET {route}"
        assert "GET" in routes[route], f"missing GET method for UI page route: {route}"

    for action, route in ACTION_ROUTES.items():
        if action in BROWSER_LINK_ACTIONS:
            continue

        assert route in routes, f"missing UI action route: POST {route}"
        assert "POST" in routes[route], f"missing POST method for UI action route: {route}"


def test_browser_only_actions_are_not_registered_as_post_routes() -> None:
    from kx_manager.ui.static import BROWSER_LINK_ACTIONS

    app = make_app()
    routes = route_methods(app)

    for action in BROWSER_LINK_ACTIONS:
        route = f"/ui/actions/{action.replace('_', '-')}"
        assert route not in routes


@pytest.mark.parametrize(
    ("route", "expected_text"),
    [
        ("/ui", "Dashboard"),
        ("/ui/capsules", "Capsules"),
        ("/ui/instances", "Instances"),
        ("/ui/targets", "Targets"),
        ("/ui/deploy", "Deploy"),
        ("/ui/security", "Security"),
        ("/ui/network", "Network"),
        ("/ui/backups", "Backups"),
        ("/ui/restore", "Restore"),
        ("/ui/logs", "Logs"),
        ("/ui/health", "Health"),
        ("/ui/settings", "Settings"),
        ("/ui/about", "About"),
    ],
)
def test_page_routes_return_html(route: str, expected_text: str) -> None:
    client = TestClient(make_app())

    response = client.get(route, headers=BROWSER_ACCEPT_HEADERS)

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/html")
    assert "Konnaxion Capsule Manager" in response.text
    assert expected_text in response.text
    assert not response.text.lstrip().startswith("{")


def test_unknown_ui_page_route_is_not_registered() -> None:
    client = TestClient(make_app())

    response = client.get("/ui/not-a-real-page", headers=BROWSER_ACCEPT_HEADERS)

    assert response.status_code == 404


def test_json_action_post_returns_json_and_dispatches_normalized_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = install_stub_dispatch(monkeypatch)
    install_identity_validation(monkeypatch)

    client = TestClient(make_app())

    response = client.post(
        "/ui/actions/update-instance",
        json={
            "instance_id": "demo-001",
            "capsule_file": "/tmp/demo.kxcap",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("application/json")

    body = response.json()

    assert body["ok"] is True
    assert body["action"] == "update_instance"
    assert body["message"] == "stubbed ui action"

    assert calls
    action, payload = calls[-1]
    assert action == "update_instance"
    assert payload["instance_id"] == "demo-001"
    assert payload["capsule_file"] == "/tmp/demo.kxcap"
    assert payload["capsule_path"] == "/tmp/demo.kxcap"


def test_browser_form_post_returns_html_result_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = install_stub_dispatch(monkeypatch)
    install_identity_validation(monkeypatch)

    client = TestClient(make_app())

    response = client.post(
        "/ui/actions/select-source-folder",
        data={
            "source_dir": r"C:\mycode\Konnaxion\Konnaxion",
        },
        headers=BROWSER_ACCEPT_HEADERS,
    )

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/html")
    assert "stubbed ui action" in response.text
    assert "select_source_folder" in response.text or "Select Source Folder" in response.text
    assert not response.text.lstrip().startswith("{")

    assert calls
    action, payload = calls[-1]
    assert action == "select_source_folder"
    assert payload["source_dir"] == r"C:\mycode\Konnaxion\Konnaxion"


def test_validation_error_is_rendered_as_html_for_browser_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ui_app = import_ui_app_module()

    def fake_validated_payload(
        action: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        del action, payload
        raise ValueError("capsule_file is required.")

    async def fake_dispatch_gui_action(
        action: Any,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise AssertionError(
            f"dispatcher should not run after validation failure: {action} {payload}"
        )

    monkeypatch.setattr(
        ui_app,
        "_validated_payload",
        fake_validated_payload,
        raising=True,
    )
    monkeypatch.setattr(
        ui_app,
        "dispatch_gui_action",
        fake_dispatch_gui_action,
        raising=False,
    )

    client = TestClient(make_app())

    response = client.post(
        "/ui/actions/verify-capsule",
        data={"capsule_file": ""},
        headers=BROWSER_ACCEPT_HEADERS,
    )

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/html")
    assert "capsule_file is required" in response.text
    assert "verify_capsule" in response.text or "Verify Capsule" in response.text
    assert not response.text.lstrip().startswith("{")


def test_validation_error_is_json_for_json_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ui_app = import_ui_app_module()

    def fake_validated_payload(
        action: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        del action, payload
        raise ValueError("instance_id is required.")

    async def fake_dispatch_gui_action(
        action: Any,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise AssertionError(
            f"dispatcher should not run after validation failure: {action} {payload}"
        )

    monkeypatch.setattr(
        ui_app,
        "_validated_payload",
        fake_validated_payload,
        raising=True,
    )
    monkeypatch.setattr(
        ui_app,
        "dispatch_gui_action",
        fake_dispatch_gui_action,
        raising=False,
    )

    client = TestClient(make_app())

    response = client.post(
        "/ui/actions/start-instance",
        json={"instance_id": ""},
    )

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("application/json")

    body = response.json()

    assert body["ok"] is False
    assert body["action"] == "start_instance"
    assert "instance_id is required" in body["message"]
    assert body["stderr"] == "instance_id is required."


def test_render_app_compatibility_entrypoint_rejects_direct_use() -> None:
    ui_app = import_ui_app_module()

    with pytest.raises(RuntimeError, match="FastAPI GUI route module"):
        ui_app.render_app()