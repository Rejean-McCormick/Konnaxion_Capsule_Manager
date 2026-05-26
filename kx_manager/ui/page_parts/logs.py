# kx_manager/ui/page_parts/logs.py

"""Logs page body for the Konnaxion Capsule Manager GUI."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from kx_manager.ui.form_constants import DEFAULT_INSTANCE_ID
from kx_manager.ui.page_parts.common import (
    action_form,
    context_value,
    field,
    instance_id_field,
    service_options,
)
from kx_manager.ui.render import render_card, render_grid


def render(context: Mapping[str, Any]) -> str:
    """Render the Logs page body."""

    form = action_form(
        "view_logs",
        [
            instance_id_field(context_value(context, "instance_id", default=DEFAULT_INSTANCE_ID)),
            field(
                "service",
                "Service",
                "",
                field_type="select",
                required=False,
                options=service_options(),
            ),
            field("lines", "Lines", 200, field_type="number"),
            field("tail", "Tail logs", True, field_type="checkbox"),
        ],
        submit_label="View Logs",
    )

    return render_grid(
        [
            render_card("Logs", form),
            render_card(
                "Log Scope",
                "<p>Select a service or leave blank to request all available instance logs.</p>",
            ),
        ]
    )


__all__ = ["render"]
