# kx_manager/ui/page_forms.py

"""Compatibility facade for page-local HTML form rendering.

Page body ownership now lives in kx_manager.ui.page_parts. This module keeps the
older page_forms import surface stable while avoiding a second page orchestrator.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from kx_manager.ui.page_parts import render_page_body
from kx_manager.ui.page_parts import (
    about,
    backups,
    capsules,
    dashboard,
    health,
    instances,
    logs,
    network,
    restore,
    security,
    settings,
    targets,
)
from kx_manager.ui.page_parts.common import action_form, button_form, default_payload


def render_page_forms(route: str, data: Mapping[str, Any] | None = None) -> str:
    """Render the page body/forms for a /ui route."""

    return render_page_body(route, dict(data or {}))


def render_dashboard_forms(data: Mapping[str, Any] | None = None) -> str:
    return dashboard.render(dict(data or {}))


def render_capsule_forms(data: Mapping[str, Any] | None = None) -> str:
    return capsules.render(dict(data or {}))


def render_instance_forms(data: Mapping[str, Any] | None = None) -> str:
    return instances.render(dict(data or {}))


def render_security_forms(data: Mapping[str, Any] | None = None) -> str:
    return security.render(dict(data or {}))


def render_network_forms(data: Mapping[str, Any] | None = None) -> str:
    return network.render(dict(data or {}))


def render_backup_forms(data: Mapping[str, Any] | None = None) -> str:
    return backups.render(dict(data or {}))


def render_restore_forms(data: Mapping[str, Any] | None = None) -> str:
    return restore.render(dict(data or {}))


def render_logs_forms(data: Mapping[str, Any] | None = None) -> str:
    return logs.render(dict(data or {}))


def render_health_forms(data: Mapping[str, Any] | None = None) -> str:
    return health.render(dict(data or {}))


def render_settings_forms(data: Mapping[str, Any] | None = None) -> str:
    return settings.render(dict(data or {}))


def render_target_forms(data: Mapping[str, Any] | None = None) -> str:
    return targets.render(dict(data or {}))


def render_about_forms(data: Mapping[str, Any] | None = None) -> str:
    return about.render(dict(data or {}))


def form_for_action(action: str, data: Mapping[str, Any] | None = None) -> str:
    """Render a small compatibility form for a single canonical GUI action.

    Detailed page-owned forms now live in page_parts. This helper remains for
    tests or older callers that need a standalone action form.
    """

    payload = default_payload(dict(data or {}))
    value = str(action).strip()

    if value.startswith("open_") or value in {"check_manager", "check_agent", "list_capsules"}:
        return button_form(value, payload=payload)

    return action_form(value, hidden=payload)


BACKUP_CLASS_OPTIONS: tuple[str, ...] = (
    "manual",
    "scheduled_daily",
    "scheduled_weekly",
    "scheduled_monthly",
    "pre_update",
    "pre_restore",
)

TARGET_MODE_OPTIONS: tuple[str, ...] = (
    "local",
    "intranet",
    "temporary_public",
    "droplet",
)


__all__ = [
    "BACKUP_CLASS_OPTIONS",
    "TARGET_MODE_OPTIONS",
    "form_for_action",
    "render_about_forms",
    "render_backup_forms",
    "render_capsule_forms",
    "render_dashboard_forms",
    "render_health_forms",
    "render_instance_forms",
    "render_logs_forms",
    "render_network_forms",
    "render_page_forms",
    "render_restore_forms",
    "render_security_forms",
    "render_settings_forms",
    "render_target_forms",
]
