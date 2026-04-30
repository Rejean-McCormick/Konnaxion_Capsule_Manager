# kx_manager/ui/app.py

"""FastAPI route registration for the Konnaxion Capsule Manager GUI.

This module owns the local /ui browser route surface.

It must remain importable without optional prototype UI dependencies.
Privileged work is not performed here. POST action routes delegate to
kx_manager.ui.actions.dispatch_gui_action, which routes through approved
Manager clients, service wrappers, or Agent APIs.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import inspect
from typing import Any, Mapping

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse

from kx_manager.ui.static import (
    ACTION_ROUTES,
    APP_ICON,
    APP_TITLE,
    BROWSER_LINK_ACTIONS,
    DEFAULT_REFRESH_SECONDS,
    UI_PAGE_ROUTES,
    normalize_payload_aliases,
    title_for_route,
)


BROWSER_ONLY_ACTIONS: frozenset[str] = frozenset(BROWSER_LINK_ACTIONS)

FALLBACK_UI_PAGE_ROUTES = UI_PAGE_ROUTES
FALLBACK_UI_ACTION_ROUTES = {
    str(action): str(route)
    for action, route in ACTION_ROUTES.items()
    if str(action) not in BROWSER_ONLY_ACTIONS
}


try:
    from kx_manager.ui.actions import dispatch_gui_action
except Exception:  # pragma: no cover - staged build compatibility
    dispatch_gui_action = None  # type: ignore[assignment]


def _load_page_routes() -> tuple[str, ...]:
    """Return canonical GUI page routes."""

    return tuple(str(route) for route in UI_PAGE_ROUTES)


def _load_action_routes() -> dict[str, str]:
    """Return canonical GUI action POST routes."""

    return {
        str(action): str(route)
        for action, route in ACTION_ROUTES.items()
        if str(action) not in BROWSER_ONLY_ACTIONS
    }


def _load_dispatcher() -> Any:
    """Return the current GUI dispatcher.

    This resolves through the module attribute first so tests and staged builds
    can monkeypatch ``kx_manager.ui.app.dispatch_gui_action`` without touching
    route registration.
    """

    dispatcher = dispatch_gui_action

    if dispatcher is not None:
        return dispatcher

    from kx_manager.ui.actions import dispatch_gui_action as loaded_dispatcher

    return loaded_dispatcher


def _page_title_for_route(route: str) -> str:
    return title_for_route(route)


def _coerce_html_response(value: Any, *, status_code: int = 200) -> HTMLResponse:
    if isinstance(value, HTMLResponse):
        return value

    if isinstance(value, bytes):
        content = value.decode("utf-8", errors="replace")
    else:
        content = str(value)

    return HTMLResponse(content=content, status_code=status_code)


def _render_page_html(route: str) -> str:
    """Render a GUI page.

    The final page body is delegated to ``kx_manager.ui.page_views`` when
    available. The internal fallback keeps routes importable during staged
    builds and tests.
    """

    try:
        from kx_manager.ui.page_views import render_ui_page

        rendered = render_ui_page(route=route)
        if isinstance(rendered, HTMLResponse):
            return rendered.body.decode("utf-8", errors="replace")
        return str(rendered)
    except Exception:
        return _render_fallback_page_html(route)


def _render_page_response(route: str) -> HTMLResponse:
    try:
        from kx_manager.ui.page_views import render_ui_page

        rendered = render_ui_page(route=route)
        return _coerce_html_response(rendered)
    except Exception:
        return HTMLResponse(_render_fallback_page_html(route))


def _render_fallback_page_html(route: str) -> str:
    title = _page_title_for_route(route)

    nav = "".join(
        f'<a href="{nav_route}">{nav_title}</a>'
        for nav_route, nav_title in (
            ("/ui", "Dashboard"),
            ("/ui/capsules", "Capsules"),
            ("/ui/instances", "Instances"),
            ("/ui/targets", "Targets"),
            ("/ui/security", "Security"),
            ("/ui/network", "Network"),
            ("/ui/backups", "Backups"),
            ("/ui/restore", "Restore"),
            ("/ui/logs", "Logs"),
            ("/ui/health", "Health"),
            ("/ui/settings", "Settings"),
            ("/ui/about", "About"),
        )
    )

    return (
        "<!doctype html>"
        '<html lang="en">'
        "<head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{APP_TITLE} · {title}</title>"
        "<style>"
        "body{font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "margin:0;background:#f7f7f8;color:#111827;}"
        "main{max-width:1120px;margin:0 auto;padding:32px;}"
        "nav{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0 24px;}"
        "a{color:#1f4fd8;text-decoration:none;}"
        ".card{background:white;border:1px solid #e5e7eb;border-radius:12px;padding:20px;}"
        "code{background:#f3f4f6;padding:2px 6px;border-radius:6px;}"
        "</style>"
        "</head>"
        "<body>"
        "<main>"
        f"<h1>{APP_TITLE}</h1>"
        f"<nav>{nav}</nav>"
        '<section class="card">'
        f"<h2>{title}</h2>"
        f"<p>Local GUI route: <code>{route}</code></p>"
        "<p>Page rendering is delegated to "
        "<code>kx_manager.ui.page_views.render_ui_page</code>.</p>"
        "</section>"
        "</main>"
        "</body>"
        "</html>"
    )


async def _request_payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        data = await request.json()
        if isinstance(data, Mapping):
            return normalize_payload_aliases(data)
        return {}

    form = await request.form()
    return normalize_payload_aliases(dict(form))


def _validation_error_result(action: str, exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "action": action,
        "message": str(exc),
        "instance_id": None,
        "data": {
            "field": getattr(exc, "field", None),
        },
        "stdout": None,
        "stderr": str(exc),
        "returncode": None,
    }


def _validated_payload(action: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_payload_aliases(payload)

    try:
        from kx_manager.ui.forms import form_to_payload, parse_action_form
        from kx_manager.ui.form_errors import FormValidationError
    except Exception:
        return normalized

    try:
        form = parse_action_form(action, normalized)
    except FormValidationError:
        raise

    return normalize_payload_aliases(form_to_payload(form))


def _result_to_dict(result: Any, *, action: str) -> dict[str, Any]:
    if result is None:
        data: dict[str, Any] = {
            "ok": True,
            "action": action,
            "message": "Action accepted.",
            "instance_id": None,
            "data": {},
            "stdout": None,
            "stderr": None,
            "returncode": None,
        }
        return jsonable_encoder(data)

    if isinstance(result, Mapping):
        data = dict(result)
    else:
        to_dict = getattr(result, "to_dict", None)
        if callable(to_dict):
            value = to_dict()
            data = dict(value) if isinstance(value, Mapping) else {}
        elif is_dataclass(result):
            data = asdict(result)
        else:
            model_dump = getattr(result, "model_dump", None)
            if callable(model_dump):
                value = model_dump()
                data = dict(value) if isinstance(value, Mapping) else {}
            else:
                data = {"data": {"result": repr(result)}}

    data.setdefault("ok", True)
    data.setdefault("action", action)
    data.setdefault("message", "Action completed.")
    data.setdefault("instance_id", None)
    data.setdefault("data", {})
    data.setdefault("stdout", None)
    data.setdefault("stderr", None)
    data.setdefault("returncode", None)

    return jsonable_encoder(data)


async def _dispatch_action(action: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    try:
        validated_payload = _validated_payload(action, payload)
    except Exception as exc:
        return _validation_error_result(action, exc)

    dispatcher = _load_dispatcher()
    result = dispatcher(action, dict(validated_payload))

    if inspect.isawaitable(result):
        result = await result

    return _result_to_dict(result, action=action)


def _wants_html_response(request: Request) -> bool:
    content_type = request.headers.get("content-type", "")
    accept = request.headers.get("accept", "")

    if "application/json" in content_type:
        return False

    return "text/html" in accept and "application/json" not in accept


def _render_action_result_response(
    *,
    request: Request,
    action: str,
    payload: Mapping[str, Any],
    result: Mapping[str, Any],
) -> Any:
    if not _wants_html_response(request):
        return JSONResponse(jsonable_encoder(result))

    try:
        from kx_manager.ui.action_views import render_action_result_page

        rendered = render_action_result_page(
            action=action,
            payload=dict(payload),
            result=dict(result),
        )
        return _coerce_html_response(rendered)
    except Exception:
        return JSONResponse(jsonable_encoder(result))


def _route_name(prefix: str, route: str) -> str:
    normalized = route.strip("/").replace("/", "_").replace("-", "_")
    return f"{prefix}_{normalized or 'root'}"


def register(app: Any) -> Any:
    """Register FastAPI GUI page and action routes."""

    def make_page_handler(route: str) -> Any:
        async def page_handler() -> Any:
            return _render_page_response(route)

        return page_handler

    def make_action_handler(action: str) -> Any:
        async def action_handler(request: Request) -> Any:
            payload = await _request_payload(request)
            result = await _dispatch_action(action, payload)
            return _render_action_result_response(
                request=request,
                action=action,
                payload=payload,
                result=result,
            )

        return action_handler

    for route in _load_page_routes():
        app.add_api_route(
            route,
            make_page_handler(route),
            methods=["GET"],
            name=_route_name("ui_page", route),
            response_class=HTMLResponse,
            response_model=None,
        )

    for action, route in _load_action_routes().items():
        app.add_api_route(
            route,
            make_action_handler(action),
            methods=["POST"],
            name=_route_name("ui_action", route),
            response_class=JSONResponse,
            response_model=None,
        )

    return app


def render_app() -> None:
    """Compatibility entrypoint for old direct callers."""

    raise RuntimeError(
        "kx_manager.ui.app is the FastAPI GUI route module. "
        "Create a FastAPI app and call register(app)."
    )


def main() -> None:
    """Console compatibility entrypoint."""

    render_app()


__all__ = [
    "APP_ICON",
    "APP_TITLE",
    "BROWSER_ONLY_ACTIONS",
    "DEFAULT_REFRESH_SECONDS",
    "FALLBACK_UI_ACTION_ROUTES",
    "FALLBACK_UI_PAGE_ROUTES",
    "dispatch_gui_action",
    "main",
    "register",
    "render_app",
]