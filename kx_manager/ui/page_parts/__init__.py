# kx_manager/ui/page_parts/__init__.py

"""Flat page-body renderer registry for Konnaxion Manager UI pages."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from kx_manager.ui.page_parts import (
    about,
    backups,
    capsules,
    dashboard,
    deploy,
    health,
    instances,
    logs,
    network,
    restore,
    security,
    settings,
    targets,
)
from kx_manager.ui.render import render_empty_state

PageBodyBuilder = Callable[[Mapping[str, Any]], str]

PAGE_PART_BUILDERS: dict[str, PageBodyBuilder] = {
    "/ui": dashboard.render,
    "/ui/capsules": capsules.render,
    "/ui/instances": instances.render,
    "/ui/security": security.render,
    "/ui/network": network.render,
    "/ui/backups": backups.render,
    "/ui/restore": restore.render,
    "/ui/logs": logs.render,
    "/ui/health": health.render,
    "/ui/settings": settings.render,
    "/ui/targets": targets.render,
    "/ui/deploy": deploy.render,
    "/ui/about": about.render,
}


def normalize_page_part_route(route: str | None) -> str:
    value = (route or "/ui").strip() or "/ui"

    if value == "/":
        return "/ui"

    if value.endswith("/") and value != "/ui":
        value = value.rstrip("/")

    return value


def render_not_found(context: Mapping[str, Any] | None = None) -> str:
    del context

    return render_empty_state(
        "Unknown UI page.",
        detail="Use the top navigation to choose a known Manager GUI page.",
    )


def render_page_body(
    route: str,
    context: Mapping[str, Any] | None = None,
) -> str:
    normalized = normalize_page_part_route(route)
    builder = PAGE_PART_BUILDERS.get(normalized)

    if builder is None:
        return render_not_found(context)

    return builder(dict(context or {}))


__all__ = [
    "PAGE_PART_BUILDERS",
    "PageBodyBuilder",
    "normalize_page_part_route",
    "render_not_found",
    "render_page_body",
]