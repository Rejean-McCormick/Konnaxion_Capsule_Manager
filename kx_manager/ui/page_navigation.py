"""
Navigation helpers for the Konnaxion Capsule Manager UI.

This module owns framework-neutral page lookup, route normalization,
navigation grouping, and breadcrumb construction.

It depends only on page type definitions and the canonical page registry.
"""

from __future__ import annotations

from kx_manager.ui.page_registry import PAGE_REGISTRY
from kx_manager.ui.page_types import (
    NavigationGroup,
    PageContext,
    PageDefinition,
    PageGroup,
    PageId,
)


_PAGE_BY_ID: dict[PageId, PageDefinition] = {
    page.page_id: page for page in PAGE_REGISTRY
}

_PAGE_BY_ROUTE: dict[str, PageDefinition] = {
    page.route: page for page in PAGE_REGISTRY
}

_GROUP_LABELS: dict[PageGroup, str] = {
    PageGroup.OVERVIEW: "Overview",
    PageGroup.OPERATIONS: "Operations",
    PageGroup.SAFETY: "Safety",
    PageGroup.SYSTEM: "System",
}


def get_page(page_id: PageId | str) -> PageDefinition:
    """Return a page definition by canonical page id."""

    normalized = PageId(page_id)

    try:
        return _PAGE_BY_ID[normalized]
    except KeyError as exc:
        raise KeyError(f"Unknown page: {page_id}") from exc


def find_page_by_route(route: str) -> PageDefinition:
    """Return the page matching a route, falling back to dashboard."""

    normalized = normalize_route(route)
    return _PAGE_BY_ROUTE.get(normalized, get_page(PageId.DASHBOARD))


def normalize_route(route: str) -> str:
    """Normalize a UI route to canonical slash-prefixed form."""

    if not route:
        return "/"

    normalized = route.strip()

    if not normalized.startswith("/"):
        normalized = f"/{normalized}"

    if normalized != "/":
        normalized = normalized.rstrip("/")

    return normalized


def build_navigation(
    *,
    selected_instance_id: str | None = None,
    include_hidden: bool = False,
) -> list[NavigationGroup]:
    """Build navigation groups for the current UI context."""

    pages = [
        page
        for page in PAGE_REGISTRY
        if (include_hidden or page.visible_in_nav)
        and (not page.requires_instance or selected_instance_id is not None)
    ]

    groups: list[NavigationGroup] = []

    for group in PageGroup:
        grouped_pages = sorted(
            [page for page in pages if page.group == group],
            key=lambda item: item.order,
        )

        if grouped_pages:
            groups.append(
                NavigationGroup(
                    group=group,
                    label=_GROUP_LABELS[group],
                    pages=tuple(grouped_pages),
                )
            )

    return groups


def build_breadcrumbs(
    page: PageDefinition,
    context: PageContext | None = None,
) -> tuple[str, ...]:
    """Build display breadcrumbs for a page and optional selected instance."""

    crumbs = ["Konnaxion Capsule Manager"]

    if page.group != PageGroup.OVERVIEW:
        crumbs.append(page.group.value.replace("_", " ").title())

    crumbs.append(page.title)

    if context and context.selected_instance_id and page.requires_instance:
        crumbs.append(context.selected_instance_id)

    return tuple(crumbs)


__all__ = [
    "build_breadcrumbs",
    "build_navigation",
    "find_page_by_route",
    "get_page",
    "normalize_route",
]