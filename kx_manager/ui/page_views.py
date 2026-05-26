# kx_manager/ui/page_views.py

"""Thin page orchestrator for the Konnaxion Capsule Manager browser UI.

This module owns route normalization, PageView lookup, and HTMLResponse
construction. Actual page bodies live under kx_manager.ui.page_parts.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from fastapi.responses import HTMLResponse

from kx_manager.ui.page_parts import (
    PAGE_PART_BUILDERS,
    about,
    backups,
    capsules,
    dashboard,
    deploy,
    health,
    instances,
    logs,
    network,
    render_not_found,
    restore,
    security,
    settings,
    targets,
)
from kx_manager.ui.render import html_response

try:
    from kx_manager.ui.static import (
        NAV_ITEMS,
        PAGE_TITLES,
        UI_BASE_PATH,
        UI_PAGE_ROUTES,
        title_for_route,
    )
except Exception:  # pragma: no cover - staged build compatibility
    UI_BASE_PATH = "/ui"

    UI_PAGE_ROUTES = (
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

    PAGE_TITLES = {
        "/ui": "Dashboard",
        "/ui/capsules": "Capsules",
        "/ui/instances": "Instances",
        "/ui/security": "Security",
        "/ui/network": "Network",
        "/ui/backups": "Backups",
        "/ui/restore": "Restore",
        "/ui/logs": "Logs",
        "/ui/health": "Health",
        "/ui/settings": "Settings",
        "/ui/targets": "Targets",
        "/ui/deploy": "Deploy",
        "/ui/about": "About",
    }

    NAV_ITEMS = (
        ("Dashboard", "/ui"),
        ("Capsules", "/ui/capsules"),
        ("Instances", "/ui/instances"),
        ("Targets", "/ui/targets"),
        ("Deploy", "/ui/deploy"),
        ("Security", "/ui/security"),
        ("Network", "/ui/network"),
        ("Backups", "/ui/backups"),
        ("Restore", "/ui/restore"),
        ("Logs", "/ui/logs"),
        ("Health", "/ui/health"),
        ("Settings", "/ui/settings"),
        ("About", "/ui/about"),
    )

    def title_for_route(route: str) -> str:
        return PAGE_TITLES.get(route, "Dashboard")


PAGE_ROUTES: tuple[str, ...] = (
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

PageBuilder = Callable[[Mapping[str, Any]], str]


@dataclass(frozen=True, slots=True)
class PageView:
    route: str
    title: str
    subtitle: str
    builder: PageBuilder


PAGE_VIEWS: dict[str, PageView] = {
    "/ui": PageView(
        "/ui",
        title_for_route("/ui"),
        "Local capsule, instance, security, network, backup, and deployment control.",
        dashboard.render,
    ),
    "/ui/capsules": PageView(
        "/ui/capsules",
        title_for_route("/ui/capsules"),
        "Build, verify, import, list, and inspect Konnaxion Capsules.",
        capsules.render,
    ),
    "/ui/instances": PageView(
        "/ui/instances",
        title_for_route("/ui/instances"),
        "Create, update, start, stop, inspect, and rollback instances.",
        instances.render,
    ),
    "/ui/security": PageView(
        "/ui/security",
        title_for_route("/ui/security"),
        "Run Security Gate checks before risky lifecycle operations.",
        security.render,
    ),
    "/ui/network": PageView(
        "/ui/network",
        title_for_route("/ui/network"),
        "Set private-by-default network profiles and disable public exposure.",
        network.render,
    ),
    "/ui/backups": PageView(
        "/ui/backups",
        title_for_route("/ui/backups"),
        "Create, list, and verify backups.",
        backups.render,
    ),
    "/ui/restore": PageView(
        "/ui/restore",
        title_for_route("/ui/restore"),
        "Restore backups safely, including test restore and restore-new flows.",
        restore.render,
    ),
    "/ui/logs": PageView(
        "/ui/logs",
        title_for_route("/ui/logs"),
        "View instance runtime logs.",
        logs.render,
    ),
    "/ui/health": PageView(
        "/ui/health",
        title_for_route("/ui/health"),
        "Inspect Manager, Agent, instance, and runtime health.",
        health.render,
    ),
    "/ui/settings": PageView(
        "/ui/settings",
        title_for_route("/ui/settings"),
        "Set local source and capsule output folders.",
        settings.render,
    ),
    "/ui/targets": PageView(
        "/ui/targets",
        title_for_route("/ui/targets"),
        "Choose where this capsule should run: local, intranet, temporary public, or Droplet.",
        targets.render,
    ),
    "/ui/deploy": PageView(
        "/ui/deploy",
        title_for_route("/ui/deploy"),
        "Run local, intranet, and Droplet deployment operations.",
        deploy.render,
    ),
    "/ui/about": PageView(
        "/ui/about",
        title_for_route("/ui/about"),
        "Konnaxion Capsule Manager information and safety boundary.",
        about.render,
    ),
}


def render_page_response(
    route: str,
    *,
    context: Mapping[str, Any] | None = None,
    result: Any | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render a /ui route as a FastAPI HTMLResponse."""

    normalized_route = normalize_ui_route(route)
    page = get_page_view(normalized_route)
    data = dict(context or {})

    return html_response(
        page.title,
        page.builder(data),
        subtitle=page.subtitle,
        active_href=normalized_route,
        nav_items=nav_items(normalized_route),
        result=result,
        status_code=status_code,
    )


def render_page_html(
    route: str,
    *,
    context: Mapping[str, Any] | None = None,
    result: Any | None = None,
) -> str:
    """Render a /ui route and return raw HTML text."""

    response = render_page_response(route, context=context, result=result)
    return response.body.decode(response.charset or "utf-8")


def render_ui_page(
    route: str,
    *,
    context: Mapping[str, Any] | None = None,
    result: Any | None = None,
) -> HTMLResponse:
    """Compatibility alias for route handlers."""

    return render_page_response(route, context=context, result=result)


def normalize_ui_route(route: str | None) -> str:
    """Normalize a browser UI path to a known page route."""

    value = (route or UI_BASE_PATH).strip() or UI_BASE_PATH

    if value == "/":
        return UI_BASE_PATH

    if value.endswith("/") and value != UI_BASE_PATH:
        value = value.rstrip("/")

    if value not in PAGE_ROUTES:
        return UI_BASE_PATH

    return value


def get_page_view(route: str) -> PageView:
    """Return the PageView for a normalized route."""

    return PAGE_VIEWS.get(normalize_ui_route(route), PAGE_VIEWS[UI_BASE_PATH])


def nav_items(active_href: str) -> list[dict[str, Any]]:
    """Return nav items marked active for the current route."""

    return [
        {
            "label": label,
            "href": href,
            "active": href == active_href,
        }
        for label, href in NAV_ITEMS
    ]


def not_found_view(context: Mapping[str, Any]) -> str:
    return render_not_found(context)


# Defensive check for staged builds: the orchestrator and page-part registry must
# agree on the canonical route set.
if set(PAGE_PART_BUILDERS) != set(PAGE_ROUTES):  # pragma: no cover
    missing = sorted(set(PAGE_ROUTES) - set(PAGE_PART_BUILDERS))
    extra = sorted(set(PAGE_PART_BUILDERS) - set(PAGE_ROUTES))
    raise RuntimeError(f"page-part route mismatch: missing={missing!r} extra={extra!r}")


__all__ = [
    "PAGE_ROUTES",
    "PAGE_VIEWS",
    "PageBuilder",
    "PageView",
    "get_page_view",
    "nav_items",
    "normalize_ui_route",
    "not_found_view",
    "render_page_html",
    "render_page_response",
    "render_ui_page",
]